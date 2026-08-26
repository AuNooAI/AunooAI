"""Admin diagnostics — event-loop health + thread stack dumps.

Light-weight and unauthenticated by design so it remains accessible when
the rest of the app is sluggish or middleware is degraded. If the service
ever stops responding under load, hit
``GET /api/admin/event-loop-status?dump=1`` to see what the threads are
doing instead of guessing.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Depends
from app.security.session import verify_session_api

router = APIRouter()


@router.get("/api/admin/event-loop-status", dependencies=[Depends(verify_session_api)])
async def event_loop_status(
    limit: int = Query(60, ge=1, le=240),
    dump: int = Query(0, ge=0, le=1),
):
    """Return recent event-loop scheduling-lag samples. Pass ``dump=1`` to
    include a Python stack trace for every live thread."""
    from app.utils.event_loop_monitor import get_recent_samples, dump_all_thread_stacks
    samples = get_recent_samples(limit)
    out = {
        "recent_samples": samples,
        "summary": {
            "count": len(samples),
            "max_lag_seconds": max((s["lag_seconds"] for s in samples), default=0),
            "current_thread_count": (
                samples[-1]["thread_count"] if samples else None
            ),
        },
    }
    if dump:
        out["thread_dump"] = dump_all_thread_stacks()
    # If the watchdog has captured a stack dump during a recent blocking
    # event, include it — this is the stack trace of what was *actually
    # holding* the loop, captured live by the faulthandler watchdog.
    from app.utils.event_loop_monitor import get_last_blocking_dump
    blocking = get_last_blocking_dump()
    if blocking:
        out["last_blocking_capture"] = blocking
    return out
