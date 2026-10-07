"""Daily removal of expired AI-analysis cache files (spec 08, WP7).

The analyser caches each result as a JSON file under ``cache/`` for 24 hours
but nothing ever deleted the expired ones. This loop runs the cleanup once
after start-up and then every ANALYSIS_CACHE_CLEANUP_HOURS (default 24). The
file walk runs in a worker thread so it never blocks the event loop.
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _hours() -> float:
    try:
        return max(1.0, float(os.getenv("ANALYSIS_CACHE_CLEANUP_HOURS", "24")))
    except ValueError:
        return 24.0


def cleanup_once(cache_dir: str = "cache", ttl_hours: int = 24) -> int:
    from app.analyzers.cache import AnalysisCache
    return AnalysisCache(cache_dir, ttl_hours).cleanup_expired()


async def run_analysis_cache_cleanup() -> None:
    from app.utils.shutdown import interruptible_sleep, is_shutting_down
    interval = _hours() * 3600
    logger.info("analysis cache cleanup started (every %.0f h)", interval / 3600)
    while not is_shutting_down():
        try:
            removed = await asyncio.to_thread(cleanup_once)
            logger.info("analysis cache cleanup removed %d expired files", removed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("analysis cache cleanup failed: %s", exc, exc_info=True)
        if await interruptible_sleep(interval):
            break
    logger.info("analysis cache cleanup stopped")
