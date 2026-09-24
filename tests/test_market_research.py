"""Latest research: which records cite an analyst report, how they fold by
report, which corpus rows are the analyst firms' own posts, and how the
section renders. All pure; the feed registration test needs Postgres and
skips without it.

The fixtures are the market 2 records the rules were written against
(29 August 2026), shortened.
"""

from __future__ import annotations

import os

import pytest

from app.services import market_report_html as html
from app.services import market_research as mres


def _row(i, title, summary="", *, vendor=None, uri=None, published="2026-08-20",
         article_class="social", author=None):
    return {"uri": uri or f"https://x/{i}", "title": title, "summary": summary,
            "published": published, "article_class": article_class,
            "vendors": [{"brand_id": i, "vendor": vendor}] if vendor else [],
            "social_meta": {"author": author} if author else None}


def test_a_press_release_names_the_report_the_position_and_the_vendor():
    row = _row(1, "LMNTRIX Positioned as a Major Player in 2026 IDC MarketScape for Worldwide "
                  "MDR/MXDR for the Enterprise",
               "LMNTRIX, a global managed detection and response provider, today announced…",
               article_class="news", uri="https://www.prnewswire.com/x")
    c = mres.cite(row)
    assert c["firm"] == "IDC" and c["family"] == "MarketScape"
    assert c["topic"] == "Worldwide MDR/MXDR for the Enterprise"
    assert c["year"] == "2026" and c["position"] == "Major Player"
    assert c["vendor"] == "LMNTRIX"


def test_three_spellings_of_one_hype_cycle_fold_into_one_group():
    rows = [
        _row(1, "Backline AI: Gartner just dropped the 2026 Hype Cycle for Security Operations.",
             vendor="Backline AI", published="2026-06-23"),
        _row(2, "Prophet Security: the latest iteration of Gartner's \"Hype Cycle for Security "
                "Operations\" came out earlier this month", vendor="Prophet Security",
             published="2026-06-18"),
        _row(3, "Dropzone AI: This year, AI in the SOC went from helping analysts to acting on its own.",
             "That is the story of the 2026 Gartner Hype Cycle™ for Security Operations.",
             vendor="Dropzone AI", published="2026-07-08"),
        _row(4, "Dropzone AI: Security operations is entering a structural reset.",
             "The Gartner Hype Cycle™ reveals a fast-moving industry, 2026 edition.",
             vendor="Dropzone AI", published="2026-06-17"),
    ]
    groups = mres.group_citations(rows)
    assert len(groups) == 1, [g["label"] for g in groups]
    g = groups[0]
    assert g["label"] == "Gartner Hype Cycle for Security Operations, 2026"
    assert [v["vendor"] for v in g["vendors"]] == ["Dropzone AI", "Backline AI", "Prophet Security"]
    # The vendor that cited it twice is counted once, with its newest record.
    assert g["vendors"][0]["uri"] == "https://x/3"
    assert g["latest"] == "2026-07-08"


def test_a_vendor_blog_is_named_like_its_posts_when_the_domain_is_known():
    row = _row(1, "Our Take on the 2026 Gartner Hype Cycle for Security Operations", "",
               uri="https://www.dropzone.ai/blog/hype-cycle", article_class="vendor")
    assert mres.cite(row)["vendor"] == "dropzone.ai"
    assert mres.cite(row, {"dropzone.ai": "Dropzone AI"})["vendor"] == "Dropzone AI"


def test_gartner_names_innovation_insights_with_a_colon():
    row = _row(1, "Thinking about adopting AI SOC Agents? In Gartner® Innovation Insight: AI SOC "
                  "Agents, Gartner highlights alternative approaches.", author="SANGFOR",
               article_class="discussion")
    c = mres.cite(row)
    assert c["family"] == "Innovation Insight" and c["topic"] == "AI SOC Agents"
    assert c["vendor"] == "@SANGFOR"
    assert mres.label_of(mres.group_citations([row])[0]) == "Gartner Innovation Insight: AI SOC Agents"


def test_research_without_a_family_is_titled_from_the_post():
    a = _row(1, "AiStrike: AiStrike is featured in new Gartner research, Domain-Specific Models "
                "Are the Future of AI Security Products", vendor="Aistrike", published="2026-08-13")
    b = _row(2, "Imperum: Imperum is featured again in new Gartner® research ✨",
             "\"Domain-Specific Models Are the Future of AI Security Products\" names Imperum.",
             vendor="Imperum", published="2026-08-12")
    groups = mres.group_citations([a, b])
    assert len(groups) == 1
    assert groups[0]["label"] == "Gartner: “Domain-Specific Models Are the Future of AI Security Products”"
    assert len(groups[0]["vendors"]) == 2


def test_summit_attendance_peer_insights_and_a_stray_statistic_are_not_research():
    assert mres.cite(_row(1, "AiStrike: Heading to the Gartner Security & Risk Management Summit "
                             "next week? Come meet the team at booth 4141.")) is None
    assert mres.cite(_row(2, "Intezer: Another Intezer AI SOC customer just shared their experience "
                             "on Gartner Peer Insights.")) is None
    assert mres.cite(_row(3, "Opnova: According to Forrester, inefficient sales order processes "
                             "significantly impact revenue.")) is None
    # "security leaders" is not "a Leader".
    assert mres.cite(_row(4, "Strike48: Security leaders told Gartner attendees what they think.")) is None


def test_a_post_that_names_no_report_folds_into_the_one_it_describes():
    """A vendor posts twice about one analyst mention and names the report
    series in only one of them. Both are the same report and belong in one
    group, or the panel prints the named report beside a bare
    "Gartner research" carrying the same news.

    The family-based reconciliation cannot reach this: it starts from the
    family and fills in a missing topic, so a post naming no family at all is
    invisible to it.
    """
    named = _row(1, "Kai: Gartner® named Kai a Sample Vendor in Autonomous Exposure Remediation "
                    "(AER) last week, in its Emerging Tech Impact Radar: Preemptive "
                    "Cybersecurity, 2028", vendor="Kai Security", published="2026-09-18")
    bare = _row(2, "Kai: Gartner® named Kai a Sample Vendor in Autonomous Exposure "
                   "Remediation last week.", vendor="Kai Security", published="2026-09-21")
    groups = mres.group_citations([named, bare])
    assert len(groups) == 1
    assert groups[0]["label"].startswith("Gartner Emerging Tech Impact Radar")
    # The later sighting is kept, so the panel dates the citation correctly.
    assert groups[0]["latest"] == "2026-09-21"


def test_two_firms_do_not_fold_into_each_other():
    """Shared subject words are not enough. A different firm is a different
    report however alike the sentences read."""
    g = _row(1, "Acme: Gartner named Acme a Sample Vendor in Autonomous Exposure Remediation, "
                "in its Emerging Tech Impact Radar: Preemptive Cybersecurity",
             vendor="Acme", published="2026-09-18")
    f = _row(2, "Acme: Forrester named Acme a Leader in Autonomous Exposure Remediation.",
             vendor="Acme", published="2026-09-19")
    labels = {x["label"] for x in mres.group_citations([g, f])}
    assert len(labels) == 2


def test_a_mention_that_names_no_report_is_not_listed():
    """"Gartner research" claimed a report the reader could not go and find.
    A vendor saying the firm's name is not a citation of anything."""
    rows = [
        _row(1, "Arambh Labs: Gartner named us one of 11 startups to watch in agentic AI.",
             vendor="Arambh Labs"),
        _row(2, "Gruve: Gartner just named AI-driven vulnerability discovery the top "
                "emerging risk, a first.", vendor="Gruve"),
    ]
    assert mres.group_citations(rows) == []


def test_a_stated_position_still_counts_without_a_named_report():
    """Dropping must not take the real recognitions with it. "a Leader" names
    something checkable even when the post never says which report."""
    row = _row(1, "Acme: Acme was named a Leader by Forrester this week.", vendor="Acme")
    groups = mres.group_citations([row])
    assert len(groups) == 1
    assert groups[0]["vendors"][0]["position"] == "Leader"


def test_a_family_only_mention_joins_the_one_report_of_that_year():
    rows = [
        _row(1, "Qevlar AI: No Gartner Hype Cycle for Security Operations goes by without Qevlar AI.",
             vendor="Qevlar", published="2026-06-17"),
        _row(2, "Simbian: our reading of the 2026 Gartner Hype Cycle.", vendor="Simbian",
             published="2026-06-21"),
        _row(3, "Acme: the 2026 Gartner Market Guide for AI SOC Agents names Acme.", vendor="Acme",
             published="2026-06-01"),
    ]
    groups = mres.group_citations(rows)
    labels = {g["label"]: [v["vendor"] for v in g["vendors"]] for g in groups}
    assert labels["Gartner Hype Cycle for Security Operations, 2026"] == ["Simbian", "Qevlar"]
    assert labels["Gartner Market Guide for AI SOC Agents, 2026"] == ["Acme"]
    # With no year either, "the Hype Cycle" still means the one the corpus
    # knows; with two Hype Cycle reports in the period it would stay apart.
    more = mres.group_citations(rows + [_row(4, "Beta: proud to be in the Hype Cycle again, "
                                                "says Gartner.", vendor="Beta", published="2026-06-02")])
    assert [v["vendor"] for v in more[0]["vendors"]] == ["Simbian", "Qevlar", "Beta"]
    two = mres.group_citations(rows + [
        _row(5, "Beta: proud to be in the Hype Cycle again, says Gartner.", vendor="Beta"),
        _row(6, "Gamma: named in the 2026 Gartner Hype Cycle for Agentic AI.", vendor="Gamma")])
    assert any(g["label"] == "Gartner Hype Cycle" and [v["vendor"] for v in g["vendors"]] == ["Beta"]
               for g in two)


def test_the_families_that_name_the_firm_do_not_repeat_it():
    row = _row(1, "Imperum: Did you know? Imperum was named a Leader in the GigaOm Radar for SecOps.",
               vendor="Imperum")
    g = mres.group_citations([row])[0]
    assert g["label"] == "GigaOm Radar for SecOps"
    assert g["vendors"][0]["position"] == "Leader"


def test_analyst_posts_come_from_the_firms_domains_and_drop_event_listings():
    market = {"id": 2, "name": "AI in the SOC", "config": {}}
    rows = [
        _row(1, "Announcing The Forrester Wave: XDR Platforms", uri="https://www.forrester.com/blogs/xdr/",
             article_class="news", published="2026-06-25"),
        _row(2, "Cyber MSSPs", uri="https://www.kuppingercole.com/research/bc80902/cyber-mssps",
             article_class="news", published="2026-08-17"),
        _row(3, "When AI Agents Don't Play Nice", uri="https://www.kuppingercole.com/watch/agents",
             article_class="news", published="2026-08-24"),
        _row(4, "Sep 22: The New Workforce Identity Challenge",
             uri="https://www.kuppingercole.com/events/new-workforce", article_class="news"),
        _row(5, "Dropzone AI: a post", vendor="Dropzone AI"),
    ]
    posts = mres.analyst_posts(rows, market)
    assert [(p["firm"], p["research_kind"]) for p in posts] == [
        ("KuppingerCole", "Webinar"), ("KuppingerCole", "Research"), ("Forrester", "Blog")]
    assert all(p["item"] == "post" for p in posts)
    assert html._river_source(posts[0]) == "KuppingerCole"


def test_feeds_default_until_the_market_sets_its_own():
    market = {"id": 2, "name": "x", "config": {}}
    assert [f["domain"] for f in mres.feeds(market)] == ["forrester.com", "kuppingercole.com"]
    assert mres.uses_defaults(market)
    own = {"id": 2, "name": "x", "config": {"analyst_feeds": [
        {"firm": "GigaOm", "url": "https://gigaom.com/feed/?post_type=go-report"}]}}
    assert mres.feeds(own) == [{"firm": "GigaOm", "url": "https://gigaom.com/feed/?post_type=go-report",
                                "domain": "gigaom.com"}]
    assert not mres.uses_defaults(own)
    assert mres.analyst_domains(own)["gigaom.com"] == "GigaOm"
    assert mres.analyst_domains(own)["gartner.com"] == "Gartner"


def test_the_section_renders_groups_with_marks_and_posts_with_their_kind():
    groups = mres.group_citations([
        _row(1, "Imperum: Imperum was named a Leader in the GigaOm Radar for SecOps.",
             vendor="Imperum", published="2026-08-26"),
        _row(2, "Backline AI: Gartner just dropped the 2026 Hype Cycle for Security Operations.",
             vendor="Backline AI", published="2026-06-23"),
    ])
    posts = mres.analyst_posts([
        _row(3, "Cyber MSSPs", uri="https://www.kuppingercole.com/research/bc80902/cyber-mssps",
             article_class="news", published="2026-08-17")], {"id": 2, "name": "x", "config": {}})
    logos = {"Imperum": "data:image/png;base64,AAAA"}
    out = html._v2_research(groups + posts, logos)
    assert "Reports vendors cite" in out and "From the analyst firms" in out
    assert "Named <a href=\"https://x/1\"><img class=\"v2-mark\"" in out
    assert "Imperum (Leader)</a>" in out
    assert "Cited by <a href=\"https://x/2\">Backline AI</a>" in out
    assert "KuppingerCole · Research · 17 Aug 2026" in out
    only_groups = html._v2_research(groups, logos)
    assert "Reports vendors cite" not in only_groups
    empty = html._v2_section("research", "", count=0, days=30, more_href="?view=v2&section=research")
    assert "No analyst report or post in the last 30 days" in empty
    assert "Research firms" in empty


@pytest.mark.skipif(os.getenv("DB_TYPE", "postgresql").lower() != "postgresql",
                    reason="the market queries are Postgres")
def test_sync_feeds_registers_and_switches_off_under_the_market_topic():
    from sqlalchemy import text
    try:
        from app.database import get_database_instance
        conn = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001 — no DB reachable, not a code failure
        pytest.skip(f"no database available: {exc}")
    try:
        mid = conn.execute(text("SELECT id FROM bw_markets ORDER BY id LIMIT 1")).scalar()
        if mid is None:
            pytest.skip("no market in this database")
        # A throwaway URL, so the run leaves nothing real behind: the row is
        # created, switched off when the list changes, and deleted at the end.
        url = "https://example.invalid/analyst-test/feed"
        market = {"id": mid, "name": "t", "config": {"analyst_feeds": [{"firm": "Test", "url": url}]}}
        r = mres.sync_feeds(conn, market)
        assert r["feeds"] == 1
        active = conn.execute(text("SELECT is_active, name FROM rss_feeds WHERE url = :u"), {"u": url}).fetchone()
        assert active[0] is True and active[1] == "Test (analyst)"
        mres.sync_feeds(conn, {"id": mid, "name": "t", "config": {"analyst_feeds": []}})
        assert conn.execute(text("SELECT is_active FROM rss_feeds WHERE url = :u"), {"u": url}).scalar() is False
    finally:
        conn.execute(text("DELETE FROM rss_feeds WHERE url = 'https://example.invalid/analyst-test/feed'"))
        conn.commit()
        conn.close()


def test_a_forecast_year_is_not_the_report_year():
    row = _row(1, "Backline: named a Sample Vendor in the Gartner Emerging Tech Impact "
                  "Radar: Preemptive Cybersecurity. Gartner expects AI agents to remediate "
                  "70% of vulnerabilities by 2028.", vendor="Backline AI",
               published="2026-09-15")
    assert mres.cite(row)["year"] != "2028"


def test_a_citer_outside_the_vendor_list_is_marked():
    tracked = mres.cite(_row(1, "Acme named a Leader in the 2026 Gartner Magic Quadrant "
                                "for SIEM", vendor="Acme"))
    handle = mres.cite(_row(2, "Named a Leader in the 2026 Gartner Magic Quadrant for SSE "
                               "and SASE", author="falconupkid", article_class="discussion"))
    assert tracked["tracked"] is True and handle["tracked"] is False


def test_a_quoted_report_title_is_read_to_its_end():
    row = _row(1, "Twine Security: proud to be mentioned in a Gartner report",
               "Twine was included in the 2026 Gartner 'Innovation Insight: Role Agents "
               "Have a Mandate, Not a Task List' report.", vendor="Twine Security")
    assert mres.group_citations([row])[0]["label"] == (
        "Gartner Innovation Insight: Role Agents Have a Mandate, Not a Task List, 2026")
