"""HTTP routes for the Wiley topic-candidate inbox.

Exposes:
    GET    /api/forecast/candidates                  — list candidates
    POST   /api/forecast/candidates/scan             — fire weekly scan now
    POST   /api/forecast/candidates/{id}/snooze      — snooze N days
    POST   /api/forecast/candidates/{id}/reject      — reject with reason
    POST   /api/forecast/candidates/{id}/merge       — merge into existing topic
    POST   /api/forecast/candidates/{id}/promote     — promote to tracked topic
                                                       (kicks off background pipeline)
    GET    /api/forecast/candidates/job/{task_id}    — poll a promotion/scan job

All long-running work goes through ``BackgroundTaskManager`` so the UI can
poll progress.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request models ──────────────────────────────────────────────────


class _SnoozeRequest(BaseModel):
    days: int = Field(7, ge=1, le=180,
                      description="Number of days to snooze (re-surfaces after).")


class _RejectRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500,
                                  description="Free-text reason for the audit trail.")


class _MergeRequest(BaseModel):
    into_topic: str = Field(..., min_length=1,
                            description="Existing topic name to merge this candidate into.")


class _PromoteRequest(BaseModel):
    triaged_by: Optional[str] = Field(None,
                                      description="Username of the analyst clicking promote.")


# ── List + scan ─────────────────────────────────────────────────────


@router.get("/api/forecast/candidates")
async def list_candidates(
    triage_status: str = Query("pending",
                               pattern="^(pending|snoozed|rejected|promoted|merged|all)$"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
):
    """List topic candidates joined with their underlying emerging-topic
    rows. Ordered by ``relevance_score * et_confidence DESC``.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    rows = db.facade.list_topic_candidates(
        triage_status=triage_status, min_score=min_score,
    )
    return {"candidates": rows, "count": len(rows)}


@router.post("/api/forecast/candidates/scan")
async def kick_off_candidate_scan(
    days_back: int = Query(14, ge=1, le=60),
    dry_run: bool = Query(False),
):
    """Trigger a manual run of the weekly candidate scan. Returns a
    ``task_id`` the UI can poll.
    """
    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_candidate_pipeline import run_weekly_scan

    tm = get_task_manager()
    task_id = tm.create_task(
        name="wiley_candidate_scan",
        total_items=100,
        metadata={"days_back": days_back, "dry_run": dry_run},
    )

    async def _job(progress_callback=None):
        if progress_callback:
            progress_callback(5, "Running emerging-topics detection")
        result = await run_weekly_scan(days_back=days_back, dry_run=dry_run)
        if progress_callback:
            progress_callback(100, "Scan complete")
        return result

    asyncio.create_task(tm.run_task(task_id, _job))
    return {
        "task_id": task_id,
        "status_url": f"/api/forecast/candidates/job/{task_id}",
    }


@router.get("/api/forecast/candidates/job/{task_id}")
async def get_candidate_job(task_id: str):
    """Poll a candidate scan or promotion task."""
    from app.services.background_task_manager import get_task_manager
    tm = get_task_manager()
    status = tm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return status


# ── Triage actions ──────────────────────────────────────────────────


@router.post("/api/forecast/candidates/{candidate_id}/snooze")
async def snooze_candidate(candidate_id: int, body: _SnoozeRequest):
    from app.database import get_database_instance
    db = get_database_instance()
    cand = db.facade.get_topic_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    updated = db.facade.triage_topic_candidate(
        candidate_id, action="snooze", snooze_days=body.days,
    )
    return updated


@router.post("/api/forecast/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: int, body: _RejectRequest):
    from app.database import get_database_instance
    db = get_database_instance()
    cand = db.facade.get_topic_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    updated = db.facade.triage_topic_candidate(
        candidate_id, action="reject", reason=body.reason,
    )
    return updated


@router.post("/api/forecast/candidates/{candidate_id}/merge")
async def merge_candidate(candidate_id: int, body: _MergeRequest):
    """Mark a candidate as merged into an existing tracked topic.
    Does NOT trigger an immediate re-assessment of the target topic — the
    next scheduled assessment will pick up the merged articles.
    """
    from app.database import get_database_instance
    db = get_database_instance()
    cand = db.facade.get_topic_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    target = db.facade.get_forecast_topic_metadata(body.into_topic)
    if not target:
        raise HTTPException(
            status_code=400,
            detail=f"Target topic '{body.into_topic}' not found in topic registry."
        )
    updated = db.facade.triage_topic_candidate(
        candidate_id, action="merge", merged_into=body.into_topic,
    )
    return updated


@router.post("/api/forecast/candidates/{candidate_id}/promote")
async def promote_candidate_route(candidate_id: int, body: _PromoteRequest):
    """Kick off the promotion pipeline as a background task. Returns a
    ``task_id`` the UI polls; on completion the response payload contains
    the new topic name + horizons run id, and the Add-Topic wizard opens
    on step 4 (overlay review).
    """
    from app.services.background_task_manager import get_task_manager
    from app.services.wiley_candidate_pipeline import promote_candidate
    from app.database import get_database_instance

    db = get_database_instance()
    cand = db.facade.get_topic_candidate(candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found")
    if cand.get("triage_status") in ("promoted", "merged"):
        raise HTTPException(
            status_code=400,
            detail=f"Candidate already {cand['triage_status']}"
        )

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"candidate_promote:{candidate_id}",
        total_items=100,
        metadata={
            "candidate_id": candidate_id,
            "proposed_topic_name": cand.get("proposed_topic_name"),
        },
    )

    async def _job(progress_callback=None):
        return await promote_candidate(
            candidate_id,
            triaged_by=body.triaged_by,
            progress_callback=progress_callback,
        )

    asyncio.create_task(tm.run_task(task_id, _job))
    return {
        "task_id": task_id,
        "candidate_id": candidate_id,
        "status_url": f"/api/forecast/candidates/job/{task_id}",
    }
