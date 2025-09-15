import os
import logging
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, date
from .base_collector import ArticleCollector
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class NewsdataCollector(ArticleCollector):
    """Collector for NewsData.io API service."""

    @staticmethod
    def is_configured() -> bool:
        """Check if NewsData.io API key is configured without initializing the collector."""
        api_key = os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY')
        return bool(api_key)

    def __init__(self):
        self.api_key = os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY')
        if not self.api_key:
            logger.error("NewsData.io API key not found in environment")
            raise ValueError("NewsData.io API key not configured")
        self.base_url = "https://newsdata.io/api/1/news"
        self.requests_today = 0
        self.last_request_date = date.today()
        self.daily_limit = 200  # NewsData.io free tier limit

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
        logger.debug(f"NewsData.io requests today: {self.requests_today}")

    def _simplify_query(self, query: str) -> str:
        """Simplify complex boolean queries for NewsData.io API compatibility."""
        try:
            # Remove complex boolean operators that NewsData.io might not support
            # Convert complex queries to simple keyword searches
            simplified = query
            
            # Remove parentheses and complex boolean operators
            simplified = simplified.replace('(', '').replace(')', '')
            simplified = simplified.replace(' | ', ' OR ')  # Convert | to OR
            simplified = simplified.replace(' + ', ' AND ')  # Convert + to AND
            
            # Remove quotes around phrases (NewsData.io might not support quoted phrases)
            simplified = simplified.replace('"', '')
            
            # NewsData.io API is strict - be very conservative with query format
            # Remove all boolean operators completely
            simplified = simplified.replace(' OR ', ' ').replace(' AND ', ' ')
            
            # Extract only the most important keywords
            words = simplified.split()
            keywords = []
            
            # Filter out common words and keep only meaningful terms
            common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
            
            for word in words:
                word = word.strip().lower()
                if (len(word) >= 3 and 
                    word not in common_words and 
                    word.replace('-', '').replace('_', '').isalnum() and  # Alphanumeric only
                    len(keywords) < 2):  # Limit to 2 keywords maximum
                    keywords.append(word)
            
            simplified = ' '.join(keywords)
            
            # Ensure query is not too long
            if len(simplified) > 50:
                simplified = simplified[:47] + "..."
            
            # If no valid keywords found, use a safe fallback
            if not simplified.strip():
                simplified = "news"
            
            logger.debug(f"Simplified query '{query}' to '{simplified}'")
            return simplified
            
        except Exception as e:
            logger.warning(f"Error simplifying query '{query}': {e}")
            # Fallback to first word if simplification fails
            return query.split()[0] if query.split() else "AI"

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = "en",
        country: Optional[str] = None,
        category: Optional[str] = None,
        domain: Optional[List[str]] = None,
        exclude_domain: Optional[List[str]] = None,
        prioritydomain: Optional[str] = None,
        **kwargs
    ) -> List[Dict]:
        """Search articles using NewsData.io API.
        
        Args:
            query: Search query string
            topic: Topic for categorization
            max_results: Maximum number of results to return (default: 10)
            start_date: Start date for article search
            end_date: End date for article search
            language: Language code (default: "en")
            country: Country code for news sources
            category: News category to filter by
            domain: List of domains to include
            exclude_domain: List of domains to exclude
            prioritydomain: Priority domain for news sources
        """
        logger.info(f"NewsData.io search_articles called with query='{query}', topic='{topic}', max_results={max_results}")
        
        if not self._check_rate_limit():
            logger.warning("NewsData.io daily rate limit reached")
            return []

        try:
            # Simplify complex queries for NewsData.io API
            simplified_query = self._simplify_query(query)
            
            # Build parameters according to NewsData.io API documentation
            # Start with minimal required parameters only
            params = {
                "apikey": self.api_key,
            }
            
            # Only add query if it's simple and valid
            if simplified_query and len(simplified_query.strip()) > 0:
                # Ensure query is properly formatted
                clean_query = simplified_query.strip()
                if len(clean_query) <= 512:  # NewsData.io has query length limits
                    params["q"] = clean_query
            
            # Add language only if it's a valid ISO code
            if language and len(language) == 2:
                params["language"] = language
                
            # Add size parameter with conservative limit
            params["size"] = min(max_results, 10)  # Start with smaller size for testing

            # Only add optional parameters if they're properly formatted
            if country and len(country) == 2:  # ISO country codes are 2 characters
                params["country"] = country
            if category and category in ['business', 'entertainment', 'environment', 'food', 'health', 'politics', 'science', 'sports', 'technology', 'top', 'tourism', 'world']:
                params["category"] = category
            if domain and isinstance(domain, list) and len(domain) > 0:
                # Validate domain format
                valid_domains = [d for d in domain if isinstance(d, str) and '.' in d]
                if valid_domains:
                    params["domain"] = ",".join(valid_domains[:5])  # Limit to 5 domains
            if exclude_domain and isinstance(exclude_domain, list) and len(exclude_domain) > 0:
                valid_exclude_domains = [d for d in exclude_domain if isinstance(d, str) and '.' in d]
                if valid_exclude_domains:
                    params["excludedomain"] = ",".join(valid_exclude_domains[:5])
            # NOTE: NewsData.io free tier does NOT support date filtering with from_date/to_date parameters
            # These parameters cause 422 errors, so we'll skip them for now
            # if start_date and isinstance(start_date, datetime):
            #     params["from_date"] = start_date.strftime("%Y-%m-%d")
            # if end_date and isinstance(end_date, datetime):
            #     params["to_date"] = end_date.strftime("%Y-%m-%d")
            
            # Log if date filtering was requested but skipped
            if start_date or end_date:
                logger.info(f"NewsData.io: Date filtering requested but skipped (free tier limitation) - start_date: {start_date}, end_date: {end_date}")

            self._increment_request_count()
            
            # Log the parameters being sent for debugging 422 errors
            logger.info(f"NewsData.io API request - URL: {self.base_url}, Params: {params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        # Get more detailed error information
                        try:
                            error_data = await response.json()
                            error_message = error_data.get('results', {}).get('message', f'HTTP {response.status}')
                            logger.error(f"NewsData.io API error {response.status}: {error_message}")
                        except:
                            logger.error(f"NewsData.io API error: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    # Check for API errors
                    if data.get('status') == 'error':
                        error_message = data.get('results', {}).get('message', 'Unknown error')
                        logger.error(f"NewsData.io API error: {error_message}")
                        return []
                    
                    articles = data.get("results", [])
                    
                    # Format articles to standard format
                    formatted_articles = []
                    for article in articles:
                        formatted_article = self._format_article(article, topic)
                        if formatted_article:
                            formatted_articles.append(formatted_article)
                    
                    logger.info(f"NewsData.io: Retrieved {len(formatted_articles)} articles for query '{query}'")
                    return formatted_articles

        except Exception as e:
            logger.error(f"Error searching articles from NewsData.io: {str(e)}", exc_info=True)
            return []

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch full content of an article by URL.
        
        Note: NewsData.io provides full content in search results, so this method
        is mainly for consistency with the base interface.
        """
        try:
            if not self._check_rate_limit():
                logger.warning("NewsData.io daily rate limit reached")
                return None

            # For NewsData.io, we can try to search for the specific URL
            # This is not ideal but NewsData.io doesn't have a direct URL fetch endpoint
            params = {
                "apikey": self.api_key,
                "qInTitle": "",  # Empty query to get recent articles
                "size": 1
            }
            
            self._increment_request_count()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    articles = data.get("results", [])
                    
                    # Try to find the article with matching URL
                    for article in articles:
                        if article.get('link') == url:
                            return {
                                'title': article.get('title', ''),
                                'content': article.get('content', '') or article.get('description', ''),
                                'source': article.get('source_id', ''),
                                'published_date': article.get('pubDate', ''),
                                'url': article.get('link', ''),
                                'raw_data': article
                            }
                    
                    return None

        except Exception as e:
            logger.error(f"Error fetching article from NewsData.io: {str(e)}")
            return None

    def _format_article(self, article: Dict, topic: str) -> Dict:
        """Format NewsData.io article data to standard format."""
        try:
            # Extract source name
            source_name = article.get('source_id', '')
            if not source_name:
                # Fallback: extract domain from URL
                url = article.get('link', '')
                if url:
                    parsed_url = urlparse(url)
                    source_name = parsed_url.netloc.replace('www.', '')

            # Parse publication date
            pub_date = article.get('pubDate', '')
            published_date = None
            if pub_date:
                try:
                    # NewsData.io returns dates in ISO format
                    published_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                except ValueError:
                    published_date = datetime.now()
            else:
                published_date = datetime.now()

            # Extract keywords from the article
            keywords = article.get('keywords', []) or []
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]

            return {
                'title': article.get('title', ''),
                'summary': article.get('description', ''),
                'content': article.get('content', ''),  # NewsData.io provides full content
                'authors': article.get('creator', []) or [],
                'published_date': published_date,
                'url': article.get('link', ''),
                'source': source_name,
                'topic': topic,
                'raw_data': {
                    'article_id': article.get('article_id'),
                    'source_id': article.get('source_id'),
                    'country': article.get('country', []),
                    'category': article.get('category', []),
                    'language': article.get('language'),
                    'keywords': keywords,
                    'image_url': article.get('image_url'),
                    'video_url': article.get('video_url'),
                    'sentiment': article.get('sentiment'),
                    'duplicate': article.get('duplicate')
                }
            }

        except Exception as e:
            logger.error(f"Error formatting NewsData.io article: {str(e)}")
            return None

    async def test_connection(self) -> bool:
        """Test the connection to NewsData.io API with minimal parameters."""
        try:
            # Use a very simple request to test connectivity
            # Use minimal parameters to avoid 422 errors
            params = {
                "apikey": self.api_key,
                "q": "news",  # Simple, safe query
                "language": "en",
                "size": 1
            }
            
            # Log the test parameters
            logger.info(f"NewsData.io connection test - URL: {self.base_url}, Params: {params}")
            
            self._increment_request_count()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params) as response:
                    logger.info(f"NewsData.io test response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"NewsData.io test response: status={data.get('status')}, results_count={len(data.get('results', []))}")
                        return data.get("status") != "error"
                    else:
                        # Log error details for debugging
                        try:
                            error_data = await response.json()
                            logger.error(f"NewsData.io test failed {response.status}: {error_data}")
                        except:
                            logger.error(f"NewsData.io test failed {response.status}: No JSON response")
                        return False
                    
        except Exception as e:
            logger.error(f"NewsData.io connection test failed: {str(e)}")
            return False
