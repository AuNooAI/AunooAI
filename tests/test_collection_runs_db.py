"""Run records, checkpoints and the rejected-candidate ledger against the
tenant database.

These write to the live tenant's ``collection_runs``,
``collection_checkpoints`` and ``rejected_candidates`` tables under a
``pytest-cdq`` provider name and delete what they wrote, so they only run
when ``CDQ_DB_TESTS=1`` is set. Spec: work packages 1, 14 and 19.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(os.getenv("CDQ_DB_TESTS") != "1", reason="set CDQ_DB_TESTS=1 to run against the tenant DB")

PROVIDER = "pytest-cdq"


@pytest.fixture
def db():
    from app.database import get_database_instance
    database = get_database_instance()
    yield database
    conn = database._temp_get_connection()
    try:
        conn.execute(text("DELETE FROM collection_runs WHERE provider = :p"), {"p": PROVIDER})
        conn.execute(text("DELETE FROM collection_checkpoints WHERE provider = :p"), {"p": PROVIDER})
        conn.execute(text("DELETE FROM collection_gaps WHERE provider = :p"), {"p": PROVIDER})
        conn.execute(text("DELETE FROM rejected_candidates WHERE group_id = -999"))
        conn.commit()
    finally:
        conn.close()


def test_run_record_written_and_readable(db):
    from app.collectors.contracts import CollectionResult, ERR_QUOTA, TRUNC_QUOTA
    from app.services.collection_runs import record_run, health_summary
    res = CollectionResult.failure(ERR_QUOTA, "newsapi: paused", retryable=True, truncated_reason=TRUNC_QUOTA,
                                   provider=PROVIDER, scope="kw:test").mark_started()
    res.counts.add(received=0, quota_skipped=1)
    rid = record_run(db, res, scope_kind="keyword", scope_id="kw:test")
    assert rid is not None
    summary = health_summary(db, since_hours=1)
    mine = [p for p in summary["providers"] if p["provider"] == PROVIDER]
    assert mine and mine[0]["quota_exhausted"] >= 1 and mine[0]["last_success_at"] is None


def test_checkpoint_only_advances_on_complete_success(db):
    from app.collectors.contracts import CollectionResult, ERR_TIMEOUT, TRUNC_TIME_BUDGET
    from app.services.collection_runs import claim_interval, commit_interval
    scope = "scope:1"
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    assert cp is not None and cp.version == 0 and cp.coverage_through is None
    end1 = cp.interval_end

    # A failure leaves coverage alone, keeps the interval and backs off.
    assert commit_interval(db, cp, CollectionResult.failure(ERR_TIMEOUT, "ReadTimeout", retryable=True))
    assert claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1)) is None
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), ignore_backoff=True)
    assert cp2.coverage_through is None and cp2.interval_end == end1 and cp2.consecutive_failures == 1

    # A partial run keeps the interval and stores the continuation.
    partial = CollectionResult.partial([{"url": "a"}], truncated_reason=TRUNC_TIME_BUDGET, continuation={"page": 2})
    assert commit_interval(db, cp2, partial)
    cp3 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    assert cp3.continuation == {"page": 2} and cp3.interval_end == end1

    # A complete success advances coverage to the interval end and clears it.
    assert commit_interval(db, cp3, CollectionResult.ok([]))
    cp4 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    assert cp4.coverage_through == end1 and cp4.continuation is None
    assert cp4.interval_start == end1 and cp4.interval_end > end1


def test_stale_version_cannot_overwrite(db):
    from app.collectors.contracts import CollectionResult
    from app.services.collection_runs import claim_interval, commit_interval
    scope = "scope:2"
    a = claim_interval(db, PROVIDER, scope, lookback=timedelta(hours=1), owner="worker-a")
    # Worker B cannot claim while A holds the lease.
    assert claim_interval(db, PROVIDER, scope, lookback=timedelta(hours=1), owner="worker-b") is None
    assert commit_interval(db, a, CollectionResult.ok([]), owner="worker-a")
    # A's old checkpoint object is now stale: a second commit does nothing.
    assert not commit_interval(db, a, CollectionResult.ok([]), owner="worker-a")


def test_rejected_candidate_ledger_roundtrip(db):
    from app.services.rejected_candidates import RejectedCandidateLedger, gate_version
    ledger = RejectedCandidateLedger(db)
    v1 = gate_version(["Acme", "acme corp"], 0.6)
    url = "https://example.com/story?utm_source=x"
    assert ledger.lookup([url], -999, v1) == {}
    ledger.record(url, -999, v1, score=0.2, threshold=0.6)
    hits = ledger.lookup(["https://example.com/story"], -999, v1)
    assert len(hits) == 1 and list(hits.values())[0].score == 0.2
    # Different terms → different version → no hit.
    v2 = gate_version(["Acme", "acme corp", "new term"], 0.6)
    assert ledger.lookup([url], -999, v2) == {}
    # Another group is not affected.
    assert ledger.lookup([url], -998, v1) == {}
    # Forgetting re-opens evaluation.
    assert ledger.forget(url) == 1
    assert ledger.lookup([url], -999, v1) == {}


def test_gate_version_is_order_and_case_insensitive():
    from app.services.rejected_candidates import gate_version
    assert gate_version(["B", "a"], 0.5) == gate_version(["a", " b "], 0.5)
    assert gate_version(["a"], 0.5) != gate_version(["a"], 0.6)


def _gaps(db, scope):
    conn = db._temp_get_connection()
    try:
        return conn.execute(text("SELECT reason, interval_start, interval_end, items FROM collection_gaps "
                                 "WHERE provider = :p AND scope_key = :s ORDER BY id"),
                            {"p": PROVIDER, "s": scope}).fetchall()
    finally:
        conn.close()


def test_a_continuation_holds_and_counts_as_progress_not_failure(db):
    from app.collectors.contracts import CollectionResult, TRUNC_TIME_BUDGET
    from app.services.collection_runs import claim_interval, commit_interval
    scope = "scope:cont"
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    end1 = cp.interval_end
    early = CollectionResult.ok([{"url": "a"}])
    early.coverage_complete = False
    early.continuation = {"after": "t3_x"}
    assert commit_interval(db, cp, early) and not cp.advanced and cp.progressed
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    assert cp2.interval_end == end1 and cp2.continuation == {"after": "t3_x"} and cp2.consecutive_failures == 0

    # The same cursor again: no progress, not a failure, and the scope backs off.
    same = CollectionResult.partial([], truncated_reason=TRUNC_TIME_BUDGET, continuation={"after": "t3_x"})
    assert commit_interval(db, cp2, same) and not cp2.progressed
    assert claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1)) is None
    cp3 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), ignore_backoff=True)
    assert cp3.consecutive_failures == 0 and cp3.no_progress_runs == 1 and cp3.coverage_through is None


def test_non_exhaustive_page_moves_the_schedule_and_records_a_gap(db, monkeypatch):
    """A list API's full page never proves coverage. Under the default
    ``advance`` policy the schedule moves past the window and the window is
    written to collection_gaps; coverage_through stays where it was."""
    from app.collectors.contracts import CollectionResult, TRUNC_PAGE_CAP
    from app.services.collection_runs import claim_interval, commit_interval, health_summary
    monkeypatch.delenv("COLLECTION_NON_EXHAUSTIVE_POLICY", raising=False)
    scope = "scope:cap"
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    start1, end1 = cp.interval_start, cp.interval_end
    capped = CollectionResult.ok([{"url": "b"}] * 10)
    capped.coverage_complete = False
    capped.truncated_reason = TRUNC_PAGE_CAP
    assert commit_interval(db, cp, capped) and cp.scheduled and not cp.advanced
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    assert cp2.coverage_through is None and cp2.scheduled_through == end1
    assert cp2.interval_start == end1 and cp2.consecutive_failures == 0
    assert [(g[0], g[1], g[2], g[3]) for g in _gaps(db, scope)] == [("page_cap", start1, end1, 10)]
    summary = health_summary(db, since_hours=1)
    assert any(g["provider"] == PROVIDER and g["reason"] == "page_cap" for g in summary["gaps"])


def test_non_exhaustive_page_under_hold_keeps_the_interval(db, monkeypatch):
    from app.collectors.contracts import CollectionResult, TRUNC_PAGE_CAP
    from app.services.collection_runs import claim_interval, commit_interval
    monkeypatch.setenv("COLLECTION_NON_EXHAUSTIVE_POLICY", "hold")
    scope = "scope:hold"
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    end1 = cp.interval_end
    capped = CollectionResult.ok([{"url": "b"}])
    capped.coverage_complete = False
    capped.truncated_reason = TRUNC_PAGE_CAP
    assert commit_interval(db, cp, capped) and not cp.scheduled and not cp.advanced
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), ignore_backoff=True)
    assert cp2.interval_end == end1 and cp2.consecutive_failures == 0 and cp2.no_progress_runs == 1
    assert _gaps(db, scope) == []


def test_an_old_unfinished_window_is_never_skipped(db):
    """The stall valve is gone: however long a window has been stuck, a
    run that did not finish it leaves coverage where it was."""
    from app.collectors.contracts import CollectionResult, ERR_TIMEOUT, TRUNC_TIME_BUDGET
    from app.services.collection_runs import claim_interval, commit_interval, health_summary
    scope = "scope:stall"
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1))
    end1 = cp.interval_end
    late = end1 + timedelta(days=10)
    stuck = CollectionResult.partial([{"url": "a"}], truncated_reason=TRUNC_TIME_BUDGET,
                                     continuation={"chunk": 0, "page": 4})
    assert commit_interval(db, cp, stuck, now=late) and not cp.advanced
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), now=late, ignore_backoff=True)
    assert cp2.coverage_through is None and cp2.interval_end == end1
    for _ in range(3):
        assert commit_interval(db, cp2, CollectionResult.failure(ERR_TIMEOUT, "slow", retryable=True), now=late)
        cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), now=late, ignore_backoff=True)
    assert cp2.coverage_through is None and cp2.consecutive_failures == 3
    # The failures kept the cursor of the page that failed.
    assert cp2.continuation == {"chunk": 0, "page": 4}
    summary = health_summary(db, since_hours=1)
    mine = [p for p in summary["providers"] if p["provider"] == PROVIDER]
    pend = [p for p in summary["pending_intervals"] if p["scope_key"] == scope]
    assert pend and pend[0]["consecutive_failures"] == 3


def test_lookback_cap_records_the_skipped_stretch_as_a_gap(db):
    from app.collectors.contracts import CollectionResult
    from app.services.collection_runs import claim_interval, commit_interval
    scope = "scope:lookback"
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    cp = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), now=t0)
    assert commit_interval(db, cp, CollectionResult.ok([]), now=t0)
    later = t0 + timedelta(days=10)
    cp2 = claim_interval(db, PROVIDER, scope, lookback=timedelta(days=1), now=later)
    assert cp2.interval_start == later - timedelta(days=1)
    gaps = _gaps(db, scope)
    assert len(gaps) == 1 and gaps[0][0] == "lookback_cap" and gaps[0][1] == t0
