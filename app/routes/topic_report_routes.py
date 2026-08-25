"""On-demand Topic Report routes.

Endpoints:

* ``POST /api/topic-reports/start`` — kick off PPTX generation for a
  caller-supplied topic list. Returns ``task_id`` + the download URL the
  UI hits when the task completes.
* ``GET /api/topic-reports/{period_label}/download.pptx`` — download the
  rendered PPTX. Hits the cache populated by the start handler.
* ``POST /api/topic-reports/{period_label}/regenerate`` — drop the cached
  PPTX so the next start re-runs the pipeline.

Sister API to ``forecast_assessment_routes`` (the cadence-locked bundle).
Progress polling reuses ``GET /api/forecast/assessment/job/{task_id}``
since the BackgroundTaskManager is shared.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.security.session import verify_session_api
# From the dependency-free error module, NOT topic_report_pptx: that one imports
# python-pptx, which is not installed on every tenant, and importing it here at
# module scope took wiley down with ModuleNotFoundError at startup.
from app.services.topic_report_errors import MissingPinnedRun

logger = logging.getLogger(__name__)
# Report downloads are private: a period_label is a cache key, not a credential.
router = APIRouter(dependencies=[Depends(verify_session_api)])


class _StartTopicReportRequest(BaseModel):
    topics: list[str] = Field(..., min_length=1, description="Topic strings to include")
    period: Optional[str] = Field(None, description="Free-form period label (e.g. 'Q3 2026'). If omitted, uses today's date.")
    rerun_forecast: bool = Field(
        False,
        description="When true, run a fresh Three Horizons analysis per topic before rendering. Adds ~2-3 min per topic.",
    )
    force_model: Optional[str] = Field(
        None,
        description="Model id to use for the forecast rerun (default 'gpt-5.4'). Ignored when rerun_forecast=False.",
    )


@router.post("/api/topic-reports/start")
async def start_topic_report_generation(payload: _StartTopicReportRequest):
    """Kick off topic-report generation in the background. Returns the task_id
    so the UI can poll ``/api/forecast/assessment/job/{task_id}`` for
    per-stage progress, then GET the download URL once complete."""
    from app.services.background_task_manager import get_task_manager
    from app.services.topic_report_service import (
        generate_topic_report, _topics_period_label,
    )
    from datetime import datetime, timezone

    topics = [t for t in (payload.topics or []) if (t or "").strip()]
    if not topics:
        raise HTTPException(status_code=400, detail="topics is required (non-empty list)")

    when = datetime.now(timezone.utc)
    period = payload.period or when.strftime("%Y-%m-%d")
    period_label = _topics_period_label(period, topics)

    tm = get_task_manager()
    task_id = tm.create_task(
        name=f"topic_report:{period_label}",
        total_items=100,
        metadata={
            "kind": "topic_report",
            "topics": topics,
            "period": period,
            "period_label": period_label,
        },
    )

    async def _job(progress_callback=None):
        def _cb(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
        blob, plabel, included, verdict, findings = await generate_topic_report(
            topics, period=period, when=when,
            rerun_forecast=payload.rerun_forecast,
            force_model=payload.force_model,
            progress_callback=_cb,
        )
        return {
            "period_label": plabel,
            "topics": included,
            "verdict": verdict,
            "error_count": sum(1 for f in (findings or []) if f.get("severity") == "error"),
            "warning_count": sum(1 for f in (findings or []) if f.get("severity") == "warning"),
            "blob_bytes": len(blob),
        }

    import asyncio
    asyncio.create_task(tm.run_task(task_id, _job))

    return {
        "task_id": task_id,
        "period_label": period_label,
        "topics": topics,
        "status_url": f"/api/forecast/assessment/job/{task_id}",
        "download_url": f"/api/topic-reports/{period_label}/download.pptx",
    }


@router.get("/api/topic-reports/{period_label}/download.pptx")
async def download_topic_report(period_label: str):
    """Serve the rendered topic-report PPTX from the render cache.

    Returns 404 if the cache slot is empty — the caller should kick off
    ``/start`` first."""
    from app.services.topic_report_service import _read_render_cache

    blob = _read_render_cache(period_label)
    if blob is None:
        raise HTTPException(
            status_code=404,
            detail=f"No rendered topic report for period_label={period_label}. "
                   "POST /api/topic-reports/start first.",
        )
    headers = {
        "Content-Disposition": f'attachment; filename="topic_report_{period_label}.pptx"',
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    }
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )


@router.get("/api/topic-reports/{period_label}/download.md")
async def download_topic_report_markdown(period_label: str):
    """Render the cached topic-report synthesis as Markdown.

    The MD/HTML/DOCX exports never re-run the multi-agent pipeline — they
    are views of the cached synthesis produced by the PPTX path. Returns
    400 if no synthesis exists yet for this period."""
    from app.services.topic_report_service import generate_topic_report_markdown
    try:
        blob, *_ = await generate_topic_report_markdown(period_label)
    except MissingPinnedRun as e:
        # The report is pinned to a run that no longer exists. Regenerating is
        # the fix; rendering a different run under this label is not.
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=blob,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="topic_report_{period_label}.md"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@router.get("/api/topic-reports/{period_label}/download.html")
async def download_topic_report_html(period_label: str):
    """Render the cached topic-report synthesis as standalone HTML."""
    from app.services.topic_report_service import generate_topic_report_html
    try:
        blob, *_ = await generate_topic_report_html(period_label)
    except MissingPinnedRun as e:
        # The report is pinned to a run that no longer exists. Regenerating is
        # the fix; rendering a different run under this label is not.
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=blob,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="topic_report_{period_label}.html"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@router.get("/api/topic-reports/{period_label}/download.docx")
async def download_topic_report_docx(period_label: str):
    """Executive-summary Word document for this period.

    Generates the synthesis on first request if the period has none, which
    can take minutes — the supervisor persists as it goes, so a retry after
    a proxy timeout renders from the stored row.
    """
    from app.services.topic_report_service import generate_topic_report_docx
    try:
        blob, *_ = await generate_topic_report_docx(period_label)
    except MissingPinnedRun as e:
        # The report is pinned to a run that no longer exists. Regenerating is
        # the fix; rendering a different run under this label is not.
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="topic_report_{period_label}.docx"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@router.get("/api/topic-reports/{period_label}/download-full.docx")
async def download_topic_report_docx_full(period_label: str):
    """Every slide's content as a Word document, for when the executive
    summary is not enough. Long by design — about 5,000 words per topic."""
    from app.services.topic_report_service import generate_topic_report_docx_full
    try:
        blob, *_ = await generate_topic_report_docx_full(period_label)
    except MissingPinnedRun as e:
        # The report is pinned to a run that no longer exists. Regenerating is
        # the fix; rendering a different run under this label is not.
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="topic_report_{period_label}_full.docx"',
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
    )


@router.post("/api/topic-reports/{period_label}/regenerate")
async def regenerate_topic_report(period_label: str):
    """Clear this report's derived state so the next start rebuilds it whole.

    Analyst-triggered when content looks stale. This used to drop only the
    cached PPTX; the supervisor synthesis, review verdict and state sidecar all
    survived. Since ``ensure_bundle_synthesis`` returns early when a payload
    exists, the Markdown and executive-DOCX exports then kept serving the
    previous executive letter against a freshly generated deck, and the stale
    sidecar still held the old pinned run ids.
    """
    from app.services.topic_report_service import invalidate_report_state
    try:
        cleared = invalidate_report_state(period_label)
    except Exception as e:
        # Report the failure rather than letting the caller regenerate a deck
        # on top of synthesis we could not clear.
        logger.error("topic report %s: regenerate failed to clear state: %s",
                     period_label, e)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not clear the previous report state for {period_label}; "
                f"nothing was regenerated. {e}"
            ),
        )
    return {"ok": True, "period_label": period_label, "cleared": cleared}


@router.get("/api/topic-reports/recent")
async def list_recent_topic_reports(limit: int = Query(20, ge=1, le=100)):
    """List recently generated topic reports (filename → mtime).

    Reads the render cache directory. Returns ``[{period_label, generated_at,
    size_bytes}]`` sorted newest-first."""
    import os
    from app.services.topic_report_service import _render_cache_dir
    from datetime import datetime, timezone

    d = _render_cache_dir()
    rows: list = []
    try:
        for fn in os.listdir(d):
            if not fn.startswith("topic_report_") or not fn.endswith(".pptx"):
                continue
            full = os.path.join(d, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            period_label = fn[len("topic_report_"):-len(".pptx")]
            rows.append({
                "period_label": period_label,
                "generated_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "size_bytes": st.st_size,
                "download_url": f"/api/topic-reports/{period_label}/download.pptx",
            })
    except FileNotFoundError:
        rows = []
    rows.sort(key=lambda r: r["generated_at"], reverse=True)
    return {"reports": rows[:limit]}
