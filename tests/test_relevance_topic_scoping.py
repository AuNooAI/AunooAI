"""The relevance verdict belongs to a topic.

An article matched by several groups is scored once per group. The row has
one topic and one score, so the two must move together (or not at all), a
rejecting topic must not demote a row another topic approved, and the LLM
auditor must judge against the topic's definition, not its bare label.
"""
import re

import pytest

from app.services import async_db as adb
from app.services.hybrid_relevance_service import HybridRelevanceService


def _sample(**over):
    d = {"uri": "u1", "title": "T", "summary": "S", "topic": "AI and Machine Learning",
         "topic_alignment_score": 0.9, "keyword_relevance_score": 0.6, "confidence_score": 1.0,
         "overall_match_explanation": "x", "ingest_status": "approved", "analyzed": True}
    d.update(over)
    return d


class TestEnrichmentUpdate:
    def test_placeholders_and_params_line_up(self):
        q, p = adb.build_enrichment_update(_sample())
        assert q.count("?") == len(p)
        assert q.endswith("WHERE uri = ?") and p[-1] == "u1"

    def test_the_topic_moves_with_the_verdict_and_only_then(self):
        q, _ = adb.build_enrichment_update(_sample())
        for col in ("topic", "topic_alignment_score", "keyword_relevance_score",
                    "confidence_score", "overall_match_explanation"):
            m = re.search(rf"{col} = CASE WHEN \((.*?)\) THEN \? ELSE articles\.{col} END", q)
            assert m, f"{col} is written unconditionally"
            cond = m.group(1)
            assert "IS DISTINCT FROM 'approved'" in cond
            assert "articles.topic = ?" in cond
            assert "COALESCE(articles.topic_alignment_score, 0)" in cond

    def test_enrichment_fields_are_always_written(self):
        q, _ = adb.build_enrichment_update(_sample())
        for col in ("category", "sentiment", "summary", "analyzed", "ingest_status"):
            assert re.search(rf"\b{col} = (\?|COALESCE\(\?, {col}\))", q), col
            assert f"{col} = CASE" not in q

    def test_verdict_params_carry_topic_score_value_in_that_order(self):
        q, p = adb.build_enrichment_update(_sample(topic="X", topic_alignment_score=0.7))
        i = q.index("topic = CASE")
        n_before = q[:i].count("?")
        assert p[n_before:n_before + 3] == ("X", 0.7, "X")

    def test_a_missing_score_compares_as_zero(self):
        _, p = adb.build_enrichment_update(_sample(topic_alignment_score=None))
        assert 0.0 in p and None in p


class TestBelowThresholdUpsert:
    def test_a_rejection_cannot_demote_another_topics_approved_row(self):
        import inspect
        src = inspect.getsource(adb.AsyncDatabaseManager.save_below_threshold_article) \
            if hasattr(adb, "AsyncDatabaseManager") else open(adb.__file__).read()
        assert "WHERE articles.topic = EXCLUDED.topic" in src
        assert "OR articles.ingest_status IS DISTINCT FROM 'approved'" in src


class TestAuditorPrompt:
    def _capture(self, monkeypatch, description):
        svc = HybridRelevanceService.__new__(HybridRelevanceService)
        seen = {}
        monkeypatch.setattr(svc, "_compute_external_llm_score",
                            lambda prompt: seen.setdefault("prompt", prompt) and 0.1)
        monkeypatch.setattr(svc, "_get_topic_description", lambda topic: description)
        svc._compute_llm_score("M&A Updates", "Musk hints at SpaceX, Tesla merger",
                               "Elon Musk said a merger is possible.", keywords=["merger"])
        return seen["prompt"]

    def test_the_definition_and_scope_rule_reach_the_auditor(self, monkeypatch):
        prompt = self._capture(monkeypatch, "Deals in scientific publishing and academia")
        assert "Topic definition: Deals in scientific publishing and academia" in prompt
        assert "SCOPE: the topic means what its definition says" in prompt
        assert "Key entities / search terms for this topic: merger" in prompt

    def test_no_definition_means_the_old_prompt(self, monkeypatch):
        prompt = self._capture(monkeypatch, None)
        assert "Topic definition" not in prompt and "SCOPE:" not in prompt

    def test_brand_topics_are_untouched(self, monkeypatch):
        svc = HybridRelevanceService.__new__(HybridRelevanceService)
        seen = {}
        monkeypatch.setattr(svc, "_compute_external_llm_score",
                            lambda prompt: seen.setdefault("prompt", prompt) and 0.1)
        svc._compute_llm_score("Brand Monitoring Wiley", "t", "s", keywords=["Wiley"])
        assert "relevance auditor for a brand monitor" in seen["prompt"]
        assert "Topic definition" not in seen["prompt"]
