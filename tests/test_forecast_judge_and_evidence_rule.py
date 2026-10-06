"""Forecast assessment: Jev judges each pair, and a verdict needs enough
evidence and enough time since the forecast."""
import asyncio

from app.services import forecast_assessment_service as fas
from app.services import typesafe_client


def _label(**kw):
    base = dict(n_confident=10, directional_rate=0.8, velocity=3.0, milestone_density=0.5,
                coverage=2.0, state_only=0, supports=8, directional_stories=8, elapsed_days=60)
    base.update(kw)
    return fas._decide_verdict_label(**base)


def test_enough_evidence_and_time_gives_a_verdict():
    assert _label() == "Accelerating"


def test_two_supporting_stories_are_inconclusive():
    assert _label(supports=2, directional_stories=2) == "Inconclusive"


def test_fifteen_days_in_is_inconclusive():
    assert _label(elapsed_days=15) == "Inconclusive"


def test_old_callers_without_the_new_arguments_still_work():
    assert fas._decide_verdict_label(n_confident=10, directional_rate=0.8, velocity=3.0,
                                     milestone_density=0.5, coverage=2.0, state_only=0,
                                     supports=8) == "Accelerating"


SCENARIO = {"type": "h1", "title": "Siloed care persists", "description": "x", "timeframe": "2025-2030"}
ARTICLE = {"title": "Insurer merges dental and medical benefits", "summary": "y",
           "submission_date": "2026-10-01T10:00:00"}


def _jev(monkeypatch, response):
    monkeypatch.setattr(typesafe_client, "is_configured", lambda: True)
    monkeypatch.setattr(typesafe_client, "system_one", lambda *a, **k: response)
    return asyncio.run(fas._classify_with_jev(forecast_iso="2026-09-21", scenario=SCENARIO, article=ARTICLE))


def test_jev_less_likely_maps_to_contradicts(monkeypatch):
    out = _jev(monkeypatch, {"answers": {
        "effect": {"choice": "less_likely",
                   "probabilities": {"more_likely": 0.05, "less_likely": 0.9, "no_bearing": 0.05}},
        "evidence_type": {"choice": "milestone"}}})
    assert out["verdict"] == "contradicts"
    assert out["evidence_type"] == "milestone"
    assert out["confidence"] == 0.9


def test_jev_failure_returns_none_so_the_llm_takes_over(monkeypatch):
    assert _jev(monkeypatch, None) is None


def test_jev_unknown_choice_returns_none(monkeypatch):
    assert _jev(monkeypatch, {"answers": {"effect": {"choice": "maybe"}}}) is None


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(typesafe_client, "is_configured", lambda: False)
    assert asyncio.run(fas._classify_with_jev(forecast_iso="2026-09-21", scenario=SCENARIO, article=ARTICLE)) is None
