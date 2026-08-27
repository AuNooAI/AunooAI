"""One vendor against its market, without flattering either (spec 4.16).

MM-26 to MM-31. The arithmetic here is trivial and the failure modes are not:
every one of them is a number that computes cleanly and means something other
than what it appears to say. A peer we did not measure entering the cohort at
zero. A cohort of four passed off as a market. A "Top 20" that is really a top
six. A median recomputed from whoever happened to refresh today.

Most of these run on constructed cohorts rather than on the database, because
the point is the rule, and a test that can only assert what production happens
to contain stops testing the day production changes.
"""

from __future__ import annotations

import os
import statistics

import pytest
from sqlalchemy import text

from app.services import market_benchmark as mb

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='the value queries are Postgres jsonb and window functions')


SPEC = mb.METRICS['posts']


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


def _measured(values, *, unmeasured=None, eligible=None, degraded=False,
              as_of='2026-08-26T17:13:37+02:00', state='healthy'):
    """A prepared metric, in the shape ``metric_values`` returns."""
    unmeasured = unmeasured or {}
    ids = eligible or (set(values) | set(unmeasured))
    return {
        'values': dict(values),
        'unmeasured': dict(unmeasured),
        'eligible': {b: f'V{b}' for b in ids},
        'collection': {'state': state, 'label': 'Vendor posts',
                       'freshness': {'last_success_at': as_of}},
        'as_of': as_of, 'spec': SPEC, 'degraded': degraded,
    }


# ---------------------------------------------------------------------------
# Cohort size (MM-26, MM-27, MM-28)
# ---------------------------------------------------------------------------

def test_mm26_the_vendor_is_excluded_from_the_aggregates_it_is_compared_with():
    """MM-26. Fifty peers, and the comparator must not contain the vendor.

    A vendor included in its own market median is partly being compared with
    itself, and the bigger its value the more it drags the thing it is supposed
    to be measured against. With an outlier vendor the difference is large
    enough to reverse the reading.
    """
    peers = {b: float(b) for b in range(2, 52)}          # 50 peers, 2..51
    values = {**peers, 1: 10_000.0}                      # the selected vendor
    out = mb.compare(_measured(values), 1)

    assert out['market_peer_count'] == 50
    assert out['top_peer_count'] == mb.TOP_N
    assert out['top_label'] == 'Top 20 by Owned LinkedIn posts'

    peer_values = sorted(peers.values())
    assert out['market_median'] == round(statistics.median(peer_values), 2)
    assert out['market_average'] == round(statistics.fmean(peer_values), 2)
    top = sorted(peers.values(), reverse=True)[:mb.TOP_N]
    assert out['top_median'] == round(statistics.median(top), 2)
    assert out['top_average'] == round(statistics.fmean(top), 2)

    # Including the vendor would have pulled the average up by roughly 196.
    assert out['market_average'] < 200


def test_mm26_the_percentile_is_the_one_place_the_vendor_counts_itself():
    """A rank is a position among everyone, including the vendor being ranked."""
    values = {b: float(b) for b in range(1, 11)}
    out = mb.compare(_measured(values), 10)
    # Top of ten, midranked: it beats nine and ties with itself.
    assert out['vendor_percentile'] == 95


def test_mm27_twelve_peers_is_labelled_top_twelve_not_top_twenty():
    """MM-27. The header must never claim a cohort it does not have."""
    values = {b: float(b) for b in range(1, 14)}         # vendor 1 + 12 peers
    out = mb.compare(_measured(values), 1)

    assert out['suppressed'] is False
    assert out['market_peer_count'] == 12
    assert out['top_peer_count'] == 12
    assert out['top_label'] == 'Top 12 available'
    assert '20' not in out['top_label']


def test_mm28_four_peers_suppresses_the_aggregates_entirely():
    """MM-28. Below five peers there is no market to compare against.

    Not a smaller median — none. A median of four values in an 84-vendor
    registry is both noise and close to naming its members.
    """
    values = {b: float(b) for b in range(1, 6)}          # vendor 1 + 4 peers
    out = mb.compare(_measured(values), 1)

    assert out['suppressed'] is True
    assert out['market_median'] is None
    assert out['market_average'] is None
    assert out['top_median'] is None
    assert out['top_average'] is None
    assert out['vendor_percentile'] is None
    assert 'Insufficient peer coverage' in out['notes'][0]


def test_mm28_the_floor_is_a_real_floor():
    assert mb.MIN_PEERS >= 5, 'four numbers are not a market either'


# ---------------------------------------------------------------------------
# What counts as a value (MM-29)
# ---------------------------------------------------------------------------

def test_mm29_an_observed_zero_counts_and_an_unmeasured_peer_does_not():
    """MM-29. The distinction the whole metric contract rests on.

    A vendor that published nothing and a vendor whose collection failed both
    render as "no posts" to the eye. One is a measurement and belongs in the
    median; the other is an outage and would drag it down while ranking the
    broken vendor last.
    """
    values = {1: 10.0, 2: 0.0, 3: 8.0, 4: 6.0, 5: 4.0, 6: 2.0}
    out_with_zero = mb.compare(_measured(values), 1)

    # Same cohort, but vendor 2's zero is an outage instead of a quiet month.
    holed = {b: v for b, v in values.items() if b != 2}
    out_without = mb.compare(
        _measured(holed, unmeasured={2: 'linkedin collection failed'},
                  eligible=set(values)), 1)

    assert out_with_zero['market_peer_count'] == 5
    assert out_without['market_peer_count'] == 4 or out_without['suppressed']
    # The observed zero pulls the median down; the outage must not.
    assert out_with_zero['market_median'] == 4.0


def test_mm29_an_unmeasured_selected_vendor_is_not_plotted_at_zero():
    values = {b: float(b) for b in range(2, 12)}
    out = mb.compare(
        _measured(values, unmeasured={1: 'no LinkedIn URL on file'},
                  eligible=set(values) | {1}), 1)

    assert out['vendor_value'] is None
    assert out['vendor_percentile'] is None
    assert out['vendor_unmeasured_because'] == 'no LinkedIn URL on file'
    assert any('Vendor not measured' in n for n in out['notes'])
    # The market is still described. Not knowing this vendor's value is no
    # reason to withhold the cohort it would have been compared with.
    assert out['market_median'] is not None


def test_a_zero_denominator_gives_an_absolute_delta_and_says_why():
    """Infinity renders as a very confident number. It must never be shown."""
    values = {1: 5.0, **{b: 0.0 for b in range(2, 9)}}
    out = mb.compare(_measured(values), 1)

    assert out['market_median'] == 0
    assert out['delta_from_market_median'] == 5.0
    assert out['percentage_delta_from_market_median'] is None
    assert any('Percentage comparison unavailable' in n for n in out['notes'])


# ---------------------------------------------------------------------------
# Identity restriction (MM-30)
# ---------------------------------------------------------------------------

def test_mm30_a_restricted_caller_gets_the_aggregates_and_no_names(conn, market):
    """MM-30. The cohort members are absent from the payload, not hidden in it.

    A name that reaches the browser has been disclosed whatever the browser
    chooses to render, so the test is on the response, not on the UI.
    """
    row = conn.execute(text("SELECT * FROM bw_markets WHERE id = :m"),
                       {'m': market}).mappings().first()
    brand_id = conn.execute(text("""
        SELECT mb.brand_id FROM bw_market_brands mb
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
         ORDER BY mb.brand_id LIMIT 1
    """), {'m': market}).scalar()
    if brand_id is None:
        pytest.skip('no vendors in this market')

    restricted = mb.benchmarks(conn, dict(row), int(brand_id), days=30,
                               metric_keys=['posts'], include_cohort=False)
    assert restricted['cohort_named'] is False
    assert all('cohort' not in m for m in restricted['metrics'])
    body = repr(restricted)
    names = [n for (n,) in conn.execute(text("""
        SELECT b.display_name FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
           AND mb.brand_id <> :b
    """), {'m': market, 'b': brand_id}).fetchall()]
    leaked = [n for n in names if n and n in body]
    assert not leaked, f'peer identities in a restricted payload: {leaked[:5]}'

    full = mb.benchmarks(conn, dict(row), int(brand_id), days=30,
                         metric_keys=['posts'], include_cohort=True)
    assert full['cohort_named'] is True
    if not full['metrics'][0]['suppressed']:
        assert full['metrics'][0]['cohort']
    # Same numbers either way. Restricting identities must not restrict truth.
    for field in ('market_median', 'market_average', 'top_median',
                  'vendor_percentile'):
        assert restricted['metrics'][0][field] == full['metrics'][0][field]


# ---------------------------------------------------------------------------
# Degraded sources (MM-31)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('state', ['failed', 'stale'])
def test_mm31_a_degraded_source_keeps_the_last_good_reading_and_warns(state):
    """MM-31. Do not recalculate from whoever happened to refresh.

    If today's run reached twelve of eighty-four vendors, a median of those
    twelve is a median of the vendors whose collectors were working, which is
    not a property of the market. The last good cohort is kept, the date it was
    good is stated, and the reader is told the reading is not current.
    """
    values = {b: float(b) for b in range(1, 21)}
    out = mb.compare(
        _measured(values, degraded=True, state=state,
                  as_of='2026-08-20T09:00:00+02:00'), 1)

    assert out['degraded'] is True
    assert out['market_median'] is not None
    assert out['as_of'] == '2026-08-20T09:00:00+02:00'
    warning = next(n for n in out['notes'] if 'not current' in n)
    assert '2026-08-20T09:00:00+02:00' in warning


@pytest.mark.parametrize('state', ['failed', 'never_collected',
                                   'not_configured', 'collecting'])
def test_mm31_a_source_that_never_succeeded_has_no_last_good_to_keep(state):
    """The other half of the rule, and the half that is easy to get wrong.

    ``failed`` is a state a source can be in on its first run and on its
    thousandth. On the first there is nothing to retain and every vendor is
    unmeasured; on the thousandth there are 999 good readings and dropping them
    would recompute the market from whoever refreshed today. The state name
    cannot tell those apart. ``last_success_at`` can.
    """
    assert mb.retains_last_good(
        {'state': state, 'freshness': {'last_success_at': None}}) is False


def test_mm31_a_failed_run_after_a_good_one_keeps_the_good_one():
    """The case the state name alone gets backwards."""
    good = {'last_success_at': '2026-08-20T09:00:00+02:00'}
    assert mb.retains_last_good({'state': 'failed', 'freshness': good}) is True
    assert mb.retains_last_good({'state': 'stale', 'freshness': good}) is True
    # A healthy source is not degraded even though it has succeeded.
    assert mb.retains_last_good({'state': 'healthy', 'freshness': good}) is False
    assert mb.retains_last_good({'state': 'partial', 'freshness': good}) is False


# ---------------------------------------------------------------------------
# Every metric keeps its own clock
# ---------------------------------------------------------------------------

def test_a_level_is_never_described_as_a_thirty_day_flow():
    """Observed jobs and headcount are as-of levels, not period flows.

    The page defaults to thirty days, and labelling "32 open roles" as a
    thirty-day figure would turn a standing count into a hiring rate.
    """
    for key in ('headcount', 'jobs_open', 'jobs_new', 'funding'):
        assert mb.METRICS[key]['window'] == 'as_of'
        assert mb.METRICS[key].get('as_of_note')
    for key in ('posts', 'mentions', 'announcements', 'headcount_pct'):
        assert mb.METRICS[key]['window'] == 'period'


def test_every_benchmark_metric_is_reachable_and_shaped(conn, market):
    """Each declared metric must actually compute against a real market."""
    row = dict(conn.execute(text("SELECT * FROM bw_markets WHERE id = :m"),
                            {'m': market}).mappings().first())
    for key in mb.METRICS:
        measured = mb.metric_values(conn, row, key, 30)
        assert set(measured) >= {'values', 'unmeasured', 'eligible',
                                 'collection', 'spec', 'degraded'}
        # No vendor may be in both. A value and a reason not to have one are
        # contradictory, and whichever the UI reads first would be arbitrary.
        assert not (set(measured['values']) & set(measured['unmeasured']))
        assert set(measured['values']) <= set(measured['eligible'])
