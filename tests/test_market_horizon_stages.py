"""Market Horizon stages and bands: the stage is the scale score cut in
four, the band is the momentum score cut in three, and the descriptions
carry the cuts."""
from app.services import market_horizon as hz


def test_stage_is_by_scale_only():
    cuts = {"stage_cuts": [25, 50, 75]}
    assert hz._tier(10, 95, cuts) == "emerging"
    assert hz._tier(25, 0, cuts) == "established"
    assert hz._tier(60, 0, cuts) == "innovators"
    assert hz._tier(75, 0, cuts) == "executors"


def test_band_is_by_momentum_only():
    cuts = {"band_cuts": [33, 67]}
    assert hz._band(0, cuts) == "holding"
    assert hz._band(33, cuts) == "growing"
    assert hz._band(90, cuts) == "accelerating"


def test_descriptions_carry_the_cuts_and_the_new_names():
    tiers = hz.tier_info({"stage_cuts": [20, 40, 80]})
    assert tiers["established"]["label"] == "Building"
    assert tiers["innovators"]["label"] == "Scaling"
    assert "20 to 40" in tiers["established"]["means"]
    assert "80 and over" in tiers["executors"]["means"]
    bands = hz.band_info({"band_cuts": [30, 60]})
    assert "under 30" in bands["holding"]["means"]
    assert "60 and over" in bands["accelerating"]["means"]


def test_report_offers_the_map_in_both_shapes():
    """The shared report draws the arc and the grid from the same vendors
    and lets the reader switch; the grid's momentum axis starts at a floor
    just below the lowest dot, never above 20."""
    from app.services import market_report_html as html
    rated = [{"brand_id": i, "vendor": f"V{i}", "scale": s, "momentum": m, "tier": "emerging", "band": "growing"}
             for i, (s, m) in enumerate([(10, 40), (60, 55), (90, 80)])]
    horizon = {"config": {"tiers": {}}, "rated": rated, "not_rated": [], "tiers": hz.tier_info({}),
               "bands": hz.band_info({}), "computed_at": "2026-08-28", "days": 90}
    out = html._horizon_section(horizon, None)
    assert out.count('<svg viewBox') == 2  # the two maps; stage icons are nested <svg>s
    assert 'data-view="arc"' in out and 'data-view="grid" hidden' in out
    assert html._momentum_floor(rated) == 20  # 40 - 3 = 37 -> 35, capped at 20
    assert html._momentum_floor([{"scale": 5, "momentum": 12}]) == 5
    grid = html._horizon_grid_svg(rated, None, {})
    assert grid.count('mm-hz-dot') == 3 and 'V1' in grid
    hidden = html._horizon_grid_svg(rated, {"V1"}, {})
    assert 'V2' not in hidden and hidden.count('mm-hz-dot') == 1


def test_a_crowded_map_opens_on_the_top_forty_with_a_switch_to_all():
    """Past forty rated vendors the map opens on the top forty by scale plus
    momentum, marks the rest ``data-tail`` on both shapes, and offers
    "Top 40 | All N"; a small map has no switch and no tail."""
    from app.services import market_report_html as html
    rated = [{"brand_id": i, "vendor": f"V{i}", "scale": 100 - i, "momentum": 50,
              "tier": "emerging", "band": "growing"} for i in range(45)]
    horizon = {"config": {"tiers": {}}, "rated": rated, "not_rated": [], "tiers": hz.tier_info({}),
               "bands": hz.band_info({}), "computed_at": "2026-08-28", "days": 90}
    out = html._horizon_section(horizon, None)
    assert '<div class="mm-hz mm-top">' in out
    assert 'data-show="top">Top 40<' in out and 'data-show="all">All 45<' in out
    assert out.count('data-tail="1"') == 10  # five vendors past forty, on two shapes
    assert 'data-rank="1"' in out and 'data-rank="45"' in out
    small = html._horizon_section({**horizon, "rated": rated[:3]}, None)
    assert 'class="mm-hz-show"' not in small and 'data-tail' not in small and '<div class="mm-hz">' in small
