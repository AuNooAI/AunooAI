"""The weekly vendor chart: movement, runs and the front page card."""

from datetime import date, timedelta

from app.services import market_chart as mc
from app.services.market_report_html import _ordinal, _trend_spark, _v2_chart

W1, W2, W3, W4 = (date(2026, 9, 7) + timedelta(days=7 * i) for i in range(4))


def _by_brand(rows):
    return {r["brand_id"]: r for r in rows}


def test_first_week_is_all_new():
    rows = mc.derive({W1: {1: 1, 2: 2}})
    assert [r["status"] for r in rows] == ["new", "new"]
    assert rows[0]["weeks_on"] == 1 and rows[0]["weeks_at_1"] == 1


def test_moves_new_and_reentry():
    history = {
        W1: {1: 1, 2: 2, 3: 3, 4: 4},
        W2: {1: 1, 3: 2, 2: 3},          # 4 drops off
        W3: {1: 1, 2: 2, 3: 3, 4: 4, 5: 5},
    }
    rows = _by_brand(mc.derive(history))
    assert rows[1]["status"] == "same" and rows[1]["move"] == 0
    assert rows[2]["status"] == "up" and rows[2]["move"] == 1
    assert rows[3]["status"] == "down" and rows[3]["move"] == -1
    assert rows[4]["status"] == "reentry" and rows[4]["last_week"] is None
    assert rows[5]["status"] == "new"
    assert rows[1]["weeks_at_1"] == 3 and rows[1]["weeks_on"] == 3
    assert rows[3]["peak"] == 2 and rows[4]["weeks_on"] == 2


def test_weeks_at_1_is_a_running_total():
    history = {W1: {1: 1, 2: 2}, W2: {2: 1, 1: 2}, W3: {1: 1, 2: 2}}
    rows = _by_brand(mc.derive(history))
    assert rows[1]["weeks_at_1"] == 2


def test_last_frozen_week_is_the_week_just_closed():
    # Week of Mon 28 Sep closes Sun 4 Oct; it freezes from Mon 5 Oct.
    assert mc.last_frozen_week(date(2026, 10, 4)) == date(2026, 9, 21)
    assert mc.last_frozen_week(date(2026, 10, 5)) == date(2026, 9, 28)
    assert mc.last_frozen_week(date(2026, 10, 11)) == date(2026, 9, 28)


def test_rank_rated_orders_by_momentum_then_scale():
    rated = [
        {"brand_id": 1, "vendor": "B", "momentum": 70.0, "scale": 10},
        {"brand_id": 2, "vendor": "A", "momentum": 80.0, "scale": 5},
        {"brand_id": 3, "vendor": "C", "momentum": 70.0, "scale": 20},
        {"brand_id": 4, "vendor": "Gone", "momentum": 99.0, "scale": 1},
        {"brand_id": None, "vendor": "No id", "momentum": 90.0},
    ]
    rows = mc.rank_rated(rated, skip={4}, size=2)
    assert [(r["brand_id"], r["rank"]) for r in rows] == [(2, 1), (3, 2)]


def test_ordinal():
    assert [_ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]


def _chart(n):
    rows = []
    for i in range(1, n + 1):
        rows.append({"brand_id": i, "vendor": f"Vendor {i}", "rank": i,
                     "last_week": i + 1 if i > 1 else 1,
                     "move": 1 if i > 1 else 0,
                     "status": "up" if i > 1 else "same",
                     "peak": 1, "weeks_on": 4,
                     "weeks_at_1": 3 if i == 1 else 0, "momentum": 80.4})
    return {"week_start": W4, "rows": rows}


def test_card_rows_and_toggle():
    html = _v2_chart(_chart(40))
    assert "Top 40 Movers" in html
    assert "3rd week at #1" in html
    assert "&#9650; 1" in html
    assert "Show 11–40" in html
    assert 'v2-chart-score">80<' in html
    assert "Last wk" in html and "Peak" in html
    assert html.count('class="v2-chart-row') == 40


def test_card_without_rest_has_no_toggle():
    html = _v2_chart(_chart(6))
    assert "Top 6 Movers" in html and "<details" not in html


def test_card_empty():
    assert _v2_chart({"week_start": None, "rows": []}) == ""


def test_compute_week_reads_the_newest_map_run_and_skips_acquired(monkeypatch):
    monkeypatch.setattr(mc, "acquired_ids", lambda conn, m: {4})
    seen = {}

    class _Res:
        def mappings(self):
            return self

        def first(self):
            return {"id": 77, "result": {"rated": [
                {"brand_id": 4, "vendor": "Gone", "momentum": 99.0},
                {"brand_id": 5, "vendor": "Kept", "momentum": 50.0}]}}

    class _Conn:
        def execute(self, stmt, params):
            seen["params"] = params
            return _Res()

    rows = mc.compute_week(_Conn(), 2, W1)
    assert [(r["brand_id"], r["rank"], r["horizon_id"]) for r in rows] == [(5, 1, 77)]
    assert seen["params"]["start"].isoformat().startswith("2026-09-07T00:00:00+02")
    assert seen["params"]["end"].date() == date(2026, 9, 14)


def test_card_metadata_line():
    chart = _chart(1)
    chart["rows"][0].update(stage="Executing", band_label="Accelerating",
                            drivers=["15 launches and partnerships"],
                            funded="Series A, Aug 2026")
    html = _v2_chart(chart)
    assert "3rd week at #1 · Executing · Accelerating" in html
    assert "15 launches and partnerships, raised Series A, Aug 2026" in html


def test_describe_picks_top_quarter_drivers_and_recent_funding():
    rated = {"tier": "executors", "band": "accelerating",
             "funded": {"date": "2026-08-07", "round": "Series A"},
             "inputs": {
                 "launches": {"value": 15.0, "percentile": 99.0},
                 "headcount_pct": {"value": 8.6, "percentile": 80.0},
                 "mentions": {"value": 17.0, "percentile": 70.0},
                 "posts": {"value": 99.0, "percentile": 100.0}}}
    d = mc.describe(rated, date(2026, 10, 4))
    assert d["stage"] == "Executing" and d["band_label"] == "Accelerating"
    assert d["drivers"] == ["15 launches and partnerships", "headcount +9%"]
    assert d["funded"] == "Series A, Aug 2026"
    assert mc.describe(rated, date(2027, 1, 30))["funded"] is None


def test_title_from_market_config():
    assert mc.title({"config": None}, 40) == "Top 40 Movers"
    cfg = {"chart": {"title": "Agentic SOC Top {n} Movers"}}
    assert mc.title({"config": cfg}, 40) == "Agentic SOC Top 40 Movers"
    assert mc.title({"config": '{"chart": {"title": "X {n}"}}'}, 12) == "X 12"


def test_card_trend_column_and_weeks_on_chart():
    chart = _chart(2)
    chart["rows"][0]["trend"] = [70.0, None, 78.0, 80.4]
    chart["rows"][1]["trend"] = [60.0, 65.0, 70.0, 72.0]
    html = _v2_chart(chart)
    assert "Trend, 4 wks" in html
    assert html.count('<svg class="v2-spark"') == 2
    assert "4th week on chart" in html
    assert "Momentum 70 → 80 over 4 weeks" in html


def test_spark_gap_and_empty():
    svg = _trend_spark([50.0, None, 60.0, 70.0], 50, 70)
    # the lone first point has no segment; the gap splits the line
    assert svg.count("<polyline") == 1
    assert _trend_spark([None, None], 0, 100) == ""


def test_post_enabled_flag():
    assert mc.post_enabled({"config": {"chart": {"linkedin_post": True}}})
    assert not mc.post_enabled({"config": {"chart": {"title": "x"}}})


def test_trend_spark_does_not_shadow_the_report_spark():
    # Both live in market_report_html; the later definition used to replace
    # the Analyst View's _spark(values, *, label=...) and 500 view=report.
    import inspect
    from app.services import market_report_html as mrh
    assert "label" in inspect.signature(mrh._spark).parameters
