import asyncio
import hashlib
import json
import os
import re
import logging
import time
import aiohttp
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone


def _aware(value):
    """A timezone-aware datetime. A naive value is on the local clock (the
    convention of the callers that still pass one). Non-datetimes pass
    through unchanged."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.astimezone()
    return value


from .base_collector import (
    ArticleCollector,
    PageClock,
    ProviderHTTPError,
    coerce_datetime,
    get_json,
    in_interval,
    page_budget,
    provider_max_pages,
    provider_message,
)
from .contracts import CollectionResult, ERR_CONFIG, ERR_PARSE, host_of
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _session():
    """Session factory; tests replace it with a fake."""
    return aiohttp.ClientSession()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


#: The API takes whole dates only (a datetime is HTTP 422) and compares
#: ``published_at >= from_date`` and ``published_at <= to_date``, each date read
#: as midnight in the server's session time zone. So the request is widened to
#: whole UTC days with a day's slack on each side for that time zone, and the
#: collector filters rows to the exact interval itself. The slack costs no
#: pages at the old end (paging is newest first and stops once a page reaches
#: past the window start) and at most the rows newer than the interval end.
def _date_params(start: Optional[datetime], end: Optional[datetime]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    if start is not None:
        params["from_date"] = (start.astimezone(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    if end is not None:
        params["to_date"] = (end.astimezone(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    return params


def _query_fingerprint(chunks: List[str], params: Dict[str, Any]) -> str:
    """Identifies the chunk list and the sort/filter parameters a
    continuation was made for. A continuation for a different query must not
    be applied to this one: its chunk and page numbers mean something else."""
    basis = json.dumps({"chunks": chunks, "params": {k: params.get(k) for k in
                        ("sort_by", "page_size", "language", "sources", "categories")}},
                       sort_keys=True)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


class NewsFirehoseCollector(ArticleCollector):
    """Collector for the NewsFirehose API - unified news aggregation service."""

    # Map ISO 639-1 language codes to full names (NewsFirehose API quirk)
    LANGUAGE_MAP = {
        'en': 'english',
        'es': 'spanish',
        'fr': 'french',
        'de': 'german',
        'it': 'italian',
        'pt': 'portuguese',
        'nl': 'dutch',
        'ru': 'russian',
        'zh': 'chinese',
        'ja': 'japanese',
        'ko': 'korean',
        'ar': 'arabic',
        'hi': 'hindi',
        'tr': 'turkish',
        'pl': 'polish',
        'sv': 'swedish',
        'no': 'norwegian',
        'da': 'danish',
        'fi': 'finnish',
    }

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Normalize query for NewsFirehose /v1/search endpoint.

        The /v1/search endpoint uses PostgreSQL full-text search via plainto_tsquery
        or a custom parser. It supports:
        - Simple keywords: climate change
        - Single words with OR: AGI OR superintelligence
        - AND: military AND coup
        - Single quoted phrase: "artificial intelligence"

        It does NOT support:
        - Multiple quoted phrases with OR: "AI" OR "machine learning" (tsquery parse error)
        - Parenthetical grouping: (AGI | "frontier model") + (research)
        - Complex NewsAPI-style boolean syntax

        Strategy: extract all meaningful terms (quoted phrases become unquoted words),
        strip parentheses and special operators, join with OR for broad matching.
        Precision comes from the relevance scoring downstream, not the search query.

        One exception: a query that is nothing but a single quoted phrase is passed
        through with its quotes intact, because the endpoint supports that form and
        it is the only way to ask for adjacent words. Unquoted, `Atlantis Press`
        becomes an AND of two terms found anywhere in the document, which matched a
        Tomb Raider page containing the word "press"; quoted, it matches nothing,
        which is the honest answer. Callers wanting a phrase must quote it —
        multi-word keywords are still normalized as before, so nothing that relies
        on the broad behaviour changes.
        """
        if not query:
            return query

        # A lone quoted phrase is the one form worth preserving. Anything else —
        # several phrases, or a phrase mixed with operators — is what the endpoint
        # cannot parse, so it still gets flattened below.
        stripped = query.strip()
        if re.fullmatch(r'"[^"]+"', stripped):
            inner = stripped[1:-1].strip()
            # &, !, :, * are tsquery operators and break the parse even inside a
            # phrase, so a phrase containing them cannot be preserved.
            if inner and not re.search(r'[&!:*\\|+()]', inner):
                return f'"{inner}"'

        # Extract quoted phrases and convert to unquoted words
        # "artificial general intelligence" -> artificial general intelligence
        normalized = re.sub(r'"([^"]+)"', r'\1', query)

        # Strip parentheses
        normalized = normalized.replace('(', '').replace(')', '')

        # Normalize boolean operators to OR for broad matching
        # | -> OR, + -> OR (AND is too restrictive for firehose full-text search)
        normalized = re.sub(r'\s*\|\s*', ' OR ', normalized)
        normalized = re.sub(r'\s*\+\s*', ' OR ', normalized)

        # Convert lowercase boolean operators to uppercase
        normalized = re.sub(r'\b(and)\b', 'OR', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\b(or)\b', 'OR', normalized, flags=re.IGNORECASE)

        # Remove NOT terms entirely (they break tsquery and we filter downstream)
        normalized = re.sub(r'\bNOT\s+\S+', '', normalized, flags=re.IGNORECASE)

        # Drop characters that break PostgreSQL tsquery when they appear
        # literally in a term (e.g. "John Wiley & Sons", "Taylor & Francis").
        # &, !, :, * are tsquery operators; replace with a space so the term
        # degrades to plain words. (| and + were already converted to OR above.)
        normalized = re.sub(r'[&!:*\\]+', ' ', normalized)

        # Clean up multiple spaces and dangling ORs
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = re.sub(r'^OR\s+|\s+OR$', '', normalized)
        normalized = re.sub(r'\s+OR\s+OR\s+', ' OR ', normalized)

        if normalized != query:
            logger.debug(f"Normalized query: '{query}' -> '{normalized}'")

        return normalized

    @staticmethod
    def _split_query_terms(normalized_query: str, max_terms: int = 8) -> List[str]:
        """Split a normalized flat OR-chain into chunks of at most max_terms.

        The API rejects queries with more than 8 OR terms since the 2026-08
        remediation. A lone quoted phrase (no " OR ") passes through whole.
        """
        if not normalized_query or " OR " not in normalized_query:
            return [normalized_query]
        terms = [t.strip() for t in normalized_query.split(" OR ") if t.strip()]
        if len(terms) <= max_terms:
            return [normalized_query]
        return [
            " OR ".join(terms[i:i + max_terms])
            for i in range(0, len(terms), max_terms)
        ]

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_NEWSFIREHOSE_API_KEY') or os.getenv('NEWSFIREHOSE_API_KEY')
        if not self.api_key:
            logger.error("NewsFirehose API key not found in environment")
            raise ValueError("NewsFirehose API key not configured")

        # Base URL - configurable for different deployments
        self.base_url = os.getenv('NEWSFIREHOSE_BASE_URL', 'http://5.9.100.178:8000')
        self.requests_today = 0
        logger.info(f"NewsFirehoseCollector initialized with base URL: {self.base_url}")

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
        timeframe: Optional[int] = None,
    ) -> List[Dict]:
        """Search articles using NewsFirehose /v1/search endpoint.

        Uses PostgreSQL full-text search with boolean operators and relevance ranking.

        Args:
            query: Search query string (supports AND, OR, NOT operators - must be uppercase)
            topic: Topic for categorization
            max_results: Maximum number of results to return (default: 10, max: 100)
            start_date: Start date for article search (YYYY-MM-DD)
            end_date: End date for article search (YYYY-MM-DD)
            language: Language code (default: "en")
            locale: Not used by NewsFirehose (kept for interface compatibility)
            domains: Not used by /v1/search (kept for interface compatibility)
            exclude_domains: Not used by /v1/search (kept for interface compatibility)
            sort_by: Sort order ("published_at" or "relevance", default: "relevance")
            source_ids: List of source names to include
            exclude_source_ids: Not used by /v1/search (kept for interface compatibility)
            categories: List of categories to filter by
            exclude_categories: Not used by /v1/search (kept for interface compatibility)
            search_fields: Not used (NewsFirehose searches all fields by default)
            page: Page number for pagination
            timeframe: Hours to look back (converts to from_date)
        """
        try:
            # Normalize query for /v1/search (strip complex boolean syntax)
            normalized_query = self._normalize_query(query)
            logger.info(f"NewsFirehose query: '{query[:80]}' -> '{normalized_query[:80]}'")

            # Build parameters for /v1/search endpoint
            params = {
                "q": normalized_query,
                "page_size": min(max_results, 100),  # API limit is 100
                "page": page,
                "sort_by": {"publishedAt": "published_at", "publishedat": "published_at"}.get(sort_by, sort_by) if sort_by else "relevance"
            }

            # Add language filter (convert ISO code to full name if needed)
            if language:
                # Map ISO 639-1 codes to full names (API quirk)
                params["language"] = self.LANGUAGE_MAP.get(language.lower(), language)

            # Add source filter
            if source_ids:
                params["sources"] = ",".join(source_ids)

            # Add category filter
            if categories:
                params["categories"] = ",".join(categories)

            # Server-side date bounds (re-enabled 2026-08-10; the API now
            # parses ISO date strings and enforces its own 14-day default /
            # 90-day cap, so an unbounded query is no longer possible). We
            # send our real window explicitly so the server bound matches the
            # client-side filter below instead of silently narrowing to 14d.
            # Bounds become timezone-aware. A naive bound from an older
            # caller is on the local clock, so astimezone() reads it as local.
            start_date = _aware(coerce_datetime(start_date) if isinstance(start_date, str) else start_date)
            end_date = _aware(coerce_datetime(end_date) if isinstance(end_date, str) else end_date)
            if start_date is not None:
                from_dt = start_date
            elif timeframe:
                from_dt = _aware(datetime.now()) - timedelta(hours=timeframe)
            else:
                from_dt = _aware(datetime.now()) - timedelta(days=30)
            params.update(_date_params(from_dt, end_date))

            logger.debug(f"NewsFirehose /v1/search params: {params}")

            # Set up headers with API key
            headers = {
                "X-API-Key": self.api_key,
                "Accept": "application/json"
            }

            # Single fetch since 2026-08-10. The old 20s newest-first attempt
            # followed by a 60s relevance re-issue ran two concurrent scans by
            # design (the abandoned first attempt kept executing server-side).
            # The server now cancels on disconnect, bounds every query with a
            # 60s statement timeout, and runs published_at sorts on bitmap
            # plans, so the pathology the two-stage fetch worked around
            # (q=Solumina hanging past 130s newest-first, 2026-08-06) is gone.
            # Client timeout 75s > server 60s: the server always resolves
            # first, so we never abandon a query that is still running.
            #
            # Retries are for requests the server never received: retry only
            # connection-establishment failures, never read timeouts.
            async def _fetch(fetch_params, timeout_seconds):
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        f"{self.base_url}/v1/search",
                        params=fetch_params,
                        headers=headers
                    ) as response:
                        if response.status != 200:
                            try:
                                body = await response.json(content_type=None)
                            except Exception:  # noqa: BLE001
                                body = (await response.text())[:500]
                            raise ProviderHTTPError(
                                response.status, provider_message(body, f"HTTP {response.status}"),
                                url=f"{self.base_url}/v1/search")
                        data = await response.json(content_type=None)
                        if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
                            raise ValueError("NewsFirehose JSON parse error: no 'articles' list")
                        return data

            async def _fetch_with_connect_retry(fetch_params, timeout_seconds):
                for attempt in (1, 2):
                    try:
                        return await _fetch(fetch_params, timeout_seconds)
                    except aiohttp.ClientConnectorError as exc:
                        if attempt == 2:
                            raise
                        logger.warning(f"NewsFirehose connect failed ({exc}); one retry in 2s")
                        await asyncio.sleep(2)

            # The API rejects queries with more than 8 OR terms (HTTP 400).
            # Normalized queries are flat OR-chains, so split into chunks and
            # merge, deduplicating by URL. A chunk that fails is not skipped
            # quietly: if every chunk fails the error is raised, and if some
            # fail the log says which. This is the interactive search; the
            # keyword monitor uses collect(), which pages and keeps a cursor.
            chunks = self._split_query_terms(normalized_query)
            merged: list = []
            seen_urls: set = set()
            chunk_errors: list = []
            for chunk in chunks:
                try:
                    data = await _fetch_with_connect_retry({**params, "q": chunk}, 75)
                except Exception as chunk_exc:  # noqa: BLE001
                    chunk_errors.append(chunk_exc)
                    logger.error(f"NewsFirehose chunk failed for '{chunk[:80]}': "
                                 f"{type(chunk_exc).__name__}: {chunk_exc}")
                    continue
                self.requests_today += 1
                for article in data.get("articles", []):
                    key = article.get("url") or article.get("external_id")
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    merged.append(article)
                if len(merged) >= max_results * 2:
                    break
            if chunk_errors and len(chunk_errors) == len(chunks):
                raise chunk_errors[0]
            if chunk_errors:
                logger.warning(f"NewsFirehose: {len(chunk_errors)} of {len(chunks)} query chunk(s) failed "
                               f"for '{query[:80]}'; results are incomplete")

            articles = merged
            logger.info(
                f"NewsFirehose returned {len(articles)} articles across "
                f"{len(chunks)} chunk(s) for query '{query[:80]}'"
            )

            # Client-side date filter to the window that was asked for: the
            # caller's start_date (or timeframe, or 30 days when neither is
            # given) up to end_date. The API only filters by whole days.
            lo = coerce_datetime(from_dt)
            hi = coerce_datetime(end_date) if end_date is not None else None
            filtered_articles = []
            outside = 0
            for article in articles:
                when = coerce_datetime(article.get('publishedAt'))
                if when is None or in_interval(when, lo, hi):
                    filtered_articles.append(article)
                else:
                    outside += 1
            if outside:
                logger.info(f"📅 Date filter: dropped {outside}/{len(articles)} outside "
                            f"{lo.isoformat() if lo else '-'}..{hi.isoformat() if hi else 'now'}")

            return [self._format_article(article, topic) for article in filtered_articles[:max_results]]

        except Exception as e:
            # Raised, not swallowed: an empty list here reads as "no news".
            # Interactive callers already handle a failed search.
            logger.error(f"NewsFirehose search failed: {type(e).__name__}: {e}")
            raise

    async def collect(
        self,
        query: str,
        topic: str,
        *,
        interval_start: Optional[datetime] = None,
        interval_end: Optional[datetime] = None,
        max_results: int = 10,
        continuation: Optional[Dict[str, Any]] = None,
        language: Optional[str] = "en",
        source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        **kw: Any,
    ) -> CollectionResult:
        """Collect one fixed interval, paging every OR-chunk to its proven end.

        Each chunk (at most 8 terms, the API's limit) is paged newest first,
        100 rows a page, until the API says ``has_more: false`` or a page
        reaches back past the window start. Nothing else counts as the end:
        a page that is short after our own filtering or deduplication is not
        exhaustion. There is no per-chunk page cap. Until 7 Oct 2026 a cap of
        3 pages advanced the checkpoint past whatever it had not read; that
        silently dropped the rest of a broad keyword's window.

        Budget per run: ``NEWSFIREHOSE_MAX_PAGES`` (default 12) and
        ``NEWSFIREHOSE_BUDGET_SECONDS`` (default 90, inside the monitor's 120 s
        timeout). Running out returns ``partial`` with a continuation naming
        the next ``{chunk, page}`` of the same interval; the monitor runs
        follow-up rounds and the next cycle resumes there. A resume replays
        the page before the cursor, because the sort (``published_at DESC``,
        no tie-breaker) is not stable across requests; repeats are
        deduplicated at insert.

        ``NEWSFIREHOSE_OVERLAP_HOURS`` (default 12): the window reaches back
        this far before the interval start, because the firehose indexes
        articles hours after publication.

        ``NEWSFIREHOSE_BROAD_PAGES_PER_DAY`` (default 20, 0 turns it off; 10 until 7 Oct 2026, when it blocked a narrowed keyword on a busy day): a
        chunk that still has rows after this many pages per day of window is
        a keyword too broad to collect in full. On 7 Oct 2026 the AI group's
        keywords returned 1,000-3,500 rows a day each, because the OR-flattened
        query contains "AI" on its own. Such a run is a configuration failure
        with no items: nothing is skipped silently, coverage does not move,
        and health shows the keyword until someone narrows it.

        An HTTP error, a malformed body or an exception is a failed result,
        never an empty success. Rows collected on earlier pages are kept on
        the failed result, with the cursor of the page that failed, so the
        caller saves them and the retry starts at that page.
        """
        res = self.new_result(query, interval_start, interval_end)
        norm = self._normalize_query(query or "")
        if not norm or not norm.strip():
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res, query, interval_start, interval_end)

        chunks = self._split_query_terms(norm)
        clock = PageClock(provider_max_pages("NEWSFIREHOSE_MAX_PAGES", 12),
                          _env_float("NEWSFIREHOSE_BUDGET_SECONDS", 90.0))
        overlap = timedelta(hours=_env_float("NEWSFIREHOSE_OVERLAP_HOURS", 12.0))

        hi = res.interval_end
        lo = (res.interval_start - overlap) if res.interval_start is not None \
            else coerce_datetime(datetime.now().astimezone() - timedelta(days=30))
        params: Dict[str, Any] = {"page_size": 100, "sort_by": "published_at",
                                  **_date_params(lo, hi)}
        if language:
            params["language"] = self.LANGUAGE_MAP.get(language.lower(), language)
        if source_ids:
            params["sources"] = ",".join(source_ids)
        if categories:
            params["categories"] = ",".join(categories)
        fingerprint = _query_fingerprint(chunks, params)
        broad_per_day = _env_float("NEWSFIREHOSE_BROAD_PAGES_PER_DAY", 20.0)
        window_days = max(1.0, ((hi - lo).total_seconds() / 86400.0) if (hi and lo) else 30.0)
        broad_limit = int(broad_per_day * window_days + 0.999) if broad_per_day > 0 else 0

        cont = continuation or {}
        ci, page = 0, 1
        # Leading pages of the current chunk that held only rows newer than
        # the window (the API's whole-day to_date plus our slack). They are
        # read, but do not count toward the broad-query limit.
        ahead = 0
        if cont and cont.get("q") == fingerprint:
            try:
                ci = max(0, int(cont.get("chunk") or 0))
                page = max(1, int(cont.get("page") or 1))
                ahead = max(0, int(cont.get("ahead") or 0))
            except (TypeError, ValueError):
                ci, page, ahead = 0, 1, 0
        elif cont:
            res.diagnostics["continuation_discarded"] = "query or parameters changed"
        resume_at = (ci, page)
        if page > 1:
            page -= 1
            res.diagnostics["replayed_page"] = page
        res.diagnostics["resumed_at"] = {"chunk": ci, "page": page}

        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        host = host_of(self.base_url)
        url = f"{self.base_url}/v1/search"
        seen: set = set()

        def _stop(out: CollectionResult) -> CollectionResult:
            out.items = res.items
            out.counts = res.counts
            out.started_at = res.started_at
            # Never hand back a cursor behind the one this run resumed from:
            # a failure on the replayed page would otherwise walk it back.
            out.continuation = {"q": fingerprint, "chunk": ci, "page": page, "ahead": ahead}
            if (ci, page) < resume_at:
                out.continuation.update(chunk=resume_at[0], page=resume_at[1])
            out.diagnostics.update(res.diagnostics, pages=clock.pages, chunks=len(chunks))
            return self.finish(out, query, interval_start, interval_end)

        def _malformed(why: str) -> CollectionResult:
            return CollectionResult.failure(
                ERR_PARSE, f"parse: NewsFirehose {why} (chunk {ci}, page {page}) host={host}",
                retryable=True)

        try:
            async with _session() as session:
                while ci < len(chunks):
                    if clock.exhausted:
                        return _stop(CollectionResult.partial([], truncated_reason=clock.reason))
                    left = clock.max_seconds - (time.monotonic() - clock.started)
                    status, data, _hdrs = await get_json(
                        session, url, params={**params, "q": chunks[ci], "page": page},
                        headers=headers, timeout=max(10.0, min(75.0, left)))
                    clock.tick()
                    self.requests_today += 1
                    if status != 200:
                        exc = ProviderHTTPError(status, provider_message(data, f"HTTP {status}"), url=url)
                        return _stop(CollectionResult.from_exception(exc, host=host))
                    if not isinstance(data, dict):
                        return _stop(_malformed("answered 200 with a body that is not a JSON object"))
                    rows = data.get("articles")
                    has_more = data.get("has_more")
                    if not isinstance(rows, list):
                        return _stop(_malformed("response has no 'articles' list"))
                    if not isinstance(has_more, bool):
                        # Without it nothing proves the chunk is finished.
                        return _stop(_malformed("response has no boolean 'has_more'"))
                    if has_more and not rows:
                        return _stop(_malformed("says has_more on an empty page"))
                    res.counts.received += len(rows)
                    oldest = None
                    for a in rows:
                        if not isinstance(a, dict):
                            res.counts.invalid += 1
                            continue
                        when = coerce_datetime(a.get("publishedAt"))
                        if when is not None and (oldest is None or when < oldest):
                            oldest = when
                        key = a.get("url") or a.get("external_id") or a.get("id")
                        if not key or not a.get("title"):
                            res.counts.invalid += 1
                            continue
                        if key in seen:
                            res.counts.duplicate += 1
                            continue
                        seen.add(key)
                        if not in_interval(when, lo, hi):
                            res.counts.filtered += 1
                            continue
                        res.items.append(self._format_article(a, topic))
                    # Newest first: once a page reaches back past the window
                    # start there is nothing older worth asking for.
                    past_start = lo is not None and oldest is not None and oldest < lo
                    if page == ahead + 1 and hi is not None and oldest is not None and oldest > hi:
                        ahead += 1
                    if has_more and not past_start:
                        if broad_limit and page - ahead >= broad_limit:
                            out = CollectionResult.failure(
                                ERR_CONFIG,
                                f"configuration: query too broad for NewsFirehose - chunk {ci + 1} of "
                                f"{len(chunks)} still has rows after {page - ahead} pages ({(page - ahead) * 100} rows) "
                                f"inside a "
                                f"{window_days:.1f}-day window (limit {broad_per_day:g} pages a day); narrow "
                                f"the keyword", retryable=False)
                            out.started_at = res.started_at
                            out.diagnostics.update(res.diagnostics, pages=clock.pages, chunks=len(chunks),
                                                   too_broad_chunk=ci, rows_seen=res.counts.received)
                            out.counts = res.counts
                            logger.warning(f"NewsFirehose: '{(query or '')[:80]}' is too broad "
                                           f"({page} pages in chunk {ci + 1}); no items kept")
                            return self.finish(out, query, interval_start, interval_end)
                        page += 1
                    else:
                        ci, page, ahead = ci + 1, 1, 0
        except Exception as exc:  # noqa: BLE001
            return _stop(CollectionResult.from_exception(exc, host=host))

        res.diagnostics.update(pages=clock.pages, chunks=len(chunks))
        logger.info(
            f"NewsFirehose collected {len(res.items)} of {res.counts.received} rows for "
            f"'{(query or '')[:80]}' in {clock.pages} page(s) over {len(chunks)} chunk(s)")
        return self.finish(res, query, interval_start, interval_end)

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch full article content from NewsFirehose by URL."""
        try:
            headers = {
                "X-API-Key": self.api_key,
                "Accept": "application/json"
            }

            # Use the search endpoint with the URL
            params = {"q": url, "page_size": 1}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/v1/search",
                    params=params,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        logger.error(f"NewsFirehose fetch_article_content error: {response.status}")
                        return None

                    data = await response.json()
                    articles = data.get("articles", [])

                    if not articles:
                        logger.warning(f"NewsFirehose returned no articles for URL: {url}")
                        return None

                    article = articles[0]

                    # Extract source name from URL
                    source_name = ''
                    if article.get('url'):
                        parsed_url = urlparse(article['url'])
                        source_name = parsed_url.netloc.replace('www.', '')

                    if not source_name:
                        source = article.get('source', {})
                        source_name = source.get('name', '') if isinstance(source, dict) else str(source)

                    return {
                        'title': article.get('title', ''),
                        'content': article.get('content') or article.get('description', ''),
                        'authors': [article.get('author')] if article.get('author') else [],
                        'published_date': article.get('publishedAt', ''),
                        'url': article.get('url', ''),
                        'source': source_name,
                        'raw_data': {
                            'source': article.get('source'),
                            'image_url': article.get('urlToImage'),
                            'categories': article.get('categories', []),
                            'topics': article.get('topics', []),
                            'language': article.get('language')
                        }
                    }

        except aiohttp.ClientError as e:
            logger.error(f"NewsFirehose fetch_article_content network error: {e}")
            return None
        except Exception as e:
            logger.error(f"NewsFirehose fetch_article_content error: {e}")
            return None

    def _format_article(self, article: Dict, topic: str) -> Dict:
        """Format NewsFirehose article data to standard format."""
        # Extract source name from URL (more reliable than API source name)
        source_name = ''
        if article.get('url'):
            parsed_url = urlparse(article['url'])
            source_name = parsed_url.netloc.replace('www.', '')

        # Fallback to API source name
        if not source_name:
            source = article.get('source', {})
            if isinstance(source, dict):
                source_name = source.get('name', '').strip()
            elif isinstance(source, str):
                source_name = source.strip()

        # Handle authors - can be string or list
        authors = []
        if article.get('author'):
            authors = [article['author']]
        elif article.get('creators'):
            authors = article['creators'] if isinstance(article['creators'], list) else [article['creators']]

        # Handle keywords
        keywords = article.get('keywords', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',') if k.strip()]

        return {
            'title': article.get('title', ''),
            'summary': article.get('description', '') or article.get('snippet', ''),
            'content': article.get('content', ''),  # NewsFirehose provides full content - no scraping needed
            'authors': authors,
            'published_date': article.get('publishedAt', ''),
            'url': article.get('url', ''),
            'source': source_name,
            'topic': topic,
            'raw_data': {
                'source': article.get('source'),
                'image_url': article.get('urlToImage'),
                'keywords': keywords,
                'categories': article.get('categories', []),
                'topics': article.get('topics', []),  # Pre-enriched topics from NewsFirehose
                'language': article.get('language'),
                'external_id': article.get('id') or article.get('external_id'),
                'ai_summary': article.get('ai_summary'),  # Pre-generated AI summary
                'ai_tag': article.get('ai_tag'),
                'sentiment': article.get('sentiment'),
                'mbfc_bias': article.get('mbfc_bias'),
                'mbfc_factual_reporting': article.get('mbfc_factual_reporting'),
                'mbfc_credibility': article.get('mbfc_credibility')
            }
        }
