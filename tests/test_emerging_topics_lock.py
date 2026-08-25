"""The detection lock, against a real PostgreSQL.

Two detection runs in the same scope double-count detections and race each
other's counter updates, so only one may hold a scope at a time. This is a
PostgreSQL session advisory lock rather than a row in a table, because the
server releases it when the holding connection dies — a crashed worker cannot
wedge the pipeline.

Only advisory locks are taken here; no table is read or written. Skips cleanly
when there is no reachable database.
"""

import pytest

pytest.importorskip("sqlalchemy")

from app.services.emerging_topics.run_lock import (  # noqa: E402
    DetectionAlreadyRunning,
    DetectionRunLock,
)


@pytest.fixture(autouse=True)
def requires_database():
    try:
        from sqlalchemy import text
        from app.database import get_database_instance

        conn = get_database_instance()._temp_get_connection()
        conn.execute(text("SELECT 1"))
        conn.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"No PostgreSQL available: {exc}")


def held_locks():
    from sqlalchemy import text
    from app.database import get_database_instance

    conn = get_database_instance()._temp_get_connection()
    try:
        return {
            row[0] for row in conn.execute(text(
                "SELECT objid FROM pg_locks WHERE locktype = 'advisory'"
            )).fetchall()
        }
    finally:
        conn.close()


def test_a_second_run_in_the_same_scope_is_refused():
    first = DetectionRunLock("lock-test-scope")
    first.acquire()
    try:
        second = DetectionRunLock("lock-test-scope")
        with pytest.raises(DetectionAlreadyRunning) as caught:
            second.acquire()
        assert caught.value.code == "detection_already_running"
        assert caught.value.topic_filter == "lock-test-scope"
        assert second.held is False
    finally:
        first.release()


def test_two_different_scopes_run_concurrently():
    climate = DetectionRunLock("lock-test-climate")
    chips = DetectionRunLock("lock-test-semiconductors")
    climate.acquire()
    try:
        chips.acquire()  # must not raise
        assert chips.held
        chips.release()
    finally:
        climate.release()


def test_the_global_scope_does_not_block_a_named_scope():
    everything = DetectionRunLock(None)
    everything.acquire()
    try:
        named = DetectionRunLock("lock-test-named")
        named.acquire()
        assert named.held
        named.release()
    finally:
        everything.release()


def test_releasing_frees_the_scope_for_the_next_run():
    first = DetectionRunLock("lock-test-reuse")
    first.acquire()
    first.release()
    assert first.held is False

    second = DetectionRunLock("lock-test-reuse")
    second.acquire()  # must not raise
    assert second.held
    second.release()


def test_release_is_idempotent_and_never_raises():
    lock = DetectionRunLock("lock-test-idempotent")
    lock.acquire()
    lock.release()
    lock.release()  # no error on a second call
    assert lock.held is False


def test_a_failed_run_releases_its_lock():
    """The service's finally block runs whatever the run did."""
    import asyncio

    from app.services.emerging_topics.emerging_topics_service import (
        EmergingTopicsService,
        EmergingTopicsConfig,
    )
    import app.services.emerging_topics.emerging_topics_service as svc_module

    service = EmergingTopicsService(config=EmergingTopicsConfig())
    service._create_detection_run = lambda *a, **kw: 1
    service._fail_detection_run = lambda *a, **kw: None

    async def explode(**kwargs):
        raise RuntimeError("encoder unreachable")

    service.theme_proposer.propose_themes = explode

    lock = DetectionRunLock("lock-test-failure")
    original = svc_module.DetectionRunLock
    svc_module.DetectionRunLock = lambda topic_filter=None: lock
    try:
        async def run():
            return [e async for e in service.run_detection_streaming("lock-test-failure")]

        events = asyncio.run(run())
    finally:
        svc_module.DetectionRunLock = original

    assert events[-1]["event"] == "error"
    assert lock.held is False, "a failed run must not keep holding the scope"

    # And the scope is genuinely free again.
    again = DetectionRunLock("lock-test-failure")
    again.acquire()
    again.release()


def test_the_lock_connection_is_not_left_idle_in_transaction():
    """A held lock must not sit inside an open transaction.

    This deployment sets idle_in_transaction_session_timeout = 1min. Because
    SQLAlchemy 2.0 opens a transaction on the acquiring SELECT, an uncommitted
    lock connection was terminated by the server about a minute into every run
    — taking the advisory lock with it. The stream carried on believing it held
    the scope, so a second run could start and no one would see it. Measured on
    2026-08-19: dead at t+60s, every time.

    Asserting on the session state catches it immediately instead of making the
    suite wait out the timeout.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    lock = DetectionRunLock("lock-test-idle-state")
    lock.acquire()
    try:
        backend_pid = lock._conn.execute(text("SELECT pg_backend_pid()")).scalar()
        lock._conn.commit()

        conn = get_database_instance()._temp_get_connection()
        try:
            state = conn.execute(text(
                "SELECT state FROM pg_stat_activity WHERE pid = :pid"
            ), {"pid": backend_pid}).scalar()
        finally:
            conn.close()

        assert state != "idle in transaction", (
            "the lock connection is inside an open transaction; the server will "
            "terminate it at idle_in_transaction_session_timeout and release the "
            "lock without anyone noticing"
        )
    finally:
        lock.release()


def test_the_lock_is_actually_visible_in_pg_locks():
    lock = DetectionRunLock("lock-test-visible")
    before = held_locks()
    lock.acquire()
    try:
        during = held_locks()
        assert during - before, "the advisory lock should be visible server-side"
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Maintenance interlock
# ---------------------------------------------------------------------------

def hold_maintenance_exclusive():
    """Take the interlock the way scripts/detection_drain.py does."""
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services.emerging_topics.run_lock import (
        MAINTENANCE_KEY, _LOCK_NAMESPACE,
    )

    conn = get_database_instance()._temp_get_connection()
    conn.execute(text("SELECT pg_advisory_lock(:ns, :key)"),
                 {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY})
    conn.commit()
    return conn


def release_maintenance(conn):
    from sqlalchemy import text
    from app.services.emerging_topics.run_lock import (
        MAINTENANCE_KEY, _LOCK_NAMESPACE,
    )
    conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"),
                 {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY})
    conn.commit()
    conn.close()


def test_a_drain_blocks_new_runs():
    """The interlock replaces "check for runs, then restart".

    That sequence has a window between the check and the action, and a run can
    start inside it. On 2026-08-19 it killed a customer's detection run. Here
    the check and the block are the same lock, so there is no window.
    """
    from app.services.emerging_topics.run_lock import MaintenanceInProgress

    drain = hold_maintenance_exclusive()
    try:
        with pytest.raises(MaintenanceInProgress) as caught:
            DetectionRunLock("drain-block-probe").acquire()
        assert caught.value.code == "maintenance_in_progress"
    finally:
        release_maintenance(drain)


def test_runs_resume_once_the_drain_releases():
    drain = hold_maintenance_exclusive()
    release_maintenance(drain)

    lock = DetectionRunLock("drain-resume-probe").acquire()
    assert lock.held
    lock.release()


def test_a_drain_cannot_start_while_a_run_holds_the_interlock():
    """The wait half: an exclusive acquire is refused while a run is in flight."""
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services.emerging_topics.run_lock import (
        MAINTENANCE_KEY, _LOCK_NAMESPACE,
    )

    run = DetectionRunLock("drain-wait-probe").acquire()
    conn = get_database_instance()._temp_get_connection()
    try:
        got_it = conn.execute(
            text("SELECT pg_try_advisory_lock(:ns, :key)"),
            {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY},
        ).scalar()
        conn.commit()
        assert got_it is False, (
            "a drain took the interlock while a run was in flight; the restart "
            "would kill that run"
        )
    finally:
        conn.close()
        run.release()

    # And once the run is done the drain gets in.
    conn = get_database_instance()._temp_get_connection()
    try:
        assert conn.execute(
            text("SELECT pg_try_advisory_lock(:ns, :key)"),
            {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY},
        ).scalar() is True
        conn.execute(text("SELECT pg_advisory_unlock(:ns, :key)"),
                     {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY})
        conn.commit()
    finally:
        conn.close()


def test_a_refused_run_does_not_leak_the_shared_interlock():
    """A second run in the same scope must release what it took on the way in."""
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services.emerging_topics.run_lock import (
        MAINTENANCE_KEY, _LOCK_NAMESPACE,
    )

    first = DetectionRunLock("interlock-leak-probe").acquire()
    try:
        with pytest.raises(DetectionAlreadyRunning):
            DetectionRunLock("interlock-leak-probe").acquire()
    finally:
        first.release()

    # With every run finished, nothing should still hold the interlock.
    conn = get_database_instance()._temp_get_connection()
    try:
        holders = conn.execute(text("""
            SELECT COUNT(*) FROM pg_locks
            WHERE locktype = 'advisory' AND classid = :ns AND objid = :key
        """), {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY}).scalar()
        conn.commit()
        assert holders == 0, "a refused run left the maintenance interlock held"
    finally:
        conn.close()
