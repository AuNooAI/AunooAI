import asyncio
import calendar
import os
import re
from collections import defaultdict
from urllib.parse import urlsplit

import feedparser
import httpx
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional
from .base_collector import ArticleCollector
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
# signature of a batch re-stamp — several entries dated within one minute.
# Wire feeds batch too, but their batches are of genuinely new items, and
# Wayback has no earlier capture of those, so nothing changes for them.

#: Entries dated within one minute of each other before a feed is suspected
#: of re-stamping. Three is a busy day; twelve is a migration.
RESTAMP_MIN_ITEMS = max(2, int(os.getenv("RSS_RESTAMP_MIN_ITEMS", "4") or 4))
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
    """The articles whose feed date is shared, to the minute, by enough others."""
    by_minute: Dict[str, List[Dict]] = defaultdict(list)
    for article in articles:
        stamp = _to_datetime(article.get("published_date"))
        if stamp is None:
            continue
        by_minute[stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")].append(article)
    out: List[Dict] = []
    for group in by_minute.values():
        if len(group) >= RESTAMP_MIN_ITEMS:
            out.extend(group)
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
        max_results: int = 50,
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Fetch and parse an RSS/Atom feed.

        Args:
            feed_url: URL of the RSS/Atom feed
            topic: Topic to assign to fetched articles
            max_results: Maximum number of articles to return
            since: Only return articles published after this date

        Returns:
            List of article dictionaries in standardized format
        """
        try:
            # Fetch the feed content
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    feed_url,
                    headers={
                        'User-Agent': 'AunooAI RSS Collector/1.0',
                        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml'
                    },
                    follow_redirects=True
                )
                response.raise_for_status()
                content = response.text

            # Parse the feed
            feed = feedparser.parse(content)

            if feed.bozo and feed.bozo_exception:
                logger.warning(f"Feed parsing warning for {feed_url}: {feed.bozo_exception}")

            articles = []
            for entry in feed.entries:
                try:
                    article = self._parse_entry(entry, feed, topic)
                    if article:
                        # Filter by date if since is provided
                        if since and article.get('published_date'):
                            pub_date = self._parse_date(article['published_date'])
                            if pub_date and pub_date < since:
                                continue
                        articles.append(article)

                        if len(articles) >= max_results:
                            break
                except Exception as e:
                    logger.warning(f"Error parsing feed entry: {e}")
                    continue

            logger.info(f"Fetched {len(articles)} articles from {feed_url}")
            return articles

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching feed {feed_url}: {e}")
            raise ValueError(f"Failed to fetch feed: {e}")
        except Exception as e:
            logger.error(f"Error processing feed {feed_url}: {e}")
            raise ValueError(f"Failed to process feed: {e}")

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

        # Get published date - normalize to ISO format for consistent database queries
        published_date = None
        for date_field in ['published', 'updated', 'created']:
            # First try the parsed struct_time (preferred - already normalized)
            if entry.get(f'{date_field}_parsed'):
                try:
                    parsed = entry.get(f'{date_field}_parsed')
                    # feedparser's *_parsed is already UTC. mktime() reads a
                    # struct_time as local time, so on a CEST server every
                    # feed date landed one or two hours early.
                    published_date = datetime.fromtimestamp(
                        calendar.timegm(parsed), tz=timezone.utc).isoformat()
                    break
                except:
                    pass
            # Fallback to raw string and normalize it
            if entry.get(date_field):
                raw_date = entry.get(date_field)
                # Try to parse and normalize the date
                parsed_dt = self._parse_date(raw_date)
                if parsed_dt:
                    published_date = parsed_dt.isoformat()
                else:
                    # Keep raw string as last resort (shouldn't happen often)
                    published_date = raw_date
                break

        if not published_date:
            published_date = datetime.now(timezone.utc).isoformat()

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
            'url': url,
            'source': source,
            'topic': topic,
            'raw_data': {
                'feed_url': feed.href if hasattr(feed, 'href') else '',
                'feed_title': feed.feed.get('title', ''),
                'entry_id': entry.get('id', url),
                'tags': tags,
                'source_name': source
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
                        'User-Agent': 'AunooAI RSS Collector/1.0',
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
