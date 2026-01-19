"""
URL Lookup Service for Auspex.

Provides URL lookup functionality with prioritized search:
1. Current topic in internal database
2. All topics in internal database
3. External Google PSE search
4. Optional Firecrawl full content fetch
"""

import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from app.database import get_database_instance
from app.services.url_detector import normalize_url

logger = logging.getLogger(__name__)


@dataclass
class UrlLookupResult:
    """Result of a URL lookup operation."""
    url: str
    found: bool
    source: str  # 'current_topic', 'other_topic', 'external_search', 'firecrawl', 'not_found'
    topic: Optional[str] = None
    article_data: Optional[Dict] = None
    external_results: Optional[List[Dict]] = None
    firecrawl_content: Optional[str] = None
    message: str = ""


class UrlLookupService:
    """
    Service for looking up URLs in the database and externally.

    Lookup priority:
    1. Current topic (if specified)
    2. All topics in database
    3. Google PSE for web search
    4. Firecrawl for full content (if API key configured)
    """

    def __init__(self):
        self.db = get_database_instance()
        self._google_provider = None
        self._firecrawl_app = None

    def _get_google_provider(self):
        """Lazy load Google search provider."""
        if self._google_provider is None:
            try:
                from app.services.external_data.google_search import get_google_search_provider
                self._google_provider = get_google_search_provider()
            except Exception as e:
                logger.warning(f"Could not load Google search provider: {e}")
        return self._google_provider

    def _get_firecrawl_app(self):
        """Lazy load Firecrawl app if API key is configured."""
        if self._firecrawl_app is None:
            firecrawl_key = (
                os.environ.get("PROVIDER_FIRECRAWL_KEY") or
                os.environ.get("FIRECRAWL_API_KEY")
            )
            if firecrawl_key:
                try:
                    from firecrawl import FirecrawlApp
                    self._firecrawl_app = FirecrawlApp(api_key=firecrawl_key)
                    logger.info("Firecrawl app initialized for URL lookup")
                except Exception as e:
                    logger.warning(f"Could not initialize Firecrawl: {e}")
        return self._firecrawl_app

    async def lookup_url(
        self,
        url: str,
        current_topic: Optional[str] = None,
        include_external: bool = True,
        include_firecrawl: bool = True
    ) -> UrlLookupResult:
        """
        Look up a URL with prioritized search.

        Args:
            url: The URL to look up
            current_topic: Current topic context (checked first)
            include_external: Whether to search externally if not found locally
            include_firecrawl: Whether to use Firecrawl for full content

        Returns:
            UrlLookupResult with lookup details
        """
        normalized_url = normalize_url(url)
        logger.info(f"Looking up URL: {url} (normalized: {normalized_url})")

        # Step 1: Check current topic
        if current_topic and current_topic != '__all__':
            result = self._lookup_in_topic(url, current_topic)
            if result:
                return UrlLookupResult(
                    url=url,
                    found=True,
                    source='current_topic',
                    topic=current_topic,
                    article_data=result,
                    message=f"Found article in current topic '{current_topic}'"
                )

        # Step 2: Check all topics
        result = self._lookup_all_topics(url)
        if result:
            found_topic = result.get('topic', 'Unknown')
            topic_msg = f"Found article in topic '{found_topic}'" if found_topic != current_topic else "Found article"
            return UrlLookupResult(
                url=url,
                found=True,
                source='other_topic' if found_topic != current_topic else 'current_topic',
                topic=found_topic,
                article_data=result,
                message=topic_msg
            )

        # Step 3: External Google search
        if include_external:
            external_results = await self._search_external(url)
            if external_results:
                return UrlLookupResult(
                    url=url,
                    found=True,
                    source='external_search',
                    external_results=external_results,
                    message="URL not in database. Found related information via web search."
                )

        # Step 4: Firecrawl full content
        if include_firecrawl:
            firecrawl_content = await self._fetch_with_firecrawl(url)
            if firecrawl_content:
                return UrlLookupResult(
                    url=url,
                    found=True,
                    source='firecrawl',
                    firecrawl_content=firecrawl_content,
                    message="URL not in database. Fetched full content directly."
                )

        # Not found anywhere
        return UrlLookupResult(
            url=url,
            found=False,
            source='not_found',
            message="URL not found in database and could not be fetched externally."
        )

    def _lookup_in_topic(self, url: str, topic: str) -> Optional[Dict]:
        """Look up URL in a specific topic."""
        try:
            article = self.db.get_article_by_url(url)
            if article and article.get('topic') == topic:
                return dict(article)
            return None
        except Exception as e:
            logger.error(f"Error looking up URL in topic: {e}")
            return None

    def _lookup_all_topics(self, url: str) -> Optional[Dict]:
        """Look up URL across all topics."""
        try:
            article = self.db.get_article_by_url(url)
            if article:
                return dict(article)
            return None
        except Exception as e:
            logger.error(f"Error looking up URL in all topics: {e}")
            return None

    async def _search_external(self, url: str) -> Optional[List[Dict]]:
        """Search for information about the URL using Google PSE."""
        provider = self._get_google_provider()
        if not provider or not provider.is_available():
            logger.info("Google search provider not available for URL lookup")
            return None

        try:
            # Search for the URL or its domain
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc

            # Create search query
            search_query = f'site:{domain} OR "{url}"'

            results = await provider._search(search_query, limit=5, days_back=365)
            if results:
                return [
                    {
                        'title': r.get('title', ''),
                        'url': r.get('link', ''),
                        'snippet': r.get('snippet', ''),
                        'source': 'Google Search'
                    }
                    for r in results
                ]
            return None
        except Exception as e:
            logger.error(f"Error in external URL search: {e}")
            return None

    async def _fetch_with_firecrawl(self, url: str) -> Optional[str]:
        """Fetch full content using Firecrawl."""
        firecrawl = self._get_firecrawl_app()
        if not firecrawl:
            logger.info("Firecrawl not configured for URL lookup")
            return None

        try:
            import asyncio
            from fastapi.concurrency import run_in_threadpool

            # Run Firecrawl in thread pool since it's blocking
            scrape_result = await run_in_threadpool(
                lambda: firecrawl.scrape(url, formats=["markdown"])
            )

            if scrape_result and isinstance(scrape_result, dict):
                # Handle both old and new Firecrawl response formats
                if 'data' in scrape_result:
                    data = scrape_result['data']
                    return data.get('markdown') or data.get('content', '')
                else:
                    return scrape_result.get('markdown') or scrape_result.get('content', '')

            return None
        except Exception as e:
            logger.error(f"Error fetching URL with Firecrawl: {e}")
            return None

    def format_lookup_context(self, result: UrlLookupResult) -> str:
        """
        Format a URL lookup result as context for the LLM.

        Args:
            result: The URL lookup result

        Returns:
            Formatted context string
        """
        if not result.found:
            return f"[URL LOOKUP] {result.url}: {result.message}"

        parts = [f"[URL LOOKUP] {result.url}"]
        parts.append(f"Status: {result.message}")

        if result.source in ('current_topic', 'other_topic') and result.article_data:
            article = result.article_data
            parts.append(f"\nArticle Found in Database:")
            parts.append(f"- Title: {article.get('title', 'Unknown')}")
            parts.append(f"- Source: {article.get('news_source') or article.get('source', 'Unknown')}")
            parts.append(f"- Topic: {article.get('topic', 'Unknown')}")
            if article.get('submission_date'):
                parts.append(f"- Date: {article.get('submission_date')}")
            if article.get('summary'):
                summary = article.get('summary', '')
                if len(summary) > 500:
                    summary = summary[:500] + "..."
                parts.append(f"- Summary: {summary}")
            if article.get('sentiment'):
                parts.append(f"- Sentiment: {article.get('sentiment')}")

        elif result.source == 'external_search' and result.external_results:
            parts.append(f"\nWeb Search Results:")
            for i, r in enumerate(result.external_results[:3], 1):
                parts.append(f"{i}. [{r.get('title', 'Untitled')}]({r.get('url', '')})")
                if r.get('snippet'):
                    parts.append(f"   {r.get('snippet')}")

        elif result.source == 'firecrawl' and result.firecrawl_content:
            content = result.firecrawl_content
            # Truncate if too long
            if len(content) > 3000:
                content = content[:3000] + "\n\n[Content truncated...]"
            parts.append(f"\nFetched Content:\n{content}")

        return "\n".join(parts)


async def lookup_urls_in_message(
    urls: List[str],
    current_topic: Optional[str] = None,
    include_external: bool = True,
    include_firecrawl: bool = True
) -> str:
    """
    Convenience function to look up multiple URLs and format results.

    Args:
        urls: List of URLs to look up
        current_topic: Current topic context
        include_external: Whether to include external search
        include_firecrawl: Whether to include Firecrawl

    Returns:
        Formatted context string for all URLs
    """
    service = UrlLookupService()
    results = []

    for url in urls:
        result = await service.lookup_url(
            url,
            current_topic=current_topic,
            include_external=include_external,
            include_firecrawl=include_firecrawl
        )
        formatted = service.format_lookup_context(result)
        results.append(formatted)

    return "\n\n".join(results)


# Singleton instance
_url_lookup_service: Optional[UrlLookupService] = None


def get_url_lookup_service() -> UrlLookupService:
    """Get URL lookup service singleton."""
    global _url_lookup_service
    if _url_lookup_service is None:
        _url_lookup_service = UrlLookupService()
    return _url_lookup_service
