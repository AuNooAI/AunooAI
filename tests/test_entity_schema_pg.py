"""The schema guarantees that only PostgreSQL can prove.

Everything here runs inside one transaction that is always rolled back, so the
tests exercise the real indexes and foreign keys without leaving a row behind.
Nothing in this file commits.

The first test is the reason the file exists. Review tasks for entity-global
problems — an identity dispute, a field conflict — have no market, and a
unique index containing a nullable ``market_id`` deduplicates nothing for
those rows, because PostgreSQL treats null indexed values as distinct. That is
not a rule you can check by reading the DDL and believing you understood it,
so it is checked by inserting the same task twice and counting.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='entity schema guarantees are PostgreSQL-specific')


@pytest.fixture()
def conn():
    """A connection whose work is always thrown away."""
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_observations')")).scalar() is None:
        connection.close()
        pytest.skip('ei_001 has not been applied to this database')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def brand(conn):
    """A throwaway entity, rolled back with everything else."""
    return conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-entity-fixture', 'Pytest Entity Fixture',
                '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()


@pytest.fixture()
def market(conn):
    return conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('Pytest Market', 'pytest-market')
        RETURNING id
    """)).scalar()


def _task(conn, *, market_id, brand_id, message='same problem, twice'):
    from app.services.entity_review import open_task
    return open_task(conn, kind='field_conflict', message=message,
                     brand_id=brand_id, market_id=market_id,
                     field='employee_count')


# ---------------------------------------------------------------------------
# Review-task dedup
# ---------------------------------------------------------------------------

def test_entity_global_task_deduplicates(conn, brand):
    """No market, filed twice, one row. Without the partial index this is two,
    and the queue grows by one on every resolver pass."""
    first = _task(conn, market_id=None, brand_id=brand)
    second = _task(conn, market_id=None, brand_id=brand)
    assert first is not None
    assert second is None

    count = conn.execute(text("""
        SELECT count(*) FROM bw_review_tasks
         WHERE brand_id = :b AND market_id IS NULL
    """), {'b': brand}).scalar()
    assert count == 1


def test_market_scoped_task_still_deduplicates(conn, brand, market):
    assert _task(conn, market_id=market, brand_id=brand) is not None
    assert _task(conn, market_id=market, brand_id=brand) is None
    count = conn.execute(text("""
        SELECT count(*) FROM bw_review_tasks WHERE brand_id = :b AND market_id = :m
    """), {'b': brand, 'm': market}).scalar()
    assert count == 1


def test_the_same_problem_in_two_scopes_is_two_tasks(conn, brand, market):
    """A market's own copy of a problem and the entity-wide one are different
    tasks for different people, so they must not collapse into each other."""
    assert _task(conn, market_id=None, brand_id=brand) is not None
    assert _task(conn, market_id=market, brand_id=brand) is not None
    total = conn.execute(text("""
        SELECT count(*) FROM bw_review_tasks WHERE brand_id = :b
    """), {'b': brand}).scalar()
    assert total == 2


def test_review_task_market_id_is_nullable(conn):
    nullable = conn.execute(text("""
        SELECT is_nullable FROM information_schema.columns
         WHERE table_name = 'bw_review_tasks' AND column_name = 'market_id'
    """)).scalar()
    assert nullable == 'YES'


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

def test_the_same_provider_record_observed_twice_is_one_observation(conn, brand):
    """A callback retry, a re-run backfill, the same snapshot reached through
    two markets: all the same assertion, and none of them a second reading."""
    from app.services.entity_observations import record_observation
    from datetime import datetime, timezone

    when = datetime(2026, 8, 1, tzinfo=timezone.utc)
    kwargs = dict(brand_id=brand, field_key='employee_count', value=296,
                  source='linkedin_company_profile',
                  source_record_id='snapshot:id=999', observed_at=when)
    first = record_observation(conn, **kwargs)
    second = record_observation(conn, **kwargs)
    assert first is not None
    assert second is None


def test_a_changed_reading_is_a_new_observation(conn, brand):
    """Same source record, different value: that is news, and both readings
    stay so the series has two points rather than one overwritten one."""
    from app.services.entity_observations import record_observation
    from datetime import datetime, timezone

    when = datetime(2026, 8, 1, tzinfo=timezone.utc)
    base = dict(brand_id=brand, field_key='employee_count',
                source='linkedin_company_profile',
                source_record_id='snapshot:id=1000', observed_at=when)
    assert record_observation(conn, value=296, **base) is not None
    assert record_observation(conn, value=310, **base) is not None
    count = conn.execute(text("""
        SELECT count(*) FROM bw_entity_observations
         WHERE brand_id = :b AND field_key = 'employee_count'
    """), {'b': brand}).scalar()
    assert count == 2


def test_a_null_reading_writes_nothing(conn, brand):
    """The provider did not answer. That is not a value, and it must not be
    able to displace one."""
    from app.services.entity_observations import record_observation
    from datetime import datetime, timezone

    result = record_observation(
        conn, brand_id=brand, field_key='employee_count', value=None,
        source='linkedin_company_profile', source_record_id='snapshot:id=1001',
        observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert result is None


def test_a_source_the_field_forbids_is_refused(conn, brand):
    """Crunchbase carries no funding total, so it may not assert one."""
    from app.services.entity_observations import (
        NormalizationError, record_observation)
    from datetime import datetime, timezone

    with pytest.raises(NormalizationError):
        record_observation(
            conn, brand_id=brand, field_key='funding_total_musd', value=105.0,
            source='crunchbase_company', source_record_id='snapshot:id=1002',
            observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc))


def test_scope_mismatch_is_refused(conn, brand, market):
    """Taxonomy without a market, or a company fact with one, is a bug in the
    caller rather than something to store and sort out later."""
    from app.services.entity_observations import (
        NormalizationError, record_observation)
    from datetime import datetime, timezone

    when = datetime(2026, 8, 1, tzinfo=timezone.utc)
    with pytest.raises(NormalizationError):
        record_observation(conn, brand_id=brand, field_key='market_category',
                           value='AI Security', source='workbook',
                           source_record_id='import:row=1', observed_at=when)
    with pytest.raises(NormalizationError):
        record_observation(conn, brand_id=brand, field_key='employee_count',
                           value=10, source='workbook', market_id=market,
                           source_record_id='import:row=1', observed_at=when)


# ---------------------------------------------------------------------------
# Resolution against the real tables
# ---------------------------------------------------------------------------

def test_a_better_source_takes_over_from_the_import(conn, brand):
    """Workbook 180, LinkedIn 296, verified PitchBook 310. The canonical value
    is 310, the reason names the source, and all three readings survive."""
    from datetime import datetime, timedelta, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    now = datetime.now(timezone.utc)
    record_observation(conn, brand_id=brand, field_key='employee_count',
                       value=180, source='workbook',
                       source_record_id='import:row=5',
                       observed_at=now - timedelta(days=120))
    record_observation(conn, brand_id=brand, field_key='employee_count',
                       value=296, source='linkedin_company_profile',
                       source_record_id='snapshot:id=2001',
                       observed_at=now - timedelta(days=10))
    record_observation(conn, brand_id=brand, field_key='employee_count',
                       value=310, source='pitchbook_company',
                       source_record_id='snapshot:id=2002',
                       observed_at=now - timedelta(days=2),
                       metadata={'verified': True})

    result = resolve_field(conn, brand, 'employee_count', trigger='backfill')
    assert result['status'] == 'current'
    assert 'pitchbook_company' in result['reason']

    value = conn.execute(text("""
        SELECT value_number FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'employee_count'
           AND market_id IS NULL
    """), {'b': brand}).scalar()
    assert int(value) == 310

    surviving = conn.execute(text("""
        SELECT count(*) FROM bw_entity_observations
         WHERE brand_id = :b AND field_key = 'employee_count'
    """), {'b': brand}).scalar()
    assert surviving == 3


def test_resolving_twice_moves_nothing_and_logs_once(conn, brand):
    """Replay has to be free. A second pass over unchanged observations must
    not write a second log row, or the audit trail becomes noise."""
    from datetime import datetime, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    record_observation(conn, brand_id=brand, field_key='hq_country',
                       value='Israel', source='workbook',
                       source_record_id='import:row=9',
                       observed_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    first = resolve_field(conn, brand, 'hq_country', trigger='backfill')
    second = resolve_field(conn, brand, 'hq_country', trigger='backfill')
    assert first['changed'] is True
    assert second['changed'] is False

    logged = conn.execute(text("""
        SELECT count(*) FROM bw_entity_resolution_log
         WHERE brand_id = :b AND field_key = 'hq_country'
    """), {'b': brand}).scalar()
    assert logged == 1


def test_a_funding_total_does_not_fall_on_its_own(conn, brand):
    """Totals accumulate. A smaller figure is a correction or a mistake, and
    telling those apart is a person's job, so the larger value is held and a
    task is filed."""
    from datetime import datetime, timedelta, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    now = datetime.now(timezone.utc)
    record_observation(conn, brand_id=brand, field_key='funding_total_musd',
                       value=105.0, source='pitchbook_company',
                       source_record_id='snapshot:id=3001',
                       observed_at=now - timedelta(days=30),
                       metadata={'verified': True})
    resolve_field(conn, brand, 'funding_total_musd', trigger='backfill')

    record_observation(conn, brand_id=brand, field_key='funding_total_musd',
                       value=45.0, source='pitchbook_company',
                       source_record_id='snapshot:id=3002',
                       observed_at=now, metadata={'verified': True})
    result = resolve_field(conn, brand, 'funding_total_musd', trigger='ingest')

    assert result['changed'] is False
    held = conn.execute(text("""
        SELECT value_number FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'funding_total_musd'
    """), {'b': brand}).scalar()
    assert float(held) == 105.0

    task = conn.execute(text("""
        SELECT count(*) FROM bw_review_tasks
         WHERE brand_id = :b AND kind = 'field_decrease' AND status = 'open'
    """), {'b': brand}).scalar()
    assert task == 1


def test_a_canonical_observation_cannot_be_deleted(conn, brand):
    """A canonical row pointing at nothing is worse than a wrong value, so the
    foreign key refuses. Retract the observation instead."""
    from datetime import datetime, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    obs_id = record_observation(
        conn, brand_id=brand, field_key='industry', value='Computer Security',
        source='linkedin_company_profile', source_record_id='snapshot:id=4001',
        observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    resolve_field(conn, brand, 'industry', trigger='backfill')

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        conn.execute(text("DELETE FROM bw_entity_observations WHERE id = :i"),
                     {'i': obs_id})
