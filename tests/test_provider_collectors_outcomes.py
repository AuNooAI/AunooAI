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
    assert full.succeeded and not full.coverage_complete and full.truncated_reason == c.TRUNC_PROVIDER_LIMIT
    bad = run(Plain().collect("boom", "t", interval_start=START, interval_end=NOW))
    assert bad.failed and bad.error_code == c.ERR_TIMEOUT and bad.retryable


def test_newsfirehose_accepts_aware_interval_bounds():
    """The keyword monitor hands over timezone-aware bounds; the firehose
    collector compares against the naive local clock. Mixing the two raised
    TypeError on every poll for eight hours after the 1 Oct restart."""
    from datetime import datetime, timedelta, timezone
    from app.collectors.newsfirehose_collector import _naive_local
    aware = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    out = _naive_local(aware)
    assert out.tzinfo is None
    # Same instant on the local clock, so arithmetic with datetime.now() works.
    assert abs((out - aware.astimezone().replace(tzinfo=None)).total_seconds()) < 1
    assert (datetime.now() - out) > timedelta(0)
    naive = datetime(2026, 10, 1, 12, 0)
    assert _naive_local(naive) is naive and _naive_local(None) is None and _naive_local("2026-10-01") == "2026-10-01"
