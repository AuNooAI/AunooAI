"""An operator's 'excluded' verdict takes a matched page out of the market.

Deleting the bw_market_articles link does not hold — the next term scan
matches the page again and the upsert puts the row back — so the exclusion
lives in review_verdict, which the upsert never touches, and the corpus
query skips it everywhere: feed, news river, report.
"""

import pytest
from sqlalchemy import text

from app.services import market_corpus as mcorp


@pytest.fixture()
def conn():
    from app.database import get_database_instance
    try:
        c = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def test_an_excluded_row_leaves_the_corpus_and_the_verdict_survives_a_rescan(conn):
    row = conn.execute(text("""
        SELECT ma.id, ma.market_id, ma.article_uri FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.review_verdict IS DISTINCT FROM 'excluded' AND ma.score >= 1
        ORDER BY ma.matched_at DESC LIMIT 1""")).mappings().first()
    if row is None:
        pytest.skip("no matched article to exclude")
    market, uri = row["market_id"], row["article_uri"]

    def present():
        rows = mcorp.articles(conn, market, limit=2000, min_score=0,
                              require_signal_for_social=False)
        return any(r["uri"] == uri for r in rows)

    assert present()
    conn.execute(text("UPDATE bw_market_articles SET review_verdict='excluded' WHERE id=:i"),
                 {"i": row["id"]})
    assert not present()

    # The scan's upsert rewrites the match but never the verdict.
    conn.execute(text("""
        INSERT INTO bw_market_articles
            (market_id, article_uri, matched_terms, title_terms, body_terms,
             score, method, origin)
        VALUES (:m, :uri, '{"rescan"}', 1, 0, 99, 'term_match', 'corpus')
        ON CONFLICT (market_id, article_uri) DO UPDATE SET
            matched_terms = EXCLUDED.matched_terms, score = EXCLUDED.score,
            matched_at = NOW()"""), {"m": market, "uri": uri})
    assert conn.execute(text("SELECT review_verdict FROM bw_market_articles WHERE id=:i"),
                        {"i": row["id"]}).scalar() == "excluded"
    assert not present()


def test_our_own_feed_rows_never_join_the_corpus(conn):
    # An approved piece returns through the feed as an articles row with
    # article_origin = 'report' (market_briefing.FEED_ORIGIN). The scan must
    # not read it: a site citing itself came out as a vendor development.
    uri = "https://test.invalid/api/market-monitor/markets/2/report.html?piece=999999"
    conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source, article_origin)
        VALUES (:u, 'Agentic SOC is a feature now', 'agentic SOC everywhere',
                'Aunoo Market Monitor', 'report')
        ON CONFLICT (uri) DO NOTHING"""), {"u": uri})
    result = mcorp.scan(conn, 2, terms=["agentic SOC"], dry_run=True, limit=50000)
    assert all(s["uri"] != uri for s in result.get("samples") or [])
