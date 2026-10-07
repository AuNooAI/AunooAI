"""Provider collectors report outcomes, page completely, honour the shared
quota ledger, keep social identity, and never invent dates.

No network: every HTTP client is a fake with the ``get`` shape the
collectors use. Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 3,
5, 7, 8, 9, 10, 20, 24, 25 and 26.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.collectors import contracts as c
from app.services import shared_ledger as sl


# ---------------------------------------------------------------------------
# Fakes and fixtures
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}
        self.content_type = "application/json" if not isinstance(body, str) else "text/xml"
        self.url = "fake://"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body

    async def text(self):
        return self._body if isinstance(self._body, str) else json.dumps(self._body)


class FakeSession:
    """``handler(url, params, headers) -> FakeResponse``; records every call."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        return self.handler(url, params or {}, headers or {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("AUNOO_SHARED_LEDGER_PATH", str(tmp_path / "ledger.sqlite"))
    monkeypatch.setenv("AUNOO_TENANT_NAME", "t-test")
    sl._default = None
    yield sl.get_ledger()
    sl._default = None


class _Facade:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Db:
    facade = _Facade()


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=1)


# ---------------------------------------------------------------------------
# NewsAPI (work packages 3, 8, 20)
# ---------------------------------------------------------------------------

def _newsapi_article(i, when=None):
    return {"url": f"https://example.com/a{i}", "title": f"t{i}", "description": "d",
            "publishedAt": (when or (NOW - timedelta(minutes=i))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": {"name": "Example"}, "content": f"body {i} [+1234 chars]"}


def _newsapi(monkeypatch, ledger, handler):
    from app.collectors import newsapi_collector as mod
    monkeypatch.setenv("PROVIDER_NEWSAPI_API_KEY", "k-newsapi")
    monkeypatch.setenv("NEWSAPI_MAX_PAGES", "5")
    session = FakeSession(handler)
    monkeypatch.setattr(mod, "_session", lambda: session)
    return mod.NewsAPICollector(_Db()), session


def test_newsapi_230_records_over_three_pages_are_230_unique(monkeypatch, ledger):
    pages = {1: [_newsapi_article(i) for i in range(100)],
             2: [_newsapi_article(i) for i in range(100, 200)],
             3: [_newsapi_article(i) for i in range(200, 230)]}
    # The plan cap is on results, not pages; pretend a paid plan by raising
    # the developer cap for this test.
    from app.collectors import newsapi_collector as mod
    monkeypatch.setattr(mod, "_DEVELOPER_RESULT_CAP", 10_000)

    def handler(url, params, headers):
        page = int(params["page"])
        return FakeResponse(200, {"status": "ok", "totalResults": 230, "articles": pages[page]})

    coll, session = _newsapi(monkeypatch, ledger, handler)
    res = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=100))
    assert res.status == c.STATUS_SUCCESS and res.coverage_complete
    assert len(res.items) == 230 and len({i["url"] for i in res.items}) == 230
    assert len(session.calls) == 3
    assert all(call["params"]["to"] == NOW.strftime("%Y-%m-%dT%H:%M:%S") for call in session.calls)
    assert all(call["params"]["sortBy"] == "publishedAt" for call in session.calls)
    assert res.items[0]["content"] == "body 0"
    assert res.items[0]["content_kind"] == "excerpt" and res.items[0]["content_truncated"] is True
    assert res.items[0]["_collector_provider"] == "newsapi"


def test_newsapi_overlapping_pages_do_not_duplicate(monkeypatch, ledger):
    from app.collectors import newsapi_collector as mod
    monkeypatch.setattr(mod, "_DEVELOPER_RESULT_CAP", 10_000)
    pages = {1: [_newsapi_article(i) for i in range(100)],
             2: [_newsapi_article(i) for i in range(90, 190)],
             3: [_newsapi_article(i) for i in range(190, 200)]}

    def handler(url, params, headers):
        return FakeResponse(200, {"status": "ok", "totalResults": 210, "articles": pages[int(params["page"])]})

    coll, _ = _newsapi(monkeypatch, ledger, handler)
    res = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=100))
    assert len(res.items) == 200 and len({i["url"] for i in res.items}) == 200
    assert res.counts.duplicate == 10 and res.counts.received == 210


def test_newsapi_full_last_page_is_not_complete(monkeypatch, ledger):
    def handler(url, params, headers):
        return FakeResponse(200, {"status": "ok", "totalResults": 1000,
                                  "articles": [_newsapi_article(i) for i in range(10)]})

    coll, session = _newsapi(monkeypatch, ledger, handler)
    res = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=10, max_pages=1))
    assert res.status == c.STATUS_PARTIAL
    assert not res.coverage_complete and not res.may_advance_checkpoint
    assert res.continuation == {"page": 2}
    assert len(session.calls) == 1


def test_newsapi_plan_cap_narrows_the_window(monkeypatch, ledger):
    def handler(url, params, headers):
        return FakeResponse(200, {"status": "ok", "totalResults": 350,
                                  "articles": [_newsapi_article(i) for i in range(100)]})

    coll, _ = _newsapi(monkeypatch, ledger, handler)
    res = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=100))
    assert res.status == c.STATUS_PARTIAL and res.truncated_reason == c.TRUNC_PROVIDER_LIMIT
    assert res.continuation["page"] == 1
    assert datetime.fromisoformat(res.continuation["to"]) == NOW - timedelta(minutes=99)


def test_newsapi_429_is_quota_exhausted_with_continuation_and_ledger_pause(monkeypatch, ledger):
    def handler(url, params, headers):
        if int(params["page"]) == 1:
            return FakeResponse(200, {"status": "ok", "totalResults": 500,
                                      "articles": [_newsapi_article(i) for i in range(10)]})
        return FakeResponse(429, {"status": "error", "code": "rateLimited", "message": "too many"},
                            headers={"Retry-After": "120"})

    coll, session = _newsapi(monkeypatch, ledger, handler)
    res = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=10))
    assert res.status == c.STATUS_FAILED and res.error_code == c.ERR_QUOTA
    assert res.retryable and res.truncated_reason == c.TRUNC_QUOTA
    assert not res.may_advance_checkpoint
    assert res.continuation == {"page": 2}
    assert len(res.items) == 10, "page one's items are kept for idempotent persistence"
    assert res.interval_end == NOW
    assert ledger.exhausted_until("newsapi", "k-newsapi") is not None

    # Every site on the key is paused: the next run sends nothing.
    calls_before = len(session.calls)
    again = run(coll.collect("acme", "tech", interval_start=START, interval_end=NOW, max_results=10,
                             continuation=res.continuation))
    assert again.error_code == c.ERR_QUOTA and len(session.calls) == calls_before
    assert again.continuation == {"page": 2}
    assert again.counts.quota_skipped == 1


def test_newsapi_search_articles_compat_returns_a_list(monkeypatch, ledger):
    def handler(url, params, headers):
        return FakeResponse(500, {"status": "error", "message": "boom"})

    coll, _ = _newsapi(monkeypatch, ledger, handler)
    assert run(coll.search_articles("acme", "tech", max_results=5)) == []


# ---------------------------------------------------------------------------
# Semantic Scholar (work packages 3, 20)
# ---------------------------------------------------------------------------

def test_semantic_scholar_pages_by_offset_and_stops_on_429(monkeypatch, ledger):
    from app.collectors import semantic_scholar_collector as mod
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)

    def paper(i):
        return {"paperId": f"p{i}", "title": f"T{i}", "abstract": "A", "publicationDate": "2026-09-30",
                "authors": [{"name": "X"}], "url": f"https://www.semanticscholar.org/paper/p{i}"}

    def handler(url, params, headers):
        off = int(params["offset"])
        if off == 0:
            return FakeResponse(200, {"total": 250, "offset": 0, "next": 100, "data": [paper(i) for i in range(100)]})
        return FakeResponse(429, {"message": "Too Many Requests"}, headers={"Retry-After": "5"})

    session = FakeSession(handler)
    monkeypatch.setattr(mod, "_session", lambda: session)
    coll = mod.SemanticScholarCollector()
    res = run(coll.collect("gum disease", "Neuroscience", interval_start=START, interval_end=NOW, max_results=100))
    assert res.error_code == c.ERR_QUOTA and res.continuation == {"offset": 100}
    assert len(res.items) == 100 and res.items[0]["content_kind"] == "abstract"
    assert res.items[0]["published_date"].startswith("2026-09-30")
    assert session.calls[0]["params"]["offset"] == 0 and session.calls[1]["params"]["offset"] == 100
    assert ledger.exhausted_until("semantic_scholar", None) is not None


# ---------------------------------------------------------------------------
# NewsData (work packages 7, 9, 20, 26)
# ---------------------------------------------------------------------------

def _newsdata(monkeypatch, ledger, handler):
    from app.collectors import newsdata_collector as mod
    monkeypatch.setenv("PROVIDER_NEWSDATA_API_KEY", "k-newsdata")
    session = FakeSession(handler)
    monkeypatch.setattr(mod, "_session", lambda: session)
    return mod.NewsdataCollector(), session


def _nd_article(i, when):
    return {"article_id": f"n{i}", "title": f"N{i}", "link": f"https://news.example/{i}",
            "description": "d", "pubDate": when.strftime("%Y-%m-%d %H:%M:%S"), "pubDateTZ": "UTC",
            "source_url": "https://news.example", "content": "ONLY AVAILABLE IN PAID PLANS"}


def test_newsdata_date_clause_dropped_is_declared_and_filtered_locally(monkeypatch, ledger):
    monkeypatch.setenv("NEWSDATA_DATE_FILTER_SUPPORTED", "0")
    body = {"status": "success", "totalResults": 3, "nextPage": None,
            "results": [_nd_article(1, NOW - timedelta(hours=2)), _nd_article(2, NOW - timedelta(hours=5)),
                        _nd_article(3, NOW - timedelta(days=9))]}
    coll, session = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(200, body))
    res = run(coll.collect('"gum disease" OR Parodontitis', "health", interval_start=START, interval_end=NOW))
    assert "from_date" not in session.calls[0]["params"] and "to_date" not in session.calls[0]["params"]
    assert session.calls[0]["params"]["q"] == '"gum disease" OR Parodontitis'
    assert res.status == c.STATUS_SUCCESS
    assert res.coverage_complete is False and res.truncated_reason == c.TRUNC_NO_DATE_FILTER
    assert not res.may_advance_checkpoint
    assert res.diagnostics["date_clause"] == "dropped:provider_no_date_filter"
    assert res.diagnostics["translation_status"] == "exact"
    assert res.diagnostics["original_expression"] == '"gum disease" OR Parodontitis'
    assert res.counts.filtered == 1 and len(res.items) == 2
    assert res.items[0]["content_kind"] == "excerpt" and res.items[0]["content"] == "d"


def test_newsdata_sends_dates_when_the_plan_supports_them(monkeypatch, ledger):
    monkeypatch.setenv("NEWSDATA_DATE_FILTER_SUPPORTED", "1")
    body = {"status": "success", "totalResults": 0, "results": []}
    coll, session = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(200, body))
    res = run(coll.collect("Sunstar", "health", interval_start=START, interval_end=NOW))
    assert session.calls[0]["params"]["from_date"] == START.strftime("%Y-%m-%d")
    assert session.calls[0]["params"]["to_date"] == NOW.strftime("%Y-%m-%d")
    assert res.coverage_complete and res.may_advance_checkpoint
    assert res.diagnostics["date_clause"] == "sent"


def test_newsdata_unsupported_query_sends_nothing(monkeypatch, ledger):
    coll, session = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(200, {}))
    res = run(coll.collect("a OR (b NOT c)", "x", interval_start=START, interval_end=NOW))
    assert res.failed and res.error_code == c.ERR_UNSUPPORTED_QUERY and not res.retryable
    assert session.calls == []
    assert res.diagnostics["translation_status"] == "unsupported"


def test_newsdata_empty_query_sends_nothing_and_succeeds(monkeypatch, ledger):
    coll, session = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(200, {}))
    res = run(coll.collect("   ", "x", interval_start=START, interval_end=NOW))
    assert res.succeeded and res.items == [] and session.calls == []
    assert "no request" in res.diagnostics["note"]


def test_newsdata_missing_pubdate_is_none_not_now(monkeypatch, ledger):
    coll, _ = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(200, {}))
    item = coll._format_article({"title": "t", "link": "https://x.example/1"}, "x")
    assert item["published_date"] is None and item["date_provenance"] is None


def test_newsdata_exhaustion_body_pauses_every_site(monkeypatch, ledger):
    body = {"status": "error", "results": {"message": "You have exceeded your assigned API credits", "code": "RateLimitExceeded"}}
    coll, session = _newsdata(monkeypatch, ledger, lambda u, p, h: FakeResponse(429, body))
    res = run(coll.collect("Sunstar", "health", interval_start=START, interval_end=NOW))
    assert res.error_code == c.ERR_QUOTA and res.truncated_reason == c.TRUNC_QUOTA
    assert ledger.exhausted_until("newsdata", "k-newsdata") is not None
    again = run(coll.collect("Sunstar", "health", interval_start=START, interval_end=NOW))
    assert again.error_code == c.ERR_QUOTA and len(session.calls) == 1


# ---------------------------------------------------------------------------
# Bluesky (work packages 7, 25)
# ---------------------------------------------------------------------------

def _bsky_post(i, created, indexed=None):
    return SimpleNamespace(
        uri=f"at://did:plc:x/app.bsky.feed.post/{i}", cid=f"cid{i}",
        author=SimpleNamespace(handle="who.bsky.social", display_name="Who", did="did:plc:x"),
        record=SimpleNamespace(text=f"post {i} about gum disease", created_at=created, embed=None),
        indexed_at=indexed or NOW.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        like_count=1, repost_count=2, reply_count=3)


class _FakeBskyClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.me = SimpleNamespace(did="did:plc:me")
        self.app = SimpleNamespace(bsky=SimpleNamespace(feed=SimpleNamespace(search_posts=self._search)))

    def _search(self, params):
        self.calls.append(dict(params))
        posts, cursor = self.pages[len(self.calls) - 1]
        return SimpleNamespace(posts=posts, cursor=cursor)


def _bluesky(pages):
    from app.collectors.bluesky_collector import BlueskyCollector
    coll = BlueskyCollector.__new__(BlueskyCollector)
    coll.client = _FakeBskyClient(pages)
    coll.requests_today = 0
    coll.username = coll.password = "x"
    return coll


def test_bluesky_sends_since_until_and_drops_posts_outside_interval():
    inside = (NOW - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    old = "2023-08-01T10:00:00.000Z"
    coll = _bluesky([([_bsky_post(1, inside), _bsky_post(2, old), _bsky_post(3, None)], None)])
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=25))
    call = coll.client.calls[0]
    assert call["since"] == START.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert call["until"] == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert call["sort"] == "latest" and call["limit"] == 25
    assert res.succeeded and res.coverage_complete
    assert res.counts.filtered == 1
    urls = {i["url"] for i in res.items}
    assert "https://bsky.app/profile/who.bsky.social/post/2" not in urls
    first = next(i for i in res.items if i["url"].endswith("/post/1"))
    assert first["published_date"].startswith((NOW - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"))
    assert first["date_provenance"] == "provider"
    assert first["source_indexed_at"].startswith(NOW.strftime("%Y-%m-%dT%H:%M"))
    assert first["content_kind"] == "social_post"
    third = next(i for i in res.items if i["url"].endswith("/post/3"))
    assert third["published_date"] is None, "no createdAt means no publication date"
    assert third["title"].startswith("@who.bsky.social:")


def test_bluesky_pages_with_cursor_and_keeps_continuation_at_budget(monkeypatch):
    monkeypatch.setenv("BLUESKY_MAX_PAGES", "2")
    inside = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    page = [_bsky_post(i, inside) for i in range(25)]
    coll = _bluesky([(page, "c1"), ([_bsky_post(100 + i, inside) for i in range(25)], "c2"), ([], None)])
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=25))
    assert res.status == c.STATUS_PARTIAL and res.continuation == {"cursor": "c2"}
    assert coll.client.calls[1]["cursor"] == "c1"
    assert len(res.items) == 50


def test_bluesky_rate_limit_on_page_two_keeps_continuation():
    inside = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    class Boom(Exception):
        def __init__(self):
            super().__init__("RateLimitExceeded")
            self.response = SimpleNamespace(status_code=429)

    coll = _bluesky([([_bsky_post(i, inside) for i in range(25)], "c1")])
    original = coll.client._search

    def search(params):
        if params.get("cursor"):
            raise Boom()
        return original(params)

    coll.client.app.bsky.feed.search_posts = search
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=25))
    assert res.failed and res.error_code == c.ERR_QUOTA and res.retryable
    assert res.continuation == {"cursor": "c1"} and len(res.items) == 25


# ---------------------------------------------------------------------------
# arXiv (work packages 7, 24)
# ---------------------------------------------------------------------------

def _arxiv_result(i):
    return SimpleNamespace(
        title=f"Paper {i}", summary="abstract", authors=[SimpleNamespace(name="A")],
        published=NOW - timedelta(hours=i), updated=NOW - timedelta(hours=i),
        entry_id=f"http://arxiv.org/abs/2610.0000{i}v1", primary_category="cs.AI",
        categories=["cs.AI"], pdf_url=f"http://arxiv.org/pdf/2610.0000{i}v1")


def _arxiv(monkeypatch, outcomes):
    """``outcomes`` is a list of exceptions or result lists, one per attempt."""
    import arxiv
    from app.collectors import arxiv_collector as mod
    monkeypatch.setattr(mod, "RETRY_DELAYS", (0.001, 0.001, 0.001))
    monkeypatch.setattr(mod, "MIN_SPACING_SECONDS", 0.0)
    monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.0)
    coll = mod.ArxivCollector()
    attempts = []

    def fetch(search, max_results):
        attempts.append(search.query)
        out = outcomes[min(len(attempts) - 1, len(outcomes) - 1)]
        if isinstance(out, BaseException):
            raise out
        return out

    monkeypatch.setattr(coll, "_fetch_sync", fetch)
    return coll, attempts, arxiv


def test_arxiv_406_then_200_is_complete(monkeypatch):
    import arxiv
    coll, attempts, _ = _arxiv(monkeypatch, [arxiv.HTTPError("u", 0, 406), [_arxiv_result(1), _arxiv_result(2)]])
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=10))
    assert res.succeeded and res.coverage_complete and res.may_advance_checkpoint
    assert len(attempts) == 2 and len(res.items) == 2
    assert res.items[0]["content_kind"] == "abstract"
    assert res.items[0]["published_date"] == (NOW - timedelta(hours=1)).isoformat()
    assert "submittedDate:[" in attempts[0]


def test_arxiv_406_every_time_fails_with_window_continuation(monkeypatch):
    import arxiv
    coll, attempts, _ = _arxiv(monkeypatch, [arxiv.HTTPError("u", 0, 406)])
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=10))
    assert res.failed and res.retryable and res.error_code == c.ERR_HTTP_4XX
    assert res.diagnostics["status"] == 406
    assert res.continuation == {"interval_start": START.isoformat(), "interval_end": NOW.isoformat()}
    assert len(attempts) == 4, "first try plus three retries"


def test_arxiv_bad_query_is_not_retried(monkeypatch):
    import arxiv
    coll, attempts, _ = _arxiv(monkeypatch, [arxiv.HTTPError("u", 0, 400)])
    res = run(coll.collect("gum disease", "health", interval_start=START, interval_end=NOW, max_results=10))
    assert res.failed and not res.retryable and len(attempts) == 1


def test_arxiv_empty_query_sends_nothing(monkeypatch):
    coll, attempts, _ = _arxiv(monkeypatch, [[]])
    res = run(coll.collect("  ", "health", interval_start=START, interval_end=NOW))
    assert res.succeeded and attempts == []


def test_arxiv_calls_are_spaced(monkeypatch):
    from app.collectors import arxiv_collector as mod
    monkeypatch.setattr(mod, "MIN_SPACING_SECONDS", 0.05)
    mod._last_call_at = 0.0
    coll, attempts, _ = _arxiv(monkeypatch, [[_arxiv_result(1)]])
    monkeypatch.setattr(mod, "MIN_SPACING_SECONDS", 0.05)
    import time

    async def two():
        t0 = time.monotonic()
        await asyncio.gather(
            coll.collect("a", "health", interval_start=START, interval_end=NOW),
            coll.collect("b", "health", interval_start=START, interval_end=NOW))
        return time.monotonic() - t0

    assert run(two()) >= 0.05


# ---------------------------------------------------------------------------
# Reddit (work package 10)
# ---------------------------------------------------------------------------

def _atom(entries):
    items = "".join(
        f"<entry><id>t3_{e['id']}</id><title>{e['title']}</title>"
        f"<link href='https://www.reddit.com/r/{e['sub']}/comments/{e['id']}/x/'/>"
        f"<updated>{e['when']}</updated><author><name>/u/a</name></author>"
        f"<content type='html'>&lt;p&gt;{e.get('body', '')}&lt;/p&gt;</content></entry>"
        for e in entries)
    return f"<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><title>r</title>{items}</feed>"


def _reddit(monkeypatch, ledger, handler):
    from app.collectors import reddit_collector as mod
    session = FakeSession(handler)
    monkeypatch.setattr(mod, "_session", lambda: session)
    return mod.RedditCollector(), session


def test_reddit_failed_search_route_keeps_subreddit_items_and_is_partial(monkeypatch, ledger):
    when = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sub = _atom([{"id": "s1", "title": "hello", "sub": "oviva", "when": when},
                 {"id": "s2", "title": "world", "sub": "oviva", "when": when}])

    def handler(url, params, headers):
        if "/r/oviva/" in url:
            return FakeResponse(200, sub)
        return FakeResponse(503, "busy")

    coll, _ = _reddit(monkeypatch, ledger, handler)
    res = run(coll.collect("Oviva", "brand", interval_start=START, interval_end=NOW, max_results=10))
    assert res.status == c.STATUS_PARTIAL and not res.coverage_complete
    assert len(res.items) == 2
    assert all(i["raw_data"]["route"] == "subreddit" and i["raw_data"]["subreddit_inferred"] is True for i in res.items)
    assert res.error_code == c.ERR_HTTP_5XX
    assert [r["scope"] for r in res.diagnostics["routes"]] == ["subreddit", "search"]
    assert res.items[0]["published_date"].startswith((NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H"))


def test_reddit_routes_have_independent_budgets_and_dedupe_across(monkeypatch, ledger):
    when = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sub = _atom([{"id": f"s{i}", "title": "post", "sub": "oviva", "when": when} for i in range(20)])
    search = _atom([{"id": f"q{i}", "title": "Oviva news", "sub": "health", "when": when} for i in range(5)]
                   + [{"id": "s0", "title": "Oviva post", "sub": "oviva", "when": when}])

    def handler(url, params, headers):
        if "/r/oviva/" in url:
            return FakeResponse(200, sub)
        assert params["sort"] == "new"
        if params.get("after"):
            return FakeResponse(200, _atom([]))
        return FakeResponse(200, search)

    coll, session = _reddit(monkeypatch, ledger, handler)
    res = run(coll.collect("Oviva", "brand", interval_start=START, interval_end=NOW, max_results=5))
    assert res.succeeded
    subs = [i for i in res.items if i["raw_data"]["route"] == "subreddit"]
    hits = [i for i in res.items if i["raw_data"]["route"] == "search"]
    assert len(subs) == 5 and len(hits) == 5, "twenty stored subreddit posts cannot suppress five search hits"
    assert len({i["raw_data"]["external_id"] for i in res.items}) == len(res.items)


def test_reddit_429_pauses_the_host_for_every_site(monkeypatch, ledger):
    def handler(url, params, headers):
        return FakeResponse(429, "slow down", headers={"Retry-After": "60"})

    coll, session = _reddit(monkeypatch, ledger, handler)
    res = run(coll.collect("Oviva", "brand", interval_start=START, interval_end=NOW, max_results=5))
    assert res.failed and res.error_code == c.ERR_QUOTA
    assert ledger.host_paused_until("reddit.com") is not None
    assert len(session.calls) == 1, "the second route saw the pause and sent nothing"


def test_reddit_missing_date_is_none(monkeypatch, ledger):
    from app.collectors.reddit_collector import RedditCollector
    item = RedditCollector._item({"title": "t", "link": "https://www.reddit.com/r/x/comments/1/a/", "id": "t3_1"},
                                 "x", route="search", inferred=False)
    assert item["published_date"] is None


# ---------------------------------------------------------------------------
# Xpoz (work packages 5, 20)
# ---------------------------------------------------------------------------

def _xpoz(monkeypatch, platforms=("instagram",)):
    from app.collectors import xpoz_collector as mod
    monkeypatch.setenv("XPOZ_API_KEY", "k-xpoz")
    monkeypatch.setenv("XPOZ_PLATFORMS", ",".join(platforms))
    return mod.XpozCollector(platforms=list(platforms))


def test_instagram_posts_without_code_url_stay_two_rows(monkeypatch):
    coll = _xpoz(monkeypatch)
    a = SimpleNamespace(id="111", caption="first", username="acme", code_url=None, image_url=None,
                        like_count=1, comment_count=0, media_type="image", created_at="2026-09-30T10:00:00Z")
    b = SimpleNamespace(id="222", caption="second", username="acme", code_url=None, image_url=None,
                        like_count=1, comment_count=0, media_type="image", created_at=None, created_at_date=None)
    ra, rb = coll._map_instagram(a, "t"), coll._map_instagram(b, "t")
    assert ra and rb
    assert ra["url"] == "xpoz://instagram/111" and rb["url"] == "xpoz://instagram/222"
    assert ra["url"] != rb["url"]
    for r in (ra, rb):
        assert r["social_meta"]["account_url"] == "https://www.instagram.com/acme/"
        assert r["social_meta"]["permalink"] is None
        assert r["raw_data"]["permalink_missing"] is True
        assert "instagram.com/acme/" not in r["url"]
        assert r["content_kind"] == "social_post"
    assert rb["published_date"] is None
    assert ra["published_date"].startswith("2026-09-30T10:00")
    with_link = coll._map_instagram(SimpleNamespace(id="333", caption="x", username="acme",
                                                     code_url="https://www.instagram.com/p/ABC/", image_url=None,
                                                     like_count=0, comment_count=0, media_type="image",
                                                     created_at=None), "t")
    assert with_link["url"] == "https://www.instagram.com/p/ABC/"
    assert with_link["social_meta"]["permalink"] == with_link["url"]
    assert "permalink_missing" not in with_link["raw_data"]


def test_xpoz_usage_limit_is_quota_exhausted_and_pauses_the_key(monkeypatch, ledger):
    import xpoz as xpoz_mod
    coll = _xpoz(monkeypatch, platforms=("twitter",))

    class OperationFailedError(Exception):
        pass

    class FakeNs:
        def search_posts(self, *a, **k):
            raise OperationFailedError("Operation  failed: Usage limit exceeded")

    class FakeClient:
        def __init__(self, *a, **k):
            self.twitter = FakeNs()

        def close(self):
            pass

    monkeypatch.setattr(xpoz_mod, "XpozClient", FakeClient)
    res = run(coll.collect("wiley", "brand", interval_start=START, interval_end=NOW, max_results=5))
    assert res.failed and res.error_code == c.ERR_QUOTA and res.truncated_reason == c.TRUNC_QUOTA
    assert res.retryable and not res.may_advance_checkpoint
    assert ledger.exhausted_until("xpoz", "k-xpoz") is not None
    again = run(coll.collect("wiley", "brand", interval_start=START, interval_end=NOW, max_results=5))
    assert again.error_code == c.ERR_QUOTA and again.counts.quota_skipped == 1


# ---------------------------------------------------------------------------
# Base collector default (work package 1)
# ---------------------------------------------------------------------------

def test_default_collect_wraps_a_list_collector():
    from app.collectors.base_collector import ArticleCollector

    class Plain(ArticleCollector):
        async def search_articles(self, query, topic, max_results=10, start_date=None, end_date=None, **kw):
            if query == "boom":
                raise TimeoutError("slow")
            return [{"url": f"u{i}", "title": "t"} for i in range(max_results if query == "full" else 2)]

        async def fetch_article_content(self, url):
            return None

    assert Plain.provider_name == "plain"
    res = run(Plain().collect("x", "t", interval_start=START, interval_end=NOW, max_results=10))
    assert res.succeeded and res.coverage_complete and res.provider == "plain"
    assert res.items[0]["_collector_provider"] == "plain" and res.items[0]["content_kind"] == "unknown"
    full = run(Plain().collect("full", "t", interval_start=START, interval_end=NOW, max_results=10))
    # A full page from a list API has no proven end and no way to ask for
    # more. It never proves coverage; it is flagged non-exhaustive so the
    # checkpoint's loss policy can record a gap. No invented continuation.
    assert full.succeeded and not full.coverage_complete and full.truncated_reason == c.TRUNC_PAGE_CAP
    assert not full.may_advance_checkpoint and full.non_exhaustive and full.continuation is None
    bad = run(Plain().collect("boom", "t", interval_start=START, interval_end=NOW))
    assert bad.failed and bad.error_code == c.ERR_TIMEOUT and bad.retryable


# ---------------------------------------------------------------------------
# NewsFirehose paging (docs/pipelines/08_INGEST_FIX_SPEC.md, WP1)
# ---------------------------------------------------------------------------

def _nf_row(i, when):
    return {"id": i, "url": f"https://news.example/{i}", "title": f"t{i}", "description": "d",
            "content": "body", "publishedAt": when.isoformat()}


def _firehose(monkeypatch, handler, **env):
    from app.collectors import newsfirehose_collector as mod
    monkeypatch.setenv("NEWSFIREHOSE_API_KEY", "k-nf")
    monkeypatch.setenv("NEWSFIREHOSE_BASE_URL", "http://nf.test")
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    session = FakeSession(handler)
    monkeypatch.setattr(mod, "_session", lambda: session)
    return mod.NewsFirehoseCollector(), session


def _nf_pages(total, newest=NOW - timedelta(minutes=1), step=timedelta(minutes=2), per_q=None,
              fail=None):
    """A /v1/search fake over ``total`` rows newest first, paged by the
    params the collector sends. ``per_q`` maps a q to its own row offset so
    two OR-chunks can return overlapping rows. ``fail(q, page)`` may return
    a FakeResponse to answer that page instead."""
    def handler(url, params, headers):
        page, size = int(params["page"]), int(params["page_size"])
        if fail is not None:
            out = fail(params["q"], page)
            if out is not None:
                return out
        base = (per_q or {}).get(params["q"], 0)
        ids = range(base + (page - 1) * size, min(base + total, base + page * size))
        rows = [_nf_row(i, newest - step * (i - base)) for i in ids]
        has_more = base + page * size < base + total
        return FakeResponse(200, {"status": "ok", "articles": rows, "has_more": has_more})
    return handler


def _cursor(res):
    return {k: v for k, v in (res.continuation or {}).items() if k != "q"}


def test_newsfirehose_pages_until_has_more_is_false(monkeypatch):
    coll, session = _firehose(monkeypatch, _nf_pages(230))
    res = run(coll.collect("SOC automation", "t", interval_start=NOW - timedelta(days=3),
                           interval_end=NOW, max_results=10))
    assert res.succeeded and res.coverage_complete and res.may_advance_checkpoint
    assert len(res.items) == 230 and len({i["url"] for i in res.items}) == 230
    assert [call["params"]["page"] for call in session.calls] == [1, 2, 3]
    p = session.calls[0]["params"]
    assert p["page_size"] == 100 and p["sort_by"] == "published_at" and p["language"] == "english"


def test_newsfirehose_stops_once_a_page_reaches_past_the_window(monkeypatch):
    # Rows are 2 minutes apart; a 1-hour window plus a 0-hour overlap is
    # covered by page 1, so page 2 is never asked for despite has_more.
    coll, session = _firehose(monkeypatch, _nf_pages(1000), NEWSFIREHOSE_OVERLAP_HOURS=0)
    res = run(coll.collect("AI", "t", interval_start=NOW - timedelta(hours=1), interval_end=NOW))
    assert res.succeeded and res.coverage_complete
    assert len(session.calls) == 1
    assert len(res.items) == 30 and res.counts.filtered == 70


def test_newsfirehose_has_no_per_chunk_cap(monkeypatch):
    """Until 7 Oct a 3-page cap per chunk advanced coverage past unread rows.
    Now a broad keyword pages to the API's proven end."""
    coll, session = _firehose(monkeypatch, _nf_pages(950, step=timedelta(seconds=10)),
                              NEWSFIREHOSE_MAX_PAGES=50, NEWSFIREHOSE_MAX_PAGES_PER_CHUNK=2)
    res = run(coll.collect("AI", "t", interval_start=NOW - timedelta(days=1), interval_end=NOW))
    assert len(session.calls) == 10 and len(res.items) == 950
    assert res.succeeded and res.coverage_complete and res.may_advance_checkpoint


def test_newsfirehose_pages_newer_than_the_window_are_read_through(monkeypatch):
    """The API filters by whole days. A window ending mid-afternoon first
    returns everything published later that day; those pages are read and
    filtered, and the run goes on to the window itself."""
    coll, session = _firehose(monkeypatch, _nf_pages(1000, newest=NOW, step=timedelta(minutes=1)),
                              NEWSFIREHOSE_OVERLAP_HOURS=0, NEWSFIREHOSE_MAX_PAGES=50)
    res = run(coll.collect("AI", "t", interval_start=NOW - timedelta(hours=10),
                           interval_end=NOW - timedelta(hours=5)))
    # Rows 300..600 are the window; page 7 (rows 600..699) reaches past its start.
    assert [call["params"]["page"] for call in session.calls] == [1, 2, 3, 4, 5, 6, 7]
    assert len(res.items) == 301 and res.coverage_complete


def test_newsfirehose_budget_returns_partial_and_resumes_with_one_page_replay(monkeypatch):
    handler = _nf_pages(450)
    coll, session = _firehose(monkeypatch, handler, NEWSFIREHOSE_MAX_PAGES=2)
    first = run(coll.collect("SOC", "t", interval_start=NOW - timedelta(days=3), interval_end=NOW))
    assert first.status == c.STATUS_PARTIAL and not first.may_advance_checkpoint
    assert first.truncated_reason == c.TRUNC_TIME_BUDGET and not first.coverage_complete
    assert _cursor(first) == {"chunk": 0, "page": 3} and len(first.items) == 200
    coll2, session2 = _firehose(monkeypatch, handler, NEWSFIREHOSE_MAX_PAGES=5)
    second = run(coll2.collect("SOC", "t", interval_start=NOW - timedelta(days=3), interval_end=NOW,
                               continuation=first.continuation))
    # Page 2 is replayed because the sort has no tie-breaker; nothing is skipped.
    assert [call["params"]["page"] for call in session2.calls] == [2, 3, 4, 5]
    assert second.succeeded and second.coverage_complete
    urls = {i["url"] for i in first.items} | {i["url"] for i in second.items}
    assert len(urls) == 450


def test_newsfirehose_continuation_for_another_query_is_discarded(monkeypatch):
    coll, session = _firehose(monkeypatch, _nf_pages(50))
    res = run(coll.collect("SOC", "t", interval_start=START, interval_end=NOW,
                           continuation={"q": "something-else", "chunk": 3, "page": 9}))
    assert session.calls[0]["params"]["page"] == 1 and res.coverage_complete
    assert res.diagnostics["continuation_discarded"]


def test_newsfirehose_failure_on_page_two_keeps_page_one(monkeypatch):
    fail = lambda q, page: FakeResponse(503, {"detail": "busy"}) if page == 2 else None
    coll, session = _firehose(monkeypatch, _nf_pages(450, fail=fail))
    res = run(coll.collect("SOC", "t", interval_start=NOW - timedelta(days=3), interval_end=NOW))
    assert res.failed and res.error_code == c.ERR_HTTP_5XX and res.retryable
    assert len(res.items) == 100 and _cursor(res) == {"chunk": 0, "page": 2}
    assert not res.may_advance_checkpoint


def test_newsfirehose_failure_on_the_replayed_page_never_walks_the_cursor_back(monkeypatch):
    broken = {"on": False}
    fail = lambda q, page: FakeResponse(503, {"detail": "busy"}) if broken["on"] and page == 4 else None
    coll, session = _firehose(monkeypatch, _nf_pages(900, fail=fail), NEWSFIREHOSE_MAX_PAGES=4)
    first = run(coll.collect("SOC", "t", interval_start=NOW - timedelta(days=3), interval_end=NOW))
    assert _cursor(first) == {"chunk": 0, "page": 5}
    broken["on"] = True
    res = run(coll.collect("SOC", "t", interval_start=NOW - timedelta(days=3), interval_end=NOW,
                           continuation=first.continuation))
    assert session.calls[-1]["params"]["page"] == 4
    assert res.failed and _cursor(res) == {"chunk": 0, "page": 5}


def test_newsfirehose_or_chunks_are_all_read_and_deduplicated(monkeypatch):
    terms = " OR ".join(f"term{i}" for i in range(20))   # 20 terms -> chunks of 8, 8, 4
    coll, session = _firehose(monkeypatch, None, NEWSFIREHOSE_MAX_PAGES=50)
    chunks = coll._split_query_terms(coll._normalize_query(terms))
    assert len(chunks) == 3 and all(len(ch.split(" OR ")) <= 8 for ch in chunks)
    # Chunk 2 returns rows 30..179 and overlaps chunk 1's 0..149.
    session.handler = _nf_pages(150, per_q={chunks[0]: 0, chunks[1]: 30, chunks[2]: 1000})
    res = run(coll.collect(terms, "t", interval_start=NOW - timedelta(days=3), interval_end=NOW))
    assert res.succeeded and res.coverage_complete
    assert len(res.items) == 150 + 30 + 150 and res.counts.duplicate == 120
    assert {call["params"]["q"] for call in session.calls} == set(chunks)
    assert len(session.calls) == 6


def test_newsfirehose_failed_chunk_is_not_skipped(monkeypatch):
    terms = " OR ".join(f"term{i}" for i in range(12))
    coll, session = _firehose(monkeypatch, None)
    chunks = coll._split_query_terms(coll._normalize_query(terms))
    fail = lambda q, page: FakeResponse(401, {"detail": "bad key"}) if q == chunks[1] else None
    session.handler = _nf_pages(20, per_q={chunks[0]: 0, chunks[1]: 100}, fail=fail)
    res = run(coll.collect(terms, "t", interval_start=START, interval_end=NOW))
    assert res.failed and res.error_code == c.ERR_AUTH and not res.retryable
    assert len(res.items) == 20 and _cursor(res) == {"chunk": 1, "page": 1}


@pytest.mark.parametrize("body,why", [
    ({"articles": []}, "has_more"),
    ({"articles": [], "has_more": "no"}, "has_more"),
    ({"has_more": False}, "articles"),
    ({"articles": [], "has_more": True}, "empty page"),
    ("<html>gateway</html>", "JSON object"),
])
def test_newsfirehose_malformed_paging_is_never_a_proven_end(monkeypatch, body, why):
    coll, session = _firehose(monkeypatch, lambda u, p, h: FakeResponse(200, body))
    res = run(coll.collect("x", "t", interval_start=START, interval_end=NOW))
    assert res.failed and res.error_code == c.ERR_PARSE and not res.may_advance_checkpoint
    assert why in res.error_message


def test_newsfirehose_date_params_are_utc_days_with_slack(monkeypatch):
    coll, session = _firehose(monkeypatch, _nf_pages(3), NEWSFIREHOSE_OVERLAP_HOURS=0)
    # Cross-midnight in Berlin, same day in UTC: 2 Oct 21:30 .. 23:30 UTC.
    end = datetime(2026, 10, 2, 23, 30, tzinfo=timezone.utc)
    run(coll.collect("x", "t", interval_start=end - timedelta(hours=2), interval_end=end))
    p = session.calls[0]["params"]
    assert p["from_date"] == "2026-10-01" and p["to_date"] == "2026-10-04"


def test_newsfirehose_boundary_rows_are_kept(monkeypatch):
    """Rows exactly on the interval bounds, and rows just past local
    midnight, survive the client-side filter."""
    lo = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)   # 00:00 Berlin
    hi = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
    rows = [_nf_row(1, hi), _nf_row(2, datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)),
            _nf_row(3, lo), _nf_row(4, lo - timedelta(seconds=1))]
    coll, session = _firehose(monkeypatch, lambda u, p, h: FakeResponse(
        200, {"articles": rows, "has_more": False}), NEWSFIREHOSE_OVERLAP_HOURS=0)
    res = run(coll.collect("x", "t", interval_start=lo, interval_end=hi))
    assert sorted(int(i["url"].rsplit("/", 1)[1]) for i in res.items) == [1, 2, 3]
    assert res.counts.filtered == 1 and res.coverage_complete


@pytest.mark.parametrize("status,code,retryable", [
    (401, c.ERR_AUTH, False), (422, c.ERR_HTTP_4XX, False),
    (500, c.ERR_HTTP_5XX, True), (429, c.ERR_QUOTA, True)])
def test_newsfirehose_http_errors_never_look_like_an_empty_success(monkeypatch, status, code, retryable):
    coll, session = _firehose(monkeypatch, lambda u, p, h: FakeResponse(status, {"detail": "nope"}))
    res = run(coll.collect("x", "t", interval_start=START, interval_end=NOW))
    assert res.failed and res.error_code == code and res.retryable is retryable
    assert not res.may_advance_checkpoint
    assert _cursor(res) == {"chunk": 0, "page": 1}


@pytest.mark.parametrize("exc,code", [
    (TimeoutError("slow"), c.ERR_TIMEOUT),
    (ConnectionRefusedError("server stopped"), c.ERR_CONNECTION)])
def test_newsfirehose_exception_is_a_failure(monkeypatch, exc, code):
    def boom(url, params, headers):
        raise exc
    coll, session = _firehose(monkeypatch, boom)
    res = run(coll.collect("x", "t", interval_start=START, interval_end=NOW))
    assert res.failed and res.error_code == code and res.retryable


def test_newsfirehose_empty_query_sends_nothing(monkeypatch):
    coll, session = _firehose(monkeypatch, _nf_pages(3))
    res = run(coll.collect("  ", "t", interval_start=START, interval_end=NOW))
    assert res.succeeded and session.calls == []


def _search_session(monkeypatch, responder):
    from app.collectors import newsfirehose_collector as mod
    monkeypatch.setenv("NEWSFIREHOSE_API_KEY", "k-nf")
    sent = []

    class _Resp:
        def __init__(self, status, body):
            self.status, self._body = status, body
            self.content_type = "application/json"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def json(self, content_type=None): return self._body
        async def text(self): return json.dumps(self._body)

    class _Sess:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def get(self, url, params=None, headers=None):
            sent.append(dict(params))
            return _Resp(*responder(params))

    monkeypatch.setattr(mod.aiohttp, "ClientSession", _Sess)
    return mod.NewsFirehoseCollector(), sent


def test_newsfirehose_search_articles_sends_utc_day_bounds(monkeypatch):
    """The interactive search used by Auspex and the MCP tools."""
    coll, sent = _search_session(monkeypatch, lambda p: (200, {"articles": []}))
    run(coll.search_articles("x", "t", start_date=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
                             end_date=datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc)))
    assert sent[0]["to_date"] == "2026-10-04" and sent[0]["from_date"] == "2026-09-30"


def test_newsfirehose_search_articles_filters_to_the_requested_window(monkeypatch):
    """No more 30-day widening: a 2-day request returns 2 days."""
    now = datetime.now(timezone.utc)
    rows = [_nf_row(i, now - timedelta(days=d)) for i, d in enumerate((0.5, 1.5, 5, 20))]
    coll, sent = _search_session(monkeypatch, lambda p: (200, {"articles": rows}))
    out = run(coll.search_articles("x", "t", max_results=10, start_date=now - timedelta(days=2)))
    assert len(out) == 2


def test_newsfirehose_search_articles_raises_when_every_chunk_fails(monkeypatch):
    coll, sent = _search_session(monkeypatch, lambda p: (503, {"detail": "busy"}))
    with pytest.raises(Exception):
        run(coll.search_articles("x", "t"))


def test_newsfirehose_too_broad_keyword_is_a_visible_configuration_failure(monkeypatch):
    coll, session = _firehose(monkeypatch, _nf_pages(5000, step=timedelta(seconds=10)),
                              NEWSFIREHOSE_MAX_PAGES=50, NEWSFIREHOSE_BROAD_PAGES_PER_DAY=3,
                              NEWSFIREHOSE_OVERLAP_HOURS=0)
    res = run(coll.collect("AI", "t", interval_start=NOW - timedelta(hours=20), interval_end=NOW))
    assert res.failed and res.error_code == c.ERR_CONFIG and not res.retryable
    assert res.items == [] and not res.may_advance_checkpoint
    assert "too broad" in res.error_message and len(session.calls) == 3


def test_newsfirehose_broad_limit_scales_with_the_window(monkeypatch):
    # A 2-day window at 3 pages a day allows 6 pages per chunk; 5 pages completes.
    coll, session = _firehose(monkeypatch, _nf_pages(450, step=timedelta(seconds=10)),
                              NEWSFIREHOSE_MAX_PAGES=50, NEWSFIREHOSE_BROAD_PAGES_PER_DAY=3)
    res = run(coll.collect("AI", "t", interval_start=NOW - timedelta(days=2), interval_end=NOW))
    assert res.succeeded and res.coverage_complete and len(res.items) == 450
