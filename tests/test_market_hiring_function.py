"""ATS postings classify by department; they are not "not stated".

Greenhouse and Lever boards leave ``function`` empty and carry the
department in ``function_hint``. The hiring analysis read only the former,
so every posting from an ATS-collected vendor (Dropzone AI: 12 of 12,
Qevlar: 15 of 17) grouped as "not stated" while LinkedIn-collected vendors
classified fine.
"""

import pytest
from sqlalchemy import text

from app.services.market_analysis import _group_function, hiring


@pytest.mark.parametrize("hint, group", [
    ("Sales", "sales"),
    ("Engineering", "engineering"),
    ("Security research", "engineering"),
    ("Operations", "operations"),
    ("Product", "marketing"),
    ("Marketing", "marketing"),
    ("", "not stated"),
    (None, "not stated"),
])
def test_ats_department_hints_land_in_a_group(hint, group):
    assert _group_function(hint) == group


def test_ats_postings_with_a_hint_are_never_not_stated():
    from app.database import get_database_instance
    try:
        conn = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    try:
        market = conn.execute(text(
            "SELECT market_id FROM bw_vendor_snapshots WHERE snapshot_type='job_posting' "
            "AND source LIKE 'ats%' AND data->>'function_hint' IS NOT NULL LIMIT 1")).scalar()
        if market is None:
            pytest.skip("no ATS job postings in this database")
        hinted = {r[0] for r in conn.execute(text("""
            SELECT DISTINCT s.brand_id FROM bw_vendor_snapshots s
            JOIN bw_market_brands mb ON mb.brand_id = s.brand_id AND mb.market_id = :m
            WHERE s.snapshot_type='job_posting' AND s.source LIKE 'ats%'
              AND COALESCE(s.data->>'function','') = ''
              AND COALESCE(s.data->>'function_hint','') <> ''
        """), {"m": market})}
        result = hiring(conn, market)
        for vendor in result["by_vendor"]:
            if vendor.get("brand_id") in hinted:
                assert "not stated" not in vendor["by_function"], vendor
    finally:
        conn.rollback()
        conn.close()
