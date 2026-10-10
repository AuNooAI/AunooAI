"""Central graceful-shutdown coordinator for background tasks.

Every long-lived background monitor loop (keyword monitor, emerging topics,
observer, RSS, etc.) and the multi-minute ingest batch loop watch one shutdown
flag. On SIGTERM the lifespan handler sets the flag and cancels the registered
task handles, so the process exits in a few seconds instead of running until
systemd's stop-timeout fires and SIGKILLs it (which caused ~90s of full 502
downtime on every restart).

The monitors run on their own threads and event loops (app.utils.off_loop),
so the flag is a ``threading.Event`` and each loop gets its own
``asyncio.Event`` to wait on. An ``asyncio.Event`` binds to the first loop
that waits on it, and a second loop waiting on the same one raises
``RuntimeError: ... is bound to a different event loop``.

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
import threading
import weakref
from typing import Set

logger = logging.getLogger(__name__)

# The process-wide flag. Safe to read from any thread.
_shutdown_flag = threading.Event()

# One asyncio.Event per event loop, created on first use. The loop is the key
# and the entry goes when the loop is garbage-collected.
_loop_events: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Event]" = (
    weakref.WeakKeyDictionary())
_loop_events_guard = threading.Lock()

# Handles to background tasks so the lifespan handler can cancel them.
_background_tasks: "Set[asyncio.Task]" = set()


def get_shutdown_event() -> asyncio.Event:
    """Return the shutdown event for the running loop.

    Must be called from inside a running event loop. The event is already set
    when shutdown was requested before this loop first asked for it.
    """
    loop = asyncio.get_running_loop()
    with _loop_events_guard:
        event = _loop_events.get(loop)
        if event is None:
            event = asyncio.Event()
            if _shutdown_flag.is_set():
                event.set()
            _loop_events[loop] = event
    return event


def is_shutting_down() -> bool:
    """True once graceful shutdown has been requested."""
    return _shutdown_flag.is_set()


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
    that want to bail promptly on restart. Works on any event loop.
    """
    if _shutdown_flag.is_set():
        return True
    event = get_shutdown_event()
    try:
        await asyncio.wait_for(event.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


def trigger_shutdown() -> None:
    """Signal all cooperative loops to stop at their next checkpoint."""
    if _shutdown_flag.is_set():
        return
    logger.info("Graceful shutdown requested — signalling background tasks")
    _shutdown_flag.set()
    with _loop_events_guard:
        waiting = list(_loop_events.items())
    for loop, event in waiting:
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            pass  # that loop has already closed


async def cancel_registered_tasks(timeout: float = 15.0) -> None:
    """Cancel every registered background task and await them, bounded.

    Sets the shutdown flag first so cooperative loops exit on their own, then
    cancels any still running and waits up to ``timeout`` seconds for them to
    unwind. A task that runs its job on another thread (app.utils.off_loop)
    passes the cancellation on to that job. Anything still alive after that is
    left for the loop teardown / systemd to reap, but by then we've already
    released connections.
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
