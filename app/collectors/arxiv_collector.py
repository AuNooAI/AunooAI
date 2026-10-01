"""arXiv collector.

arXiv answers HTTP 406 in bursts to a query that returns 200 a minute later
(work package 24). Before this the collector raised on the first error and
the day window was lost until a later cycle happened to succeed. Now 406,
429, 503 and connection errors are transient: the call is retried with
exponential backoff inside a time budget, consecutive calls from this
process are spaced at least three seconds apart (arXiv's documented
request interval), and when the budget runs out the run fails with
``retryable`` true and a continuation for the same fixed window, so the next
cycle replays that window instead of a new one.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 3, 7 and 24.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import arxiv

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_ABSTRACT, coerce_datetime,
)
from app.collectors.contracts import (
    CollectionResult, ERR_CONNECTION, ERR_HTTP_4XX, ERR_HTTP_5XX, TRUNC_PROVIDER_LIMIT,
    TRANSIENT_HTTP_STATUSES, describe_exception,
)
from app.collectors.dates import parse_date
from app.models.topic import Topic

logger = logging.getLogger(__name__)

#: arXiv asks for one request every three seconds.
MIN_SPACING_SECONDS = 3.0
#: Backoff before each retry, with up to half a second of jitter.
RETRY_DELAYS = (1.0, 3.0, 9.0)

_spacing_lock: Optional[asyncio.Lock] = None
_last_call_at: float = 0.0


def _lock() -> asyncio.Lock:
    global _spacing_lock
    if _spacing_lock is None:
        _spacing_lock = asyncio.Lock()
    return _spacing_lock


def retry_budget_seconds() -> float:
    try:
        return max(1.0, float(os.getenv("ARXIV_RETRY_BUDGET_SECONDS", "60")))
    except ValueError:
        return 60.0


async def _wait_turn() -> None:
    """Space consecutive arXiv calls from this process by at least
    ``MIN_SPACING_SECONDS``. Held under a lock so two concurrent keyword
    searches do not both decide it is their turn."""
    global _last_call_at
    async with _lock():
        now = time.monotonic()
        wait = MIN_SPACING_SECONDS - (now - _last_call_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = time.monotonic()


def _status_of(exc: BaseException) -> Optional[int]:
    status = getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def is_transient(exc: BaseException) -> bool:
    """A provider or network hiccup, not a bad query."""
    if isinstance(exc, arxiv.HTTPError):
        return _status_of(exc) in TRANSIENT_HTTP_STATUSES
    if isinstance(exc, arxiv.UnexpectedEmptyPageError):
        return True
    name = type(exc).__name__.lower()
    if "connection" in name or "timeout" in name:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError)) and not isinstance(exc, FileNotFoundError)


class ArxivCollector(ArticleCollector):
    """ArXiv article collector implementation."""

    provider_name = "arxiv"

    def __init__(self):
        # The library's own retry loop is switched off; this collector
        # decides when and how often to retry.
        self.client = arxiv.Client(page_size=100, delay_seconds=MIN_SPACING_SECONDS, num_retries=0)
        # Mapping of our topics to arXiv categories
        self.topic_category_mapping = {
            "AI and Machine Learning": [
                "cs.AI",  # Artificial Intelligence
                "cs.LG",  # Machine Learning
                "cs.CL",  # Computation and Language
                "cs.CV",  # Computer Vision
                "cs.NE",  # Neural and Evolutionary Computing
                "cs.RO",  # Robotics
            ],
            "Cloud Computing": [
                "cs.DC",  # Distributed Computing
                "cs.NI",  # Networking and Internet Architecture
                "cs.OS",  # Operating Systems
                "cs.PF",  # Performance
            ]
        }

    # -- query ------------------------------------------------------------------

    def _build_query(self, query: str, topic: Optional[str], start_dt: datetime, end_dt: datetime,
                     search_fields: Optional[List[str]]) -> str:
        parts = [f"submittedDate:[{start_dt.strftime('%Y%m%d%H%M')} TO {end_dt.strftime('%Y%m%d%H%M')}]"]
        if search_fields:
            field_mapping = {'title': 'ti', 'abstract': 'abs', 'author': 'au',
                             'comments': 'co', 'journal_ref': 'jr'}
            field_queries = [f"{field_mapping[f]}:{query}" for f in search_fields if f in field_mapping]
            if field_queries:
                parts.append(f"({' OR '.join(field_queries)})")
            else:
                # search_fields can carry another collector's field names
                # (e.g. Semantic Scholar's ['Medicine', 'Biology']); none
                # map to arXiv prefixes, and dropping the keyword here is
                # what produced date-only full-catalog queries.
                logger.warning("arXiv: no usable search_fields in %r, falling back to all:%s",
                               search_fields, query)
                parts.append(f"all:{query}")
        else:
            parts.append(f"all:{query}")
        if topic and topic in self.topic_category_mapping:
            cats = " OR ".join(f"cat:{c}" for c in self.topic_category_mapping[topic])
            parts.append(f"({cats})")
        return " AND ".join(f"({p})" for p in parts if p)

    @staticmethod
    def _window(start_date, end_date) -> "tuple[datetime, datetime]":
        now = datetime.now(timezone.utc)
        start_dt = coerce_datetime(start_date) or (now - timedelta(days=7))
        if start_dt > now:
            start_dt = now - timedelta(days=7)
        end_dt = coerce_datetime(end_date) or now
        if end_dt > now:
            end_dt = now
        return start_dt, end_dt

    def _fetch_sync(self, search: "arxiv.Search", max_results: int) -> List[Any]:
        """The blocking library call. Tests replace this."""
        results = []
        for result in self.client.results(search):
            results.append(result)
            if len(results) >= max_results:
                break
        return results

    @staticmethod
    def _map(result, topic: Optional[str]) -> Dict[str, Any]:
        published = parse_date(getattr(result, "published", None))
        return {
            'title': result.title,
            'summary': result.summary,
            'content': result.summary,
            'content_kind': CONTENT_ABSTRACT,
            'authors': [author.name for author in result.authors],
            'published_date': published.iso(),
            'published_at_raw': published.raw,
            'date_provenance': published.provenance if published.known else None,
            'url': result.entry_id,
            'source': 'arXiv',
            'topic': topic,
            'raw_data': {
                'arxiv_id': result.entry_id,
                'primary_category': result.primary_category,
                'categories': result.categories,
                'updated': parse_date(getattr(result, "updated", None)).iso(),
                'links': {
                    'abstract': result.entry_id,
                    'pdf': result.pdf_url,
                },
                'source_name': 'arXiv'
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
        sort_by: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        # A blank keyword must never reach arXiv: with no term the query
        # degenerates to the date filter alone, which asks for the entire
        # catalog and pages through it 100 records at a time.
        if not query or not query.strip():
            logger.warning("Skipping arXiv search: empty query for topic %r", topic)
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        query = query.strip()
        cont = dict(continuation or {})
        start_dt, end_dt = self._window(cont.get("interval_start") or interval_start,
                                        cont.get("interval_end") or interval_end)
        final_query = self._build_query(query, topic, start_dt, end_dt, search_fields)
        sort_mapping = {
            'relevance': arxiv.SortCriterion.Relevance,
            'lastupdateddate': arxiv.SortCriterion.LastUpdatedDate,
            'submitteddate': arxiv.SortCriterion.SubmittedDate,
        }
        criterion = sort_mapping.get((sort_by or 'submittedDate').lower(), arxiv.SortCriterion.SubmittedDate)
        search = arxiv.Search(query=final_query, max_results=max_results, sort_by=criterion)
        res.diagnostics.update({"query": final_query, "sort": criterion.value})
        window_cont = {"interval_start": start_dt.isoformat(), "interval_end": end_dt.isoformat()}

        deadline = time.monotonic() + retry_budget_seconds()
        attempt = 0
        while True:
            await _wait_turn()
            try:
                results = await asyncio.to_thread(self._fetch_sync, search, max_results)
                break
            except Exception as exc:  # noqa: BLE001
                if not is_transient(exc):
                    logger.error(f"arXiv query failed: {describe_exception(exc, host='export.arxiv.org')}")
                    out = CollectionResult.from_exception(exc, host="export.arxiv.org", continuation=window_cont)
                    out.started_at = res.started_at
                    out.diagnostics.update(res.diagnostics)
                    status = _status_of(exc)
                    if status:
                        out.diagnostics["status"] = status
                    return self.finish(out, query, interval_start, interval_end)
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)] + random.uniform(0, 0.5)
                attempt += 1
                if attempt > len(RETRY_DELAYS) or time.monotonic() + delay > deadline:
                    status = _status_of(exc)
                    code = ERR_HTTP_5XX if status and status >= 500 else ERR_HTTP_4XX if status else ERR_CONNECTION
                    msg = describe_exception(exc, host="export.arxiv.org")
                    logger.error(f"arXiv transient failure persisted after {attempt} attempts: {msg}")
                    out = CollectionResult.failure(code, msg, retryable=True, continuation=window_cont)
                    out.started_at = res.started_at
                    out.diagnostics.update(res.diagnostics)
                    out.diagnostics["attempts"] = attempt
                    if status:
                        out.diagnostics["status"] = status
                    return self.finish(out, query, interval_start, interval_end)
                logger.warning(f"arXiv transient error ({describe_exception(exc)}); retry {attempt} in {delay:.1f}s")
                await asyncio.sleep(delay)

        res.counts.received = len(results)
        res.items = [self._map(r, topic) for r in results]
        res.diagnostics["attempts"] = attempt + 1
        if len(results) >= max_results:
            # The library stops at max_results; nothing proves the window
            # ended. Sorted newest-first, the window can be narrowed to the
            # oldest submission seen so the next run collects the rest.
            res.status = "partial"
            res.coverage_complete = False
            res.retryable = True
            res.truncated_reason = TRUNC_PROVIDER_LIMIT
            oldest = None
            for item in res.items:
                when = coerce_datetime(item['published_date'])
                if when and (oldest is None or when < oldest):
                    oldest = when
            if criterion == arxiv.SortCriterion.SubmittedDate and oldest and oldest < end_dt:
                res.continuation = {"interval_start": start_dt.isoformat(), "interval_end": oldest.isoformat()}
        logger.info(f"Found {len(results)} arXiv articles matching criteria")
        return self.finish(res)

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
        """Search ArXiv articles. Raises ``ValueError`` when the run failed,
        as it always did; use ``collect`` to see the classified outcome."""
        result = await self.collect(query, topic, interval_start=start_date, interval_end=end_date,
                                    max_results=max_results, sort_by=sort_by or 'relevance',
                                    search_fields=search_fields)
        if result.failed:
            raise ValueError(f"ArXiv search failed: {result.error_message}")
        return result.items

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch article content from ArXiv."""
        try:
            arxiv_id = url.split('/')[-1]
            search = arxiv.Search(id_list=[arxiv_id])
            await _wait_turn()
            results = await asyncio.to_thread(self._fetch_sync, search, 1)
            if results:
                result = results[0]
                item = self._map(result, None)
                item['url'] = result.pdf_url
                item['source'] = 'arxiv'
                return item
            return None

        except Exception as e:
            logger.error(f"Error fetching ArXiv article: {str(e)}")
            return None

    def get_latest_papers(self, topic: Topic, count: int = 5) -> List[Dict]:
        if not hasattr(topic, 'arxiv_categories') or not topic.arxiv_categories:
            # Use default categories if none are specified
            categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.RO"]
        else:
            categories = topic.arxiv_categories

        category_filter = " OR ".join(f"cat:{cat}" for cat in categories)
        query = f"{topic.paper_query} AND ({category_filter})"
