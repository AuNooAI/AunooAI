"""Retry selection is fair and capped in SQL (WP5c / M4). CDQ_DB_TESTS=1."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(os.getenv("CDQ_DB_TESTS") != "1", reason="set CDQ_DB_TESTS=1")
PFX = "pytest-retry:"


@pytest.fixture
def db():
    from app.database import get_database_instance
    d = get_database_instance()
    yield d
    c = d._temp_get_connection()
    c.execute(text("DELETE FROM articles WHERE uri LIKE :p"), {"p": PFX + "%"})
    c.commit()
    c.close()


def _add(conn, uri, status, seen, **kw):
    row = dict(uri=PFX + uri, title="t", summary="s", topic="pytest", ingest_status=status, first_seen_at=seen)
    row.update(kw)
    conn.execute(text(f"INSERT INTO articles ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"), row)


def test_capped_newest_rows_cannot_starve_an_older_eligible_failure(db):
    from app.tasks.enrichment_retry_sweep import _fetch_waiting_rows, max_attempts
    now = datetime.now(timezone.utc)
    conn = db._temp_get_connection()
    for i in range(30):
        _add(conn, f"capped{i}", "enrichment_failed", now - timedelta(minutes=i),
             enrichment_attempts=max_attempts())
    _add(conn, "old-eligible", "enrichment_failed", now - timedelta(days=20), enrichment_attempts=1)
    _add(conn, "relevance-due", "relevance_check_failed", now - timedelta(days=2), relevance_attempts=1,
         relevance_next_retry_at=now - timedelta(minutes=5))
    _add(conn, "relevance-later", "relevance_check_failed", now - timedelta(days=3), relevance_attempts=1,
         relevance_next_retry_at=now + timedelta(hours=2))
    _add(conn, "relevance-exhausted", "relevance_check_failed", now - timedelta(days=4), relevance_attempts=99)
    conn.commit()
    conn.close()
    got = [r["uri"] for r in _fetch_waiting_rows(db, 500) if r["uri"].startswith(PFX)]
    assert PFX + "old-eligible" in got and PFX + "relevance-due" in got
    assert not any("capped" in u for u in got)
    assert PFX + "relevance-later" not in got and PFX + "relevance-exhausted" not in got


def test_overlapping_sweeps_skip(db):
    import asyncio
    from app.tasks import enrichment_retry_sweep as s
    held = s._try_lock(db)
    assert held
    try:
        out = asyncio.new_event_loop().run_until_complete(s.sweep_once(db, configs={}, record=False))
        assert out == {"skipped": "locked"}
    finally:
        held.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": s._SWEEP_LOCK_KEY})
        held.close()
