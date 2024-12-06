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
        self.api_key = os.getenv('NEWSAPI_KEY')
        if not self.api_key:
            logger.error("NewsAPI key not found in environment")
            raise ValueError("NewsAPI key not configured")
            
        self.base_url = "https://newsapi.org/v2"
        
        # Mapping topics to NewsAPI keywords/categories
        self.topic_mapping = {
            "AI and Machine Learning": {
                "keywords": ["artificial intelligence", "machine learning", "AI", "neural network", 
                           "deep learning", "robotics", "computer vision", "natural language processing"],
                "domains": ["techcrunch.com", "wired.com", "venturebeat.com", "technologyreview.com"]
            },
            "Cloud Computing": {
                "keywords": ["cloud computing", "cloud infrastructure", "cloud services", 
                           "cloud platform", "cloud security", "cloud storage"],
                "domains": ["cloudcomputing-news.net", "zdnet.com", "infoworld.com"]
            }
        }

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Search NewsAPI articles."""
        try:
            topic_config = self.topic_mapping.get(topic, {})
            if not topic_config:
                logger.warning(f"No NewsAPI configuration for topic: {topic}")
                return []

            # Build the query
            topic_keywords = " OR ".join(topic_config["keywords"])
            search_query = f"({query}) AND ({topic_keywords})"
            
            # Build parameters
            params = {
                "apiKey": self.api_key,
                "q": search_query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max_results,
                "domains": ",".join(topic_config["domains"])
            }

            if start_date:
                params["from"] = start_date.isoformat()
            if end_date:
                params["to"] = end_date.isoformat()

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/everything", params=params) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        logger.error(f"NewsAPI error: {error_data}")
                        return []
                    
                    data = await response.json()
                    articles = []

                    for article in data.get("articles", []):
                        articles.append({
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
                        })

                    return articles

        except Exception as e:
            logger.error(f"Error searching NewsAPI: {str(e)}")
            return []

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