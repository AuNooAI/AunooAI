"""Timeline mementos scheduler.

Every 30 minutes checks what is due, per scope (enabled brands + active
non-brand-lane topics):

- daily extraction for YESTERDAY after 01:00 UTC (full ingest day; the
  timeline_runs unique row makes each (scope, day) one-shot), with a 3-day
  catch-up window for downtime
- weekly rollups on Mondays (prior week), monthly on the 1st (prior month)
- state-doc top-up for scopes whose doc is missing or older than 8 days

All service functions are sync (raw connection); each unit of work runs via
asyncio.to_thread so the event loop stays free. Disable with TIMELINE_ENABLED=0.
"""
import asyncio
import logging
import os
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30 * 60
DAILY_AFTER_HOUR_UTC = 1
CATCHUP_DAYS = 3
STATE_DOC_TOPUP_PER_CYCLE = 2

_status = {"running": False, "last_cycle": None, "last_error": None}


def get_timeline_task_status() -> dict:
    return dict(_status)


def _cycle(db) -> dict:
    """One scheduler pass. Sync — called via asyncio.to_thread."""
    from app.services.timeline_events import (
        extract_daily_events, get_timeline_scopes, run_already_completed)
    from app.services.timeline_rollup import (
        generate_monthly_rollup, generate_weekly_rollup, refresh_state_doc,
        state_doc_stale_scopes)

    stats = {"daily": 0, "weekly": 0, "monthly": 0, "state_docs": 0}
    now = datetime.now(timezone.utc)
    today = now.date()

    conn = db._temp_get_connection()
    try:
        scopes = get_timeline_scopes(conn)

        # Daily extraction for yesterday (+ short catch-up window).
        if now.hour >= DAILY_AFTER_HOUR_UTC:
            for scope in scopes:
                for back in range(1, CATCHUP_DAYS + 1):
                    target = today - timedelta(days=back)
                    if run_already_completed(conn, scope["scope_type"], scope["scope_id"],
                                             "daily_extraction", target):
                        continue
                    try:
                        # LLM extraction only for the most recent day; catch-up
                        # days get the cheap SQL/structured sources only.
                        res = extract_daily_events(
                            conn, scope["scope_type"], scope["scope_id"], target,
                            use_llm=(back == 1))
                        if res["events_created"] or res["events_deduplicated"]:
                            stats["daily"] += 1
                    except Exception:  # noqa: BLE001
                        logger.exception("timeline daily extraction failed: %s", scope)

        # Weekly rollups on Mondays (prior full week).
        if today.weekday() == 0:
            week_start = today - timedelta(days=7)
            for scope in scopes:
                try:
                    if generate_weekly_rollup(conn, scope["scope_type"],
                                              scope["scope_id"], week_start):
                        stats["weekly"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("timeline weekly rollup failed: %s", scope)

        # Monthly rollups on the 1st (prior month).
        if today.day == 1:
            month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            for scope in scopes:
                try:
                    if generate_monthly_rollup(conn, scope["scope_type"],
                                               scope["scope_id"], month_start):
                        stats["monthly"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("timeline monthly rollup failed: %s", scope)

        # State-doc top-up (missing or stale), a couple per cycle.
        for scope in state_doc_stale_scopes(conn)[:STATE_DOC_TOPUP_PER_CYCLE]:
            try:
                if refresh_state_doc(conn, scope["scope_type"], scope["scope_id"]):
                    stats["state_docs"] += 1
            except Exception:  # noqa: BLE001
                logger.exception("timeline state doc top-up failed: %s", scope)
    finally:
        conn.close()
    return stats


async def run_timeline_task():
    """Background loop. Started from app_factory lifespan."""
    if os.getenv("TIMELINE_ENABLED", "1").lower() in ("0", "false", "no"):
        logger.info("Timeline mementos task disabled via TIMELINE_ENABLED")
        return
    from app.database import Database
    db = Database()
    _status["running"] = True
    logger.info("Timeline mementos background task started")
    while True:
        try:
            stats = await asyncio.to_thread(_cycle, db)
            _status["last_cycle"] = datetime.now(timezone.utc).isoformat()
            _status["last_error"] = None
            if any(stats.values()):
                logger.info("Timeline cycle: %s", stats)
        except Exception as e:  # noqa: BLE001
            _status["last_error"] = str(e)[:300]
            logger.exception("Timeline cycle failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
