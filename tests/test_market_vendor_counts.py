"""Acquired vendors drop out of every vendor count.

A vendor marked ``acquired`` on the horizon controls is no longer an
independent vendor. The test marks one inside a transaction that is always
rolled back, so nothing it does survives.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services import market_publish as mp


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    c = get_database_instance()._temp_get_connection()
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _a_live_vendor(conn):
    row = conn.execute(text(f"""
        SELECT mb.market_id, mb.brand_id FROM bw_market_brands mb
         WHERE mb.role = 'vendor' AND mb.collection_enabled
           AND NOT {mp.is_acquired("mb")}
         ORDER BY mb.market_id, mb.brand_id LIMIT 1
    """)).first()
    if row is None:
        pytest.skip("no live vendor in this database")
    return int(row[0]), int(row[1])


def test_coverage_parts_add_up_to_the_registry(conn):
    market_id, _ = _a_live_vendor(conn)
    cov = mp._vendor_coverage(conn, market_id)
    assert cov["registry"] == (cov["excluded"] + cov["acquired"]
                               + cov["watching"] + cov["paused"])
    assert cov["vendors"] == cov["watching"] + cov["paused"]


def test_marking_a_vendor_acquired_moves_it_out_of_the_counts(conn):
    market_id, brand_id = _a_live_vendor(conn)
    before = mp._vendor_coverage(conn, market_id)
    conn.execute(text("""
        INSERT INTO bw_market_vendor_controls
            (market_id, brand_id, multipliers, status, acquired_by, updated_at)
        VALUES (:m, :b, '{}'::jsonb, 'acquired', 'Test Buyer', NOW())
        ON CONFLICT (market_id, brand_id) DO UPDATE SET status = 'acquired'
    """), {"m": market_id, "b": brand_id})
    after = mp._vendor_coverage(conn, market_id)
    assert after["vendors"] == before["vendors"] - 1
    assert after["watching"] == before["watching"] - 1
    assert after["acquired"] == before["acquired"] + 1
    assert brand_id in mp.acquired_ids(conn, market_id)
