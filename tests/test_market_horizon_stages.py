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
