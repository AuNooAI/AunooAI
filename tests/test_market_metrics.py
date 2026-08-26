"""The rule that a zero must be a measurement.

MM-01 to MM-09 from the Market Monitor specification. The interesting cases are
the ones that used to render as ``0``: a source that never ran, a source that
failed, a source that reached part of the market. Each of those is now a
different state, and each test here is written so that collapsing two of them
back together fails.

Everything that touches the database runs inside a transaction that is rolled
back, so the states are constructed rather than waited for. A test that can only
assert what production happens to contain is a test that stops testing the day
production changes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.services import market_metrics as mmet

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the state queries are Postgres jsonb and window functions')


@pytest.fixture()
def conn():
    """A connection whose work is always discarded."""
    from app.database import get_database_instance

    c = get_database_instance()._temp_get_connection()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    row = conn.execute(text(
        "SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip('no market in this database')
    return int(row)


def _a_vendor(conn, market_id: int, source: str) -> int:
    """One vendor in this market with a policy row for ``source``."""
    bid = conn.execute(text("""
        SELECT p.brand_id FROM bw_entity_source_policies p
        JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded' AND p.source = :s
        ORDER BY p.brand_id LIMIT 1
    """), {'m': market_id, 's': source}).scalar()
    if bid is None:
        pytest.skip(f'no {source} policy rows in this market')
    return int(bid)


# ---------------------------------------------------------------------------
# The states themselves
# ---------------------------------------------------------------------------

def test_mm01_a_source_that_never_ran_is_never_collected_not_zero(conn, market):
    """MM-01. Eligible, no run: ``never_collected``, and never a numeric zero."""
    src = 'linkedin_company_post'
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NULL, last_attempt_at = NULL, claimed_at = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})
    # No run rows either, or the failed branch claims it first.
    conn.execute(text("DELETE FROM bw_collection_runs "
                      "WHERE market_id = :m AND source = :s"),
                 {'m': market, 's': src})

    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'never_collected'
    assert state['coverage']['successful'] == 0
    assert state['coverage']['eligible'] > 0, 'the fixture needs eligible vendors'

    # The rule this whole module exists for: a count of zero against a source
    # that never ran is not an observed zero.
    assert mmet.resolve(state, 0) == 'never_collected'
    assert 'never_collected' in mmet.UNMEASURED


def test_mm02_a_failed_latest_run_reads_failed_and_keeps_the_last_good(conn, market):
    """MM-02. Latest run failed: ``failed``, with the last success preserved."""
    src = 'linkedin_company_post'
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NULL, last_attempt_at = NOW(), claimed_at = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})
    conn.execute(text("""
        INSERT INTO bw_collection_runs
            (market_id, source, provider, status, error_code, error, started_at)
        VALUES (:m, :s, 'brightdata', 'failed', 'http_400',
                'the provider rejected the request', NOW())
    """), {'m': market, 's': src})

    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'failed'
    # The error is surfaced, because "failed" with no reason sends somebody
    # looking through logs for something we already know.
    assert state['state_detail'] == 'http_400'
    assert state['latest_run']['status'] == 'failed'
    assert mmet.resolve(state, 0) == 'failed'


def test_mm03_partial_collection_reports_both_numbers(conn, market):
    """MM-03. Some vendors succeeded: ``partial``, with covered and expected."""
    src = 'linkedin_company_post'
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})
    # Exactly two succeed.
    conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET last_success_at = NOW(), last_attempt_at = NOW()
         WHERE id IN (
               SELECT p.id FROM bw_entity_source_policies p
                 JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
                WHERE mb.market_id = :m AND mb.role <> 'excluded'
                  AND p.source = :s
                ORDER BY p.brand_id LIMIT 2)
    """), {'m': market, 's': src})

    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'partial'
    assert state['coverage']['successful'] == 2
    assert state['coverage']['eligible'] > 2
    # A percentage on its own hides which of the two coverage ideas it is, so
    # both numbers have to travel with it.
    assert f"2 of {state['coverage']['eligible']}" in state['coverage']['label']
    assert mmet.resolve(state, 0) == 'partial'


def test_mm04_all_succeeded_with_nothing_found_is_the_only_real_zero(conn, market):
    """MM-04. Every eligible vendor succeeded and found none: ``observed_zero``."""
    src = 'linkedin_company_post'
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW(), last_attempt_at = NOW(), claimed_at = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})

    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'healthy'
    assert mmet.resolve(state, 0) == 'observed_zero'
    # And a real count still reads as a plain measurement.
    assert mmet.resolve(state, 17) == 'healthy'
    # observed_zero is the one empty-looking state that is a measurement.
    assert 'observed_zero' not in mmet.UNMEASURED


def test_mm05_an_unchanged_payload_writes_no_snapshot_and_is_still_healthy(conn, market):
    """MM-05. The trap that made a working collector look broken.

    ``market_collect.store_snapshot`` deduplicates on a content hash, so a
    profile poll that finds nothing changed writes no new snapshot row. Reading
    health from snapshot rows therefore reports a healthy weekly collector as
    failed every week the vendor did not edit its page. Health comes from the
    policy row, which records the attempt regardless.
    """
    src = 'linkedin_company_profile'
    _a_vendor(conn, market, src)
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW(), last_attempt_at = NOW(),
               consecutive_failures = 0, claimed_at = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})
    # No snapshot rows at all for this market's vendors: the payload never
    # changed, so nothing was stored.
    conn.execute(text("""
        DELETE FROM bw_vendor_snapshots
         WHERE snapshot_type = 'profile' AND brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'m': market})

    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'healthy', (
        'an unchanged payload stores no row and must not read as a failure')


def test_stale_uses_the_sources_own_cadence_not_one_global_threshold(conn, market):
    """A weekly collector and a twelve-hourly one cannot share a threshold.

    Sharing one meant the weekly profile source read as stale six days out of
    seven. Two missed intervals of its *own* cadence is the rule.
    """
    src = 'linkedin_company_profile'
    cadence = mmet.sch.CADENCE_HOURS[src]
    # One interval late: not stale.
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW() - (:h || ' hours')::INTERVAL,
               last_attempt_at = NOW(), claimed_at = NULL, cadence_seconds = NULL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market, 'h': str(cadence + 1)})
    assert mmet.collection_state(conn, market, src)['state'] == 'healthy'

    # Past two intervals: stale.
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW() - (:h || ' hours')::INTERVAL
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market, 'h': str(cadence * 2 + 1)})
    state = mmet.collection_state(conn, market, src)
    assert state['state'] == 'stale'
    assert state['freshness']['is_stale'] is True


def test_a_source_no_vendor_can_use_is_unconfigured_not_broken(conn, market):
    """Indeed has no employer field, so nothing is eligible for it.

    That is a configuration fact, not a collector failure, and the reason has to
    come through — otherwise the panel sends a reader looking for an identifier
    that does not exist.
    """
    state = mmet.collection_state(conn, market, 'indeed_jobs')
    assert state['state'] == 'not_configured'
    assert state['scheduled'] is False
    assert 'employer' in (state['state_detail'] or ''), state['state_detail']


# ---------------------------------------------------------------------------
# Quiet versus unmeasured (MM-08, MM-09)
# ---------------------------------------------------------------------------

def test_mm08_and_mm09_quiet_requires_collection_unmeasured_is_separate(conn, market):
    """The finding that was actively wrong before this change.

    A vendor with no posts on file looks identical whether it published nothing
    or was never collected. Reported as quiet, the dashboard accused 57
    companies of silence that nobody had listened for.
    """
    from app.services import market_analysis as man

    src = 'linkedin_company_post'
    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW()
         WHERE p.source = :s AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'s': src, 'm': market})

    before = man.share_of_voice(conn, market, days=30)
    assert before['quietest_total'] > 0, 'the fixture needs some quiet vendors'
    assert before['unmeasured_total'] == 0

    # MM-09: take one quiet vendor's collection away.
    victim = before['quietest'][0]
    conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET last_success_at = NULL
         WHERE brand_id = :b AND source = :s
    """), {'b': victim['brand_id'], 's': src})

    after = man.share_of_voice(conn, market, days=30)
    quiet_ids = {v['brand_id'] for v in after['quietest']}
    unmeasured_ids = {v['brand_id'] for v in after['unmeasured']}
    assert victim['brand_id'] not in quiet_ids, (
        'a vendor we never collected must not be called quiet')
    assert victim['brand_id'] in unmeasured_ids
    assert after['quietest_total'] == before['quietest_total'] - 1
    # The two groups are disjoint, so no caller can double count them.
    assert not (quiet_ids & unmeasured_ids)


def test_last_posted_is_all_time_so_a_quiet_month_is_not_reported_as_never(conn, market):
    """MM-08's date rule.

    "Last posted" inside the selected window is always empty for a quiet vendor
    by construction, which would print "never" for a vendor that posted last
    month. The date is deliberately unbounded by the window.
    """
    from app.services import market_analysis as man

    conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = NOW()
         WHERE p.source = 'linkedin_company_post' AND p.brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'m': market})

    # A one-day window makes almost everyone quiet, which is the point: their
    # real last-post dates still have to come through.
    narrow = man.share_of_voice(conn, market, days=1)
    dated = [v for v in narrow['quietest'] if v['last_posted_at']]
    assert dated, 'some quiet vendor should have posted at some point'
    for v in narrow['quietest']:
        assert v['posts_in_selected_window'] == 0


# ---------------------------------------------------------------------------
# Headcount (MM-06, MM-07)
# ---------------------------------------------------------------------------

def test_mm06_a_mover_needs_two_readings_and_shows_both_dates(conn, market):
    """MM-06. Two exact readings produce a mover with both values and dates."""
    from app.services import market_publish as mp

    src = 'linkedin_company_profile'
    bid = _a_vendor(conn, market, src)
    conn.execute(text("""
        DELETE FROM bw_vendor_snapshots
         WHERE snapshot_type = 'profile' AND brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'m': market})
    for days_ago, count in ((30, 100), (1, 120)):
        conn.execute(text("""
            INSERT INTO bw_vendor_snapshots
                (brand_id, source, provider_item_id, snapshot_type, data,
                 observed_at, content_hash)
            VALUES (:b, 'linkedin_company_profile', :h, 'profile',
                    CAST(:d AS JSONB),
                    NOW() - (:n || ' days')::INTERVAL, :h)
        """), {'b': bid, 'd': '{"employee_count": %d}' % count,
               'n': str(days_ago), 'h': f'test-{days_ago}-{count}'})

    out = mp.headcount_market(conn, {'id': market})
    mine = [m for m in out['movers'] if m['brand_id'] == bid]
    assert len(mine) == 1, out['movers']
    mover = mine[0]
    assert (mover['previous'], mover['latest']) == (100.0, 120.0)
    assert mover['delta'] == 20.0
    assert mover['pct'] == 20.0
    # Both dates, because +20 over a month and +20 over a day are different
    # facts and a reader cannot tell them apart otherwise.
    assert mover['previous_at'] and mover['latest_at']
    assert mover['previous_at'] < mover['latest_at']


def test_mm07_a_band_or_a_single_reading_is_excluded_from_the_sum(conn, market):
    """MM-07. Neither a size band nor one reading may become a data point.

    The band case is the dangerous one. A parser that strips non-digits turns
    "51-200" into 51200 and "1,001-5,000" into 10015000, so one provider
    response missing the exact field could put ten million staff into a market
    total with nothing on screen to suggest a problem.
    """
    from app.services import market_publish as mp

    src = 'linkedin_company_profile'
    bid = _a_vendor(conn, market, src)
    conn.execute(text("""
        DELETE FROM bw_vendor_snapshots
         WHERE snapshot_type = 'profile' AND brand_id IN (
               SELECT brand_id FROM bw_market_brands
                WHERE market_id = :m AND role <> 'excluded')
    """), {'m': market})
    # A band, and a zero, which the provider returns when it has no count.
    conn.execute(text("""
        INSERT INTO bw_vendor_snapshots
            (brand_id, source, provider_item_id, snapshot_type, data,
             observed_at, content_hash)
        VALUES (:b, 'linkedin_company_profile', 'test-band', 'profile',
                CAST('{"employee_band": "51-200", "employee_count": 0}' AS JSONB),
                NOW(), 'test-band')
    """), {'b': bid})

    out = mp.headcount_market(conn, {'id': market})
    assert out['observed_market_headcount'] == 0
    assert out['cohort'] == 0
    assert all(m['brand_id'] != bid for m in out['movers'])
    gaps = {g['brand_id'] for g in out['insufficient_history']}
    assert bid in gaps, 'a vendor with no exact reading belongs in the gap list'

    # One exact reading is still not movement.
    conn.execute(text("""
        INSERT INTO bw_vendor_snapshots
            (brand_id, source, provider_item_id, snapshot_type, data,
             observed_at, content_hash)
        VALUES (:b, 'linkedin_company_profile', 'test-one', 'profile',
                CAST('{"employee_count": 77}' AS JSONB),
                NOW(), 'test-one')
    """), {'b': bid})
    out = mp.headcount_market(conn, {'id': market})
    assert out['observed_market_headcount'] == 77
    assert all(m['brand_id'] != bid for m in out['movers'])
    reasons = [g['reason'] for g in out['insufficient_history']
               if g['brand_id'] == bid]
    assert reasons and 'one' in reasons[0].lower()


def test_the_workbook_baseline_is_never_summed_into_a_linkedin_total(conn, market):
    """The forbidden join, kept apart.

    The old movers query compared the latest LinkedIn reading against the April
    workbook import and called the difference growth: two different
    measurements four months apart, so nearly every vendor looked like a mover.
    The comparison still ships, under its own key, with its own source label.
    """
    from app.services import market_publish as mp

    out = mp.headcount_market(conn, {'id': market})
    baseline = out['baseline_comparison']
    assert 'workbook' in baseline['source']
    assert baseline['caution']
    # Nothing from the baseline reaches the movers list.
    for mover in out['movers']:
        assert 'workbook' not in mover


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------

def test_a_metric_takes_the_worst_state_of_its_sources(conn, market):
    """A total whose news half failed is not healthy because LinkedIn worked."""
    healthy = {'source': 'linkedin_company_post', 'state': 'healthy',
               'coverage': {}, 'freshness': {'last_success_at': None,
                                             'expected_interval_seconds': 3600},
               'latest_run': None}
    broken = dict(healthy, source='news', state='failed')
    meta = mmet.metric('x', label='X', definition='d', numerator='n',
                       collections=[healthy, broken], value=5)
    assert meta['data_state'] == 'failed'
    assert meta['measured'] is False
    # Both sources are still named, so the reader can see which half failed.
    assert len(meta['sources']) == 2


def test_every_metric_carries_what_the_contract_requires():
    """The envelope is the point; a metric missing half of it is not auditable."""
    state = {'source': 'linkedin_company_post', 'state': 'healthy',
             'coverage': {'registry_total': 83, 'eligible': 82,
                          'attempted': 82, 'successful': 82,
                          'pct_of_eligible': 100.0, 'label': '82 of 82 vendors'},
             'freshness': {'last_success_at': None, 'stale_after': None,
                           'is_stale': False,
                           'expected_interval_seconds': 43200},
             'latest_run': None}
    meta = mmet.metric('owned_post_volume', label='Vendor posts observed',
                       definition='d', numerator='posts',
                       denominator='vendors', window={'days': 30},
                       collection=state, value=533,
                       limitations=['LinkedIn only'])
    for field in ('metric_id', 'label', 'definition', 'numerator',
                  'denominator', 'window', 'as_of', 'data_state', 'sources',
                  'coverage', 'freshness', 'limitations'):
        assert meta.get(field) is not None, f'{field} missing'
    src = meta['sources'][0]
    # Platform and provider are separate fields, always. Collapsing them is how
    # Xpoz ended up reported as a social network.
    assert src['platform'] == 'LinkedIn'
    assert src['provider'] == 'Bright Data'
    assert src['ownership'] == 'vendor-owned'


def test_the_legend_never_reports_a_provider_as_a_platform():
    """Xpoz is a provider; its items carry their own real platform."""
    xpoz = mmet.legend_for('xpoz_social')
    assert xpoz['provider'] == 'Xpoz'
    assert xpoz['platform'] != 'Xpoz'
    assert xpoz['ownership'].startswith('third-party')
    # An unknown source admits it rather than defaulting to a plausible guess.
    unknown = mmet.legend_for('something_new')
    assert unknown['platform'] == 'unknown'


def test_every_tracked_source_has_a_legend_entry():
    """A source with no legend row renders as "unknown" on the page."""
    missing = [s for s in mmet.tracked_sources()
               if mmet.legend_for(s)['platform'] == 'unknown']
    assert not missing, f'no legend row for: {missing}'
