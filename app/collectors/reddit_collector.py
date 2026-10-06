"""Reddit collector: subreddit feed plus keyword search via Reddit's free RSS.

No OAuth or API key. Two routes, each with its own budget and its own
identity set (work package 10), merged into one ``CollectionResult`` so a
failed route shows as a partial run instead of a quiet success:

1. Subreddit feed ``r/<slug>/.rss``. The slug is inferred from the brand
   term, so an item from here is a discovery candidate, not proof of
   relevance: ``raw_data["route"] == "subreddit"`` and
   ``raw_data["subreddit_inferred"]`` is True. It bypasses the term filter.
2. Search ``search.rss?q=<term>&sort=new``. Newest first for monitoring,
   paged with ``after`` until the interval is covered or the page budget is
   spent. Reddit search stems and returns cross-sub noise, so results are
   kept only when a brand term appears. ``raw_data["route"] == "search"``.

Reddit rate-limits by client address and every site on this host shares
one, so each request first asks the host-wide ``HostGuard`` and a 429
pauses reddit.com for everyone (work package 21).

Dates come from the feed's ``published_parsed`` through the shared parser;
a missing date stays None (work package 7).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
import feedparser

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_SOCIAL_POST, PageClock, ProviderHTTPError, coerce_datetime,
    in_interval, page_budget, provider_max_pages,
)
from app.collectors.contracts import (
    CollectionResult, STATUS_FAILED, STATUS_PARTIAL, STATUS_SUCCESS, TRUNC_PROVIDER_LIMIT,
)
from app.collectors.dates import parse_date
from app.services.provider_quota import HostGuard

logger = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_DEFAULT_UA = "aunoo-reddit-collector/1.0 (+https://aunoo.ai)"
_HOST = "reddit.com"


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = re.sub(r"\s+", " ", _TAG.sub(" ", html)).strip()
    return text[:1000] or None


def _entry_dt(entry) -> Optional[datetime]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return parse_date(parsed).value if parsed else None


def _social_meta(external_id: Any, author: Optional[str], permalink: Optional[str],
                 subreddit: Optional[str], created) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"platform": "reddit", "external_id": str(external_id),
                            "author": author, "subreddit": subreddit, "permalink": permalink}
    if created is not None and created.known:
        meta["created_at"] = created.iso()
    return meta


class RedditCollector(ArticleCollector):
    """Collector for Reddit posts via free RSS feeds (no credentials)."""

    provider_name = "reddit"

    def __init__(self):
        self.user_agent = os.getenv("REDDIT_USER_AGENT", _DEFAULT_UA)
        self.base_url = "https://www.reddit.com"
        self.requests_today = 0  # rate-counter expected by keyword_monitor logging
        logger.info("RedditCollector initialized (RSS, no credentials)")

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": self.user_agent,
                "Accept": "application/atom+xml, application/rss+xml, text/xml"}

    # -- one feed request -------------------------------------------------------

    async def _feed(self, session, url: str, params=None) -> List[Any]:
        """Fetch and parse one feed. Raises ``ProviderHTTPError`` for a
        non-200 answer so the route reports it; a 429 also pauses the host
        for every site."""
        blocked = HostGuard(_HOST).check()
        if blocked is not None:
            raise ProviderHTTPError(429, blocked.error_message or "reddit.com paused in the shared ledger", url=url)
        self.requests_today += 1
        async with session.get(url, headers=self._headers(), params=params) as resp:
            status = int(getattr(resp, "status", 0) or 0)
            if status == 429:
                hdrs = getattr(resp, "headers", None) or {}
                HostGuard(_HOST).rate_limited(hdrs.get("Retry-After") if hasattr(hdrs, "get") else None)
                raise ProviderHTTPError(429, "Reddit answered 429", url=url)
            if status != 200:
                raise ProviderHTTPError(status, f"Reddit feed returned {status}", url=url)
            text = await resp.text()
        return feedparser.parse(text).entries or []

    # -- mapping ------------------------------------------------------------------
    # social_meta is what the Social tab, the observers' social branch and the
    # briefing key on. It carries the fields the product needs and only those
    # the provider gave: author, permalink, timestamp, subreddit, and on the
    # JSON route the engagement counts. A missing field stays missing.

    @staticmethod
    def _item(e, topic: Optional[str], *, route: str, inferred: bool) -> Optional[Dict[str, Any]]:
        title = e.get("title")
        url = e.get("link")
        ext = e.get("id") or url
        if not title or not url or not ext:
            return None
        body = _strip_html(e.get("summary"))
        pub = parse_date(e.get("published_parsed") or e.get("updated_parsed"))
        source_name = urlparse(url).netloc.replace("www.", "") or "reddit.com"
        m = re.search(r"/r/([A-Za-z0-9_]+)/", url or "")
        subreddit = m.group(1) if m else None
        return {
            "title": title,
            "summary": body or "",
            "content": body or "",
            "content_kind": CONTENT_SOCIAL_POST,
            "authors": [e.get("author")] if e.get("author") else [],
            "published_date": pub.iso(),
            "published_at_raw": pub.raw,
            "date_provenance": pub.provenance if pub.known else None,
            "url": url,
            "source": source_name,
            "topic": topic,
            "social_meta": _social_meta(ext, e.get("author"), url, subreddit, pub),
            "raw_data": {
                "platform": "reddit",
                "external_id": str(ext),
                "subreddit": subreddit,
                "route": route,
                "subreddit_inferred": inferred,
            },
        }

    @staticmethod
    def _mentions(item: Dict[str, Any], terms: List[str]) -> bool:
        blob = f"{item['title']} {item.get('summary') or ''}".lower()
        return any(re.search(r"\b" + re.escape(t) + r"\b", blob) for t in terms)

    # -- routes -------------------------------------------------------------------

    async def _subreddit_route(self, session, slug: str, topic, budget: int, start, end) -> CollectionResult:
        out = self.new_result(f"r/{slug}", start, end)
        out.scope = "subreddit"
        try:
            entries = await self._feed(session, f"{self.base_url}/r/{slug}/.rss", params={"limit": budget})
        except Exception as exc:  # noqa: BLE001
            fail = CollectionResult.from_exception(exc, host=_HOST, scope="subreddit")
            fail.started_at = out.started_at
            return fail.mark_finished()
        seen = set()
        out.counts.received = len(entries)
        for e in entries:
            item = self._item(e, topic, route="subreddit", inferred=True)
            if item is None:
                out.counts.invalid += 1
                continue
            key = item["raw_data"]["external_id"]
            if key in seen:
                out.counts.duplicate += 1
                continue
            seen.add(key)
            out.items.append(item)
            if len(out.items) >= budget:
                break
        return out.mark_finished()

    async def _search_route(self, session, term: str, terms: List[str], topic, budget: int,
                            start, end, continuation: Optional[Dict[str, Any]],
                            max_pages: Optional[int]) -> CollectionResult:
        out = self.new_result(term, start, end)
        out.scope = "search"
        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("REDDIT_MAX_PAGES", pages), seconds)
        after = (continuation or {}).get("after")
        seen = set()
        limit = max(1, min(budget, 100))
        while True:
            params = {"q": term, "sort": "new", "limit": limit, "type": "link"}
            if after:
                params["after"] = after
            try:
                entries = await self._feed(session, f"{self.base_url}/search.rss", params=params)
            except Exception as exc:  # noqa: BLE001
                fail = CollectionResult.from_exception(exc, host=_HOST, scope="search",
                                                       continuation={"after": after} if after else None)
                fail.items, fail.counts, fail.started_at = out.items, out.counts, out.started_at
                return fail.mark_finished()
            clock.tick()
            out.counts.received += len(entries)
            oldest: Optional[datetime] = None
            last_id = None
            for e in entries:
                item = self._item(e, topic, route="search", inferred=False)
                if item is None:
                    out.counts.invalid += 1
                    continue
                last_id = item["raw_data"]["external_id"]
                when = coerce_datetime(item["published_date"])
                if when and (oldest is None or when < oldest):
                    oldest = when
                if when is not None and not in_interval(when, out.interval_start, out.interval_end):
                    out.counts.filtered += 1
                    continue
                if not self._mentions(item, terms):
                    out.counts.filtered += 1
                    continue
                if last_id in seen:
                    out.counts.duplicate += 1
                    continue
                seen.add(last_id)
                out.items.append(item)
            if len(out.items) >= budget:
                # This route's own allowance is spent; the subreddit route
                # keeps its own (work package 10).
                out.coverage_complete = False
                out.truncated_reason = TRUNC_PROVIDER_LIMIT
                out.continuation = {"after": last_id} if last_id else None
                return out.mark_finished()
            if len(entries) < limit or not last_id:
                return out.mark_finished()
            if out.interval_start and oldest is not None and oldest < out.interval_start:
                out.diagnostics["stopped_at"] = "page older than interval start"
                return out.mark_finished()
            after = last_id
            if clock.exhausted:
                part = CollectionResult.partial(out.items, truncated_reason=clock.reason,
                                                continuation={"after": after}, scope="search")
                part.counts, part.started_at = out.counts, out.started_at
                part.interval_start, part.interval_end = out.interval_start, out.interval_end
                return part.mark_finished()

    # -- structured collection ------------------------------------------------

    async def collect(
        self,
        query: str,
        topic: Optional[str] = None,
        *,
        interval_start: Optional[datetime] = None,
        interval_end: Optional[datetime] = None,
        max_results: int = 10,
        continuation: Optional[Dict[str, Any]] = None,
        max_pages: Optional[int] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        term = (query or "").strip()
        if not term:
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        raw_terms = re.split(r"\s+OR\s+|,", term, flags=re.IGNORECASE)
        terms = [t.strip().strip('"').lower() for t in raw_terms if t.strip().strip('"')]
        primary = terms[0] if terms else term.lower()
        slug = re.sub(r"[^a-z0-9]", "", primary.lower())
        budget = max(1, int(max_results or 10))

        routes: List[CollectionResult] = []
        try:
            async with _session() as session:
                if slug:
                    routes.append(await self._subreddit_route(session, slug, topic, budget,
                                                              interval_start, interval_end))
                routes.append(await self._search_route(session, term, terms, topic, budget,
                                                       interval_start, interval_end, continuation, max_pages))
        except Exception as exc:  # noqa: BLE001
            out = CollectionResult.from_exception(exc, host=_HOST)
            out.started_at = res.started_at
            return self.finish(out, query, interval_start, interval_end)

        # Merge successes first so a failed route makes the whole partial
        # rather than hiding the records the other route brought back.
        order = {STATUS_SUCCESS: 0, STATUS_PARTIAL: 1, STATUS_FAILED: 2}
        for route in sorted(routes, key=lambda r: order.get(r.status, 3)):
            res.merge(route)
        # The same post through both routes is one record.
        seen = set()
        unique = []
        for item in res.items:
            key = item["raw_data"]["external_id"]
            if key in seen:
                res.counts.duplicate += 1
                continue
            seen.add(key)
            unique.append(item)
        res.items = unique
        res.diagnostics["subreddit"] = slug or None
        res.diagnostics["terms"] = terms
        logger.info(f"Reddit returned {len(res.items)} posts for query '{term[:60]}' (r/{slug} + search), status {res.status}")
        return self.finish(res)

    # -- compatibility list API --------------------------------------------

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = "en",
        locale: Optional[str] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        exclude_source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        page: int = 1,
    ) -> List[Dict]:
        """Both routes, as a list. Failures log and return what was found."""
        result = await self.collect(query, topic, interval_start=start_date, interval_end=end_date,
                                    max_results=max_results, max_pages=1)
        if result.failed:
            logger.error(f"Reddit search failed: {result.error_message}")
        return result.items

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch a single Reddit post's content via its ``.json`` endpoint."""
        try:
            if HostGuard(_HOST).check() is not None:
                return None
            json_url = url.rstrip("/") + "/.json"
            headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
            async with _session() as session:
                async with session.get(json_url, headers=headers) as resp:
                    if resp.status == 429:
                        HostGuard(_HOST).rate_limited((getattr(resp, "headers", None) or {}).get("Retry-After"))
                        return None
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            # Reddit post JSON: [ {listing of post}, {listing of comments} ]
            post = data[0]["data"]["children"][0]["data"]
            body = post.get("selftext") or post.get("title", "")
            created = parse_date(post.get("created_utc"))
            parsed = urlparse(url)
            meta = _social_meta(post.get("name") or post.get("id") or url, post.get("author"),
                                post.get("permalink") and ("https://www.reddit.com" + post["permalink"]) or url,
                                post.get("subreddit"), created)
            # Engagement only as the provider gave it; the RSS route has none.
            for key in ("score", "num_comments", "upvote_ratio"):
                if post.get(key) is not None:
                    meta[key] = post[key]
            return {
                "title": post.get("title", ""),
                "content": body,
                "content_kind": CONTENT_SOCIAL_POST,
                "authors": [post.get("author")] if post.get("author") else [],
                "published_date": created.iso(),
                "url": url,
                "source": parsed.netloc.replace("www.", "") or "reddit.com",
                "social_meta": meta,
                "raw_data": {"platform": "reddit", "subreddit": post.get("subreddit")},
            }
        except Exception as e:
            logger.error(f"Reddit fetch_article_content error: {e}")
            return None
