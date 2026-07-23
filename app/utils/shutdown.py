"""Central graceful-shutdown coordinator for background tasks.

Every long-lived background monitor loop (keyword monitor, emerging topics,
observer, RSS, etc.) and the multi-minute ingest batch loop share a single
``asyncio.Event``. On SIGTERM the lifespan handler sets the event and cancels
the registered task handles, so the process exits in a few seconds instead of
running until systemd's stop-timeout fires and SIGKILLs it (which caused ~90s
of full 502 downtime on every restart).

Usage:
    from app.utils.shutdown import (
        is_shutting_down, register_task, interruptible_sleep,
        trigger_shutdown, cancel_registered_tasks,
    )

    # In a monitor loop instead of `await asyncio.sleep(n)`:
    if await interruptible_sleep(n):
        break  # woke because shutdown was requested

    # In a long work loop, between units of work:
    if is_shutting_down():
        break
"""

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Loop-agnostic in Python 3.10+ — safe to construct at import time and use
# from within the running loop later.
_shutdown_event = asyncio.Event()

# Handles to background tasks so the lifespan handler can cancel them.
_background_tasks: "Set[asyncio.Task]" = set()


def get_shutdown_event() -> asyncio.Event:
    """Return the shared shutdown event."""
    return _shutdown_event


def is_shutting_down() -> bool:
    """True once graceful shutdown has been requested."""
    return _shutdown_event.is_set()


def register_task(task: "asyncio.Task") -> "asyncio.Task":
    """Track a background task so it can be cancelled on shutdown.

    Returns the task unchanged so callers can wrap inline:
        register_task(asyncio.create_task(run_monitor()))
    """
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def interruptible_sleep(seconds: float) -> bool:
    """Sleep up to ``seconds``, waking early if shutdown is requested.

    Returns True if it woke because shutdown was requested, False on a normal
    timeout. Drop-in replacement for ``await asyncio.sleep(seconds)`` in loops
    that want to bail promptly on restart.
    """
    if _shutdown_event.is_set():
        return True
    try:
        await asyncio.wait_for(_shutdown_event.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


def trigger_shutdown() -> None:
    """Signal all cooperative loops to stop at their next checkpoint."""
    if not _shutdown_event.is_set():
        logger.info("Graceful shutdown requested — signalling background tasks")
        _shutdown_event.set()


async def cancel_registered_tasks(timeout: float = 15.0) -> None:
    """Cancel every registered background task and await them, bounded.

    Sets the shutdown event first so cooperative loops exit on their own, then
    cancels any still running and waits up to ``timeout`` seconds for them to
    unwind. Anything still alive after that is left for the loop teardown /
    systemd to reap, but by then we've already released connections.
    """
    trigger_shutdown()

    tasks = [t for t in _background_tasks if not t.done()]
    if not tasks:
        return

    logger.info(f"Cancelling {len(tasks)} background task(s) for shutdown")
    for t in tasks:
        t.cancel()

    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )
        logger.info("Background tasks stopped cleanly")
    except asyncio.TimeoutError:
        still_running = [t for t in tasks if not t.done()]
        logger.warning(
            f"{len(still_running)} background task(s) did not stop within "
            f"{timeout}s — proceeding with shutdown anyway"
        )
