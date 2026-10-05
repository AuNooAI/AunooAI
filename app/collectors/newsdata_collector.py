"""NewsData.io collector.

Three things changed here against the spec.

- Work package 9: the query is parsed as an expression and compiled for
  NewsData's ``q`` syntax (AND, OR, NOT, quoted phrases, brackets, 512
  characters). Phrases, full brand names and Unicode survive. An expression
  NewsData cannot express is refused with ``unsupported_query`` and no
  request is sent. Nothing is ever replaced by "news" or "AI".
- Work package 26: whether the plan supports date filtering is declared,
  not logged. With ``NEWSDATA_DATE_FILTER_SUPPORTED=1`` the interval is sent
  as ``from_date`` and ``to_date``. Otherwise the run record says the date
  clause was dropped (``truncated_reason=provider_no_date_filter``,
  ``coverage_complete=False``) and records outside the interval are filtered
  locally and counted.
- Work package 20: every request goes through the host-wide quota guard.
  The per-process daily counter that never fired on a shared key is gone;
  ``requests_today`` stays for the monitor's log line.

API facts this file relies on (NewsData.io documentation, checked
2026-10-01): ``q`` supports AND, OR, NOT, quotes and brackets up to 512
characters; ``size`` is at most 10 on the free plan and 50 on paid plans;
paging is by the ``page`` token the previous response returned as
``nextPage``; ``pubDate`` is ``YYYY-MM-DD HH:MM:SS`` in UTC (``pubDateTZ``);
the free plan serves ``content`` as the literal text "ONLY AVAILABLE IN
PAID PLANS".

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 7, 9, 20 and 26.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_EXCERPT, CONTENT_FULL_TEXT, PageClock, ProviderHTTPError,
    coerce_datetime, get_json, in_interval, page_budget, provider_max_pages, provider_message,
)
from app.collectors.contracts import (
    CollectionResult, ERR_HTTP_4XX, ERR_UNSUPPORTED_QUERY, TRUNC_NO_DATE_FILTER, TRUNC_RETENTION,
)
from app.collectors.dates import parse_date
from app.collectors.query_expression import compile_for, parse_expression
from app.services.provider_quota import QuotaGuard, looks_exhausted

logger = logging.getLogger(__name__)

_CATEGORIES = ('business', 'entertainment', 'environment', 'food', 'health', 'politics',
               'science', 'sports', 'technology', 'top', 'tourism', 'world')
_PAID_ONLY = "only available in paid plans"


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


def date_filter_supported() -> bool:
    """Whether the plan on this key accepts ``from_date``/``to_date``."""
    return os.getenv("NEWSDATA_DATE_FILTER_SUPPORTED", "0").strip().lower() in ("1", "true", "yes", "on")


class NewsdataCollector(ArticleCollector):
    """Collector for NewsData.io API service."""

    provider_name = "newsdata"

    @staticmethod
    def is_configured() -> bool:
        """Check if NewsData.io API key is configured without initializing the collector."""
        api_key = os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY')
        return bool(api_key)

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY')
        if not self.api_key:
            logger.error("NewsData.io API key not found in environment")
            raise ValueError("NewsData.io API key not configured")
        self.base_url = "https://newsdata.io/api/1/news"
        self.requests_today = 0
        self.last_request_date = date.today()

    def _increment_request_count(self):
        """Count requests for the monitor's log line. Nothing here decides
        whether a request is sent; the shared ledger does."""
        current_date = date.today()
        if current_date > self.last_request_date:
            self.requests_today = 0
            self.last_request_date = current_date
        self.requests_today += 1
        logger.debug(f"NewsData.io requests today: {self.requests_today}")

    def _simplify_query(self, query: str) -> Optional[str]:
        """Compile the operator's expression for NewsData. Returns the provider
        query, or None when it cannot be expressed (``collect`` then refuses
        the run instead of sending something else)."""
        compiled = compile_for("newsdata", parse_expression(query))
        return compiled.query if compiled.ok else None

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
        language: str = "en",
        country: Optional[str] = None,
        category: Optional[str] = None,
        domain: Optional[List[str]] = None,
        exclude_domain: Optional[List[str]] = None,
        prioritydomain: Optional[str] = None,
        max_pages: Optional[int] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        expr = parse_expression(query)
        compiled = compile_for("newsdata", expr)
        res.diagnostics.update({
            "original_expression": expr.original,
            "compiled_query": compiled.query,
            "translation_status": compiled.status,
        })
        if expr.empty:
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        if not compiled.ok:
            out = CollectionResult.failure(
                ERR_UNSUPPORTED_QUERY,
                f"newsdata cannot express this query: {compiled.reason}", retryable=False)
            out.diagnostics.update(res.diagnostics)
            out.started_at = res.started_at
            return self.finish(out, query, interval_start, interval_end)

        params: Dict[str, Any] = {"apikey": self.api_key, "q": compiled.query}
        if language and len(language) == 2:
            params["language"] = language
        size = max(1, min(int(max_results or 10), 50))
        params["size"] = size
        if country and len(country) == 2:
            params["country"] = country
        if category and category in _CATEGORIES:
            params["category"] = category
        if domain and isinstance(domain, list):
            valid = [d for d in domain if isinstance(d, str) and '.' in d]
            if valid:
                params["domain"] = ",".join(valid[:5])
        if exclude_domain and isinstance(exclude_domain, list):
            valid = [d for d in exclude_domain if isinstance(d, str) and '.' in d]
            if valid:
                params["excludedomain"] = ",".join(valid[:5])
        if prioritydomain:
            params["prioritydomain"] = prioritydomain

        dates_sent = date_filter_supported()
        has_interval = bool(res.interval_start or res.interval_end)
        if dates_sent and has_interval:
            if res.interval_start:
                params["from_date"] = res.interval_start.strftime("%Y-%m-%d")
            if res.interval_end:
                params["to_date"] = res.interval_end.strftime("%Y-%m-%d")
            res.diagnostics["date_clause"] = "sent"
        elif has_interval:
            res.diagnostics["date_clause"] = "dropped:provider_no_date_filter"
        else:
            res.diagnostics["date_clause"] = "none"

        page_token = (continuation or {}).get("page")
        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("NEWSDATA_MAX_PAGES", pages), seconds)
        guard = QuotaGuard(self.provider_name, self.api_key, scope=query)
        seen = set()
        host = "newsdata.io"

        def _declare(out: CollectionResult) -> CollectionResult:
            """Work package 26: a run whose date clause was dropped never
            claims complete coverage, whatever it collected."""
            if has_interval and not dates_sent:
                out.coverage_complete = False
                if not out.truncated_reason:
                    out.truncated_reason = TRUNC_NO_DATE_FILTER
            elif has_interval and dates_sent and out.status == "success" and out.coverage_complete:
                # The provider bounds the archive by plan retention; say so
                # without pretending the limitation is ours.
                out.diagnostics.setdefault("coverage_note", "bounded by provider retention")
            return out

        def _carry(out: CollectionResult, cont: Optional[Dict[str, Any]]) -> CollectionResult:
            out.items, out.counts, out.started_at = res.items, res.counts, res.started_at
            out.continuation = cont
            out.diagnostics.update(res.diagnostics)
            return self.finish(_declare(out), query, interval_start, interval_end)

        try:
            async with _session() as session:
                while True:
                    blocked = guard.check()
                    if blocked is not None:
                        return _carry(blocked, {"page": page_token} if page_token else None)
                    if page_token:
                        params["page"] = page_token
                    else:
                        params.pop("page", None)
                    self._increment_request_count()
                    logger.info(f"NewsData.io request: q={compiled.query!r} size={size} page={page_token or 1}")
                    status, data, headers = await get_json(session, self.base_url, params=params)
                    clock.tick()
                    body = data if isinstance(data, dict) else {}
                    message = provider_message(data, f"HTTP {status}")

                    if status == 200 and body.get("status") != "error":
                        guard.ok()
                        articles = body.get("results") or []
                        res.counts.received += len(articles)
                        oldest: Optional[datetime] = None
                        for article in articles:
                            item = self._format_article(article, topic)
                            if not item or not item.get("url"):
                                res.counts.invalid += 1
                                continue
                            when = coerce_datetime(item.get("published_date"))
                            if when and (oldest is None or when < oldest):
                                oldest = when
                            if not dates_sent and has_interval and when is not None and \
                                    not in_interval(when, res.interval_start, res.interval_end):
                                res.counts.filtered += 1
                                continue
                            key = item["raw_data"].get("article_id") or item["url"]
                            if key in seen:
                                res.counts.duplicate += 1
                                continue
                            seen.add(key)
                            res.items.append(item)
                        res.diagnostics["total_results"] = int(body.get("totalResults") or 0)
                        next_token = body.get("nextPage")
                        if not next_token or len(articles) < size:
                            return self.finish(_declare(res))
                        # Newest first: once a page is older than the
                        # interval start, the rest is older still.
                        if has_interval and res.interval_start and oldest is not None and oldest < res.interval_start:
                            res.diagnostics["stopped_at"] = "page older than interval start"
                            return self.finish(_declare(res))
                        page_token = str(next_token)
                        if clock.exhausted:
                            out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
                                                           continuation={"page": page_token})
                            return _carry(out, {"page": page_token})
                        continue

                    if looks_exhausted(status, data):
                        until = guard.exhausted(retry_after=headers.get("Retry-After"), detail=message)
                        out = guard.result_for_exhaustion(until, f"newsdata: {message}")
                        return _carry(out, {"page": page_token} if page_token else None)

                    guard.error(message)
                    logger.error(f"NewsData.io API error {status}: {message} (q={compiled.query!r})")
                    low = message.lower()
                    if status == 422 and ("from_date" in low or "to_date" in low or "archive" in low):
                        # The plan rejected the date clause after all. Report it
                        # as a retention limit rather than a query fault, so the
                        # operator sees the plan and the flag disagree.
                        out = CollectionResult.failure(
                            ERR_HTTP_4XX, f"newsdata rejected the date filter: {message}",
                            retryable=False, truncated_reason=TRUNC_RETENTION)
                        out.diagnostics["date_clause"] = "rejected_by_provider"
                        return _carry(out, None)
                    exc = ProviderHTTPError(status, message, url=self.base_url)
                    out = CollectionResult.from_exception(exc, host=host)
                    return _carry(out, {"page": page_token} if page_token else None)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"NewsData.io request failed: {type(exc).__name__}: {exc}", exc_info=True)
            guard.error(f"{type(exc).__name__}: {exc}")
            out = CollectionResult.from_exception(exc, host=host)
            return _carry(out, {"page": page_token} if page_token else None)

    # -- compatibility list API --------------------------------------------

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = "en",
        country: Optional[str] = None,
        category: Optional[str] = None,
        domain: Optional[List[str]] = None,
        exclude_domain: Optional[List[str]] = None,
        prioritydomain: Optional[str] = None,
        **kwargs
    ) -> List[Dict]:
        """One page, as a list. Failures log and return an empty list."""
        result = await self.collect(
            query, topic, interval_start=start_date, interval_end=end_date, max_results=max_results,
            language=language, country=country, category=category, domain=domain,
            exclude_domain=exclude_domain, prioritydomain=prioritydomain, max_pages=1)
        if result.failed:
            logger.error(f"NewsData.io search failed: {result.error_message}")
        return result.items[:max_results]

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """NewsData has no fetch-by-URL endpoint. Search results already carry
        everything the plan serves, so there is nothing to fetch here."""
        return None

    def _format_article(self, article: Dict, topic: Optional[str]) -> Optional[Dict]:
        """Format NewsData.io article data to standard format."""
        try:
            # Source name: source_url (the publisher) before the article link
            # before source_id (often truncated without a TLD).
            source_name = ''
            source_url = article.get('source_url', '')
            if source_url:
                source_name = urlparse(source_url).netloc.replace('www.', '')
            if not source_name:
                link = article.get('link', '')
                if link:
                    source_name = urlparse(link).netloc.replace('www.', '')
            if not source_name:
                source_name = article.get('source_id', '')

            # pubDate is UTC per the provider (pubDateTZ). Missing stays
            # missing; nothing substitutes the current time (work package 7).
            parsed = parse_date(article.get('pubDate'), assume_utc=True)

            keywords = article.get('keywords', []) or []
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]

            content = article.get('content') or ''
            if _PAID_ONLY in content.lower():
                content = ''
            content_kind = CONTENT_FULL_TEXT if content else CONTENT_EXCERPT

            return {
                'title': article.get('title', '') or '',
                'summary': article.get('description', '') or '',
                'content': content or (article.get('description', '') or ''),
                'content_kind': content_kind,
                'authors': article.get('creator', []) or [],
                'published_date': parsed.iso(),
                'published_at_raw': parsed.raw,
                'date_provenance': parsed.provenance if parsed.known else None,
                'url': article.get('link', '') or '',
                'source': source_name,
                'topic': topic,
                'raw_data': {
                    'article_id': article.get('article_id'),
                    'source_id': article.get('source_id'),
                    'source_url': article.get('source_url'),
                    'country': article.get('country', []),
                    'category': article.get('category', []),
                    'language': article.get('language'),
                    'keywords': keywords,
                    'image_url': article.get('image_url'),
                    'video_url': article.get('video_url'),
                    'sentiment': article.get('sentiment'),
                    'duplicate': article.get('duplicate')
                }
            }

        except Exception as e:
            logger.error(f"Error formatting NewsData.io article: {str(e)}")
            return None

    async def test_connection(self) -> bool:
        """Test the connection to NewsData.io API with a one-result request."""
        guard = QuotaGuard(self.provider_name, self.api_key, scope="test_connection")
        try:
            if guard.check() is not None:
                logger.warning("NewsData.io connection test skipped: key is paused in the shared ledger")
                return False
            params = {"apikey": self.api_key, "q": "news", "language": "en", "size": 1}
            self._increment_request_count()
            async with _session() as session:
                status, data, headers = await get_json(session, self.base_url, params=params)
            if status == 200 and isinstance(data, dict) and data.get("status") != "error":
                guard.ok()
                return True
            if looks_exhausted(status, data):
                guard.exhausted(retry_after=headers.get("Retry-After"), detail=provider_message(data))
            else:
                guard.error(provider_message(data, f"HTTP {status}"))
            logger.error(f"NewsData.io test failed {status}: {provider_message(data)}")
            return False
        except Exception as e:
            logger.error(f"NewsData.io connection test failed: {str(e)}")
            return False
