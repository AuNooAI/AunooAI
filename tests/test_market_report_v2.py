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
    assert "Top 2 by open roles" in block
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
    # The byline is the author whatever the generation flag says; the
    # Article 50 footer on the piece page carries the AI disclosure.
    row["generation"] = "edited"
    assert "By Oliver" in html._v2_piece_card(row, {})
    assert "Drafted" not in html._v2_piece_card(row, {})


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
    pieces = mbr.approved_pieces(conn, market["id"])
    # A fresh piece takes the lead (2 Sep 2026 rule); the Analysis section
    # shows only the pieces left after that, so with one fresh piece it is
    # absent. The lead's own markup says whether it is a piece.
    lead = page[page.find('id="v2-lead"'):page.find("</section>", page.find('id="v2-lead"'))]
    lead_is_piece = "piece=" in lead
    expected = bool(pieces) and (len(pieces) > 1 or not lead_is_piece)
    assert ('id="v2-analysis"' in page) == expected
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
def test_shared_view_opens_text_but_keeps_metrics_to_authorized(conn, market):
    """Operator policy, 9 Sep 2026: a restricted reader sees every vendor's
    news, posts and developments; KPIs and metrics stay with the authorized
    set. So the page may name withheld vendors in editorial surfaces, but
    the attention bars must only carry authorized vendors."""
    import re

    from app.services import market_entitlements as ent

    allowed = ent.authorized_brand_ids(conn, market["id"], 10)
    withheld = set(ent.withheld_names(conn, market["id"], allowed))
    if not withheld:
        pytest.skip("this market has no vendors to withhold")
    page = html.build_market_report_v2(conn, market, days=30,
                                       allowed_brand_ids=allowed).decode()
    shown = set(ent.vendor_names(conn, market["id"], allowed).values())
    assert any(n in page for n in shown), "no authorized vendor appears"
    # The attention bars are a metric surface: no withheld vendor's row.
    bar_names = set(re.findall(r'v2-bar-name">(?:<[^>]*>)*([^<]+)<', page))
    assert bar_names, "no attention bars rendered"
    assert not (bar_names & withheld), (
        f"withheld vendors in the attention bars: {bar_names & withheld}")
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


def _topics_run(**over):
    base = {"computed_at": "2026-09-06T10:00:00+00:00", "n": 300, "assigned": 90, "window_days": 30,
            "clusters": [
                {"id": 0, "name": "Fal.Con 2026", "summary": "Live from the show.",
                 "n_recent": 18, "n_total": 51, "rise": 1.18, "top_vendors": [], "uris": []},
                {"id": 1, "name": "7AI funding round", "summary": "A $130M Series A.",
                 "n_recent": 9, "n_total": 13, "rise": 2.15, "top_vendors": [], "uris": []},
                {"id": 2, "name": "Acme launches", "summary": "Acme Corp shipped a thing.",
                 "n_recent": 6, "n_total": 8, "rise": 1.9,
                 "top_vendors": [{"brand_id": 99, "vendor": "Acme Corp", "n": 4}], "uris": []},
            ],
            "being_discussed": [0, 1, 2], "emerging": [1]}
    base.update(over)
    return base


def test_topics_card_shows_both_lists_and_links_each_subject():
    card = html._v2_topics(_topics_run(), {}, 30)
    assert "Being discussed" in card and ">Emerging<" in card
    assert "topic=0" in card and "topic=1" in card
    assert card.count("&#9650; 2.1&times;") == 2     # the rise: on its discussed row and under Emerging
    assert card.count("&#9650; 1.9&times;") == 1     # Acme rises too, listed once
    assert "&#9650; 1.2&times;" not in card          # Fal.Con is not above pace
    assert card.count("Fal.Con 2026") == 1 and card.count("7AI funding round") == 2
    assert "From 300 articles over the last 30 days, grouped 06 September." in card


def test_topics_card_is_empty_without_a_run_or_without_entries():
    assert html._v2_topics(None, {}, 30) == ""
    assert html._v2_topics(_topics_run(being_discussed=[], emerging=[]), {}, 30) == ""


def test_topics_projection_drops_a_subject_naming_a_withheld_vendor_and_reranks():
    slim = html._v2_topics_for_view(_topics_run(), [1, 2], {"Fal.Con", "7AI"}, ["Acme Corp"])
    ids = [c["id"] for c in slim["clusters"]]
    assert ids == [0, 1]                         # the Acme subject is gone by its own words
    assert slim["being_discussed"] == [0, 1] and slim["emerging"] == []


def test_schedule_an_inquiry_link_appears_only_when_configured_and_public(monkeypatch):
    for k, v in {"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_PRICE_INQUIRY_30": "p30",
                 "STRIPE_PRICE_INQUIRY_60": "p60", "MARKET_INQUIRY_BOOKING_URL_30": "https://c/30",
                 "MARKET_INQUIRY_BOOKING_URL_60": "https://c/60"}.items():
        monkeypatch.setenv(k, v)
    link = html._book_link({"id": 2, "name": "M", "is_public": True})
    assert 'class="n-book"' in link and "/markets/2/inquiry" in link and "Schedule an inquiry" in link
    assert html._book_link({"id": 2, "name": "M", "is_public": False}) == ""
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    assert html._book_link({"id": 2, "name": "M", "is_public": True}) == ""


def test_recent_movers_prefers_this_weeks_motion_over_old_heavyweights():
    # 8 Sep 2026: the Who moved card showed only 17-31 Aug because it took
    # the importance-ranked slice; a mover card answers a recency question.
    from app.services.market_report_html import _recent_movers

    old_high = [{"date": f"2026-08-{d:02d}", "importance": "high",
                 "event_type": "acquisition"} for d in (17, 19, 20, 25, 26, 28, 31)]
    new_low = [{"date": f"2026-09-{d:02d}", "importance": "low",
                "event_type": "product_launch"} for d in (3, 4, 7)]
    undated = [{"date": None, "importance": "high", "event_type": "funding"}]
    hiring = [{"date": "2026-09-08", "importance": "low",
               "event_type": "significant_hiring"}]
    out = _recent_movers(old_high + new_low + undated + hiring, limit=8)
    assert [d["date"] for d in out[:3]] == ["2026-09-07", "2026-09-04", "2026-09-03"]
    assert all(d.get("date") for d in out)
    assert all(d["event_type"] != "significant_hiring" for d in out)


def test_attention_bars_carry_a_delta_against_the_period_before():
    from app.services.market_report_html import _v2_motion

    rows = [{"vendor": "7ai", "reactions": 500, "earned": 12, "measured": 9},
            {"vendor": "Torq", "reactions": 300, "earned": 20, "measured": 4}]
    prev = [{"vendor": "7ai", "reactions": 200, "earned": 12},
            {"vendor": "Torq", "reactions": 400, "earned": 5}]
    html = _v2_motion(rows, prev=prev)
    assert 'v2-move up' in html and "&#9650; 300" in html      # 7ai reactions up
    assert 'v2-move down' in html and "&#9660; 100" in html    # Torq reactions down
    assert "the same in the period before" in html             # 7ai earned unchanged
    # Without a previous window the engagement bar keeps its posts note.
    assert "9 posts" in _v2_motion(rows, prev=None)


def test_the_social_panel_spreads_across_voices():
    """On 16 September 2026 one feed robot held two of the six front-page
    slots and one person's duplicate post held two more, so the panel showed
    three voices where it had room for six."""
    from app.services.market_report_html import _spread_voices

    rows = [{"uri": f"u{i}", "social_meta": {"author": a}} for i, a in
            enumerate(["opsmatters", "opsmatters", "gullible", "gullible",
                       "chuvakin", "polsia", "torq_io"])]
    shown = _spread_voices(rows, 6)
    authors = [(r["social_meta"]["author"]) for r in shown]
    assert authors[:5] == ["opsmatters", "gullible", "chuvakin", "polsia",
                           "torq_io"]
    # Nothing is dropped: with five distinct voices and room for six, a
    # second post fills the last slot rather than leaving it empty.
    assert len(shown) == 6
    assert len(_spread_voices(rows, 20)) == len(rows)


def test_the_social_panel_keeps_rows_with_no_author():
    from app.services.market_report_html import _spread_voices

    rows = [{"uri": "a", "social_meta": {}}, {"uri": "b", "social_meta": None},
            {"uri": "c"}]
    assert len(_spread_voices(rows, 6)) == 3


def test_the_social_panel_shows_one_line_of_campaign_copy_once():
    """A partner campaign runs the same sentence from several handles: the
    Microsoft Copilot line ran from three accounts, two of which reached the
    panel on 16 September 2026."""
    from app.services.market_report_html import _spread_voices

    copy = "Fragmented security tools impact visibility. Message us to talk."
    rows = [{"uri": "a", "title": copy, "social_meta": {"author": "one"}},
            {"uri": "b", "title": copy, "social_meta": {"author": "two"}},
            {"uri": "c", "title": "Wazuh and TheHive are talking to each other",
             "social_meta": {"author": "three"}}]
    shown = _spread_voices(rows, 2)
    assert [r["uri"] for r in shown] == ["a", "c"]
    # Kept, not dropped: with room for three the repeat fills the last slot.
    assert [r["uri"] for r in _spread_voices(rows, 3)] == ["a", "c", "b"]


def test_the_same_post_from_two_handles_keys_the_same():
    """A social title is "@handle: <the post>", so keying the panel's dedup
    on the title let one line of syndicated copy through twice (16 Sep
    2026)."""
    from app.services.market_report_html import _same_words

    body = ("AI-powered SOC automation reduces detection time and improves "
            "accuracy while keeping human analysts responsible.")
    a = {"title": f"@bizintelbriefly.bsky.social: {body}", "summary": body}
    b = {"title": f"@devopsbriefly.bsky.social: {body}", "summary": body}
    assert _same_words(a) == _same_words(b)
    # With no body, the handle still comes off the title.
    assert (_same_words({"title": f"@one: {body}"})
            == _same_words({"title": f"@two: {body}"}))


def test_a_contract_award_is_a_move_tagged_contract():
    award = _dev(5, "customer")
    award["headline"] = "Method Security wins $30M STRATFI award from U.S. Space Force"
    lead = _dev(0, "acquisition")
    parts = html._v2_sections([lead, award], [], [], [])
    # The lead rotates by day, so the award is either the lead or a move;
    # what it must never be is a case study.
    assert award not in parts["buckets"]["cases"]
    assert award in parts["buckets"]["moves"] or parts.get("lead") is award
    assert html._v2_tag(award) == "Contract"


def test_the_vendors_own_text_is_never_the_summary():
    own = _dev(7, "partnership", summary="We are proud to announce that we are the partner.",
               evidence=[{"uri": "https://x/7", "voice": "owned", "social": True}])
    assert html._summary_unless_duplicate(own) == ""
    own["dek"] = "Camelot becomes the Ravens' cyber resilience partner."
    assert html._summary_unless_duplicate(own) == own["dek"]
    news = _dev(8, "launch", summary="The publisher's own summary of the launch.",
                evidence=[{"uri": "https://x/8", "voice": "independent", "social": False}])
    assert html._summary_unless_duplicate(news)


def test_a_headcount_reading_is_measured_on_a_day():
    dev = _dev(9, "headcount_change", date="2026-09-23", date_established=False)
    assert html._dev_date(dev) == "measured 23 Sep 2026"


def test_a_vendor_post_row_drops_the_page_name_the_byline_already_gives():
    row = {"uri": "https://www.linkedin.com/posts/x", "article_class": "social",
           "title": "detections.ai: Threat actor delivery picked up the pace this week.",
           "summary": "", "published": "2026-09-25T10:00:00Z",
           "vendors": [{"brand_id": 1, "vendor": "System Two Security"}]}
    out = html._v2_voice_row(row)
    assert "System Two Security on LinkedIn" in out
    assert "detections.ai:" not in out and "Threat actor delivery" in out
    assert "(A Devo company)" not in html._river_source(
        {**row, "vendors": [{"vendor": "Strike48 (A Devo company)"}]})
