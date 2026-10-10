"""Run a coroutine on its own thread and event loop, and await its result.

For background jobs that mix awaits with synchronous database work. On the
web server's loop every one of those queries freezes the site; on a thread
with its own loop the job runs the same code and the site keeps answering.
Since 10 Oct 2026 every background monitor the app starts runs this way
(app_factory), as do the Market Monitor tick and Brand Watcher runs.

The thread is a daemon, so a restart never waits on a job. Cancelling the
awaiting task cancels the job on its own loop too, and waits a few seconds
for it to unwind so connections go back before the pool closes. Anything the
coroutine shares with the web server's loop must not be bound to that loop:
asyncio locks, semaphores and async HTTP clients created there will not
work here. The shutdown event, the asyncpg pool, the LLM semaphore and the
task manager's slots all keep one object per loop for this reason.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Callable

# How long a cancelled caller waits for the job to unwind on its own loop.
CANCEL_GRACE_SECONDS = 5.0


async def run_off_loop(factory: Callable[..., Awaitable[Any]], *args: Any,
                       name: str = "off-loop-job", **kwargs: Any) -> Any:
    """Await ``factory(*args, **kwargs)`` run on a daemon thread with its own loop."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()
    inner: dict[str, Any] = {}          # the job's loop and task, once started
    cancelled = threading.Event()       # cancel arrived before the job started

    def _settle(result: Any = None, exc: BaseException | None = None) -> None:
        if done.done():
            return
        if exc is not None:
            done.set_exception(exc)
        else:
            done.set_result(result)

    async def _main() -> Any:
        inner["loop"] = asyncio.get_running_loop()
        inner["task"] = asyncio.current_task()
        if cancelled.is_set():
            raise asyncio.CancelledError()
        return await factory(*args, **kwargs)

    def _run() -> None:
        try:
            result, exc = asyncio.run(_main()), None
        except BaseException as e:  # noqa: BLE001 - handed back to the caller
            result, exc = None, e
        try:
            loop.call_soon_threadsafe(_settle, result, exc)
        except RuntimeError:
            pass  # the web server's loop closed while the job ran

    def _cancel_job() -> None:
        cancelled.set()
        job_loop, task = inner.get("loop"), inner.get("task")
        if job_loop is not None and task is not None:
            try:
                job_loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # the job's loop already finished

    threading.Thread(target=_run, name=name, daemon=True).start()
    try:
        return await asyncio.shield(done)
    except asyncio.CancelledError:
        _cancel_job()
        try:
            await asyncio.wait_for(asyncio.shield(done), timeout=CANCEL_GRACE_SECONDS)
        except BaseException:  # noqa: BLE001 - the job's outcome no longer matters
            pass
        raise
