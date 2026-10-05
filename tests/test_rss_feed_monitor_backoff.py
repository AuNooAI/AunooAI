"""RSSFeedMonitor: backoff, storage outcomes, validators and checkpoints.

Work packages 1, 16 and 21 of docs/COLLECTOR_DATA_QUALITY_SPEC.md. The
database is a fake whose connection records every statement; the
collector is a stub that returns a prepared CollectionResult. Nothing
touches the network or the tenant database.
"""
from __future__ import annotations

import asyncio
import socket
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Insert, Update
from sqlalchemy.sql.elements import TextClause

from app.collectors import contracts as c
from app.collectors import rss_collector
from app.tasks import rss_feed_monitor as rfm

FEED_URL = "https://feeds.example.test/rss.xml"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.rowcount = 1

    def fetchone(self):
        return self.rows[0] if self.rows else (1,)

    def fetchall(self):
        return list(self.rows)


class FakeConn:
    def __init__(self, db):
        self.db = db

    def execute(self, stmt, params=None):
        self.db.statements.append((stmt, params))
        if isinstance(stmt, Insert) and stmt.table.name == "articles":
            uri = stmt.compile(dialect=postgresql.dialect()).params.get("uri")
            self.db.inserted_uris.append(uri)
            if uri in self.db.fail_uris:
                raise RuntimeError("deadlock detected")
        if isinstance(stmt, TextClause):
            sql = str(stmt)
            if "FROM pending_feed_entries" in sql:
                return FakeResult(self.db.pending_rows)
            if "INSERT INTO collection_runs" in sql:
                return FakeResult([(7,)])
        return FakeResult()

    def commit(self):
        self.db.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeFacade:
    def __init__(self, existing=()):
        self.existing = set(existing)

    def article_exists(self, params):
        return params[0] in self.existing


class FakeDb:
    def __init__(self, existing=(), fail_uris=(), pending_rows=None):
        self.statements = []
        self.inserted_uris = []
        self.commits = 0
        self.fail_uris = set(fail_uris)
        self.pending_rows = pending_rows or []
        self.facade = FakeFacade(existing)

    def _temp_get_connection(self):
        return FakeConn(self)

    # -- what the test reads back ------------------------------------------

    def feed_updates(self):
        out = []
        for stmt, _ in self.statements:
            if isinstance(stmt, Update) and stmt.table.name == "rss_feeds":
                out.append(stmt.compile(dialect=postgresql.dialect()).params)
        return out

    def last_feed_update(self):
        ups = self.feed_updates()
        assert ups, "no rss_feeds UPDATE was issued"
        return ups[-1]

    def article_inserts(self):
        return [stmt.compile(dialect=postgresql.dialect()).params
                for stmt, _ in self.statements
                if isinstance(stmt, Insert) and stmt.table.name == "articles"]

    def text_statements(self, needle):
        return [(str(stmt), params) for stmt, params in self.statements
                if isinstance(stmt, TextClause) and needle in str(stmt)]


class FakeHostGuard:
    blocked = None
    calls = []

    def __init__(self, host, **kw):
        self.host = host

    def check(self):
        return FakeHostGuard.blocked

    def rate_limited(self, retry_after=None):
        FakeHostGuard.calls.append(retry_after)
        return NOW + timedelta(minutes=5)


def _feed(**over):
    feed = {
        "id": 42, "url": FEED_URL, "topic": "AI", "name": "Example",
        "check_interval": 60, "interval_unit": "minutes",
        "relevance_threshold": 0, "default_factual_reporting": None,
        "last_checked_at": None, "last_article_date": None,
        "consecutive_error_count": 0, "polling_status": "ok",
        "first_failed_at": None, "last_failed_at": None, "next_poll_at": None,
        "coverage_through": None, "etag": None, "last_modified": None,
        "parse_partial_count": 0, "needs_attention_reason": None,
    }
    feed.update(over)
    return feed


def _article(n, pub="2026-08-14T09:07:52+00:00"):
    return {"title": f"Entry {n}", "summary": "s", "url": f"https://x.test/{n}",
            "source": "T", "topic": "AI", "published_date": pub,
            "published_at_raw": pub, "publication_date_precision": "second" if pub else None,
            "date_provenance": "feed" if pub else "unknown", "raw_data": {}}


def _ok(items, **kw):
    res = c.CollectionResult.ok(items, provider="rss", scope=FEED_URL, **kw)
    res.started_at = NOW
    res.interval_end = NOW
    return res


def _http_failure(status, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    response = httpx.Response(status, text="x", headers=headers, request=httpx.Request("GET", FEED_URL))
    exc = httpx.HTTPStatusError("bad", request=response.request, response=response)
    res = c.CollectionResult.from_exception(exc, host="feeds.example.test", provider="rss", scope=FEED_URL)
    res.diagnostics["http_status"] = status
    if retry_after:
        res.diagnostics["retry_after"] = retry_after
    return res


def _timeout():
    exc = httpx.ReadTimeout("", request=httpx.Request("GET", FEED_URL))
    return c.CollectionResult.from_exception(exc, host="feeds.example.test", provider="rss", scope=FEED_URL)


@pytest.fixture
def monitor(monkeypatch):
    """A monitor over a fake db, with every outside call stubbed. The
    collector's answer is ``monitor.next_result``; run records and
    enrichment calls are captured."""
    db = FakeDb()
    mon = rfm.RSSFeedMonitor(db)
    mon.next_result = _ok([])
    mon.runs = []
    mon.enriched_with = []
    mon.collector_calls = []

    class StubCollector(rss_collector.RSSCollector):
        async def fetch_feed_result(self_, feed_url, topic="", since=None, etag=None,
                                    last_modified=None, max_entries=None, client=None):
            mon.collector_calls.append({"etag": etag, "last_modified": last_modified, "since": since})
            return mon.next_result

    async def no_english(record):
        return None

    async def fake_ingest(articles, topic, relevance_threshold=None, default_factual_reporting=None):
        mon.enriched_with.append(list(articles))
        return 0

    def fake_record_run(db_, result, *, scope_kind=None, scope_id=None,
                        checkpoint_before=None, checkpoint_after=None):
        mon.runs.append({"result": result, "scope_kind": scope_kind, "scope_id": scope_id,
                         "before": checkpoint_before, "after": checkpoint_after})
        return 1

    FakeHostGuard.blocked = None
    FakeHostGuard.calls = []
    monkeypatch.setattr(rfm, "RSSCollector", StubCollector)
    monkeypatch.setattr(rfm, "HostGuard", FakeHostGuard)
    monkeypatch.setattr(rfm, "record_run", fake_record_run)
    monkeypatch.setattr(rss_collector, "restamp_check_enabled", lambda: False)
    monkeypatch.setattr(rfm.RSSFeedMonitor, "_english", staticmethod(no_english))
    monkeypatch.setattr(mon, "_resolve_countries", lambda articles: {})
    monkeypatch.setattr(mon, "_run_auto_ingest", fake_ingest)
    return mon


def _poll(mon, feed):
    return asyncio.run(mon.fetch_feed(feed))


def _apply(feed, values):
    """Feed the written row back as the next poll's input."""
    for k, v in values.items():
        if k in feed and not k.startswith("articles_"):
            feed[k] = v
    return feed


# ---------------------------------------------------------------------------
# Work package 21: backoff maths
# ---------------------------------------------------------------------------


def test_backoff_doubles_and_saturates_at_eight_times():
    base = timedelta(minutes=60)
    assert [rfm.backoff_delay(base, n) for n in (1, 2, 3, 4, 5, 20)] == [
        base, base * 2, base * 4, base * 8, base * 8, base * 8]


def test_hard_failures_are_403_404_410_dns_parse_not_timeouts_5xx_429():
    assert rfm.is_hard_failure(_http_failure(403))
    assert rfm.is_hard_failure(_http_failure(404))
    assert rfm.is_hard_failure(_http_failure(410))
    assert rfm.is_hard_failure(c.CollectionResult.from_exception(socket.gaierror("Name or service not known")))
    assert rfm.is_hard_failure(c.CollectionResult.failure(c.ERR_PARSE, "parse: bad", retryable=False))
    assert not rfm.is_hard_failure(_timeout())
    assert not rfm.is_hard_failure(_http_failure(503))
    assert not rfm.is_hard_failure(_http_failure(429))
    assert not rfm.is_hard_failure(_ok([]))


def test_due_from_next_poll_at_else_from_last_attempt():
    assert rfm.is_due(_feed(next_poll_at=NOW + timedelta(minutes=1)), NOW) is False
    assert rfm.is_due(_feed(next_poll_at=NOW - timedelta(minutes=1)), NOW) is True
    assert rfm.is_due(_feed(), NOW) is True
    assert rfm.is_due(_feed(last_checked_at=NOW - timedelta(minutes=30)), NOW) is False
    assert rfm.is_due(_feed(last_checked_at=NOW - timedelta(minutes=61)), NOW) is True
    # A long backoff wins over the base interval having passed.
    assert rfm.is_due(_feed(last_checked_at=NOW - timedelta(hours=3),
                            next_poll_at=NOW + timedelta(hours=1)), NOW) is False


def test_failure_values_count_backoff_and_flag_after_twenty_hard_failures(monitor):
    base = timedelta(minutes=60)
    feed = _feed(consecutive_error_count=0)
    v = monitor._failure_values(feed, _http_failure(403), NOW)
    assert v["consecutive_error_count"] == 1 and v["polling_status"] == "error"
    assert v["next_poll_at"] == NOW + base
    assert v["first_failed_at"] == NOW and v["last_failed_at"] == NOW
    assert v["last_attempt_at"] == NOW and v["last_checked_at"] == NOW
    assert v["last_error"] and "HTTP 403" in v["last_error"]

    v = monitor._failure_values(_feed(consecutive_error_count=3, first_failed_at=NOW - base),
                                _http_failure(403), NOW)
    assert v["next_poll_at"] == NOW + base * 8 and "first_failed_at" not in v

    v = monitor._failure_values(_feed(consecutive_error_count=19), _http_failure(403), NOW)
    assert v["polling_status"] == "needs_attention"
    assert "20 consecutive failures" in v["needs_attention_reason"]
    assert v["next_poll_at"] == NOW + base * 8, "still polled, at the slow cadence"

    v = monitor._failure_values(_feed(consecutive_error_count=19), _timeout(), NOW)
    assert v["polling_status"] == "error" and v["needs_attention_reason"] is None


def test_twenty_403s_in_a_row_reach_needs_attention_but_twenty_timeouts_do_not(monitor):
    for failure, expected in ((_http_failure(403), "needs_attention"), (_timeout(), "error")):
        feed = _feed()
        monitor.next_result = failure
        for _ in range(20):
            _poll(monitor, feed)
            values = monitor.db.last_feed_update()
            assert "coverage_through" not in values, "a failure never moves the checkpoint"
            assert "etag" not in values
            _apply(feed, values)
        assert feed["consecutive_error_count"] == 20
        assert feed["polling_status"] == expected
        assert monitor.runs[-1]["result"].failed
        assert monitor.runs[-1]["after"] == monitor.runs[-1]["before"]
        assert monitor.collector_calls, "the feed is still fetched, never deactivated"


def test_success_after_failures_resets_counters_and_returns_to_base_cadence(monitor):
    feed = _feed(consecutive_error_count=5, polling_status="error",
                 first_failed_at=NOW - timedelta(hours=5), last_failed_at=NOW - timedelta(hours=1),
                 needs_attention_reason="old", coverage_through=NOW - timedelta(days=1))
    monitor.next_result = _ok([_article(1)], proposed_validators={"etag": '"v1"'})
    inserted = _poll(monitor, feed)
    assert inserted == 1
    v = monitor.db.last_feed_update()
    assert v["consecutive_error_count"] == 0 and v["polling_status"] == "ok"
    assert v["first_failed_at"] is None and v["last_failed_at"] is None
    assert v["needs_attention_reason"] is None and v["last_error"] is None
    assert v["last_success_at"] == v["last_attempt_at"] == v["last_checked_at"]
    assert v["next_poll_at"] - v["last_attempt_at"] == timedelta(minutes=60)
    assert v["coverage_through"] == NOW
    assert v["etag"] == '"v1"'
    assert v["last_article_date"] == datetime(2026, 8, 14, 9, 7, 52, tzinfo=timezone.utc)
    assert monitor.runs[-1]["before"] == NOW - timedelta(days=1)
    assert monitor.runs[-1]["after"] == NOW
    assert monitor.runs[-1]["scope_kind"] == "rss_feed" and monitor.runs[-1]["scope_id"] == "42"
    assert monitor.enriched_with == [[_article(1)]]


# ---------------------------------------------------------------------------
# Work package 21: shared host budget
# ---------------------------------------------------------------------------


def test_blocked_reddit_host_records_quota_run_without_touching_backoff(monitor):
    until = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0)
    FakeHostGuard.blocked = c.CollectionResult.quota_exhausted("host:reddit.com", until)
    feed = _feed(url="https://www.reddit.com/r/netsec/.rss", consecutive_error_count=2)
    _poll(monitor, feed)
    assert monitor.collector_calls == [], "nothing was fetched"
    v = monitor.db.last_feed_update()
    assert "consecutive_error_count" not in v and "polling_status" not in v
    assert v["next_poll_at"] == until
    assert monitor.runs[-1]["result"].error_code == c.ERR_QUOTA
    assert monitor.runs[-1]["after"] == monitor.runs[-1]["before"]


def test_429_from_reddit_pauses_the_host(monitor):
    monitor.next_result = _http_failure(429, retry_after="90")
    _poll(monitor, _feed(url="https://old.reddit.com/search.rss?q=x"))
    assert FakeHostGuard.calls == ["90"]
    v = monitor.db.last_feed_update()
    assert v["next_poll_at"] >= NOW + timedelta(minutes=5)


def test_429_from_another_host_does_not_touch_the_reddit_budget(monitor):
    monitor.next_result = _http_failure(429, retry_after="90")
    _poll(monitor, _feed())
    assert FakeHostGuard.calls == []


# ---------------------------------------------------------------------------
# Work package 16: storage outcomes, validators, pending entries
# ---------------------------------------------------------------------------


def test_store_article_outcomes_are_three_distinct_strings(monitor):
    monitor.db.facade.existing.add("https://x.test/dup")
    monitor.db.fail_uris.add("https://x.test/bad")
    run = lambda a: asyncio.run(monitor._store_article(a, "AI", {}))
    assert run(_article("dup")) == "existing"
    assert run(_article("new")) == "inserted"
    assert run(_article("bad")) == "failed"
    assert monitor._last_store_error and "RuntimeError" in monitor._last_store_error
    assert run({"title": "no url", "url": ""}) == "failed"
    outcomes = {"existing", "inserted", "failed"}
    assert all(isinstance(o, str) for o in outcomes)


def test_insert_writes_dates_with_provenance_and_null_when_unknown(monitor):
    asyncio.run(monitor._store_article(_article(1), "AI", {}))
    row = monitor.db.article_inserts()[-1]
    assert row["publication_date"] == "2026-08-14T09:07:52+00:00"
    assert row["published_at_raw"] == "2026-08-14T09:07:52+00:00"
    assert row["publication_date_precision"] == "second"
    assert row["date_provenance"] == "feed"
    assert row["content_kind"] == "excerpt" and row["record_type"] == "news"
    assert isinstance(row["first_seen_at"], datetime)

    asyncio.run(monitor._store_article(_article(2, pub=None), "AI", {}))
    row = monitor.db.article_inserts()[-1]
    assert row["publication_date"] is None
    assert row["date_provenance"] == "unknown"
    assert row["publication_date_precision"] is None
    assert isinstance(row["first_seen_at"], datetime)


def test_failed_insert_blocks_validators_and_checkpoint_and_queues_the_entry(monitor):
    monitor.db.fail_uris.add("https://x.test/2")
    monitor.db.facade.existing.add("https://x.test/3")
    monitor.next_result = _ok([_article(1), _article(2), _article(3)],
                              proposed_validators={"etag": '"v9"', "last_modified": "lm"})
    inserted = _poll(monitor, _feed(coverage_through=NOW - timedelta(days=1)))
    assert inserted == 1
    v = monitor.db.last_feed_update()
    assert "etag" not in v and "last_modified" not in v, "validators wait for the queued entry"
    assert "coverage_through" not in v and "last_article_date" not in v
    assert v["polling_status"] == "ok" and v["consecutive_error_count"] == 0, "not a feed failure"
    assert "queued" in v["last_error"]
    queued = monitor.db.text_statements("INSERT INTO pending_feed_entries")
    assert len(queued) == 1
    assert queued[0][1]["entry_key"] == "https://x.test/2" and queued[0][1]["feed_id"] == 42
    assert '"url": "https://x.test/2"' in queued[0][1]["payload"]
    run = monitor.runs[-1]
    assert run["after"] == run["before"] == NOW - timedelta(days=1)
    counts = run["result"].counts
    assert counts.inserted == 1 and counts.duplicate == 1 and counts.deferred == 1
    assert run["result"].status == c.STATUS_PARTIAL
    assert monitor.enriched_with == [[_article(1)]], "only the inserted article is enriched"


def test_all_stored_commits_validators_and_advances_checkpoint(monitor):
    monitor.db.facade.existing.add("https://x.test/1")
    monitor.next_result = _ok([_article(1), _article(2)], proposed_validators={"etag": '"v9"'})
    _poll(monitor, _feed())
    v = monitor.db.last_feed_update()
    assert v["etag"] == '"v9"' and v["coverage_through"] == NOW
    assert monitor.db.text_statements("INSERT INTO pending_feed_entries") == []
    counts = monitor.runs[-1]["result"].counts
    assert counts.inserted == 1 and counts.duplicate == 1


def test_parse_partial_keeps_items_but_not_validators_or_checkpoint(monitor):
    res = c.CollectionResult.partial([_article(1)], truncated_reason=c.TRUNC_PARSE_PARTIAL,
                                     provider="rss", scope=FEED_URL)
    res.parse_partial = True
    res.diagnostics.update({"bozo": "not well-formed (invalid token)", "entries_recovered": 1})
    res.started_at = res.interval_end = NOW
    monitor.next_result = res
    feed = _feed(parse_partial_count=8)
    _poll(monitor, feed)
    v = monitor.db.last_feed_update()
    assert "etag" not in v and "coverage_through" not in v
    assert v["parse_partial_count"] == 9 and v["polling_status"] == "ok"
    assert "parse_partial" in v["last_error"]
    assert monitor.db.article_inserts()[-1]["uri"] == "https://x.test/1"
    # The tenth consecutive partial parse is surfaced like a failing feed.
    _apply(feed, v)
    _poll(monitor, feed)
    v = monitor.db.last_feed_update()
    assert v["parse_partial_count"] == 10 and v["polling_status"] == "needs_attention"
    assert "parse_partial for 10" in v["needs_attention_reason"]


def test_304_is_a_success_that_leaves_coverage_alone(monitor):
    res = _ok([], proposed_validators={"etag": '"same"'})
    res.diagnostics["not_modified"] = True
    monitor.next_result = res
    _poll(monitor, _feed(etag='"same"', consecutive_error_count=3, polling_status="error",
                         coverage_through=NOW - timedelta(hours=2)))
    assert monitor.collector_calls[-1]["etag"] == '"same"'
    v = monitor.db.last_feed_update()
    assert v["consecutive_error_count"] == 0 and v["polling_status"] == "ok"
    assert v["last_success_at"] == v["last_attempt_at"]
    assert "coverage_through" not in v
    assert monitor.runs[-1]["after"] == NOW - timedelta(hours=2)


def test_pending_entries_are_replayed_before_the_fetch(monitor):
    monitor.db.pending_rows = [
        (11, "https://x.test/a", {"title": "A", "url": "https://x.test/a", "published_date": None}, 1),
        (12, "https://x.test/b", '{"title": "B", "url": "https://x.test/b"}', 1),
        (13, "https://x.test/c", {"title": "C", "url": "https://x.test/c"}, 4),
    ]
    monitor.db.facade.existing.add("https://x.test/b")
    monitor.db.fail_uris.add("https://x.test/c")
    monitor.next_result = _ok([])
    inserted = _poll(monitor, _feed())
    assert inserted == 1, "the replayed insert counts"
    assert monitor.db.inserted_uris[:1] == ["https://x.test/a"]
    deleted = [p["id"] for _, p in monitor.db.text_statements("DELETE FROM pending_feed_entries")]
    assert sorted(deleted) == [11, 12, 13], "stored, existing, and given-up rows all go"
    assert monitor.db.text_statements("UPDATE pending_feed_entries") == []
    assert monitor.enriched_with == [[{"title": "A", "url": "https://x.test/a", "published_date": None}]]


def test_pending_entry_that_fails_again_counts_an_attempt(monitor):
    monitor.db.pending_rows = [(21, "https://x.test/c", {"title": "C", "url": "https://x.test/c"}, 1)]
    monitor.db.fail_uris.add("https://x.test/c")
    _poll(monitor, _feed())
    ups = monitor.db.text_statements("UPDATE pending_feed_entries")
    assert len(ups) == 1 and ups[0][1]["attempts"] == 2 and ups[0][1]["id"] == 21
    assert "RuntimeError" in ups[0][1]["error"]
    assert monitor.db.text_statements("DELETE FROM pending_feed_entries") == []


def test_collector_exception_is_classified_and_backs_off(monitor, monkeypatch):
    async def boom(self_, *a, **k):
        raise socket.gaierror("Temporary failure in name resolution")
    monkeypatch.setattr(rfm.RSSCollector, "fetch_feed_result", boom)
    _poll(monitor, _feed())
    v = monitor.db.last_feed_update()
    assert v["polling_status"] == "error" and v["consecutive_error_count"] == 1
    assert "gaierror" in v["last_error"]
    assert monitor.runs[-1]["result"].error_code == c.ERR_DNS


def test_replayed_entries_are_enriched_even_when_the_fetch_fails(monitor):
    monitor.db.pending_rows = [(31, "https://x.test/a", {"title": "A", "url": "https://x.test/a"}, 1)]
    monitor.next_result = _http_failure(503)
    assert _poll(monitor, _feed()) == 1
    assert monitor.enriched_with == [[{"title": "A", "url": "https://x.test/a"}]]
    v = monitor.db.last_feed_update()
    assert v["polling_status"] == "error" and "coverage_through" not in v


# ---------------------------------------------------------------------------
# Identity on the RSS route (work packages 4 and 8)
# ---------------------------------------------------------------------------

def test_store_resolves_identity_merges_repeats_and_records_observations(monitor, monkeypatch):
    """A tracking variant of a stored article is that article: the monitor
    merges into the existing row and records the sighting instead of
    inserting; a new article is inserted with its canonical URL and then
    observed once."""
    import app.tasks.rss_feed_monitor as mod
    from app.services.article_identity import Resolution

    calls = {"resolve": [], "merge": [], "observe": []}

    def fake_resolve(facade, item):
        calls["resolve"].append(item["url"])
        if "utm_source" in item["url"]:
            return Resolution(uri="https://x.test/known", method="canonical_url",
                              canonical_url="https://x.test/known", existing=True, matched_by="alias")
        return Resolution(uri=None, method="canonical_url",
                          canonical_url=item["url"], existing=False)

    monkeypatch.setattr("app.services.article_identity.resolve_identity", fake_resolve)
    monkeypatch.setattr(mod.RSSFeedMonitor, "_merge_and_observe",
                        lambda self, uri, item, res: calls["merge"].append(uri))
    monkeypatch.setattr(mod.RSSFeedMonitor, "_observe",
                        lambda self, uri, item, res: calls["observe"].append(uri))

    variant = _article(9); variant["url"] = "https://x.test/known?utm_source=rss"
    assert asyncio.run(monitor._store_article(variant, "AI", {})) == mod.STORE_EXISTING
    assert calls["merge"] == ["https://x.test/known"]
    assert monitor.db.article_inserts() == []

    fresh = _article(10)
    assert asyncio.run(monitor._store_article(fresh, "AI", {})) == mod.STORE_INSERTED
    row = monitor.db.article_inserts()[-1]
    assert row["canonical_url"] == "https://x.test/10" and row["identity_method"] == "canonical_url"
    assert calls["observe"] == ["https://x.test/10"]
    assert calls["resolve"] == [variant["url"], "https://x.test/10"]


def test_new_entries_beyond_the_per_poll_budget_are_queued_not_enriched(monitor, monkeypatch):
    """A 250-entry first poll stores and enriches the budget's worth and queues
    the rest with zero attempts; validators still commit because the queue is
    durable, and the next poll drains the queue before fetching."""
    import app.tasks.rss_feed_monitor as mod
    monkeypatch.setattr(mod, "NEW_ENTRIES_PER_POLL", 100)
    enriched = []
    async def fake_ingest(articles, topic, *a, **k):
        enriched.extend(articles); return 0
    monkeypatch.setattr(monitor, "_run_auto_ingest", fake_ingest)
    items = [_article(i) for i in range(250)]
    res = _ok(items, proposed_validators={"etag": "W/abc"})
    feed = _feed()
    asyncio.run(monitor._persist_result(feed, res, NOW, [], 0, None))
    assert len(monitor.db.article_inserts()) == 100
    assert len(enriched) == 100
    assert res.counts.deferred == 150 and res.diagnostics["deferred_backlog"] == 150
    queued = [p for stmt, p in monitor.db.statements
              if isinstance(stmt, TextClause) and "INSERT INTO pending_feed_entries" in str(stmt)]
    assert len(queued) == 150 and all(p["attempts"] == 0 for p in queued)
    assert monitor.db.last_feed_update().get("etag") == "W/abc"
