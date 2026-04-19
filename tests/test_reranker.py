"""Unit tests for app/retrieval/reranker.py.

The reranker is designed to be a drop-in on cosine-ordered candidate lists.
Tests cover the three shapes callers rely on:
  1. No-op when disabled → returns the input slice unchanged.
  2. Graceful degradation when the model fails to load → same no-op path.
  3. When enabled and a model is available → returns top_k in score order
     with ``rerank_score`` populated.

We monkeypatch the lazy loader (`_get_model`) with a fake model rather than
importing sentence-transformers, so the tests run on any CI worker without
the model cache.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.retrieval import reranker


# ── Helpers ────────────────────────────────────────────────────────────────


class _FakeModel:
    """Returns each candidate's ``rank_key`` float as its CE score.

    Lets tests assert the reranker actually re-orders results by the score
    it gets back from the model (not by the cosine order it received).
    """

    def __init__(self, score_by_text: dict[str, float]):
        self.score_by_text = score_by_text
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs, batch_size: int = 32, show_progress_bar: bool = False):
        self.calls.append(list(pairs))
        return [self.score_by_text.get(cand_text, 0.0) for _, cand_text in pairs]


def _enable(monkeypatch, model: Any | None):
    """Force the module-level flag on and inject a model (or None)."""
    monkeypatch.setattr(reranker, "RERANK_ENABLED", True)
    monkeypatch.setattr(reranker, "_model", model)
    monkeypatch.setattr(reranker, "_load_failed", False)
    if model is not None:
        monkeypatch.setattr(reranker, "_get_model", lambda: model)
    else:
        monkeypatch.setattr(reranker, "_get_model", lambda: None)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


# ── Tests ──────────────────────────────────────────────────────────────────


def test_overfetch_limit_disabled(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_ENABLED", False)
    assert reranker.overfetch_limit(10) == 10


def test_overfetch_limit_enabled(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_ENABLED", True)
    monkeypatch.setattr(reranker, "RERANK_OVERFETCH_FACTOR", 5)
    monkeypatch.setattr(reranker, "RERANK_MAX_CANDIDATES", 200)
    assert reranker.overfetch_limit(10) == 50
    # Ceiling applies
    assert reranker.overfetch_limit(1000) == 200
    # Floor: never asks for fewer than top_k
    monkeypatch.setattr(reranker, "RERANK_OVERFETCH_FACTOR", 0)
    assert reranker.overfetch_limit(10) == 10


def test_rerank_no_op_when_disabled(monkeypatch):
    monkeypatch.setattr(reranker, "RERANK_ENABLED", False)
    candidates = [{"id": i, "title": f"c{i}"} for i in range(5)]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=3))
    assert result == candidates[:3]
    assert all("rerank_score" not in c for c in result)


def test_rerank_no_op_when_model_unavailable(monkeypatch):
    _enable(monkeypatch, model=None)
    candidates = [{"id": i, "title": f"c{i}"} for i in range(5)]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=3))
    assert [c["id"] for c in result] == [0, 1, 2]
    assert all("rerank_score" not in c for c in result)


def test_rerank_empty_input(monkeypatch):
    _enable(monkeypatch, model=_FakeModel({}))
    assert _run(reranker.rerank(query="q", candidates=[], top_k=5)) == []


def test_rerank_empty_query(monkeypatch):
    """Empty/whitespace query should no-op rather than scoring garbage."""
    _enable(monkeypatch, model=_FakeModel({}))
    candidates = [{"id": 1, "title": "hi"}, {"id": 2, "title": "bye"}]
    result = _run(reranker.rerank(query="   ", candidates=candidates, top_k=1))
    assert result == candidates[:1]
    assert "rerank_score" not in result[0]


def test_rerank_zero_top_k(monkeypatch):
    _enable(monkeypatch, model=_FakeModel({"x": 1.0}))
    candidates = [{"title": "x"}]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=0))
    assert result == []


def test_rerank_reorders_and_scores(monkeypatch):
    """Cosine-order input [a,b,c,d]; model says d>b>c>a; top_k=2 → [d,b]."""
    fake = _FakeModel({"a": 0.1, "b": 0.7, "c": 0.3, "d": 0.9})
    _enable(monkeypatch, model=fake)

    candidates = [
        {"id": 1, "title": "a"},
        {"id": 2, "title": "b"},
        {"id": 3, "title": "c"},
        {"id": 4, "title": "d"},
    ]
    result = _run(reranker.rerank(
        query="q", candidates=candidates, top_k=2, text_key="title",
    ))
    assert [c["id"] for c in result] == [4, 2]
    assert result[0]["rerank_score"] == pytest.approx(0.9)
    assert result[1]["rerank_score"] == pytest.approx(0.7)
    # The model was called exactly once, with all 4 candidates paired to the query.
    assert len(fake.calls) == 1
    assert [p[0] for p in fake.calls[0]] == ["q", "q", "q", "q"]


def test_rerank_top_k_larger_than_pool(monkeypatch):
    """When top_k > candidate count, return all, still scored."""
    fake = _FakeModel({"a": 0.2, "b": 0.8})
    _enable(monkeypatch, model=fake)
    candidates = [{"title": "a"}, {"title": "b"}]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=10))
    assert [c["title"] for c in result] == ["b", "a"]
    assert all("rerank_score" in c for c in result)


def test_rerank_custom_text_fn(monkeypatch):
    """text_fn override lets callers combine fields (e.g. title+summary)."""
    fake = _FakeModel({"alpha / one": 0.9, "beta / two": 0.1})
    _enable(monkeypatch, model=fake)
    candidates = [
        {"title": "alpha", "summary": "one"},
        {"title": "beta", "summary": "two"},
    ]
    result = _run(reranker.rerank(
        query="q",
        candidates=candidates,
        top_k=2,
        text_fn=lambda c: f"{c['title']} / {c['summary']}",
    ))
    assert [c["title"] for c in result] == ["alpha", "beta"]


def test_rerank_falls_back_to_composed_text(monkeypatch):
    """When text_key is missing, compose from title/summary/content."""
    fake = _FakeModel({"t1. s1": 0.9, "t2. s2": 0.1})
    _enable(monkeypatch, model=fake)
    candidates = [
        {"title": "t1", "summary": "s1"},
        {"title": "t2", "summary": "s2"},
    ]
    result = _run(reranker.rerank(
        query="q", candidates=candidates, top_k=2, text_key="does_not_exist",
    ))
    assert [c["title"] for c in result] == ["t1", "t2"]


def test_rerank_inference_failure_is_graceful(monkeypatch):
    """If model.predict raises, we return cosine order unchanged."""

    class _Exploding:
        def predict(self, *a, **kw):
            raise RuntimeError("boom")

    _enable(monkeypatch, model=_Exploding())
    candidates = [{"id": i, "title": f"c{i}"} for i in range(3)]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=2))
    assert [c["id"] for c in result] == [0, 1]
    assert all("rerank_score" not in c for c in result)


def test_rerank_preserves_candidate_fields(monkeypatch):
    """Non-text fields on candidates must survive reranking."""
    fake = _FakeModel({"x": 0.5})
    _enable(monkeypatch, model=fake)
    candidates = [{"id": 42, "title": "x", "similarity": 0.77, "extra": {"foo": 1}}]
    result = _run(reranker.rerank(query="q", candidates=candidates, top_k=1))
    assert result[0]["id"] == 42
    assert result[0]["similarity"] == 0.77
    assert result[0]["extra"] == {"foo": 1}
    assert result[0]["rerank_score"] == pytest.approx(0.5)
