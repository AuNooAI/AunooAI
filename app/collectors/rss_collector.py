import feedparser
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from .base_collector import ArticleCollector
import logging
from email.utils import parsedate_to_datetime
from time import mktime

logger = logging.getLogger(__name__)


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

        # Get published date - prefer parsed version, fall back to raw string
        published_date = None
        for date_field in ['published', 'updated', 'created']:
            # First try the pre-parsed struct_time (more reliable)
            if entry.get(f'{date_field}_parsed'):
                try:
                    parsed = entry.get(f'{date_field}_parsed')
                    published_date = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc).isoformat()
                    break
                except:
                    pass
            # Fall back to raw string and parse it
            if entry.get(date_field):
                raw_date = entry.get(date_field)
                # Try to parse and normalize to ISO format
                parsed_dt = self._parse_date(raw_date)
                if parsed_dt:
                    published_date = parsed_dt.isoformat()
                else:
                    # Last resort: use raw string (may cause issues)
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
