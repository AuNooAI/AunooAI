"""Background tasks must actually run, or actually fail — never sit pending.

``run_task`` checked the concurrency limit and, when it was reached, logged
"Too many concurrent tasks, queuing task" and returned. Nothing queued it. The
row stayed ``pending`` with no worker, so a caller polling its ``status_url``
watched a task that would never start, never finish and never fail. With a limit
of three, the fourth simultaneous assessment or report generation was simply
lost.

A worker also only exists inside the process that started it, so a restart left
rows persisted as ``running`` with nobody advancing them — the same symptom from
the other direction.

These tests drive the real manager with persistence stubbed out; nothing here
touches the database.
"""

import asyncio
from unittest.mock import Mock

import pytest


def _manager(monkeypatch, max_concurrent=3):
    from app.services.background_task_manager import BackgroundTaskManager

    tm = BackgroundTaskManager.__new__(BackgroundTaskManager)
    tm._tasks = {}
    tm._running_tasks = {}
    tm._max_concurrent_tasks = max_concurrent
    tm._slots = None
    tm._db = None
    monkeypatch.setattr(tm, "_persist_task", lambda info: None)
    return tm


def test_work_beyond_the_limit_is_queued_and_still_runs(monkeypatch):
    """Acceptance: four simultaneous jobs with a limit of three. The fourth
    must run once a slot frees, not vanish."""
    from app.services.background_task_manager import TaskStatus

    tm = _manager(monkeypatch, max_concurrent=3)
    started = []
    release = None

    async def _job(progress_callback=None, name=None):
        started.append(name)
        await release.wait()
        return {"ok": name}

    async def _drive():
        nonlocal release
        release = asyncio.Event()
        ids = [tm.create_task(name=f"job-{i}") for i in range(4)]
        runners = [
            asyncio.create_task(tm.run_task(tid, _job, name=f"job-{i}"))
            for i, tid in enumerate(ids)
        ]
        # Let the first three claim slots.
        for _ in range(20):
            await asyncio.sleep(0)
        assert len(started) == 3, f"expected 3 running under the limit, got {len(started)}"
        assert tm._tasks[ids[3]].status is TaskStatus.PENDING

        release.set()
        await asyncio.wait_for(asyncio.gather(*runners), timeout=5)
        return ids

    ids = asyncio.run(_drive())

    assert len(started) == 4, "the fourth job never ran"
    for tid in ids:
        assert tm._tasks[tid].status is TaskStatus.COMPLETED, (
            f"task {tid} ended as {tm._tasks[tid].status}"
        )


def test_no_task_is_left_pending_forever(monkeypatch):
    """The precise old failure: over the limit, run_task returned and the row
    stayed pending with nothing to advance it."""
    from app.services.background_task_manager import TaskStatus

    tm = _manager(monkeypatch, max_concurrent=1)

    async def _job(progress_callback=None):
        return "done"

    async def _drive():
        ids = [tm.create_task(name=f"job-{i}") for i in range(3)]
        await asyncio.wait_for(
            asyncio.gather(*[tm.run_task(t, _job) for t in ids]), timeout=5,
        )
        return ids

    ids = asyncio.run(_drive())

    assert all(tm._tasks[t].status is TaskStatus.COMPLETED for t in ids)


def test_a_failing_job_releases_its_slot(monkeypatch):
    """A slot leak would wedge the queue permanently after one bad job."""
    from app.services.background_task_manager import TaskStatus

    tm = _manager(monkeypatch, max_concurrent=1)

    async def _boom(progress_callback=None):
        raise RuntimeError("job blew up")

    async def _ok(progress_callback=None):
        return "fine"

    async def _drive():
        bad = tm.create_task(name="bad")
        good = tm.create_task(name="good")
        await asyncio.wait_for(tm.run_task(bad, _boom), timeout=5)
        await asyncio.wait_for(tm.run_task(good, _ok), timeout=5)
        return bad, good

    bad, good = asyncio.run(_drive())

    assert tm._tasks[bad].status is TaskStatus.FAILED
    assert tm._tasks[good].status is TaskStatus.COMPLETED, (
        "the failed job did not release its slot"
    )


def test_restart_closes_tasks_no_worker_owns(monkeypatch):
    """After a restart, rows persisted as running have nobody advancing them."""
    tm = _manager(monkeypatch)
    facade = Mock()
    facade.close_interrupted_background_tasks.return_value = 2
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(tm, "_get_db", lambda: db)

    assert tm.reconcile_interrupted_tasks() == 2
    facade.close_interrupted_background_tasks.assert_called_once()


def test_reconciliation_does_not_touch_tasks_running_in_this_process(monkeypatch):
    """A genuinely live task must never be mislabelled as interrupted."""
    tm = _manager(monkeypatch)
    tm._running_tasks = {"live-task": Mock()}
    facade = Mock()
    facade.close_interrupted_background_tasks.return_value = 0
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(tm, "_get_db", lambda: db)

    tm.reconcile_interrupted_tasks()

    kwargs = facade.close_interrupted_background_tasks.call_args.kwargs
    assert "live-task" in kwargs["keep_task_ids"]


def test_reconciliation_failure_is_not_fatal(monkeypatch):
    """Startup must not be blocked by a reconciliation problem."""
    tm = _manager(monkeypatch)
    db = Mock()
    db.facade.close_interrupted_background_tasks.side_effect = RuntimeError("db down")
    monkeypatch.setattr(tm, "_get_db", lambda: db)

    assert tm.reconcile_interrupted_tasks() == 0


def test_the_facade_method_does_not_call_a_session_that_does_not_exist():
    """DatabaseQueryFacade has no `self.session` — _execute_with_rollback
    commits by itself. The `self.session.commit()` calls elsewhere in that file
    are dead code that survives only because they sit inside
    `except Exception: pass`. Copying that idiom into a method with real error
    handling turns every call into a failure: the first version of
    delete_forecast_bundle_state re-raised the AttributeError, so regenerate
    would have returned 500 on every request even though the deletes committed.
    """
    import ast
    import inspect
    import textwrap

    from app.database_query_facade import DatabaseQueryFacade

    for name in ("close_interrupted_background_tasks", "delete_forecast_bundle_state"):
        tree = ast.parse(textwrap.dedent(
            inspect.getsource(getattr(DatabaseQueryFacade, name))
        ))
        # Look at real attribute access, not comments or docstrings that
        # explain the trap.
        uses = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id == "self"
            and n.attr == "session"
        ]
        assert not uses, f"{name} uses self.session, which this facade does not have"

    # And the facade really does not have it, so this check is not vacuous.
    assert not hasattr(DatabaseQueryFacade, "session")
