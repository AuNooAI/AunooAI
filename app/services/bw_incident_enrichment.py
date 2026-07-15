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
import re
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
BRIEF_INPUT_CAP = 32000   # room for full evidence text — see _write_brief
MAX_SIGNAL_SCREENS = int(os.getenv("BW_ENRICH_MAX_SIGNAL_SCREENS", "5"))

# Assistive triage (user-confirmed 2026-07-15): the agent may auto-DISMISS
# clear noise (candidates table only) and RECOMMEND attaches, but never
# writes the evidence locker itself — attaching stays a human action.
TRIAGE_MODEL = os.getenv("BW_TRIAGE_MODEL", "gpt-5.4-mini")
# Incidents created without a description get one drafted from the initial
# evidence + brief on the first enrichment run (any trigger) — analysts often
# open a case from a single post with just a title.
DESCRIPTION_MODEL = os.getenv("BW_ENRICH_DESC_MODEL", "gpt-5.4-mini")
# Candidate-overlap duplicate signal: this many shared topic-scoped candidate
# refs (story siblings / vector hits, NOT brand-window posts) flags a merge.
DUP_MIN_SHARED_CANDIDATES = int(os.getenv("BW_DUP_MIN_SHARED_CANDIDATES", "3"))
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
            SELECT evidence_type, source_ref, title, meta, captured_at, content
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
        for etype, ref, title, meta, cap_at, content in evidence:
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
                                 "source": meta.get("news_source"),
                                 "author": meta.get("author"),
                                 "platform": meta.get("platform"),
                                 # the locker snapshot IS the material — the
                                 # brief is useless without it
                                 "content": (content or "")[:1500]})
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

    # Full evidence text goes in — a brief written from titles alone can only
    # hedge ("content not provided"), which is worthless to an analyst.
    ev_blocks = []
    for e in ctx["evidence_summaries"][:20]:
        head = f"[{e['type']}] {e.get('title') or '(untitled)'}"
        if e.get("author"):
            head += f" — @{e['author']}" + (f" on {e['platform']}" if e.get("platform") else "")
        if e.get("date"):
            head += f" ({str(e['date'])[:10]})"
        body = (e.get("content") or "").strip()
        ev_blocks.append(head + (f"\n{body}" if body else ""))
    cand_lines = [f"- [{c['candidate_type']}] {c.get('title') or c['source_ref']}"
                  + (f" ({(c.get('meta') or {}).get('publication_date', '')[:10]})"
                     if (c.get('meta') or {}).get('publication_date') else "")
                  + (f": {c.get('snippet')}" if c.get("snippet") else "")
                  for c in cands[:25]]
    prompt = (
        f"Case: {ctx['title']}\n"
        f"Brand: {ctx['brand_name']}\nSeverity: {ctx['severity']}  Status: {ctx['status']}\n"
        f"Description: {ctx['description'] or '(none)'}\n\n"
        f"MATERIAL IN THE CASE (full captured text follows each item):\n\n"
        + ("\n\n".join(ev_blocks) or "(none)") + "\n\n"
        f"RELATED MATERIAL FOUND BY AUTOMATED SEARCH (snippets):\n"
        + ("\n".join(cand_lines) or "(none)")
    )[:BRIEF_INPUT_CAP]
    try:
        model = LiteLLMModel.get_instance(BRIEF_MODEL)
        brief = await model.agenerate_response([
            {"role": "system", "content":
                "You write incident assessments for a brand-protection analyst doing "
                "adverse-media screening. The captured text above IS the material — read "
                "it and state plainly what is being said about the brand, by whom, and "
                "how far it has spread. Never write meta-commentary about the evidence "
                "('content is not provided', 'cannot be determined from the material', "
                "'document is not included') — if a point isn't in the text, simply don't "
                "make it. Never invent sources, numbers, or events. Plain factual prose, "
                "no dramatic framing. Markdown sections: ## What happened, "
                "## How it is spreading, ## Key voices, ## Recommended actions (max 3 "
                "bullets a brand/comms team can act on). Skip a section entirely if "
                "there is nothing to say."},
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
    mark strong ones recommendation='attach', and ROUTE items that belong to
    a different open case of the same brand (the sweeps are brand-wide, so
    without routing every case stages the same items — which then reads as
    shared evidence and manufactures duplicate-case suggestions). Never raises.

    Writes only bw_incident_enrichment_candidates — auto-dismissals show up
    in the disposition history as decided_by='agent:triage'; attaching (the
    locker write) remains a human decision.
    """
    from app.ai_models import LiteLLMModel
    stats = {"scored": 0, "auto_dismissed": 0, "recommended": 0, "routed": 0}
    conn = _conn()
    try:
        rows = conn.execute(text("""
            SELECT id, candidate_type, title, snippet, reason, source_ref, score, meta
            FROM bw_incident_enrichment_candidates
            WHERE incident_id = :i AND state = 'pending' AND triage_score IS NULL
            ORDER BY score DESC NULLS LAST, id
            LIMIT :lim
        """), {"i": incident_id, "lim": TRIAGE_MAX_PER_RUN}).fetchall()
        siblings = conn.execute(text("""
            SELECT id, title, LEFT(COALESCE(description, ''), 200)
            FROM bw_incidents
            WHERE brand_id = :b AND id != :i AND status IN ('open', 'investigating')
            ORDER BY id
        """), {"b": ctx["brand_id"], "i": incident_id}).fetchall()
    finally:
        conn.close()
    if not rows:
        return stats
    sibling_ids = {s[0] for s in siblings}

    context = (f"Incident: {ctx['title']}\n"
               f"Brand: {ctx['brand_name']}\n"
               f"Description: {ctx['description'] or '(none)'}\n"
               f"Brand keywords: {', '.join(ctx['keywords'])}")
    if siblings:
        context += "\n\nOTHER OPEN CASES for this brand (an item that is really about one "
        context += "of these belongs there, not here):\n" + "\n".join(
            f"- case {s[0]}: {s[1]}" + (f" — {s[2]}" if s[2] else "") for s in siblings)
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
            + ("If a candidate is really about one of the OTHER open cases listed "
               "above, set \"case\" to that case's number; otherwise omit it. "
               if siblings else "")
            + "Respond with ONLY a JSON array: "
            '[{"id": <id>, "score": <0.0-1.0>, "why": "<one short sentence>"'
            + (', "case": <other case number, only if it belongs there>' if siblings else '')
            + '}]')
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
                best_case = None
                try:
                    if item.get("case") is not None and int(item["case"]) in sibling_ids:
                        best_case = int(item["case"])
                except (TypeError, ValueError):
                    pass
                scored[cid] = (sc, str(item.get("why") or "")[:300], best_case)

    if not scored:
        return stats
    row_by_id = {r[0]: r for r in rows}
    conn = _conn()
    try:
        for cid, (sc, why, best_case) in scored.items():
            # Route to the better-fitting open case: dismiss here (never
            # re-proposed on this case) and stage a pending candidate there.
            if best_case is not None and sc >= TRIAGE_DISMISS_BELOW:
                src = row_by_id[cid]
                r = conn.execute(text("""
                    UPDATE bw_incident_enrichment_candidates
                    SET triage_score = :s, triage_rationale = :w,
                        state = 'dismissed', decided_by = 'agent:triage', decided_at = NOW()
                    WHERE id = :id AND state = 'pending'
                    RETURNING id
                """), {"s": sc, "w": f"routed to case #{best_case}: {why}"[:300], "id": cid}).fetchone()
                if r:
                    conn.execute(text("""
                        INSERT INTO bw_incident_enrichment_candidates
                            (run_id, incident_id, candidate_type, source_ref, title,
                             snippet, score, reason, meta)
                        VALUES (:r, :i, :t, :sr, :ti, :sn, :sc, :re, CAST(:m AS jsonb))
                        ON CONFLICT (incident_id, candidate_type, source_ref) DO NOTHING
                    """), {"r": run_id, "i": best_case, "t": src[1], "sr": src[5],
                           "ti": src[2], "sn": src[3], "sc": src[6],
                           "re": f"routed from case #{incident_id}: {why}"[:300],
                           "m": json.dumps(_jload(src[7]) or {}, default=str)})
                    stats["routed"] += 1
                continue
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
        flagged_dup_ids: Set[int] = set()
        for other_id, other_title in dup:
            note = (f"possible duplicate of incident #{other_id} ('{(other_title or '')[:80]}')"
                    f" — they share attached evidence; consider merging")
            if not any(n and n.startswith(f"possible duplicate of incident #{other_id} ") for n in existing):
                _event(conn, incident_id, "agent_suggestion", "agent:triage", note=note)
                posted += 1
            flagged_dup_ids.add(other_id)

        # Possible duplicate (weaker signal): another open incident of the same
        # brand whose research sweeps keep surfacing the same topic-scoped
        # material. Brand-matched window posts are excluded — any two concurrent
        # cases of one brand share those, so they say nothing about the topic.
        dup2 = conn.execute(text("""
            SELECT i2.id, i2.title, COUNT(DISTINCT c1.source_ref) AS shared
            FROM bw_incident_enrichment_candidates c1
            JOIN bw_incident_enrichment_candidates c2
              ON c2.source_ref = c1.source_ref AND c2.incident_id != c1.incident_id
            JOIN bw_incidents i2 ON i2.id = c2.incident_id
              AND i2.brand_id = :b AND i2.status IN ('open', 'investigating')
            WHERE c1.incident_id = :i
              AND c1.candidate_type != 'account_profile'
              AND c1.reason NOT ILIKE 'brand-matched%'
              AND c2.reason NOT ILIKE 'brand-matched%'
            GROUP BY i2.id, i2.title
            HAVING COUNT(DISTINCT c1.source_ref) >= :minshared
        """), {"i": incident_id, "b": ctx["brand_id"],
               "minshared": DUP_MIN_SHARED_CANDIDATES}).fetchall()
        for other_id, other_title, shared in dup2:
            if other_id in flagged_dup_ids:
                continue
            note = (f"possible duplicate of incident #{other_id} ('{(other_title or '')[:80]}')"
                    f" — the research sweeps found the same {shared} related items for both;"
                    f" consider merging")
            if not any(n and n.startswith(f"possible duplicate of incident #{other_id} ") for n in existing):
                _event(conn, incident_id, "agent_suggestion", "agent:triage", note=note)
                posted += 1

        # Severity calibration: a high/critical case whose screened coverage
        # all came back low-risk gets stepped down one level automatically
        # (user-directed 2026-07-15: apply, don't nag). Guardrails: fires at
        # most once per case, and never after ANY severity_change event —
        # if a human (or a previous auto-adjust) has set severity
        # deliberately, the agent leaves it alone.
        if ctx["severity"] in ("high", "critical"):
            prior_sev_changes = conn.execute(text("""
                SELECT COUNT(*) FROM bw_incident_events
                WHERE incident_id = :i AND kind = 'severity_change'
            """), {"i": incident_id}).fetchone()[0]
            vr = conn.execute(text("""
                SELECT s.verdict FROM bw_incident_evidence e
                JOIN bw_article_signals s
                  ON s.article_uri = e.source_ref AND s.brand_id = :b
                     AND s.status = 'completed' AND s.verdict IS NOT NULL
                WHERE e.incident_id = :i
            """), {"i": incident_id, "b": ctx["brand_id"]}).fetchall()
            verdicts = [r[0] for r in vr]
            risky = {"corroborated", "contested", "likely_coordinated"}
            if verdicts and not (set(verdicts) & risky) and prior_sev_changes == 0:
                new_sev = {"critical": "high", "high": "medium"}[ctx["severity"]]
                conn.execute(text(
                    "UPDATE bw_incidents SET severity = :s, updated_at = NOW() WHERE id = :i"
                ), {"s": new_sev, "i": incident_id})
                conn.execute(text("""
                    INSERT INTO bw_incident_events
                        (incident_id, kind, actor, old_value, new_value, note)
                    VALUES (:i, 'severity_change', 'agent:triage', :o, :n, :note)
                """), {"i": incident_id, "o": ctx["severity"], "n": new_sev,
                       "note": f"auto-adjusted: all {len(verdicts)} screened item(s) are low-risk "
                               f"({', '.join(sorted(set(verdicts)))}) — revert if you disagree"})
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

def _title_is_placeholder(title: str, brand_name: str) -> bool:
    """'Wiley Case #1', 'incident 3', bare brand name, one word — anything
    that doesn't say what the case is about."""
    t = (title or "").strip()
    if not t or t.lower() == (brand_name or "").strip().lower():
        return True
    if re.search(r"\b(case|incident|test)\s*#?\d*\s*$", t, re.IGNORECASE):
        return True
    return len(t.split()) <= 1


async def _draft_title_and_description(ctx: Dict, brief: Optional[str]) -> Dict[str, str]:
    """Factual case title + 2-3 sentence description for an incident the
    analyst opened with a placeholder name and/or no description. Facts only —
    assessment lives in the brief. Returns {} on failure."""
    from app.ai_models import LiteLLMModel

    ev_lines = []
    for e in ctx["evidence_summaries"][:10]:
        who = e.get("author") or ""
        plat = e.get("platform") or e.get("source") or ""
        ev_lines.append(f"- [{e['type']}] {who and '@' + str(who) + ' '}{plat and 'on ' + str(plat) + ' '}"
                        f"{str(e.get('date') or '')[:10]}: "
                        f"{str(e.get('content') or e.get('title') or '')[:400]}")
    if not ev_lines and not brief:
        return {}
    prompt = (
        "You are naming and describing a brand-monitoring incident for its case file.\n"
        "- title: 4-8 words naming the concrete issue (e.g. \"Consent concerns over AI companion "
        "tool\"), not the brand alone, never 'Case'/'Incident' + number.\n"
        "- description: 2-3 factual sentences — what the incident concerns (the concrete thing "
        "that happened or is being said) and who raised it where. Plain prose, no markdown, no "
        "assessment, no recommendations, no hedging about evidence quality. Attribute claims to "
        "the exact accounts named in the material. Do not invent facts.\n\n"
        'Respond ONLY with JSON: {"title": "...", "description": "..."}\n\n'
        f"Brand: {ctx['brand_name']}\nCurrent working title: {ctx['title']}\n\n"
        "Attached evidence:\n" + ("\n".join(ev_lines) or "(none)")
        + (f"\n\nAgent brief:\n{brief[:3000]}" if brief else "")
    )
    try:
        model = LiteLLMModel.get_instance(DESCRIPTION_MODEL)
        out = (await model.agenerate_response([
            {"role": "system", "content":
                "You write concise case-file titles and descriptions. Respond only with valid JSON."},
            {"role": "user", "content": prompt},
        ])).strip()
        if not out or out.startswith("⚠️"):
            return {}
        if out.startswith("```"):
            out = out.split("```")[1]
            if out.startswith("json"):
                out = out[4:]
            out = out.strip()
        parsed = json.JSONDecoder().raw_decode(out)[0]
        return {"title": str(parsed.get("title") or "").strip()[:300],
                "description": str(parsed.get("description") or "").strip()[:1000]}
    except Exception as e:  # noqa: BLE001
        logger.warning("Incident title/description draft failed: %s", e)
        return {}


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

        desc_missing = not (ctx.get("description") or "").strip()
        title_placeholder = _title_is_placeholder(ctx.get("title") or "", ctx["brand_name"])
        drafted: Dict[str, str] = {}
        if desc_missing or title_placeholder:
            _stage(run_id, "drafting case name and description")
            drafted = await _draft_title_and_description(ctx, brief)

        stats = {"story_siblings": len(siblings), "vector_similar": len(vector),
                 "social_posts": len(socials), "profiles": len(profiles),
                 "candidates_found": len(cands), "staged_new": staged,
                 "brief": bool(brief),
                 "triage_scored": triage["scored"],
                 "triage_auto_dismissed": triage["auto_dismissed"],
                 "triage_recommended": triage["recommended"],
                 "triage_routed": triage.get("routed", 0),
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
            if desc_missing and drafted.get("description"):
                # guarded so an analyst who typed one mid-run wins
                res = conn.execute(text("""
                    UPDATE bw_incidents SET description = :d, updated_at = NOW()
                    WHERE id = :i AND (description IS NULL OR description = '')
                """), {"i": incident_id, "d": drafted["description"]})
                if res.rowcount:
                    _event(conn, incident_id, "note", actor,
                           note="Incident description drafted by the agent from the initial "
                                "evidence — review and edit as needed.")
            new_title = drafted.get("title")
            if (title_placeholder and new_title
                    and not _title_is_placeholder(new_title, ctx["brand_name"])):
                # guarded on the old value so an analyst rename mid-run wins
                res = conn.execute(text("""
                    UPDATE bw_incidents SET title = :t, updated_at = NOW()
                    WHERE id = :i AND title = :old
                """), {"i": incident_id, "t": new_title, "old": ctx.get("title") or ""})
                if res.rowcount:
                    _event(conn, incident_id, "note", actor,
                           note=f"Case renamed by the agent: '{(ctx.get('title') or '')[:80]}' → "
                                f"'{new_title[:100]}' — edit as needed.")
            if brief:
                _event(conn, incident_id, "agent_brief", actor,
                       note=brief.replace("\n", " ")[:200])
            sig_note = (f"; {sig['screened']} attached article(s) sent through Five Signals"
                        if sig["screened"] else "")
            triage_note = ""
            if triage["scored"]:
                triage_note = (f"; triage: {triage['auto_dismissed']} auto-dismissed as noise, "
                               f"{triage['recommended']} recommended for attach"
                               + (f", {triage['routed']} routed to better-fitting cases"
                                  if triage.get("routed") else ""))
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
