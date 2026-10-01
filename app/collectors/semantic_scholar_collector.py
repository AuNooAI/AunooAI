"""Semantic Scholar collector.

``collect`` pages ``/graph/v1/paper/search`` with ``offset`` and ``limit``
behind one ``CollectionResult`` (work package 3) and runs every request
through the host-wide quota guard (work package 20). The first 429 ends the
run: the key is paused for every site and the interval keeps its offset as a
continuation.

API facts this file relies on (Semantic Scholar Academic Graph API
documentation, checked 2026-10-01): ``limit`` is at most 100 per request;
``offset`` is 0-based and ``offset + limit`` may not exceed 1000; the
response carries ``total``, ``offset``, ``data`` and, when more results
remain, ``next`` (the next offset); ``publicationDateOrYear`` takes
``YYYY-MM-DD:YYYY-MM-DD``; the API key goes in ``x-api-key``.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 3, 8 and 20.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_ABSTRACT, PageClock, ProviderHTTPError, coerce_datetime,
    get_json, page_budget, provider_max_pages, provider_message,
)
from app.collectors.contracts import CollectionResult, TRUNC_PROVIDER_LIMIT
from app.collectors.dates import parse_date
from app.services.provider_quota import QuotaGuard, looks_exhausted

logger = logging.getLogger(__name__)

#: The relevance search endpoint refuses offsets past this.
_OFFSET_CAP = 1000


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


class SemanticScholarCollector(ArticleCollector):
    """Semantic Scholar article collector implementation."""

    provider_name = "semantic_scholar"

    def __init__(self):
        self.api_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY')  # Optional
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.requests_today = 0  # Track API requests for compatibility with keyword monitor

        # Mapping of our topics to Semantic Scholar fieldsOfStudy
        self.topic_field_mapping = {
            "magic and occultism": ["Psychology", "Sociology", "History", "Philosophy"],
            "AI and Machine Learning": ["Computer Science"],
            "Cloud Computing": ["Computer Science"],
            "Blockchain": ["Computer Science", "Economics"],
            "Quantum Computing": ["Computer Science", "Physics"],
            "Cybersecurity": ["Computer Science"],
            "Biotechnology": ["Biology", "Medicine"],
            "Climate Change": ["Environmental Science", "Geography"],
            "Neuroscience": ["Medicine", "Psychology", "Biology"],
            # Oral-systemic health (Sunstar, 2026-08-31): dental and medical literature.
            "Oral-Systemic Health Research": ["Medicine", "Biology"],
            "Regenerative Dentistry": ["Medicine", "Biology", "Materials Science"],
        }

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _window(start_date, end_date) -> "tuple[datetime, datetime]":
        now = datetime.now(timezone.utc)
        start_dt = coerce_datetime(start_date) or (now - timedelta(days=30))
        if start_dt > now:
            start_dt = now - timedelta(days=30)
        end_dt = coerce_datetime(end_date) or now
        if end_dt > now:
            end_dt = now
        return start_dt, end_dt

    def _headers(self) -> Dict[str, str]:
        return {'x-api-key': self.api_key} if self.api_key else {}

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
        if not (query or "").strip():
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        start_dt, end_dt = self._window(interval_start, interval_end)
        limit = max(1, min(int(max_results or 10), 100))
        offset = max(0, int((continuation or {}).get("offset") or 0))
        params: Dict[str, Any] = {
            'query': query,
            'fields': 'title,abstract,authors,year,venue,url,paperId,publicationDate,citationCount,fieldsOfStudy,externalIds',
            'limit': limit,
            'offset': offset,
            'publicationDateOrYear': f"{start_dt.strftime('%Y-%m-%d')}:{end_dt.strftime('%Y-%m-%d')}",
        }
        if topic and topic in self.topic_field_mapping:
            params['fieldsOfStudy'] = ','.join(self.topic_field_mapping[topic])
        res.diagnostics.update({"limit": limit, "first_offset": offset,
                                "date_range": params['publicationDateOrYear'],
                                "authenticated": bool(self.api_key)})
        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("SEMANTIC_SCHOLAR_MAX_PAGES", pages), seconds)
        guard = QuotaGuard(self.provider_name, self.api_key, scope=query)
        seen = set()
        host = "api.semanticscholar.org"

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
                        return _carry(blocked, {"offset": offset})
                    params['offset'] = offset
                    self.requests_today += 1
                    status, data, headers = await get_json(
                        session, f"{self.base_url}/paper/search", params=params,
                        headers=self._headers(), timeout=30)
                    clock.tick()
                    body = data if isinstance(data, dict) else {}
                    message = provider_message(data, f"HTTP {status}")

                    if status == 200:
                        guard.ok()
                        papers = body.get('data') or []
                        total = int(body.get('total') or 0)
                        res.counts.received += len(papers)
                        for paper in papers:
                            item = self._format_article(paper, topic)
                            if not item:
                                res.counts.invalid += 1
                                continue
                            key = item['raw_data'].get('paper_id') or item.get('url')
                            if key in seen:
                                res.counts.duplicate += 1
                                continue
                            seen.add(key)
                            res.items.append(item)
                        res.diagnostics["total_results"] = total
                        next_offset = body.get('next')
                        if next_offset is None or len(papers) < limit:
                            return self.finish(res)
                        offset = int(next_offset)
                        if offset >= _OFFSET_CAP:
                            out = CollectionResult.partial(res.items, truncated_reason=TRUNC_PROVIDER_LIMIT,
                                                           continuation=None)
                            out.diagnostics["offset_cap"] = _OFFSET_CAP
                            return _carry(out, None)
                        if clock.exhausted:
                            out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
                                                           continuation={"offset": offset})
                            return _carry(out, {"offset": offset})
                        continue

                    if looks_exhausted(status, data):
                        until = guard.exhausted(retry_after=headers.get("Retry-After"), detail=message)
                        out = guard.result_for_exhaustion(until, f"semantic_scholar: {message}")
                        return _carry(out, {"offset": offset})

                    guard.error(message)
                    if status == 404:
                        # The relevance endpoint answers 404 for "no match".
                        res.diagnostics["provider_message"] = message
                        return self.finish(res)
                    exc = ProviderHTTPError(status, message, url=f"{self.base_url}/paper/search")
                    out = CollectionResult.from_exception(exc, host=host)
                    return _carry(out, {"offset": offset})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Semantic Scholar request failed: {type(exc).__name__}: {exc}")
            guard.error(f"{type(exc).__name__}: {exc}")
            out = CollectionResult.from_exception(exc, host=host)
            return _carry(out, {"offset": offset})

    # -- compatibility list API --------------------------------------------

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: Optional[str] = None,
        sort_by: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        page: Optional[int] = None,
        **kwargs
    ) -> List[Dict]:
        """One page, as a list. Failures log and return an empty list."""
        cont = None
        if page and int(page) > 1:
            cont = {"offset": (int(page) - 1) * max(1, min(int(max_results or 10), 100))}
        result = await self.collect(query, topic, interval_start=start_date, interval_end=end_date,
                                    max_results=max_results, continuation=cont, max_pages=1)
        if result.failed:
            logger.error(f"Semantic Scholar search failed: {result.error_message}")
        return result.items[:max_results]

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch article metadata from Semantic Scholar.
        Note: Semantic Scholar does not provide full-text content.
        """
        try:
            paper_id = None
            if 'semanticscholar.org/paper/' in url:
                paper_id = url.split('/paper/')[-1].split('?')[0]
            else:
                return None

            guard = QuotaGuard(self.provider_name, self.api_key, scope=url)
            if guard.check() is not None:
                return None
            self.requests_today += 1
            async with _session() as session:
                status, paper, headers = await get_json(
                    session, f"{self.base_url}/paper/{paper_id}",
                    params={'fields': 'title,abstract,authors,year,venue,url,publicationDate,citationCount'},
                    headers=self._headers(), timeout=30)
            if status != 200 or not isinstance(paper, dict):
                if looks_exhausted(status, paper):
                    guard.exhausted(retry_after=headers.get("Retry-After"), detail=provider_message(paper))
                else:
                    guard.error(provider_message(paper, f"HTTP {status}"))
                logger.error(f"Error fetching Semantic Scholar paper {paper_id}: {status}")
                return None
            guard.ok()
            authors = [a.get('name', '') for a in (paper.get('authors') or [])]
            parsed = parse_date(paper.get('publicationDate') or paper.get('year'))
            return {
                'title': paper.get('title', ''),
                'content': paper.get('abstract', '') or '',
                'content_kind': CONTENT_ABSTRACT,
                'authors': authors,
                'published_date': parsed.iso(),
                'url': paper.get('url', url),
                'source': 'semantic_scholar',
                'raw_data': {
                    'paper_id': paper.get('paperId', ''),
                    'citation_count': paper.get('citationCount', 0),
                    'venue': paper.get('venue', ''),
                    'year': paper.get('year', '')
                }
            }

        except Exception as e:
            logger.error(f"Error fetching Semantic Scholar article: {str(e)}")
            return None

    def _format_article(self, article: Dict, topic: str) -> Optional[Dict]:
        """Format Semantic Scholar response to standard project format."""
        try:
            if not article.get('title'):
                return None
            authors = [a.get('name', '') for a in (article.get('authors') or [])]
            url = article.get('url')
            if not url and article.get('paperId'):
                url = f"https://www.semanticscholar.org/paper/{article['paperId']}"
            # A day when the record has one; a year keeps year precision.
            # Nothing invents January the first.
            parsed = parse_date(article.get('publicationDate') or article.get('year'))
            external = article.get('externalIds') or {}
            abstract = article.get('abstract', '') or ''
            return {
                'title': article.get('title', ''),
                'summary': abstract,
                'content': abstract,
                'content_kind': CONTENT_ABSTRACT,
                'authors': authors,
                'published_date': parsed.iso(),
                'published_at_raw': parsed.raw,
                'publication_date_precision': parsed.precision,
                'date_provenance': parsed.provenance if parsed.known else None,
                'url': url,
                'source': 'semantic_scholar',
                'topic': topic,
                'raw_data': {
                    'paper_id': article.get('paperId', ''),
                    'doi': external.get('DOI') if isinstance(external, dict) else None,
                    'citation_count': article.get('citationCount', 0),
                    'venue': article.get('venue', ''),
                    'year': article.get('year', ''),
                    'fields_of_study': article.get('fieldsOfStudy', []),
                    'source_name': 'Semantic Scholar'
                }
            }
        except Exception as e:
            logger.error(f"Error formatting Semantic Scholar article: {str(e)}")
            return None
