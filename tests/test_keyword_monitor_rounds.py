"""Keyword monitor collection rounds (docs/pipelines/08_INGEST_FIX_SPEC.md, WP1).

The checkpoint store and the database are fakes; the collector returns real
``CollectionResult`` objects. What is checked here is the monitor's own
order of work: items are saved before a checkpoint moves, a failed save
keeps the interval, and a provider that stopped at its budget with a cursor
that moved gets follow-up rounds in the same check.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors.contracts import CollectionResult, TRUNC_TIME_BUDGET
from app.services.collection_runs import Checkpoint
from app.tasks import keyword_monitor as km

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class Store:
    """In-memory checkpoints with the commit rules that matter here."""

    def __init__(self):
        self.cont = None
        self.coverage = None
        self.commits = []
        self.claims = 0

    def claim(self, db, provider, scope_key, *, lookback, ignore_backoff=False, **kw):
        self.claims += 1
        return Checkpoint(provider, scope_key, NOW - lookback, NOW, self.coverage, self.cont, 1)

    def commit(self, db, cp, result, **kw):
        self.commits.append((result.status, list(db.facade.saved)))
        cp.progressed = bool(result.continuation) and result.continuation != cp.continuation
        if result.may_advance_checkpoint:
            self.coverage, self.cont, cp.advanced = cp.interval_end, None, True
        elif result.continuation:
            self.cont = result.continuation
        return True


class Facade:
    def __init__(self, fail_urls=()):
        self.saved = []
        self.fail_urls = set(fail_urls)

    def create_or_update_keyword_monitor_last_check(self, *a):
        return None

    def get_monitored_keywords_by_group_id(self, gid):
        return [{"id": 7, "keyword": "SOC", "last_checked": None, "topic": "T", "group_id": gid,
                 "group_name": "g"}]

    def get_keyword_group_with_settings(self, gid):
        return None

    def article_exists(self, args):
        return False

    def create_article(self, exists, url, article, topic, kid):
        if url in self.fail_urls:
            raise RuntimeError("insert failed")
        self.saved.append(url)
        return True, False, False

    def __getattr__(self, name):
        return lambda *a, **k: None


class Db:
    def __init__(self, facade):
        self.facade = facade


class PagedCollector:
    """Three budget-sized slices of one interval; the cursor is the slice."""
    requests_today = 0

    def __init__(self, slices=3):
        self.slices = slices
        self.calls = []

    async def collect(self, query, topic, *, continuation=None, **kw):
        n = int((continuation or {}).get("slice") or 0)
        self.calls.append(n)
        items = [{"url": f"https://x.test/{n}-{i}", "title": "t", "source": "x.test"} for i in range(2)]
        if n + 1 < self.slices:
            return CollectionResult.partial(items, truncated_reason=TRUNC_TIME_BUDGET,
                                            continuation={"slice": n + 1})
        return CollectionResult.ok(items)


def _monitor(monkeypatch, collector, facade, rounds=2):
    store = Store()
    monkeypatch.setattr(km, "claim_interval", store.claim)
    monkeypatch.setattr(km, "commit_interval", store.commit)
    monkeypatch.setattr(km, "record_run", lambda *a, **k: None)
    monkeypatch.setenv("COLLECTION_FOLLOWUP_ROUNDS", str(rounds))
    m = object.__new__(km.KeywordMonitor)
    m.db = Db(facade)
    m.collector = collector
    m.collectors = {"newsfirehose": collector}
    m.country = None
    m.language = "en"
    m.search_date_range = 7
    m.page_size = 10
    m.search_fields = None
    m.sort_by = "publishedAt"
    m.auto_ingest_service = None
    m._group_relevance_threshold = None
    m._group_context_applied = True
    monkeypatch.setattr(m, "should_auto_ingest", lambda: False, raising=False)
    monkeypatch.setattr(m, "_filter_by_source_country", lambda arts, kw: arts, raising=False)
    return m, store


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_followup_rounds_drain_a_budget_stop_in_one_check(monkeypatch):
    coll = PagedCollector(slices=3)
    m, store = _monitor(monkeypatch, coll, Facade(), rounds=2)
    run(m.check_keywords(group_id=1))
    assert coll.calls == [0, 1, 2]
    assert store.coverage == NOW and len(m.db.facade.saved) == 6
    # Every commit happened after that round's items were saved.
    assert [len(saved) for _status, saved in store.commits] == [2, 4, 6]


def test_rounds_are_bounded(monkeypatch):
    coll = PagedCollector(slices=10)
    m, store = _monitor(monkeypatch, coll, Facade(), rounds=1)
    run(m.check_keywords(group_id=1))
    assert coll.calls == [0, 1] and store.cont == {"slice": 2} and store.coverage is None


def test_a_failed_save_keeps_the_interval_for_replay(monkeypatch):
    coll = PagedCollector(slices=1)
    facade = Facade(fail_urls={"https://x.test/0-1"})
    m, store = _monitor(monkeypatch, coll, facade, rounds=2)
    run(m.check_keywords(group_id=1))
    assert store.coverage is None and store.commits[0][0] == "partial"
    # Next check: the same interval is collected again and the unsaved item lands.
    facade.fail_urls.clear()
    run(m.check_keywords(group_id=1))
    assert store.coverage == NOW and "https://x.test/0-1" in facade.saved


def test_the_matched_keyword_reaches_ingest(monkeypatch):
    m, store = _monitor(monkeypatch, PagedCollector(slices=1), Facade())
    seen = {}

    class Svc:
        async def process_articles_batch(self, articles, topic, keywords, **kw):
            seen["mk"] = [a.get("_matched_keywords") for a in articles]
            return {"processed": len(articles), "saved": 0, "errors": []}
    m.auto_ingest_service = Svc()
    monkeypatch.setattr(m, "should_auto_ingest", lambda: True, raising=False)
    out = run(m.auto_ingest_pipeline([{"url": "https://x.test/a", "title": "t", "_matched_keywords": ["SOC"]}],
                                     "T", ["SOC"], suppress_notifications=True))
    assert seen.get("mk") == [["SOC"]], out
