import aiohttp
from datetime import datetime
from typing import List, Dict, Optional
from .base_collector import ArticleCollector
import logging
import os
import json
from app.database import Database

logger = logging.getLogger(__name__)

class NewsAPICollector(ArticleCollector):
    """NewsAPI article collector implementation."""
    
    def __init__(self, db: Database):
        self.api_key = os.getenv('PROVIDER_NEWSAPI_KEY')
        if not self.api_key:
            logger.error("NewsAPI key not found in environment")
            raise ValueError("NewsAPI key not configured")
            
        self.db = db
        self.base_url = "https://newsapi.org/v2"
        self._init_request_counter()
        self.last_request_time = None

    def _init_request_counter(self):
        """Initialize request counter from database"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get today's request count and last reset date
                cursor.execute("""
                    SELECT requests_today, last_reset_date 
                    FROM keyword_monitor_status 
                    WHERE id = 1
                """)
                row = cursor.fetchone()
                today = datetime.now().date().isoformat()
                
                if row:
                    requests_today, last_reset = row
                    
                    if not last_reset or last_reset < today:
                        # Reset counter for new day
                        self.requests_today = 0
                        cursor.execute("""
                            UPDATE keyword_monitor_status 
                            SET requests_today = 0,
                                last_reset_date = ?
                            WHERE id = 1
                        """, (today,))
                        conn.commit()
                    else:
                        self.requests_today = requests_today
                else:
                    self.requests_today = 0
                    
        except Exception as e:
            logger.error(f"Error initializing request counter: {str(e)}")
            self.requests_today = 0

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
        page: int = 1
    ) -> List[Dict]:
        try:
            # Check if we're already at the limit before making request
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT requests_today FROM keyword_monitor_status WHERE id = 1")
                row = cursor.fetchone()
                current_requests = row[0] if row else 0
                
                if current_requests >= 100:  # Hard limit from NewsAPI
                    error_msg = "NewsAPI daily request limit reached (100/100 requests used)"
                    cursor.execute("""
                        UPDATE keyword_monitor_status 
                        SET last_error = ?,
                            requests_today = 100
                        WHERE id = 1
                    """, (error_msg,))
                    conn.commit()
                    raise ValueError(error_msg)

            params = {
                'q': query,
                'apiKey': self.api_key,
                'pageSize': max_results,
                'language': language,
                'sortBy': sort_by or 'publishedAt',
                'page': page
            }

            # Add optional parameters if provided
            if search_fields:
                params['searchIn'] = ','.join(search_fields)

            if domains:
                params['domains'] = ','.join(domains)

            if exclude_domains:
                params['excludeDomains'] = ','.join(exclude_domains)

            # Handle start_date
            if start_date:
                params['from'] = start_date.strftime('%Y-%m-%d')

            # Handle end_date
            if end_date:
                params['to'] = end_date.strftime('%Y-%m-%d')

            # Handle topic/category mapping
            valid_categories = ['business', 'entertainment', 'general', 'health', 
                              'science', 'sports', 'technology']
            if topic and topic.lower() in valid_categories:
                params['category'] = topic.lower()

            logger.info(f"Making NewsAPI request: query='{query}', requests_today={self.requests_today}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/everything",
                    params=params
                ) as response:
                    data = await response.json()
                    status = response.status
                    
                    # Log the complete API response for debugging
                    logger.info(
                        f"NewsAPI response: status={status}, "
                        f"headers={dict(response.headers)}, "
                        f"data={json.dumps(data, indent=2)}"
                    )
                    
                    if status == 200:
                        # Track successful request
                        self.requests_today += 1
                        
                        # Update request count in database
                        with self.db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE keyword_monitor_status 
                                SET requests_today = ?,
                                    last_check_time = ?
                                WHERE id = 1
                            """, (self.requests_today, datetime.now().isoformat()))
                            conn.commit()
                        
                        articles = data.get("articles", [])
                        logger.info(
                            f"NewsAPI search successful: found {len(articles)} articles "
                            f"for query '{query}' (request {self.requests_today}/100)"
                        )
                        
                        # Transform to our standard format, maintaining compatibility
                        return [{
                            'title': article.get('title', ''),
                            'summary': article.get('description', '') or '',
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', 'NewsAPI'),  # Set default source name
                            'authors': [article.get('author')] if article.get('author') else [],
                            'published_date': article.get('publishedAt', ''),
                            'raw_data': {
                                'url_to_image': article.get('urlToImage'),
                                'content': article.get('content')
                            }
                        } for article in articles if article.get('url')]

                    elif status == 429:
                        error_msg = data.get('message', 'Unknown error')
                        logger.error(f"NewsAPI rate limit exceeded: {error_msg}")
                        raise ValueError(f"Rate limit exceeded: {error_msg}")
                    
                    else:
                        error_msg = data.get('message', 'Unknown error')
                        error_code = data.get('code', 'unknown')
                        
                        logger.error(
                            f"NewsAPI error: status={status}, code={error_code}, "
                            f"message={error_msg}, query='{query}'"
                        )
                        return []

        except ValueError as e:
            if "Rate limit exceeded" in str(e) or "limit reached" in str(e):
                # Always ensure the counter shows 100 when rate limited
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE keyword_monitor_status 
                        SET requests_today = 100,
                            last_error = ?
                        WHERE id = 1
                    """, (str(e),))
                    conn.commit()
                    self.requests_today = 100  # Update in-memory counter too
                raise
            logger.error(f"Error searching NewsAPI: {str(e)}, query='{query}'")
            return []
        except Exception as e:
            logger.error(f"Error searching NewsAPI: {str(e)}, query='{query}'")
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