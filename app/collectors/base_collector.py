"""Base class for article collectors.

Two entry points live on every collector:

- ``search_articles`` is the old list API. Callers that have not moved yet
  (Auspex tools, the MCP server, brand signals) keep using it.
- ``collect`` is the structured API background tasks use. It returns a
  ``CollectionResult`` so a caller can tell an empty interval from a failed
  request, keep a continuation when a run stopped early, and decide whether
  the coverage checkpoint may move.

The default ``collect`` wraps ``search_articles`` so a collector that has not
been rewritten still reports an outcome. A provider that pages, rate-limits
or filters dates overrides ``collect`` and makes ``search_articles`` delegate
to it.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 1 and 3.
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.collectors.contracts import (
    CollectionResult,
    TRUNC_PROVIDER_LIMIT,
    host_of,
)

logger = logging.getLogger(__name__)

#: Content kinds a collector may stamp on an item (work package 8).
CONTENT_FULL_TEXT = "full_text"
CONTENT_ABSTRACT = "abstract"
CONTENT_EXCERPT = "excerpt"
CONTENT_SOCIAL_POST = "social_post"
CONTENT_UNKNOWN = "unknown"


class ProviderHTTPError(Exception):
    """An HTTP status a provider answered with, carried as an exception so
    ``CollectionResult.from_exception`` classifies it the same way it
    classifies a client library's own errors."""

    def __init__(self, status: int, message: str = "", url: Optional[str] = None):
        self.status = int(status)
        self.url = url
        super().__init__(message or f"HTTP {status}")


def page_budget() -> "tuple[int, float]":
    """Pages and seconds one provider interval may spend (work package 3).
    ``PROVIDER_MAX_PAGES`` and ``PROVIDER_PAGE_BUDGET_SECONDS`` set the
    defaults; a provider may read its own override first."""
    try:
        pages = max(1, int(os.getenv("PROVIDER_MAX_PAGES", "5")))
    except ValueError:
        pages = 5
    try:
        seconds = max(1.0, float(os.getenv("PROVIDER_PAGE_BUDGET_SECONDS", "60")))
    except ValueError:
        seconds = 60.0
    return pages, seconds


def provider_max_pages(env_name: str, default: Optional[int] = None) -> int:
    """A provider's own page budget, falling back to the shared one."""
    raw = os.getenv(env_name)
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return default if default is not None else page_budget()[0]


def coerce_datetime(value: Any) -> Optional[datetime]:
    """A UTC-aware datetime from a datetime or ISO string. Naive input is
    taken as UTC; anything unparseable is None. Used for interval bounds,
    never for publication dates (those go through ``dates.parse_date``)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def in_interval(when: Optional[datetime], start: Optional[datetime], end: Optional[datetime]) -> bool:
    """True when ``when`` lies inside [start, end]. An unknown date is not
    outside the interval: the caller decides what to do with it."""
    if when is None:
        return True
    if start is not None and when < start:
        return False
    if end is not None and when > end:
        return False
    return True


class PageClock:
    """Tracks the page and time budget of one collection run."""

    def __init__(self, max_pages: int, max_seconds: float):
        self.max_pages = max_pages
        self.max_seconds = max_seconds
        self.started = time.monotonic()
        self.pages = 0

    def tick(self) -> None:
        self.pages += 1

    @property
    def exhausted(self) -> bool:
        return self.pages >= self.max_pages or (time.monotonic() - self.started) >= self.max_seconds

    @property
    def reason(self) -> str:
        """Why the run stopped: both the page cap and the clock are the
        caller's own budget, so both report ``time_budget``."""
        from app.collectors.contracts import TRUNC_TIME_BUDGET
        return TRUNC_TIME_BUDGET


class ArticleCollector(ABC):
    """Base class for article collectors."""

    #: Ledger and run-record name. Defaults to the class name without the
    #: ``Collector`` suffix, lower-cased; a subclass may set it explicitly.
    provider_name: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("provider_name"):
            name = cls.__name__
            if name.lower().endswith("collector"):
                name = name[: -len("collector")]
            cls.provider_name = name.lower()

    @abstractmethod
    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Search for articles based on query and topic.

        Args:
            query: Search query string
            topic: Topic name from the application's topics
            max_results: Maximum number of results to return
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering

        Returns:
            List of article dictionaries with standardized fields:
            {
                'title': str,
                'summary': str,
                'authors': List[str],
                'published_date': datetime,
                'url': str,
                'source': str,
                'topic': str,
                'raw_data': Dict  # Source-specific raw data
            }
        """
        pass

    @abstractmethod
    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch full content of an article.

        Args:
            url: Article URL or identifier

        Returns:
            Dictionary containing article content and metadata
        """
        pass

    # -- structured collection (work package 1) --------------------------------

    def new_result(self, query: Optional[str], interval_start: Optional[datetime],
                   interval_end: Optional[datetime], **kw: Any) -> CollectionResult:
        """An empty successful result stamped with this provider and interval."""
        res = CollectionResult.ok([], provider=self.provider_name, scope=query, **kw)
        res.interval_start = coerce_datetime(interval_start)
        res.interval_end = coerce_datetime(interval_end)
        return res.mark_started()

    def stamp_items(self, items: List[Dict], content_kind: Optional[str] = None) -> List[Dict]:
        """Mark every item with the provider that produced it and a content
        kind, so ingest never has to guess either."""
        for item in items:
            if isinstance(item, dict):
                item["_collector_provider"] = self.provider_name
                if content_kind and not item.get("content_kind"):
                    item["content_kind"] = content_kind
                item.setdefault("content_kind", CONTENT_UNKNOWN)
        return items

    def finish(self, res: CollectionResult, query: Optional[str] = None,
               interval_start: Optional[datetime] = None,
               interval_end: Optional[datetime] = None) -> CollectionResult:
        """Fill provider, scope and interval on a result built by a
        constructor that did not know them, stamp the items, mark finished."""
        res.provider = res.provider or self.provider_name
        if res.scope is None:
            res.scope = query
        if res.interval_start is None:
            res.interval_start = coerce_datetime(interval_start)
        if res.interval_end is None:
            res.interval_end = coerce_datetime(interval_end)
        self.stamp_items(res.items)
        return res.mark_finished()

    async def collect(
        self,
        query: str,
        topic: str,
        *,
        interval_start: Optional[datetime] = None,
        interval_end: Optional[datetime] = None,
        max_results: int = 10,
        continuation: Optional[Dict[str, Any]] = None,
        **kw: Any,
    ) -> CollectionResult:
        """Collect over a fixed interval and report the outcome.

        The default wraps ``search_articles``. A full page from a list API has
        no proven end, so it is reported as coverage incomplete with a
        provider-limit truncation; fewer results than asked for is complete.
        An exception becomes a failed result with a classified error code.
        """
        res = self.new_result(query, interval_start, interval_end)
        try:
            items = await self.search_articles(
                query, topic, max_results, start_date=interval_start, end_date=interval_end, **kw)
        except Exception as exc:  # noqa: BLE001
            host = host_of(getattr(self, "base_url", None))
            out = CollectionResult.from_exception(exc, host=host, continuation=continuation)
            out.started_at = res.started_at
            return self.finish(out, query, interval_start, interval_end)
        items = list(items or [])
        res.items = items
        res.counts.received = len(items)
        if max_results and len(items) >= max_results:
            res.coverage_complete = False
            res.truncated_reason = TRUNC_PROVIDER_LIMIT
            res.diagnostics["note"] = "list API returned a full page; no proven end"
        return self.finish(res, query, interval_start, interval_end)


async def get_json(session, url: str, *, params: Optional[Dict[str, Any]] = None,
                   headers: Optional[Dict[str, str]] = None, timeout: float = 30.0
                   ) -> "tuple[int, Any, Dict[str, str]]":
    """One GET, returning ``(status, body, headers)``. The body is parsed JSON
    when the provider sent JSON, otherwise the text. The session is whatever
    the collector's ``_session()`` factory returned, so tests can hand in a
    fake with the same ``get`` shape."""
    import aiohttp

    kwargs: Dict[str, Any] = {"params": params}
    if headers:
        kwargs["headers"] = headers
    try:
        kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout)
    except Exception:  # noqa: BLE001
        pass
    async with session.get(url, **kwargs) as response:
        status = int(getattr(response, "status", 0) or 0)
        try:
            body = await response.json(content_type=None)
        except Exception:  # noqa: BLE001
            try:
                body = await response.text()
            except Exception:  # noqa: BLE001
                body = ""
        raw_headers = getattr(response, "headers", None) or {}
        try:
            hdrs = {str(k): str(v) for k, v in raw_headers.items()}
        except Exception:  # noqa: BLE001
            hdrs = {}
        return status, body, hdrs


def provider_message(body: Any, default: str = "") -> str:
    """The human-readable error a provider put in its body, if any."""
    if isinstance(body, dict):
        for key in ("message", "error", "detail"):
            val = body.get(key)
            if isinstance(val, dict):
                val = val.get("message")
            if val:
                return str(val)[:300]
        res = body.get("results")
        if isinstance(res, dict) and res.get("message"):
            return str(res["message"])[:300]
    elif isinstance(body, str) and body.strip():
        return body.strip()[:300]
    return default
