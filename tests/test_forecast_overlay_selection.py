"""When several deck overlays claim one topic, the loader picks the one that
fits the run, not the first by filename (wileytest, Open Science, 6 Oct 2026)."""
import json
import os

from app.services import forecast_assessment_service as fas

TOPIC = "Open Science Transition Uncertainty"
RUN_SCENARIOS = [{"title": "New A"}, {"title": "New B"}, {"title": "New C"}]


def _write(dir_, name, mapping, mtime):
    p = dir_ / name
    p.write_text(json.dumps({"topic": TOPIC, "scenario_title_to_deck_key": mapping, "deck_scenarios": {}}))
    os.utime(p, (mtime, mtime))
    return p


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fas, "DECK_OVERLAY_DIR", tmp_path)
    # The stale file sorts first by name and is NEWER, so neither old rule saves us.
    _write(tmp_path, "open_science_deck_overlay.json", {"Old X": "k1", "Old Y": "k2"}, 2_000_000_000)
    _write(tmp_path, "open_science_transition_uncertainty_deck_overlay.json",
           {"New A": "k1", "New B": "k1", "New C": "k2"}, 1_900_000_000)


def test_overlay_that_maps_the_run_wins(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    got = fas._load_deck_overlay(TOPIC, RUN_SCENARIOS)
    assert "New A" in got["scenario_title_to_deck_key"]


def test_without_scenarios_the_newest_file_wins(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    got = fas._load_deck_overlay(TOPIC)
    assert "Old X" in got["scenario_title_to_deck_key"]


def test_single_overlay_is_returned_even_if_it_maps_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(fas, "DECK_OVERLAY_DIR", tmp_path)
    _write(tmp_path, "only_deck_overlay.json", {"Other": "k"}, 1_900_000_000)
    assert fas._load_deck_overlay(TOPIC, RUN_SCENARIOS)["scenario_title_to_deck_key"] == {"Other": "k"}


def test_unknown_topic_returns_empty(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert fas._load_deck_overlay("Nope", RUN_SCENARIOS) == {}
