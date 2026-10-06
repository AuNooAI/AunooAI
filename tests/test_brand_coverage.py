"""brand_coverage: the shared inclusion rule against PostgreSQL in a throwaway
schema. One URI owned for brand A and earned for brand B; sector, invalid and
unlabelled rows; the classification selection and the reader filter."""
import os
import uuid

import pytest

from app.services import brand_coverage as bc


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("BRAND_RELATION_DECISIONS", "1")
    try:
        from dotenv import load_dotenv
        from sqlalchemy import create_engine, text
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        schema = f"bctest_{uuid.uuid4().hex[:8]}"
        url = (f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
               f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}")
        eng = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
        conn = eng.connect()
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        for t in ("articles", "keyword_groups", "keyword_article_matches", "bw_brands", "bw_article_categories"):
            conn.execute(text(f"CREATE TABLE {schema}.{t} (LIKE public.{t} INCLUDING ALL)"))
        conn.commit()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no sandbox: {e}")
    bc._cols.update(ok=None, at=0.0)
    yield conn, text
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    conn.commit()
    conn.close()


def _setup(conn, text):
    for bid, name in ((1, "Acme"), (2, "Beta")):
        conn.execute(text("INSERT INTO bw_brands (id, name, display_name, enabled, brand_keywords) VALUES (:i, :n, :n, true, '[]')"), {"i": bid, "n": name})
    gids = {}
    for name in ("Acme", "Beta"):
        gids[name] = conn.execute(text(
            "INSERT INTO keyword_groups (name, topic, source, is_active) VALUES (:n, :t, 'news', true) RETURNING id"),
            {"n": name, "t": f"Brand Monitoring {name}"}).scalar()

    def art(uri, title, bias_source=None):
        conn.execute(text("INSERT INTO articles (uri, title, analyzed, news_source, bias_source, ingest_status) "
                          "VALUES (:u, :t, true, 'news.example', :b, 'approved')"), {"u": uri, "t": title, "b": bias_source})

    def match(uri, brand, rel=None, src=None, status="approved"):
        conn.execute(text("INSERT INTO keyword_article_matches (article_uri, keyword_ids, group_id, brand_relation, "
                          "source_relation, relevance_status) VALUES (:u, '1', :g, :r, :s, :st)"),
                     {"u": uri, "g": gids[brand], "r": rel, "s": src, "st": status})

    def cat(uri, bid):
        conn.execute(text("INSERT INTO bw_article_categories (article_uri, brand_id, category) VALUES (:u, :b, 'News')"),
                     {"u": uri, "b": bid})

    # Acme's own blog post about Beta: owned for Acme, earned for Beta.
    art("acme-blog", "Acme compares itself with Beta", bias_source="owned:acme.example")
    match("acme-blog", "Acme", "subject", "owned"); match("acme-blog", "Beta", "notable", "independent")
    cat("acme-blog", 1); cat("acme-blog", 2)
    # Independent story about Acme.
    art("press-1", "Acme raises funding"); match("press-1", "Acme", "subject", "independent"); cat("press-1", 1)
    # Sector story in Acme's topic, body only, name filter would miss it.
    art("sector-1", "Widget market grows"); match("sector-1", "Acme", "sector", "independent")
    # Labelled earned row whose title does not name the brand (body mention).
    art("body-1", "Industry outlook"); match("body-1", "Acme", "notable", "independent")
    # Invalid stored label.
    art("bad-1", "Acme odd row"); match("bad-1", "Acme", "great", "independent")
    # Legacy row, no label, title names the brand.
    art("legacy-1", "Acme legacy story"); match("legacy-1", "Acme", None, None); cat("legacy-1", 1)
    conn.commit()


def test_classification_selection(db):
    conn, text = db
    _setup(conn, text)
    topics = bc.brand_topics("Acme")
    q = (f"SELECT a.uri FROM articles a WHERE a.analyzed AND ((a.title ILIKE '%Acme%') OR "
         f"{bc.labelled_earned_sql('a', 't')}) AND {bc.label_veto_sql('a', 't')} ORDER BY a.uri")
    got = [r[0] for r in conn.execute(text(q), {"t": topics})]
    # owned (acme-blog), sector and invalid are vetoed; body-1 enters by label; legacy by name.
    assert got == ["body-1", "legacy-1", "press-1"]


def test_reader_filter_is_scoped_per_brand(db):
    conn, text = db
    _setup(conn, text)
    q = ("SELECT a.uri FROM bw_article_categories bac JOIN articles a ON a.uri = bac.article_uri "
         f"WHERE bac.brand_id = :b AND {bc.earned_news_scoped_sql('a', 'bac')} ORDER BY a.uri")
    acme = [r[0] for r in conn.execute(text(q), {"b": 1})]
    beta = [r[0] for r in conn.execute(text(q), {"b": 2})]
    assert "acme-blog" not in acme and acme == ["legacy-1", "press-1"]
    assert beta == ["acme-blog"]  # legacy owned tag overridden by Beta's independent label


def test_labels_for_prefers_the_non_earned_reading(db):
    conn, text = db
    _setup(conn, text)
    labels = bc.labels_for(conn, ["acme-blog", "press-1", "legacy-1"], bc.brand_topics("Acme"))
    assert labels["acme-blog"]["source_relation"] == "owned" and "legacy-1" not in labels


def test_coverage_split_buckets_and_rows(db):
    conn, text = db
    _setup(conn, text)
    out = bc.coverage_split(conn, "Acme", days=30, relation="earned")
    assert out["counts"] == {"owned": 1, "earned": 2, "sector": 1, "invalid": 1, "unlabelled": 1}
    assert {r["uri"] for r in out["rows"]} == {"press-1", "body-1"}


@pytest.mark.parametrize("flag,cols", [("1", False), ("", True)])
def test_degrades_to_legacy_sql_without_columns_or_flag(monkeypatch, flag, cols):
    monkeypatch.setenv("BRAND_RELATION_DECISIONS", flag)
    monkeypatch.setattr(bc, "labels_available", lambda conn=None: cols)
    from app.services.social_sources import earned_news_sql
    assert bc.earned_news_scoped_sql("a", "bac") == earned_news_sql("a")
    assert bc.label_veto_sql() == "TRUE" and bc.labelled_earned_sql() == "FALSE"
    assert f"{bc.LazySql(bc.label_veto_sql)}" == "TRUE"
