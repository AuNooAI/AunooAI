"""
Daily-briefing compose orchestration (staged + narrated + LLM-curated).

Rebuilt to mirror how a human builds these briefings (learned from the corpus
of past briefings), NOT a single threshold pass:

  - Briefings are CROSS-candidate but SCOPED to the chosen topics.
  - Real picks are RECENT (median ~1 day old), not high-alignment — the article
    gather is recency-first with no alignment gate (picked articles average
    0.62 alignment, BELOW the population average; a 0.7 floor drops them).
  - INCIDENTS are first-class (~7/briefing) and are DETECTED live via the
    incident-tracking flow, then curated.
  - Volumes are small: ~8 articles / ~7 incidents / ~5 emerging topics.
  - A final LLM CURATOR selects the briefing-worthy items from the candidate
    pools, few-shot'd with what the analyst picked in past briefings.

The pipeline is an async generator yielding progress events (SSE-framed by the
route), terminating with a ``complete`` event. ``compose_daily_briefing`` is a
non-streaming wrapper that drains it and returns the final payload.
"""

import json
import logging
import re
from datetime import datetime, date
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

# Target volumes — medians observed across the briefing corpus.
TARGET_ARTICLES = 8
TARGET_INCIDENTS = 7
TARGET_EMERGING = 5

# Candidate-pool sizing (what the curator chooses FROM).
ARTICLE_POOL_PER_TOPIC = 40
ARTICLE_GATHER_DAYS = 3          # recency-first; picks are median ~1 day old
FEWSHOT_BRIEFINGS = 5            # past briefings shown to the curator as taste
MAX_PER_SOURCE = 3               # cap candidates per news_source to dampen source/region skew

DEFAULT_DAYS_BACK = 7
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_DETECT_MODEL = "gpt-5.4-mini"


def _evt(stage: str, status: str, message: str, **extra) -> Dict[str, Any]:
    e = {"stage": stage, "status": status, "message": message}
    e.update(extra)
    return e


def _unique_briefing_name(facade, username: str, base_name: str) -> str:
    existing = {b["name"] for b in facade.get_desk_briefings_for_user(username)}
    if base_name not in existing:
        return base_name
    i = 2
    while f"{base_name} ({i})" in existing:
        i += 1
    return f"{base_name} ({i})"


# --------------------------------------------------------------------------
# Organizational profile (steers curation toward the org's priorities)
# --------------------------------------------------------------------------

def _get_default_org_profile(db) -> Optional[Dict[str, Any]]:
    """The tenant's default org profile (same convention as the rest of the app)."""
    from sqlalchemy import text
    conn = db._temp_get_connection()
    try:
        row = conn.execute(text("""
            SELECT id, name, industry, organization_type, key_concerns,
                   strategic_priorities, competitive_landscape, regulatory_environment,
                   custom_context, region, monitored_brands
            FROM organizational_profiles
            WHERE is_default = true
            LIMIT 1
        """)).mappings().first()
        if not row:
            return None
        d = dict(row)
        for f in ("key_concerns", "strategic_priorities", "competitive_landscape",
                  "regulatory_environment", "monitored_brands"):
            v = d.get(f)
            if isinstance(v, str):
                try:
                    d[f] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
    except Exception as e:
        logger.warning(f"[compose] org profile fetch failed: {e}")
        return None
    finally:
        conn.close()


def _profile_context(p: Optional[Dict[str, Any]]) -> str:
    """Compact profile text for the curator prompt."""
    if not p:
        return ""
    out = [f"Organization: {p.get('name')} ({p.get('industry') or p.get('organization_type') or ''})"]
    for label, key in (
        ("Key concerns", "key_concerns"),
        ("Strategic priorities", "strategic_priorities"),
        ("Monitored brands", "monitored_brands"),
        ("Competitive landscape", "competitive_landscape"),
        ("Regulatory environment", "regulatory_environment"),
    ):
        v = p.get(key)
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v[:12])
        if v:
            out.append(f"{label}: {str(v)[:400]}")
    if p.get("custom_context"):
        out.append(f"Context: {str(p['custom_context'])[:400]}")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Candidate gathering
# --------------------------------------------------------------------------

def _gather_candidate_articles(facade, topics: List[str], days_back: int) -> List[Dict[str, Any]]:
    """Recent articles across the chosen topics — recency-first, source-diversified.

    Caps articles per news_source (MAX_PER_SOURCE) so a few high-volume outlets
    (the dataset skews heavily toward a handful of Indian business sources) can't
    flood the candidate pool and crowd out the rest before the curator even sees it.
    """
    pool: Dict[str, Dict[str, Any]] = {}
    for topic in topics:
        rows = facade.get_relevant_articles_for_topic(
            topic, days_back=days_back, min_alignment=-1.0, limit=ARTICLE_POOL_PER_TOPIC,
        )
        for r in rows:
            r = dict(r)
            uri = r.get("uri")
            if uri and uri not in pool:
                r["_topic"] = topic
                pool[uri] = r
    items = list(pool.values())
    # Recency-first (picked articles are median ~1 day old).
    items.sort(key=lambda r: (r.get("publication_date") or ""), reverse=True)
    # Diversify: keep at most MAX_PER_SOURCE per news_source.
    per_source: Dict[str, int] = {}
    diversified: List[Dict[str, Any]] = []
    for r in items:
        src = (r.get("news_source") or "").lower()
        if per_source.get(src, 0) >= MAX_PER_SOURCE:
            continue
        per_source[src] = per_source.get(src, 0) + 1
        diversified.append(r)
    return diversified[: ARTICLE_POOL_PER_TOPIC * 2]


async def _detect_incidents(topics: List[str], days_back: int, model: str,
                            profile_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Run the incident-tracking detection for the chosen topics (best-effort).

    Passes profile_id so incidents are assessed against the org's priorities.
    """
    try:
        from app.routes.vector_routes import analyze_incidents, _IncidentTrackingRequest
        req = _IncidentTrackingRequest(
            topics=topics[:25],
            days_limit=max(days_back, 14),
            max_articles=120,
            model=model,
            profile_id=profile_id,
        )
        result = await analyze_incidents(req, session=None)
        return result.get("incidents", []) or []
    except Exception as e:
        logger.error(f"[compose] incident detection failed: {e}", exc_info=True)
        return []


def _fewshot_examples(db, k: int = FEWSHOT_BRIEFINGS) -> Dict[str, List[str]]:
    """Pull titles/names the analyst picked in recent finalized briefings."""
    from sqlalchemy import text
    articles: List[str] = []
    incidents: List[str] = []
    emerging: List[str] = []
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT articles, incidents, emerging_topics
            FROM desk_briefings
            WHERE status = 'finalized'
            ORDER BY finalized_at DESC NULLS LAST
            LIMIT :k
        """), {"k": k}).mappings().all()
        for row in rows:
            for a in (row["articles"] or []):
                if a.get("title"):
                    articles.append(a["title"])
            for i in (row["incidents"] or []):
                if i.get("name") or i.get("title"):
                    incidents.append(i.get("name") or i.get("title"))
            for e in (row["emerging_topics"] or []):
                if e.get("name"):
                    emerging.append(e["name"])
    except Exception as e:
        logger.warning(f"[compose] few-shot fetch failed: {e}")
    finally:
        conn.close()
    return {"articles": articles[:40], "incidents": incidents[:40], "emerging": emerging[:40]}


# --------------------------------------------------------------------------
# LLM curator
# --------------------------------------------------------------------------

def _compact_article(a: Dict[str, Any], id_: str) -> Dict[str, Any]:
    return {
        "id": id_,
        "title": a.get("title"),
        "source": a.get("news_source"),
        "date": a.get("publication_date"),
        "topic": a.get("_topic"),
        "summary": (a.get("summary") or "")[:300],
    }


def _compact_incident(i: Dict[str, Any], id_: str) -> Dict[str, Any]:
    return {
        "id": id_,
        "name": i.get("name") or i.get("title"),
        "type": i.get("type"),
        "significance": i.get("significance"),
        "plausibility": i.get("plausibility"),
        "source_quality": i.get("source_quality"),
        "description": (i.get("description") or i.get("summary") or "")[:300],
    }


def _compact_emerging(t: Dict[str, Any], id_: str) -> Dict[str, Any]:
    ts = t.get("trend_score") or {}
    return {
        "id": id_,
        "name": t.get("topic_label") or t.get("name"),
        "why_emerging": (t.get("why_emerging") or "")[:200],
        "confidence": t.get("confidence_score"),
        "composite": ts.get("composite") if isinstance(ts, dict) else None,
    }


def _extract_json(text_resp: str) -> Optional[Dict[str, Any]]:
    if not text_resp:
        return None
    s = text_resp.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None


async def _curate(
    payload: Dict[str, List[Dict[str, Any]]],
    fewshot: Dict[str, List[str]],
    model: str,
    profile_ctx: str = "",
) -> Optional[Dict[str, List[Dict[str, str]]]]:
    """LLM selects the briefing-worthy items from each pool. Returns ids + rationale."""
    import litellm

    # Cap each list so the FULL payload (all three sections) fits the prompt —
    # never truncate the serialized blob mid-way (that silently drops sections).
    capped = {
        "candidate_articles": payload.get("candidate_articles", [])[:30],
        "candidate_incidents": payload.get("candidate_incidents", [])[:15],
        "candidate_emerging_topics": payload.get("candidate_emerging_topics", [])[:15],
    }
    org_block = (
        f"\nThis briefing is for the following organization — prioritize items "
        f"material to ITS concerns, priorities, brands and competitive/regulatory "
        f"landscape over generic news:\n{profile_ctx}\n" if profile_ctx else ""
    )
    system = (
        "You are the editor of a daily intelligence briefing. You select which "
        "candidate items are briefing-worthy from EACH of the three pools (articles, "
        "incidents, emerging topics). Favor recent, materially significant, credible "
        "developments; avoid routine or redundant items. "
        "RELEVANCE TEST (most important): judge each item on whether it is globally or "
        "strategically MATERIAL TO THIS ORGANIZATION — NOT on the source's country. The "
        "candidate pool over-represents purely local/regional stories (e.g. local Indian "
        "college, exam, admissions or municipal data) that are not material to the "
        "organization — exclude those. But KEEP genuinely relevant items regardless of "
        "where they are sourced: India-sourced coverage of globally-relevant themes "
        "(e.g. generic-drug patent cliffs, national R&D/science policy, the organization's "
        "monitored brands or competitors) IS relevant and should be kept. The goal is "
        "relevance, not geographic exclusion. "
        "Select ONLY by the exact 'id' values provided — never invent ids. If a pool is "
        "empty, return [] for it."
        + org_block
    )
    user = f"""Past briefings picked items like these (match this editorial taste):
ARTICLES: {json.dumps(fewshot.get('articles', [])[:25])}
INCIDENTS: {json.dumps(fewshot.get('incidents', [])[:25])}
EMERGING TOPICS: {json.dumps(fewshot.get('emerging', [])[:25])}

Today's candidates:
{json.dumps(capped, indent=1)}

Select up to {TARGET_ARTICLES} articles, {TARGET_INCIDENTS} incidents, and
{TARGET_EMERGING} emerging topics. Return JSON ONLY:
{{
  "articles": [{{"id": "<article id>", "reason": "<one line>"}}],
  "incidents": [{{"id": "<incident id>", "reason": "<one line>"}}],
  "emerging_topics": [{{"id": "<topic id>", "reason": "<one line>"}}]
}}"""

    call_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1500,
    }
    if not str(model).startswith("gpt-5"):
        call_kwargs["temperature"] = 0.2

    try:
        resp = await litellm.acompletion(**call_kwargs)
        content = resp.choices[0].message.content
        parsed = _extract_json(content)
        if not parsed:
            return None
        return {
            "articles": parsed.get("articles") or [],
            "incidents": parsed.get("incidents") or [],
            "emerging_topics": parsed.get("emerging_topics") or [],
        }
    except Exception as e:
        logger.error(f"[compose] curator LLM failed: {e}", exc_info=True)
        return None


def _heuristic_select(art_by_id, inc_by_id, em_by_id) -> Dict[str, List[Dict[str, str]]]:
    """Fallback when the curator is unavailable: recency / significance / confidence.

    art_by_id is insertion-ordered recency-first; sort incidents by significance
    and emerging by confidence. Returns the same short ids used everywhere else.
    """
    sig_rank = {"high": 3, "medium": 2, "low": 1}
    art_ids = list(art_by_id.keys())[:TARGET_ARTICLES]
    inc_ids = sorted(
        inc_by_id.keys(),
        key=lambda k: sig_rank.get((inc_by_id[k].get("significance") or "").lower(), 0), reverse=True,
    )[:TARGET_INCIDENTS]
    em_ids = sorted(
        em_by_id.keys(), key=lambda k: (em_by_id[k].get("confidence_score") or 0), reverse=True,
    )[:TARGET_EMERGING]
    return {
        "articles": [{"id": k, "reason": "recent"} for k in art_ids],
        "incidents": [{"id": k, "reason": "significance"} for k in inc_ids],
        "emerging_topics": [{"id": k, "reason": "confidence"} for k in em_ids],
    }


# --------------------------------------------------------------------------
# Staging mappers
# --------------------------------------------------------------------------

def _article_to_briefing(a: Dict[str, Any], reason: str, topic: str) -> Dict[str, Any]:
    return {
        "uri": a.get("uri"),
        "title": a.get("title"),
        "summary": a.get("summary"),
        "source": a.get("news_source"),
        "publication_date": a.get("publication_date"),
        "topic": a.get("_topic") or topic,
        "url": a.get("uri"),
        "topic_alignment_score": a.get("topic_alignment_score"),
        "analysis": {"key_insight": reason} if reason else None,
        "added_at": datetime.utcnow().isoformat(),
    }


def _incident_to_briefing(i: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "name": i.get("name") or i.get("title"),
        "title": i.get("name") or i.get("title"),
        "type": i.get("type"),
        "significance": i.get("significance"),
        "description": i.get("description"),
        "summary": i.get("description") or i.get("summary"),
        "timeline": i.get("timeline"),
        "entities": i.get("related_entities") or i.get("entities"),
        "article_uris": i.get("article_uris"),
        "plausibility": i.get("plausibility"),
        "source_quality": i.get("source_quality"),
        "credibility_summary": i.get("credibility_summary"),
        "investigation_leads": i.get("investigation_leads"),
        "organizational_relevance": i.get("organizational_relevance"),
        "analysis": {"key_insight": reason} if reason else None,
        "added_at": datetime.utcnow().isoformat(),
    }


def _emerging_to_briefing(t: Dict[str, Any], reason: str, topic: str) -> Dict[str, Any]:
    synthesis = t.get("synthesis") or {}
    return {
        "name": t.get("topic_label") or t.get("name"),
        "summary": synthesis.get("key_takeaway") or t.get("topic_description"),
        "description": t.get("topic_description"),
        "why_emerging": t.get("why_emerging"),
        "key_takeaway": synthesis.get("key_takeaway"),
        "trend_score": t.get("trend_score"),
        "confidence_score": t.get("confidence_score"),
        "key_entities": t.get("key_entities"),
        "representative_keywords": t.get("representative_keywords"),
        "key_themes": t.get("key_themes"),
        "topic": topic,
        "implications": t.get("implications"),
        "organization_implications": t.get("organization_implications"),
        "signals": t.get("signals"),
        "actors": t.get("actors"),
        "events": t.get("events"),
        "analysis": {"key_insight": reason} if reason else None,
        "added_at": datetime.utcnow().isoformat(),
    }


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

async def compose_daily_briefing_stream(
    db,
    username: str,
    topics: List[str],
    *,
    days_back: int = DEFAULT_DAYS_BACK,
    run_detection: bool = True,
    model: str = DEFAULT_MODEL,
    detect_model: str = DEFAULT_DETECT_MODEL,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Staged, narrated compose. Yields progress events, ends with 'complete'/'error'."""
    from app.services.emerging_topics import EmergingTopicsService, EmergingTopicsConfig
    from app.ai_models import get_ai_model

    facade = db.facade
    if not topics:
        yield _evt("error", "failed", "No topics selected.")
        return

    try:
        # 1. Create draft -------------------------------------------------
        yield _evt("create", "started", "Creating draft briefing…", progress=0.05)
        today = date.today().isoformat()
        name = _unique_briefing_name(facade, username, f"Daily Briefing — {today}")
        briefing_id = facade.create_desk_briefing(
            name=name, username=username,
            description=f"Auto-composed {today} from: {', '.join(topics)}", topic=None,
        )
        yield _evt("create", "completed", f"Created '{name}'", briefing_id=briefing_id, progress=0.1)

        # Load the tenant's default org profile — steers incident detection and
        # curation toward its priorities (and helps de-bias generic coverage).
        org_profile = _get_default_org_profile(db)
        profile_ctx = _profile_context(org_profile)
        profile_id = org_profile.get("id") if org_profile else None
        if org_profile:
            yield _evt("create", "progress", f"Curating for {org_profile.get('name')}", progress=0.12)

        # 2. Gather recent article candidates ----------------------------
        yield _evt("gather", "started", "Gathering recent articles…", progress=0.15)
        cand_articles = _gather_candidate_articles(facade, topics, ARTICLE_GATHER_DAYS)
        yield _evt("gather", "completed", f"Pulled {len(cand_articles)} recent articles",
                   count=len(cand_articles), progress=0.25)

        # 3. Detect emerging topics --------------------------------------
        yield _evt("emerging", "started", "Detecting emerging topics…", progress=0.3)
        cand_emerging: List[Dict[str, Any]] = []
        service = EmergingTopicsService(
            config=EmergingTopicsConfig(days_back=days_back, model=detect_model),
            ai_model_getter=get_ai_model,
        )
        for idx, topic in enumerate(topics):
            if run_detection:
                try:
                    await service.run_detection(topic_filter=topic, days_back=days_back)
                except Exception as e:
                    logger.error(f"[compose] emerging detection '{topic}' failed: {e}")
            found = service.get_emerging_topics(topic_filter=topic, days_back=days_back,
                                                min_confidence=0.0, limit=20)
            cand_emerging.extend(t.to_dict() for t in found)
            yield _evt("emerging", "progress",
                       f"Scanned {idx + 1}/{len(topics)} topics — {len(cand_emerging)} candidates",
                       current=idx + 1, total=len(topics),
                       progress=0.3 + 0.25 * (idx + 1) / max(len(topics), 1))
        # de-dup emerging by id
        seen = set(); uniq_em = []
        for t in cand_emerging:
            tid = t.get("topic_label") or t.get("name")
            if tid and tid not in seen:
                seen.add(tid); uniq_em.append(t)
        cand_emerging = uniq_em
        yield _evt("emerging", "completed", f"Found {len(cand_emerging)} emerging topics",
                   count=len(cand_emerging), progress=0.55)

        # 4. Detect incidents --------------------------------------------
        yield _evt("incidents", "started", "Detecting incidents…", progress=0.6)
        cand_incidents = await _detect_incidents(topics, days_back, detect_model, profile_id=profile_id)
        yield _evt("incidents", "completed", f"Found {len(cand_incidents)} incidents",
                   count=len(cand_incidents), progress=0.72)

        # 5. Curate -------------------------------------------------------
        yield _evt("curate", "started",
                   f"Curating {len(cand_articles)} articles / {len(cand_incidents)} incidents / "
                   f"{len(cand_emerging)} topics…", progress=0.75)
        # Short, stable ids so the LLM echoes them back exactly.
        art_by_id = {f"a{n}": a for n, a in enumerate(cand_articles)}
        inc_by_id = {f"i{n}": i for n, i in enumerate(cand_incidents)}
        em_by_id = {f"e{n}": t for n, t in enumerate(cand_emerging)}
        compact = {
            "candidate_articles": [_compact_article(a, k) for k, a in art_by_id.items()],
            "candidate_incidents": [_compact_incident(i, k) for k, i in inc_by_id.items()],
            "candidate_emerging_topics": [_compact_emerging(t, k) for k, t in em_by_id.items()],
        }
        fewshot = _fewshot_examples(db)
        selection = await _curate(compact, fewshot, model, profile_ctx=profile_ctx)
        used_fallback = selection is None
        if used_fallback:
            selection = _heuristic_select(art_by_id, inc_by_id, em_by_id)
        # Keep only picks whose id is a real candidate (drop any hallucinated ids).
        selection["articles"] = [p for p in selection["articles"] if p.get("id") in art_by_id]
        selection["incidents"] = [p for p in selection["incidents"] if p.get("id") in inc_by_id]
        selection["emerging_topics"] = [p for p in selection["emerging_topics"] if p.get("id") in em_by_id]
        yield _evt("curate", "completed",
                   ("Curator unavailable — used recency/significance fallback"
                    if used_fallback else
                    f"Selected {len(selection['articles'])} articles, "
                    f"{len(selection['incidents'])} incidents, {len(selection['emerging_topics'])} topics"),
                   fallback=used_fallback, progress=0.85)

        # 6. Stage selections into the draft -----------------------------
        yield _evt("stage", "started", "Staging selections into the draft…", progress=0.88)
        staged_a = staged_i = staged_e = 0
        for pick in selection["articles"]:
            a = art_by_id.get(pick.get("id"))
            if a and facade.add_article_to_desk_briefing(
                    briefing_id, username, _article_to_briefing(a, pick.get("reason", ""), a.get("_topic"))):
                staged_a += 1
        for pick in selection["incidents"]:
            i = inc_by_id.get(pick.get("id"))
            if i and facade.add_incident_to_desk_briefing(
                    briefing_id, username, _incident_to_briefing(i, pick.get("reason", ""))):
                staged_i += 1
        for pick in selection["emerging_topics"]:
            t = em_by_id.get(pick.get("id"))
            if t and facade.add_emerging_topic_to_desk_briefing(
                    briefing_id, username, _emerging_to_briefing(t, pick.get("reason", ""), t.get("topic_filter") or "")):
                staged_e += 1

        yield _evt("stage", "completed",
                   f"Staged {staged_a} articles, {staged_i} incidents, {staged_e} emerging topics",
                   progress=0.97)

        # 7. Done ---------------------------------------------------------
        yield _evt("complete", "completed", f"Draft '{name}' ready to curate",
                   briefing_id=briefing_id, name=name,
                   articles_staged=staged_a, incidents_staged=staged_i,
                   emerging_topics_staged=staged_e, fallback=used_fallback, progress=1.0)

    except Exception as e:
        logger.error(f"[compose] pipeline failed: {e}", exc_info=True)
        yield _evt("error", "failed", f"Compose failed: {e}")


async def compose_daily_briefing(
    db, username: str, topics: List[str], **kwargs
) -> Dict[str, Any]:
    """Non-streaming wrapper: drains the pipeline, returns the final summary."""
    final: Dict[str, Any] = {"success": False}
    async for evt in compose_daily_briefing_stream(db, username, topics, **kwargs):
        if evt.get("stage") == "complete":
            final = {
                "success": True,
                "briefing_id": evt.get("briefing_id"),
                "name": evt.get("name"),
                "status": "draft",
                "topics_requested": topics,
                "emerging_topics_staged": evt.get("emerging_topics_staged", 0),
                "articles_staged": evt.get("articles_staged", 0),
                "incidents_staged": evt.get("incidents_staged", 0),
            }
        elif evt.get("stage") == "error":
            raise RuntimeError(evt.get("message", "compose failed"))
    return final
