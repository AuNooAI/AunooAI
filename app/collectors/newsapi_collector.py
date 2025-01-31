import aiohttp
from datetime import datetime
from typing import List, Dict, Optional
from .base_collector import ArticleCollector
import logging
import os

logger = logging.getLogger(__name__)

class NewsAPICollector(ArticleCollector):
    """NewsAPI article collector implementation."""
    
    def __init__(self):
        self.api_key = os.getenv('PROVIDER_NEWSAPI_KEY')
        if not self.api_key:
            logger.error("NewsAPI key not found in environment")
            raise ValueError("NewsAPI key not configured")
            
        self.base_url = "https://newsapi.org/v2"

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Implement abstract method from ArticleCollector"""
        try:
            article = await self.get_article(url)
            if article:
                return {
                    'content': article['raw_data'].get('content', ''),
                    'title': article['title'],
                    'source': article['source'],
                    'publication_date': article['published_date']
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching article content: {str(e)}")
            return None

    async def search_articles(
        self,
        query: str,
        topic: Optional[str] = None,
        max_results: int = 10,
        start_date: Optional[str] = None,
        search_fields: Optional[str] = None,
        language: Optional[str] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict]:
        try:
            params = {
                'q': query,
                'apiKey': self.api_key,
                'pageSize': max_results,
                'language': language or 'en',
                'sortBy': sort_by or 'publishedAt'
            }

            if search_fields:
                params['searchIn'] = search_fields

            if start_date:
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    except ValueError:
                        logger.warning(f"Invalid start_date format: {start_date}")
                        start_date = None
                
                if start_date:
                    params['from'] = start_date.strftime('%Y-%m-%d')

            # Handle topic/category mapping
            valid_categories = ['business', 'entertainment', 'general', 'health', 
                              'science', 'sports', 'technology']
            if topic and topic.lower() in valid_categories:
                params['category'] = topic.lower()

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/everything",
                    params=params
                ) as response:
                    data = await response.json()
                    
                    if response.status != 200:
                        error_msg = data.get('message', 'Unknown error')
                        logger.error(f"NewsAPI error: {error_msg}")
                        return []

                    articles = data.get("articles", [])
                    
                    # Transform to our standard format, maintaining compatibility
                    return [{
                        'title': article.get('title', ''),
                        'summary': article.get('description', '') or '',
                        'url': article.get('url', ''),  # Keep url for new code
                        'uri': article.get('url', ''),  # Keep uri for old code
                        'source': article.get('source', {}).get('name', ''),
                        'news_source': article.get('source', {}).get('name', ''),  # For compatibility
                        'published_date': article.get('publishedAt', ''),
                        'publication_date': article.get('publishedAt', ''),  # For compatibility
                        'raw_data': {
                            'author': article.get('author'),
                            'url_to_image': article.get('urlToImage'),
                            'content': article.get('content')
                        }
                    } for article in articles if article.get('url')]

        except Exception as e:
            logger.error(f"Error searching NewsAPI: {str(e)}")
            return []

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