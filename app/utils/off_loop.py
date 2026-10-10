"""Run a coroutine on its own thread and event loop, and await its result.

For background jobs that mix awaits with synchronous database work. On the
web server's loop every one of those queries freezes the site; on a thread
with its own loop the job runs the same code and the site keeps answering.
Brand Watcher classification runs did this once a day for about 16s on
bugfixing (10 Oct 2026); the Market Monitor tick uses the same pattern
(market_monitor._tick_off_loop).

The thread is a daemon, so a restart never waits on a job; work cut off
mid-run is rolled back with its connection. Anything the coroutine shares
with the web server's loop must not be bound to that loop: asyncio locks,
semaphores and async HTTP clients created there will not work here
(ai_models keeps one LLM semaphore per loop for this reason).
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Callable


async def run_off_loop(factory: Callable[..., Awaitable[Any]], *args: Any,
                       name: str = "off-loop-job", **kwargs: Any) -> Any:
    """Await ``factory(*args, **kwargs)`` run on a daemon thread with its own loop."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()

    def _settle(result: Any = None, exc: BaseException | None = None) -> None:
        if done.done():
            return
        if exc is not None:
            done.set_exception(exc)
        else:
            done.set_result(result)

    def _run() -> None:
        try:
            result, exc = asyncio.run(factory(*args, **kwargs)), None
        except BaseException as e:  # noqa: BLE001 - handed back to the caller
            result, exc = None, e
        try:
            loop.call_soon_threadsafe(_settle, result, exc)
        except RuntimeError:
            pass  # the web server's loop closed while the job ran

    threading.Thread(target=_run, name=name, daemon=True).start()
    return await done
