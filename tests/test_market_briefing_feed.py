"""An approved market briefing is a news-feed item; a draft or rejected one is not.

The shared news feed is a query over ``articles`` gated on category and
sentiment (get_news_feed_articles_for_date_range). There is no "post to
feed" path, so the briefing joins the feed by becoming a row there and
leaves it by that row being deleted. These tests pin the row's shape, the
summary pulled from the briefing text, and the approve/withdraw round trip.
"""

import pytest
from sqlalchemy import text

from app.services import market_briefing as mbr

BRIEFING_TEXT = """ Wiley Scientific Publisher | Market Briefing
**AI in the SOC — Week of 17–23 August 2026**

---

## 1. What Happened

### Product Launches
Four vendors announced new AI SOC capabilities. [A2, A12] Arambh Labs launched Armor Detect. [A2] System Two Security made its enterprise tier available. [A12]

### Partnerships
Five partnership announcements occurred. [A5]
"""

MARKET = {"id": 2, "name": "AI in the SOC",
          "config": {"collection": {"topic_name": "Market Monitoring SOC Automation"}}}


def test_the_summary_is_the_first_prose_paragraph_without_citations():
    s = mbr.feed_summary(BRIEFING_TEXT)
    assert s.startswith("Four vendors announced new AI SOC capabilities.")
    assert "[A" not in s
    assert "Wiley" not in s and "What Happened" not in s and "---" not in s
    assert "capabilities. Arambh" in s  # no space left where the bracket was


def test_a_long_summary_is_cut_on_a_sentence_end():
    text_ = "## H\n\n" + "A sentence of some length here. " * 40
    s = mbr.feed_summary(text_, limit=200)
    assert len(s) <= 200
    assert s.endswith(".")


def test_the_feed_row_passes_the_feed_gate_and_is_marked_as_a_report(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://example.test/")
    row = mbr.feed_row(MARKET, {"id": 7, "title": "SOC — Week of 2026-08-17",
                                "period_label": "Week of 2026-08-17",
                                "report_content": BRIEFING_TEXT})
    assert row["uri"] == "https://example.test/api/market-monitor/markets/2/briefings/7/report.html"
    assert row["category"] and row["sentiment"]          # the feed's gate
    assert row["article_origin"] == "report"
    assert row["topic"] == "Market Monitoring SOC Automation"
    assert row["news_source"] == mbr.FEED_SOURCE
    assert row["analyzed"] is True


def test_the_page_links_each_citation_and_lists_the_references():
    html = mbr.render_page(MARKET, {
        "id": 7, "title": "T", "period_label": "W", "status": "approved",
        "report_content": BRIEFING_TEXT,
        "facts": {"citation_index": {
            "A2": {"vendor": "Arambh Labs", "title": "Armor Detect",
                   "uri": "https://arambh.test/armor"},
            "A12": {"vendor": "System Two", "title": "Enterprise tier",
                    "uri": "https://s2.test/tier"},
        }},
    })
    assert '<a href="https://arambh.test/armor"' in html
    assert "<h2>References</h2>" in html
    assert html.count("<li>") == 2           # A5 has no source, so no entry
    assert "[A5]" in html                    # but the citation text stays


# --- Round trip against the database, rolled back ---------------------------

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


@pytest.fixture()
def briefing(conn):
    row = conn.execute(text(
        "SELECT id, market_id FROM bw_market_briefings ORDER BY id LIMIT 1"
    )).mappings().first()
    if row is None:
        pytest.skip("no market briefing in this database")
    market = conn.execute(text(
        "SELECT id, name, config FROM bw_markets WHERE id = :m"),
        {"m": row["market_id"]}).mappings().first()
    return dict(market), int(row["id"])


def _feed_has(conn, uri):
    return conn.execute(text("""
        SELECT COUNT(*) FROM articles WHERE uri = :u
          AND category IS NOT NULL AND category != '' AND sentiment IS NOT NULL
    """), {"u": uri}).scalar() == 1


def test_approving_puts_the_briefing_in_the_feed_and_rejecting_takes_it_out(conn, briefing):
    market, bid = briefing
    uri = mbr.briefing_page_url(market["id"], bid)

    conn.execute(text("UPDATE bw_market_briefings SET status='approved' WHERE id=:i"), {"i": bid})
    assert mbr.sync_feed_entry(conn, market, bid, commit=False) == "published"
    assert _feed_has(conn, uri)
    assert conn.execute(text("SELECT article_origin FROM articles WHERE uri=:u"),
                        {"u": uri}).scalar() == "report"

    # Approving twice is an update, not a second row.
    assert mbr.sync_feed_entry(conn, market, bid, commit=False) == "published"
    assert conn.execute(text("SELECT COUNT(*) FROM articles WHERE uri=:u"),
                        {"u": uri}).scalar() == 1

    conn.execute(text("UPDATE bw_market_briefings SET status='rejected' WHERE id=:i"), {"i": bid})
    assert mbr.sync_feed_entry(conn, market, bid, commit=False) == "withdrawn"
    assert not _feed_has(conn, uri)


def test_syncing_an_unknown_briefing_does_nothing(conn, briefing):
    market, _ = briefing
    assert mbr.sync_feed_entry(conn, market, 999999, commit=False) is None
