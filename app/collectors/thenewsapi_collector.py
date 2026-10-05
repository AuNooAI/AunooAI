"""TheNewsAPI collector.

``collect`` pages ``/v1/news/all`` behind one ``CollectionResult`` (work
package 3) and sends every request through the host-wide quota guard (work
package 20). The old per-process daily counter is gone: it only ever saw one
site, so it never fired on a shared key.

API facts this file relies on (TheNewsAPI documentation, checked
2026-10-01): ``limit`` is capped by plan (the free plan serves 3 per
request); ``page`` is 1-based; ``published_after`` and ``published_before``
accept ``Y-m-d\\TH:i:s``; ``sort`` is ``published_at`` or ``relevance_score``;
the response's ``meta`` carries ``found``, ``returned``, ``limit`` and
``page``; the body of an article is not served, only ``snippet``.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 3, 8 and 20.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_EXCERPT, PageClock, ProviderHTTPError, coerce_datetime,
    get_json, page_budget, provider_max_pages, provider_message,
)
from app.collectors.contracts import CollectionResult
from app.collectors.dates import parse_date
from app.services.provider_quota import QuotaGuard, looks_exhausted

logger = logging.getLogger(__name__)

_FIELD_MAP = {"title": "title", "description": "description",
              "content": "main_text", "main_text": "main_text", "keywords": "keywords"}


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


def _iso_param(value) -> Optional[str]:
    dt = coerce_datetime(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


class TheNewsAPICollector(ArticleCollector):
    """Collector for TheNewsAPI service."""

    provider_name = "thenewsapi"

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_THENEWSAPI_API_KEY') or os.getenv('PROVIDER_THENEWSAPI_KEY')
        if not self.api_key:
            logger.error("TheNewsAPI key not found in environment")
            raise ValueError("TheNewsAPI key not configured")
        self.base_url = "https://api.thenewsapi.com/v1/news"
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
        logger.debug(f"TheNewsAPI requests today: {self.requests_today}")

    # -- parameters -----------------------------------------------------------

    def _build_params(self, query: str, limit: int, *, language, locale, domains, exclude_domains,
                      sort_by, source_ids, exclude_source_ids, categories, exclude_categories,
                      search_fields) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "api_token": self.api_key,
            "search": query,
            "language": language,
            "limit": limit,
        }
        if locale:
            params["locale"] = locale
        if domains:
            params["domains"] = ",".join(domains)
        if exclude_domains:
            params["exclude_domains"] = ",".join(exclude_domains)
        params["sort"] = sort_by or "published_at"
        if source_ids:
            params["source_ids"] = ",".join(source_ids)
        if exclude_source_ids:
            params["exclude_source_ids"] = ",".join(exclude_source_ids)
        if categories:
            params["categories"] = ",".join(categories)
        if exclude_categories:
            params["exclude_categories"] = ",".join(exclude_categories)
        if search_fields:
            # Callers (keyword_monitor) may pass a comma-separated string
            # instead of a list; ",".join() on a string iterates characters
            # and malforms the param. Normalise to a list first.
            if isinstance(search_fields, str):
                search_fields = [f.strip() for f in search_fields.split(",") if f.strip()]
            # The tenant setting uses NewsAPI's vocabulary (title, description,
            # content). TheNewsAPI knows title, description, keywords, main_text;
            # an unknown name is silently dropped and the article body is never
            # searched, which cut Japanese/German/French results 5-14x
            # (2026-08-31: 歯周病 8 vs 114, Parodontitis 4 vs 23).
            mapped = []
            for f in search_fields:
                m = _FIELD_MAP.get(str(f).lower())
                if m and m not in mapped:
                    mapped.append(m)
            if "main_text" in mapped and "keywords" not in mapped:
                mapped.append("keywords")
            if mapped:
                params["search_fields"] = ",".join(mapped)
        return params

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
        locale: Optional[str] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        exclude_source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        if not (query or "").strip():
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        limit = max(1, min(int(max_results or 10), 100))
        page = max(1, int((continuation or {}).get("page") or 1))
        params = self._build_params(query, limit, language=language, locale=locale, domains=domains,
                                    exclude_domains=exclude_domains, sort_by=sort_by,
                                    source_ids=source_ids, exclude_source_ids=exclude_source_ids,
                                    categories=categories, exclude_categories=exclude_categories,
                                    search_fields=search_fields)
        if res.interval_start:
            params["published_after"] = _iso_param(res.interval_start)
        if res.interval_end:
            params["published_before"] = _iso_param(res.interval_end)
        res.diagnostics.update({"limit": limit, "first_page": page, "sort": params["sort"]})
        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("THENEWSAPI_MAX_PAGES", pages), seconds)
        guard = QuotaGuard(self.provider_name, self.api_key, scope=query)
        seen = set()
        host = "api.thenewsapi.com"

        def _carry(out: CollectionResult, cont: Optional[Dict[str, Any]]) -> CollectionResult:
            out.items, out.counts, out.started_at = res.items, res.counts, res.started_at
            out.continuation = cont
            out.diagnostics.update(res.diagnostics)
            return self.finish(out, query, interval_start, interval_end)

        try:
            async with _session() as session:
                while True:
                    blocked = guard.check()
                    if blocked is not None:
                        return _carry(blocked, {"page": page})
                    params["page"] = page
                    self._increment_request_count()
                    status, data, headers = await get_json(session, f"{self.base_url}/all", params=params)
                    clock.tick()
                    body = data if isinstance(data, dict) else {}
                    message = provider_message(data, f"HTTP {status}")

                    if status == 200 and isinstance(data, dict):
                        guard.ok()
                        articles = body.get("data") or []
                        meta = body.get("meta") or {}
                        res.counts.received += len(articles)
                        for article in articles:
                            url = (article.get("url") or "").strip()
                            if not url or not article.get("title"):
                                res.counts.invalid += 1
                                continue
                            if url in seen:
                                res.counts.duplicate += 1
                                continue
                            seen.add(url)
                            res.items.append(self._format_article(article, topic))
                        found = int(meta.get("found") or 0)
                        served_limit = int(meta.get("limit") or limit)
                        res.diagnostics["total_results"] = found
                        if len(articles) < served_limit or page * served_limit >= found:
                            return self.finish(res)
                        page += 1
                        if clock.exhausted:
                            out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
                                                           continuation={"page": page})
                            return _carry(out, {"page": page})
                        continue

                    if looks_exhausted(status, data):
                        until = guard.exhausted(retry_after=headers.get("Retry-After"), detail=message)
                        out = guard.result_for_exhaustion(until, f"thenewsapi: {message}")
                        return _carry(out, {"page": page})

                    guard.error(message)
                    logger.error(f"TheNewsAPI HTTP {status}: {message} (query='{query}')")
                    exc = ProviderHTTPError(status, message, url=f"{self.base_url}/all")
                    out = CollectionResult.from_exception(exc, host=host)
                    return _carry(out, {"page": page})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"TheNewsAPI request failed: {type(exc).__name__}: {exc} (query='{query}')")
            guard.error(f"{type(exc).__name__}: {exc}")
            out = CollectionResult.from_exception(exc, host=host)
            return _carry(out, {"page": page})

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
        """One page of ``/all``, as a list. Failures log and return []."""
        result = await self.collect(
            query, topic, interval_start=start_date, interval_end=end_date, max_results=max_results,
            continuation={"page": page} if page and page > 1 else None, language=language, locale=locale,
            domains=domains, exclude_domains=exclude_domains, sort_by=sort_by, source_ids=source_ids,
            exclude_source_ids=exclude_source_ids, categories=categories,
            exclude_categories=exclude_categories, search_fields=search_fields, max_pages=1)
        if result.failed:
            logger.error(f"TheNewsAPI search failed: {result.error_message}")
        return result.items[:max_results]

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch article metadata from TheNewsAPI by URL (the body is not served)."""
        guard = QuotaGuard(self.provider_name, self.api_key, scope=url)
        try:
            if guard.check() is not None:
                return None
            self._increment_request_count()
            async with _session() as session:
                status, data, headers = await get_json(
                    session, f"{self.base_url}/all", params={'api_token': self.api_key, 'url': url})
            if status != 200 or not isinstance(data, dict):
                if looks_exhausted(status, data):
                    guard.exhausted(retry_after=headers.get("Retry-After"), detail=provider_message(data))
                else:
                    guard.error(provider_message(data, f"HTTP {status}"))
                logger.error(f"TheNewsAPI fetch_article_content HTTP {status} for {url}")
                return None
            guard.ok()
            articles = data.get("data") or []
            if not articles:
                logger.warning(f"TheNewsAPI returned no articles for URL: {url}")
                return None
            item = self._format_article(articles[0], None)
            item['content'] = item.get('content') or ''
            item['raw_data']['categories'] = articles[0].get('categories', [])
            item['raw_data']['locale'] = articles[0].get('locale')
            return item
        except Exception as e:
            logger.error(f"TheNewsAPI fetch_article_content failed: {type(e).__name__}: {e} ({url})")
            return None

    def _format_article(self, article: Dict, topic: Optional[str]) -> Dict:
        """Format TheNewsAPI article data to standard format."""
        source = article.get('source', {})
        # The URL's host first: the API's source name often lacks a TLD.
        source_name = ''
        if article.get('url'):
            parsed_url = urlparse(article['url'])
            source_name = parsed_url.netloc.replace('www.', '')
        if not source_name:
            if isinstance(source, dict):
                source_name = source.get('name', '').strip()
            elif isinstance(source, str):
                source_name = source.strip()

        keywords = article.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',') if k.strip()]
        elif not isinstance(keywords, list):
            keywords = []

        parsed = parse_date(article.get('published_at'))
        snippet = article.get('snippet', '') or ''
        return {
            'title': article['title'],
            'summary': article.get('description', '') or snippet,
            'content': snippet,
            'content_kind': CONTENT_EXCERPT,
            'content_truncated': bool(snippet),
            'authors': [],  # TheNewsAPI doesn't provide author info
            'published_date': parsed.iso(),
            'published_at_raw': parsed.raw,
            'date_provenance': parsed.provenance if parsed.known else None,
            'url': article['url'],
            'source': source_name,
            'topic': topic,
            'raw_data': {
                'source': source,
                'image_url': article.get('image_url'),
                'keywords': keywords,
            }
        }
