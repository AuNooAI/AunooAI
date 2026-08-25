"""The cutover check: reading a field both ways and classifying the difference.

The risk this guards is quiet. Vendor filters read the imported workbook today
and should read the resolved value; flip that without looking and a "fewer than
ten staff" filter silently returns a different set of companies, which nobody
notices until a customer asks where a vendor went.

The classification is the substance. A value that changed is usually the system
working — a newer source displaced the import. A value that *disappeared* is
the only class that can shrink a result set, and even then it matters whether
what disappeared was a real number or a zero standing in for a blank cell.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.services import entity_dual_read as dr

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='dual read is exercised against PostgreSQL')


# ---------------------------------------------------------------------------
# Expression selection — pure
# ---------------------------------------------------------------------------

def test_the_flag_chooses_which_store_is_read():
    """Rollback has to be a flag and nothing else, so the two sides are the
    same expression picked two ways."""
    assert 'baseline' in dr.expression('employee_count', canonical=False)
    assert dr.expression('employee_count', canonical=True) == 'p.employee_count::numeric'


def test_taxonomy_reads_the_membership_not_the_profile():
    """Category is market-relative and analyst-controlled, so its canonical
    home is the typed membership column, not the entity profile."""
    assert dr.expression('category', canonical=True) == 'mb.category'
    assert dr.expression('hq_country', canonical=True) == 'p.hq_country'


def test_the_profile_join_is_a_left_join():
    """A vendor with no resolved profile must still appear in a list, reading
    as unknown rather than dropping out of it."""
    assert dr.PROFILE_JOIN.strip().upper().startswith('LEFT JOIN')


# ---------------------------------------------------------------------------
# Classification — pure
# ---------------------------------------------------------------------------

def test_a_blank_cell_served_as_zero_is_not_a_lost_value():
    """The workbook writes 0 for an empty headcount. Losing that is the fix."""
    assert dr._is_placeholder_zero('employee_count', 0) is True
    assert dr._is_placeholder_zero('employee_count', 122) is False


def test_a_field_where_zero_is_real_is_never_a_placeholder():
    """A brand-new company page really can have no followers."""
    assert dr._is_placeholder_zero('followers_linkedin', 0) is False


def test_small_numeric_drift_is_within_tolerance():
    read = dr.READS['employee_count']
    assert dr._within(read, 62, 63) is True
    assert dr._within(read, 122, 145) is False


# ---------------------------------------------------------------------------
# Against real data
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_profiles')")).scalar() is None:
        connection.close()
        pytest.skip('ei_001 has not been applied to this database')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_the_comparison_runs_and_accounts_for_every_vendor(conn):
    market_id = conn.execute(text('SELECT id FROM bw_markets ORDER BY id LIMIT 1')).scalar()
    if market_id is None:
        pytest.skip('no market to compare')

    result = dr.compare_market(conn, market_id)
    assert result['vendors'] > 0
    for field, bucket in result['by_field'].items():
        counted = (bucket['same'] + bucket['changed'] + bucket['gained']
                   + bucket['lost'] + bucket['placeholder_dropped']
                   + bucket['within_tolerance'])
        # Every vendor lands in exactly one class for every field, so a
        # difference cannot go unreported by falling between categories.
        assert counted == bucket['compared'], field


def test_only_a_genuinely_lost_value_blocks_the_cutover(conn):
    """Placeholder zeroes disappearing must not hold up a cutover; a real
    value becoming unknown must."""
    market_id = conn.execute(text('SELECT id FROM bw_markets ORDER BY id LIMIT 1')).scalar()
    if market_id is None:
        pytest.skip('no market to compare')
    result = dr.compare_market(conn, market_id)
    assert result['safe_to_cut_over'] == (result['total_lost'] == 0)


def test_both_expressions_are_valid_sql_over_the_same_rows(conn):
    """A comparison that could not run either side would certify nothing."""
    market_id = conn.execute(text('SELECT id FROM bw_markets ORDER BY id LIMIT 1')).scalar()
    if market_id is None:
        pytest.skip('no market to compare')
    for field, read in dr.READS.items():
        for side in (read.legacy, read.canonical):
            value = conn.execute(text(f"""
                SELECT {side} FROM bw_market_brands mb
                {dr.PROFILE_JOIN}
                WHERE mb.market_id = :m LIMIT 1
            """), {'m': market_id}).scalar()
            assert value is None or value is not None, f'{field}/{side}'


def test_a_filter_reads_the_same_rows_both_ways_when_nothing_changed(conn):
    """Fields the two stores agree on must produce identical filter results,
    or the cutover is not a no-op where it should be."""
    from app.routes.market_monitor_routes import VendorFilter, _filter_sql

    market_id = conn.execute(text('SELECT id FROM bw_markets ORDER BY id LIMIT 1')).scalar()
    if market_id is None:
        pytest.skip('no market to compare')

    category = conn.execute(text("""
        SELECT category FROM bw_market_brands
         WHERE market_id = :m AND category IS NOT NULL LIMIT 1
    """), {'m': market_id}).scalar()
    if not category:
        pytest.skip('no taxonomy to filter on')

    def count(canonical: bool) -> int:
        os.environ['ENTITY_INTELLIGENCE_CANONICAL_READ'] = str(canonical).lower()
        try:
            where, params = _filter_sql(VendorFilter(categories=[category]))
            params = dict(params)
            params['m'] = market_id
            return conn.execute(text(f"""
                SELECT count(*) FROM bw_market_brands mb
                {dr.PROFILE_JOIN}
                WHERE mb.market_id = :m AND {where}
            """), params).scalar()
        finally:
            os.environ['ENTITY_INTELLIGENCE_CANONICAL_READ'] = 'false'

    # Taxonomy was backfilled from the same baseline it is compared against,
    # so these must agree exactly.
    assert count(False) == count(True)
