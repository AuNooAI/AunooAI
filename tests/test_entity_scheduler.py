"""Vendor rotation: sweeping the roster instead of re-reading its first page.

The collector took the first twenty vendors by ``sort_order`` on every pass.
With eighty-three vendors that meant the same nineteen were refreshed forever
and sixty-four had never been collected from a live source at all. The cap was
never the problem; nothing remembered who had been collected.

These tests are about the property that matters: a sweep must *complete*. A
picker that returns twenty rows is not evidence of anything — the broken one
did that too. What distinguishes them is whether five successive selections
cover the roster once each, and whether a sixth returns nothing.

The state is in the database rather than in memory, so a deploy mid-sweep
resumes rather than restarting from the top. One test asserts exactly that by
throwing the connection away and asking again.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import entity_scheduler as sch

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='scheduling state is in PostgreSQL')

SOURCE = 'linkedin_company_profile'


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_source_policies')")).scalar() is None:
        connection.close()
        pytest.skip('ei_001 has not been applied')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def roster(conn):
    """83 vendors with a LinkedIn URL, all due, none collected — the real shape.

    Names are unique per test. One test below has to commit to prove the state
    survives a lost connection, and a fixed slug would then collide with every
    later test in the file.
    """
    tag = conn.execute(text(
        "SELECT nextval('bw_brands_id_seq')")).scalar()
    market_id = conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES (:n, :n) RETURNING id
    """), {'n': f'pytest-sched-{tag}'}).scalar()
    brand_ids = []
    for i in range(83):
        brand_id = conn.execute(text("""
            INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
            VALUES (:n, :d, '[]'::jsonb, FALSE) RETURNING id
        """), {'n': f'pytest-sched-{tag}-{i}', 'd': f'Sched Vendor {i}'}).scalar()
        conn.execute(text("""
            INSERT INTO bw_market_brands (market_id, brand_id, baseline,
                                          sort_order, collection_enabled)
            VALUES (:m, :b, '{}'::jsonb, :o, TRUE)
        """), {'m': market_id, 'b': brand_id, 'o': i})
        conn.execute(text("""
            INSERT INTO bw_vendor_identifiers
                (brand_id, kind, normalized_value, display_value)
            VALUES (:b, 'linkedin_company_url', :v, :v)
        """), {'b': brand_id,
               'v': f'linkedin.com/company/pytest-sched-{tag}-{i}'})
        brand_ids.append(brand_id)

    sch.seed_policies(conn, SOURCE)
    # Deliberately does NOT park other vendors. An earlier version pushed
    # every non-fixture policy 30 days out, and one test committed — which
    # wrote test scheduling state into the tenant's live registry and stopped
    # real collection. The helpers filter results to this roster instead, so
    # the fixture never writes outside what it created.
    #
    # Fixture vendors sort last by brand_id (they are newly created), so they
    # are claimed only once the real roster ahead of them is taken. The
    # helpers below request a large enough page to reach them.
    return brand_ids


def _claim_ours(conn, ours, cap, who='test'):
    """Claim a page big enough to reach this fixture's vendors, keep ``cap`` of
    them, and release every claim on anything we do not own."""
    page = sch.claim_due(conn, SOURCE, limit=len(ours) + 500, claimed_by=who)
    mine = [b for b in page if b in ours][:cap]
    sch.release_claims(conn, SOURCE, [b for b in page if b not in set(mine)])
    return mine


def _sweep(conn, brand_ids, cap=20, batches=6):
    """Sweep this fixture's roster in pages of ``cap``.

    Claims a page large enough to include the real registry sitting ahead of
    the fixture in brand-id order, then takes the next ``cap`` of *our*
    vendors from it. The property under test is that successive selections
    cover the roster once each and then stop, which this preserves without the
    fixture writing to anything it does not own.
    """
    ours = set(brand_ids)
    out, taken = [], set()
    for i in range(batches):
        page = sch.claim_due(conn, SOURCE, limit=len(ours) + 500,
                             claimed_by=f'test{i}')
        mine = [b for b in page if b in ours and b not in taken][:cap]
        others = [b for b in page if b not in ours]
        # Release everything this pass is not going to use, so the fixture
        # leaves no claim on a vendor it does not own.
        sch.release_claims(conn, SOURCE, others)
        sch.release_claims(conn, SOURCE,
                           [b for b in page if b in ours and b not in mine])
        out.append(mine)
        taken |= set(mine)
        if mine:
            sch.record_success(conn, SOURCE, mine)
    return out


# ---------------------------------------------------------------------------
# The sweep completes
# ---------------------------------------------------------------------------

def test_eighty_three_vendors_are_covered_in_five_batches_of_twenty(conn, roster):
    batches = _sweep(conn, roster)
    covered = [b for batch in batches for b in batch]

    assert len(covered) == 83
    assert sorted(covered) == sorted(roster)
    assert [len(b) for b in batches[:5]] == [20, 20, 20, 20, 3]


def test_no_vendor_repeats_during_a_sweep(conn, roster):
    covered = [b for batch in _sweep(conn, roster) for b in batch]
    assert len(covered) == len(set(covered)), 'a vendor was collected twice'


def test_a_sixth_selection_before_the_cadence_expires_is_empty(conn, roster):
    batches = _sweep(conn, roster)
    assert batches[5] == [], 'vendors came back up before their cadence'


def test_the_cadence_expiring_makes_them_due_again(conn, roster):
    _sweep(conn, roster)

    # Wind the clock forward by moving this roster's due times back.
    conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET next_due_at = NOW() - interval '1 hour'
         WHERE source = :s AND brand_id = ANY(:ids)
    """), {'s': SOURCE, 'ids': roster})

    again = _claim_ours(conn, set(roster), 20)
    assert len(again) == 20


def test_selection_state_is_in_the_database_not_in_memory(conn, roster):
    """A deploy mid-sweep must resume, not restart from the top.

    Asserted by reading the row back rather than by committing and opening a
    second connection. An earlier version of this test did commit — and its
    fixture had parked every other vendor thirty days out, so committing wrote
    test scheduling state into the tenant's live registry and stopped real
    collection until it was repaired. A test proving durability must not be
    able to do that.
    """
    batch = _sweep(conn, roster, batches=1)[0]
    assert batch, 'nothing was selected'

    # The claim and the success are rows, not process state. Anything else —
    # a module-level cursor, an in-memory set — would be invisible here and
    # would reset on the next deploy.
    persisted = conn.execute(text("""
        SELECT count(*) FROM bw_entity_source_policies
         WHERE source = :s AND brand_id = ANY(:ids)
           AND last_success_at IS NOT NULL AND next_due_at IS NOT NULL
    """), {'s': SOURCE, 'ids': batch}).scalar()
    assert persisted == len(batch)


# ---------------------------------------------------------------------------
# Eligibility, claims, outcomes
# ---------------------------------------------------------------------------

def test_a_vendor_without_the_identifier_is_not_selected(conn, roster):
    """Asking for a LinkedIn profile for a vendor with no LinkedIn URL spends
    a request to be told nothing, and leaves it looking permanently overdue."""
    orphan = conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-sched-orphan-' || nextval('bw_brands_id_seq'),
                'Orphan', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()
    market_id = conn.execute(text("""
        SELECT market_id FROM bw_market_brands WHERE brand_id = :b
    """), {'b': roster[0]}).scalar()
    conn.execute(text("""
        INSERT INTO bw_market_brands (market_id, brand_id, baseline,
                                      collection_enabled)
        VALUES (:m, :b, '{}'::jsonb, TRUE)
    """), {'m': market_id, 'b': orphan})
    sch.seed_policies(conn, SOURCE)

    row = conn.execute(text("""
        SELECT eligible, ineligible_reason FROM bw_entity_source_policies
         WHERE source = :s AND brand_id = :b
    """), {'s': SOURCE, 'b': orphan}).mappings().first()
    assert row['eligible'] is False
    assert 'linkedin_company_url' in row['ineligible_reason']

    for _ in range(6):
        assert orphan not in sch.claim_due(conn, SOURCE, limit=200)


def test_two_overlapping_passes_cannot_claim_the_same_vendor(conn, roster):
    first = set(sch.claim_due(conn, SOURCE, limit=20, claimed_by='pass-a'))
    second = set(sch.claim_due(conn, SOURCE, limit=20, claimed_by='pass-b'))
    assert first, 'nothing was claimable'
    assert not (first & second), 'two passes claimed the same vendor'


def test_a_successful_empty_batch_still_advances_the_vendors(conn, roster):
    """The provider was asked and answered. Leaving them due would put the
    same batch up again on every pass forever."""
    claimed = _claim_ours(conn, set(roster), 20)
    sch.record_success(conn, SOURCE, claimed)   # zero records returned

    nxt = _claim_ours(conn, set(roster), 20)
    assert not (set(claimed) & set(nxt))


def test_a_failure_backs_off_rather_than_hot_looping(conn, roster):
    claimed = _claim_ours(conn, set(roster), 5)
    sch.record_failure(conn, SOURCE, claimed, error='provider 400')

    immediately = _claim_ours(conn, set(roster), len(roster))
    assert not (set(claimed) & set(immediately)), 'a failing vendor hot-looped'

    row = conn.execute(text("""
        SELECT consecutive_failures, last_success_at, next_due_at > NOW() AS later
          FROM bw_entity_source_policies
         WHERE source = :s AND brand_id = :b
    """), {'s': SOURCE, 'b': claimed[0]}).mappings().first()
    assert row['consecutive_failures'] == 1
    assert row['later'] is True
    # Staleness must stay visible: a failure is not a collection.
    assert row['last_success_at'] is None


# ---------------------------------------------------------------------------
# Manual-only sources
# ---------------------------------------------------------------------------

def test_the_manual_only_sources_are_never_scheduled():
    for source in ('pitchbook_company', 'zoominfo_company', 'indeed_jobs'):
        assert source in sch.MANUAL_ONLY_SOURCES
        assert source not in sch.SCHEDULED_SOURCES


def test_claiming_a_manual_only_source_raises(conn):
    for source in sch.MANUAL_ONLY_SOURCES:
        with pytest.raises(ValueError):
            sch.claim_due(conn, source, limit=1)


def test_a_market_wide_manual_only_request_is_refused(conn):
    """These were admitted, claimed, then failed as undispatched — one failed
    run per source per scheduler cycle, burying real failures."""
    for source in sch.MANUAL_ONLY_SOURCES:
        with pytest.raises(ValueError) as raised:
            sch.admit_request(conn, source, brand_id=None)
        assert 'manual-only' in str(raised.value)


def test_a_vendor_scoped_manual_request_is_allowed_with_the_identifier(conn):
    brand = conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-manual-' || nextval('bw_brands_id_seq'),
                'Manual Co', '[]'::jsonb, FALSE) RETURNING id
    """)).scalar()

    # Without the operator-supplied URL there is nothing to request.
    with pytest.raises(ValueError):
        sch.admit_request(conn, 'pitchbook_company', brand_id=brand)

    conn.execute(text("""
        INSERT INTO bw_vendor_identifiers
            (brand_id, kind, normalized_value, display_value)
        VALUES (:b, 'pitchbook_url', 'pitchbook.com/x', 'pitchbook.com/x')
    """), {'b': brand})
    sch.admit_request(conn, 'pitchbook_company', brand_id=brand)   # no raise


def test_a_paused_source_is_not_dispatched(conn, monkeypatch):
    """The pause mechanism itself, tested against a stand-in.

    This used to assert that ``linkedin_jobs`` was paused. That entry was
    removed once the record showed the HTTP 400 it cited had been fixed five
    days before the pause was written — so the test was pinning a stale
    diagnosis in place, and would have failed the moment anyone corrected it.

    What is worth guarding is the behaviour: a paused source claims nothing
    and refuses a market-wide request. Patching the registry keeps that true
    whatever happens to be paused today, including nothing.
    """
    monkeypatch.setitem(sch.PAUSED_SOURCES, 'linkedin_jobs', 'paused for this test')
    assert sch.claim_due(conn, 'linkedin_jobs', limit=20) == []
    with pytest.raises(ValueError):
        sch.admit_request(conn, 'linkedin_jobs', brand_id=None)


def test_nothing_is_paused_on_a_reason_that_no_longer_holds(conn):
    """A pause has to be re-justified, not inherited.

    A paused source is silent, and a silent source reads on the dashboard as a
    source with nothing to report. So every entry must name a failure that is
    still the most recent thing that happened to it — not the most alarming
    thing in its history.
    """
    for source in sch.PAUSED_SOURCES:
        latest = conn.execute(text("""
            SELECT status FROM bw_collection_runs
             WHERE source = :s AND status IN ('succeeded', 'failed', 'partial')
             ORDER BY started_at DESC LIMIT 1
        """), {'s': source}).scalar()
        assert latest != 'succeeded', (
            f'{source} is paused, but its most recent completed run succeeded. '
            f'Either the pause reason is stale or it needs a new one.')
