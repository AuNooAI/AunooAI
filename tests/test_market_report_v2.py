"""The front page (``?view=v2``): every development in exactly one section,
the customer rule, the thought-leadership selection, and the same access
rules as the report.

The bucketing tests are pure. The page tests render against the database
and skip without one, like the entitlement tests they mirror.
"""

from __future__ import annotations

import os

import pytest

from app.services import market_report_html as html


def _dev(i, event_type, **extra):
    d = {"event_id": f"e{i}", "event_type": event_type,
         "event_type_label": event_type.replace("_", " ").title(),
         "headline": f"Headline {i}", "summary": "", "vendors": [{"brand_id": i, "vendor": f"V{i}"}],
         "evidence": [{"uri": f"https://x/{i}"}], "date": "2026-08-20", "rank": i,
         "provenance_label": "Vendor sources only", "source_count": 1}
    d.update(extra)
    return d


def test_every_development_lands_once_and_the_lead_is_not_repeated():
    types = ["acquisition", "market_exit", "market_entry", "funding", "partnership",
             "executive_appointment", "product_launch", "product_expansion",
             "significant_hiring", "headcount_change"]
    devs = [_dev(i, t) for i, t in enumerate(types)]
    parts = html._v2_sections(devs, [], [], [])
    assert parts["lead"] is devs[0]
    placed = [d["event_id"] for b in parts["buckets"].values() for d in b
              if "event_id" in d]
    assert sorted(placed) == sorted(d["event_id"] for d in devs[1:])
    assert [d["event_type"] for d in parts["buckets"]["launches"]] == ["product_launch", "product_expansion"]
    assert [d["event_type"] for d in parts["buckets"]["hiring"]] == ["significant_hiring", "headcount_change"]
    assert all(d["event_type"] not in ("product_launch", "product_expansion",
                                       "significant_hiring", "headcount_change")
               for d in parts["buckets"]["moves"])


def test_hiring_is_ordered_by_open_roles_and_the_top_of_it_says_so():
    lead = _dev(0, "acquisition")
    small = _dev(1, "significant_hiring", attributes={"openings": 6, "by_function": {}})
    big = _dev(2, "significant_hiring", attributes={"openings": 14, "by_function": {}})
    head = _dev(3, "headcount_change", attributes={"pct": 12, "previous": 50, "latest": 56})
    parts = html._v2_sections([lead, head, small, big], [], [], [])
    assert parts["buckets"]["hiring"] == [big, small, head]
    block = html._render_hiring_block([big, small], total=8)
    assert "Top 2 of 8 vendors with" in block
    assert "2 vendors with" in html._render_hiring_block([big, small])


def test_a_fresh_piece_takes_the_lead_and_the_developments_all_stay_in_sections():
    from datetime import datetime, timedelta, timezone
    devs = [_dev(0, "acquisition"), _dev(1, "product_launch")]
    parts = html._v2_sections(devs, [], [], [], lead_from_developments=False)
    assert parts["lead"] is None
    assert parts["buckets"]["moves"] == [devs[0]] and parts["buckets"]["launches"] == [devs[1]]
    fresh = {"published_at": datetime.now(timezone.utc) - timedelta(days=1)}
    stale = {"published_at": datetime.now(timezone.utc) - timedelta(days=5)}
    assert html._piece_is_fresh(fresh) and not html._piece_is_fresh(stale)
    assert not html._piece_is_fresh({"published_at": None})


def test_piece_card_says_who_wrote_it():
    from datetime import datetime, timezone
    row = {"id": 7, "kind": "analysis", "title": "A title", "author": "Oliver",
           "generation": "written", "report_content": "First paragraph of the piece.\n\nSecond.",
           "published_at": datetime(2026, 8, 29, tzinfo=timezone.utc)}
    card = html._v2_piece_card(row, {"days": 30}, lead=True)
    assert "Our analysis" in card and "By Oliver" in card and "29 Aug 2026" in card
    assert "First paragraph of the piece." in card and "view=v2&amp;piece=7" in card
    row["generation"] = "edited"
    assert "edited by Oliver" in html._v2_piece_card(row, {})


def test_voices_card_shows_ten_then_blurs_the_rest_in_the_shared_view():
    rows = [{"id": i, "platform": "twitter", "handle": f"h{i}", "display_name": f"Person {i}",
             "followers_count": 1000 - i, "profile_url": None, "watchlisted": i == 0,
             "role": "practitioner"} for i in range(13)]
    tv = {"voices": [{"platform": "twitter", "author": "h1", "posts": 3,
                      "latest_post": {"url": "https://x/p"}}]}
    shared = html._v2_voices_card(rows, tv, teaser=True)
    assert shared.index("Person 0") < shared.index("Person 1")
    assert "Following" in shared and "3 posts" in shared and "quiet this period" in shared
    assert html._TEASER_START in shared and shared.index("Person 10") > shared.index(html._TEASER_START)
    full = html._v2_voices_card(rows, tv, teaser=False)
    assert html._TEASER_START not in full and "Person 12" in full
    assert html._v2_voices_card([], tv, teaser=True) == ""


def test_followed_posts_are_kept_only_when_they_touch_the_market():
    import re
    from app.services import market_follow as mf
    terms = mf._term_patterns(["AI SOC", "alert triage", "security operations center"])
    vendors = [("Crogl", re.compile(r"(?<![a-z0-9])crogl(?![a-z0-9])"))]
    assert mf.touches_market("The AI-SOC hype cycle, again.", terms, vendors) == ["AI SOC"]
    assert mf.touches_market("Alert triage is where the money is", terms, vendors) == ["alert triage"]
    assert mf.touches_market("Crogl raised a round", terms, vendors) == ["Crogl"]
    assert mf.touches_market("A post about lunch", terms, vendors) == []
    assert mf.touches_market("microcrogl is not crogl", terms, vendors) == ["Crogl"]
    # A followed account gets the short markers too; the firehose does not.
    markers = mf._term_patterns(mf.follow_markers({"config": {}}))
    assert mf.touches_market("Your SOC is not a helpdesk.", terms, vendors) == []
    assert mf.touches_market("Your SOC is not a helpdesk.", terms, vendors, markers) == ["SOC"]
    assert mf.touches_market("Social media is not a SOCk puppet", terms, vendors, markers) == []
    assert mf.follow_markers({"config": {"follow_markers": ["logs"]}}) == ["logs"]
    # The stored URL is the keyword collector's form, so one reply is one row.
    assert (mf.canonical_url("twitter", "anton_chuvakin", {"id": "209", "url": "https://x.com/i/status/209"})
            == "https://x.com/anton_chuvakin/status/209")
    assert mf.canonical_url("bluesky", "a.bsky.social", {"id": "1", "url": "https://bsky.app/x"}) == "https://bsky.app/x"


def test_lead_skips_a_hiring_count():
    devs = [_dev(0, "significant_hiring"), _dev(1, "product_launch")]
    parts = html._v2_sections(devs, [], [], [])
    assert parts["lead"] is devs[1]
    assert parts["buckets"]["hiring"] == [devs[0]]


def test_named_customer_is_a_customer_and_unnamed_is_a_case_study():
    lead = _dev(0, "acquisition")
    named = _dev(1, "customer", attributes={"customer": {"named": True, "name": "Acme"}})
    unnamed = _dev(2, "customer", attributes={"customer": {"named": False}})
    bare = _dev(3, "customer")
    parts = html._v2_sections([lead, named, unnamed, bare], [], [], [])
    assert parts["buckets"]["moves"] == [named]
    assert parts["buckets"]["cases"] == [unnamed, bare]
    assert html._v2_tag(named) == "Customer"
    assert html._v2_tag(unnamed) == "Case study"
    assert html._v2_tag(bare) == "Case study"
    assert html._v2_tag(lead) == "Acquisition"


def test_thought_leadership_selection():
    dev = _dev(0, "product_launch", evidence=[{"uri": "https://x/used"}])
    rows = [
        {"uri": "https://x/op", "article_class": "social", "review_verdict": "commentary",
         "review_kind": "opinion", "published": "2026-08-01"},
        {"uri": "https://x/res", "article_class": "social", "review_verdict": "signal",
         "review_kind": "research", "published": "2026-08-03"},
        {"uri": "https://x/launch", "article_class": "social", "review_verdict": "signal",
         "review_kind": "launch", "published": "2026-08-04"},
        {"uri": "https://x/noise", "article_class": "social", "review_verdict": "noise",
         "review_kind": "opinion", "published": "2026-08-05"},
        {"uri": "https://x/used", "article_class": "social", "review_verdict": "commentary",
         "review_kind": "opinion", "published": "2026-08-06"},
        {"uri": "https://x/news", "article_class": "news", "review_verdict": None,
         "review_kind": None, "published": "2026-08-07"},
    ]
    discussion = [{"uri": "https://x/disc", "article_class": "discussion", "published": "2026-08-02"},
                  {"uri": "https://x/op", "article_class": "discussion", "published": "2026-08-09"}]
    highlights = [{"uri": "https://x/used", "quote": "q"}, {"uri": "https://x/res", "quote": "q"},
                  {"uri": "https://x/hot", "quote": "q"}]
    parts = html._v2_sections([dev], rows, discussion, highlights)
    # Vendor opinion and research stay under Thought leadership; the
    # practitioner post goes to Social with the most-shared posts.
    assert [r["uri"] for r in parts["buckets"]["voices"]] == ["https://x/res", "https://x/op"]
    assert [r["uri"] for r in parts["buckets"]["social"]] == ["https://x/disc"]
    assert [h["uri"] for h in parts["highlights"]] == ["https://x/hot"]


def test_empty_section_says_so_and_a_full_one_links_to_its_page():
    empty = html._v2_section("cases", "", count=0, days=30, more_href="?view=v2&section=cases")
    assert "No case study in the last 30 days" in empty
    assert "All 0" not in empty
    full = html._v2_section("moves", "<p>x</p>", count=7, days=30, more_href="?view=v2&section=moves")
    assert "All 7" in full and 'id="v2-moves"' in full and "<p>x</p>" in full


def test_small_horizon_has_dots_but_no_names():
    from app.services import market_horizon as hz
    rated = [{"brand_id": i, "vendor": f"V{i}", "scale": s, "momentum": m, "tier": "emerging", "band": "growing"}
             for i, (s, m) in enumerate([(10, 40), (60, 55), (90, 80)])]
    svg = html._horizon_svg(rated, None, {}, tiers=hz.tier_info({}), bands=hz.band_info({}), labels=False)
    assert svg.count("mm-hz-dot") == 3
    assert "mm-lbl" not in svg
    # A number names that many, the largest and fastest first.
    two = html._horizon_svg(rated, None, {}, tiers=hz.tier_info({}), bands=hz.band_info({}),
                            labels=2, label_scale=2.0)
    assert two.count('class="mm-lbl"') == 2 and ">V2<" in two and ">V1<" in two and ">V0<" not in two
    assert 'data-tip="' in svg  # the hover panel still names the vendor
    assert 'class="mm-hz-legend"' in svg and 'class="mm-hz-axis"' in svg


# ---------------------------------------------------------------------------
# Rendered pages, against the database
# ---------------------------------------------------------------------------

pytestmark_db = pytest.mark.skipif(
    os.getenv("DB_TYPE", "postgresql").lower() != "postgresql",
    reason="the market queries are Postgres")


@pytest.fixture()
def conn():
    from app.database import get_database_instance

    try:
        c = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001 — no DB reachable, not a code failure
        pytest.skip(f"no database available: {exc}")
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def market(conn):
    from sqlalchemy import text

    from app.routes.market_monitor_routes import _load_market

    row = conn.execute(text("SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
    if row is None:
        pytest.skip("no market in this database")
    return _load_market(conn, int(row))


@pytestmark_db
def test_front_page_has_its_sections_and_links(conn, market):
    page = html.build_market_report_v2(conn, market, days=30).decode()
    for key in html.V2_SECTIONS:
        if key == "analysis":
            continue   # shown only when a piece of ours is approved
        assert f'id="v2-{key}"' in page
    from app.services import market_briefing as mbr
    assert ('id="v2-analysis"' in page) == bool(mbr.approved_pieces(conn, market["id"]))
    assert 'id="v2-lead"' in page and 'class="v2-grid"' in page
    assert "<h2>Highlights</h2>" in page and '<details class="v2-hl"><summary>' in page
    assert "Most active vendors" in page
    assert "Who got attention" in page and "Most discussed" in page
    # Submit news: the button in the top bar and the panel it jumps to.
    assert 'class="n-tip" href="#mm-tip">Submit news</a>' in page
    # One contact form with a dropdown; the button's anchor lands on it.
    assert 'id="mm-contact"' in page and 'id="mm-tip"' in page
    assert '<option value="news">Submit news</option>' in page
    assert '<option value="missing">' in page and '<option value="trial">' not in page
    assert f'data-base="/api/market-monitor/markets/{market["id"]}/"' in page
    assert 'href="?days=30&amp;view=report">Analyst View</a>' in page
    assert "view=news" in page
    assert page.count("view=v2&amp;section=") >= len(html.V2_SECTIONS)


@pytestmark_db
def test_the_report_and_the_river_link_to_the_front_page(conn, market):
    report = html.build_market_report(conn, market, days=30).decode()
    river = html.build_market_news_page(conn, market, days=30).decode()
    for page in (report, river):
        nav = page[page.index('class="n-pages"'):page.index("</nav>", page.index('class="n-pages"'))]
        assert "view=v2" in nav and "Front page" in nav


@pytestmark_db
def test_about_page_has_the_disclosure_and_privacy_and_unknown_page_raises(conn, market):
    from app.compliance.ai_disclosure import AI_DISCLOSURE_LONG
    page = html.build_market_report_v2(conn, market, days=30, page="about").decode()
    assert 'id="v2-about"' in page and 'id="privacy"' in page and 'id="disclaimer"' in page
    assert AI_DISCLOSURE_LONG in page and "Article 50 of the EU AI Act" in page
    assert "<title>About — " in page
    assert "Oliver Rochford Ltd" in page and "14480528" in page and "SK13 8DA" in page
    front = html.build_market_report_v2(conn, market, days=30).decode()
    # Linked from the footer only, not the top bar (user, 29 Aug).
    assert front.count('page=about">About</a>') == 1 and 'page=about#privacy">Privacy</a>' in front
    assert 'page=about">About</a>' not in front.split('<header class="v2-mast">')[0]
    with pytest.raises(KeyError):
        html.build_market_report_v2(conn, market, days=30, page="bogus")


@pytestmark_db
def test_section_page_renders_and_unknown_section_raises(conn, market):
    page = html.build_market_report_v2(conn, market, days=30, section="hiring").decode()
    assert 'id="v2-hiring"' in page and 'id="v2-lead"' not in page
    assert 'aria-current="page">Hiring</a>' in page
    with pytest.raises(KeyError):
        html.build_market_report_v2(conn, market, days=30, section="bogus")


@pytestmark_db
def test_shared_view_names_only_authorized_vendors(conn, market):
    from app.services import market_entitlements as ent

    allowed = ent.authorized_brand_ids(conn, market["id"], 10)
    withheld = ent.withheld_names(conn, market["id"], allowed)
    if not withheld:
        pytest.skip("this market has no vendors to withhold")
    page = html.build_market_report_v2(conn, market, days=30,
                                       allowed_brand_ids=allowed).decode()
    # The Horizon names every rated vendor by decision (27 August 2026) and
    # is put back after the production check, so it is taken out here the
    # same way the check never saw it.
    import re
    checked = re.sub(r'<div class="mm-hz v2-hz">.*?<div class="mm-hz-tip" hidden></div></div>',
                     "", page, flags=re.S)
    ent.assert_no_withheld(checked, withheld, context="front page")
    shown = ent.vendor_names(conn, market["id"], allowed).values()
    assert any(n in page for n in shown), "no authorized vendor appears either"
    assert "shared view" in page and 'id="mm-trial"' in page
    # The hiring top five and the figures are readable in the shared view;
    # the only blur on the front page is the tail of the influencers list.
    assert page.count('class="mm-teaser"') <= 1
    if 'class="mm-teaser"' in page:
        assert "Want more data?" in page and "The rest of the voices we track" in page


@pytestmark_db
def test_front_page_has_no_banned_copy_patterns(conn, market):
    import re

    from tests.test_market_report_copy import BANNED_PATTERNS

    page = html.build_market_report_v2(conn, market, days=30).decode()
    hits = [p for p in BANNED_PATTERNS if re.search(p, page)]
    assert not hits, f"banned copy in the front page: {hits}"
