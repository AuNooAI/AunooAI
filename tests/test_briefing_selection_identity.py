"""Briefing selection by one stable id (work package 31).

The six-articles newsletter resolver (news_feed_service) and the executive
briefing selection (executive_briefing_service) both take the model's pick by
its id and refuse a pick whose echoed uri or title names another candidate.
No model calls: litellm is replaced by a fake that returns scripted JSON.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.news_feed_service import NewsFeedService

CORPUS = [
    {"uri": "https://example.com/a0", "title": "First story about quantum computing hardware roadmaps"},
    {"uri": "https://example.com/a1", "title": "Second story about fusion energy pilot plants"},
    {"uri": "https://example.com/a2", "title": "Third story about chip export rules tightening"},
]


def _svc():
    return NewsFeedService.__new__(NewsFeedService)


# ---------------------------------------------------------------------------
# Resolver rules
# ---------------------------------------------------------------------------

def test_id_and_uri_disagreement_is_rejected_as_selection_mismatch():
    svc = _svc()
    pick = {"id": "a0", "uri": "https://example.com/a2", "title": CORPUS[2]["title"]}
    resolved, unresolved = svc._resolve_selected_articles([pick], CORPUS)
    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == NewsFeedService.UNRESOLVED_MISMATCH


def test_id_and_title_disagreement_is_rejected():
    svc = _svc()
    pick = {"id": "a0", "title": CORPUS[2]["title"] + " (Reuters, 2026-10-01)"}
    resolved, unresolved = svc._resolve_selected_articles([pick], CORPUS)
    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == NewsFeedService.UNRESOLVED_MISMATCH


def test_id_alone_resolves_and_a_garbled_uri_does_not_matter():
    svc = _svc()
    resolved, unresolved = svc._resolve_selected_articles(
        [{"id": "a1", "uri": "https://example.com/nope", "title": "whatever"}], CORPUS)
    assert [a["uri"] for a in resolved] == ["https://example.com/a1"] and unresolved == []


def test_no_selection_from_a_title_alone():
    svc = _svc()
    resolved, unresolved = svc._resolve_selected_articles(
        [{"uri": "https://example.com/garbled", "title": CORPUS[1]["title"]}], CORPUS)
    assert resolved == []
    assert unresolved[0]["_unresolved_reason"] == NewsFeedService.UNRESOLVED_NO_MATCH


def test_without_an_id_only_an_exact_uri_resolves():
    svc = _svc()
    resolved, _ = svc._resolve_selected_articles(
        [{"uri": "https://example.com/a2?utm_source=x", "title": "anything"}], CORPUS)
    assert [a["uri"] for a in resolved] == ["https://example.com/a2"]


def test_mismatch_counter_counts_only_mismatches():
    bad = [{"_unresolved_reason": "selection_mismatch"}, {"_unresolved_reason": "no_match"}]
    assert NewsFeedService._count_selection_mismatches(bad, [{"_unresolved_reason": "selection_mismatch"}]) == 2


# ---------------------------------------------------------------------------
# Retry once, then skip and count (six-articles report)
# ---------------------------------------------------------------------------

class _FakeLitellm:
    """Returns the scripted responses in order and keeps the messages sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def acompletion(self, **kwargs):
        self.calls.append(kwargs)
        text = self.responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _report_service(fake):
    svc = _svc()

    async def org_profile(_pid):
        return None

    async def make_article(data):
        return {"uri": data["uri"], "title": data.get("title")}

    async def fallback(*_a, **_k):
        raise AssertionError("fallback must not run")

    svc._get_organizational_profile = org_profile
    svc._build_six_articles_analyst_prompt = lambda *a, **k: "PROMPT"
    svc._create_six_article_from_analyst_data = make_article
    svc._create_fallback_six_articles = fallback
    svc._parse_six_articles_response = lambda text: json.loads(text)
    return svc


def _request():
    return SimpleNamespace(starred_articles=None, profile_id=None, persona="CEO",
                           article_count=2, topic="T", model="fake", user_id=None)


def _run(svc, fake):
    import litellm
    from datetime import datetime
    with patch.object(litellm, "acompletion", fake.acompletion), \
            patch("app.services.news_feed_service.resolve_litellm_call_params", lambda m: {"model": m}):
        return asyncio.run(svc._generate_six_articles_report(CORPUS, datetime(2026, 10, 1), _request()))


def test_a_mismatch_is_retried_once_and_the_replacement_is_used():
    first = json.dumps([
        {"id": "a0", "uri": "https://example.com/a2", "title": "x"},   # mismatch
        {"id": "a1", "title": "y"},
    ])
    second = json.dumps([{"id": "a2", "title": "z"}])
    fake = _FakeLitellm([first, second])
    svc = _report_service(fake)
    articles = _run(svc, fake)
    assert [a["uri"] for a in articles] == ["https://example.com/a1", "https://example.com/a2"]
    assert len(fake.calls) == 2, "exactly one retry"
    retry_text = fake.calls[1]["messages"][-1]["content"]
    assert "return only" in retry_text and "a0" in retry_text
    assert svc.last_selection_mismatches == 1


def test_a_second_mismatch_skips_the_slot_and_is_counted():
    first = json.dumps([
        {"id": "a0", "uri": "https://example.com/a2", "title": "x"},   # mismatch
        {"id": "a1", "title": "y"},
    ])
    second = json.dumps([{"id": "a2", "uri": "https://example.com/a0", "title": "z"}])  # mismatch again
    fake = _FakeLitellm([first, second])
    svc = _report_service(fake)
    articles = _run(svc, fake)
    assert [a["uri"] for a in articles] == ["https://example.com/a1"]
    assert len(fake.calls) == 2, "no third attempt"
    assert svc.last_selection_mismatches == 2


def test_prompt_asks_for_the_id_only():
    fake = _FakeLitellm([json.dumps([{"id": "a0", "title": "x"}, {"id": "a1", "title": "y"}])])
    svc = _report_service(fake)
    _run(svc, fake)
    system = fake.calls[0]["messages"][0]["content"]
    assert "do NOT return the URI" in system
    assert "- uri (string - REQUIRED" not in system
    assert svc.last_selection_mismatches == 0


# ---------------------------------------------------------------------------
# Executive briefing selection
# ---------------------------------------------------------------------------

def _ebs():
    from app.services.executive_briefing_service import ExecutiveBriefingService
    return ExecutiveBriefingService.__new__(ExecutiveBriefingService)


RAW = [
    {"uri": "https://example.com/r0", "title": "Zero story about regulators and pilots"},
    {"uri": "https://example.com/r1", "title": "One story about chips and export rules"},
    {"uri": "https://example.com/r2", "title": "Two story about fusion plant financing"},
]


def test_ebs_valid_index_with_matching_echo_is_kept():
    ok, bad = _ebs()._validate_selection(
        [{"article_index": 1, "url": RAW[1]["uri"], "title": RAW[1]["title"]}], RAW)
    assert [p["article_index"] for p in ok] == [1] and bad == []


def test_ebs_index_and_url_disagreement_is_a_selection_mismatch():
    ok, bad = _ebs()._validate_selection([{"article_index": 1, "url": RAW[2]["uri"]}], RAW)
    assert ok == [] and bad[0]["_rejected"] == "selection_mismatch"


def test_ebs_index_and_title_disagreement_is_a_selection_mismatch():
    ok, bad = _ebs()._validate_selection([{"article_index": 0, "title": RAW[2]["title"]}], RAW)
    assert ok == [] and bad[0]["_rejected"] == "selection_mismatch"


def test_ebs_out_of_range_or_non_integer_index_is_dropped_not_guessed():
    ok, bad = _ebs()._validate_selection(
        [{"article_index": 7, "title": RAW[0]["title"]}, {"article_index": "a1", "url": RAW[1]["uri"]}], RAW)
    assert ok == [] and bad == [], "a title or url never stands in for a bad index"


def test_ebs_second_mismatch_skips_the_slot_and_is_counted():
    from app.services.executive_briefing_service import EBState

    svc = _ebs()
    svc._load_agent_prompt = lambda name: "SYS"
    svc._get_agent_config = lambda name: {}
    svc._get_persona_config = lambda *a, **k: {}
    state = EBState(scan_id="s", topic="T", persona="CEO", raw_articles=RAW)
    config = SimpleNamespace(persona="CEO", custom_persona=None, article_count=2,
                             selection_model="fake", selection_temp=0.3)
    first = json.dumps({"selected_articles": [
        {"article_index": 0, "url": RAW[2]["uri"]},            # mismatch
        {"article_index": 1, "url": RAW[1]["uri"]},
    ]})
    second = json.dumps({"selected_articles": [{"article_index": 2, "url": RAW[0]["uri"]}]})  # mismatch again
    fake = _FakeLitellm([first, second])
    with patch("app.services.executive_briefing_service.litellm.acompletion", fake.acompletion), \
            patch("app.services.executive_briefing_service.resolve_litellm_call_params", lambda m: {"model": m}), \
            patch("app.services.executive_briefing_service.extract_json_response", json.loads):
        asyncio.run(svc._run_selection(state, config))
    assert [p["article_index"] for p in state.selected_articles] == [1]
    assert state.selection_mismatches == 2
    assert len(fake.calls) == 2
    assert "article_index" in fake.calls[1]["messages"][-1]["content"]


@pytest.mark.parametrize("bad_index", [-1, 99, "x"])
def test_ebs_analysis_skips_bad_indices(bad_index):
    """``_run_analysis`` must not index the corpus with whatever it was handed."""
    import inspect
    from app.services.executive_briefing_service import ExecutiveBriefingService
    src = inspect.getsource(ExecutiveBriefingService._run_analysis)
    assert "article_index < 0 or article_index >= len(state.raw_articles)" in src
    assert "int(article_index)" in src
