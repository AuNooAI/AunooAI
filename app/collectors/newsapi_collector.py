"""NewsAPI collector.

``collect`` pages through ``/v2/everything`` behind one ``CollectionResult``
(work package 3): the interval end is frozen, results are sorted by
``publishedAt``, pages are deduplicated by URL, and a run that hits the page
or time budget hands back a continuation instead of pretending it finished.
Every request goes through the host-wide quota guard (work package 20), so
two sites on one key stop together when the provider says the key is spent.

NewsAPI facts this file relies on (developer documentation, checked
2026-10-01): ``pageSize`` is at most 100; ``page`` is 1-based; ``from`` and
``to`` take ISO 8601; ``sortBy`` is ``relevancy``, ``popularity`` or
``publishedAt``; the developer plan serves at most 100 results per query and
answers HTTP 426 ``maximumResultsReached`` beyond that; ``content`` is cut at
200 characters and ends with ``[+N chars]``.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 3, 8 and 20.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_EXCERPT, PageClock, ProviderHTTPError, coerce_datetime,
    get_json, page_budget, provider_max_pages, provider_message,
)
from app.collectors.contracts import (
    CollectionResult, TRUNC_PROVIDER_LIMIT, TRUNC_RETENTION,
)
from app.collectors.dates import parse_date
from app.database import Database
from app.services.provider_quota import QuotaGuard, looks_exhausted

logger = logging.getLogger(__name__)

#: The developer plan's hard cap on results per query.
_DEVELOPER_RESULT_CAP = 100
_TRUNCATION_MARKER = re.compile(r"\s*\[\+\d+\s+chars\]\s*$")
_VALID_CATEGORIES = ('business', 'entertainment', 'general', 'health',
                     'science', 'sports', 'technology')


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


def _iso_param(value: Optional[datetime]) -> Optional[str]:
    dt = coerce_datetime(value)
    return dt.strftime('%Y-%m-%dT%H:%M:%S') if dt else None


class NewsAPICollector(ArticleCollector):
    """NewsAPI article collector implementation."""

    provider_name = "newsapi"

    def __init__(self, db: Database):
        self.api_key = os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY')
        if not self.api_key:
            logger.error("NewsAPI key not found in environment")
            raise ValueError("NewsAPI key not configured")

        self.db = db
        self.base_url = "https://newsapi.org/v2"
        self._init_request_counter()
        self.last_request_time = None

    def _init_request_counter(self):
        """Initialize request counter from database"""
        try:
            logger.debug("Initializing request counter")

            row = self.db.facade.get_request_count_for_today()
            today = datetime.now().date().isoformat()

            logger.debug(f"Current status row: {row}, today: {today}")

            if row:
                requests_today, last_reset = row

                if not last_reset or last_reset < today:
                    # Reset counter for new day
                    self.requests_today = 0
                    self.db.facade.reset_keyword_monitoring_counter((today,))
                    logger.debug("Reset counter for new day")
                else:
                    self.requests_today = requests_today
                    logger.debug(f"Using existing count: {requests_today}")
            else:
                self.requests_today = 0
                logger.debug("No existing count found, starting at 0")

        except Exception as e:
            logger.error(f"Error initializing request counter: {str(e)}")
            self.requests_today = 0

    def _update_request_counter(self):
        """Keep the tenant's own request count for the UI. It no longer
        decides whether a request is sent: that is the shared ledger's job
        (work package 20), because this counter only ever saw one site."""
        try:
            self.requests_today += 1
            today = datetime.now().date().isoformat()
            self.db.facade.stamp_keyword_monitor_status_table_with_todays_date((self.requests_today, today))
            logger.debug(f"Updated NewsAPI request count to {self.requests_today}")
        except Exception as e:
            logger.error(f"Error updating request counter: {str(e)}")

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Implement abstract method from ArticleCollector"""
        try:
            article = await self.get_article(url)
            if article:
                return {
                    'content': article.get('content') or article['raw_data'].get('content', ''),
                    'title': article['title'],
                    'source': article['source'],
                    'publication_date': article['published_date']
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching article content: {str(e)}")
            return None

    # -- parameters -----------------------------------------------------------

    def _build_params(self, query: str, topic: Optional[str], page_size: int, *,
                      language: Optional[str], domains, exclude_domains, sort_by,
                      search_fields) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            'apiKey': self.api_key,
            'q': query,
            'pageSize': page_size,
        }
        if language:
            params['language'] = language
        params['sortBy'] = sort_by or 'publishedAt'
        if search_fields:
            if isinstance(search_fields, str):
                search_fields = search_fields.split(',')
            mapping = {'title': 'title', 'desc': 'description',
                       'description': 'description', 'content': 'content'}
            valid = []
            for field in search_fields:
                name = mapping.get(str(field).lower().strip(), str(field).strip())
                if name in ('title', 'description', 'content') and name not in valid:
                    valid.append(name)
            if valid:
                params['searchIn'] = ','.join(valid)
        if domains:
            params['domains'] = ','.join(domains)
        if exclude_domains:
            params['excludeDomains'] = ','.join(exclude_domains)
        if topic and topic.lower() in _VALID_CATEGORIES:
            params['category'] = topic.lower()
        return params

    @staticmethod
    def _map(article: Dict[str, Any], topic: Optional[str]) -> Dict[str, Any]:
        raw_content = article.get('content') or ''
        truncated = bool(_TRUNCATION_MARKER.search(raw_content))
        content = _TRUNCATION_MARKER.sub('', raw_content).strip()
        parsed = parse_date(article.get('publishedAt'))
        return {
            'title': article.get('title', '') or '',
            'summary': article.get('description', '') or '',
            # Work package 8: the body lives at the top level, where ingest
            # reads it, and is labelled for what it is: a cut excerpt.
            'content': content,
            'content_kind': CONTENT_EXCERPT,
            'content_truncated': True if (truncated or content) else False,
            'url': article.get('url', ''),
            'source': (article.get('source') or {}).get('name') or 'NewsAPI',
            'authors': [article.get('author')] if article.get('author') else [],
            'published_date': parsed.iso(),
            'published_at_raw': parsed.raw,
            'date_provenance': parsed.provenance if parsed.known else None,
            'topic': topic,
            'raw_data': {
                'url_to_image': article.get('urlToImage'),
                'content': article.get('content'),
                'content_truncated': truncated,
            }
        }

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
        language: Optional[str] = "en",
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        max_pages: Optional[int] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        if not (query or "").strip():
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        page_size = max(1, min(int(max_results or 10), 100))
        cont = dict(continuation or {})
        page = max(1, int(cont.get("page") or 1))
        # A previous run that hit the plan cap narrowed the window: resume
        # from the oldest timestamp it saw instead of the interval end.
        to_bound = coerce_datetime(cont.get("to")) or res.interval_end
        from_bound = res.interval_start
        params = self._build_params(query, topic, page_size, language=language, domains=domains,
                                    exclude_domains=exclude_domains, sort_by=sort_by,
                                    search_fields=search_fields)
        if from_bound:
            params['from'] = _iso_param(from_bound)
        if to_bound:
            params['to'] = _iso_param(to_bound)
        res.diagnostics.update({"page_size": page_size, "first_page": page,
                                "sort": params['sortBy'], "to": params.get('to')})

        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("NEWSAPI_MAX_PAGES", pages), seconds)
        guard = QuotaGuard(self.provider_name, self.api_key, scope=query)
        seen = set()
        oldest: Optional[datetime] = None
        total_results: Optional[int] = None
        host = "newsapi.org"

        def _resume(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            out = {"page": page}
            if cont.get("to"):
                out["to"] = cont["to"]
            if extra:
                out.update(extra)
            return out

        try:
            async with _session() as session:
                while True:
                    blocked = guard.check()
                    if blocked is not None:
                        blocked.items = res.items
                        blocked.counts.add(received=res.counts.received, duplicate=res.counts.duplicate)
                        blocked.continuation = _resume()
                        blocked.started_at = res.started_at
                        return self.finish(blocked, query, interval_start, interval_end)
                    params['page'] = page
                    logger.info(f"NewsAPI request: query='{query}', page={page}, requests_today={self.requests_today}")
                    self._update_request_counter()
                    status, data, headers = await get_json(session, f"{self.base_url}/everything", params=params)
                    clock.tick()
                    body = data if isinstance(data, dict) else {}
                    code = body.get('code')
                    message = provider_message(data, f"HTTP {status}")

                    if status == 200 and body.get('status') == 'ok':
                        guard.ok()
                        articles = body.get('articles') or []
                        total_results = int(body.get('totalResults') or 0)
                        res.counts.received += len(articles)
                        for article in articles:
                            url = (article.get('url') or '').strip()
                            if not url:
                                res.counts.invalid += 1
                                continue
                            if url in seen:
                                res.counts.duplicate += 1
                                continue
                            seen.add(url)
                            item = self._map(article, topic)
                            res.items.append(item)
                            when = coerce_datetime(item['published_date'])
                            if when and (oldest is None or when < oldest):
                                oldest = when
                        if len(articles) < page_size or page * page_size >= total_results:
                            res.diagnostics["total_results"] = total_results
                            return self.finish(res)
                        if page * page_size >= _DEVELOPER_RESULT_CAP:
                            return self._plan_capped(res, query, interval_start, interval_end,
                                                     oldest, to_bound, total_results)
                        page += 1
                        if clock.exhausted:
                            out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
                                                           continuation=_resume())
                            out.counts, out.diagnostics, out.started_at = res.counts, res.diagnostics, res.started_at
                            out.diagnostics["total_results"] = total_results
                            return self.finish(out, query, interval_start, interval_end)
                        continue

                    if looks_exhausted(status, data, code):
                        until = guard.exhausted(retry_after=headers.get("Retry-After"), detail=message)
                        out = guard.result_for_exhaustion(until, f"newsapi: {message}")
                        out.items, out.counts, out.started_at = res.items, res.counts, res.started_at
                        out.continuation = _resume()
                        out.diagnostics.update(res.diagnostics)
                        return self.finish(out, query, interval_start, interval_end)

                    guard.error(message)
                    if status == 426 or code in ('maximumResultsReached',):
                        # Beyond what the plan serves. ``from`` too far back is
                        # a retention limit; everything else is the result cap.
                        reason = TRUNC_RETENTION if 'far in the past' in message.lower() or 'too far' in message.lower() \
                            else TRUNC_PROVIDER_LIMIT
                        if reason == TRUNC_PROVIDER_LIMIT and res.items:
                            return self._plan_capped(res, query, interval_start, interval_end,
                                                     oldest, to_bound, total_results, message)
                        out = CollectionResult.partial(res.items, truncated_reason=reason, continuation=None)
                        out.counts, out.started_at = res.counts, res.started_at
                        out.diagnostics.update(res.diagnostics)
                        out.diagnostics["provider_message"] = message
                        return self.finish(out, query, interval_start, interval_end)
                    exc = ProviderHTTPError(status, f"{code or 'error'}: {message}", url=f"{self.base_url}/everything")
                    out = CollectionResult.from_exception(exc, host=host, items=res.items, continuation=_resume())
                    out.counts, out.started_at = res.counts, res.started_at
                    out.diagnostics.update(res.diagnostics)
                    return self.finish(out, query, interval_start, interval_end)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"NewsAPI request failed: {type(exc).__name__}: {exc}")
            guard.error(f"{type(exc).__name__}: {exc}")
            out = CollectionResult.from_exception(exc, host=host, items=res.items, continuation=_resume())
            out.counts, out.started_at = res.counts, res.started_at
            out.diagnostics.update(res.diagnostics)
            return self.finish(out, query, interval_start, interval_end)

    def _plan_capped(self, res: CollectionResult, query, interval_start, interval_end,
                     oldest: Optional[datetime], to_bound: Optional[datetime],
                     total_results: Optional[int], message: str = "") -> CollectionResult:
        """The plan cannot page further. Sorted newest-first, everything
        newer than the oldest article seen is covered, so the continuation
        narrows ``to`` to that instant and the next run collects the rest.
        If the page shares one timestamp the window cannot shrink and the
        limitation is reported without a continuation."""
        cont = None
        if oldest is not None and (to_bound is None or oldest < to_bound):
            cont = {"page": 1, "to": oldest.isoformat()}
        out = CollectionResult.partial(res.items, truncated_reason=TRUNC_PROVIDER_LIMIT, continuation=cont)
        out.counts, out.started_at = res.counts, res.started_at
        out.diagnostics.update(res.diagnostics)
        out.diagnostics["plan_result_cap"] = _DEVELOPER_RESULT_CAP
        if total_results is not None:
            out.diagnostics["total_results"] = total_results
        if message:
            out.diagnostics["provider_message"] = message
        return self.finish(out, query, interval_start, interval_end)

    # -- compatibility list API --------------------------------------------

    async def search_articles(
        self,
        query: str,
        topic: Optional[str] = None,
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
        page: int = 1
    ) -> List[Dict]:
        """One page, as a list. Failures log and return an empty list; use
        ``collect`` to see why."""
        result = await self.collect(
            query, topic, interval_start=start_date, interval_end=end_date,
            max_results=max_results, continuation={"page": page} if page and page > 1 else None,
            language=language, domains=domains, exclude_domains=exclude_domains,
            sort_by=sort_by, search_fields=search_fields, max_pages=1,
        )
        if result.failed:
            logger.error(f"NewsAPI search failed: {result.error_message}")
        return result.items[:max_results]

    async def get_article(self, url: str) -> Optional[Dict]:
        """Get a specific article by URL"""
        try:
            articles = await self.search_articles(
                query=f"url:{url}",
                max_results=1
            )
            return articles[0] if articles else None

        except Exception as e:
            logger.error(f"Error fetching article from NewsAPI: {str(e)}")
            return None
