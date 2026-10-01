"""Run records and interval checkpoints for collectors (monolith).

Two tables, both written here and nowhere else:

- ``collection_runs``: one row per collection run, from the
  ``CollectionResult`` the adapter returned. This is what the health probe
  and the alerts read. A process heartbeat says the loop is alive; a run
  record says what it collected and what it could not.
- ``collection_checkpoints``: per provider and scope, the fixed interval
  being worked, how far coverage is proven, and a continuation when the
  last run stopped early. A lease and a version number stop two workers
  from overwriting each other's state.

Every write is best-effort: a collector must never fail because its
bookkeeping did. Errors are logged and swallowed.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 1 and 14.
"""
from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.collectors.contracts import CollectionResult

logger = logging.getLogger(__name__)

#: How long a worker may hold a scope before another may take it over.
DEFAULT_LEASE = timedelta(minutes=30)


def _owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def record_run(db, result: CollectionResult, *, scope_kind: Optional[str] = None,
               scope_id: Optional[str] = None, checkpoint_before: Optional[datetime] = None,
               checkpoint_after: Optional[datetime] = None) -> Optional[int]:
    """Write one run record. Returns the new row id, or None when the write
    failed (logged, never raised)."""
    rec = result.to_record()
    if result.finished_at is None:
        result.mark_finished()
        rec = result.to_record()
    conn = None
    try:
        conn = db._temp_get_connection()
        row = conn.execute(text("""
            INSERT INTO collection_runs
                (provider, scope_kind, scope_id, status, interval_start, interval_end, coverage_complete,
                 checkpoint_before, checkpoint_after, continuation, counts, item_count, duration_ms,
                 error_code, error_message, truncated_reason, parse_partial, diagnostics, started_at, finished_at)
            VALUES
                (:provider, :scope_kind, :scope_id, :status, :interval_start, :interval_end, :coverage_complete,
                 :checkpoint_before, :checkpoint_after, CAST(:continuation AS jsonb), CAST(:counts AS jsonb),
                 :item_count, :duration_ms, :error_code, :error_message, :truncated_reason, :parse_partial,
                 CAST(:diagnostics AS jsonb), :started_at, COALESCE(:finished_at, NOW()))
            RETURNING id
        """), {
            "provider": (result.provider or "unknown")[:40],
            "scope_kind": (scope_kind or "")[:32] or None,
            "scope_id": scope_id if scope_id is not None else result.scope,
            "status": result.status,
            "interval_start": result.interval_start,
            "interval_end": result.interval_end,
            "coverage_complete": bool(result.coverage_complete),
            "checkpoint_before": checkpoint_before,
            "checkpoint_after": checkpoint_after,
            "continuation": _json(result.continuation),
            "counts": _json(rec["counts"]),
            "item_count": rec["item_count"],
            "duration_ms": rec["duration_ms"],
            "error_code": (result.error_code or "")[:32] or None,
            "error_message": rec["error_message"],
            "truncated_reason": (result.truncated_reason or "")[:32] or None,
            "parse_partial": bool(result.parse_partial),
            "diagnostics": _json(rec["diagnostics"]),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        }).fetchone()
        conn.commit()
        return int(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("collection run record not written (%s/%s): %s", result.provider, scope_id, exc)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


@dataclass
class Checkpoint:
    provider: str
    scope_key: str
    interval_start: Optional[datetime]
    interval_end: Optional[datetime]
    coverage_through: Optional[datetime]
    continuation: Optional[Dict[str, Any]]
    version: int
    consecutive_failures: int = 0
    last_error_code: Optional[str] = None
    last_success_at: Optional[datetime] = None
    coverage_unknown_before: Optional[datetime] = None

    @property
    def has_unfinished_interval(self) -> bool:
        return self.interval_end is not None and (
            self.coverage_through is None or self.coverage_through < self.interval_end)


def claim_interval(db, provider: str, scope_key: str, *, lookback: timedelta,
                   now: Optional[datetime] = None, lease: timedelta = DEFAULT_LEASE,
                   owner: Optional[str] = None) -> Optional[Checkpoint]:
    """Lease the scope and return the interval to work.

    If the previous run left an interval unfinished, that same interval is
    returned with its continuation; otherwise a new interval from the proven
    coverage (or ``now - lookback`` on first contact) to ``now``, fixed at
    this moment. Returns None when another worker holds the lease.
    """
    now = now or datetime.now(timezone.utc)
    owner = owner or _owner()
    conn = None
    try:
        conn = db._temp_get_connection()
        row = conn.execute(text("""
            SELECT interval_start, interval_end, coverage_through, coverage_unknown_before, continuation,
                   version, lease_owner, lease_until, consecutive_failures, last_error_code, last_success_at
              FROM collection_checkpoints WHERE provider = :p AND scope_key = :s FOR UPDATE
        """), {"p": provider, "s": scope_key}).fetchone()
        if row is not None and row[6] and row[7] and row[7] > now and row[6] != owner:
            conn.rollback()
            return None
        if row is None:
            start = now - lookback
            cp = Checkpoint(provider, scope_key, start, now, None, None, 0,
                            coverage_unknown_before=start)
            conn.execute(text("""
                INSERT INTO collection_checkpoints
                    (provider, scope_key, interval_start, interval_end, coverage_unknown_before,
                     version, lease_owner, lease_until, last_attempt_at, updated_at)
                VALUES (:p, :s, :a, :b, :u, 0, :o, :l, :n, :n)
                ON CONFLICT (provider, scope_key) DO UPDATE SET
                    lease_owner = EXCLUDED.lease_owner, lease_until = EXCLUDED.lease_until,
                    last_attempt_at = EXCLUDED.last_attempt_at, updated_at = EXCLUDED.updated_at
            """), {"p": provider, "s": scope_key, "a": start, "b": now, "u": start,
                   "o": owner, "l": now + lease, "n": now})
            conn.commit()
            return cp
        (istart, iend, through, unknown_before, cont, version, _lo, _lu, fails, last_code, last_ok) = row
        if isinstance(cont, str):
            try:
                cont = json.loads(cont)
            except ValueError:
                cont = None
        cp = Checkpoint(provider, scope_key, istart, iend, through, cont, int(version or 0),
                        int(fails or 0), last_code, last_ok, unknown_before)
        if not cp.has_unfinished_interval:
            # Start the next fixed interval from proven coverage.
            cp.interval_start = through or (now - lookback)
            # Cap the replay at the lookback so a scope idle for months does
            # not ask the provider for its whole history in one go.
            if cp.interval_start < now - lookback:
                cp.coverage_unknown_before = now - lookback
                cp.interval_start = now - lookback
            cp.interval_end = now
            cp.continuation = None
        conn.execute(text("""
            UPDATE collection_checkpoints
               SET interval_start = :a, interval_end = :b, continuation = CAST(:c AS jsonb),
                   coverage_unknown_before = COALESCE(:u, coverage_unknown_before),
                   lease_owner = :o, lease_until = :l, last_attempt_at = :n, updated_at = :n
             WHERE provider = :p AND scope_key = :s
        """), {"a": cp.interval_start, "b": cp.interval_end, "c": _json(cp.continuation),
               "u": cp.coverage_unknown_before, "o": owner, "l": now + lease, "n": now,
               "p": provider, "s": scope_key})
        conn.commit()
        return cp
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint claim failed for %s/%s: %s", provider, scope_key, exc)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Without a checkpoint the caller still collects a bounded window; it
        # just cannot prove coverage. Return a transient one.
        return Checkpoint(provider, scope_key, now - lookback, now, None, None, -1)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def commit_interval(db, cp: Checkpoint, result: CollectionResult, *,
                    owner: Optional[str] = None) -> bool:
    """Record the run's effect on the checkpoint, atomically against the
    version read at claim time.

    A complete success moves ``coverage_through`` to the interval end and
    clears the continuation. A partial run keeps the interval and stores the
    continuation. A failure leaves coverage alone and counts the failure.
    Returns False when the version moved under us (another worker committed
    first), in which case nothing is written.
    """
    if cp.version < 0:
        return False
    owner = owner or _owner()
    now = datetime.now(timezone.utc)
    conn = None
    try:
        conn = db._temp_get_connection()
        if result.may_advance_checkpoint:
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET coverage_through = :b, continuation = NULL, version = version + 1,
                       lease_owner = NULL, lease_until = NULL, last_success_at = :n,
                       consecutive_failures = 0, last_error_code = NULL, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {"b": cp.interval_end, "n": now, "p": cp.provider, "s": cp.scope_key, "v": cp.version})
        elif result.status == "partial" or (result.failed and result.retryable):
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET continuation = CAST(:c AS jsonb), version = version + 1,
                       lease_owner = NULL, lease_until = NULL,
                       consecutive_failures = CASE WHEN :failed THEN consecutive_failures + 1 ELSE consecutive_failures END,
                       last_error_code = :e, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {"c": _json(result.continuation), "failed": bool(result.failed),
                   "e": (result.error_code or "")[:32] or None, "n": now,
                   "p": cp.provider, "s": cp.scope_key, "v": cp.version})
        else:
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET version = version + 1, lease_owner = NULL, lease_until = NULL,
                       consecutive_failures = consecutive_failures + 1,
                       last_error_code = :e, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {"e": (result.error_code or "")[:32] or None, "n": now,
                   "p": cp.provider, "s": cp.scope_key, "v": cp.version})
        conn.commit()
        if res.rowcount == 0:
            logger.warning("checkpoint %s/%s moved under us (version %s); nothing written",
                           cp.provider, cp.scope_key, cp.version)
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint commit failed for %s/%s: %s", cp.provider, cp.scope_key, exc)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def release_lease(db, provider: str, scope_key: str) -> None:
    conn = None
    try:
        conn = db._temp_get_connection()
        conn.execute(text("UPDATE collection_checkpoints SET lease_owner = NULL, lease_until = NULL "
                          "WHERE provider = :p AND scope_key = :s"), {"p": provider, "s": scope_key})
        conn.commit()
    except Exception:  # noqa: BLE001
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Health view (work package 14)
# ---------------------------------------------------------------------------


def health_summary(db, *, since_hours: int = 24) -> Dict[str, Any]:
    """What the collector health endpoint reports from the run records:
    per provider, the last successful run, the last run of any status,
    pending continuations, and error counts by code."""
    conn = None
    try:
        conn = db._temp_get_connection()
        providers = conn.execute(text("""
            SELECT provider,
                   MAX(finished_at) FILTER (WHERE status = 'success') AS last_success,
                   MAX(finished_at) AS last_run,
                   COUNT(*) FILTER (WHERE status = 'failed' AND finished_at > NOW() - make_interval(hours => :h)) AS failed,
                   COUNT(*) FILTER (WHERE status = 'partial' AND finished_at > NOW() - make_interval(hours => :h)) AS partial,
                   COUNT(*) FILTER (WHERE error_code = 'quota_exhausted' AND finished_at > NOW() - make_interval(hours => :h)) AS quota,
                   COUNT(*) FILTER (WHERE status = 'success' AND item_count = 0 AND finished_at > NOW() - make_interval(hours => :h)) AS empty_success
              FROM collection_runs
             GROUP BY provider ORDER BY provider
        """), {"h": since_hours}).fetchall()
        errors = conn.execute(text("""
            SELECT provider, error_code, COUNT(*) FROM collection_runs
             WHERE error_code IS NOT NULL AND finished_at > NOW() - make_interval(hours => :h)
             GROUP BY provider, error_code ORDER BY 3 DESC LIMIT 50
        """), {"h": since_hours}).fetchall()
        pending = conn.execute(text("""
            SELECT provider, scope_key, interval_start, interval_end, coverage_through, consecutive_failures,
                   last_error_code, updated_at
              FROM collection_checkpoints
             WHERE continuation IS NOT NULL OR consecutive_failures >= 3
             ORDER BY updated_at LIMIT 100
        """)).fetchall()
        return {
            "providers": [
                {"provider": r[0], "last_success_at": r[1].isoformat() if r[1] else None,
                 "last_run_at": r[2].isoformat() if r[2] else None, "failed": int(r[3]),
                 "partial": int(r[4]), "quota_exhausted": int(r[5]), "empty_success": int(r[6])}
                for r in providers],
            "errors": [{"provider": r[0], "error_code": r[1], "count": int(r[2])} for r in errors],
            "pending_intervals": [
                {"provider": r[0], "scope_key": r[1],
                 "interval_start": r[2].isoformat() if r[2] else None,
                 "interval_end": r[3].isoformat() if r[3] else None,
                 "coverage_through": r[4].isoformat() if r[4] else None,
                 "consecutive_failures": int(r[5] or 0), "last_error_code": r[6],
                 "updated_at": r[7].isoformat() if r[7] else None}
                for r in pending],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "providers": [], "errors": [], "pending_intervals": []}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
