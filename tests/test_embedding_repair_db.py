"""Embedding repair sweep against the tenant database (WP5b / M5).

Writes rows with uri prefix 'pytest-emb:' and deletes them afterwards; runs
only with CDQ_DB_TESTS=1. The encoder is a fake.
"""
import asyncio
import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(os.getenv("CDQ_DB_TESTS") != "1", reason="set CDQ_DB_TESTS=1")

PFX = "pytest-emb:"
VEC = [0.01] * 768


@pytest.fixture
def db(monkeypatch):
    from app.database import get_database_instance
    from app.tasks import embedding_repair as er
    database = get_database_instance()
    # Only our rows: restrict eligibility to the test prefix.
    real = er.eligible_sql
    monkeypatch.setattr(er, "eligible_sql", lambda ref="articles": f"({real(ref)} AND {ref}.uri LIKE '{PFX}%')")
    yield database
    conn = database._temp_get_connection()
    conn.execute(text("DELETE FROM articles WHERE uri LIKE :p"), {"p": PFX + "%"})
    conn.commit()
    conn.close()


def _add(db, name, **kw):
    row = dict(uri=PFX + name, title="Title " + name, summary="A summary long enough to embed.",
               topic="pytest", ingest_status="approved", topic_alignment_score=0.8)
    row.update(kw)
    conn = db._temp_get_connection()
    cols = ", ".join(row)
    conn.execute(text(f"INSERT INTO articles ({cols}) VALUES ({', '.join(':' + c for c in row)})"), row)
    conn.commit()
    conn.close()


def _get(db, name):
    conn = db._temp_get_connection()
    r = conn.execute(text("SELECT embedding IS NOT NULL, embedding_attempts, embedding_last_error, "
                          "embedding_next_retry_at FROM articles WHERE uri = :u"), {"u": PFX + name}).fetchone()
    conn.close()
    return r


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def test_eligible_rows_are_embedded_and_rejected_ones_are_not(db):
    from app.tasks.embedding_repair import repair_once
    _add(db, "news")
    _add(db, "social", ingest_status="social_evaluated", topic_alignment_score=0.6, category=None)
    _add(db, "social-low", ingest_status="social_evaluated", topic_alignment_score=0.2)
    _add(db, "rejected", ingest_status="filtered_relevance", topic_alignment_score=0.1)
    _add(db, "failed", ingest_status="relevance_check_failed", topic_alignment_score=None)
    out = run(repair_once(db, encode=lambda t, b: VEC))
    assert out["stored"] == 2
    assert _get(db, "news")[0] and _get(db, "social")[0]
    assert not _get(db, "social-low")[0] and not _get(db, "rejected")[0] and not _get(db, "failed")[0]


def test_encoder_outage_spends_no_attempts_and_drains_after(db):
    from app.tasks.embedding_repair import repair_once, EncoderUnavailable
    _add(db, "a")
    _add(db, "b")

    def down(t, b):
        raise EncoderUnavailable("ConnectionError: refused")
    out = run(repair_once(db, encode=down))
    assert out["encoder_unavailable"] and out["stored"] == 0
    assert _get(db, "a")[1] is None and _get(db, "b")[1] is None
    out = run(repair_once(db, encode=lambda t, b: VEC))
    assert out["stored"] == 2


def test_a_bad_vector_counts_an_attempt_and_backs_off(db):
    from app.tasks.embedding_repair import repair_once
    _add(db, "short")
    out = run(repair_once(db, encode=lambda t, b: [0.1] * 10))
    assert out["failed"] == 1
    has, attempts, err, next_at = _get(db, "short")
    assert not has and attempts == 1 and "expected 768" in err and next_at is not None
    # Backing off: the next pass does not pick it up.
    assert run(repair_once(db, encode=lambda t, b: VEC))["selected"] == 0


def test_a_row_error_is_recorded(db):
    from app.tasks.embedding_repair import repair_once
    _add(db, "err")

    def bad(t, b):
        raise ValueError("encoder returned garbage")
    out = run(repair_once(db, encode=bad))
    assert out["failed"] == 1 and _get(db, "err")[1] == 1


def test_two_passes_never_overlap(db):
    from app.tasks import embedding_repair as er
    conn = db._temp_get_connection()
    try:
        assert conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": er._LOCK_KEY}).scalar()
        _add(db, "locked")
        out = run(er.repair_once(db, encode=lambda t, b: VEC))
        assert out.get("skipped") == "locked" and not _get(db, "locked")[0]
    finally:
        conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": er._LOCK_KEY})
        conn.close()


def test_ingest_upsert_failure_is_recorded_for_the_sweep(db, monkeypatch):
    from app import vector_store_pgvector as vs
    _add(db, "ingest")
    monkeypatch.setattr(vs, "_encode_fields", lambda t, c: (_ for _ in ()).throw(RuntimeError("encoder 500")))
    assert vs.upsert_article({"uri": PFX + "ingest", "title": "T", "summary": "body text"}) is False
    has, attempts, err, _ = _get(db, "ingest")
    assert not has and attempts == 1 and "encoder 500" in err
    monkeypatch.setattr(vs, "_encode_fields", lambda t, c: VEC)
    assert vs.upsert_article({"uri": PFX + "ingest", "title": "T", "summary": "body text"}) is True
    has, attempts, err, _ = _get(db, "ingest")
    assert has and attempts is None and err is None


def test_approving_an_old_article_makes_it_due_now(db):
    from app.services.async_db import get_async_database_instance
    _add(db, "old", ingest_status="filtered_relevance", topic_alignment_score=0.5)
    adb = get_async_database_instance()

    async def go():
        await adb.initialize() if hasattr(adb, "initialize") else None
        return await adb.record_relevance_decision(PFX + "old", {
            "relevance_accepted_applied": True, "relevance_threshold_applied": 0.4,
            "relevance_decision_engine": "local", "relevance_policy_version": "t"})
    assert run(go())
    conn = db._temp_get_connection()
    due = conn.execute(text("SELECT embedding_due_at > NOW() - interval '1 minute' FROM articles WHERE uri = :u"),
                       {"u": PFX + "old"}).scalar()
    conn.close()
    assert due
