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


# --- The briefing on the shared report ---------------------------------------

def test_the_summary_skips_a_plain_text_subtitle():
    text_ = ("Aunoo | Market Briefing\n\nWeek of 17–23 August 2026: AI-SOC Market Briefing\n\n"
             "## 1. What Happened\n\nFour vendors announced new capabilities. [A2]\n")
    assert mbr.feed_summary(text_) == "Four vendors announced new capabilities."


def test_safe_sentences_drop_the_sentence_naming_a_withheld_vendor_whole():
    s = ("Four vendors announced new AI SOC capabilities. Arambh Labs launched Armor Detect. "
         "System Two Security made its enterprise tier available. Intezer added workflows.")
    out = mbr.safe_sentences(s, ["Arambh Labs", "Intezer"])
    assert out == ("Four vendors announced new AI SOC capabilities. "
                   "System Two Security made its enterprise tier available.")
    assert mbr.safe_sentences(s, []) == s
    # Word boundary: "Joon" must not match "Joone" but must match "Joon."
    assert mbr.safe_sentences("Joone rose. Joon fell.", ["Joon"]) == "Joone rose."


def test_a_shared_reader_gets_the_card_and_never_the_text(conn, briefing):
    """The shared report withholds most vendors and refuses a page that names
    one, so the briefing text — which names them all — must not be there,
    blurred or otherwise. Only the card."""
    from app.services import market_entitlements as ent
    from app.services.market_report_html import build_market_briefing_page

    market, bid = briefing
    conn.execute(text("UPDATE bw_market_briefings SET status='approved' WHERE id=:i"), {"i": bid})
    allowed = ent.authorized_brand_ids(conn, market["id"], 1)
    withheld = ent.withheld_names(conn, market["id"], allowed)
    if not withheld:
        pytest.skip("market has one vendor; nothing is withheld")

    page = build_market_briefing_page(conn, market, briefing_id=bid,
                                      allowed_brand_ids=allowed).decode()
    assert 'id="mm-briefing"' in page
    assert "References" not in page and 'class="refs"' not in page
    assert "Request a trial" in page

    full = build_market_briefing_page(conn, market, briefing_id=bid).decode()
    assert "Read the briefing" not in full          # it *is* the briefing
    assert "<h1>" in full and "mm-briefing" not in full


def test_a_draft_is_never_served_on_the_report_even_by_id(conn, briefing):
    from app.services.market_report_html import build_market_briefing_page

    market, bid = briefing
    conn.execute(text("UPDATE bw_market_briefings SET status='draft' WHERE id=:i"), {"i": bid})
    page = build_market_briefing_page(conn, market, briefing_id=bid).decode()
    assert "No approved briefing yet" in page


def test_a_shared_feed_keeps_the_briefing_item_with_a_safe_description(conn, briefing):
    from app.services import market_entitlements as ent
    from app.services import market_publish as mp

    import re

    market, bid = briefing
    # set_status stamps updated_at, and the feed sorts on it; an approval
    # dated weeks ago would fall past the feed's item cut.
    conn.execute(text("UPDATE bw_market_briefings SET status='approved', "
                      "updated_at=NOW() WHERE id=:i"), {"i": bid})
    allowed = ent.authorized_brand_ids(conn, market["id"], 1)
    withheld = ent.withheld_names(conn, market["id"], allowed)
    if not withheld:
        pytest.skip("market has one vendor; nothing is withheld")
    xml = mp.build_feed(conn, market, base_url="https://example.test",
                        allowed_brand_ids=allowed).decode()
    assert f"market-briefing-{bid}" in xml
    for name in withheld:
        assert not re.search(rf"(?<!\w){re.escape(name)}(?!\w)", xml, re.IGNORECASE), name
