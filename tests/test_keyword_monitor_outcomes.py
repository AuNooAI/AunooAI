"""The keyword monitor tells an empty interval from a failed provider.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 1 and 20.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.collectors import contracts as c
from app.tasks import keyword_monitor as km


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_empty_success_says_no_new_articles():
    articles, messages = km.summarize_outcomes("acme", {"newsapi": c.CollectionResult.ok([])})
    assert articles == []
    assert messages == [("info", "No new articles for keyword: acme")]


def test_failed_provider_is_named_with_its_reason():
    outcomes = {
        "newsapi": c.CollectionResult.ok([{"url": "u1"}]),
        "newsdata": c.CollectionResult.failure(c.ERR_HTTP_5XX, "transient: HTTP 503 host=newsdata.io", retryable=True),
    }
    articles, messages = km.summarize_outcomes("acme", outcomes)
    assert [a["url"] for a in articles] == ["u1"]
    assert messages == [("error", "newsdata failed: transient: HTTP 503 host=newsdata.io")]
    assert not any("No new articles" in m for _, m in messages)


def test_quota_exhausted_is_recorded_not_raised():
    outcomes = {"newsapi": c.CollectionResult.quota_exhausted("newsapi"),
                "thenewsapi": c.CollectionResult.ok([])}
    articles, messages = km.summarize_outcomes("acme", outcomes)
    assert articles == []
    levels = dict((m.split(" ")[0], lvl) for lvl, m in messages)
    assert levels["newsapi"] == "warning"
    assert any(m.startswith("newsapi failed: newsapi quota exhausted") for _, m in messages)
    assert ("info", "No new articles for keyword: acme") in messages


def test_every_provider_failed_is_not_a_quiet_day():
    outcomes = {"newsapi": c.CollectionResult.failure(c.ERR_TIMEOUT, "timeout", retryable=True)}
    _, messages = km.summarize_outcomes("acme", outcomes)
    assert ("warning", "Every provider failed for keyword: acme") in messages
    assert not any("No new articles" in m for _, m in messages)


def _monitor():
    mon = km.KeywordMonitor.__new__(km.KeywordMonitor)
    mon.country = None
    mon.page_size = 10
    mon.search_fields = None
    mon.language = "en"
    mon.sort_by = None
    return mon


class _Collector:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.seen = None

    async def search_articles(self, query, topic, max_results=10, start_date=None, end_date=None, **kw):
        return []

    async def collect(self, query, topic, **kw):
        self.seen = kw
        if self.behaviour == "raise":
            raise ValueError("Rate limit exceeded: boom")
        if self.behaviour == "hang":
            await asyncio.sleep(5)
        if self.behaviour == "list":
            return [{"url": "u"}]
        return c.CollectionResult.ok([{"url": "u1"}], provider="fake")


def test_search_with_collector_returns_structured_outcomes(monkeypatch):
    mon = _monitor()
    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc)
    ok = run(mon._search_with_collector("fake", _Collector("ok"), "company:acme", "t", start, end, {"page": 2}))
    assert ok.succeeded and ok.items[0]["collector_source"] == "fake"
    assert ok.items[0]["_matched_keywords"] == ["acme"]
    failed = run(mon._search_with_collector("fake", _Collector("raise"), "acme", "t", start, end))
    assert failed.failed and failed.error_code == c.ERR_QUOTA and "Rate limit" in failed.error_message
    monkeypatch.setattr(km, "SEARCH_TIMEOUT_SECONDS", 0.05)
    slow = run(mon._search_with_collector("fake", _Collector("hang"), "acme", "t", start, end))
    assert slow.failed and slow.error_code == c.ERR_TIMEOUT and slow.retryable
    plain = run(mon._search_with_collector("fake", _Collector("list"), "acme", "t", start, end))
    assert plain.succeeded and plain.items == [{"url": "u", "collector_source": "fake", "_matched_keywords": ["acme"]}]
    assert plain.interval_start == start and plain.provider == "fake"
