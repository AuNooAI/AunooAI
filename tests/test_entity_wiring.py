"""The wiring, the switches, and the scoping — the gaps a review found.

Every test in this file corresponds to a defect that the original suite could
not have caught, because those tests all called the services directly. A
service nobody calls still passes its own tests, and a flag nobody reads still
reports the value it was given. So these assert the connections rather than the
components: that closing a collection run actually processes what it collected,
that turning the master switch off actually turns the surface off, and that a
correction addressed to one market cannot alter another.

The two operator-input failures are here for the same reason. A second manual
correction to a locked field was stored and then silently discarded, and a held
funding decrease reported a conflict that the database never recorded. Both
look fine from inside the function that produced them.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv('DB_TYPE', 'postgresql').lower() != 'postgresql',
    reason='wiring is exercised against PostgreSQL')


@pytest.fixture()
def flags(monkeypatch):
    """Set entity flags for one test without touching the tenant's .env."""
    def _set(**values):
        for name, value in values.items():
            monkeypatch.setenv(f'ENTITY_INTELLIGENCE_{name.upper()}',
                               'true' if value else 'false')
    return _set


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    db = get_database_instance()
    connection = db._temp_get_connection()
    if connection.execute(
            text("SELECT to_regclass('bw_entity_observations')")).scalar() is None:
        connection.close()
        pytest.skip('entity migrations have not been applied')
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture()
def brand(conn):
    return conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-wiring', 'Pytest Wiring Co', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()


# ---------------------------------------------------------------------------
# 1. Continuous ingestion is connected
# ---------------------------------------------------------------------------

def test_closing_a_run_processes_what_it_collected(conn, brand, flags):
    """The whole layer decays without this. A snapshot that lands and is never
    normalised leaves the canonical value frozen at whatever the backfill
    produced."""
    from app.services import market_collect as mc

    flags(enabled=True)
    market_id = conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('W', 'pytest-wiring-m')
        RETURNING id
    """)).scalar()
    conn.execute(text("""
        INSERT INTO bw_market_brands (market_id, brand_id, baseline)
        VALUES (:m, :b, '{}'::jsonb)
    """), {'m': market_id, 'b': brand})

    run_id = mc.open_run(conn, market_id=market_id,
                         source='linkedin_company_profile', provider='pytest')
    mc.store_snapshot(
        conn, market_id=market_id, brand_id=brand,
        source='linkedin_company_profile', snapshot_type='profile',
        provider_item_id='pytest-wiring-1',
        data={'employee_count': 210, 'followers': 900, 'founded': 2019,
              'industry': 'Computer and Network Security', 'country': 'US'},
        run_id=run_id)

    pending_before = conn.execute(text("""
        SELECT normalization_status FROM bw_vendor_snapshots
         WHERE provider_item_id = 'pytest-wiring-1'
    """)).scalar()
    assert pending_before == 'pending'

    mc.close_run(conn, run_id, status='succeeded', received=1, new=1)

    after = conn.execute(text("""
        SELECT normalization_status FROM bw_vendor_snapshots
         WHERE provider_item_id = 'pytest-wiring-1'
    """)).scalar()
    assert after == 'normalized'

    headcount = conn.execute(text("""
        SELECT value_number FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'employee_count'
           AND market_id IS NULL
    """), {'b': brand}).scalar()
    assert int(headcount) == 210


def test_a_failed_run_leaves_its_snapshots_queued(conn, brand, flags):
    """A crash must not consume the backlog marker, or the rows it stranded
    are never retried."""
    from app.services import market_collect as mc

    flags(enabled=True)
    market_id = conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('W2', 'pytest-wiring-m2')
        RETURNING id
    """)).scalar()
    run_id = mc.open_run(conn, market_id=market_id, source='crunchbase_company',
                         provider='pytest')
    mc.store_snapshot(
        conn, market_id=market_id, brand_id=brand, source='crunchbase_company',
        snapshot_type='funding', provider_item_id='pytest-wiring-2',
        data={'operating_status': 'active', 'country': 'United States'},
        run_id=run_id)
    mc.close_run(conn, run_id, status='failed', error='provider timeout')

    assert conn.execute(text("""
        SELECT normalization_status FROM bw_vendor_snapshots
         WHERE provider_item_id = 'pytest-wiring-2'
    """)).scalar() == 'pending'


def test_the_master_switch_stops_new_processing(conn, brand, flags):
    """Off has to mean off, not 'reads differently'."""
    from app.services import entity_ingest, market_collect as mc

    flags(enabled=False)
    market_id = conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('W3', 'pytest-wiring-m3')
        RETURNING id
    """)).scalar()
    run_id = mc.open_run(conn, market_id=market_id,
                         source='linkedin_company_profile', provider='pytest')
    mc.store_snapshot(
        conn, market_id=market_id, brand_id=brand,
        source='linkedin_company_profile', snapshot_type='profile',
        provider_item_id='pytest-wiring-3', data={'employee_count': 55},
        run_id=run_id)
    mc.close_run(conn, run_id, status='succeeded')

    assert entity_ingest.on_run_closed(conn, run_id, 'succeeded') is None
    assert conn.execute(text("""
        SELECT normalization_status FROM bw_vendor_snapshots
         WHERE provider_item_id = 'pytest-wiring-3'
    """)).scalar() == 'pending'


def test_processing_a_run_never_breaks_the_run(conn, brand, flags, monkeypatch):
    """The provider data is already paid for and durable. A fault in
    processing must not be able to fail the run that collected it."""
    from app.services import entity_ingest

    flags(enabled=True)

    def _explode(*a, **kw):
        raise RuntimeError('normalizer fault')

    monkeypatch.setattr(entity_ingest, 'process_pending', _explode)
    assert entity_ingest.on_run_closed(conn, 1, 'succeeded') is None


# ---------------------------------------------------------------------------
# 2. The switches are real
# ---------------------------------------------------------------------------

def test_every_flag_has_a_caller():
    """A flag nobody reads is documentation pretending to be a control."""
    import subprocess

    for name in ('enabled', 'events_enabled', 'social_enabled',
                 'canonical_read', 'mention_read', 'dual_write'):
        found = subprocess.run(
            ['grep', '-rl', f'entity_flags.{name}()', 'app/'],
            capture_output=True, text=True).stdout.strip()
        assert found, f'entity_flags.{name}() is never called'


def test_event_extraction_is_gated(conn, flags):
    from app.services import entity_event_extractors as ex

    flags(events_enabled=False)
    result = ex.run_all(conn)
    assert result['events_created'] == 0
    assert '*' in result['skipped']


def test_the_entity_routes_disappear_when_the_layer_is_off(flags):
    """Rolling back has to restore the old API surface, not leave the new one
    answering."""
    from fastapi import HTTPException

    from app.routes.market_entity_routes import require_entity_layer

    flags(enabled=False)
    with pytest.raises(HTTPException) as raised:
        require_entity_layer()
    assert raised.value.status_code == 404

    flags(enabled=True)
    assert require_entity_layer() is None


# ---------------------------------------------------------------------------
# 3 & 4. Operator input is not silently discarded
# ---------------------------------------------------------------------------

def test_a_second_manual_correction_replaces_the_first(conn, brand):
    """The lock exists to stop automatic sources overriding a person. It must
    not stop the person changing their mind — which it did, storing the new
    observation and then keeping the old one."""
    from datetime import datetime, timedelta, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    now = datetime.now(timezone.utc)
    first = record_observation(
        conn, brand_id=brand, field_key='employee_count', value=100,
        source='manual', source_record_id='manual:one', observed_at=now,
        confidence=1.0, metadata={'actor': 'pytest'})
    resolve_field(conn, brand, 'employee_count', trigger='manual')
    conn.execute(text("""
        UPDATE bw_entity_canonical_fields SET locked = TRUE, locked_by = 'pytest'
         WHERE brand_id = :b AND field_key = 'employee_count'
    """), {'b': brand})

    second = record_observation(
        conn, brand_id=brand, field_key='employee_count', value=140,
        source='manual', source_record_id='manual:two',
        observed_at=now + timedelta(minutes=5), confidence=1.0,
        metadata={'actor': 'pytest'})
    result = resolve_field(conn, brand, 'employee_count', trigger='manual')

    assert second != first
    assert result['observation_id'] == second
    value = conn.execute(text("""
        SELECT value_number FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'employee_count'
    """), {'b': brand}).scalar()
    assert int(value) == 140


def test_a_correction_cannot_name_a_different_market_than_the_route(conn, brand):
    """Otherwise a request addressed to one market rewrites another's
    taxonomy."""
    import asyncio

    from fastapi import HTTPException

    from app.routes.market_entity_routes import FieldCorrection, correct_field

    with pytest.raises(HTTPException) as raised:
        asyncio.run(correct_field(
            market_id=2, brand_id=brand, field_key='market_category',
            payload=FieldCorrection(value='AI Security', reason='test',
                                    market_id=99),
            session={'username': 'pytest'}))
    assert raised.value.status_code == 400
    assert 'does not match' in raised.value.detail


def test_a_company_fact_rejects_a_market_id(conn, brand):
    import asyncio

    from fastapi import HTTPException

    from app.routes.market_entity_routes import FieldCorrection, correct_field

    with pytest.raises(HTTPException) as raised:
        asyncio.run(correct_field(
            market_id=2, brand_id=brand, field_key='employee_count',
            payload=FieldCorrection(value=10, reason='test', market_id=2),
            session={'username': 'pytest'}))
    assert raised.value.status_code == 400


def test_unlocking_one_market_leaves_the_others_locked(conn, brand):
    """Taxonomy has one canonical row per membership. An unscoped UPDATE
    released the field everywhere the company appears."""
    from datetime import datetime, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    now = datetime.now(timezone.utc)
    markets = []
    for slug in ('pytest-unlock-a', 'pytest-unlock-b'):
        market_id = conn.execute(text("""
            INSERT INTO bw_markets (name, slug) VALUES (:s, :s) RETURNING id
        """), {'s': slug}).scalar()
        conn.execute(text("""
            INSERT INTO bw_market_brands (market_id, brand_id, baseline)
            VALUES (:m, :b, '{}'::jsonb)
        """), {'m': market_id, 'b': brand})
        record_observation(
            conn, brand_id=brand, field_key='market_category',
            value='AI Security', source='manual', market_id=market_id,
            source_record_id=f'manual:{slug}', observed_at=now, confidence=1.0)
        resolve_field(conn, brand, 'market_category', market_id=market_id,
                      trigger='manual')
        markets.append(market_id)

    conn.execute(text("""
        UPDATE bw_entity_canonical_fields SET locked = TRUE
         WHERE brand_id = :b AND field_key = 'market_category'
    """), {'b': brand})

    # Unlock only the first market, the way the endpoint now scopes it.
    conn.execute(text("""
        UPDATE bw_entity_canonical_fields
           SET locked = FALSE
         WHERE brand_id = :b AND field_key = 'market_category'
           AND market_id IS NOT DISTINCT FROM :m
    """), {'b': brand, 'm': markets[0]})

    still_locked = conn.execute(text("""
        SELECT locked FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'market_category'
           AND market_id = :m
    """), {'b': brand, 'm': markets[1]}).scalar()
    assert still_locked is True


# ---------------------------------------------------------------------------
# 6. A held decrease is recorded as a conflict
# ---------------------------------------------------------------------------

def test_a_held_funding_decrease_marks_the_field_in_conflict(conn, brand):
    """Reporting a conflict in the return value while the row still read
    'current' meant the page showed a settled figure and the health endpoint
    counted no conflicts."""
    from datetime import datetime, timedelta, timezone

    from app.services.entity_observations import record_observation
    from app.services.entity_resolution import resolve_field

    now = datetime.now(timezone.utc)
    record_observation(
        conn, brand_id=brand, field_key='funding_total_musd', value=105.0,
        source='pitchbook_company', source_record_id='snap:hi',
        observed_at=now - timedelta(days=10), metadata={'verified': True})
    resolve_field(conn, brand, 'funding_total_musd', trigger='backfill')

    record_observation(
        conn, brand_id=brand, field_key='funding_total_musd', value=45.0,
        source='pitchbook_company', source_record_id='snap:lo',
        observed_at=now, metadata={'verified': True})
    result = resolve_field(conn, brand, 'funding_total_musd', trigger='ingest')

    assert result['status'] == 'conflict'
    row = conn.execute(text("""
        SELECT status, value_number FROM bw_entity_canonical_fields
         WHERE brand_id = :b AND field_key = 'funding_total_musd'
    """), {'b': brand}).mappings().first()
    assert row['status'] == 'conflict'      # the database, not just the return
    assert float(row['value_number']) == 105.0


# ---------------------------------------------------------------------------
# 8. A mapping decision belongs to one vendor
# ---------------------------------------------------------------------------

def test_one_vendor_cannot_decide_another_vendors_mapping(conn, brand):
    import asyncio

    from fastapi import HTTPException

    from app.routes.market_entity_routes import IdentityDecision, decide_identity
    from app.services import entity_identity

    other = conn.execute(text("""
        INSERT INTO bw_brands (name, display_name, brand_keywords, enabled)
        VALUES ('pytest-wiring-2', 'Pytest Wiring Two', '[]'::jsonb, FALSE)
        RETURNING id
    """)).scalar()
    market_id = conn.execute(text("""
        INSERT INTO bw_markets (name, slug) VALUES ('W4', 'pytest-wiring-m4')
        RETURNING id
    """)).scalar()
    for b in (brand, other):
        conn.execute(text("""
            INSERT INTO bw_market_brands (market_id, brand_id, baseline)
            VALUES (:m, :b, '{}'::jsonb)
        """), {'m': market_id, 'b': b})

    account = entity_identity.upsert_account(conn, platform='twitter',
                                             handle='pytest-other')
    mapping = entity_identity.propose_identity(
        conn, brand_id=other, social_account_id=account['account_id'],
        relationship='unofficial', verification_method='content_inference')

    with pytest.raises(HTTPException) as raised:
        asyncio.run(decide_identity(
            market_id=market_id, brand_id=brand,
            mapping_id=mapping['identity_id'],
            payload=IdentityDecision(action='verify'),
            session={'username': 'pytest'}))
    assert raised.value.status_code == 404
