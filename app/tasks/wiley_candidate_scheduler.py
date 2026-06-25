"""Weekly candidate scan + daily snooze sweeper for the Wiley topic
discovery pipeline.

Runs forever as a single asyncio task started from ``app_factory``'s
lifespan. Each tick:

* If 7+ days have passed since the last scan (or this is the first
  tick), run ``wiley_candidate_pipeline.run_weekly_scan``.
* Always run the snooze sweeper to flip elapsed snoozes back to pending.
* Sleep 24h and tick again.

Gating envs:
* ``WILEY_CANDIDATE_SCAN_ENABLED`` — set to ``false`` to disable the
  whole loop (the task exits immediately).
* ``WILEY_CANDIDATE_SCAN_DAYS_BACK`` — detection window, default 14.
* ``WILEY_CANDIDATE_SCAN_INTERVAL_DAYS`` — gap between full scans,
  default 7. The sweeper still runs every 24h regardless.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return os.environ.get("WILEY_CANDIDATE_SCAN_ENABLED", "true").lower() not in (
        "false", "0", "off", "no",
    )


async def run_wiley_candidate_scheduler() -> None:
    """Top-level scheduler entrypoint — starts the daily tick loop."""
    if not _is_enabled():
        logger.info(
            "wiley_candidate_scheduler: disabled via WILEY_CANDIDATE_SCAN_ENABLED, exiting."
        )
        return

    days_back = int(os.environ.get("WILEY_CANDIDATE_SCAN_DAYS_BACK", "14"))
    interval_days = int(os.environ.get("WILEY_CANDIDATE_SCAN_INTERVAL_DAYS", "7"))
    # Stagger the first scan with up to 30 minutes of jitter so multiple
    # tenant services restarting together don't slam the LLM provider.
    initial_jitter_seconds = random.uniform(60, 1800)

    logger.info(
        "wiley_candidate_scheduler: starting (days_back=%d, interval_days=%d, "
        "initial_jitter=%.0fs)",
        days_back, interval_days, initial_jitter_seconds,
    )
    await asyncio.sleep(initial_jitter_seconds)

    last_scan_at: datetime | None = None

    while True:
        try:
            # Sweep snoozes first — cheap and idempotent.
            try:
                from app.services.wiley_candidate_pipeline import (
                    sweep_snoozed_candidates,
                )
                unsnoozed = sweep_snoozed_candidates()
                if unsnoozed:
                    logger.info(
                        "wiley_candidate_scheduler: unsnoozed %d candidate(s)",
                        unsnoozed,
                    )
            except Exception as e:
                logger.error("Snooze sweeper failed: %s", e)

            # Weekly scan — only if interval elapsed.
            now = datetime.utcnow()
            due = (
                last_scan_at is None
                or (now - last_scan_at) >= timedelta(days=interval_days)
            )
            if due:
                logger.info("wiley_candidate_scheduler: running weekly scan")
                try:
                    from app.services.wiley_candidate_pipeline import (
                        run_weekly_scan,
                    )
                    summary = await run_weekly_scan(days_back=days_back)
                    logger.info(
                        "wiley_candidate_scheduler: scan complete — %s",
                        summary,
                    )
                    last_scan_at = now
                except Exception as e:
                    logger.error("Weekly scan failed: %s", e)
                    # On failure, retry tomorrow rather than wait the full
                    # interval. Leaving last_scan_at unchanged ensures the
                    # next tick re-fires the scan.
        except Exception as e:
            # Catch-all: a panic in the loop body must not kill the task.
            logger.exception("wiley_candidate_scheduler unexpected error: %s", e)

        # Tick once a day.
        await asyncio.sleep(24 * 3600)
