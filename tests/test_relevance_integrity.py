"""Relevance integrity: invalid evidence cannot decide, and no evidence is not
a reject. Pure-function tests; no models, no database, no provider calls."""
from __future__ import annotations

import asyncio
import importlib.util
import math
import os

import pytest

from app.services import hybrid_relevance_service as hrs
from app.services import relevance_scorer as rsc
from app import relevance as rel


# --- number parsing -----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("0.2", 0.2), ("Score: 0.85", 0.85), (".2", 0.2), ("1e-3", 0.001),
    ("1", 1.0), ("0", 0.0), ("Score:\n0.75\n", 0.75),
])
def test_parse_unit_score_reads_real_numbers(text, expected):
    assert hrs.parse_unit_score(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["2.0", "8/10", "-0.1", "", None, "nan", "inf", "no number here", "1.5e2"])
def test_parse_unit_score_rejects_out_of_range_and_unreadable(text):
    assert hrs.parse_unit_score(text) is None


@pytest.mark.parametrize("value,expected", [
    (0.5, 0.5), (1, 1.0), (0, 0.0), (True, None), (False, None), (2.0, None),
    (float("inf"), None), (float("nan"), None), ("0.5", None), (None, None),
])
def test_unit_value(value, expected):
    assert hrs.unit_value(value) == expected


def test_unit_value_upper_bound_for_ordinal_scores():
    assert hrs.unit_value(1.5, upper=2.0) == 1.5
    assert hrs.unit_value(2.5, upper=2.0) is None


def test_old_clamp_turned_nan_into_a_perfect_score():
    # The behaviour the validators replace.
    assert max(0.0, min(1.0, float("nan"))) == 1.0


# --- brand detection ---------------------------------------------------------

@pytest.mark.parametrize("topic,name", [
    ("Brand Monitoring Wiley", "Wiley"), ("Wiley - Brand Watch", "Wiley"),
    ("Brand Monitoring Second Nature", "Second Nature"), ("Oviva - Brand Watch", "Oviva"),
    ("brand monitoring wiley", "wiley"),
])
def test_brand_name_from_both_naming_conventions(topic, name):
    assert hrs.brand_name_from_topic(topic) == name
    assert hrs.is_brand_topic(topic)


@pytest.mark.parametrize("topic", ["Market Monitoring SOC Automation", "Geopolitics", "", None, "Brand Monitoring"])
def test_non_brand_topics(topic):
    assert hrs.brand_name_from_topic(topic) is None
    assert not hrs.is_brand_topic(topic)


# --- Jev parser ----------------------------------------------------------------

def _svc():
    svc = hrs.HybridRelevanceService()
    svc._embedding_loaded = False
    svc._classifier_loaded = False
    return svc


def _jev_reply(noul, score, confidence=0.9):
    return {"model": "jev-test", "answers": {
        "on_topic": {"noul": noul},
        "alignment": {"score": score, "confidence": confidence},
    }, "usage": {}}


@pytest.mark.parametrize("noul,score", [
    (2.0, 1), (float("inf"), 1), (-0.5, 1), (True, 1), ("0.9", 1),
    (0.9, float("nan")), (0.9, 5), (0.9, -1), (0.9, True),
])
def test_jev_out_of_range_answers_are_ignored(monkeypatch, noul, score):
    from app.services import typesafe_client
    monkeypatch.setattr(typesafe_client, "is_configured", lambda: True)
    monkeypatch.setattr(typesafe_client, "system_one", lambda *a, **k: _jev_reply(noul, score))
    assert _svc()._compute_jev_shadow("Geopolitics", "t", "s") is None


def test_jev_valid_answer_is_read(monkeypatch):
    from app.services import typesafe_client
    monkeypatch.setattr(typesafe_client, "is_configured", lambda: True)
    monkeypatch.setattr(typesafe_client, "system_one", lambda *a, **k: _jev_reply(0.85, 2, 0.7))
    out = _svc()._compute_jev_shadow("Geopolitics", "t", "s")
    assert out["jev_on_topic"] == 0.85 and out["jev_confidence"] == 0.7
    assert 0.0 <= out["jev_score"] <= 1.0


def test_jev_nan_confidence_is_ignored(monkeypatch):
    from app.services import typesafe_client
    monkeypatch.setattr(typesafe_client, "is_configured", lambda: True)
    monkeypatch.setattr(typesafe_client, "system_one", lambda *a, **k: _jev_reply(0.9, 1, float("nan")))
    assert _svc()._compute_jev_shadow("Geopolitics", "t", "s") is None


# --- no engines is not a reject ------------------------------------------------

def _no_engines(monkeypatch):
    svc = _svc()
    monkeypatch.setattr(svc, "_load_embedding_model", lambda: False)
    monkeypatch.setattr(svc, "_load_classifier", lambda: False)
    monkeypatch.setattr(hrs, "JEV_ACCEPT", False)
    monkeypatch.setattr(hrs, "JEV_SHADOW", False)
    monkeypatch.setattr(hrs, "USE_CE_TIER", False)
    return svc


def test_no_engines_and_no_fallback_is_unavailable(monkeypatch):
    svc = _no_engines(monkeypatch)
    r = svc.score_relevance("Geopolitics", "t", "s", threshold=0.45, use_llm_fallback=False)
    assert r["status"] == "unavailable"
    assert r["relevant"] is None
    assert r["method"] == "none"


def test_no_engines_runs_the_llm_fallback(monkeypatch):
    svc = _no_engines(monkeypatch)
    monkeypatch.setattr(svc, "_compute_llm_score", lambda *a, **k: 0.9)
    r = svc.score_relevance("Geopolitics", "t", "s", threshold=0.45, use_llm_fallback=True)
    assert r["status"] == "ok" and r["relevant"] is True
    assert r["method"].endswith("llm_fallback")


def test_no_engines_and_failed_fallback_is_unavailable(monkeypatch):
    svc = _no_engines(monkeypatch)
    monkeypatch.setattr(svc, "_compute_llm_score", lambda *a, **k: None)
    r = svc.score_relevance("Geopolitics", "t", "s", threshold=0.45, use_llm_fallback=True)
    assert r["status"] == "unavailable" and r["relevant"] is None


# --- research scorer -------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [(0.7, 0.7), (1, 1.0), (True, None), (1.7, None), (float("nan"), None), ("0.7", None), (None, None)])
def test_research_unit(value, expected):
    assert rsc._unit(value) == expected


def test_research_failed_batches_are_kept_and_flagged(monkeypatch):
    scorer = rsc.RelevanceScorer(rsc.RelevanceScoringConfig(relevance_threshold=0.6, batch_size=2))

    async def fake_batch(batch, query, objectives, batch_idx):
        if batch_idx == 0:
            raise RuntimeError("provider down")
        for a in batch:
            a["relevance_score"] = 0.2 if a["title"] == "low" else 0.9
        return batch

    monkeypatch.setattr(scorer, "_score_batch", fake_batch)
    articles = [{"title": "a"}, {"title": "b"}, {"title": "low"}, {"title": "high"}]
    out = asyncio.run(scorer.score_articles(articles, "q", [], filter_below_threshold=True))
    titles = {a["title"] for a in out}
    assert titles == {"a", "b", "high"}          # "low" filtered; failed ones kept
    assert all(a.get("relevance_status") == "unavailable" and a["relevance_score"] is None
               for a in out if a["title"] in {"a", "b"})
    assert out[0]["title"] == "high"             # unscored sort last


# --- RelevanceCalculator parser ------------------------------------------------------

def test_calculator_unit_score():
    assert rel._unit_score({"x": 0.3}, "x") == 0.3
    assert rel._unit_score({}, "x", default=0.0) == 0.0
    for bad in ({}, {"x": True}, {"x": float("nan")}, {"x": 1.7}, {"x": "0.3"}, {"x": float("inf")}):
        with pytest.raises(ValueError):
            rel._unit_score(bad, "x")


# --- regression harness ----------------------------------------------------------------

def _harness():
    path = os.path.join(os.path.dirname(__file__), "..", "eval", "relevance_regression", "run.py")
    spec = importlib.util.spec_from_file_location("relevance_regression_run", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_harness_empty_run_is_inconclusive_not_perfect():
    h = _harness()
    acc, prec, rec, cm = h.metrics([])
    assert (acc, prec, rec) == (None, None, None)
    assert not h.conclusive(acc, prec, rec)


def test_harness_no_positive_support_is_inconclusive():
    h = _harness()
    acc, prec, rec, _ = h.metrics([(False, False), (False, False)])
    assert acc == 1.0 and prec is None and rec is None
    assert not h.conclusive(acc, prec, rec)


def test_harness_normal_run_is_conclusive():
    h = _harness()
    acc, prec, rec, _ = h.metrics([(True, True), (False, True), (True, False), (False, False)])
    assert h.conclusive(acc, prec, rec) and prec == 0.5 and rec == 0.5
