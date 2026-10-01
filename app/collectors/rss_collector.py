import asyncio
import os
import re
from urllib.parse import urlsplit

import feedparser
import httpx
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional
from .base_collector import ArticleCollector
from app.collectors import dates
from app.collectors.contracts import (
    CollectionResult, ERR_PARSE, STATUS_PARTIAL, TRUNC_PARSE_PARTIAL,
    describe_exception, host_of,
)
import logging
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Re-stamped feeds
# ---------------------------------------------------------------------------
#
# A site that migrates or republishes its blog gives every old post a new
# date, and its feed then presents a 2024 funding announcement as this
# week's news. Prophet Security's feed carried twelve posts dated within one
# minute of 14 August 2026; the Wayback Machine had captured the Series A
# post in July 2025 and the launch post in October 2024. Dropzone AI's feed
# did the same on 18 June and 1 July.
#
# The feed cannot be trusted on its own and neither can the page — the
# page's own ``datePublished`` was rewritten with it. The one outside record
# is the Wayback Machine's first capture of the URL, which bounds the
# publication date from above: a page captured in July 2025 was not
# published in August 2026. That check costs one request per URL, so it
# only runs for URLs that are new to us and only when the feed shows the
# signature of a batch re-stamp — entries dated within minutes of each
# other. Dropzone re-stamped just two posts 68 seconds apart on
# 1 Sep 2026, and the same-minute-times-four rule missed them.
# Wire feeds batch too, but their batches are of genuinely new items, and
# Wayback has no earlier capture of those, so nothing changes for them.

#: Entries dated within the window of each other before a feed is suspected
#: of re-stamping. Two is enough: a false positive costs one Wayback lookup
#: per new URL, a miss puts an old post on the front page as news.
RESTAMP_MIN_ITEMS = max(2, int(os.getenv("RSS_RESTAMP_MIN_ITEMS", "2") or 2))
#: How close together entry dates must sit to count as one batch. Same-minute
#: caught whole-archive migrations; partial re-stamps arrive minutes apart.
RESTAMP_WINDOW_MINUTES = max(1, int(os.getenv("RSS_RESTAMP_WINDOW_MINUTES", "15") or 15))
#: A first capture this many days before the feed's date proves the feed
#: wrong; anything closer is crawl lag.
RESTAMP_TOLERANCE_DAYS = max(0, int(os.getenv("RSS_RESTAMP_TOLERANCE_DAYS", "2") or 2))
#: Seconds allowed per Wayback lookup. The CDX index regularly takes
#: 10–20 seconds to answer; a shorter limit turned every lookup into "no
#: capture on record".
WAYBACK_TIMEOUT = float(os.getenv("RSS_WAYBACK_TIMEOUT", "30") or 30)
#: Failed lookups in a row before a poll gives up on the index for now. The
#: feed's dates then stand, and the next poll tries again for what is new.
RESTAMP_MAX_CONSECUTIVE_FAILURES = 3
WAYBACK_CDX = "http://web.archive.org/cdx/search/cdx"


def restamp_check_enabled() -> bool:
    return (os.getenv("RSS_RESTAMP_CHECK", "1") or "1").strip().lower() not in (
        "0", "false", "no", "off")


def _wayback_key(url: str) -> str:
    """The URL the way the CDX index wants it: no scheme, no fragment."""
    parts = urlsplit(url.strip())
    host = (parts.netloc or "").lower()
    path = parts.path or "/"
    return f"{host}{path}" + (f"?{parts.query}" if parts.query else "")


async def first_capture(url: str, *, client: Optional[httpx.AsyncClient] = None
                        ) -> Optional[datetime]:
    """When the Wayback Machine first saw this URL return a page, or None.

    None means "no capture on record or the index did not answer", and the
    caller treats both the same way: the feed's date stands.
    """
    params = {"url": _wayback_key(url), "fl": "timestamp",
              "filter": "statuscode:200", "limit": "1"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=WAYBACK_TIMEOUT)
    try:
        response = await client.get(WAYBACK_CDX, params=params,
                                    headers={"User-Agent": "AunooAI RSS Collector/1.0"})
        response.raise_for_status()
        stamp = (response.text or "").strip().split("\n")[0].strip()
        if not re.fullmatch(r"\d{14}", stamp):
            return None
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception as exc:                                       # noqa: BLE001
        logger.info("wayback lookup failed for %s: %s", url, exc)
        raise LookupFailed(str(exc)) from exc
    finally:
        if own:
            await client.aclose()


class LookupFailed(RuntimeError):
    """The index did not answer. Distinct from "no capture on record"."""


def restamped_batches(articles: List[Dict]) -> List[Dict]:
    """The articles whose feed dates cluster tightly enough to look re-stamped.

    Entries sorted by date are chained while each sits within
    ``RESTAMP_WINDOW_MINUTES`` of the one before; a chain of
    ``RESTAMP_MIN_ITEMS`` or more is suspect. A feed posting twice in an
    afternoon stays clear of the window; a re-stamp lands its fake dates
    minutes apart because one job wrote them.
    """
    stamped = []
    for article in articles:
        stamp = _to_datetime(article.get("published_date"))
        if stamp is not None:
            stamped.append((stamp.astimezone(timezone.utc), article))
    stamped.sort(key=lambda pair: pair[0])
    window = timedelta(minutes=RESTAMP_WINDOW_MINUTES)
    out: List[Dict] = []
    cluster: List[Dict] = []
    last = None
    for stamp, article in stamped:
        if last is not None and (stamp - last) <= window:
            cluster.append(article)
        else:
            if len(cluster) >= RESTAMP_MIN_ITEMS:
                out.extend(cluster)
            cluster = [article]
        last = stamp
    if len(cluster) >= RESTAMP_MIN_ITEMS:
        out.extend(cluster)
    return out


async def bound_restamped_dates(
        articles: List[Dict], *,
        lookup: Optional[Callable[[str], "asyncio.Future"]] = None) -> int:
    """Replace a re-stamped feed date with the Wayback first capture, in place.

    Only articles in a same-minute batch are looked up. Where the first
    capture is earlier than the feed's date by more than the tolerance, the
    capture becomes ``published_date`` — an upper bound on when the page was
    published, which is the honest figure — and ``raw_data`` records both the
    feed's date and where the replacement came from. Returns how many dates
    were replaced.
    """
    suspects = restamped_batches(articles)
    if not suspects:
        return 0
    replaced = failures = 0
    async with httpx.AsyncClient(timeout=WAYBACK_TIMEOUT) as client:
        for article in suspects:
            url = (article.get("url") or "").strip()
            feed_date = _to_datetime(article.get("published_date"))
            if not url or feed_date is None:
                continue
            raw = article.setdefault("raw_data", {})
            try:
                capture = await (lookup(url) if lookup
                                 else first_capture(url, client=client))
            except LookupFailed:
                failures += 1
                raw["date_source"] = "feed"
                raw["date_check"] = "batch-dated; capture index did not answer"
                if failures >= RESTAMP_MAX_CONSECUTIVE_FAILURES:
                    logger.warning("re-stamp check stopped after %d failed "
                                   "lookups; feed dates stand", failures)
                    break
                continue
            failures = 0
            if capture is None:
                raw["date_source"] = "feed"
                raw["date_check"] = "batch-dated; no earlier capture on record"
                continue
            if capture <= feed_date - timedelta(days=RESTAMP_TOLERANCE_DAYS):
                raw["feed_published_date"] = article.get("published_date")
                raw["date_source"] = "wayback_first_capture"
                raw["date_precision"] = "no_later_than"
                article["published_date"] = capture.isoformat()
                # The stored row says where the date came from (work
                # package 7); the feed's own value stays in raw_data.
                article["date_provenance"] = dates.PROV_WAYBACK
                replaced += 1
                logger.info("re-stamped feed date corrected for %s: feed said %s, "
                            "first captured %s", url, feed_date.date(), capture.date())
            else:
                raw["date_source"] = "feed"
                raw["date_check"] = "batch-dated; first capture agrees"
    return replaced


def _to_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


#: Characters a publisher may leave in front of the XML declaration: the
#: UTF-8 byte-order mark (as a code point, and as it looks when the bytes
#: were decoded as Latin-1) and plain whitespace. feedparser rejects the
#: whole document as "XML or text declaration not at start of entity"
#: when any of these precede ``<?xml``; 47 such warnings in seven days.
_LEADING_JUNK = "\ufeff\xef\xbb\xbf\xa0 \t\r\n"
_DECLARATION_NOT_AT_START = "not at start of entity"


def clean_feed_text(text: str) -> str:
    """The feed body with a byte-order mark and leading whitespace removed."""
    if not text:
        return text or ""
    return text.lstrip(_LEADING_JUNK)


def _bozo_message(feed) -> str:
    exc = feed.get("bozo_exception") if hasattr(feed, "get") else None
    if exc is None:
        return "feed parser reported an error without a message"
    return describe_exception(exc)


class RSSCollector(ArticleCollector):
    """RSS/Atom feed collector implementation."""

    def __init__(self):
        self.timeout = 30  # seconds

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        feed_url: Optional[str] = None,
        **kwargs
    ) -> List[Dict]:
        """
        Search RSS feed for articles.

        For RSS feeds, the 'query' parameter is actually the feed URL.
        The query parameter can also be used for filtering if feed_url is provided.
        """
        # The feed URL can be passed as query or feed_url parameter
        url = feed_url or query

        if not url or not url.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid RSS feed URL: {url}")

        try:
            articles = await self.fetch_feed(
                feed_url=url,
                topic=topic,
                max_results=max_results,
                since=start_date
            )
            return articles[:max_results]
        except Exception as e:
            logger.error(f"Error fetching RSS feed {url}: {str(e)}")
            raise ValueError(f"RSS feed fetch failed: {str(e)}")

    async def fetch_feed(
        self,
        feed_url: str,
        topic: str = "",
        max_results: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """Compatibility wrapper around :meth:`fetch_feed_result`.

        Returns the items as a plain list, the way the manual fetch route
        and ``search_articles`` expect. A failed fetch raises ``ValueError``
        as before. ``max_results`` is honoured only when a caller passes
        one; the collection layer itself no longer stops at 50 entries
        (work package 2). Entries older than ``since`` are returned too,
        marked ``_older_than_since``, because the feed monitor dedups by
        URL and an old-dated entry can still be one we have never seen.
        """
        result = await self.fetch_feed_result(
            feed_url, topic=topic, since=since, max_entries=max_results)
        if result.failed:
            raise ValueError(f"Failed to fetch feed: {result.error_message}")
        return list(result.items)

    async def fetch_feed_result(
        self,
        feed_url: str,
        topic: str = "",
        since: Optional[datetime] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        max_entries: Optional[int] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> CollectionResult:
        """Fetch and parse one feed and say what happened.

        The result separates the outcomes a list could not: a 304 and a
        valid empty feed are successes with no items; a document that
        yields no feed structure is a parse failure; a document the parser
        only partly recovered returns its entries with ``parse_partial``
        set and no cache validators, so the next poll fetches the whole
        response again (work package 29).

        Nothing here writes feed state. ``proposed_validators`` carries the
        ETag and Last-Modified the caller may commit once every item is
        persisted or durably queued (work package 16).
        """
        host = host_of(feed_url)
        started = datetime.now(timezone.utc)
        result = CollectionResult.ok([], provider="rss", scope=feed_url)
        result.started_at = started
        result.interval_start = since
        # Fixed at run start: this is what coverage_through becomes when the
        # caller decides the run was complete.
        result.interval_end = started

        headers = {
            'User-Agent': 'AunooAI Feed Reader/1.0 (+https://aunoo.ai)',
            'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml',
        }
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified

        own_client = client is None
        client = client or httpx.AsyncClient(timeout=self.timeout)
        try:
            try:
                response = await client.get(feed_url, headers=headers, follow_redirects=True)
            except Exception as exc:                                   # noqa: BLE001
                logger.error("feed fetch failed for %s: %s", feed_url, describe_exception(exc, host=host))
                failed = CollectionResult.from_exception(exc, host=host, provider="rss", scope=feed_url)
                return self._finish(failed, started, since)
        finally:
            if own_client:
                await client.aclose()

        status = int(getattr(response, "status_code", 0) or 0)
        result.diagnostics["http_status"] = status
        retry_after = response.headers.get("Retry-After") if getattr(response, "headers", None) else None
        if retry_after:
            result.diagnostics["retry_after"] = retry_after

        if status == 304:
            # Nothing changed since the validators we sent. A success with
            # no items; the caller keeps its checkpoint where it is.
            result.diagnostics["not_modified"] = True
            result.proposed_validators = self._validators_of(response, etag, last_modified)
            logger.info("feed not modified: %s", feed_url)
            return self._finish(result, started, since)

        try:
            response.raise_for_status()
        except Exception as exc:                                       # noqa: BLE001
            logger.error("feed fetch failed for %s: %s", feed_url, describe_exception(exc, host=host))
            failed = CollectionResult.from_exception(exc, host=host, provider="rss", scope=feed_url)
            failed.diagnostics.update(result.diagnostics)
            return self._finish(failed, started, since)

        text = clean_feed_text(response.text or "")
        feed = feedparser.parse(text)
        if feed.bozo and _DECLARATION_NOT_AT_START in str(feed.get("bozo_exception") or ""):
            # Something other than whitespace sat before the declaration
            # (a stray byte, a comment). Cut to the first tag and try once
            # more; the retry is recorded so a feed that needs it is visible.
            start = text.find("<?xml")
            if start > 0:
                feed = feedparser.parse(text[start:])
                result.diagnostics["hygiene_retry"] = True

        entries = list(feed.entries or [])
        since_utc = _to_datetime(since) if since is not None else None
        items: List[Dict] = []
        invalid = 0
        older = 0
        for entry in entries:
            try:
                article = self._parse_entry(entry, feed, topic)
            except Exception as exc:                                   # noqa: BLE001
                logger.warning("Error parsing feed entry: %s", describe_exception(exc))
                article = None
            if not article:
                invalid += 1
                continue
            if since_utc is not None:
                pub = _to_datetime(article.get("published_date"))
                if pub is not None and pub < since_utc:
                    # Advisory only. An entry dated before the cutoff can
                    # still be one we never stored; the caller dedups by URL.
                    article["_older_than_since"] = True
                    older += 1
            items.append(article)
            if max_entries is not None and len(items) >= max_entries:
                result.diagnostics["max_entries_reached"] = max_entries
                break

        if feed.bozo and not items:
            # The parser choked and nothing usable came out: an error, not
            # an empty feed. A truncated document can leave one entry with
            # no title or link; that is still nothing usable.
            message = _bozo_message(feed)
            logger.error("feed could not be parsed: %s: %s", feed_url, message)
            failed = CollectionResult.failure(
                ERR_PARSE, f"{message} host={host}" if host and "host=" not in message else message,
                retryable=False, provider="rss", scope=feed_url)
            failed.diagnostics.update(result.diagnostics)
            failed.diagnostics["bozo"] = message
            failed.counts.add(received=len(entries), invalid=invalid)
            return self._finish(failed, started, since)
        if not items and not feed.get("version") and not feed.feed.get("title"):
            # Not an error the parser noticed, but not a feed either: an
            # empty document, an HTML page, a JSON blob. socjedi.ai/rss.xml
            # served an empty document 72 times with last_error NULL.
            message = f"parse: no feed structure in response ({len(text)} chars)"
            logger.error("feed could not be parsed: %s: %s", feed_url, message)
            failed = CollectionResult.failure(
                ERR_PARSE, f"{message} host={host}" if host else message,
                retryable=False, provider="rss", scope=feed_url)
            failed.diagnostics.update(result.diagnostics)
            return self._finish(failed, started, since)

        if feed.bozo:
            # The parser recovered some entries and lost an unknown number.
            # Say so, and offer no validators: the next poll must see the
            # whole response again rather than a 304.
            message = _bozo_message(feed)
            logger.warning("feed parsed partially: %s: %s (%d entries recovered)",
                           feed_url, message, len(items))
            result.status = STATUS_PARTIAL
            result.coverage_complete = False
            result.parse_partial = True
            result.retryable = True
            result.truncated_reason = TRUNC_PARSE_PARTIAL
            result.diagnostics["bozo"] = message
            result.diagnostics["entries_recovered"] = len(items)
        else:
            result.proposed_validators = self._validators_of(response, None, None)

        result.items = items
        result.counts.add(received=len(entries), invalid=invalid)
        result.diagnostics["older_than_since"] = older
        logger.info("Fetched %d articles from %s", len(items), feed_url)
        return self._finish(result, started, since)

    @staticmethod
    def _finish(result: CollectionResult, started: datetime, since: Optional[datetime]) -> CollectionResult:
        result.started_at = result.started_at or started
        result.interval_start = result.interval_start or since
        result.interval_end = result.interval_end or started
        if result.provider is None:
            result.provider = "rss"
        return result.mark_finished()

    @staticmethod
    def _validators_of(response, etag: Optional[str], last_modified: Optional[str]) -> Dict[str, Optional[str]]:
        """The validators the caller may commit: the response's own, or the
        ones we sent when the response (a 304) did not repeat them."""
        headers = getattr(response, "headers", None) or {}
        out: Dict[str, Optional[str]] = {}
        new_etag = headers.get("ETag") or headers.get("etag") or etag
        new_lm = headers.get("Last-Modified") or headers.get("last-modified") or last_modified
        if new_etag:
            out["etag"] = str(new_etag)[:500]
        if new_lm:
            out["last_modified"] = str(new_lm)[:200]
        return out

    def _parse_entry(self, entry, feed, topic: str) -> Optional[Dict]:
        """Parse a single feed entry into standardized article format."""
        # Get title
        title = entry.get('title', '').strip()
        if not title:
            return None

        # Get URL
        url = entry.get('link', '')
        if not url:
            # Try alternate links
            for link in entry.get('links', []):
                if link.get('rel') == 'alternate' or link.get('type', '').startswith('text/html'):
                    url = link.get('href', '')
                    break
        if not url:
            return None

        # Get summary/description
        summary = ''
        if entry.get('summary'):
            summary = entry.get('summary', '')
        elif entry.get('description'):
            summary = entry.get('description', '')
        elif entry.get('content'):
            # Atom feeds may have content
            content_list = entry.get('content', [])
            if content_list and isinstance(content_list, list):
                summary = content_list[0].get('value', '')

        # Clean HTML from summary (basic cleanup)
        summary = self._strip_html(summary)[:1000]  # Limit length

        # Publication date, with precision and provenance (work package 7).
        # feedparser's *_parsed struct_time is already UTC and is preferred;
        # the raw string is kept beside it. A missing or unparseable date
        # stays None: the monitor stamps first_seen_at instead, and nothing
        # substitutes the current time.
        parsed = dates.unknown(provenance=dates.PROV_FEED)
        raw_text = None
        for date_field in ['published', 'updated', 'created']:
            raw_value = entry.get(date_field)
            struct = entry.get(f'{date_field}_parsed')
            candidate = dates.parse_date(struct, provenance=dates.PROV_FEED) if struct else None
            if candidate is None or not candidate.known:
                if raw_value:
                    candidate = dates.parse_date(raw_value, provenance=dates.PROV_FEED)
            if candidate is None:
                continue
            if candidate.known:
                parsed = candidate
                raw_text = str(raw_value)[:200] if raw_value else candidate.raw
                break
            if raw_value and raw_text is None:
                # Remember the first unparseable value so the row says what
                # the feed actually sent.
                parsed = candidate
                raw_text = str(raw_value)[:200]
        published_date = parsed.iso()

        # Get authors
        authors = []
        if entry.get('author'):
            authors.append(entry.get('author'))
        elif entry.get('authors'):
            for author in entry.get('authors', []):
                if isinstance(author, dict):
                    authors.append(author.get('name', ''))
                else:
                    authors.append(str(author))

        # Get source name from feed
        source = feed.feed.get('title', '') or self._extract_domain(url)

        # Get categories/tags
        tags = []
        for tag in entry.get('tags', []):
            if isinstance(tag, dict):
                tags.append(tag.get('term', ''))
            else:
                tags.append(str(tag))

        return {
            'title': title,
            'summary': summary,
            'authors': authors,
            'published_date': published_date,
            'published_at_raw': raw_text,
            'publication_date_precision': parsed.precision if parsed.known else None,
            'date_provenance': parsed.provenance if parsed.known else dates.PROV_UNKNOWN,
            'url': url,
            'source': source,
            'topic': topic,
            'raw_data': {
                'feed_url': feed.href if hasattr(feed, 'href') else '',
                'feed_title': feed.feed.get('title', ''),
                'entry_id': entry.get('id', url),
                'tags': tags,
                'source_name': source,
                'date_parse_status': parsed.status,
            }
        }

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch full article content from URL.

        Note: RSS feeds typically only provide summaries. For full content,
        the article URL would need to be scraped, which is handled by the
        enrichment pipeline (Firecrawl).
        """
        # RSS collector doesn't fetch full content - that's handled by enrichment
        # This is a placeholder that returns minimal info
        return {
            'url': url,
            'content': '',  # Will be filled by enrichment pipeline
            'source': 'rss'
        }

    def _strip_html(self, text: str) -> str:
        """Basic HTML tag removal."""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Decode common HTML entities
        clean = clean.replace('&nbsp;', ' ')
        clean = clean.replace('&amp;', '&')
        clean = clean.replace('&lt;', '<')
        clean = clean.replace('&gt;', '>')
        clean = clean.replace('&quot;', '"')
        clean = clean.replace('&#39;', "'")
        # Normalize whitespace
        clean = ' '.join(clean.split())
        return clean.strip()

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL for source attribution."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except:
            return 'RSS Feed'

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats to datetime."""
        if isinstance(date_str, datetime):
            return date_str

        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            pass

        try:
            # Try RFC 2822 format (common in RSS)
            return parsedate_to_datetime(date_str)
        except:
            pass

        return None

    @staticmethod
    async def test_feed_url(url: str) -> Dict:
        """
        Test if a URL is a valid RSS/Atom feed.

        Returns:
            Dict with 'valid', 'title', 'description', 'entry_count', 'error'
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    url,
                    headers={
                        'User-Agent': 'AunooAI Feed Reader/1.0 (+https://aunoo.ai)',
                        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml'
                    },
                    follow_redirects=True
                )
                response.raise_for_status()
                content = response.text

            feed = feedparser.parse(content)

            if feed.bozo and not feed.entries:
                return {
                    'valid': False,
                    'error': str(feed.bozo_exception) if feed.bozo_exception else 'Invalid feed format'
                }

            return {
                'valid': True,
                'title': feed.feed.get('title', 'Unknown'),
                'description': feed.feed.get('description', ''),
                'entry_count': len(feed.entries),
                'feed_type': feed.version or 'unknown'
            }

        except httpx.HTTPError as e:
            return {'valid': False, 'error': f'HTTP error: {str(e)}'}
        except Exception as e:
            return {'valid': False, 'error': str(e)}
