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

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_by: str = "publishedAt",
        language: str = "en",
        search_in: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[Dict]:
        """Search NewsAPI articles using the /everything endpoint."""
        try:
            # Build parameters according to NewsAPI documentation
            params = {
                "apiKey": self.api_key,
                "q": query,
                "language": language,
                "sortBy": sort_by,
                "pageSize": min(max_results, 100),  # NewsAPI limit is 100
            }

            # Add optional parameters
            if search_in:
                params["searchIn"] = ",".join(search_in)  # title,description,content
            if sources:
                params["sources"] = ",".join(sources)
            if domains:
                params["domains"] = ",".join(domains)
            if exclude_domains:
                params["excludeDomains"] = ",".join(exclude_domains)
            if start_date:
                params["from"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["to"] = end_date.strftime("%Y-%m-%d")

            logger.debug(f"NewsAPI search params: {params}")

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/everything", params=params) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        logger.error(f"NewsAPI error: {error_data}")
                        return []
                    
                    data = await response.json()
                    logger.info(f"NewsAPI returned {len(data.get('articles', []))} articles")
                    
                    return [self._format_article(article, topic) for article in data.get("articles", [])]

        except Exception as e:
            logger.error(f"Error searching NewsAPI: {str(e)}")
            return []

    def _format_article(self, article: Dict, topic: str) -> Dict:
        """Format NewsAPI article to standard format."""
        return {
            'title': article['title'],
            'summary': article['description'] or article['content'] or "",
            'authors': [article['author']] if article['author'] else [],
            'published_date': article['publishedAt'],
            'url': article['url'],
            'source': 'newsapi',
            'topic': topic,
            'raw_data': {
                'source_name': article['source']['name'],
                'url_to_image': article.get('urlToImage'),
                'content': article.get('content'),
            }
        }

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch article content from NewsAPI."""
        try:
            # Search for the specific article by URL
            params = {
                "apiKey": self.api_key,
                "qInTitle": url,  # Search by exact URL
                "language": "en"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/everything", params=params) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    articles = data.get("articles", [])
                    
                    if not articles:
                        return None

                    article = articles[0]  # Get the first matching article
                    return {
                        'title': article['title'],
                        'content': article['content'] or article['description'] or "",
                        'authors': [article['author']] if article['author'] else [],
                        'published_date': article['publishedAt'],
                        'url': article['url'],
                        'source': 'newsapi',
                        'raw_data': {
                            'source_name': article['source']['name'],
                            'url_to_image': article.get('urlToImage'),
                            'description': article.get('description')
                        }
                    }

        except Exception as e:
            logger.error(f"Error fetching article from NewsAPI: {str(e)}")
            return None 