"""Incident enrichment agent for Brand Watcher.

Given an incident, gathers related content and STAGES it for human review —
nothing enters the append-only evidence locker until an analyst confirms it
(the locker is hash-chained and unpurgeable, so agent output must not land
there directly):

  1. story-group siblings of already-attached articles (bw_article_stories)
  2. vector-similar articles (pgvector KNN over the incident text + seeds)
  3. brand-matched social posts inside the incident window
  4. account profiles of the authors behind attached/related social posts
  5. an LLM incident brief, stored on the run row (attachable on request)

Separately from the staging flow, already-ATTACHED locker articles are sent
through the Five Signals screen (bw_signals_service → saas.aunoo.ai): results
land per-article in bw_article_signals, the same rows the /signals UI reads.
Screens are skipped without the saas key, deduped against existing rows, and
capped per run — each fresh screen costs saas-side LLM + web-search quota.

Candidates land in bw_incident_enrichment_candidates with a UNIQUE
(incident_id, candidate_type, source_ref) constraint, so anything already
staged — including analyst-dismissed items — is never re-proposed.

Assistive triage (user-confirmed 2026-07-15): after staging, an LLM pass
scores each pending candidate against the incident. Clear noise
(< TRIAGE_DISMISS_BELOW) is auto-dismissed with decided_by='agent:triage';
strong matches (>= TRIAGE_RECOMMEND_AT) get recommendation='attach' for a
one-click human accept. The agent also posts merge/severity SUGGESTIONS as
'agent_suggestion' timeline events. It never writes the locker itself.

Modeled on bw_signals_service: a never-raises BackgroundTasks/monitor target;
the outcome lands on the bw_incident_enrichment_runs row. No DB connection is
held across the slow parts (vector search, xpoz profile builds, LLM call) —
each phase uses a fresh short-lived connection.
"""

import asyncio
import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

from app.services.social_sources import is_social_source, social_src_sql

logger = logging.getLogger(__name__)

MAX_ARTICLE_CANDIDATES = 15
MAX_SOCIAL_CANDIDATES = 10
MAX_PROFILE_CANDIDATES = 5
VECTOR_MIN_SIMILARITY = 0.55   # search_articles returns cosine DISTANCE; sim = 1 - distance
MIN_ALIGNMENT = 0.4
MAX_NEW_PROFILE_BUILDS = 3     # each build costs xpoz + LLM calls
MAX_KEYWORDS = 10
WINDOW_PAD_DAYS = 7            # window = created_at - pad .. (resolved_at or now)
BRIEF_MODEL = os.getenv("BW_ENRICH_BRIEF_MODEL", "gpt-5.4")
BRIEF_INPUT_CAP = 12000
MAX_SIGNAL_SCREENS = int(os.getenv("BW_ENRICH_MAX_SIGNAL_SCREENS", "5"))

# Assistive triage (user-confirmed 2026-07-15): the agent may auto-DISMISS
# clear noise (candidates table only) and RECOMMEND attaches, but never
# writes the evidence locker itself — attaching stays a human action.
TRIAGE_MODEL = os.getenv("BW_TRIAGE_MODEL", "gpt-5.4-mini")
TRIAGE_DISMISS_BELOW = float(os.getenv("BW_TRIAGE_DISMISS_BELOW", "0.3"))
TRIAGE_RECOMMEND_AT = float(os.getenv("BW_TRIAGE_RECOMMEND_AT", "0.7"))
TRIAGE_MAX_PER_RUN = int(os.getenv("BW_TRIAGE_MAX_PER_RUN", "80"))
TRIAGE_CHUNK = 25

STR_CAP = 2000
LIST_CAP = 12


def _trim(obj: Any, depth: int = 0) -> Any:
    """Cap list lengths and string sizes recursively before JSONB storage."""
    if depth > 6:
        return None
    if isinstance(obj, str):
        return obj[:STR_CAP]
    if isinstance(obj, list):
        return [_trim(v, depth + 1) for v in obj[:LIST_CAP]]
    if isinstance(obj, dict):
        return {k: _trim(v, depth + 1) for k, v in obj.items()}
    return obj


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _run_update(run_id: int, **cols) -> None:
    sets, params = [], {"id": run_id}
    for k, v in cols.items():
        sets.append(f"{k} = :{k}")
        params[k] = json.dumps(_trim(v)) if k in ("stats", "params") and v is not None else v
    conn = _conn()
    try:
        conn.execute(text(
            f"UPDATE bw_incident_enrichment_runs SET {', '.join(sets)} WHERE id = :id"), params)
        conn.commit()
    finally:
        conn.close()


def _stage(run_id: int, stage: str) -> None:
    _run_update(run_id, stage=stage)


def _event(conn, incident_id: int, kind: str, actor: str, note: Optional[str] = None) -> None:
    conn.execute(text("""
        INSERT INTO bw_incident_events (incident_id, kind, actor, note)
        VALUES (:i, :k, :a, :n)
    """), {"i": incident_id, "k": kind, "a": actor, "n": note})


def _jload(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return None


# ─── Gather stages ───────────────────────────────────────────────────────────

def _load_context(incident_id: int) -> Optional[Dict]:
    """Incident + brand + evidence refs + already-staged refs, in one connection."""
    conn = _conn()
    try:
        r = conn.execute(text("""
            SELECT i.id, i.brand_id, i.title, i.description, i.severity, i.status,
                   i.created_at, i.resolved_at, b.name, b.display_name,
                   b.brand_keywords, b.product_keywords, b.people_keywords
            FROM bw_incidents i JOIN bw_brands b ON b.id = i.brand_id
            WHERE i.id = :i
        """), {"i": incident_id}).fetchone()
        if not r:
            return None
        evidence = conn.execute(text("""
            SELECT evidence_type, source_ref, title, meta, captured_at
            FROM bw_incident_evidence WHERE incident_id = :i ORDER BY id
        """), {"i": incident_id}).fetchall()
        staged = conn.execute(text("""
            SELECT candidate_type, source_ref FROM bw_incident_enrichment_candidates
            WHERE incident_id = :i
        """), {"i": incident_id}).fetchall()

        def _kw(v):
            return v if isinstance(v, list) else (_jload(v) or [])

        seen: Set[str] = set()
        seed_uris: List[str] = []
        attached_article_urls: List[str] = []
        attached_social_meta: List[Dict] = []
        ev_summaries: List[Dict] = []
        for etype, ref, title, meta, cap_at in evidence:
            meta = _jload(meta) or {}
            if ref:
                seen.add(ref)
            if meta.get("uri"):
                seen.add(meta["uri"])
            if etype in ("article", "social_post") and ref:
                seed_uris.append(ref)
            # Five Signals needs a public article URL (same guard as the
            # /signals/run route — social posts are not screenable)
            if (etype == "article" and ref
                    and str(ref).lower().startswith(("http://", "https://"))
                    and ref not in attached_article_urls):
                attached_article_urls.append(ref)
            if etype == "social_post":
                attached_social_meta.append(meta)
            if etype == "account_profile" and meta.get("platform") and meta.get("handle"):
                seen.add(f"{meta['platform']}:{meta['handle']}")
            ev_summaries.append({"type": etype, "title": title,
                                 "date": meta.get("publication_date"),
                                 "source": meta.get("news_source")})
        for _ctype, ref in staged:
            seen.add(ref)

        created_at, resolved_at = r[6], r[7]
        w_start = (created_at - timedelta(days=WINDOW_PAD_DAYS)).strftime("%Y-%m-%d") if created_at else "1970-01-01"
        w_end = (resolved_at.strftime("%Y-%m-%d") if resolved_at else "9999-12-31")
        keywords = [k for k in
                    ([r[9], r[8]] + _kw(r[10]) + _kw(r[11]) + _kw(r[12]))
                    if k and isinstance(k, str)]
        dedup_kw, seen_kw = [], set()
        for k in keywords:
            if k.lower() not in seen_kw:
                seen_kw.add(k.lower())
                dedup_kw.append(k)
        return {
            "id": r[0], "brand_id": r[1], "title": r[2], "description": r[3],
            "severity": r[4], "status": r[5],
            "window": (w_start, w_end),
            "brand_name": r[9] or r[8],
            "keywords": dedup_kw[:MAX_KEYWORDS],
            "seen": seen, "seed_uris": seed_uris[:20],
            "attached_article_urls": attached_article_urls,
            "attached_social_meta": attached_social_meta,
            "evidence_summaries": ev_summaries,
        }
    finally:
        conn.close()


def _story_siblings(ctx: Dict) -> List[Dict]:
    if not ctx["seed_uris"]:
        return []
    conn = _conn()
    try:
        rows = conn.execute(text("""
            SELECT DISTINCT a.uri, a.title, a.summary, a.news_source,
                            a.publication_date, a.topic_alignment_score, a.social_meta
            FROM bw_article_stories s1
            JOIN bw_article_stories s2
              ON s2.story_group_id = s1.story_group_id AND s2.brand_id = s1.brand_id
            JOIN articles a ON a.uri = s2.article_uri
            WHERE s1.article_uri = ANY(:seeds) AND s1.brand_id = :b
        """), {"seeds": ctx["seed_uris"], "b": ctx["brand_id"]}).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        if r[0] in ctx["seen"]:
            continue
        out.append(_article_candidate(r, reason="story-group sibling of attached article",
                                      score=r[5]))
    return out


def _article_candidate(row, reason: str, score) -> Dict:
    social = is_social_source(row[3])
    sm = _jload(row[6]) or {}
    return {
        "candidate_type": "social_post" if social else "article",
        "source_ref": row[0],
        "title": row[1],
        "snippet": (row[2] or "")[:400],
        "score": round(float(score), 3) if score is not None else None,
        "reason": reason,
        "meta": {"news_source": row[3],
                 "publication_date": str(row[4]) if row[4] else None,
                 "platform": sm.get("platform"), "author": sm.get("author")},
    }


async def _vector_similar(ctx: Dict) -> List[Dict]:
    from app.vector_store import search_articles
    seeds = ""
    if ctx["seed_uris"]:
        conn = _conn()
        try:
            rows = conn.execute(text(
                "SELECT title FROM articles WHERE uri = ANY(:u) LIMIT 3"
            ), {"u": ctx["seed_uris"][:3]}).fetchall()
        finally:
            conn.close()
        seeds = ". ".join(r[0] for r in rows if r[0])
    query = f"{ctx['title']}. {ctx['description'] or ''} {seeds}".strip()
    try:
        hits = await asyncio.to_thread(search_articles, query, 30)
    except Exception as e:  # noqa: BLE001
        logger.warning("Enrichment vector search failed: %s", e)
        return []
    w_start, w_end = ctx["window"]
    out = []
    for h in hits or []:
        uri = h.get("id")
        if not uri or uri in ctx["seen"]:
            continue
        sim = 1.0 - float(h.get("score") or 1.0)
        if sim < VECTOR_MIN_SIMILARITY:
            continue
        md = h.get("metadata") or {}
        pub = str(md.get("publication_date") or "")
        if pub and not (w_start <= pub[:10] <= w_end):
            continue
        social = is_social_source(md.get("news_source"))
        out.append({
            "candidate_type": "social_post" if social else "article",
            "source_ref": uri,
            "title": md.get("title"),
            "snippet": (md.get("summary") or "")[:400],
            "score": round(sim, 3),
            "reason": f"vector similarity {sim:.2f}",
            "meta": {"news_source": md.get("news_source"), "publication_date": pub or None},
        })
    return out


def _social_in_window(ctx: Dict) -> List[Dict]:
    w_start, w_end = ctx["window"]
    # publication_date is TEXT ISO; "~" sorts after "T"/" ", so a date-day
    # suffix of "~" makes the <= bound inclusive of that whole day
    kw_clauses, params = [], {"b": ctx["brand_id"], "ws": w_start, "we": w_end + "~"}
    for i, kw in enumerate(ctx["keywords"]):
        kw_clauses.append(f"(a.title ILIKE :kw{i} OR a.summary ILIKE :kw{i})")
        params[f"kw{i}"] = f"%{kw}%"
    brand_match = ("(" + " OR ".join(kw_clauses) +
                   " OR a.uri IN (SELECT article_uri FROM bw_article_risks WHERE brand_id = :b))"
                   ) if kw_clauses else \
        "a.uri IN (SELECT article_uri FROM bw_article_risks WHERE brand_id = :b)"
    conn = _conn()
    try:
        rows = conn.execute(text(f"""
            SELECT a.uri, a.title, a.summary, a.news_source,
                   a.publication_date, a.topic_alignment_score, a.social_meta
            FROM articles a
            WHERE {social_src_sql('a.news_source')}
              AND a.publication_date >= :ws AND a.publication_date <= :we
              AND (a.topic_alignment_score IS NULL OR a.topic_alignment_score >= {MIN_ALIGNMENT})
              AND {brand_match}
            ORDER BY a.publication_date DESC
            LIMIT 60
        """), params).fetchall()
    finally:
        conn.close()
    cands = []
    for r in rows:
        if r[0] in ctx["seen"]:
            continue
        c = _article_candidate(r, reason="brand-matched social post in incident window", score=r[5])
        c["candidate_type"] = "social_post"
        sm = _jload(r[6]) or {}
        c["meta"]["engagement"] = sum(int(sm.get(k) or 0) for k in ("likes", "reposts", "comments"))
        cands.append(c)
    cands.sort(key=lambda c: c["meta"].get("engagement") or 0, reverse=True)
    return cands


async def _author_profiles(ctx: Dict, social_cands: List[Dict]) -> List[Dict]:
    from app.database import get_database_instance
    from app.services.social_profile_service import SocialProfileService, norm_handle
    handles: List[Tuple[str, str]] = []
    hseen: Set[str] = set()
    for m in ctx["attached_social_meta"] + [c["meta"] for c in social_cands]:
        platform, author = (m or {}).get("platform"), (m or {}).get("author")
        if not platform or not author or platform == "social":
            continue
        key = f"{platform.lower()}:{norm_handle(platform, author)}"
        if key in hseen or key in ctx["seen"]:
            continue
        hseen.add(key)
        handles.append((platform.lower(), author))
    if not handles:
        return []
    svc = SocialProfileService()
    db = get_database_instance()
    out, builds = [], 0
    for platform, author in handles[:MAX_PROFILE_CANDIDATES * 2]:
        canon = norm_handle(platform, author)
        try:
            prof = svc.get_stored(db, platform, canon)
            if not prof and builds < MAX_NEW_PROFILE_BUILDS:
                builds += 1
                prof = await svc.build_profile(db, platform, canon, brand=ctx["brand_name"])
        except Exception as e:  # noqa: BLE001
            logger.warning("Enrichment profile %s:%s failed: %s", platform, canon, e)
            continue
        if not prof:
            continue
        out.append({
            "candidate_type": "account_profile",
            "source_ref": f"{platform}:{canon}",
            "title": f"@{prof.get('handle') or canon} on {platform}",
            "snippet": (prof.get("summary") or prof.get("bio") or "")[:400],
            "score": None,
            "reason": f"author of attached/related post (@{canon})",
            "meta": {"platform": platform, "handle": canon, "account_id": prof.get("id"),
                     "display_name": prof.get("display_name"),
                     "avatar_url": prof.get("avatar_url"),
                     "followers_count": prof.get("followers_count")},
        })
        if len(out) >= MAX_PROFILE_CANDIDATES:
            break
    return out


def _stage_candidates(run_id: int, incident_id: int, cands: List[Dict]) -> int:
    if not cands:
        return 0
    conn = _conn()
    staged = 0
    try:
        for c in cands:
            r = conn.execute(text("""
                INSERT INTO bw_incident_enrichment_candidates
                    (run_id, incident_id, candidate_type, source_ref, title, snippet,
                     score, reason, meta)
                VALUES (:r, :i, :t, :sr, :ti, :sn, :sc, :re, CAST(:m AS jsonb))
                ON CONFLICT (incident_id, candidate_type, source_ref) DO NOTHING
                RETURNING id
            """), {"r": run_id, "i": incident_id, "t": c["candidate_type"],
                   "sr": c["source_ref"], "ti": (c.get("title") or "")[:300],
                   "sn": c.get("snippet"), "sc": c.get("score"), "re": c.get("reason"),
                   "m": json.dumps(_trim(c.get("meta") or {}), default=str)}).fetchone()
            if r:
                staged += 1
        conn.commit()
    finally:
        conn.close()
    return staged


async def _write_brief(ctx: Dict, cands: List[Dict]) -> Optional[str]:
    from app.ai_models import LiteLLMModel
    ev_lines = [f"- [{e['type']}] {e['title'] or '(untitled)'}"
                + (f" ({e['date']})" if e.get("date") else "")
                for e in ctx["evidence_summaries"][:30]]
    cand_lines = [f"- [{c['candidate_type']}] {c.get('title') or c['source_ref']}"
                  + (f" — {c.get('reason')}" if c.get("reason") else "")
                  + (f": {c.get('snippet')}" if c.get("snippet") else "")
                  for c in cands[:25]]
    prompt = (
        f"Incident: {ctx['title']}\n"
        f"Brand: {ctx['brand_name']}\nSeverity: {ctx['severity']}  Status: {ctx['status']}\n"
        f"Window: {ctx['window'][0]} to {ctx['window'][1]}\n"
        f"Description: {ctx['description'] or '(none)'}\n\n"
        f"Attached evidence:\n" + ("\n".join(ev_lines) or "(none)") + "\n\n"
        f"Related material found by automated search:\n" + ("\n".join(cand_lines) or "(none)")
    )[:BRIEF_INPUT_CAP]
    try:
        model = LiteLLMModel.get_instance(BRIEF_MODEL)
        brief = await model.agenerate_response([
            {"role": "system", "content":
                "You summarize brand-monitoring incidents for an analyst. Use only the "
                "material provided; never invent sources, numbers, or events. Write plain, "
                "factual prose — no dramatic framing, no marketing language. Markdown with "
                "these sections: ## What happened, ## How it is spreading, ## Key voices, "
                "## Assessment and next steps (max 3 bullets, scoped to what a brand/comms "
                "team can act on). If the material is too thin for a section, say so in one "
                "line rather than padding."},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:  # noqa: BLE001
        logger.warning("Enrichment brief LLM call failed: %s", e)
        return None
    brief = (brief or "").strip()
    # LiteLLMModel signals failure by returning "⚠️ ..." text instead of raising
    if not brief or brief.startswith("⚠️"):
        return None
    return brief


def _parse_triage_json(raw: str) -> List[Dict]:
    """First JSON array in the response — models append trailing prose."""
    start = raw.find("[")
    if start < 0:
        return []
    try:
        parsed, _ = json.JSONDecoder().raw_decode(raw[start:])
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


async def _triage_candidates(ctx: Dict, run_id: int, incident_id: int) -> Dict[str, int]:
    """Score pending candidates against the incident; auto-dismiss noise,
    mark strong ones recommendation='attach'. Never raises.

    Writes only bw_incident_enrichment_candidates — auto-dismissals show up
    in the disposition history as decided_by='agent:triage'; attaching (the
    locker write) remains a human decision.
    """
    from app.ai_models import LiteLLMModel
    stats = {"scored": 0, "auto_dismissed": 0, "recommended": 0}
    conn = _conn()
    try:
        rows = conn.execute(text("""
            SELECT id, candidate_type, title, snippet, reason
            FROM bw_incident_enrichment_candidates
            WHERE incident_id = :i AND state = 'pending' AND triage_score IS NULL
            ORDER BY score DESC NULLS LAST, id
            LIMIT :lim
        """), {"i": incident_id, "lim": TRIAGE_MAX_PER_RUN}).fetchall()
    finally:
        conn.close()
    if not rows:
        return stats

    context = (f"Incident: {ctx['title']}\n"
               f"Brand: {ctx['brand_name']}\n"
               f"Description: {ctx['description'] or '(none)'}\n"
               f"Brand keywords: {', '.join(ctx['keywords'])}")
    try:
        model = LiteLLMModel.get_instance(TRIAGE_MODEL)
    except Exception as e:  # noqa: BLE001
        logger.warning("Triage model unavailable: %s", e)
        return stats

    scored: Dict[int, Tuple[float, str]] = {}
    for off in range(0, len(rows), TRIAGE_CHUNK):
        chunk = rows[off:off + TRIAGE_CHUNK]
        listing = "\n".join(
            f"- id={r[0]} [{r[1]}] {(r[2] or '(untitled)')[:150]}"
            + (f" :: {(r[3] or '')[:200]}" if r[3] else "")
            + (f" (found: {(r[4] or '')[:80]})" if r[4] else "")
            for r in chunk)
        prompt = (
            f"{context}\n\n"
            f"Candidates found by automated search:\n{listing}\n\n"
            "For EACH candidate, judge how relevant it is as evidence for THIS "
            "specific incident (not the brand in general). Score 0.0-1.0: "
            "0.0-0.3 unrelated or generic brand noise; 0.3-0.7 possibly related, "
            "needs a human look; 0.7-1.0 clearly about this incident. "
            "Respond with ONLY a JSON array: "
            '[{"id": <id>, "score": <0.0-1.0>, "why": "<one short sentence>"}]')
        try:
            raw = await model.agenerate_response([
                {"role": "system", "content":
                    "You triage evidence candidates for a brand-monitoring incident. "
                    "Judge only from the material given; be conservative — when unsure, "
                    "score in the middle band so a human reviews it. JSON only."},
                {"role": "user", "content": prompt},
            ])
        except Exception as e:  # noqa: BLE001
            logger.warning("Triage LLM call failed: %s", e)
            continue
        if not raw or raw.startswith("⚠️"):
            continue
        valid_ids = {r[0] for r in chunk}
        for item in _parse_triage_json(raw):
            try:
                cid, sc = int(item["id"]), float(item["score"])
            except (KeyError, TypeError, ValueError):
                continue
            if cid in valid_ids and 0.0 <= sc <= 1.0:
                scored[cid] = (sc, str(item.get("why") or "")[:300])

    if not scored:
        return stats
    conn = _conn()
    try:
        for cid, (sc, why) in scored.items():
            if sc < TRIAGE_DISMISS_BELOW:
                r = conn.execute(text("""
                    UPDATE bw_incident_enrichment_candidates
                    SET triage_score = :s, triage_rationale = :w,
                        state = 'dismissed', decided_by = 'agent:triage', decided_at = NOW()
                    WHERE id = :id AND state = 'pending'
                    RETURNING id
                """), {"s": sc, "w": why, "id": cid}).fetchone()
                if r:
                    stats["auto_dismissed"] += 1
            else:
                rec = "attach" if sc >= TRIAGE_RECOMMEND_AT else None
                conn.execute(text("""
                    UPDATE bw_incident_enrichment_candidates
                    SET triage_score = :s, triage_rationale = :w, recommendation = :r
                    WHERE id = :id AND state = 'pending'
                """), {"s": sc, "w": why, "r": rec, "id": cid})
                if rec:
                    stats["recommended"] += 1
        conn.commit()
    finally:
        conn.close()
    stats["scored"] = len(scored)
    return stats


def _post_suggestions(ctx: Dict, incident_id: int) -> int:
    """Deterministic merge/severity suggestions as timeline events (once each).

    Suggestions only — no state is changed. Never raises past the caller's
    guard; dedupes by note prefix so re-runs don't spam the timeline.
    """
    posted = 0
    conn = _conn()
    try:
        existing = {r[0] for r in conn.execute(text(
            "SELECT note FROM bw_incident_events"
            " WHERE incident_id = :i AND kind = 'agent_suggestion'"
        ), {"i": incident_id}).fetchall()}

        # Possible duplicate: another open incident of the same brand sharing
        # locker evidence.
        dup = conn.execute(text("""
            SELECT DISTINCT i2.id, i2.title
            FROM bw_incident_evidence e1
            JOIN bw_incident_evidence e2
              ON e2.source_ref = e1.source_ref AND e2.incident_id != e1.incident_id
            JOIN bw_incidents i2 ON i2.id = e2.incident_id
              AND i2.brand_id = :b AND i2.status IN ('open', 'investigating')
            WHERE e1.incident_id = :i AND e1.source_ref IS NOT NULL
              AND e1.source_ref != ''
        """), {"i": incident_id, "b": ctx["brand_id"]}).fetchall()
        for other_id, other_title in dup:
            note = (f"possible duplicate of incident #{other_id} ('{(other_title or '')[:80]}')"
                    f" — they share attached evidence; consider merging")
            if not any(n and n.startswith(f"possible duplicate of incident #{other_id} ") for n in existing):
                _event(conn, incident_id, "agent_suggestion", "agent:triage", note=note)
                posted += 1

        # Severity sanity-check: high/critical incident whose screened
        # attachments all came back without a confirmed/coordinated verdict.
        if ctx["severity"] in ("high", "critical"):
            vr = conn.execute(text("""
                SELECT s.verdict FROM bw_incident_evidence e
                JOIN bw_article_signals s
                  ON s.article_uri = e.source_ref AND s.brand_id = :b
                     AND s.status = 'completed' AND s.verdict IS NOT NULL
                WHERE e.incident_id = :i
            """), {"i": incident_id, "b": ctx["brand_id"]}).fetchall()
            verdicts = [r[0] for r in vr]
            risky = {"corroborated", "contested", "likely_coordinated"}
            if verdicts and not (set(verdicts) & risky):
                note = (f"severity review: all {len(verdicts)} screened attachment(s) returned "
                        f"low-risk verdicts ({', '.join(sorted(set(verdicts)))}) — "
                        f"consider whether '{ctx['severity']}' still fits")
            else:
                note = None
            if note and not any(n and n.startswith("severity review:") for n in existing):
                _event(conn, incident_id, "agent_suggestion", "agent:triage", note=note)
                posted += 1
        conn.commit()
    finally:
        conn.close()
    return posted


async def _screen_attached_articles(ctx: Dict, requested_by: str) -> Dict[str, int]:
    """Five Signals screens for the incident's attached locker articles.

    Results land per-article in bw_article_signals (bw_signals_service owns the
    row lifecycle and never raises); this only decides which attachments are
    screenable and caps the fan-out. Screens with an existing running/completed
    row are skipped — failed ones get retried. Never raises.
    """
    stats = {"eligible": 0, "screened": 0, "already_screened": 0}
    try:
        from app.services.bw_signals_service import run_five_signals, signals_available
        urls = ctx["attached_article_urls"]
        stats["eligible"] = len(urls)
        if not urls or not signals_available():
            return stats
        def _already_screened(url: str) -> bool:
            # Same rule as the /signals/run cached-return: a completed row only
            # counts when BOTH engine payloads landed — a ceiling-timeout run
            # composes from xnet alone and should be retried next time. Checked
            # per-URL right before each screen (screens take minutes; another
            # run — the same article can be attached to several incidents —
            # may have screened it since this run started).
            conn = _conn()
            try:
                return bool(conn.execute(text("""
                    SELECT 1 FROM bw_article_signals
                    WHERE article_uri = :u AND brand_id = :b
                      AND (status = 'running'
                           OR (status = 'completed'
                               AND validation IS NOT NULL AND reach IS NOT NULL))
                """), {"u": url, "b": ctx["brand_id"]}).fetchone())
            finally:
                conn.close()

        # Sequential on purpose: saas runs screen jobs from a small worker
        # pool, and concurrent screens starve each other into the 600s job
        # ceiling (observed: 2 parallel screens = all 4 jobs timing out).
        # run_five_signals never raises. requested_by is 'agent:…', NOT
        # 'auto' — the monitor's AUTO_SIGNALS_DAILY_CAP counts only 'auto'.
        for u in urls:
            if stats["screened"] >= MAX_SIGNAL_SCREENS:
                break
            if _already_screened(u):
                stats["already_screened"] += 1
                continue
            await run_five_signals(u, ctx["brand_id"], u,
                                   requested_by=f"agent:{requested_by}")
            stats["screened"] += 1
    except Exception as e:  # noqa: BLE001
        logger.warning("Enrichment Five Signals screening failed: %s", e)
    return stats


# ─── Entry point ─────────────────────────────────────────────────────────────

async def run_incident_enrichment(run_id: int, incident_id: int,
                                  requested_by: str = "user") -> None:
    """BackgroundTasks / monitor-loop target — never raises; the outcome lands
    on the bw_incident_enrichment_runs row."""
    try:
        _stage(run_id, "loading incident context")
        ctx = _load_context(incident_id)
        if not ctx:
            conn = _conn()
            try:
                conn.execute(text("""
                    UPDATE bw_incident_enrichment_runs
                    SET status = 'failed', stage = NULL, error = 'Incident not found',
                        finished_at = NOW()
                    WHERE id = :id
                """), {"id": run_id})
                conn.commit()
            finally:
                conn.close()
            return

        # Kicked off first: the saas jobs poll for minutes, so they overlap the
        # gather/brief phases instead of extending the run. Awaited at the end.
        signals_task = asyncio.create_task(
            _screen_attached_articles(ctx, requested_by))

        _stage(run_id, "finding story-group siblings")
        siblings = _story_siblings(ctx)

        _stage(run_id, "searching for similar coverage")
        vector = await _vector_similar(ctx)

        _stage(run_id, "gathering social posts in the incident window")
        social = _social_in_window(ctx)

        # rank + cap per type across gather stages (siblings outrank vector hits
        # at equal score by coming first — stable sort keeps that order)
        articles = [c for c in siblings + vector if c["candidate_type"] == "article"]
        socials = ([c for c in siblings + vector if c["candidate_type"] == "social_post"]
                   + social)
        articles.sort(key=lambda c: c.get("score") or 0, reverse=True)
        seen_refs: Set[str] = set()
        def _dedupe(cands):
            out = []
            for c in cands:
                if c["source_ref"] in seen_refs:
                    continue
                seen_refs.add(c["source_ref"])
                out.append(c)
            return out
        articles = _dedupe(articles)[:MAX_ARTICLE_CANDIDATES]
        socials = _dedupe(socials)[:MAX_SOCIAL_CANDIDATES]

        _stage(run_id, "profiling post authors")
        profiles = await _author_profiles(ctx, socials)

        _stage(run_id, "staging candidates for review")
        cands = articles + socials + profiles
        staged = _stage_candidates(run_id, incident_id, cands)

        _stage(run_id, "triaging candidates and writing brief")
        triage_task = asyncio.create_task(_triage_candidates(ctx, run_id, incident_id))
        brief = await _write_brief(ctx, cands)
        triage = await triage_task

        try:
            suggestions = _post_suggestions(ctx, incident_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("Enrichment suggestions failed: %s", e)
            suggestions = 0

        _stage(run_id, "screening attached articles (Five Signals)")
        sig = await signals_task

        stats = {"story_siblings": len(siblings), "vector_similar": len(vector),
                 "social_posts": len(socials), "profiles": len(profiles),
                 "candidates_found": len(cands), "staged_new": staged,
                 "brief": bool(brief),
                 "triage_scored": triage["scored"],
                 "triage_auto_dismissed": triage["auto_dismissed"],
                 "triage_recommended": triage["recommended"],
                 "suggestions_posted": suggestions,
                 "signals_screened": sig["screened"],
                 "signals_already_screened": sig["already_screened"]}
        conn = _conn()
        try:
            conn.execute(text("""
                UPDATE bw_incident_enrichment_runs
                SET status = 'completed', stage = NULL, stats = CAST(:s AS jsonb),
                    brief = :b, finished_at = NOW()
                WHERE id = :id
            """), {"id": run_id, "s": json.dumps(stats), "b": brief})
            actor = f"agent:{requested_by}"
            if brief:
                _event(conn, incident_id, "agent_brief", actor,
                       note=brief.replace("\n", " ")[:200])
            sig_note = (f"; {sig['screened']} attached article(s) sent through Five Signals"
                        if sig["screened"] else "")
            triage_note = ""
            if triage["scored"]:
                triage_note = (f"; triage: {triage['auto_dismissed']} auto-dismissed as noise, "
                               f"{triage['recommended']} recommended for attach")
            _event(conn, incident_id, "enrichment", actor,
                   note=f"run #{run_id}: {staged} new candidate(s) staged for review "
                        f"({len(articles)} articles, {len(socials)} social, {len(profiles)} profiles)"
                        + triage_note + sig_note)
            conn.commit()
        finally:
            conn.close()
        logger.info("Incident %s enrichment run %s completed: %s", incident_id, run_id, stats)
    except Exception as e:  # noqa: BLE001
        logger.error("Incident %s enrichment run %s failed: %s", incident_id, run_id, e,
                     exc_info=True)
        try:
            conn = _conn()
            try:
                conn.execute(text("""
                    UPDATE bw_incident_enrichment_runs
                    SET status = 'failed', stage = NULL, error = :e, finished_at = NOW()
                    WHERE id = :id
                """), {"id": run_id, "e": str(e)[:2000]})
                conn.commit()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
