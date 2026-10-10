"""Background monitors run on their own event loops (app_factory via
app.utils.off_loop). Everything they share with the web server's loop must
keep one object per loop, and cancelling the web-loop handle must stop the
job on its own loop."""
from __future__ import annotations

import asyncio
import threading

import pytest

from app.utils import shutdown as sd
from app.utils.off_loop import run_off_loop


def _run_on_new_loop(coro_factory):
    """Run a coroutine on a fresh loop in another thread; return its result."""
    out: dict = {}

    def _go():
        try:
            out["result"] = asyncio.run(coro_factory())
        except BaseException as e:  # noqa: BLE001
            out["error"] = e

    t = threading.Thread(target=_go)
    t.start()
    t.join(10)
    if "error" in out:
        raise out["error"]
    return out["result"]


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    sd._shutdown_flag.clear()
    yield
    sd._shutdown_flag.clear()


def test_run_off_loop_returns_result_from_other_thread():
    async def job(x):
        await asyncio.sleep(0)
        return (x, threading.current_thread().name)

    async def main():
        return await run_off_loop(job, 7, name="t-job")

    value, thread_name = asyncio.run(main())
    assert value == 7
    assert thread_name == "t-job"


def test_run_off_loop_propagates_exception():
    async def job():
        raise ValueError("boom")

    async def main():
        with pytest.raises(ValueError, match="boom"):
            await run_off_loop(job)

    asyncio.run(main())


def test_cancelling_the_handle_cancels_the_job_on_its_own_loop():
    job_cancelled = threading.Event()
    job_started = threading.Event()

    async def job():
        job_started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            job_cancelled.set()
            raise

    async def main():
        handle = asyncio.create_task(run_off_loop(job, name="cancel-me"))
        await asyncio.get_running_loop().run_in_executor(None, job_started.wait, 5)
        handle.cancel()
        with pytest.raises(asyncio.CancelledError):
            await handle

    asyncio.run(main())
    assert job_cancelled.wait(5), "the job on the other loop never saw the cancellation"


def test_interruptible_sleep_wakes_on_every_loop():
    """Two loops wait; one trigger_shutdown wakes both. With one shared
    asyncio.Event the second loop raised 'bound to a different event loop'."""
    results: dict = {}
    both_waiting = threading.Barrier(3, timeout=10)

    async def waiter(key):
        async def _arm():
            # take the per-loop event now, so the barrier is passed only once
            # this loop is really waiting on it
            sd.get_shutdown_event()
            both_waiting.wait()
        asyncio.get_running_loop().call_soon(lambda: None)
        await _arm()
        results[key] = await sd.interruptible_sleep(30)

    threads = [threading.Thread(target=lambda k=k: asyncio.run(waiter(k))) for k in ("a", "b")]
    for t in threads:
        t.start()
    both_waiting.wait()
    sd.trigger_shutdown()
    for t in threads:
        t.join(10)
    assert results == {"a": True, "b": True}


def test_shutdown_event_is_already_set_for_a_loop_created_after_trigger():
    sd.trigger_shutdown()

    async def main():
        return sd.get_shutdown_event().is_set(), await sd.interruptible_sleep(30)

    assert _run_on_new_loop(main) == (True, True)


def test_arxiv_spacing_lock_is_per_loop():
    from app.collectors import arxiv_collector as ac

    async def grab():
        return id(ac._lock())

    first = asyncio.run(grab())
    second = _run_on_new_loop(grab)
    assert first != second


def test_task_manager_slots_are_per_loop():
    from app.services.background_task_manager import BackgroundTaskManager

    tm = BackgroundTaskManager.__new__(BackgroundTaskManager)
    tm._max_concurrent_tasks = 3
    import weakref
    tm._slots = weakref.WeakKeyDictionary()

    async def grab():
        return id(tm._get_slots())

    first = asyncio.run(grab())
    second = _run_on_new_loop(grab)
    assert first != second


def test_async_db_opens_one_asyncpg_pool_per_loop(monkeypatch):
    import weakref
    from app.services import async_db as adb

    created: list = []

    class _FakePool:
        def __init__(self, sizes):
            self.sizes = sizes

    async def fake_create_pool(url, **kw):
        created.append((kw["min_size"], kw["max_size"]))
        await asyncio.sleep(0)
        return _FakePool((kw["min_size"], kw["max_size"]))

    import asyncpg
    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    db = adb.AsyncDatabase.__new__(adb.AsyncDatabase)
    db.db_type = "postgresql"
    db.database_url = "postgresql://x"
    db._pool = None
    db._pool_size = 10
    db._pools = weakref.WeakKeyDictionary()
    db._pool_creating = weakref.WeakKeyDictionary()
    db._initialized = False

    async def two_concurrent_first_callers():
        a, b = await asyncio.gather(db._pg_pool(), db._pg_pool())
        return a is b, (await db._pg_pool()) is a

    assert asyncio.run(two_concurrent_first_callers()) == (True, True)
    second = _run_on_new_loop(db._pg_pool)
    assert created == [(10, 20), (1, 10)]
    assert second is not db._pool
