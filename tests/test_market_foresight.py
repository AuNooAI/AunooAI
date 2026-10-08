"""The public Consensus and Three-Horizons pages of a market.

Pure parts here: config reading, the double-encoded payload, the strip
above the report. The page render itself is checked against the live
tenant (a DB test below that skips without one).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services import market_foresight as mf


def test_topic_and_profile_come_from_the_market_config():
    market = {"config": {"collection": {"topic_name": "T"}, "foresight": {"profile_id": "9"}}}
    assert mf.topic_for(market) == "T" and mf.profile_for(market) == 9
    assert mf.topic_for({"config": '{"collection": {"topic_name": "S"}}'}) == "S"
    assert mf.topic_for({"config": None}) is None and mf.profile_for({}) is None


def test_raw_output_unwraps_one_or_two_layers_of_json():
    assert mf._raw({"a": 1}) == {"a": 1}
    assert mf._raw('{"a": 1}') == {"a": 1}
    assert mf._raw('"{\\"a\\": 1}"') == {"a": 1}
    assert mf._raw("not json") == {} and mf._raw(None) == {}


def test_chrome_carries_the_site_bar_the_other_report_and_earlier_runs():
    run = {"id": "b", "created_at": datetime(2026, 9, 6)}
    history = [run, {"id": "a", "created_at": datetime(2026, 9, 2)}]
    head, top, foot = mf._chrome({"name": "M"}, "consensus", run, history, "/?view=v2")
    assert "DM Sans" in head and ".mm-news" in head
    assert 'class="mm-news mm-v2 mm-report"' in top and "Front page" in top
    assert "Three horizons" in top and "Three horizons" in foot
    assert 'page=consensus&run=b" aria-current="page">06 Sep 2026</a>' in top
    assert 'page=consensus&run=a">02 Sep 2026</a>' in top
    # One run: no runs row.
    _, top1, _ = mf._chrome({"name": "M"}, "horizons", run, [run], "/")
    assert 'aria-label="Runs"' not in top1


def test_restyle_swaps_palette_inside_styles_and_the_wiley_eyebrow():
    html = ('<style>a { color: #d6346c; } body { background: #f8fafc; }</style>'
            '<div class="eyebrow">WILEY HORIZONS · X</div><p>#d6346c stays in text</p>'
            '<div>Produced by AunooAI</div>')
    out = mf._restyle(html)
    assert "#c2298a" in out and "#f7f6f2" in out
    assert "<p>#d6346c stays in text</p>" in out          # only style blocks change
    assert "CYBERFUTURISTS · X" in out and "WILEY" not in out
    assert "By the Cyberfuturists, made using Aunoo" in out and "AunooAI" not in out


def test_session_cookie_needs_the_secret(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        mf._session_cookie("admin")
    monkeypatch.setenv("FLASK_SECRET_KEY", "x" * 32)
    assert "." in mf._session_cookie("admin")


def test_render_rejects_a_run_of_another_topic():
    from app.database import get_database_instance
    from sqlalchemy import text

    try:
        c = get_database_instance()._temp_get_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database available: {exc}")
    try:
        row = c.execute(text("SELECT id, name, config FROM bw_markets WHERE is_public LIMIT 1")).mappings().first()
        if not row or not mf.topic_for(dict(row)):
            pytest.skip("no public market with a collection topic")
        market = dict(row)
        with pytest.raises(LookupError):
            mf.render(c, "consensus", market, run_id="not-a-run")
        page = mf.render(c, "horizons", market)
        if page is None:
            pytest.skip("no horizons run stored for this market")
        assert b"Front page</a>" in page and b"<title>" in page
    finally:
        c.rollback()
        c.close()


def test_public_consensus_page_leaves_out_the_advice_to_the_profile_org():
    # The run's sections 7-9 and each insight's relevance line are written
    # for the organisational profile, which on a market site is the
    # publisher. aisocnews.com printed them as the publisher's business plan.
    from app.services.consensus_html import build_consensus_html

    payload = {
        "categories": [{
            "category_name": "Agentic SOC",
            "category_description": "Sources agree triage is automating.",
            "7_strategic_implications": "PUBLISHER-REVENUE-MODEL",
            "8_key_decision_windows": [{"action": "PUBLISHER-ACTION", "urgency": "high"}],
            "9_timeframe_analysis": {
                "immediate": "PUBLISHER-NOW",
                "key_milestones": [{"year": 2027, "milestone": "PUBLISHER-MILESTONE",
                                    "significance": "PUBLISHER-ACQUISITION"}],
            },
        }],
        "key_insights": [{"quote": "Triage works first.", "source": "Expert Consensus",
                          "relevance": "PUBLISHER-SHOULD"}],
    }
    public = build_consensus_html("AI in the SOC", payload, public=True).decode()
    assert "Sources agree triage is automating." in public
    assert "Triage works first." in public
    assert "PUBLISHER-" not in public

    operator = build_consensus_html("AI in the SOC", payload).decode()
    for marker in ("PUBLISHER-REVENUE-MODEL", "PUBLISHER-ACTION", "PUBLISHER-MILESTONE",
                   "PUBLISHER-SHOULD"):
        assert marker in operator


def test_refresh_skips_a_market_without_a_profile():
    # The tenant default profile belongs to another customer; a run made
    # with it would be published on this market's site.
    import asyncio
    market = {"id": 1830, "config": {"collection": {"topic_name": "EV"}}}
    assert asyncio.run(mf.refresh(None, market, datetime.now(), force=True)) == []


def test_public_horizons_cards_leave_out_the_action_window():
    from app.services.html_report_common import render_executive_summary_cards

    card = {"topic_title": "Platforms absorb the category",
            "opening_statement": "Sources expect consolidation.",
            "decision_fork": {"condition_a": {"condition": "Funding dries up",
                                              "outcome": "Two survivors"}},
            "action_window": {"assessment": {"timeframe": "0-6 months",
                                             "action": "PUBLISHER-TODO"}}}
    public = render_executive_summary_cards([card], public=True)
    assert "Two survivors" in public
    assert "PUBLISHER-TODO" not in public and "Your window" not in public
    assert "PUBLISHER-TODO" in render_executive_summary_cards([card])


def test_show_advice_is_off_unless_the_market_turns_it_on():
    assert mf.show_advice({"config": {}}) is False
    assert mf.show_advice({"config": {"foresight": {"profile_id": 9}}}) is False
    assert mf.show_advice({"config": '{"foresight": {"show_advice": true}}'}) is True
