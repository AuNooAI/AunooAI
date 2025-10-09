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
        self.api_key = os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY')
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
            logger.debug("Initializing request counter")

            row = self.db.facade.get_request_count_for_today()
            today = datetime.now().date().isoformat()

            logger.debug(f"Current status row: {row}, today: {today}")

            if row:
                requests_today, last_reset = row

                if not last_reset or last_reset < today:
                    # Reset counter for new day
                    self.requests_today = 0
                    self.db.facade.reset_keyword_monitoring_counter((today,))
                    logger.debug("Reset counter for new day")
                else:
                    self.requests_today = requests_today
                    logger.debug(f"Using existing count: {requests_today}")
            else:
                self.requests_today = 0
                logger.debug("No existing count found, starting at 0")
                
        except Exception as e:
            logger.error(f"Error initializing request counter: {str(e)}")
            self.requests_today = 0

    def _update_request_counter(self):
        """Update request counter in the database after a successful API call"""
        try:
            # Increment the in-memory counter
            self.requests_today += 1
            
            # Update in database
            today = datetime.now().date().isoformat()

            # Make sure we have a row in the status table with today's date
            self.db.facade.stamp_keyword_monitor_status_table_with_todays_date((self.requests_today, today))

            logger.debug(f"Updated NewsAPI request count to {self.requests_today}")

            # Check if we're at or near the limit
            # Default limit is 100 (NewsAPI free tier)
            daily_limit = 100

            # Get configured limit if available
            limit_row = self.db.facade.get_keyword_monitor_status_daily_request_limit()
            if limit_row and limit_row[0]:
                daily_limit = limit_row[0]

            if self.requests_today >= daily_limit:
                logger.warning(f"NewsAPI request limit reached: {self.requests_today}/{daily_limit}")
        except Exception as e:
            logger.error(f"Error updating request counter: {str(e)}")

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
            logger.info(f"NewsAPI search request - query: '{query}', topic: '{topic}', requests_today: {self.requests_today}")
            
            # Map field abbreviations to their full names
            search_field_mapping = {
                'title': 'title',
                'desc': 'description',
                'description': 'description',
                'content': 'content'
            }
            
            # Set up base params
            params = {
                'apiKey': self.api_key,
                'q': query,
                'page': page,
                'pageSize': max_results,
            }
            
            # Add language if provided
            if language:
                params['language'] = language
            
            # Add sortBy if provided
            if sort_by:
                params['sortBy'] = sort_by

            # Add optional parameters if provided
            if search_fields:
                # Handle string input (comma-separated list)
                if isinstance(search_fields, str):
                    search_fields = search_fields.split(',')
                
                # Map any abbreviated fields to their full names
                mapped_fields = [
                    search_field_mapping.get(field.lower().strip(), field.strip())
                    for field in search_fields
                ]
                # Filter out any invalid fields
                valid_fields = [
                    field for field in mapped_fields
                    if field in ['title', 'description', 'content']
                ]
                if valid_fields:
                    params['searchIn'] = ','.join(valid_fields)
                    logger.debug(f"Using searchIn parameter: {params['searchIn']}")

            if domains:
                params['domains'] = ','.join(domains)

            if exclude_domains:
                params['excludeDomains'] = ','.join(exclude_domains)

            # Handle start_date
            if start_date:
                if isinstance(start_date, str):
                    start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                params['from'] = start_date.strftime('%Y-%m-%d')
                logger.debug(f"Using from date: {params['from']}")

            # Handle end_date
            if end_date:
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                params['to'] = end_date.strftime('%Y-%m-%d')
                logger.debug(f"Using to date: {params['to']}")

            # Add more debug logging
            logger.debug(f"Making NewsAPI request with params: {params}")

            # Handle topic/category mapping
            valid_categories = ['business', 'entertainment', 'general', 'health', 
                              'science', 'sports', 'technology']
            if topic and topic.lower() in valid_categories:
                params['category'] = topic.lower()

            logger.info(f"Making NewsAPI request: query='{query}', requests_today={self.requests_today}")
            
            # Update request counter in the database
            self._update_request_counter()
            
            # Make the API request
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/everything", params=params) as response:
                    status = response.status
                    data = await response.json()
                    
                    # Log API response for debugging
                    logger.debug(f"NewsAPI response status: {status}")
                    logger.debug(f"NewsAPI response: {data.get('status')}, total results: {data.get('totalResults', 0)}")
                    
                    if status == 200 and data.get('status') == 'ok':
                        # Successful response
                        articles = data.get('articles', [])
                        logger.info(f"NewsAPI returned {len(articles)} articles for query '{query}'")
                        
                        if len(articles) == 0:
                            logger.warning(f"NewsAPI returned 0 articles for query '{query}' - check search parameters")
                        else:
                            # Log first article for debugging
                            if articles:
                                first_article = articles[0]
                                logger.debug(f"First article: {first_article.get('title')} - {first_article.get('publishedAt')}")
                        
                        # Transform to our standard format, maintaining compatibility
                        return [{
                            'title': article.get('title', ''),
                            'summary': article.get('description', '') or '',
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', 'NewsAPI'),  # Set default source name
                            'authors': [article.get('author')] if article.get('author') else [],
                            'published_date': article.get('publishedAt', ''),
                            'topic': topic,  # Add topic field for auto-ingest pipeline
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
                        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error when calling NewsAPI: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in NewsAPI search: {str(e)}")
            logger.exception("Full exception traceback:")
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