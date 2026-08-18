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

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, JSONResponse

from app.security.session import require_admin, verify_session_api

logger = logging.getLogger(__name__)

# Every endpoint on this router is private. Authentication is enforced once here
# rather than per-endpoint so a new route cannot be added unprotected by accident.
router = APIRouter(dependencies=[Depends(verify_session_api)])


@router.post("/api/forecast/{run_id}/assess")
async def kick_off_assessment(
    run_id: str,
    mode: str = Query("live", pattern="^(live|placebo)$"),
    max_articles: int = Query(2000, ge=10, le=5000),
    classify_model: str = Query("gpt-5.4-mini"),
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
    classify_model: str = Query("gpt-5.4-mini"),
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


@router.get("/api/forecast/topics/{topic}/latest-run")
async def get_latest_run_for_topic(topic: str):
    """Return the most recent ``future_horizons_runs`` row for a topic, or
    404 if none exist. The UI uses this to resolve the correct ``run_id``
    when an analyst opens the Forecast Tracker via the Topics dashboard —
    where the previously-loaded ``analysis_id`` may belong to a different
    topic entirely.
    """
    from app.database import get_database_instance
    from sqlalchemy import text as sa_text
    db = get_database_instance()
    sql = sa_text("""
        SELECT id, topic, model_used, created_at
        FROM future_horizons_runs
        WHERE topic = :topic
        ORDER BY created_at DESC
        LIMIT 1
    """)
    row = db.facade._execute_with_rollback(sql, {"topic": topic}).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No future_horizons_runs entry for topic '{topic}'",
        )
    rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    created = rd.get("created_at")
    if hasattr(created, "isoformat"):
        rd["created_at"] = created.isoformat()
    return {
        "run_id": rd["id"],
        "topic": rd["topic"],
        "model_used": rd.get("model_used"),
        "generated_at": rd.get("created_at"),
    }


@router.get("/api/forecast/{run_id}/assessment")
async def get_latest_assessment(run_id: str):
    """Return the most recent assessment **for this run**, with scenario verdicts.

    ``assessment`` only ever holds an assessment whose ``run_id`` matches the
    URL. When the run has not been assessed yet it is ``null`` and the caller
    gets this run's own scenarios, so the UI can render a real empty state.

    An assessment of an *older* run for the same topic used to be served in
    ``assessment`` as if it belonged to this run. Scenarios came from the
    requested run while verdicts came from the other one, so ``scenario_idx``
    values did not line up and the two could describe different scenarios. Any
    such assessment is now returned separately in ``historical_assessment``,
    carries its own ``run_id``, and is flagged read-only: it is for display
    while the new run is still being assessed, never a mutation target.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    record = db.facade.get_latest_forecast_assessment(run_id)

    # An assessment row that is not for this run must never land in `assessment`.
    if record and record.get("run_id") and record.get("run_id") != run_id:
        logger.error(
            "get_latest_forecast_assessment(%s) returned an assessment for run %s; "
            "dropping it rather than serving cross-run state",
            run_id, record.get("run_id"),
        )
        record = None

    run = db.facade.get_future_horizons_analysis(run_id)
    topic = (run or {}).get("topic")

    historical = None
    if not record and topic:
        candidate = db.facade.get_latest_forecast_assessment_by_topic(topic)
        # Only historical if it really is another run — never re-label this run's own.
        if candidate and candidate.get("run_id") and candidate.get("run_id") != run_id:
            historical = candidate
        elif candidate and candidate.get("run_id") == run_id:
            record = candidate

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
        # Read-only view of an older run's assessment for the same topic. The
        # UI must not offer scenario status or promotion against this.
        "historical_assessment": historical,
        "historical_assessment_run_id": (historical or {}).get("run_id"),
        "historical_read_only": bool(historical),
        # Retained for older UI builds that branch on this flag.
        "topic_fallback": bool(historical),
    }


def _require_assessment_in_run(db, run_id: str, assessment_id: str) -> dict:
    """Load an assessment and refuse it if it belongs to a different run.

    Run-scoped URLs carry both ids. Serving an assessment from another run
    under this URL is what let the Forecast Tracker mix a run's scenarios with
    another run's verdicts, so a mismatch is an error rather than something to
    paper over with the latest row.
    """
    from app.services.forecast_assessment_service import _hydrate_assessment_by_id

    record = _hydrate_assessment_by_id(db, assessment_id)
    if not record:
        raise HTTPException(
            status_code=404, detail=f"Assessment {assessment_id} not found",
        )
    owner = record.get("run_id")
    if owner and owner != run_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Assessment {assessment_id} belongs to run {owner}, not {run_id}. "
                "Reload the Forecast Tracker for this run."
            ),
        )
    return record


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
async def export_assessment_pptx(
    run_id: str,
    assessment_id: str,
    updates_only: bool = Query(False, description="Render only what's changed since the prior live snapshot."),
):
    """Render the assessment as a slide-per-scenario PowerPoint deck mirroring
    the Wiley Horizons brief layout (slides 64-68 of the Feb 2026 deck).

    Renders exactly the ``assessment_id`` in the URL, and only if it belongs
    to ``run_id``. It used to render whatever the latest assessment for the run
    was — including, via a topic fallback, one belonging to a different run —
    which meant a stale link could silently produce a deck of someone else's
    analysis under this run's heading.

    On the first export for an assessment that has no cached narratives,
    LLM synthesis fires and persists the prose to ``summary_md`` /
    ``summary.exec_narrative`` so subsequent exports are instant.

    With ``updates_only=true``, the export diffs against the previous
    ``mode='live'`` assessment for the run and emits a slimmer deck:
    only scenarios with new evidence or verdict flips, plus newly-emerged
    surprise clusters.
    """
    from app.database import get_database_instance
    from app.services.forecast_pptx_export import build_assessment_pptx
    from app.services.forecast_narrative import ensure_narratives_for_assessment

    db = get_database_instance()
    record = _require_assessment_in_run(db, run_id, assessment_id)

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

    prior = None
    if updates_only:
        prior = db.facade.get_prior_live_assessment(
            run_id=record.get("run_id") or run_id,
            before_assessed_at=record.get("assessed_at"),
        )
        # When no prior snapshot exists yet, fall back to a stub "first snapshot"
        # deck rather than 422-ing — the browser would try to save the JSON
        # error response as a .pptx file otherwise.

    blob = build_assessment_pptx(
        record, forecast_run or {},
        updates_only=updates_only,
        prior_assessment=prior,
    )

    topic_slug = (record.get("topic") or "forecast").lower().replace(" ", "_").replace("/", "_")[:60]
    suffix = "_updates" if updates_only else ""
    fname = f"forecast_assessment_{topic_slug}{suffix}_{record.get('id', 'latest')}.pptx"
    return Response(
        content=blob,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Promote unanticipated developments to tracked scenarios ──────────────

class _DraftScenarioRequest(__import__("pydantic").BaseModel):  # noqa: N801 — keep BaseModel inline
    assessment_id: str
    surprise_index: int


@router.post("/api/forecast/{run_id}/scenarios/draft-from-surprise")
async def draft_scenario_from_surprise(run_id: str, payload: _DraftScenarioRequest):
    """LLM-draft a tracked scenario from a surprise cluster on a stored assessment.

    Returns ``{title, description, horizon_type, timeframe}`` for the UI to
    present in an editable modal. Nothing is persisted at this step — the UI
    posts the (possibly edited) draft to the create endpoint below.
    """
    from app.database import get_database_instance
    from app.services.forecast_narrative import synthesize_scenario_from_surprise

    db = get_database_instance()

    # The drafted scenario becomes an addendum to THIS run, so the surprise it
    # is drafted from must come from this run's own assessment. Promoting a
    # surprise found in a sibling run's assessment would attach evidence from
    # one forecast to another.
    assessment = _require_assessment_in_run(db, run_id, payload.assessment_id)

    surprises = assessment.get("surprises") or []
    if payload.surprise_index < 0 or payload.surprise_index >= len(surprises):
        raise HTTPException(
            status_code=422,
            detail=f"surprise_index {payload.surprise_index} out of range (0..{len(surprises)-1})",
        )

    cluster = surprises[payload.surprise_index]
    topic = assessment.get("topic") or ""
    try:
        draft = await synthesize_scenario_from_surprise(cluster, topic)
    except Exception as e:
        logger.error("Scenario draft failed for run %s surprise %s: %s",
                     run_id, payload.surprise_index, e)
        raise HTTPException(status_code=502, detail=f"LLM draft failed: {e}")

    sample_uris = [a.get("uri") for a in (cluster.get("sample_articles") or []) if a.get("uri")]
    return {
        **draft,
        "source_assessment_id": payload.assessment_id,
        "source_surprise_label": cluster.get("label"),
        "source_article_uris": sample_uris,
    }


class _CreateScenarioRequest(__import__("pydantic").BaseModel):  # noqa: N801
    title: str
    description: str
    horizon_type: str
    timeframe: str | None = None
    source_assessment_id: str | None = None
    source_surprise_label: str | None = None
    source_article_uris: list[str] | None = None
    window_weeks: int = 8


@router.post("/api/forecast/{run_id}/scenarios")
async def create_user_scenario(run_id: str, payload: _CreateScenarioRequest):
    """Persist a user-promoted scenario and kick off a fresh paired assessment.

    The new scenario is appended to the run's scenario list at assessment
    time (the original forecast's ``raw_output['scenarios']`` is never
    mutated). After saving we immediately trigger an ``assess-paired`` job
    so the user sees how articles classify against the new scenario.
    """
    from app.database import get_database_instance
    from app.services.background_task_manager import get_task_manager
    from app.services.forecast_assessment_service import assess_run, apply_baseline_correction

    db = get_database_instance()
    run = db.facade.get_future_horizons_analysis(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Forecast run {run_id} not found")

    horizon = (payload.horizon_type or "h2").lower()
    if horizon not in ("h1", "h2", "h3"):
        raise HTTPException(status_code=422, detail="horizon_type must be h1, h2, or h3")

    scenario_id = db.facade.save_forecast_user_scenario(
        run_id=run_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        horizon_type=horizon,
        timeframe=(payload.timeframe or "").strip() or None,
        source_assessment_id=payload.source_assessment_id,
        source_surprise_label=payload.source_surprise_label,
        source_article_uris=payload.source_article_uris or [],
    )

    # Kick off the fresh paired assessment so the new scenario gets classified.
    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"forecast_paired:{run_id}",
        total_items=100,
        metadata={
            "run_id": run_id,
            "topic": run.get("topic"),
            "window_weeks": payload.window_weeks,
            "triggered_by": "scenario_promotion",
            "new_scenario_id": scenario_id,
        },
    )

    async def _job(progress_callback=None):
        def _cb_for(phase_start: int, phase_end: int):
            def _emit(pct: int, msg: str):
                child_pct = min(max(pct, 0), 100)
                mapped = phase_start + int((phase_end - phase_start) * child_pct / 100)
                if progress_callback:
                    progress_callback(mapped, msg)
            return _emit

        live_result = await assess_run(
            run_id=run_id, mode="live",
            window_weeks=payload.window_weeks,
            progress_callback=_cb_for(0, 48),
        )
        placebo_result = await assess_run(
            run_id=run_id, mode="placebo",
            window_weeks=payload.window_weeks,
            progress_callback=_cb_for(48, 96),
        )
        if progress_callback:
            progress_callback(97, "Computing baseline correction")
        correction = apply_baseline_correction(
            live_assessment_id=(live_result or {}).get("id"),
            placebo_assessment_id=(placebo_result or {}).get("id"),
        )
        if progress_callback:
            progress_callback(100, "Reassessment complete")
        return {
            "live_assessment_id": (live_result or {}).get("id"),
            "placebo_assessment_id": (placebo_result or {}).get("id"),
            "correction": correction,
            "new_scenario_id": scenario_id,
        }

    import asyncio
    asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "scenario_id": scenario_id,
        "task_id": task_id,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.get("/api/forecast/{run_id}/scenarios")
async def list_user_scenarios(run_id: str):
    """List addendum scenarios (user-promoted) for a forecast run."""
    from app.database import get_database_instance
    db = get_database_instance()
    statuses = db.facade.get_forecast_scenario_statuses(run_id)
    return {
        "run_id": run_id,
        "addendum_scenarios": db.facade.get_forecast_user_scenarios(run_id),
        "scenario_statuses": statuses,
    }


# ── Mark-as-done overlay ─────────────────────────────────────────────────

class _ScenarioStatusRequest(__import__("pydantic").BaseModel):  # noqa: N801
    scenario_idx: int | None = None
    user_scenario_id: str | None = None
    # Preferred identifier for an original scenario. scenario_idx is accepted
    # for older clients and resolved to a key server-side.
    scenario_key: str | None = None
    status: str  # 'active' | 'done'
    note: str | None = None


@router.patch("/api/forecast/{run_id}/scenarios/status")
async def patch_scenario_status(run_id: str, payload: _ScenarioStatusRequest):
    """Mark a scenario as done (or revert to active).

    Identify the scenario with ``scenario_key`` (originals) or
    ``user_scenario_id`` (promoted). ``scenario_idx`` is still accepted from
    older clients and resolved to the run's key here, because an index is only
    a position and moves between assessments. Done scenarios are skipped from
    reranker/LLM on the next assessment run and rendered in the "Resolved
    scenarios" section in the UI.
    """
    from app.database import get_database_instance

    identifiers = [
        payload.scenario_key is not None,
        payload.user_scenario_id is not None,
        payload.scenario_idx is not None,
    ]
    if sum(identifiers) != 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Exactly one of scenario_key (originals), user_scenario_id "
                "(promoted) or scenario_idx (legacy originals) must be set"
            ),
        )
    status = (payload.status or "active").lower()
    if status not in ("active", "done"):
        raise HTTPException(status_code=422, detail="status must be 'active' or 'done'")

    db = get_database_instance()
    run = db.facade.get_future_horizons_analysis(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Forecast run {run_id} not found")

    if payload.user_scenario_id is not None:
        owned = {s.get("id") for s in (db.facade.get_forecast_user_scenarios(run_id) or [])}
        if payload.user_scenario_id not in owned:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Promoted scenario {payload.user_scenario_id} does not belong to run "
                    f"{run_id}. Promoted scenarios stay with the run they were added to."
                ),
            )
        row = db.facade.save_forecast_scenario_status(
            run_id=run_id,
            user_scenario_id=payload.user_scenario_id,
            status=status,
            note=(payload.note or None),
        )
        return {"status_row": row}

    # Original scenario. Resolve to this run's own scenarios so an identifier
    # carried over from a previously-displayed run cannot mark an unrelated
    # scenario done, and so an index is converted to the stable key before it is
    # written.
    from app.services.scenario_identity import scenario_key_for

    raw = run.get("raw_output")
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    originals = (raw or {}).get("scenarios") or []

    resolved_idx = None
    resolved_key = None
    if payload.scenario_idx is not None:
        if payload.scenario_idx < 0 or payload.scenario_idx >= len(originals):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"scenario_idx {payload.scenario_idx} is not an original scenario of "
                    f"run {run_id} (it has {len(originals)}). Promoted scenarios are "
                    "identified by user_scenario_id."
                ),
            )
        resolved_idx = payload.scenario_idx
        resolved_key = scenario_key_for(run_id, originals[resolved_idx], resolved_idx)
    else:
        for i, sc in enumerate(originals):
            if isinstance(sc, dict) and scenario_key_for(run_id, sc, i) == payload.scenario_key:
                resolved_idx, resolved_key = i, payload.scenario_key
                break
        if resolved_key is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"scenario_key {payload.scenario_key} is not a scenario of run {run_id}. "
                    "Reload the Forecast Tracker for this run."
                ),
            )

    row = db.facade.save_forecast_scenario_status(
        run_id=run_id,
        scenario_key=resolved_key,
        scenario_idx=resolved_idx,   # stored as display ordering, not identity
        status=status,
        note=(payload.note or None),
    )
    return {"status_row": row}


# ── Per-topic delivery config ────────────────────────────────────────────

@router.get("/api/forecast/topics/delivery")
async def list_topic_delivery_configs():
    """Return all topics × cadence × recipient × last_delivered. Used by the
    Wiley Deliverables panel in the UI."""
    from app.database import get_database_instance
    db = get_database_instance()
    return {"configs": db.facade.get_forecast_topic_delivery_configs()}


class _TopicDeliveryRequest(__import__("pydantic").BaseModel):  # noqa: N801
    cadence: str  # 'monthly' | 'quarterly' | 'none'
    recipient_email: str | None = None


@router.patch("/api/forecast/topics/{topic}/delivery",
              dependencies=[Depends(require_admin)])
async def patch_topic_delivery_config(topic: str, payload: _TopicDeliveryRequest):
    """Upsert the delivery cadence + recipient for a topic. Admin only: this
    decides who receives generated reports by email."""
    from app.database import get_database_instance
    db = get_database_instance()
    cadence = (payload.cadence or "none").lower()
    if cadence not in ("monthly", "quarterly", "none"):
        raise HTTPException(status_code=422, detail="cadence must be monthly|quarterly|none")
    return {"config": db.facade.upsert_forecast_topic_delivery_config(
        topic=topic,
        cadence=cadence,
        recipient_email=(payload.recipient_email or None),
    )}


# ── Topic lifecycle: metadata + overlay management ────────────────────────


class _TopicMetadataCreate(__import__("pydantic").BaseModel):  # noqa: N801
    topic: str
    display_name: str | None = None
    description: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    source_topics: list[str] | None = None


class _TopicMetadataPatch(__import__("pydantic").BaseModel):  # noqa: N801
    display_name: str | None = None
    description: str | None = None
    owner: str | None = None
    status: str | None = None  # 'draft' | 'active' | 'archived'
    tags: list[str] | None = None


@router.get("/api/forecast/topics")
async def list_topics_with_lifecycle():
    """Single endpoint for the Topics dashboard: one row per topic merging
    metadata, latest assessment, and delivery config. Health dot is derived
    on the client from these fields."""
    from app.database import get_database_instance
    db = get_database_instance()
    return {"topics": db.facade.list_topics_with_lifecycle()}


@router.get("/api/forecast/topics/available")
async def list_available_source_topics():
    """Every distinct ``articles.topic`` value with its article count.

    Drives the Add-Topic wizard's source-topic multi-select so an analyst
    picks from topics that actually have a corpus rather than typing a name
    that must match exactly."""
    from app.database import get_database_instance
    from sqlalchemy import text as sa_text
    db = get_database_instance()
    rows = db.facade._execute_with_rollback(sa_text("""
        SELECT topic, COUNT(*) AS count
        FROM articles
        WHERE topic IS NOT NULL AND topic <> ''
        GROUP BY topic
        ORDER BY count DESC
    """)).fetchall()
    return {"topics": [
        {"topic": r._mapping["topic"], "count": int(r._mapping["count"])}
        for r in rows
    ]}


@router.get("/api/forecast/topics/suggest")
async def suggest_source_topics(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=25),
):
    """Freeform → ranked existing topics. Vector-searches the corpus for the
    typed text and aggregates the hits by ``topic`` so a name like "Quantum
    Advantage" surfaces "Quantum Computing" even though the strings differ.

    Returns each candidate topic with how many of the top semantic hits it
    accounts for (``match_count``) and its total corpus size (``total``)."""
    from app.database import get_database_instance
    from app.vector_store_pgvector import search_articles_async
    db = get_database_instance()

    try:
        results = await search_articles_async(q, top_k=150)
    except Exception as e:
        logger.warning("Topic suggest vector search failed for %r: %s", q, e)
        results = []

    agg: dict[str, dict] = {}
    for rank, r in enumerate(results):
        # async results nest fields under "metadata"; sync returns them flat
        t = r.get("topic") or (r.get("metadata") or {}).get("topic")
        if not t:
            continue
        slot = agg.setdefault(t, {"topic": t, "match_count": 0, "best_score": None})
        slot["match_count"] += 1
        # search results are ordered best-first; capture the strongest hit
        if slot["best_score"] is None:
            slot["best_score"] = r.get("score")

    # attach total corpus counts for the matched topics
    if agg:
        from sqlalchemy import text as sa_text
        rows = db.facade._execute_with_rollback(sa_text("""
            SELECT topic, COUNT(*) AS count
            FROM articles
            WHERE topic = ANY(:topics)
            GROUP BY topic
        """), {"topics": list(agg.keys())}).fetchall()
        totals = {r._mapping["topic"]: int(r._mapping["count"]) for r in rows}
        for t, slot in agg.items():
            slot["total"] = totals.get(t, 0)

    ranked = sorted(agg.values(), key=lambda s: s["match_count"], reverse=True)
    return {"query": q, "suggestions": ranked[:limit]}


@router.post("/api/forecast/topics")
async def create_topic_metadata(payload: _TopicMetadataCreate):
    """Register a new topic — wizard step 1. Creates a metadata row in
    'draft' status. Idempotent: if a row already exists, returns it."""
    from app.database import get_database_instance
    topic = (payload.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic is required")
    db = get_database_instance()
    existing = db.facade.get_forecast_topic_metadata(topic)
    if existing:
        return {"topic": existing, "created": False}
    row = db.facade.upsert_forecast_topic_metadata(
        topic,
        display_name=payload.display_name,
        description=payload.description,
        owner=payload.owner,
        tags=payload.tags,
        source_topics=payload.source_topics,
        status="draft",
        overlay_status="missing",
    )
    return {"topic": row, "created": True}


@router.patch("/api/forecast/topics/{topic}/metadata")
async def patch_topic_metadata(topic: str, payload: _TopicMetadataPatch):
    """Edit description / owner / tags / status. Only supplied fields update."""
    from app.database import get_database_instance
    if payload.status is not None and payload.status not in ("draft", "active", "archived"):
        raise HTTPException(status_code=422, detail="status must be draft|active|archived")
    db = get_database_instance()
    return {"topic": db.facade.upsert_forecast_topic_metadata(
        topic,
        display_name=payload.display_name,
        description=payload.description,
        owner=payload.owner,
        status=payload.status,
        tags=payload.tags,
    )}


def _overlay_slug(topic: str) -> str:
    """Filesystem-safe slug for the overlay file. Mirrors the existing
    naming convention (patent_cliffs_deck_overlay.json, etc.)."""
    import re
    s = re.sub(r"[^a-z0-9]+", "_", (topic or "").lower()).strip("_")
    return f"{s}_deck_overlay"


def _overlay_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "data" / "wiley_horizons"


class _WizardBuildRequest(__import__("pydantic").BaseModel):  # noqa: N801
    """Optional body for the wizard build — lets the analyst pin the seed to
    specific existing corpus topics. Omitted/empty falls back to exact-name
    match then corpus-wide semantic search."""
    source_topics: list[str] | None = None


@router.post("/api/forecast/topics/{topic}/wizard/build")
async def wizard_build_topic_pipeline(
    topic: str,
    article_limit: int = Query(60, ge=10, le=200),
    days_back: int = Query(90, ge=14, le=730),
    payload: Optional[_WizardBuildRequest] = None,
):
    """Wizard helper — fires the full horizons → paired assessment →
    overlay pipeline for an analyst-named topic in a single background
    task. Returns a ``task_id`` the wizard polls.

    The optional ``source_topics`` body pins the article seed to one or more
    existing corpus topics the analyst selected; otherwise the seed resolves
    by exact-name match then corpus-wide semantic search. Used by the
    Add-Topic wizard so the analyst doesn't have to bounce between the
    Future Horizons + Forecast Tracker tabs.
    """
    from app.database import get_database_instance
    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_candidate_pipeline import build_topic_pipeline
    import asyncio

    db = get_database_instance()
    if not db.facade.get_forecast_topic_metadata(topic):
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")

    source_topics = payload.source_topics if payload else None
    # Persist the seed provenance so downstream consumers (the assessment's
    # post-forecast article window, re-builds) can find the real corpus even
    # though the deck name tags no articles.
    if source_topics:
        db.facade.upsert_forecast_topic_metadata(topic, source_topics=source_topics)

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"wizard_build:{topic}",
        total_items=100,
        metadata={"topic": topic, "kind": "wizard_build"},
    )

    async def _job(progress_callback=None):
        return await build_topic_pipeline(
            topic,
            article_limit=article_limit,
            days_back=days_back,
            source_topics=source_topics,
            progress_callback=progress_callback,
        )

    asyncio.create_task(tm.run_task(task_id, _job))
    return {
        "task_id": task_id,
        "topic": topic,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.post("/api/forecast/topics/{topic}/overlay/generate")
async def generate_topic_overlay(topic: str):
    """Kick off LLM overlay generation as a background task. The task
    writes a .proposed file to data/wiley_horizons/ and flips the topic's
    overlay_status to 'auto_generated'. Returns a task_id the wizard polls."""
    from app.database import get_database_instance
    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_overlay_generator import generate_overlay_proposal
    import asyncio

    db = get_database_instance()
    if not db.facade.get_forecast_topic_metadata(topic):
        raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"overlay_generation:{topic}",
        total_items=100,
        metadata={"topic": topic, "kind": "overlay_generation"},
    )

    async def _job(progress_callback=None):
        def _cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
        proposed_path, overlay = await generate_overlay_proposal(
            topic, progress_callback=_cb
        )
        return {
            "topic": topic,
            "proposed_path": str(proposed_path),
            "scenarios_count": len((overlay or {}).get("deck_scenarios") or {}),
        }

    asyncio.create_task(tm.run_task(task_id, _job))
    return {
        "task_id": task_id,
        "topic": topic,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.get("/api/forecast/topics/{topic}/overlay/proposed")
async def get_topic_overlay_proposed(topic: str):
    """Return the proposed (LLM-generated) overlay JSON for review."""
    import json
    slug = _overlay_slug(topic)
    p = _overlay_dir() / f"{slug}.json.proposed"
    if not p.exists():
        raise HTTPException(status_code=404, detail="No proposed overlay on disk")
    try:
        return {"topic": topic, "overlay": json.loads(p.read_text())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read proposed overlay: {e}")


class _OverlayApprove(__import__("pydantic").BaseModel):  # noqa: N801
    overlay: dict


@router.post("/api/forecast/topics/{topic}/overlay/approve",
             dependencies=[Depends(require_admin)])
async def approve_topic_overlay(topic: str, payload: _OverlayApprove):
    """Persist the (possibly human-edited) overlay JSON as the production
    file. Marks overlay_status='human_reviewed', metadata.status='active'.
    Admin only: this replaces a production file."""
    import json
    from app.database import get_database_instance

    overlay = payload.overlay or {}
    if not overlay.get("topic"):
        overlay["topic"] = topic
    if overlay.get("topic") != topic:
        raise HTTPException(
            status_code=422,
            detail=f"Overlay's 'topic' field '{overlay.get('topic')}' must match URL topic '{topic}'",
        )

    slug = _overlay_slug(topic)
    final_path = _overlay_dir() / f"{slug}.json"
    final_path.write_text(json.dumps(overlay, indent=2, ensure_ascii=False))
    # Best-effort clean up the .proposed sibling
    proposed_path = _overlay_dir() / f"{slug}.json.proposed"
    if proposed_path.exists():
        try:
            proposed_path.unlink()
        except Exception:
            pass

    db = get_database_instance()
    row = db.facade.upsert_forecast_topic_metadata(
        topic,
        status="active",
        overlay_status="human_reviewed",
    )
    return {"topic": row, "overlay_path": str(final_path)}


# ── Wiley deliverables: preview + bundle PPTX + scheduled send ───────────

@router.get("/api/forecast/deliverables/preview")
async def preview_deliverable(cadence: str = Query(..., pattern="^(monthly|quarterly|all)$")):
    """Preview what would go in a cadence bundle: topic list, evidence counts,
    surprise counts, recipient summary. Used by the UI to confirm before
    generating or sending."""
    from app.database import get_database_instance
    db = get_database_instance()

    configs = db.facade.get_forecast_topic_delivery_configs()
    configs_by_topic = {c["topic"]: c for c in configs}

    if cadence == "all":
        from app.services.wiley_delivery_service import _all_topics_with_assessments
        topic_names = _all_topics_with_assessments(db)
    else:
        topic_names = [c["topic"] for c in configs
                       if (c.get("cadence") or "").lower() == cadence]

    topics_preview = []
    for topic in topic_names:
        cfg = configs_by_topic.get(topic) or {}
        assessment = db.facade.get_latest_forecast_assessment_by_topic(topic)
        if not assessment:
            topics_preview.append({
                "topic": topic,
                "ready": False,
                "reason": "No assessment yet",
                "recipient_email": cfg.get("recipient_email"),
            })
            continue
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        surprises = assessment.get("surprises") or []

        # Baseline-corrected label distribution for the all-topics dashboard
        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        baseline_labels = [(bc_per.get(str(v.get("scenario_idx"))) or {}).get("label")
                            or v.get("verdict_label")
                           for v in verdicts]
        label_dist = {}
        for lbl in baseline_labels:
            if not lbl:
                continue
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

        topics_preview.append({
            "topic": topic,
            "ready": True,
            "run_id": assessment.get("run_id"),
            "assessment_id": assessment.get("id"),
            "assessed_at": (
                assessment.get("assessed_at").isoformat()
                if hasattr(assessment.get("assessed_at"), "isoformat")
                else assessment.get("assessed_at")
            ),
            "evidence_count": assessment.get("evidence_count"),
            "scenarios_count": len(verdicts),
            "surprises_count": len(surprises),
            "label_distribution": label_dist,
            "recipient_email": cfg.get("recipient_email"),
            "cadence": (cfg.get("cadence") or "none").lower(),
        })

    return {
        "cadence": cadence,
        "topics": topics_preview,
        "configured_count": len(topic_names),
        "ready_count": sum(1 for t in topics_preview if t.get("ready")),
    }


@router.get("/api/forecast/deliverables/bundle.pptx")
async def export_bundle_pptx(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(False),
):
    """Render the cadence bundle PPTX on demand via the WileyBundleSupervisor pipeline.

    Returns 422 if no topics are configured for that cadence yet.
    Returns 202 + findings if the LLM-as-judge reviewer flagged ``error``
    severity issues — the UI shows the review panel so a human can resolve
    before the deck ships.
    """
    from app.services.wiley_delivery_service import generate_bundle

    try:
        blob, period_label, topics, verdict, findings = await generate_bundle(
            cadence, updates_only=updates_only
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # The download endpoint always returns a PPTX — even when the reviewer
    # flagged errors. The PPTX has a banner slide explaining the issue when
    # ``verdict == 'revision_requested'``. The /send endpoint is the one
    # that refuses to ship until a human approves.
    suffix = "_updates" if updates_only else ""
    fname = (
        f"wiley_forecast_{cadence}{suffix}_"
        + period_label.replace(" ", "_").lower()
        + ".pptx"
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        # Same URL + query string can otherwise serve a stale browser-cached
        # PPTX downloaded days earlier (the file we ship is data-dependent and
        # changes whenever a topic/assessment is added).
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    if verdict:
        headers["X-Review-Verdict"] = verdict
    if findings:
        headers["X-Review-Error-Count"] = str(
            sum(1 for f in findings if f.get("severity") == "error")
        )
    return Response(
        content=blob,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        headers=headers,
    )


@router.get("/api/forecast/deliverables/bundle.md")
async def export_bundle_markdown(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(False),
):
    """Markdown export of the bundle so reviewers can vet analytical content
    before committing to a PPTX regeneration. Runs the same supervisor
    pipeline as the PPTX export — cached calls return instantly."""
    from app.services.wiley_delivery_service import generate_bundle_markdown

    try:
        blob, period_label, topics, verdict, findings = await generate_bundle_markdown(
            cadence, updates_only=updates_only
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    suffix = "_updates" if updates_only else ""
    fname = (
        f"wiley_forecast_{cadence}{suffix}_"
        + period_label.replace(" ", "_").lower()
        + ".md"
    )
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    if verdict:
        headers["X-Review-Verdict"] = verdict
    if findings:
        headers["X-Review-Error-Count"] = str(
            sum(1 for f in findings if f.get("severity") == "error")
        )
    return Response(
        content=blob,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


@router.get("/api/forecast/deliverables/bundle.html")
async def export_bundle_html(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(False),
):
    """Self-contained interactive HTML bundle — one standalone file with the
    calibration matrix + per-trend evidence ledgers, data inlined. Same
    synthesis pipeline as the PPTX; cached calls return instantly."""
    from app.services.wiley_delivery_service import generate_bundle_html

    try:
        blob, period_label, topics, verdict, findings = await generate_bundle_html(
            cadence, updates_only=updates_only
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    suffix = "_updates" if updates_only else ""
    fname = (
        f"wiley_foresight_{cadence}{suffix}_"
        + period_label.replace(" ", "_").lower()
        + ".html"
    )
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    if verdict:
        headers["X-Review-Verdict"] = verdict
    return Response(content=blob, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/api/forecast/deliverables/bundle.docx")
async def export_bundle_docx(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(False),
):
    """Word-document export of the bundle — emailable executive briefing.

    Same supervisor pipeline as the PPTX export. The docx is intentionally
    NOT a slide-by-slide dump: it leads with the rewritten exec-summary
    letter, then cross-cutting themes, then a 1-paragraph-per-topic
    appendix. Modeled on the human reference at
    ``docs/Wiley_Horizons_Executive_Summary_May2026.docx``.
    """
    from app.services.wiley_delivery_service import generate_bundle_docx

    try:
        blob, period_label, topics, verdict, findings = await generate_bundle_docx(
            cadence, updates_only=updates_only
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    suffix = "_updates" if updates_only else ""
    fname = (
        f"wiley_forecast_{cadence}{suffix}_"
        + period_label.replace(" ", "_").lower()
        + ".docx"
    )
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    if verdict:
        headers["X-Review-Verdict"] = verdict
    if findings:
        headers["X-Review-Error-Count"] = str(
            sum(1 for f in findings if f.get("severity") == "error")
        )
    return Response(
        content=blob,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers=headers,
    )


@router.post("/api/forecast/deliverables/send",
             dependencies=[Depends(require_admin)])
async def send_bundle(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(True),
):
    """Generate + email the cadence bundle to each topic's configured recipient.

    Used by the "Send to recipients now" button in the UI and by the
    scheduled monthly/quarterly job on the 1st of the month/quarter.
    """
    from app.services.wiley_delivery_service import deliver_bundle
    from app.services.wiley_bundle_supervisor import BundleRequiresReviewError

    try:
        return await deliver_bundle(cadence, updates_only=updates_only)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BundleRequiresReviewError as e:
        return JSONResponse(
            status_code=202,
            content={
                "status": "revision_requested",
                "cadence": e.cadence,
                "period_label": e.period_label,
                "findings": e.findings,
                "message": "Review required before deck ships.",
            },
        )


# ── Background bundle generation with progress streaming ─────────────

@router.post("/api/forecast/deliverables/bundle/start")
async def start_bundle_generation(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    updates_only: bool = Query(False),
):
    """Kick off a bundle generation as a background task. Returns task_id
    so the UI can poll ``/api/forecast/assessment/job/{task_id}`` for
    per-stage progress, then GET ``/api/forecast/deliverables/bundle.pptx``
    once the task completes (the cache from this task makes the second
    request instant).
    """
    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_delivery_service import generate_bundle

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"wiley_bundle:{cadence}",
        total_items=100,
        metadata={"cadence": cadence, "updates_only": updates_only,
                  "kind": "wiley_bundle"},
    )

    async def _job(progress_callback=None):
        def _cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
        blob, period_label, topics, verdict, findings = await generate_bundle(
            cadence, updates_only=updates_only, progress_callback=_cb,
        )
        return {
            "cadence": cadence,
            "period_label": period_label,
            "topics": topics,
            "verdict": verdict,
            "error_count": sum(1 for f in (findings or []) if f.get("severity") == "error"),
            "warning_count": sum(1 for f in (findings or []) if f.get("severity") == "warning"),
            "blob_bytes": len(blob),
        }

    import asyncio
    asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "task_id": task_id,
        "cadence": cadence,
        "updates_only": updates_only,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
        "bundle_url": f"/api/forecast/deliverables/bundle.pptx?cadence={cadence}&updates_only={'true' if updates_only else 'false'}",
    }


# ── Reviewer gate endpoints ──────────────────────────────────────────

@router.get("/api/forecast/deliverables/review-status")
async def get_bundle_review_status(
    cadence: str = Query(..., pattern="^(monthly|quarterly|all)$"),
    period_label: str = Query(None, description="If omitted, returns the current period's review row."),
):
    """Return the current review-gate state for a (cadence, period_label).

    UI polls this when the bundle endpoint returns 202; surfaces the
    reviewer's findings + verdict so a human can act on them.
    """
    from app.database import get_database_instance
    from app.services.wiley_delivery_service import _period_label
    from datetime import datetime, timezone

    if not period_label:
        period_label = _period_label(cadence, datetime.now(timezone.utc))

    db = get_database_instance()
    row = db.facade.get_forecast_bundle_review(cadence, period_label) or {}
    return {"cadence": cadence, "period_label": period_label, "review": row}


class _BundleReviewApproveRequest(__import__("pydantic").BaseModel):  # noqa: N801
    cadence: str
    period_label: str
    note: str | None = None
    approved_by: str | None = None


@router.post("/api/forecast/deliverables/review/approve",
             dependencies=[Depends(require_admin)])
async def approve_bundle_review(payload: _BundleReviewApproveRequest):
    """Override the reviewer gate and approve the bundle for delivery.
    Admin only: this releases content to customers."""
    from app.database import get_database_instance
    from datetime import datetime, timezone

    db = get_database_instance()
    row = db.facade.upsert_forecast_bundle_review(
        cadence=payload.cadence,
        period_label=payload.period_label,
        status="approved",
        approved_by=payload.approved_by or "ui",
        approved_at=datetime.now(timezone.utc),
    )
    return {"ok": True, "review": row}


class _BundleReviewRevisionRequest(__import__("pydantic").BaseModel):  # noqa: N801
    cadence: str
    period_label: str
    target_stages: list[str] | None = None


@router.post("/api/forecast/deliverables/review/request-revision")
async def request_bundle_revision(payload: _BundleReviewRevisionRequest):
    """Mark the bundle for revision. Clears the targeted caches so the next
    bundle generation re-fires the affected agents."""
    from app.database import get_database_instance
    db = get_database_instance()

    # Clear the bundle-level synthesis cache so cross-topic agents re-run
    targets = set(payload.target_stages or [])
    if not targets or "cross_topic" in targets or "exec_summary" in targets:
        try:
            from app.database_models import t_forecast_bundle_synthesis
            from sqlalchemy import delete
            stmt = delete(t_forecast_bundle_synthesis).where(
                (t_forecast_bundle_synthesis.c.cadence == payload.cadence) &
                (t_forecast_bundle_synthesis.c.period_label == payload.period_label)
            )
            db.facade._execute_with_rollback(stmt)
            try:
                db.facade.session.commit()
            except Exception:
                pass
        except Exception as e:
            logger.warning("Failed to clear bundle synth cache: %s", e)

    row = db.facade.upsert_forecast_bundle_review(
        cadence=payload.cadence,
        period_label=payload.period_label,
        status="awaiting_synth",
    )

    # Drop the rendered-PPTX cache so the next bundle download re-renders
    # with whatever the revision pass produces. The cache key is just
    # ``(cadence, period_label, updates_only)`` — without this clear, the
    # GET handler would return the pre-revision deck from /tmp.
    try:
        from app.services.wiley_delivery_service import invalidate_render_cache
        invalidate_render_cache(payload.cadence, payload.period_label)
    except Exception as e:
        logger.warning("render-cache invalidation failed: %s", e)

    return {"ok": True, "cleared_targets": list(targets), "review": row}


@router.get("/api/forecast/{run_id}/assessment/{assessment_id}/articles")
async def get_assessment_articles(
    run_id: str,
    assessment_id: str,
    scenario_idx: Optional[int] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
):
    """Paginated per-article verdicts. If scenario_idx supplied, scopes to one scenario.

    Rejects an ``assessment_id`` from a different run with 409 — the URL is
    run-scoped, so returning another run's article verdicts here would attribute
    evidence to the wrong forecast.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    _require_assessment_in_run(db, run_id, assessment_id)
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


# ======================================================================
# Quarterly Brief Editor endpoints
#
# Back the QuarterlyBriefEditor page (ui/src/pages/QuarterlyBriefEditor.tsx).
# The editor lets the analyst edit/lock/curate the generated bundle
# before sending it to Wiley. Locks survive supervisor re-runs via
# `_apply_locks_after_call` in wiley_bundle_supervisor.py.
# ======================================================================

import os as _os
from pydantic import BaseModel as _BM


def _editor_enabled() -> bool:
    """Feature-flag the editor endpoints. Default ON for non-prod;
    require explicit env opt-in on wiley (prod)."""
    raw = _os.getenv("WILEY_BRIEF_EDITOR", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class _BriefFieldPatch(_BM):
    path: str
    value: object | None = None
    lock: bool | None = None
    edited_by: str | None = None


class _BriefLockPatch(_BM):
    path: str
    locked: bool


class _BriefRegenStage(_BM):
    stage: str  # 'briefing' | 'recommendations' | 'next_steps' | 'cross_topic' | 'exec_summary' | 'events'
    topic: str | None = None  # required for per-topic stages
    actor: str | None = None  # editor username, for audit


class _BriefTopicFieldPatch(_BM):
    topic: str
    assessment_id: str
    path: str
    value: object | None = None
    lock: bool | None = None
    edited_by: str | None = None


class _BriefApprove(_BM):
    approved_by: str | None = None
    note: str | None = None


class _EventCreate(_BM):
    topic: str
    cadence: str | None = None
    period_label: str | None = None
    actor: str
    action: str
    subject: str
    magnitude_value: float | None = None
    magnitude_unit: str | None = None
    event_date: str | None = None  # ISO date
    source_urls: list[str] | None = None
    confidence: float | None = None
    requires_review: bool | None = False
    scenario_relevance: list[str] | None = None
    edited_by: str | None = None


class _EventPatch(_BM):
    actor: str | None = None
    action: str | None = None
    subject: str | None = None
    magnitude_value: float | None = None
    magnitude_unit: str | None = None
    event_date: str | None = None
    confidence: float | None = None
    requires_review: bool | None = None
    include_in_deck: bool | None = None
    scenario_relevance: list[str] | None = None
    edited_by: str | None = None


def _normalize(s: str | None) -> str:
    if not s:
        return ""
    return "-".join((s or "").lower().strip().split())


@router.get("/api/forecast/brief/{cadence}/{period_label}")
async def get_brief(cadence: str, period_label: str):
    """Return the full editable bundle state: synthesis payload, locks,
    edit history, review state, and per-topic summaries."""
    if not _editor_enabled():
        raise HTTPException(403, "Quarterly Brief Editor disabled on this tenant")
    from app.database import get_database_instance
    db = get_database_instance()
    payload = db.facade.get_brief_payload(cadence, period_label)
    if not payload:
        raise HTTPException(404, f"No brief for {cadence}/{period_label}")
    return payload


@router.patch("/api/forecast/brief/{cadence}/{period_label}/field")
async def patch_brief_field_endpoint(
    cadence: str, period_label: str, payload: _BriefFieldPatch,
):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    try:
        result = db.facade.patch_brief_field(
            cadence, period_label,
            path=payload.path, value=payload.value,
            edited_by=payload.edited_by, lock=payload.lock,
        )
    except Exception as e:
        logger.exception("patch_brief_field failed")
        raise HTTPException(500, f"patch failed: {e}")
    return result


@router.patch("/api/forecast/brief/{cadence}/{period_label}/lock")
async def patch_brief_lock(
    cadence: str, period_label: str, payload: _BriefLockPatch,
):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    try:
        result = db.facade.toggle_brief_lock(
            cadence, period_label, path=payload.path, locked=payload.locked,
        )
    except Exception as e:
        raise HTTPException(500, f"lock toggle failed: {e}")
    return result


@router.patch("/api/forecast/brief/{cadence}/{period_label}/topic-field")
async def patch_brief_topic_field(
    cadence: str, period_label: str, payload: _BriefTopicFieldPatch,
):
    """Patch a field inside a topic's assessment summary (e.g. briefing
    lede or tension body)."""
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    try:
        result = db.facade.patch_topic_summary_field(
            topic=payload.topic, assessment_id=payload.assessment_id,
            path=payload.path, value=payload.value,
            edited_by=payload.edited_by, lock=payload.lock,
        )
    except Exception as e:
        logger.exception("patch_brief_topic_field failed")
        raise HTTPException(500, f"patch failed: {e}")
    return result


@router.post("/api/forecast/brief/{cadence}/{period_label}/regenerate-stage")
async def regenerate_brief_stage(
    cadence: str, period_label: str, payload: _BriefRegenStage,
):
    """Re-run one supervisor stage with locks respected. Returns task_id;
    UI polls /api/forecast/assessment/job/{task_id} for progress.
    """
    if not _editor_enabled():
        raise HTTPException(403, "disabled")

    valid_stages = {
        "briefing", "recommendations", "next_steps",
        "cross_topic", "exec_summary", "expert_commentary", "events",
    }
    if payload.stage not in valid_stages:
        raise HTTPException(400, f"unknown stage '{payload.stage}'; pick one of {valid_stages}")

    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_bundle_supervisor import regenerate_single_stage

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"regen_brief_stage:{cadence}:{period_label}:{payload.stage}",
        total_items=100,
        metadata={
            "cadence": cadence, "period_label": period_label,
            "stage": payload.stage, "topic": payload.topic,
        },
    )

    async def _job(progress_callback=None):
        async def _emit(pct, msg):
            if progress_callback:
                try:
                    progress_callback(int(pct * 100), msg)
                except Exception:
                    pass
        await regenerate_single_stage(
            cadence=cadence, period_label=period_label,
            stage=payload.stage, topic=payload.topic,
            actor=payload.actor or "ui",
            progress_cb=_emit,
        )
        return {"ok": True, "stage": payload.stage}

    import asyncio as _asyncio
    _asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "ok": True, "task_id": task_id, "stage": payload.stage,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
    }


@router.get("/api/forecast/brief/{cadence}/{period_label}/preview.pptx")
async def preview_brief_pptx(cadence: str, period_label: str):
    """Render the current brief state (overrides applied, locks respected)
    to PPTX for preview. Reads from cached forecast_bundle_synthesis +
    latest assessments rather than re-running agents — fast iteration."""
    if not _editor_enabled():
        raise HTTPException(403, "disabled")

    from app.database import get_database_instance
    from app.services.forecast_bundle_pptx import build_bundle_pptx
    from app.services.wiley_delivery_service import _data_quality_note
    from app.services.wiley_bundle_supervisor import _load_items_for_period

    db = get_database_instance()
    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    if not synth.get("payload"):
        raise HTTPException(
            404,
            f"No cached brief for {cadence}/{period_label} — generate the bundle first",
        )

    items = await _load_items_for_period(cadence, period_label)
    if not items:
        raise HTTPException(404, "No assessments available for this period")

    # EOS per topic — load from per-topic assessment if present
    eos_per_topic: dict = {}
    for a, _r, _p in items:
        topic = a.get("topic")
        summary = a.get("summary") or {}
        eos = summary.get("extreme_outlier_scenarios") or summary.get("eos") or []
        if topic and eos:
            eos_per_topic[topic] = eos

    review = db.facade.get_forecast_bundle_review(cadence, period_label) or {}
    # Per-trend evidence ledger needs this period's deck-included events.
    events_by_topic: dict = {}
    for e in (db.facade.list_extracted_events(
            cadence=cadence, period_label=period_label, include_excluded=False) or []):
        events_by_topic.setdefault(e.get("topic"), []).append(e)
    blob = build_bundle_pptx(
        items,
        period_label=period_label,
        cadence=cadence,
        updates_only=False,
        bundle_synthesis=synth,
        eos_per_topic=eos_per_topic,
        events_by_topic=events_by_topic,
        data_quality_note=_data_quality_note(),
        review_findings=(review.get("reviewer_findings")
                         if review.get("status") == "revision_requested" else None),
        review_verdict=review.get("status"),
    )
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": (
                f'attachment; filename="brief-{cadence}-{period_label}-preview.pptx"'
            ),
        },
    )


@router.post("/api/forecast/brief/{cadence}/{period_label}/approve")
async def approve_brief(
    cadence: str, period_label: str, payload: _BriefApprove,
):
    """Single-analyst self-approval. Sets approved_by/approved_at on
    forecast_bundle_review so the standard bundle.pptx download returns
    200 instead of 202.
    """
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    from datetime import datetime, timezone
    db = get_database_instance()
    row = db.facade.upsert_forecast_bundle_review(
        cadence=cadence, period_label=period_label,
        status="approved",
        approved_by=payload.approved_by or "ui",
        approved_at=datetime.now(timezone.utc),
    )
    return {"ok": True, "review": row}


# ---- Events CRUD ----

@router.get("/api/forecast/brief/{cadence}/{period_label}/events")
async def list_brief_events(
    cadence: str, period_label: str,
    topic: str | None = Query(None),
    include_excluded: bool = Query(True),
):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    return {
        "events": db.facade.list_extracted_events(
            topic=topic, cadence=cadence, period_label=period_label,
            include_excluded=include_excluded,
        ),
    }


@router.post("/api/forecast/brief/{cadence}/{period_label}/events")
async def create_brief_event(
    cadence: str, period_label: str, payload: _EventCreate,
):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    event = {
        "topic": payload.topic,
        "cadence": payload.cadence or cadence,
        "period_label": payload.period_label or period_label,
        "actor": payload.actor,
        "actor_normalized": _normalize(payload.actor),
        "action": payload.action,
        "subject": payload.subject,
        "subject_normalized": _normalize(payload.subject),
        "magnitude_value": payload.magnitude_value,
        "magnitude_unit": payload.magnitude_unit,
        "event_date": payload.event_date,
        "source_urls": payload.source_urls or [],
        "confidence": payload.confidence,
        "requires_review": bool(payload.requires_review),
        "scenario_relevance": payload.scenario_relevance or [],
        "origin": "manual",
        "edited_by": payload.edited_by,
    }
    new_id = db.facade.upsert_extracted_event(event)
    return {"ok": True, "id": new_id, "event": db.facade.get_extracted_event(new_id)}


@router.patch("/api/forecast/brief/events/{event_id}")
async def patch_brief_event(event_id: int, payload: _EventPatch):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    return {"ok": True, "event": db.facade.patch_extracted_event(event_id, fields)}


@router.delete("/api/forecast/brief/events/{event_id}")
async def delete_brief_event(event_id: int):
    if not _editor_enabled():
        raise HTTPException(403, "disabled")
    from app.database import get_database_instance
    db = get_database_instance()
    return {"ok": db.facade.delete_extracted_event(event_id)}
