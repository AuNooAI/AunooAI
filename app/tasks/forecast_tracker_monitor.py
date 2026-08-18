"""Scheduled re-runs of forecast assessments.

For every stored horizons run that has a matching deck overlay, this monitor
kicks off a paired assessment if the last one is older than the staleness
threshold. The intent is to keep a rolling monthly snapshot per topic so
the UI can plot per-scenario ``net_rate`` trajectories over time.

Disabled by default — set ``FORECAST_TRACKER_AUTO_RUN=true`` in the tenant
env to enable. Each paired run takes ~15 minutes and ~$3-8, so 4 topics
monthly is ~$10-30/month. Don't enable on tenants that don't use the brief.

State lives in the existing ``forecast_assessments`` table; we don't need a
separate scheduling table — last assessment timestamp per topic is the
authoritative "when did we last check this?" signal.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Tunables (override via env if needed). Defaults are monthly cadence —
# staleness=30d means a topic gets re-assessed once a month. The check loop
# only inspects "should we run?" — actual work only happens at the staleness
# boundary, so a 6h check interval is plenty.
CHECK_INTERVAL_SECONDS = int(os.getenv("FORECAST_TRACKER_CHECK_INTERVAL_SEC", "21600"))  # 6 h
STALENESS_DAYS = int(os.getenv("FORECAST_TRACKER_STALENESS_DAYS", "30"))
WINDOW_WEEKS = int(os.getenv("FORECAST_TRACKER_WINDOW_WEEKS", "8"))
MAX_ARTICLES = int(os.getenv("FORECAST_TRACKER_MAX_ARTICLES", "2000"))

_status = {
    "enabled": False,
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "last_kicked_off": [],  # list of (topic, run_id, kicked_at)
    "last_delivery_check": None,
    "last_delivery_results": [],  # list of {cadence, period_label, topics, ok, at}
}

# run_id -> task_id of the scheduled assessment currently running for it.
# Repeated monitor ticks must not stack jobs on the same run: the paired job
# takes ~15 minutes, and a hung or slow one would otherwise be relaunched on
# every tick. Cleared in the job's finally block, so a failure cannot wedge a
# run out of scheduling permanently.
_ACTIVE_RUN_JOBS: dict = {}
# run_id -> the asyncio task handle, so a job that was cancelled or died before
# its body ran (and therefore never reached the finally that clears the marker)
# can still be detected as finished.
_ACTIVE_TASK_HANDLES: dict = {}


def _is_job_active(task_manager, run_id: str) -> bool:
    """True while this run's scheduled assessment is still going.

    The in-memory marker is authoritative for this process. It is cross-checked
    against the task manager so a task that died without unwinding (process
    restart, cancelled task) does not block the run forever.
    """
    task_id = _ACTIVE_RUN_JOBS.get(run_id)
    if not task_id:
        return False
    try:
        status = (task_manager.get_task_status(task_id) or {}).get("status")
    except Exception:
        status = None
    if status in ("completed", "failed", "cancelled", "error", None):
        _ACTIVE_RUN_JOBS.pop(run_id, None)
        return False
    if status == "pending":
        # A queued task is legitimately pending while it waits for a slot, but
        # a task cancelled before its body ran also stays pending forever and
        # never clears the marker — which would wedge this run out of
        # scheduling for the life of the process. Trust the asyncio task, not
        # the persisted status.
        handle = _ACTIVE_TASK_HANDLES.get(run_id)
        if handle is None or handle.done():
            _ACTIVE_RUN_JOBS.pop(run_id, None)
            _ACTIVE_TASK_HANDLES.pop(run_id, None)
            return False
    return True


# Override day-of-month + month checks for testing (e.g.
# FORECAST_DELIVERY_FORCE_DAY=22 to make today behave as the 1st of the month).
_FORCE_DAY = int(os.getenv("FORECAST_DELIVERY_FORCE_DAY", "0") or 0)
_FORCE_QUARTER_MONTH = os.getenv("FORECAST_DELIVERY_FORCE_QUARTER", "").lower() in ("1", "true", "yes")


def get_task_status() -> dict:
    return dict(_status)


async def run_forecast_tracker_monitor():
    """Main loop. Gated by env flag — exits immediately if unset."""
    if os.getenv("FORECAST_TRACKER_AUTO_RUN", "").lower() not in ("1", "true", "yes"):
        logger.info("Forecast tracker auto-run disabled (FORECAST_TRACKER_AUTO_RUN unset)")
        return

    _status["enabled"] = True
    _status["running"] = True
    logger.info(
        "Forecast tracker monitor started (interval=%ds, staleness=%dd, window=%dw)",
        CHECK_INTERVAL_SECONDS, STALENESS_DAYS, WINDOW_WEEKS,
    )

    while True:
        try:
            _status["last_check_time"] = datetime.now(timezone.utc).isoformat()
            await _check_and_kick_off()
            await _check_delivery_cadences()
        except Exception as e:
            logger.error("Forecast tracker monitor loop error: %s", e, exc_info=True)
            _status["last_error"] = str(e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _check_delivery_cadences():
    """Fire monthly / quarterly bundle deliveries on calendar boundaries.

    Runs once per check-loop iteration. Idempotent: ``last_delivered_at`` on
    each topic guards against double-sends within the same period.

    Boundaries:
    * monthly  → day-of-month == 1
    * quarterly → day-of-month == 1 AND month in (1, 4, 7, 10)
    """
    from app.database import get_database_instance
    from app.services.wiley_delivery_service import deliver_bundle

    now = datetime.now(timezone.utc)
    _status["last_delivery_check"] = now.isoformat()

    day = _FORCE_DAY or now.day
    if day != 1:
        return  # only fire on the 1st of the month

    is_quarter_start = (now.month in (1, 4, 7, 10)) or _FORCE_QUARTER_MONTH

    db = get_database_instance()
    configs = db.facade.get_forecast_topic_delivery_configs()

    # Decide whether each cadence needs to fire — guarded by checking whether
    # any topic in that cadence hasn't been delivered yet for this period.
    monthly_due = _period_due(configs, "monthly", now)
    quarterly_due = is_quarter_start and _period_due(configs, "quarterly", now)

    for cadence, due in (("monthly", monthly_due), ("quarterly", quarterly_due)):
        if not due:
            continue
        try:
            result = await deliver_bundle(cadence, updates_only=True, when=now)
            _status["last_delivery_results"] = (
                [{
                    "cadence": cadence,
                    "period_label": result.get("period_label"),
                    "topics": result.get("topics"),
                    "ok": result.get("ok"),
                    "at": now.isoformat(),
                }]
                + _status["last_delivery_results"][:9]
            )
            logger.info("Scheduled %s delivery: ok=%s topics=%s",
                        cadence, result.get("ok"), result.get("topics"))
        except Exception as e:
            logger.error("Scheduled %s delivery failed: %s", cadence, e, exc_info=True)


def _period_due(configs: list, cadence: str, now: datetime) -> bool:
    """True if ANY topic with the given cadence hasn't been delivered yet
    in the current month (monthly) or quarter (quarterly)."""
    selected = [c for c in configs if (c.get("cadence") or "").lower() == cadence]
    if not selected:
        return False
    for c in selected:
        last = c.get("last_delivered_at")
        if not last:
            return True
        last_dt = _ensure_aware(last)
        if last_dt is None:
            return True
        if cadence == "monthly":
            if (last_dt.year, last_dt.month) < (now.year, now.month):
                return True
        else:  # quarterly
            last_q = (last_dt.month - 1) // 3
            now_q = (now.month - 1) // 3
            if (last_dt.year, last_q) < (now.year, now_q):
                return True
    return False


async def _check_and_kick_off():
    """Start paired assessments for forecast runs that need one.

    Freshness is a property of a RUN, not of a topic. This used to compare the
    newest assessment for the *topic* against the threshold, so generating a new
    forecast for a topic assessed last week left that new run unassessed until
    the topic's 30-day clock expired — the tracker showed a fresh forecast with
    no evidence against it, and the report pipeline pinned a run nothing had
    scored. Each run now carries its own clock, and a run that has never been
    assessed is due immediately.
    """
    from app.database import get_database_instance
    from app.services.background_task_manager import get_task_manager

    db = get_database_instance()

    # Enumerate (topic → most-recent run_id) for topics that have a deck overlay.
    topics_with_overlays = _load_overlay_topics()
    if not topics_with_overlays:
        logger.debug("No deck overlays found; nothing to schedule")
        return

    conn = db._temp_get_connection()
    try:
        # For each topic, pick the most-recent horizons run.
        most_recent_runs = conn.execute(
            text(
                "SELECT DISTINCT ON (topic) topic, id, created_at "
                "FROM future_horizons_runs "
                "WHERE topic = ANY(:topics) "
                "ORDER BY topic, created_at DESC"
            ),
            {"topics": list(topics_with_overlays)},
        ).fetchall()

        # Freshness per RUN, not per topic, and only COMPLETED live assessments
        # count. A failed or partial row must not look like evidence that the
        # run has been scored, or a run that keeps failing would never retry.
        run_ids = [r._mapping["id"] for r in most_recent_runs]
        last_assessments = conn.execute(
            text(
                "SELECT run_id, MAX(assessed_at) AS last "
                "FROM forecast_assessments "
                "WHERE run_id = ANY(:run_ids) AND mode='live' AND status='completed' "
                "GROUP BY run_id"
            ),
            {"run_ids": run_ids},
        ).fetchall() if run_ids else []
        last_by_run = {r._mapping["run_id"]: r._mapping["last"] for r in last_assessments}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    staleness_threshold = datetime.now(timezone.utc) - timedelta(days=STALENESS_DAYS)
    tm = get_task_manager()

    for r in most_recent_runs:
        topic = r._mapping["topic"]
        run_id = r._mapping["id"]
        last = last_by_run.get(run_id)
        if last:
            aware = _ensure_aware(last)
            # An unparseable timestamp must not decide scheduling either way;
            # treat it as unknown and let the run be assessed.
            if aware is not None and aware > staleness_threshold:
                continue

        # Repeated ticks must not stack jobs on the same run. The paired job
        # takes ~15 minutes and the loop wakes every 6 hours, but a hung or
        # slow run would otherwise be launched again on every tick, unbounded.
        if _is_job_active(tm, run_id):
            logger.info(
                "Scheduled assessment already active for run %s (topic %r) — skipping",
                run_id, topic,
            )
            continue

        logger.info(
            "Kicking off scheduled paired assessment for topic '%s' (run_id=%s, last=%s)",
            topic, run_id, last or "never",
        )

        # Use the same job pattern the route uses, but call directly so we can
        # await the structure without going through HTTP.
        task_id = tm.create_task(
            name=f"forecast_paired_scheduled:{run_id}",
            total_items=100,
            metadata={"run_id": run_id, "topic": topic, "scheduled": True,
                      "window_weeks": WINDOW_WEEKS},
        )

        _ACTIVE_RUN_JOBS[run_id] = task_id
        _ACTIVE_TASK_HANDLES[run_id] = asyncio.create_task(
            tm.run_task(task_id, _build_paired_job(run_id, topic))
        )
        _status["last_kicked_off"] = (
            [{"topic": topic, "run_id": run_id, "at": datetime.now(timezone.utc).isoformat()}]
            + _status["last_kicked_off"][:9]
        )


def _build_paired_job(run_id: str, topic: str):
    """Closure binding the run_id so the same monitor loop can fan out
    multiple jobs at once without race conditions.

    Clears this run's in-progress marker on the way out, however the job ends,
    so a failure cannot wedge the run out of scheduling forever.
    """
    from app.services.forecast_assessment_service import assess_run, apply_baseline_correction

    async def _job(progress_callback=None):
        try:
            return await _run_paired(progress_callback)
        finally:
            _ACTIVE_RUN_JOBS.pop(run_id, None)
            _ACTIVE_TASK_HANDLES.pop(run_id, None)

    async def _run_paired(progress_callback=None):
        def _cb_for(start, end):
            def _emit(pct, msg):
                if progress_callback:
                    progress_callback(start + int((end - start) * pct / 100), msg)
            return _emit

        live = await assess_run(
            run_id=run_id, mode="live", max_articles=MAX_ARTICLES,
            margin=0.04, granularity="auto",
            window_weeks=WINDOW_WEEKS,
            progress_callback=_cb_for(0, 48),
        )
        placebo = await assess_run(
            run_id=run_id, mode="placebo", max_articles=MAX_ARTICLES,
            margin=0.04, granularity="auto",
            window_weeks=WINDOW_WEEKS,
            progress_callback=_cb_for(48, 96),
        )
        correction = apply_baseline_correction(
            live_assessment_id=(live or {}).get("id"),
            placebo_assessment_id=(placebo or {}).get("id"),
        )
        if progress_callback:
            progress_callback(100, "Scheduled paired assessment complete")
        return {
            "scheduled": True,
            "topic": topic,
            "live_assessment_id": (live or {}).get("id"),
            "placebo_assessment_id": (placebo or {}).get("id"),
            "correction": correction,
        }
    return _job


def _load_overlay_topics() -> set[str]:
    """Read each overlay JSON's ``topic`` field. Cheap — done every check loop
    so newly-added overlays are picked up without a restart."""
    overlay_dir = Path("data/wiley_horizons")
    topics: set[str] = set()
    if not overlay_dir.exists():
        return topics
    for path in overlay_dir.glob("*_deck_overlay.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            topic = data.get("topic")
            if topic:
                topics.add(topic)
        except Exception as e:
            logger.warning("Failed to read overlay %s: %s", path.name, e)
    return topics


def _ensure_aware(dt):
    """Postgres timestamps come back as either aware or naive depending on
    column type; normalise to UTC-aware for comparison."""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
