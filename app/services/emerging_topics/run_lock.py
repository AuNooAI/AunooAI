"""Cross-process serialization for emerging-topic detection runs.

Detection writes global rows (``emerging_topics``, ``detection_runs``,
``topic_history``) and adjusts per-topic counters. Two runs in the same scope at
once double-count detections and race each other's updates, so only one may be
in flight per scope at a time.

The lock is a PostgreSQL session-level advisory lock, which is the right tool
here for one reason above all: it is released by the server when the holding
connection dies. A crashed worker or a dropped client cannot leave the pipeline
wedged, which a row in a "locks" table would.

Scope is the tenant database plus the normalized ``topic_filter``. The global
(``NULL``) scope gets its own stable key, so a global run and a "climate" run do
not block each other, while two "climate" runs do.
"""

import hashlib
import logging
import os
from typing import Optional

from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)

# Namespace half of the advisory-lock key. Any other advisory-lock user in this
# database picks a different constant, so the two cannot collide.
_LOCK_NAMESPACE = 0x45544C4B  # "ETLK"

# Reserved key for the maintenance interlock. Every run holds this SHARED for
# its whole life; a drain holds it EXCLUSIVE. Postgres refuses a shared lock
# while an exclusive is held and vice versa, so "stop new runs and wait for the
# active ones" is one atomic operation instead of a check followed by a restart.
# A check-then-act sequence always has a window: a run can start in it.
MAINTENANCE_KEY = 0x0D0A1E5  # "DRAINS"

# Sentinel scope name for the global (topic_filter IS NULL) scope, so that a
# NULL filter and a topic literally named "" hash to the same slot only if they
# are in fact the same scope.
_GLOBAL_SCOPE = "\x00__global__"


class MaintenanceInProgress(RuntimeError):
    """Raised when a drain holds the interlock, so no run may start."""

    code = "maintenance_in_progress"

    def __init__(self):
        super().__init__(
            "Emerging-topics detection is drained for maintenance; no new run "
            "may start until the drain releases."
        )


class DetectionAlreadyRunning(RuntimeError):
    """Raised when another detection run holds the lock for this scope."""

    code = "detection_already_running"

    def __init__(self, topic_filter: Optional[str] = None):
        self.topic_filter = topic_filter
        scope = topic_filter or "all topics"
        super().__init__(
            f"An emerging-topics detection run is already in progress for {scope}."
        )


def normalize_topic_filter(topic_filter: Optional[str]) -> Optional[str]:
    """Normalize a topic filter for identity, lifecycle, and lock scoping.

    Empty and whitespace-only filters mean "no filter" and normalize to None so
    that they cannot become a second, invisible scope.
    """
    if topic_filter is None:
        return None
    trimmed = str(topic_filter).strip()
    return trimmed or None


def scope_key(topic_filter: Optional[str]) -> int:
    """Signed 32-bit lock key for a scope, stable across processes and restarts."""
    normalized = normalize_topic_filter(topic_filter)
    scope = _GLOBAL_SCOPE if normalized is None else normalized.lower()
    database = os.getenv("DB_NAME", "")
    digest = hashlib.sha256(f"{database}\x1f{scope}".encode("utf-8")).digest()
    unsigned = int.from_bytes(digest[:4], "big")
    # pg_try_advisory_lock takes int4; fold into the signed range.
    return unsigned - 0x100000000 if unsigned >= 0x80000000 else unsigned


class DetectionRunLock:
    """Holds the advisory lock for one detection scope.

    Usage::

        lock = DetectionRunLock(topic_filter)
        lock.acquire()            # raises DetectionAlreadyRunning
        try:
            ...
        finally:
            lock.release()

    ``release()`` is idempotent and never raises, so it is safe in a ``finally``.
    """

    def __init__(self, topic_filter: Optional[str] = None):
        self.topic_filter = normalize_topic_filter(topic_filter)
        self.key = scope_key(self.topic_filter)
        self._conn = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> "DetectionRunLock":
        """Take the lock, or raise :class:`DetectionAlreadyRunning`."""
        if self._held:
            return self

        db = get_database_instance()
        conn = db._temp_get_connection()
        try:
            # Maintenance interlock first, held shared for the run's lifetime.
            # A drain takes it exclusively, which both blocks new runs here and
            # waits for the in-flight ones to release — no polling, no race.
            open_for_business = conn.execute(
                text("SELECT pg_try_advisory_lock_shared(:ns, :key)"),
                {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY},
            ).scalar()
            if not open_for_business:
                conn.close()
                raise MaintenanceInProgress()

            acquired = conn.execute(
                text("SELECT pg_try_advisory_lock(:ns, :key)"),
                {"ns": _LOCK_NAMESPACE, "key": self.key},
            ).scalar()
        except MaintenanceInProgress:
            raise
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            raise

        if not acquired:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock_shared(:ns, :key)"),
                    {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY},
                )
                conn.commit()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            raise DetectionAlreadyRunning(self.topic_filter)

        # Commit, or this connection sits "idle in transaction" for the whole
        # run. SQLAlchemy 2.0 opens a transaction on the SELECT above and this
        # deployment sets idle_in_transaction_session_timeout = 1min, so the
        # server terminated the connection about a minute in — releasing the
        # lock with it, silently, on every run longer than that. Advisory locks
        # taken with pg_try_advisory_lock are session-scoped, not
        # transaction-scoped, so committing keeps the lock and stops the clock.
        try:
            conn.commit()
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            raise RuntimeError(
                f"Could not commit after taking the detection lock: {exc}"
            ) from exc

        self._conn = conn
        self._held = True
        logger.info(
            "Acquired emerging-topics detection lock for scope %s (key=%s)",
            self.topic_filter or "<global>",
            self.key,
        )
        return self

    def release(self) -> None:
        """Release the lock and close its connection. Safe to call twice."""
        if not self._held:
            self._close()
            return
        try:
            self._conn.execute(
                text("SELECT pg_advisory_unlock(:ns, :key)"),
                {"ns": _LOCK_NAMESPACE, "key": self.key},
            )
            self._conn.execute(
                text("SELECT pg_advisory_unlock_shared(:ns, :key)"),
                {"ns": _LOCK_NAMESPACE, "key": MAINTENANCE_KEY},
            )
            self._conn.commit()
        except Exception as exc:  # the connection may already be gone
            logger.warning(
                "Could not explicitly release detection lock for %s: %s "
                "(closing the connection releases it server-side)",
                self.topic_filter or "<global>",
                exc,
            )
        finally:
            self._held = False
            self._close()
            logger.info(
                "Released emerging-topics detection lock for scope %s",
                self.topic_filter or "<global>",
            )

    def _close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "DetectionRunLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
