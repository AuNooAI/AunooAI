"""Assessment freshness is a property of a forecast run, not of a topic.

The monitor compared the newest assessment for a *topic* against the staleness
threshold. Generating a new forecast for a topic assessed last week therefore
left that new run unassessed until the topic's 30-day clock expired: the tracker
showed a fresh forecast with no evidence scored against it, and the report
pipeline could pin a run nothing had assessed.

It also had no guard against launching the same job twice. The paired job takes
about fifteen minutes and the loop wakes every six hours, so in practice ticks
rarely overlapped — but a hung or slow run was relaunched on every tick with no
bound.

The monitor is driven here with a stubbed connection and task manager; it never
touches the database. pytest-asyncio is not installed, so the async entrypoint
is driven with asyncio.run() from a plain test function.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

TOPIC = "Quantum Advantage"
RUN_OLD = "run-old-assessed"
RUN_NEW = "run-new-unassessed"


def _row(**kw):
    return Mock(_mapping=kw)


class _Conn:
    """Answers the monitor's two queries and records what it was asked."""

    def __init__(self, runs, assessments_by_run):
        self._runs = runs
        self._assessments = assessments_by_run
        self.queries = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.queries.append((sql, params or {}))
        if "FROM future_horizons_runs" in sql:
            return Mock(fetchall=lambda: self._runs)
        if "FROM forecast_assessments" in sql:
            rows = [_row(run_id=rid, last=ts) for rid, ts in self._assessments.items()]
            return Mock(fetchall=lambda: rows)
        return Mock(fetchall=lambda: [])

    def close(self):
        pass


def _drive(monkeypatch, runs, assessments_by_run, task_status="running"):
    """Run one monitor tick and return the task manager it used."""
    import app.database as appdb
    import app.services.background_task_manager as btm
    import app.tasks.forecast_tracker_monitor as mon

    conn = _Conn(runs, assessments_by_run)
    db = Mock()
    db._temp_get_connection = lambda: conn
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    monkeypatch.setattr(mon, "_load_overlay_topics", lambda: {TOPIC})

    tm = Mock()
    tm.create_task = Mock(side_effect=lambda **kw: f"task-for-{kw['metadata']['run_id']}")
    tm.get_task_status = Mock(return_value={"status": task_status})
    # run_task returns a plain value and create_task is stubbed out, so no real
    # coroutine is created and none is left un-awaited.
    tm.run_task = Mock(return_value=None)
    monkeypatch.setattr(btm, "get_task_manager", lambda: tm)

    monkeypatch.setattr(mon.asyncio, "create_task", lambda coro: Mock())
    monkeypatch.setattr(mon, "_build_paired_job", lambda run_id, topic: (lambda **k: None))

    mon._ACTIVE_RUN_JOBS.clear()
    asyncio.run(mon._check_and_kick_off())
    return tm, conn


def _scheduled_run_ids(tm):
    return [c.kwargs["metadata"]["run_id"] for c in tm.create_task.call_args_list]


def test_a_new_unassessed_run_is_scheduled_even_if_the_topic_was_just_assessed(monkeypatch):
    """The whole failure: run B is newer than the topic's last assessment, so
    under per-topic freshness it waited a month for evidence."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    tm, _ = _drive(
        monkeypatch,
        runs=[_row(topic=TOPIC, id=RUN_NEW, created_at=datetime.now(timezone.utc))],
        assessments_by_run={RUN_OLD: yesterday},   # the OLD run was assessed
    )

    assert _scheduled_run_ids(tm) == [RUN_NEW]


def test_freshness_is_queried_per_run_and_only_for_completed_assessments(monkeypatch):
    """A failed or partial row must not look like the run has been scored, or a
    run that keeps failing would never retry."""
    _, conn = _drive(
        monkeypatch,
        runs=[_row(topic=TOPIC, id=RUN_NEW, created_at=datetime.now(timezone.utc))],
        assessments_by_run={},
    )

    sql = next(s for s, _ in conn.queries if "FROM forecast_assessments" in s)
    assert "run_id = ANY(:run_ids)" in sql, "freshness must be keyed on the run"
    assert "status='completed'" in sql, "only completed assessments count as fresh"
    assert "GROUP BY topic" not in sql


def test_a_recently_assessed_run_is_left_alone(monkeypatch):
    """The staleness threshold still applies to runs that have been assessed."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    tm, _ = _drive(
        monkeypatch,
        runs=[_row(topic=TOPIC, id=RUN_NEW, created_at=datetime.now(timezone.utc))],
        assessments_by_run={RUN_NEW: yesterday},
    )

    assert _scheduled_run_ids(tm) == []


def test_a_stale_run_is_rescheduled(monkeypatch):
    long_ago = datetime.now(timezone.utc) - timedelta(days=90)
    tm, _ = _drive(
        monkeypatch,
        runs=[_row(topic=TOPIC, id=RUN_NEW, created_at=datetime.now(timezone.utc))],
        assessments_by_run={RUN_NEW: long_ago},
    )

    assert _scheduled_run_ids(tm) == [RUN_NEW]


def test_a_second_tick_does_not_launch_the_same_run_again(monkeypatch):
    """Repeated ticks while a job is still running must not stack jobs."""
    import app.tasks.forecast_tracker_monitor as mon

    runs = [_row(topic=TOPIC, id=RUN_NEW, created_at=datetime.now(timezone.utc))]
    tm, _ = _drive(monkeypatch, runs=runs, assessments_by_run={})
    assert _scheduled_run_ids(tm) == [RUN_NEW]
    assert mon._ACTIVE_RUN_JOBS.get(RUN_NEW), "the run must be marked in progress"

    # Second tick, same state, job still running — must not schedule again.
    import app.database as appdb
    import app.services.background_task_manager as btm

    conn = _Conn(runs, {})
    db = Mock()
    db._temp_get_connection = lambda: conn
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    monkeypatch.setattr(btm, "get_task_manager", lambda: tm)

    asyncio.run(mon._check_and_kick_off())

    assert _scheduled_run_ids(tm) == [RUN_NEW], "the second tick scheduled a duplicate"


def test_a_finished_job_releases_the_run(monkeypatch):
    """A task that ended must not block the run from ever being assessed again."""
    import app.tasks.forecast_tracker_monitor as mon

    tm = Mock()
    tm.get_task_status = Mock(return_value={"status": "completed"})
    mon._ACTIVE_RUN_JOBS[RUN_NEW] = "task-1"

    assert mon._is_job_active(tm, RUN_NEW) is False
    assert RUN_NEW not in mon._ACTIVE_RUN_JOBS


def test_a_task_the_manager_has_lost_releases_the_run(monkeypatch):
    """After a process restart the marker can outlive its worker; an unknown
    task must not wedge the run out of scheduling forever."""
    import app.tasks.forecast_tracker_monitor as mon

    tm = Mock()
    tm.get_task_status = Mock(return_value=None)
    mon._ACTIVE_RUN_JOBS[RUN_NEW] = "task-gone"

    assert mon._is_job_active(tm, RUN_NEW) is False
