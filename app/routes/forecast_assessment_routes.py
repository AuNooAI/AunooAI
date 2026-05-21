"""HTTP routes for the Forecast Assessment feature.

Exposes:
    POST /api/forecast/{run_id}/assess         — single-mode assessment job
    POST /api/forecast/{run_id}/assess-paired  — runs live + placebo on the
        same window_weeks and computes baseline-corrected support rates per
        scenario. The placebo functions as a temporal canary: subtracting the
        pre-forecast support rate from the post-forecast rate removes
        baseline-rate inflation (where a "supports_trajectory" article would
        have classified the same way before the forecast existed).
    GET  /api/forecast/{run_id}/assessment      — most recent assessment
    GET  /api/forecast/assessment/job/{task_id} — job progress
    GET  /api/forecast/{run_id}/assessment/{assessment_id}/articles

The assessment itself is long-running (5–15 min), so POST returns a
background task ID and the UI polls /api/forecast/assessment/job/{task_id}.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/forecast/{run_id}/assess")
async def kick_off_assessment(
    run_id: str,
    mode: str = Query("live", pattern="^(live|placebo)$"),
    max_articles: int = Query(2000, ge=10, le=5000),
    classify_model: str = Query("gpt-4.1-mini"),
    margin: float = Query(0.04, ge=0.0, le=0.5),
    granularity: str = Query("auto", pattern="^(auto|deck|db)$"),
    window_weeks: Optional[int] = Query(None, ge=1, le=104),
):
    """Start a forecast assessment as a background task. Returns task_id for polling."""
    from app.services.background_task_manager import get_task_manager
    from app.services.forecast_assessment_service import assess_run
    from app.database import get_database_instance

    db = get_database_instance()
    run = db.facade.get_future_horizons_analysis(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Forecast run {run_id} not found")

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"forecast_assessment:{run_id}",
        total_items=100,
        metadata={
            "run_id": run_id,
            "mode": mode,
            "topic": run.get("topic"),
        },
    )

    async def _job(progress_callback=None):
        def _cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        result = await assess_run(
            run_id=run_id,
            mode=mode,
            max_articles=max_articles,
            classify_model=classify_model,
            margin=margin,
            granularity=granularity,
            window_weeks=window_weeks,
            progress_callback=_cb,
        )
        return {
            "assessment_id": result.get("id"),
            "topic": result.get("topic"),
            "evidence_count": result.get("evidence_count"),
            "scenarios_count": result.get("scenarios_count"),
        }

    import asyncio
    asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "task_id": task_id,
        "run_id": run_id,
        "mode": mode,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.post("/api/forecast/{run_id}/assess-paired")
async def kick_off_paired_assessment(
    run_id: str,
    window_weeks: int = Query(8, ge=1, le=52),
    max_articles: int = Query(2000, ge=10, le=5000),
    classify_model: str = Query("gpt-4.1-mini"),
    margin: float = Query(0.04, ge=0.0, le=0.5),
    granularity: str = Query("auto", pattern="^(auto|deck|db)$"),
):
    """Run live + placebo assessments on the same N-week window, then patch
    the live assessment with baseline-corrected support rates.

    Both runs see the same number of weeks of articles (live = forecast+N
    weeks, placebo = forecast-N weeks). The placebo's per-pool support rate
    is subtracted from the live's, surfacing only the *incremental* support
    attributable to the post-forecast window."""
    from app.services.background_task_manager import get_task_manager
    from app.services.forecast_assessment_service import assess_run, apply_baseline_correction
    from app.database import get_database_instance

    db = get_database_instance()
    run = db.facade.get_future_horizons_analysis(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Forecast run {run_id} not found")

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"forecast_paired:{run_id}",
        total_items=100,
        metadata={
            "run_id": run_id,
            "topic": run.get("topic"),
            "window_weeks": window_weeks,
        },
    )

    async def _job(progress_callback=None):
        def _cb_for(phase_start: int, phase_end: int):
            def _emit(pct: int, msg: str):
                # Map child progress (0-100) onto [phase_start, phase_end].
                child_pct = min(max(pct, 0), 100)
                mapped = phase_start + int((phase_end - phase_start) * child_pct / 100)
                if progress_callback:
                    progress_callback(mapped, msg)
            return _emit

        live_result = await assess_run(
            run_id=run_id,
            mode="live",
            max_articles=max_articles,
            classify_model=classify_model,
            margin=margin,
            granularity=granularity,
            window_weeks=window_weeks,
            progress_callback=_cb_for(0, 48),
        )
        live_assessment_id = (live_result or {}).get("id")

        placebo_result = await assess_run(
            run_id=run_id,
            mode="placebo",
            max_articles=max_articles,
            classify_model=classify_model,
            margin=margin,
            granularity=granularity,
            window_weeks=window_weeks,
            progress_callback=_cb_for(48, 96),
        )
        placebo_assessment_id = (placebo_result or {}).get("id")

        if progress_callback:
            progress_callback(97, "Computing baseline correction")

        correction = apply_baseline_correction(
            live_assessment_id=live_assessment_id,
            placebo_assessment_id=placebo_assessment_id,
        )

        if progress_callback:
            progress_callback(100, "Paired assessment complete")

        return {
            "live_assessment_id": live_assessment_id,
            "placebo_assessment_id": placebo_assessment_id,
            "window_weeks": window_weeks,
            "correction": correction,
        }

    import asyncio
    asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "task_id": task_id,
        "run_id": run_id,
        "window_weeks": window_weeks,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.get("/api/forecast/assessment/job/{task_id}")
async def get_assessment_job(task_id: str):
    """Poll job progress."""
    from app.services.background_task_manager import get_task_manager

    tm = get_task_manager()
    status = tm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return status


@router.get("/api/forecast/{run_id}/assessment")
async def get_latest_assessment(run_id: str):
    """Return the most recent assessment for the run (with scenario verdicts).

    If the supplied run has no assessments stored, falls back to the latest
    assessment for the run's topic across any horizons run. This keeps the
    Forecast Tracker tab useful when the trend-convergence page has
    freshly-generated a new horizons run while the saved assessments are
    against an older run for the same topic.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    record = db.facade.get_latest_forecast_assessment(run_id)

    # Always resolve the run's topic so we can fallback by topic.
    run = db.facade.get_future_horizons_analysis(run_id)
    topic = (run or {}).get("topic")
    fallback_used = False
    if not record and topic:
        record = db.facade.get_latest_forecast_assessment_by_topic(topic)
        fallback_used = bool(record)

    raw = run.get("raw_output") if run else None
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    scenarios = (raw or {}).get("scenarios", []) if raw else []

    return {
        "run_id": run_id,
        "assessment": record or None,
        "scenarios": scenarios,
        "forecast_generated_at": run.get("created_at") if run else None,
        "topic_fallback": fallback_used,
    }


@router.get("/api/forecast/snapshots/by-topic")
async def get_snapshots_by_topic(
    topic: str = Query(...),
    limit: int = Query(52, ge=1, le=520),
):
    """Chronological list of paired-mode assessments for a topic.

    Each snapshot has the per-scenario ``net_rate`` extracted from its
    baseline_correction block so the UI can plot the trajectory over time.
    Powers the "Snapshot history" panel on the Forecast Tracker tab.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    snapshots = db.facade.get_forecast_assessment_snapshots(topic=topic, limit=limit)
    return {"topic": topic, "snapshots": snapshots, "count": len(snapshots)}


@router.get("/api/forecast/tracker-monitor/status")
async def get_tracker_monitor_status():
    """Inspect the scheduled-reassessment monitor — what it's doing, when it
    last checked, what topics it has kicked off recently."""
    from app.tasks.forecast_tracker_monitor import get_task_status
    return get_task_status()


@router.get("/api/forecast/{run_id}/assessment/{assessment_id}/export.pptx")
async def export_assessment_pptx(run_id: str, assessment_id: str):
    """Render the assessment as a slide-per-scenario PowerPoint deck mirroring
    the Wiley Horizons brief layout (slides 64-68 of the Feb 2026 deck).

    Pulls the latest assessment for the run (we treat the explicit
    ``assessment_id`` as a sanity-check parameter so a stale URL doesn't
    silently render a newer assessment).

    On the first export for an assessment that has no cached narratives,
    LLM synthesis fires and persists the prose to ``summary_md`` /
    ``summary.exec_narrative`` so subsequent exports are instant.
    """
    from app.database import get_database_instance
    from app.services.forecast_pptx_export import build_assessment_pptx
    from app.services.forecast_narrative import ensure_narratives_for_assessment

    db = get_database_instance()
    record = db.facade.get_latest_forecast_assessment(run_id)
    if not record:
        # Fallback: assessment may be for a sibling run of the same topic.
        run = db.facade.get_future_horizons_analysis(run_id)
        topic = (run or {}).get("topic")
        if topic:
            record = db.facade.get_latest_forecast_assessment_by_topic(topic)
    if not record:
        raise HTTPException(status_code=404, detail="No assessment found")
    if record.get("id") != assessment_id:
        logger.info(
            "PPTX export requested assessment %s but latest is %s; rendering latest",
            assessment_id, record.get("id"),
        )

    # Lazily synthesize any missing narratives + persist them so the next
    # export is fast. This can add 5-15s on first export per assessment.
    try:
        enriched = await ensure_narratives_for_assessment(record["id"])
        if enriched:
            record = enriched
    except Exception as e:
        logger.warning("Narrative synthesis failed for %s: %s — exporting without",
                       record.get("id"), e)

    forecast_run = db.facade.get_future_horizons_analysis(record.get("run_id") or run_id)
    blob = build_assessment_pptx(record, forecast_run or {})

    topic_slug = (record.get("topic") or "forecast").lower().replace(" ", "_").replace("/", "_")[:60]
    fname = f"forecast_assessment_{topic_slug}_{record.get('id', 'latest')}.pptx"
    return Response(
        content=blob,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/api/forecast/{run_id}/assessment/{assessment_id}/articles")
async def get_assessment_articles(
    run_id: str,
    assessment_id: str,
    scenario_idx: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
):
    """Paginated per-article verdicts. If scenario_idx supplied, scopes to one scenario."""
    from app.database import get_database_instance
    db = get_database_instance()
    rows = db.facade.get_forecast_article_verdicts(assessment_id, scenario_idx=scenario_idx)
    if not rows:
        return {"assessment_id": assessment_id, "articles": []}

    # Join in article titles to make the UI render-ready
    uris = [r["article_uri"] for r in rows][:limit]
    if uris:
        from sqlalchemy import text
        conn = db._temp_get_connection()
        try:
            placeholders = ",".join([f":u{i}" for i in range(len(uris))])
            params = {f"u{i}": u for i, u in enumerate(uris)}
            sql = text(
                f"SELECT uri, title, news_source, submission_date, summary "
                f"FROM articles WHERE uri IN ({placeholders})"
            )
            article_rows = conn.execute(sql, params).mappings().all()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        by_uri = {a["uri"]: dict(a) for a in article_rows}
    else:
        by_uri = {}

    out = []
    for r in rows[:limit]:
        meta = by_uri.get(r["article_uri"]) or {}
        out.append({**r, "article": meta})
    return {"assessment_id": assessment_id, "articles": out, "total_in_assessment": len(rows)}
