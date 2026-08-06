import asyncio
import os
import re
import logging
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .base_collector import ArticleCollector
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


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

            # Note: Date filtering (from_date/to_date) is disabled due to API bug
            # The server expects datetime objects but the HTTP API can only pass strings
            # Workaround: NewsFirehose returns recent articles by default (sorted by relevance)
            # Once the API is fixed, uncomment the following:
            #
            # if timeframe:
            #     from_dt = datetime.now() - timedelta(hours=timeframe)
            #     params["from_date"] = from_dt.strftime("%Y-%m-%d")
            # elif start_date:
            #     if isinstance(start_date, datetime):
            #         params["from_date"] = start_date.strftime("%Y-%m-%d")
            #     else:
            #         params["from_date"] = str(start_date)[:10]
            # if end_date:
            #     if isinstance(end_date, datetime):
            #         params["to_date"] = end_date.strftime("%Y-%m-%d")
            #     else:
            #         params["to_date"] = str(end_date)[:10]

            logger.debug(f"NewsFirehose /v1/search params: {params}")

            # Set up headers with API key
            headers = {
                "X-API-Key": self.api_key,
                "Accept": "application/json"
            }

            # The server's published_at sort is pathological for rare terms: it
            # walks the recency index checking every row against the tsquery, so
            # a query with few matches (a niche brand name) runs for minutes while
            # a common term returns instantly. Measured 2026-08-06: q=Solumina
            # answered in 63ms with sort_by=relevance and hung past 130s with
            # sort_by=published_at — every search for the iBASEt group hit the
            # monitor's 120s timeout, and the group never collected an article.
            # So newest-first gets a short budget and falls back to relevance
            # ranking, which always answers; the client-side date filter below
            # keeps the recency guarantee either way.
            async def _fetch(fetch_params, timeout_seconds):
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        f"{self.base_url}/v1/search",
                        params=fetch_params,
                        headers=headers
                    ) as response:
                        if response.status != 200:
                            logger.error(f"NewsFirehose HTTP ERROR: status={response.status}")
                            try:
                                if 'json' in response.content_type:
                                    logger.error(f"Error Response: {await response.json()}")
                                else:
                                    logger.error(f"Error Response: {(await response.text())[:500]}...")
                            except Exception as parse_error:
                                logger.error(f"Could not parse error response: {parse_error}")
                            return None
                        try:
                            return await response.json()
                        except Exception as json_error:
                            logger.error(f"NewsFirehose JSON parse error: {json_error}")
                            return None

            if params["sort_by"] == "published_at":
                try:
                    data = await _fetch(params, 20)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"NewsFirehose published_at sort timed out after 20s for "
                        f"'{normalized_query[:60]}' — retrying with relevance sort"
                    )
                    data = await _fetch({**params, "sort_by": "relevance"}, 60)
            else:
                data = await _fetch(params, 60)

            if data is None:
                return []

            self.requests_today += 1

            articles = data.get("articles", [])
            total = data.get("total_results", len(articles))
            logger.info(f"NewsFirehose returned {len(articles)} articles (total: {total}) for query '{query}'")

            # Client-side date filtering (API date filtering is broken)
            # Filter to only keep articles from the last N days. 30 days is
            # a floor, not a ceiling: the caller's start_date widens the
            # window but never narrows it, so a group with a deliberately
            # long search_date_range (backfilling a low-volume brand) gets
            # its older coverage, while every group left on the 7-day
            # default keeps the 30 days it collects today.
            max_age_days = 30  # Extended to 30 days since NewsFirehose may have stale index
            if start_date is not None:
                requested_days = (datetime.now() - start_date).days
                max_age_days = max(max_age_days, requested_days)
            cutoff_date = datetime.now() - timedelta(days=max_age_days)

            filtered_articles = []
            oldest_date = None
            newest_date = None

            for article in articles:
                pub_date_str = article.get('publishedAt', '')
                if pub_date_str:
                    try:
                        # Parse ISO format date
                        if 'T' in pub_date_str:
                            pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00').replace('+00:00', ''))
                        else:
                            pub_date = datetime.strptime(pub_date_str[:10], '%Y-%m-%d')

                        # Track date range for logging
                        if oldest_date is None or pub_date < oldest_date:
                            oldest_date = pub_date
                        if newest_date is None or pub_date > newest_date:
                            newest_date = pub_date

                        if pub_date >= cutoff_date:
                            filtered_articles.append(article)
                    except (ValueError, TypeError) as e:
                        # If we can't parse date, include the article
                        filtered_articles.append(article)
                else:
                    # No date, include the article
                    filtered_articles.append(article)

            if len(filtered_articles) < len(articles):
                date_range = f"API returned dates: {oldest_date.strftime('%Y-%m-%d') if oldest_date else 'N/A'} to {newest_date.strftime('%Y-%m-%d') if newest_date else 'N/A'}"
                logger.info(f"📅 Date filter: kept {len(filtered_articles)}/{len(articles)} from last {max_age_days} days. {date_range}")

            return [self._format_article(article, topic) for article in filtered_articles]

        except aiohttp.ClientError as e:
            logger.error(f"NewsFirehose network error: {type(e).__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"NewsFirehose unexpected error: {type(e).__name__}: {e}")
            return []

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
