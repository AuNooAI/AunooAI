"""The weekly LinkedIn post: parsing the model's bullets, and the lines the
code writes itself."""

from datetime import date

from app.services import market_weekly_post as mwp

_INDEX = {"A1": {"uri": "u1", "title": "Launch", "vendor": "Strike48"},
          "C2": {"uri": "u2", "title": "Partner news", "source": "SecurityWeek"}}


def test_parse_keeps_cited_bullets_and_strips_ids():
    content = """- Strike48 launched an appliance — fully air-gapped. [A1]
- A bullet that cites nothing we gave it. [A9]
- No citation at all.
* Exaforce signed KDDI as a partner. [C2] [A1]
SUMMARY: The specialists shipped for specific settings."""
    bullets, summary = mwp.parse(content, _INDEX)
    assert [b["text"] for b in bullets] == [
        "Strike48 launched an appliance, fully air-gapped.",
        "Exaforce signed KDDI as a partner."]
    assert [s["id"] for s in bullets[1]["sources"]] == ["C2", "A1"]
    assert summary == "The specialists shipped for specific settings."


def _row(rank, vendor, status, last_week, move=None, weeks_at_1=0):
    return {"rank": rank, "vendor": vendor, "status": status,
            "last_week": last_week, "move": move, "weeks_at_1": weeks_at_1}


_MARKET = {"name": "AI in the SOC",
           "config": {"chart": {"title": "Agentic SOC Top {n} Movers"}}}


def test_movers_line_says_what_moved():
    rows = [_row(1, "Exaforce", "up", 2, 1), _row(2, "7AI", "down", 1, -1),
            _row(3, "Small", "up", 5, 2), _row(4, "Mars", "up", 19, 15),
            _row(5, "Qevlar", "up", 16, 11), _row(6, "Mate", "down", 3 - 0, -3),
            _row(7, "Simbian", "new", None)]
    line = mwp.movers_line(_MARKET, {"week_start": date(2026, 9, 28), "rows": rows})
    assert line == ("On the Agentic SOC Top 7 Movers, Exaforce took #1 from 7AI. "
                    "Mars climbed 15 places to #4 and Qevlar 11 to #5. "
                    "Mate fell 3 places to #6. New this week: Simbian.")


def test_hiring_line_trend(monkeypatch):
    from app.services import market_analysis as man
    monkeypatch.setattr(man, "hiring", lambda conn, m: {
        "openings": 184, "by_vendor": [
            {"vendor": "7AI", "openings": 39}, {"vendor": "Kai Security", "openings": 21},
            {"vendor": "Qevlar", "openings": 21}, {"vendor": "Other", "openings": 2}]})
    line, total = mwp.hiring_line(None, 2, 193)
    assert total == 184
    assert line == ("We count 184 open roles across the vendors we track, down from "
                    "193 a week earlier, led by 7AI (39), Kai Security (21) and Qevlar (21).")
    assert "a week earlier" not in mwp.hiring_line(None, 2, None)[0]


def test_clean_removes_dashes():
    assert mwp._clean("A — B – C .") == "A, B, C."


def test_parse_drops_a_sentence_naming_a_vendor_its_source_is_not_about():
    index = {"A2": {"uri": "u", "title": "Exaforce: Exaforce is now on the CrowdStrike Marketplace.",
                    "vendor": "Exaforce"},
             "A3": {"uri": "v", "title": "Anvilogic Federated Search Adds SentinelOne Endpoint Data",
                    "vendor": "Anvilogic"}}
    vendors = {"Exaforce", "Exabeam", "Anvilogic", "SentinelOne", "CrowdStrike"}
    content = ("- Anvilogic added SentinelOne endpoint data to its Federated Search. [A3] "
               "Exabeam is now on the CrowdStrike Marketplace. [A2]")
    bullets, _ = mwp.parse(content, index, vendors)
    assert [b["text"] for b in bullets] == [
        "Anvilogic added SentinelOne endpoint data to its Federated Search."]
    assert [s["id"] for s in bullets[0]["sources"]] == ["A3"]


def test_parse_lead_sentence_and_sentence_cap():
    index = {f"A{i}": {"uri": f"u{i}", "title": f"V{i} news", "vendor": f"V{i}"} for i in range(1, 6)}
    vendors = {f"V{i}" for i in range(1, 6)}
    content = ("- Specialists signed partners. V1 signed X. [A1] V2 signed Y. [A2] "
               "V3 signed Z. [A3] V4 signed W. [A4]\n"
               "- V5 is great. Then V5 shipped. [A5]")
    bullets, _ = mwp.parse(content, index, vendors)
    assert bullets[0]["text"] == "Specialists signed partners. V1 signed X. V2 signed Y. V3 signed Z."
    assert bullets[1]["text"] == "Then V5 shipped."   # an uncited lead may not name a vendor


def test_parse_orders_by_kind_and_checks_summary():
    index = {"A1": {"uri": "u", "title": "V1 named Leader", "vendor": "V1"},
             "A2": {"uri": "v", "title": "V2 launched X", "vendor": "V2"}}
    content = ("- (5) V1 was named a Leader by IDC. [A1]\n"
               "- (1) V2 launched X in Japan. [A2]\n"
               "SUMMARY: The specialists launched products in Japan and the Middle East.")
    bullets, summary = mwp.parse(content, index, {"V1", "V2"})
    assert [b["text"][:2] for b in bullets] == ["V2", "V1"]
    assert summary is None
    _, ok = mwp.parse(content.replace(" and the Middle East", ""), index, {"V1", "V2"})
    assert ok == "The specialists launched products in Japan."
