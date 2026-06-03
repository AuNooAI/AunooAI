"""Trend-discovery → topic-promotion pipeline for the Wiley track.

Three pieces:

1. ``run_weekly_scan`` — fires the existing EmergingTopicsService over
   the corpus, then for every detected cluster runs the
   ``wiley_relevance_judge`` agent against the Wiley organisational
   profile and upserts a row in ``topic_candidates``. Off-scope verdicts
   are auto-rejected at insert. This is what the weekly cron runs.

2. ``promote_candidate`` — given a candidate id, creates the
   ``forecast_topic_metadata`` row, fires a Three Horizons run seeded
   with the candidate's articles, chains into a paired assessment, and
   then drafts the deck overlay. The wizard lands the analyst on step 4
   (overlay review) when this finishes.

3. ``sweep_snoozed_candidates`` — daily tick to flip elapsed snoozes
   back to 'pending'.

Reuses existing primitives:
- ``EmergingTopicsService.run_detection``
- ``app.services.wiley_bundle_supervisor._call_agent``
- ``wiley_overlay_generator.generate_overlay_proposal``
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


WILEY_ORG_PROFILE_NAME = os.environ.get(
    "WILEY_ORG_PROFILE_NAME", "Wiley Scientific Publisher"
)
DEFAULT_DAYS_BACK = int(os.environ.get("WILEY_CANDIDATE_SCAN_DAYS_BACK", "14"))
JUDGE_CONCURRENCY = int(os.environ.get("WILEY_CANDIDATE_JUDGE_CONCURRENCY", "4"))


# ── Helpers ─────────────────────────────────────────────────────────


def _serialize_org_profile(row: dict) -> dict:
    """Shape the organizational_profiles row into the structure the
    ``wiley_relevance_judge`` agent expects."""
    def _parse_json_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []

    return {
        "name": row.get("name"),
        "description": row.get("description"),
        "industry": row.get("industry"),
        "key_concerns": _parse_json_list(row.get("key_concerns")),
        "strategic_priorities": _parse_json_list(row.get("strategic_priorities")),
        "competitive_landscape": _parse_json_list(row.get("competitive_landscape")),
        "regulatory_environment": _parse_json_list(row.get("regulatory_environment")),
        "stakeholder_focus": _parse_json_list(row.get("stakeholder_focus")),
        "custom_context": row.get("custom_context"),
        "monitored_keywords": _parse_json_list(row.get("monitored_keywords")),
    }


def _fetch_article_titles(db, article_uris: list, limit: int = 12) -> list:
    """Pull a handful of titles for the judge's context. Keep the payload
    small — the model just needs a feel for the cluster."""
    if not article_uris:
        return []
    from sqlalchemy import text as sa_text
    uris = list(article_uris)[:limit]
    sql = sa_text(
        "SELECT uri, title FROM articles WHERE uri = ANY(:uris)"
    )
    rows = db.facade._execute_with_rollback(sql, {"uris": uris}).fetchall()
    titles_by_uri = {r._mapping["uri"]: r._mapping["title"] for r in rows}
    # Preserve input order — the cluster's sample order is more meaningful
    # than alphabetical.
    return [titles_by_uri[u] for u in uris if u in titles_by_uri]


def _list_unjudged_emerging_topics(db, org_profile_id: int, days_back: int) -> list:
    """Emerging topics from the last ``days_back`` days that don't yet
    have a topic_candidates row for this organisational profile. Run
    after detection so every freshly created cluster is judged exactly
    once.
    """
    from sqlalchemy import text as sa_text
    sql = sa_text("""
        SELECT et.id, et.topic_label, et.topic_description, et.detection_date,
               et.article_count, et.growth_rate, et.velocity, et.confidence_score,
               et.key_themes, et.representative_keywords,
               et.sample_article_uris, et.article_uris,
               et.composite_score
        FROM emerging_topics et
        LEFT JOIN topic_candidates tc
               ON tc.emerging_topic_id = et.id
              AND tc.org_profile_id    = :opid
        WHERE et.detection_date >= CURRENT_DATE - (:days_back || ' days')::interval
          AND tc.id IS NULL
          AND (et.status IS NULL OR et.status NOT IN ('declined', 'retired'))
        ORDER BY COALESCE(et.composite_score, et.confidence_score, 0) DESC,
                 et.detection_date DESC
    """)
    rows = db.facade._execute_with_rollback(sql, {
        "opid": int(org_profile_id),
        "days_back": int(days_back),
    }).fetchall()
    out = []
    for r in rows:
        rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        out.append(rd)
    return out


def _build_judge_payload(cluster_row: dict, org_profile: dict,
                        sample_titles: list) -> dict:
    def _parse_jsonish(value):
        if value is None:
            return []
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return []
        return []

    return {
        "cluster": {
            "label": cluster_row.get("topic_label") or "—",
            "topic_description": cluster_row.get("topic_description") or "",
            "key_themes": _parse_jsonish(cluster_row.get("key_themes")),
            "representative_keywords":
                _parse_jsonish(cluster_row.get("representative_keywords")),
            "article_titles": sample_titles,
            "article_count": cluster_row.get("article_count") or 0,
            "growth_rate": cluster_row.get("growth_rate"),
            "velocity": cluster_row.get("velocity"),
        },
        "organization": org_profile,
    }


# ── Public API ──────────────────────────────────────────────────────


async def run_weekly_scan(
    days_back: int = DEFAULT_DAYS_BACK,
    *, dry_run: bool = False,
) -> dict:
    """Detect emerging clusters over the last ``days_back`` days, judge
    each against the Wiley org profile, and upsert into
    ``topic_candidates``. Returns a summary dict.
    """
    from app.database import get_database_instance
    from app.services.emerging_topics.emerging_topics_service import (
        get_emerging_topics_service,
    )
    from app.services.wiley_bundle_supervisor import _call_agent

    summary = {
        "started_at": datetime.utcnow().isoformat(),
        "days_back": days_back,
        "dry_run": dry_run,
        "detection_run": False,
        "candidates_judged": 0,
        "candidates_in_scope": 0,
        "candidates_adjacent": 0,
        "candidates_off_scope": 0,
        "candidates_persisted": 0,
        "errors": [],
    }

    db = get_database_instance()

    org_profile_row = db.facade.get_organizational_profile_by_name(
        WILEY_ORG_PROFILE_NAME
    )
    if not org_profile_row:
        msg = (
            f"Organisational profile '{WILEY_ORG_PROFILE_NAME}' not found — "
            "create it before running the candidate scan."
        )
        logger.error(msg)
        summary["errors"].append(msg)
        return summary

    org_profile_id = int(org_profile_row["id"])
    org_profile = _serialize_org_profile(org_profile_row)

    # 1) Discovery — full run over the corpus for the last `days_back` days.
    try:
        svc = get_emerging_topics_service()
        logger.info(
            "wiley_candidate_pipeline: running emerging-topics detection "
            "(days_back=%d)", days_back,
        )
        await svc.run_detection(topic_filter=None, days_back=days_back)
        summary["detection_run"] = True
    except Exception as e:
        logger.error("Emerging-topics detection failed: %s", e)
        summary["errors"].append(f"detection: {e}")
        # Don't abort — re-judge older unjudged rows even if a fresh run failed.

    # 2) Judge — every emerging-topic without a candidate row for this profile.
    unjudged = _list_unjudged_emerging_topics(db, org_profile_id, days_back)
    logger.info(
        "wiley_candidate_pipeline: %d unjudged emerging-topic(s) to evaluate",
        len(unjudged),
    )

    semaphore = asyncio.Semaphore(JUDGE_CONCURRENCY)

    async def _judge_one(cluster_row: dict) -> Optional[dict]:
        async with semaphore:
            try:
                sample_uris = (cluster_row.get("sample_article_uris")
                               or cluster_row.get("article_uris") or [])
                sample_titles = _fetch_article_titles(db, sample_uris, limit=12)
                payload = _build_judge_payload(cluster_row, org_profile, sample_titles)
                verdict = await _call_agent("wiley_relevance_judge", payload)
                if not verdict or "verdict" not in verdict:
                    return None
                return {"cluster": cluster_row, "verdict": verdict}
            except Exception as e:
                logger.error("Judge failed for emerging_topic=%s: %s",
                             cluster_row.get("id"), e)
                summary["errors"].append(
                    f"judge et={cluster_row.get('id')}: {e}"
                )
                return None

    results = await asyncio.gather(*[_judge_one(c) for c in unjudged])

    for r in results:
        if not r:
            continue
        summary["candidates_judged"] += 1
        v = r["verdict"]
        verdict_kind = v.get("verdict")
        if verdict_kind == "in_scope":
            summary["candidates_in_scope"] += 1
        elif verdict_kind == "adjacent":
            summary["candidates_adjacent"] += 1
        elif verdict_kind == "off_scope":
            summary["candidates_off_scope"] += 1

        if dry_run:
            logger.info(
                "[dry-run] et=%s '%s' → %s (%.2f) %s",
                r["cluster"].get("id"),
                r["cluster"].get("topic_label"),
                verdict_kind,
                v.get("score") or 0.0,
                v.get("proposed_topic_name") or "",
            )
            continue

        try:
            db.facade.upsert_topic_candidate(
                emerging_topic_id=int(r["cluster"]["id"]),
                org_profile_id=org_profile_id,
                relevance_verdict=verdict_kind,
                relevance_score=float(v.get("score")) if v.get("score") is not None else None,
                relevance_rationale=v.get("rationale"),
                proposed_topic_name=v.get("proposed_topic_name"),
                proposed_description=v.get("proposed_description"),
                proposed_tags=v.get("proposed_tags") if isinstance(v.get("proposed_tags"), list) else None,
            )
            summary["candidates_persisted"] += 1
        except Exception as e:
            logger.error("Upsert failed for et=%s: %s",
                         r["cluster"].get("id"), e)
            summary["errors"].append(
                f"upsert et={r['cluster'].get('id')}: {e}"
            )

    summary["completed_at"] = datetime.utcnow().isoformat()
    logger.info(
        "wiley_candidate_pipeline: scan complete — judged=%d in_scope=%d "
        "adjacent=%d off_scope=%d persisted=%d errors=%d",
        summary["candidates_judged"], summary["candidates_in_scope"],
        summary["candidates_adjacent"], summary["candidates_off_scope"],
        summary["candidates_persisted"], len(summary["errors"]),
    )
    return summary


def sweep_snoozed_candidates() -> int:
    """Daily tick — flip 'snoozed' rows whose window has elapsed back to
    'pending'. Returns the number of rows unsnoozed.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    return db.facade.sweep_snoozed_candidates()


async def _gather_seed_articles(
    db, topic: str, *,
    source_topics: Optional[List[str]] = None,
    days_back: int = 90,
    limit: int = 60,
) -> List[str]:
    """Resolve the seed article set for a (possibly brand-new) tracked topic.

    Three strategies, in priority order:

    1. ``source_topics`` — the analyst explicitly picked one or more existing
       corpus topics to draw from. Pull alignment-filtered, recent articles
       from each (falling back to a plain topic match if a topic has no
       alignment scores computed yet, e.g. a raw keyword-group feed), merge
       newest-first, and cap at ``limit``.
    2. Exact match — the tracked name itself matches a stored ``topic`` value.
       This is the original behaviour and covers candidate-promotion as well
       as tracked topics that reuse an existing collection name.
    3. Semantic fallback — a genuinely new free-typed name (e.g. "Quantum
       Advantage") with nothing tagged to it. Vector-search the corpus for the
       name (+ description) and seed from the most relevant articles, whatever
       topic they carry, rather than dead-ending on a zero exact match.
    """
    from sqlalchemy import text as sa_text

    def _exact_match(t: str) -> list:
        sql = sa_text("""
            SELECT uri
            FROM articles
            WHERE topic = :topic
              AND (publication_date IS NULL OR
                   publication_date::timestamp >= NOW() - (:days || ' days')::interval)
            ORDER BY publication_date DESC NULLS LAST
            LIMIT :limit
        """)
        rows = db.facade._execute_with_rollback(
            sql, {"topic": t, "days": int(days_back), "limit": int(limit)},
        ).fetchall()
        return [r._mapping["uri"] for r in rows]

    seen: set = set()
    ordered: list = []

    def _add(new_uris):
        for u in new_uris:
            if u and u not in seen:
                seen.add(u)
                ordered.append(u)

    # 1. Explicit source topics — alignment-filtered (customer-facing quality)
    if source_topics:
        for t in source_topics:
            rows = db.facade.get_relevant_articles_for_topic(
                t, days_back=days_back, limit=limit,
            )
            picked = [r["uri"] for r in rows]
            if not picked:
                # topic has no alignment scores yet — fall back to raw match
                picked = _exact_match(t)
            _add(picked)
        return ordered[:limit]

    # 2. Exact match on the tracked name (original behaviour)
    _add(_exact_match(topic))
    if ordered:
        return ordered[:limit]

    # 3. Semantic fallback for a brand-new free-typed name
    try:
        from app.vector_store_pgvector import search_articles_async
        meta = db.facade.get_forecast_topic_metadata(topic) or {}
        query = topic
        if meta.get("description"):
            query = f"{topic}. {meta['description']}"
        cutoff = (datetime.now() - timedelta(days=int(days_back))).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        results = await search_articles_async(
            query,
            top_k=max(limit * 2, 60),
            metadata_filter={"publication_date": {"$gte": cutoff}},
        )
        _add([r.get("id") for r in results])
    except Exception as e:
        logger.warning("Semantic seed fallback failed for '%s': %s", topic, e)

    return ordered[:limit]


async def build_topic_pipeline(
    topic: str, *,
    article_limit: int = 60,
    days_back: int = 90,
    source_topics: Optional[List[str]] = None,
    progress_callback=None,
) -> dict:
    """Wizard helper — run horizons + paired assessment + overlay for an
    analyst-named topic that doesn't have a backing candidate.

    The seed articles are resolved by :func:`_gather_seed_articles`, which
    accepts an explicit ``source_topics`` selection, falls back to an exact
    match on the tracked name, and finally to a corpus-wide semantic search
    so a brand-new free-typed name still bootstraps. The tracked name is only
    a deck/join label — the Three Horizons run is seeded from article URIs, so
    the name need not match any stored ``topic`` value.

    If the topic already has a horizons run, the wizard's UI can call
    this for the assessment + overlay-only path; on the backend we still
    run a fresh horizons run rather than rely on a stale one. Callers
    who want to skip horizons should call assess/overlay endpoints
    directly.
    """
    from app.database import get_database_instance

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    db = get_database_instance()

    _emit(2, f"Looking up articles for '{topic}'")
    article_uris = await _gather_seed_articles(
        db, topic,
        source_topics=source_topics,
        days_back=days_back,
        limit=article_limit,
    )
    if not article_uris:
        srcs = f" from {', '.join(source_topics)}" if source_topics else ""
        raise RuntimeError(
            f"No articles found for topic '{topic}'{srcs} in the last {days_back} days. "
            "Either select one or more existing source topics that have articles, "
            "or add/collect articles for this topic first."
        )
    _emit(8, f"Found {len(article_uris)} seed article(s)")

    meta = db.facade.get_forecast_topic_metadata(topic) or {}
    synthetic_candidate = {
        "id": None,
        "article_uris": article_uris,
        "sample_article_uris": article_uris[:10],
        "proposed_description": meta.get("description"),
        "topic_description": meta.get("description"),
        "proposed_topic_name": meta.get("display_name") or topic,
        "topic_label": topic,
    }

    _emit(15, "Running Three Horizons (~3-5 min)")
    horizons_run_id = await _run_three_horizons(topic, synthetic_candidate)

    _emit(55, "Running paired assessment (~3-6 min)")
    await _run_paired_assessment(horizons_run_id)

    _emit(80, "Drafting deck overlay (~1-2 min)")
    from app.services.wiley_overlay_generator import generate_overlay_proposal
    try:
        proposed_path, _overlay = await generate_overlay_proposal(topic)
    except Exception as e:
        logger.warning("Overlay draft failed for '%s': %s", topic, e)
        proposed_path = None

    _emit(100, "Build complete")
    return {
        "topic": topic,
        "horizons_run_id": horizons_run_id,
        "overlay_path": str(proposed_path) if proposed_path else None,
        "article_count": len(article_uris),
    }


async def promote_candidate(
    candidate_id: int, *,
    triaged_by: Optional[str] = None,
    progress_callback=None,
) -> dict:
    """Promotion pipeline:

    1. Create ``forecast_topic_metadata`` row (status='draft').
    2. Fire a Three Horizons run for the topic.
    3. Run a paired assessment on the new run.
    4. Draft the deck overlay (.proposed file).
    5. Flip the candidate row to 'promoted'.

    Returns the resulting topic name + overlay path. Raises on failure.
    """
    from app.database import get_database_instance

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    db = get_database_instance()
    cand = db.facade.get_topic_candidate(candidate_id)
    if not cand:
        raise ValueError(f"Candidate {candidate_id} not found")
    if cand.get("triage_status") in ("promoted", "merged"):
        raise ValueError(
            f"Candidate {candidate_id} already {cand['triage_status']}"
        )

    proposed_name = (
        cand.get("proposed_topic_name")
        or cand.get("topic_label")
        or f"Candidate {candidate_id}"
    )

    _emit(5, f"Creating draft topic '{proposed_name}'")
    db.facade.upsert_forecast_topic_metadata(
        topic=proposed_name,
        display_name=proposed_name,
        description=cand.get("proposed_description"),
        tags=cand.get("proposed_tags") if isinstance(cand.get("proposed_tags"), list) else None,
        status="draft",
    )

    # Wire source_candidate_id so the dashboard can show lineage.
    try:
        from sqlalchemy import text as sa_text
        db.facade._execute_with_rollback(
            sa_text(
                "UPDATE forecast_topic_metadata SET source_candidate_id = :cid, "
                "updated_at = NOW() WHERE topic = :topic"
            ),
            {"cid": int(candidate_id), "topic": proposed_name},
        )
        try:
            db.facade.session.commit()
        except Exception:
            pass
    except Exception as e:
        logger.warning("Failed to set source_candidate_id on '%s': %s",
                       proposed_name, e)

    _emit(20, "Running Three Horizons")
    horizons_run_id = await _run_three_horizons(proposed_name, cand)

    _emit(55, "Running paired assessment")
    await _run_paired_assessment(horizons_run_id)

    _emit(80, "Drafting deck overlay")
    from app.services.wiley_overlay_generator import generate_overlay_proposal
    try:
        proposed_path, _overlay = await generate_overlay_proposal(proposed_name)
    except Exception as e:
        # Overlay drafting is non-fatal for promotion — wizard step 4 will
        # offer "Generate overlay" if .proposed is missing.
        logger.warning("Overlay draft failed for '%s': %s", proposed_name, e)
        proposed_path = None

    _emit(95, "Marking candidate promoted")
    db.facade.triage_topic_candidate(
        candidate_id,
        action="promote",
        promoted_to=proposed_name,
        triaged_by=triaged_by,
    )

    _emit(100, "Promotion complete")
    return {
        "topic": proposed_name,
        "horizons_run_id": horizons_run_id,
        "overlay_path": str(proposed_path) if proposed_path else None,
    }


async def _run_three_horizons(topic: str, candidate: dict) -> str:
    """Generate a Three Horizons run for the promoted topic, seeded with
    the candidate's article corpus, then persist to
    ``future_horizons_runs`` via the facade.

    Returns the new run id (UUID string).
    """
    import time as _time
    import uuid as _uuid
    from collections import Counter
    from datetime import datetime as _dt
    from pathlib import Path as _Path
    from sqlalchemy import text as sa_text

    from app.database import get_database_instance
    from app.ai_models import get_ai_model

    db = get_database_instance()
    article_uris = list(candidate.get("article_uris") or candidate.get("sample_article_uris") or [])
    if not article_uris:
        raise RuntimeError(
            "Candidate has no article URIs to seed Three Horizons with."
        )

    # Pull full article rows so the prompt can reference real titles +
    # signals. Match the shape used by analyze_topic_in_horizons.
    article_rows = []
    if article_uris:
        sql = sa_text("""
            SELECT uri, title, summary, publication_date, sentiment, category,
                   future_signal, driver_type, time_to_impact, quality_score
            FROM articles WHERE uri = ANY(:uris)
        """)
        rows = db.facade._execute_with_rollback(
            sql, {"uris": article_uris[:50]}
        ).fetchall()
        for r in rows:
            article_rows.append(dict(r._mapping) if hasattr(r, "_mapping") else dict(r))
    if not article_rows:
        raise RuntimeError(
            "Could not fetch any articles for the candidate's URIs."
        )

    # Three Horizons prompt — reuse the exact builder the Future Horizons tab's
    # generator uses (PromptLoader future_horizons/current → "Three Horizons
    # framework", h1/h2/h3 scenarios). This previously loaded the Futures-Cone
    # emerging_topic_driver prompt, whose probable/plausible/possible/preferable
    # types render in NEITHER the Future Horizons tab nor the Forecast Tracker
    # (both built around h1/h2/h3) — a naming/implementation drift the function
    # name ("three_horizons") never matched. Seeded with the same article rows;
    # org framing left default-executive, matching the prior empty org_context.
    from app.routes.trend_convergence_routes import generate_future_horizons_prompt
    formatted_prompt = generate_future_horizons_prompt(topic, article_rows, "", None)

    ai_model = get_ai_model("gpt-4o")
    if not ai_model:
        raise RuntimeError("gpt-4o model not available for Three Horizons run.")

    started = _time.time()
    raw_response = await ai_model.agenerate_response(
        [{"role": "user", "content": formatted_prompt}]
    )

    # Parse JSON out of the response — strip fences if present.
    s = (raw_response or "").strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    # The agent sometimes wraps JSON in prose; grab the outermost braces.
    if "{" in s and "}" in s:
        s = s[s.find("{"): s.rfind("}") + 1]
    try:
        parsed = json.loads(s)
    except Exception as e:
        raise RuntimeError(f"Three Horizons response was not valid JSON: {e}")

    scenarios = parsed.get("scenarios") or []
    if not scenarios:
        raise RuntimeError("Three Horizons returned no scenarios.")

    # Normalize horizon types to lowercase h1/h2/h3 — the Future Horizons tab
    # filters strictly on these, and the model occasionally emits "H1".
    for sc in scenarios:
        t = str(sc.get("type") or "").strip().lower()
        if t in ("h1", "h2", "h3"):
            sc["type"] = t

    run_id = str(_uuid.uuid4())
    raw_output = {
        "topic": topic,
        "scenarios": scenarios,
        "disruption_scenarios": parsed.get("disruption_scenarios", []),
        "metadata": {
            "topic_label": topic,
            "topic_description": candidate.get("proposed_description"),
            "articles_analyzed": len(article_rows),
            "model_used": "gpt-4o",
            "generated_at": _dt.utcnow().isoformat(),
            "analysis_type": "candidate_promotion",
            "source_candidate_id": candidate.get("id"),
        },
    }
    db.facade.save_future_horizons_analysis(
        analysis_id=run_id,
        user_id=None,
        topic=topic,
        model_used="gpt-4o",
        raw_output=raw_output,
        total_articles_analyzed=len(article_rows),
        analysis_duration_seconds=_time.time() - started,
    )

    # Bind the candidate's article URIs to this run so the assessment
    # service has a reference set.
    try:
        db.facade.save_future_horizon_articles(
            horizon_id=run_id, article_uris=article_uris, topic=topic,
        )
    except Exception as e:
        logger.warning(
            "Failed to save reference articles for horizons %s: %s", run_id, e,
        )
    return run_id


async def _run_paired_assessment(horizons_run_id: str) -> None:
    """Run a live + placebo assessment against a freshly created horizons
    run, then apply the baseline correction — mirrors the route handler
    at ``POST /api/forecast/{run_id}/assess-paired`` minus the HTTP +
    background-task scaffolding.
    """
    from app.services.forecast_assessment_service import (
        assess_run, apply_baseline_correction,
    )

    live = await assess_run(
        run_id=horizons_run_id, mode="live",
        window_weeks=12, granularity="auto",
    )
    placebo = await assess_run(
        run_id=horizons_run_id, mode="placebo",
        window_weeks=12, granularity="auto",
    )
    apply_baseline_correction(
        live_assessment_id=(live or {}).get("id"),
        placebo_assessment_id=(placebo or {}).get("id"),
    )
