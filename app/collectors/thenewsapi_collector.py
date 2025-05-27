import os
import logging
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, date
from .base_collector import ArticleCollector
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class TheNewsAPICollector(ArticleCollector):
    """Collector for TheNewsAPI service."""

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_THENEWSAPI_API_KEY') or os.getenv('PROVIDER_THENEWSAPI_KEY')
        if not self.api_key:
            logger.error("TheNewsAPI key not found in environment")
            raise ValueError("TheNewsAPI key not configured")
        self.base_url = "https://api.thenewsapi.com/v1/news"
        self.requests_today = 0
        self.last_request_date = date.today()
        self.daily_limit = 100  # TheNewsAPI free tier limit

    def _check_rate_limit(self) -> bool:
        """Check if we've hit the daily rate limit."""
        current_date = date.today()
        
        # Reset counter if it's a new day
        if current_date > self.last_request_date:
            self.requests_today = 0
            self.last_request_date = current_date
            
        return self.requests_today < self.daily_limit

    def _increment_request_count(self):
        """Increment the request counter."""
        self.requests_today += 1
        logger.debug(f"TheNewsAPI requests today: {self.requests_today}")

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
        """Search articles using TheNewsAPI /all endpoint.
        
        Args:
            query: Search query string
            topic: Topic for categorization
            max_results: Maximum number of results to return (default: 10)
            start_date: Start date for article search
            end_date: End date for article search
            language: Language code (default: "en")
            locale: Country code for news sources
            domains: List of domains to include
            exclude_domains: List of domains to exclude
            sort_by: Sort order ("relevancy" or "published_at")
            source_ids: List of source IDs to include
            exclude_source_ids: List of source IDs to exclude
            categories: List of categories to filter by
            exclude_categories: List of categories to exclude
            search_fields: List of fields to search in
            page: Page number for pagination
        """
        if not self._check_rate_limit():
            logger.warning("TheNewsAPI daily rate limit reached")
            return []

        try:
            # Build parameters according to TheNewsAPI documentation
            params = {
                "api_token": self.api_key,
                "search": query,
                "language": language,
                "limit": min(max_results, 100),  # API limit is 100
                "page": page
            }

            # Add optional parameters
            if locale:
                params["locale"] = locale
            if domains:
                params["domains"] = ",".join(domains)
            if exclude_domains:
                params["exclude_domains"] = ",".join(exclude_domains)
            if start_date:
                params["published_after"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["published_before"] = end_date.strftime("%Y-%m-%d")
            if sort_by:
                params["sort"] = sort_by
            if source_ids:
                params["source_ids"] = ",".join(source_ids)
            if exclude_source_ids:
                params["exclude_source_ids"] = ",".join(exclude_source_ids)
            if categories:
                params["categories"] = ",".join(categories)
            if exclude_categories:
                params["exclude_categories"] = ",".join(exclude_categories)
            if search_fields:
                params["search_fields"] = ",".join(search_fields)

            logger.debug(f"TheNewsAPI search params: {params}")

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/all", params=params) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        logger.error(f"TheNewsAPI error: {error_data}")
                        return []
                    
                    self._increment_request_count()
                    data = await response.json()
                    articles = data.get("data", [])
                    logger.info(f"TheNewsAPI returned {len(articles)} articles")
                    
                    return [self._format_article(article, topic) for article in articles]

        except Exception as e:
            logger.error(f"Error searching TheNewsAPI: {str(e)}")
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch full article content from TheNewsAPI."""
        try:
            params = {
                'api_token': self.api_key,
                'url': url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/all", params=params) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    articles = data.get("data", [])
                    if not articles:
                        return None
                    
                    article = articles[0]
                    
                    # Extract source name using the same logic as _format_article
                    source = article.get('source', {})
                    source_name = source.get('name', '') if isinstance(source, dict) else str(source)
                    
                    # If source_name is empty, try to extract from URL
                    if not source_name and article.get('url'):
                        parsed_url = urlparse(article['url'])
                        source_name = parsed_url.netloc.replace('www.', '')
                    
                    return {
                        'title': article['title'],
                        'content': article.get('snippet', ''),
                        'authors': [],  # TheNewsAPI doesn't provide author info
                        'published_date': article['published_at'],
                        'url': article['url'],
                        'source': source_name,
                        'raw_data': {
                            'source': article.get('source'),
                            'image_url': article.get('image_url'),
                            'keywords': article.get('keywords', []),
                            'categories': article.get('categories', []),
                            'locale': article.get('locale')
                        }
                    }

        except Exception as e:
            logger.error(f"Error fetching article from TheNewsAPI: {str(e)}")
            return None

    def _format_article(self, article: Dict, topic: str) -> Dict:
        """Format TheNewsAPI article data to standard format."""
        # Try to extract the true media source name
        source = article.get('source', {})
        source_name = ''
        
        # Log the raw source data for debugging
        logger.debug(f"Raw source data for article '{article.get('title', '')}': {source}")
        
        if isinstance(source, dict):
            source_name = source.get('name', '').strip()
        elif isinstance(source, str):
            source_name = source.strip()

        # Fallback: extract domain from URL if source_name is empty
        if not source_name and article.get('url'):
            from urllib.parse import urlparse
            parsed_url = urlparse(article['url'])
            source_name = parsed_url.netloc.replace('www.', '')
            
        # Log the extracted source name
        logger.debug(f"Extracted source name for article '{article.get('title', '')}': {source_name}")

        return {
            'title': article['title'],
            'summary': article.get('description', '') or article.get('snippet', ''),
            'authors': [],  # TheNewsAPI doesn't provide author info
            'published_date': article['published_at'],
            'url': article['url'],
            'source': source_name,
            'topic': topic,
            'raw_data': {
                'source': source,
                'image_url': article.get('image_url'),
                'keywords': article.get('keywords', []),
            }
        } 