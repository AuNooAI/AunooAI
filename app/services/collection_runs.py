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


#: What to do with a window a provider cannot page through (a list API that
#: returned a full page and has no way to ask for the rest). ``advance``: the
#: schedule moves past it, proven coverage does not, and a ``collection_gaps``
#: row records the loss. ``hold``: keep asking for the same window (it never
#: finishes; only useful while investigating). Firehose pages, so it never
#: reaches this. Choosing the policy is a product decision
#: (docs/pipelines/08_INGEST_FIX_SPEC.md, WP1 item 7); ``advance`` keeps the
#: behaviour these providers have had since 7 Oct 2026, now on the record.
def _non_exhaustive_policy() -> str:
    value = (os.getenv("COLLECTION_NON_EXHAUSTIVE_POLICY") or "advance").strip().lower()
    return value if value in ("advance", "hold") else "advance"


def _backoff(attempts: int, now: datetime) -> datetime:
    """When a scope that failed or made no progress ``attempts`` times in a
    row may be claimed again: ``COLLECTION_BACKOFF_MINUTES`` (default 15),
    doubling per attempt, at most 12 hours."""
    try:
        base = float(os.getenv("COLLECTION_BACKOFF_MINUTES", "15"))
    except ValueError:
        base = 15.0
    minutes = min(720.0, max(1.0, base) * (2 ** max(0, min(attempts, 12) - 1)))
    return now + timedelta(minutes=minutes)


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
    #: How far the schedule moved past windows that could not be read in
    #: full. Never proof of coverage; see ``collection_gaps``.
    scheduled_through: Optional[datetime] = None
    no_progress_runs: int = 0
    #: Set by ``commit_interval``: True when proven coverage moved to
    #: interval_end. ``scheduled`` is True when only the schedule moved.
    advanced: bool = False
    scheduled: bool = False
    #: Set by ``commit_interval``: the continuation cursor or coverage moved.
    progressed: bool = False

    @property
    def schedule_position(self) -> Optional[datetime]:
        """Where the next interval starts: proven coverage, or the schedule
        when it moved further past a window recorded as a gap."""
        if self.coverage_through and self.scheduled_through:
            return max(self.coverage_through, self.scheduled_through)
        return self.coverage_through or self.scheduled_through

    @property
    def has_unfinished_interval(self) -> bool:
        pos = self.schedule_position
        return self.interval_end is not None and (pos is None or pos < self.interval_end)


def claim_interval(db, provider: str, scope_key: str, *, lookback: timedelta,
                   now: Optional[datetime] = None, lease: timedelta = DEFAULT_LEASE,
                   owner: Optional[str] = None, ignore_backoff: bool = False) -> Optional[Checkpoint]:
    """Lease the scope and return the interval to work.

    If the previous run left an interval unfinished, that same interval is
    returned with its continuation; otherwise a new interval from the
    schedule position (proven coverage, or the schedule when it moved past a
    recorded gap; ``now - lookback`` on first contact) to ``now``, fixed at
    this moment. Returns None when another worker holds the lease, or when
    the scope is backing off after failures or runs that made no progress
    (``next_attempt_at``), unless ``ignore_backoff``.

    When the schedule position is older than the lookback, the interval
    starts at ``now - lookback`` and the skipped stretch is written to
    ``collection_gaps`` (reason ``lookback_cap``); an explicit catch-up run
    can refill it.
    """
    now = now or datetime.now(timezone.utc)
    owner = owner or _owner()
    conn = None
    try:
        conn = db._temp_get_connection()
        row = conn.execute(text("""
            SELECT interval_start, interval_end, coverage_through, coverage_unknown_before, continuation,
                   version, lease_owner, lease_until, consecutive_failures, last_error_code, last_success_at,
                   scheduled_through, no_progress_runs, next_attempt_at
              FROM collection_checkpoints WHERE provider = :p AND scope_key = :s FOR UPDATE
        """), {"p": provider, "s": scope_key}).fetchone()
        if row is not None and row[6] and row[7] and row[7] > now and row[6] != owner:
            conn.rollback()
            return None
        if row is not None and row[13] and row[13] > now and not ignore_backoff:
            conn.rollback()
            logger.info("checkpoint %s/%s backing off until %s", provider, scope_key, row[13])
            return None
        if row is None:
            start = now - lookback
            cp = Checkpoint(provider, scope_key, start, now, None, None, 0,
                            coverage_unknown_before=start)
            conn.execute(text("""
                INSERT INTO collection_checkpoints
                    (provider, scope_key, interval_start, interval_end, coverage_unknown_before,
                     version, lease_owner, lease_until, last_attempt_at, updated_at, progress_at)
                VALUES (:p, :s, :a, :b, :u, 0, :o, :l, :n, :n, :n)
                ON CONFLICT (provider, scope_key) DO UPDATE SET
                    lease_owner = EXCLUDED.lease_owner, lease_until = EXCLUDED.lease_until,
                    last_attempt_at = EXCLUDED.last_attempt_at, updated_at = EXCLUDED.updated_at
            """), {"p": provider, "s": scope_key, "a": start, "b": now, "u": start,
                   "o": owner, "l": now + lease, "n": now})
            conn.commit()
            return cp
        (istart, iend, through, unknown_before, cont, version, _lo, _lu, fails, last_code, last_ok,
         sched, no_prog, _next) = row
        if isinstance(cont, str):
            try:
                cont = json.loads(cont)
            except ValueError:
                cont = None
        cp = Checkpoint(provider, scope_key, istart, iend, through, cont, int(version or 0),
                        int(fails or 0), last_code, last_ok, unknown_before,
                        scheduled_through=sched, no_progress_runs=int(no_prog or 0))
        if not cp.has_unfinished_interval:
            # Start the next fixed interval from the schedule position.
            cp.interval_start = cp.schedule_position or (now - lookback)
            # Cap the replay at the lookback so a scope idle for months does
            # not ask the provider for its whole history in one go. The
            # stretch skipped is a gap on record, not a silent loss.
            if cp.interval_start < now - lookback:
                if cp.schedule_position is not None:
                    _insert_gap(conn, provider, scope_key, cp.interval_start, now - lookback,
                                "lookback_cap", None, now)
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


def _insert_gap(conn, provider: str, scope_key: str, start: Optional[datetime],
                end: Optional[datetime], reason: str, items: Optional[int], now: datetime) -> None:
    conn.execute(text("""
        INSERT INTO collection_gaps (provider, scope_key, interval_start, interval_end, reason, items, recorded_at)
        VALUES (:p, :s, :a, :b, :r, :i, :n)
    """), {"p": provider, "s": scope_key, "a": start, "b": end, "r": (reason or "unknown")[:32],
           "i": items, "n": now})


def commit_interval(db, cp: Checkpoint, result: CollectionResult, *,
                    owner: Optional[str] = None, now: Optional[datetime] = None) -> bool:
    """Record the run's effect on the checkpoint, atomically against the
    version read at claim time. The caller has already saved the items.

    - Complete success: ``coverage_through`` moves to the interval end; the
      continuation, failure count, no-progress count and backoff clear.
    - Non-exhaustive success (a list API's full page with no way to ask for
      more, ``CollectionResult.non_exhaustive``): proven coverage stays.
      Under the ``advance`` policy the schedule moves to the interval end and
      a ``collection_gaps`` row records the window; under ``hold`` the
      interval is kept and counted as no progress.
    - Failure: coverage stays, the failure is counted, the continuation of
      the page that failed is kept, and the scope backs off.
    - Partial (budget stop, persist failure, parse loss): coverage stays and
      the continuation is kept. Not a failure. When the cursor did not move,
      it counts as no progress and backs off.

    Nothing skips an interval because it failed or stalled for long. A
    stuck scope stays visible in ``health_summary`` until it moves.

    Sets ``cp.advanced``, ``cp.scheduled`` and ``cp.progressed``. Returns
    False when the version moved under us (another worker committed first),
    in which case nothing is written.
    """
    cp.advanced = cp.scheduled = cp.progressed = False
    if cp.version < 0:
        return False
    owner = owner or _owner()
    now = now or datetime.now(timezone.utc)
    conn = None
    try:
        conn = db._temp_get_connection()
        key = {"p": cp.provider, "s": cp.scope_key, "v": cp.version, "n": now}
        advancing = scheduled = progressed = False
        if result.may_advance_checkpoint:
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET coverage_through = :b, continuation = NULL, version = version + 1,
                       lease_owner = NULL, lease_until = NULL, last_success_at = :n,
                       consecutive_failures = 0, no_progress_runs = 0, next_attempt_at = NULL,
                       last_error_code = NULL, progress_at = :n, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {**key, "b": cp.interval_end})
            advancing = progressed = True
        elif result.non_exhaustive and _non_exhaustive_policy() == "advance":
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET scheduled_through = :b, continuation = NULL, version = version + 1,
                       lease_owner = NULL, lease_until = NULL, last_success_at = :n,
                       consecutive_failures = 0, no_progress_runs = 0, next_attempt_at = NULL,
                       last_error_code = :e, progress_at = :n, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {**key, "b": cp.interval_end, "e": (result.truncated_reason or "")[:32] or None})
            if res.rowcount:
                _insert_gap(conn, cp.provider, cp.scope_key, cp.interval_start, cp.interval_end,
                            result.truncated_reason or "non_exhaustive", len(result.items), now)
            scheduled = progressed = True
        else:
            new_cont = result.continuation if result.continuation else cp.continuation
            progressed = bool(result.continuation) and result.continuation != cp.continuation
            failed = bool(result.failed)
            fails = cp.consecutive_failures + 1 if failed else (0 if progressed else cp.consecutive_failures)
            no_prog = 0 if progressed else cp.no_progress_runs + 1
            if failed:
                next_at = _backoff(fails, now)
            elif not progressed:
                next_at = _backoff(no_prog, now)
            else:
                next_at = None
            res = conn.execute(text("""
                UPDATE collection_checkpoints
                   SET continuation = CAST(:c AS jsonb), version = version + 1,
                       lease_owner = NULL, lease_until = NULL,
                       consecutive_failures = :f, no_progress_runs = :np, next_attempt_at = :na,
                       progress_at = CASE WHEN :prog THEN :n ELSE progress_at END,
                       last_error_code = :e, updated_at = :n
                 WHERE provider = :p AND scope_key = :s AND version = :v
            """), {**key, "c": _json(new_cont), "f": fails, "np": no_prog, "na": next_at,
                   "prog": progressed,
                   "e": (result.error_code or result.truncated_reason or "")[:32] or None})
        conn.commit()
        if res.rowcount == 0:
            logger.warning("checkpoint %s/%s moved under us (version %s); nothing written",
                           cp.provider, cp.scope_key, cp.version)
            return False
        cp.advanced, cp.scheduled, cp.progressed = advancing, scheduled, progressed
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
        # A scope is stalled when its interval ended over a day ago and neither
        # coverage nor the schedule reached it. Every run touches updated_at,
        # so it cannot say this. ``no_progress`` counts scopes whose last runs
        # moved neither coverage nor their continuation cursor.
        stalled = conn.execute(text("""
            SELECT provider, COUNT(*), MIN(interval_end),
                   COUNT(*) FILTER (WHERE no_progress_runs >= 3),
                   COUNT(*) FILTER (WHERE consecutive_failures >= 3)
              FROM collection_checkpoints
             WHERE (interval_end < NOW() - interval '24 hours'
                    AND COALESCE(GREATEST(coverage_through, scheduled_through), '-infinity') < interval_end)
                OR no_progress_runs >= 3 OR consecutive_failures >= 3
             GROUP BY provider
        """)).fetchall()
        stalled_by = {r[0]: (int(r[1]), r[2], int(r[3]), int(r[4])) for r in stalled}
        gaps = conn.execute(text("""
            SELECT provider, reason, COUNT(*), MIN(interval_start)
              FROM collection_gaps
             WHERE resolved_at IS NULL AND recorded_at > NOW() - make_interval(hours => :h)
             GROUP BY provider, reason
        """), {"h": since_hours}).fetchall()
        pending = conn.execute(text("""
            SELECT provider, scope_key, interval_start, interval_end, coverage_through, consecutive_failures,
                   last_error_code, updated_at, scheduled_through, progress_at, no_progress_runs,
                   next_attempt_at, continuation
              FROM collection_checkpoints
             WHERE continuation IS NOT NULL OR consecutive_failures >= 3 OR no_progress_runs >= 3
             ORDER BY COALESCE(progress_at, updated_at) LIMIT 100
        """)).fetchall()

        def _iso(v):
            return v.isoformat() if v else None

        return {
            "providers": [
                {"provider": r[0], "last_success_at": _iso(r[1]),
                 "last_run_at": _iso(r[2]), "failed": int(r[3]),
                 "partial": int(r[4]), "quota_exhausted": int(r[5]), "empty_success": int(r[6]),
                 "stalled": stalled_by.get(r[0], (0, None, 0, 0))[0],
                 "stalled_oldest_interval_end": _iso(stalled_by.get(r[0], (0, None, 0, 0))[1]),
                 "no_progress": stalled_by.get(r[0], (0, None, 0, 0))[2],
                 "repeatedly_failed": stalled_by.get(r[0], (0, None, 0, 0))[3]}
                for r in providers],
            "errors": [{"provider": r[0], "error_code": r[1], "count": int(r[2])} for r in errors],
            "gaps": [{"provider": r[0], "reason": r[1], "count": int(r[2]), "oldest_start": _iso(r[3])}
                     for r in gaps],
            "pending_intervals": [
                {"provider": r[0], "scope_key": r[1],
                 "interval_start": _iso(r[2]), "interval_end": _iso(r[3]),
                 "coverage_through": _iso(r[4]),
                 "consecutive_failures": int(r[5] or 0), "last_error_code": r[6],
                 "updated_at": _iso(r[7]), "scheduled_through": _iso(r[8]),
                 "progress_at": _iso(r[9]), "no_progress_runs": int(r[10] or 0),
                 "next_attempt_at": _iso(r[11]), "continuation": r[12]}
                for r in pending],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "providers": [], "errors": [], "gaps": [], "pending_intervals": []}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
