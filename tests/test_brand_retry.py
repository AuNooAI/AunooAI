"""app/services/brand_retry.py selection against PostgreSQL in a throwaway
schema: failed judgments always, admitted items whose analysis failed only
when asked (cron sites), each such attempt counted, and the cap respected."""
import json
import os
import uuid

import pytest


@pytest.fixture
def db(monkeypatch):
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        schema = f"brtest_{uuid.uuid4().hex[:8]}"
        url = (f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
               f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}")
        eng = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        conn = eng.connect()
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"CREATE TABLE {schema}.articles (uri text primary key, title text, news_source text, "
                          "publication_date text, summary text, submission_date text, ingest_status text)"))
        conn.execute(text(f"CREATE TABLE {schema}.keyword_groups (id int primary key, topic text)"))
        conn.execute(text(f"CREATE TABLE {schema}.keyword_article_matches (article_uri text, group_id int, "
                          "relevance_status text, brand_relation text, last_failure jsonb)"))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no sandbox: {e}")
    monkeypatch.setenv("BRAND_RELATION_DECISIONS", "1")

    class _Conn:
        def __getattr__(self, k):
            return getattr(conn, k)

        def close(self):
            pass

    class _Db:
        def _temp_get_connection(self):
            return _Conn()

    yield conn, text, _Db()
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    conn.commit()
    conn.close()


def _seed(conn, text):
    conn.execute(text("INSERT INTO keyword_groups VALUES (1, 'Brand Monitoring Haleon'), (2, 'Oral health')"))
    rows = [("failed", "relevance_check_failed", None, "filtered_relevance", None, 1),
            ("pending", "pending", "subject", "enrichment_failed", None, 1),
            ("pending_capped", "pending", "subject", "enrichment_failed", {"attempts": 3}, 1),
            ("pending_ok", "pending", "subject", "approved", None, 1),
            ("not_brand", "relevance_check_failed", None, "filtered_relevance", None, 2)]
    for uri, st, rel, ing, lf, g in rows:
        conn.execute(text("INSERT INTO articles VALUES (:u, 't', 's', NULL, '', '2026-10-06', :i)"), {"u": uri, "i": ing})
        conn.execute(text("INSERT INTO keyword_article_matches VALUES (:u, :g, :s, :r, CAST(:lf AS jsonb))"),
                     {"u": uri, "g": g, "s": st, "r": rel, "lf": json.dumps(lf) if lf else None})
    conn.commit()


def test_sweep_sites_retry_failed_judgments_only(db):
    conn, text, fake = db
    _seed(conn, text)
    from app.services.brand_retry import _fetch_brand_retry_rows
    assert {r["uri"] for r in _fetch_brand_retry_rows(fake, 25)} == {"failed"}


def test_cron_sites_also_retry_admitted_items_whose_analysis_failed_and_count_it(db):
    conn, text, fake = db
    _seed(conn, text)
    from app.services.brand_retry import _fetch_brand_retry_rows
    assert {r["uri"] for r in _fetch_brand_retry_rows(fake, 25, include_pending=True)} == {"failed", "pending"}
    att = conn.execute(text("SELECT last_failure->>'attempts' FROM keyword_article_matches WHERE article_uri='pending'")).scalar()
    assert att == "1"
    for _ in range(2):
        _fetch_brand_retry_rows(fake, 25, include_pending=True)
    assert "pending" not in {r["uri"] for r in _fetch_brand_retry_rows(fake, 25, include_pending=True)}
