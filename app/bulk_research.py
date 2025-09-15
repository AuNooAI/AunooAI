from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from app.research import Research
from app.database import Database
from app.ai_models import get_ai_model
from app.analyzers.article_analyzer import ArticleAnalyzer
from app.collectors.collector_factory import CollectorFactory
import logging
import traceback
import datetime
import json
import os
import asyncio
from app.database_query_facade import DatabaseQueryFacade

# flake8: noqa  # Disable style warnings (long lines etc.) for this file

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

class BulkResearch:
    def __init__(self, db, research: Research = None):
        logger.debug("Initializing BulkResearch class")
        logger.debug(f"Input db type: {type(db)}")
        
        try:
            if isinstance(db, Session):
                self.db = Database()
                self.session = db
            elif isinstance(db, Database):
                self.db = db
                self.session = None
            else:
                raise TypeError(f"Expected Session or Database, got {type(db)}")
            
            # Use provided Research instance or get it from dependencies
            if research is None:
                from app.dependencies import get_research
                self.research = get_research(self.db)
            else:
                self.research = research
                
            logger.debug("BulkResearch initialized successfully")
            
        except Exception as e:
            logger.error(f"Error in BulkResearch initialization: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def is_bluesky_url(self, uri: str) -> bool:
        """Check if a URL is from the Bluesky platform."""
        parsed_uri = urlparse(uri)
        domain = parsed_uri.netloc.lower()
        # Check for bsky.app domain or any subdomain ending with .bsky.social
        return domain == 'bsky.app' or domain.endswith('.bsky.social')

    def is_newsdata_article(self, uri: str) -> bool:
        """Check if an article came from NewsData.io by checking the feed_items table."""
        try:
            # Check if this URI exists in feed_items with source_type = 'newsdata'
            query = "SELECT id FROM feed_items WHERE url = ? AND source_type = 'newsdata' LIMIT 1"
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (uri,))
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.debug(f"Error checking if article is from NewsData.io: {str(e)}")
            return False

    async def analyze_bulk_urls(
        self,
        urls: List[str],
        summary_type: str,
        model_name: str,
        summary_length: int,
        summary_voice: str,
        topic: str,
    ) -> List[Dict]:  # noqa: E501
        results = []
        logger.info(f"Starting analysis of {len(urls)} URLs with topic: {topic}")
        
        try:
            # Set the topic before starting analysis
            self.research.set_topic(topic)
            self.research.set_ai_model(model_name)
            
            # Initialize Firecrawl for batch scraping
            if not self.research.firecrawl_app:
                logger.info("Initializing Firecrawl for batch scraping...")
                self.research.firecrawl_app = self.research.initialize_firecrawl()
                if self.research.firecrawl_app:
                    logger.info("✅ Firecrawl initialized successfully for batch operations")
                else:
                    logger.warning("⚠️ Firecrawl initialization failed - will fallback to individual scraping")
            
            # Create cache directory if it doesn't exist
            os.makedirs("cache", exist_ok=True)
            
            # Initialize ArticleAnalyzer with the AI model and caching
            self.article_analyzer = ArticleAnalyzer(
                self.research.ai_model,
                use_cache=True,
            )
            
            # Initialize media bias module
            from app.models.media_bias import MediaBias
            media_bias = MediaBias(self.db)
            logger.info(f"Media bias module initialized, enabled: {media_bias.get_status().get('enabled', False)}")
            
            # Initialize BlueskyCollector for handling Bluesky URLs
            self.bluesky_collector = None
            try:
                self.bluesky_collector = CollectorFactory.get_collector('bluesky')
                logger.info("BlueskyCollector initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize BlueskyCollector: {str(e)}")
            
            # Initialize NewsdataCollector for handling NewsData.io articles
            self.newsdata_collector = None
            try:
                self.newsdata_collector = CollectorFactory.get_collector('newsdata')
                logger.info("NewsdataCollector initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NewsdataCollector: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error setting up analysis: {str(e)}")
            raise ValueError(f"Error in setup: {str(e)}")

        # Pre-scrape all articles in batch for better performance
        # Note: NewsData.io articles should already have their content stored in the database
        # via the UnifiedFeedService since NewsData.io provides full content in their API responses
        logger.info(f"🚀 Pre-scraping {len(urls)} articles in batch mode...")
        scraped_content = await self._batch_scrape_articles(urls, topic)
        logger.info(f"✅ Batch scraping completed: {len(scraped_content)} articles")

        for url in urls:
            try:
                logger.debug(f"Processing URL: {url} for topic: {topic}")
                
                # Get pre-scraped content
                article_content = scraped_content.get(url)
                
                if not article_content:
                    # Fallback to individual scraping if batch failed
                    logger.warning(f"No batch content for {url}, trying individual scraping")
                    
                    # Check if this is a Bluesky URL
                    if self.is_bluesky_url(url) and self.bluesky_collector:
                        logger.info(f"Detected Bluesky URL: {url}, using BlueskyCollector")
                        try:
                            # Fetch content using BlueskyCollector
                            content_result = await self.bluesky_collector.fetch_article_content(url)
                            
                            if not content_result:
                                logger.error(f"Failed to fetch Bluesky content for {url}")
                                raise ValueError(f"Failed to fetch Bluesky content for {url}")
                                
                            article_content = {
                                "content": content_result.get("content", ""),
                                "source": content_result.get("source", self.extract_source(url)),
                                "publication_date": content_result.get("published_date", 
                                                    datetime.datetime.now().date().isoformat()),
                                "title": content_result.get("title", "")
                            }
                            
                            # Save raw article with topic if needed
                            try:
                                self.db.save_raw_article(url, article_content["content"], topic)
                                logger.info(f"Successfully saved Bluesky content with topic: {topic}")
                            except Exception as save_error:
                                logger.error(f"Failed to save Bluesky content, continuing: {str(save_error)}")
                        except Exception as bluesky_error:
                            logger.error(f"Error with BlueskyCollector: {str(bluesky_error)}")
                            raise ValueError(f"Failed to process Bluesky URL: {str(bluesky_error)}")
                    else:
                        # Fetch article content using the research component's method
                        try:
                            logger.debug(f"Fetching article content for URL: {url}")
                            article_content = await self.research.fetch_article_content(url, save_with_topic=True)
                            
                            # Log the result of the fetch operation
                            if article_content and article_content.get("content"):
                                logger.debug(f"Successfully fetched content for {url}, length: {len(article_content['content'])}")
                            else:
                                logger.error(f"Failed to fetch valid content for URL: {url}")
                                logger.debug(f"Article content response: {article_content}")
                                raise ValueError(f"Failed to fetch valid content for URL: {url}")
                            
                        except Exception as fetch_error:
                            logger.error(f"Error in fetch_article_content for {url}: {str(fetch_error)}")
                            
                            # If there was a foreign key constraint error, try direct scraping
                            if "FOREIGN KEY constraint failed" in str(fetch_error):
                                logger.info(f"Database constraint error encountered - trying direct scraping for {url}")
                                # Use the _direct_scrape method that bypasses database operations
                                try:
                                    article_content = await self._direct_scrape(url)
                                except Exception as direct_scrape_error:
                                    logger.error(f"Direct scraping also failed for {url}: {str(direct_scrape_error)}")
                                    raise ValueError(f"Both fetch methods failed for {url}")
                            else:
                                # For other errors, reraise
                                raise
                
                # Validate the article content before proceeding
                if (
                    not article_content or 
                    not article_content.get("content") or 
                    article_content.get("content").startswith("Article cannot be scraped") or
                    article_content.get("content").startswith("Failed to fetch article content") or
                    len(article_content.get("content", "").strip()) < 10  # Ensure we have meaningful content
                ):
                    logger.error(f"Invalid or empty content for URL: {url}")
                    raise ValueError(f"Failed to fetch valid content for URL: {url}")

                # Extract title if not present
                title = article_content.get("title", "")
                if not title:
                    title = self.article_analyzer.extract_title(article_content["content"])
                    logger.debug(f"Extracted title for {url}: {title}")

                # Get publication date from article_content
                publication_date = article_content.get("publication_date")
                if not publication_date:
                    publication_date = self.article_analyzer.extract_publication_date(article_content["content"])
                logger.debug(f"Extracted publication date for {url}: {publication_date}")

                # Analyze article using ArticleAnalyzer
                result = self.article_analyzer.analyze_content(
                    article_text=article_content["content"],
                    title=title,
                    source=article_content.get("source", self.extract_source(url)),
                    uri=url,
                    summary_length=summary_length,
                    summary_voice=summary_voice,
                    summary_type=summary_type,
                    categories=self.research.CATEGORIES,
                    future_signals=self.research.FUTURE_SIGNALS,
                    sentiment_options=self.research.SENTIMENT,
                    time_to_impact_options=self.research.TIME_TO_IMPACT,
                    driver_types=self.research.DRIVER_TYPES
                )

                # Add news source, publication date and submission date
                result["news_source"] = article_content.get("source", self.extract_source(url))
                result["publication_date"] = publication_date
                result["submission_date"] = datetime.datetime.now().date().isoformat()
                result["uri"] = url  # Ensure URL is included
                result["analyzed"] = True  # Add this line to include the analyzed field
                
                # Add media bias data if not already present
                try:
                    # Try to get media bias data using the URL (more reliable)
                    bias_data = media_bias.get_bias_for_source(url)
                    if not bias_data:
                        # If URL lookup failed, try using the source name
                        bias_data = media_bias.get_bias_for_source(result["news_source"])
                        
                    if bias_data:
                        logger.info(f"Found media bias data for {url}: {bias_data.get('bias')}, {bias_data.get('factual_reporting')}")
                        result["bias"] = bias_data.get("bias", "")
                        result["factual_reporting"] = bias_data.get("factual_reporting", "")
                        result["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating", "")
                        result["bias_country"] = bias_data.get("country", "")
                        result["press_freedom"] = bias_data.get("press_freedom", "")
                        result["media_type"] = bias_data.get("media_type", "")
                        result["popularity"] = bias_data.get("popularity", "")
                    else:
                        logger.debug(f"No media bias data found for {url}")
                except Exception as bias_error:
                    logger.error(f"Error getting media bias data for {url}: {str(bias_error)}")
                    # Don't fail the entire process on bias lookup error
                
                logger.info(f"Successfully analyzed URL: {url}")
                
                # ✅ ADD AUTOMATIC VECTOR INDEXING FOR ANALYZED ARTICLES
                try:
                    from app.vector_store import upsert_article
                    
                    # Create a copy of result for vector indexing
                    vector_article = result.copy()
                    
                    # Add raw article content if available (upsert_article looks for 'raw' field)
                    if article_content and article_content.get('content'):
                        vector_article['raw'] = article_content['content']
                    
                    # Ensure we have some content for indexing
                    if vector_article.get('raw') or vector_article.get('summary') or vector_article.get('title'):
                        # Index into vector database with correct function signature
                        upsert_article(vector_article)
                        logger.info(f"Successfully indexed analyzed article into vector database: {result.get('title', url)}")
                    else:
                        logger.warning(f"No content available for vector indexing during analysis: {url}")
                        
                except Exception as vector_error:
                    logger.error(f"Failed to index analyzed article into vector database: {str(vector_error)}")
                    # Don't fail the analysis if vector indexing fails
                    logger.warning("Article analyzed but not indexed in vector store")
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing URL {url}: {str(e)}")
                logger.error(traceback.format_exc())
                
                results.append({
                    "uri": url,
                    "error": str(e),
                    "title": "Error",
                    "summary": f"Failed to analyze: {str(e)}",
                    "sentiment": "N/A",
                    "future_signal": "N/A",
                    "future_signal_explanation": "N/A",
                    "time_to_impact": "N/A",
                    "time_to_impact_explanation": "N/A",
                    "driver_type": "N/A",
                    "driver_type_explanation": "N/A",
                    "category": "N/A",
                    "tags": [],
                    "news_source": "N/A",
                    "publication_date": self.article_analyzer.extract_publication_date(""),  # Will return today's date as fallback
                    "submission_date": datetime.datetime.now().date().isoformat(),
                    "topic": topic
                })

        logger.info(f"Completed analysis of {len(urls)} URLs")
        return results

    async def save_bulk_articles(self, articles: List[Dict]) -> Dict:
        results = {
            "success": [],
            "errors": []
        }
        
        # Create MediaBias instance once for efficiency
        from app.models.media_bias import MediaBias
        media_bias = MediaBias(self.db)
        
        for article in articles:
            try:
                logger.debug(f'Attempting to save article: {article}')
                
                # Validate required fields
                required_fields = [
                    'title', 'uri', 'news_source', 'summary', 'sentiment', 'time_to_impact',
                    'category', 'future_signal', 'future_signal_explanation', 'publication_date',
                    'sentiment_explanation', 'time_to_impact_explanation', 'tags', 'driver_type',
                    'driver_type_explanation', 'submission_date', 'topic', 'analyzed'
                ]
                
                missing_fields = [field for field in required_fields if field not in article]
                if missing_fields:
                    error_msg = f"Missing required fields: {', '.join(missing_fields)}"
                    logger.warning(error_msg)
                    results["errors"].append({
                        "uri": article.get('uri', 'Unknown'),
                        "error": error_msg
                    })
                    continue
                
                # Check for empty URI
                if not article['uri']:
                    error_msg = "Empty URI provided"
                    logger.warning(error_msg)
                    results["errors"].append({
                        "uri": "Empty",
                        "error": error_msg
                    })
                    continue
                
                # Convert tags list to string if necessary
                if isinstance(article.get('tags'), list):
                    article['tags'] = ', '.join(article['tags'])
                    
                # Add media bias data if not already present
                if article.get('news_source') and not article.get('bias'):
                    try:
                        # Check if media bias enrichment is enabled
                        status = media_bias.get_status()
                        if status.get('enabled', False):
                            logger.debug(
                                f"Media bias enrichment is enabled, "
                                f"looking up data for {article['news_source']}"
                            )
                            
                            # Get bias data for this source
                            bias_data = media_bias.get_bias_for_source(article['news_source'])
                            
                            if bias_data:
                                logger.debug(
                                    f"Found media bias data for {article['news_source']}: "
                                    f"{bias_data}"
                                )
                                
                                # Add bias data to article
                                article['bias'] = bias_data.get('bias', '')
                                article['factual_reporting'] = bias_data.get('factual_reporting', '')
                                article['mbfc_credibility_rating'] = bias_data.get('mbfc_credibility_rating', '')
                                article['bias_source'] = bias_data.get('source', '')
                                article['bias_country'] = bias_data.get('country', '')
                                article['press_freedom'] = bias_data.get('press_freedom', '')
                                article['media_type'] = bias_data.get('media_type', '')
                                article['popularity'] = bias_data.get('popularity', '')
                            else:
                                logger.debug(f"No media bias data found for {article['news_source']}")
                    except Exception as e:
                        logger.error(f"Error enriching article with media bias data: {str(e)}")
                        # Don't fail the entire process if bias enrichment fails
                
                # Save the article to the database
                self.db.save_article(article)
                
                # Save raw markdown if available
                if article.get('raw_markdown'):
                    self.db.save_raw_article(
                        article['uri'],
                        article['raw_markdown'],
                        article.get('topic', '')
                    )
                
                # ✅ ADD AUTOMATIC VECTOR INDEXING
                try:
                    from app.vector_store import upsert_article
                    
                    # Create a copy of article for vector indexing
                    vector_article = article.copy()
                    
                    # Add raw content if available (upsert_article looks for 'raw' field)
                    raw_content = article.get('raw_markdown', '')
                    if not raw_content:
                        # Try to get from database
                        try:
                            raw_article = self.db.get_raw_article(article['uri'])
                            if raw_article:
                                raw_content = raw_article.get('raw_markdown', '')
                        except Exception:
                            pass
                    
                    if raw_content:
                        vector_article['raw'] = raw_content
                    
                    # Ensure we have some content for indexing
                    if vector_article.get('raw') or vector_article.get('summary') or vector_article.get('title'):
                        # Index into vector database with correct function signature
                        upsert_article(vector_article)
                        logger.info(f"Successfully indexed bulk article into vector database: {article['title']}")
                    else:
                        logger.warning(f"No content available for vector indexing: {article['uri']}")
                        
                except Exception as vector_error:
                    logger.error(f"Failed to index bulk article into vector database: {str(vector_error)}")
                    # Don't fail the entire save operation if vector indexing fails
                    logger.warning("Bulk article saved to database but not indexed in vector store")
                
                logger.info(f"Successfully saved article: {article['title']}")
                results["success"].append({
                    "uri": article['uri'], 
                    "title": article['title']
                })
                
            except Exception as e:
                logger.error(f"Error saving article: {str(e)}")
                results["errors"].append({
                    "uri": article.get('uri', 'Unknown'),
                    "error": str(e)
                })
        
        return results
    
    def extract_source(self, uri):
        domain = urlparse(uri).netloc
        return domain.replace('www.', '')

    def set_ai_model(self, model_name: str):
        self.ai_model = get_ai_model(model_name)

    async def analyze_articles(self, urls: List[str], topic: str) -> None:
        for url in urls:
            # Check if it's from keyword alerts
            alert_article = self.db.get_keyword_alert_article(url)
            if alert_article:
                # Analyze the article
                analysis = await self.analyze_single_article(url)
                
                # If analysis successful, move to main articles table
                if analysis:
                    await (DatabaseQueryFacade(self.db, logger)).research.move_alert_to_articles(url)

    async def _batch_scrape_articles(self, urls: List[str], topic: str = None) -> Dict[str, Dict[str, Any]]:
        """
        Batch scrape articles using Firecrawl's batch API or fallback to individual scraping
        
        Args:
            urls: List of URLs to scrape
            topic: Topic for saving raw articles
            
        Returns:
            Dictionary mapping URLs to article content dictionaries
        """
        results = {}
        
        # Separate Bluesky URLs from regular URLs
        bluesky_urls = []
        regular_urls = []
        
        for url in urls:
            if self.is_bluesky_url(url):
                bluesky_urls.append(url)
            else:
                regular_urls.append(url)
        
        # Handle Bluesky URLs individually (they don't support batch)
        for url in bluesky_urls:
            if self.bluesky_collector:
                try:
                    content_result = await self.bluesky_collector.fetch_article_content(url)
                    if content_result:
                        results[url] = {
                            "content": content_result.get("content", ""),
                            "source": content_result.get("source", self.extract_source(url)),
                            "publication_date": content_result.get("published_date", 
                                                datetime.datetime.now().date().isoformat()),
                            "title": content_result.get("title", "")
                        }
                        
                        # Save raw content
                        try:
                            if topic:
                                self.db.save_raw_article(url, results[url]["content"], topic)
                        except Exception as save_error:
                            logger.error(f"Failed to save Bluesky content: {save_error}")
                except Exception as e:
                    logger.error(f"Error fetching Bluesky content for {url}: {e}")
                    results[url] = None
        
        # Handle regular URLs with batch processing
        if regular_urls:
            try:
                # Try batch processing first
                if self.research.firecrawl_app:
                    logger.info(f"Attempting batch scraping for {len(regular_urls)} regular URLs")
                    batch_results = await self._firecrawl_batch_scrape(regular_urls)
                    
                    for url, content in batch_results.items():
                        if content:
                            results[url] = {
                                "content": content,
                                "source": self.extract_source(url),
                                "publication_date": self.article_analyzer.extract_publication_date(content),
                                "title": self.article_analyzer.extract_title(content)
                            }
                            
                            # Save raw content
                            try:
                                if topic:
                                    self.db.save_raw_article(url, content, topic)
                            except Exception as save_error:
                                logger.error(f"Failed to save batch content: {save_error}")
                        else:
                            results[url] = None
                else:
                    logger.warning("Firecrawl not available, falling back to individual scraping")
                    # Fallback to individual scraping
                    for url in regular_urls:
                        try:
                            article_content = await self.research.fetch_article_content(url, save_with_topic=bool(topic))
                            if article_content and article_content.get("content"):
                                results[url] = article_content
                            else:
                                results[url] = None
                        except Exception as e:
                            logger.error(f"Individual scraping failed for {url}: {e}")
                            results[url] = None
                            
            except Exception as e:
                logger.error(f"Batch scraping failed: {e}")
                # Fallback to individual scraping
                for url in regular_urls:
                    if url not in results:  # Only process if not already processed
                        try:
                            article_content = await self.research.fetch_article_content(url, save_with_topic=bool(topic))
                            if article_content and article_content.get("content"):
                                results[url] = article_content
                            else:
                                results[url] = None
                        except Exception as e:
                            logger.error(f"Fallback individual scraping failed for {url}: {e}")
                            results[url] = None
        
        return results
    
    async def _firecrawl_batch_scrape(self, urls: List[str]) -> Dict[str, Optional[str]]:
        """
        Use Firecrawl's batch API to scrape multiple URLs
        
        Args:
            urls: List of URLs to scrape
            
        Returns:
            Dictionary mapping URLs to scraped content
        """
        try:
            # Prepare batch request
            batch_response = self.research.firecrawl_app.start_batch_scrape(
                urls,
                formats=["markdown"],
                only_main_content=True,
                timeout=30000
            )
            
            # Check if we got a valid response with an ID
            batch_id = getattr(batch_response, 'id', None) if batch_response else None
            if not batch_response or not batch_id:
                logger.error(f"Batch scrape failed: {batch_response}")
                return {}
            
            logger.info(f"✅ Batch scrape submitted with ID: {batch_id}")
            
            # Poll for completion
            return await self._poll_batch_completion(batch_id)
            
        except Exception as e:
            logger.error(f"Error in Firecrawl batch scraping: {e}")
            return {}
    
    async def _poll_batch_completion(self, batch_id: str, max_wait_time: int = 300) -> Dict[str, Optional[str]]:
        """
        Poll Firecrawl batch API for completion
        
        Args:
            batch_id: Batch job ID
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            Dictionary mapping URLs to scraped content
        """
        import time
        
        start_time = time.time()
        poll_interval = 5  # Start with 5 second intervals
        
        while time.time() - start_time < max_wait_time:
            try:
                status_response = self.research.firecrawl_app.get_batch_scrape_status(batch_id)
                
                if not status_response:
                    logger.warning(f"No status response for batch {batch_id}")
                    await asyncio.sleep(poll_interval)
                    continue
                
                status = status_response.get('status')
                logger.debug(f"Batch {batch_id} status: {status}")
                
                if status == 'completed':
                    # Get results
                    results = {}
                    data = status_response.get('data', [])
                    
                    for item in data:
                        url = item.get('url')
                        if item.get('success') and 'markdown' in item:
                            # Apply token limiting
                            content = item['markdown']
                            from app.analyzers.article_analyzer import ArticleAnalyzer
                            truncated_content = ArticleAnalyzer.truncate_text(None, content, max_chars=65000)
                            
                            if len(content) > len(truncated_content):
                                logger.info(f"Truncated content for {url}: {len(content)} -> {len(truncated_content)} chars")
                            
                            results[url] = truncated_content
                        else:
                            results[url] = None
                            logger.warning(f"Failed to scrape {url}: {item.get('error', 'Unknown error')}")
                    
                    logger.info(f"Batch {batch_id} completed with {len(results)} results")
                    return results
                    
                elif status == 'failed':
                    logger.error(f"Batch {batch_id} failed: {status_response.get('error', 'Unknown error')}")
                    return {}
                    
                # Still processing, wait before next poll
                await asyncio.sleep(poll_interval)
                
                # Increase poll interval gradually
                poll_interval = min(poll_interval * 1.2, 30)
                
            except Exception as e:
                logger.error(f"Error polling batch status: {e}")
                await asyncio.sleep(poll_interval)
        
        logger.warning(f"Batch {batch_id} timed out after {max_wait_time} seconds")
        return {}

    async def _direct_scrape(self, url):
        """Directly scrape the URL without saving to database.
        This is a workaround for foreign key constraint issues."""
        try:
            logger.debug(f"Performing direct scrape for URL: {url}")
            
            if not self.research.firecrawl_app:
                logger.warning("Firecrawl is not configured. Cannot perform direct scrape.")
                return {
                    "content": "Article content cannot be fetched. Firecrawl is not configured.",
                    "source": self.extract_source(url),
                    "publication_date": datetime.datetime.now().date().isoformat(),
                    "success": False
                }
            
            # Try to scrape with Firecrawl directly
            scrape_result = self.research.firecrawl_app.scrape(
                url,
                formats=["markdown"]
            )
            
            # Extract content
            if isinstance(scrape_result, dict) and 'markdown' in scrape_result:
                content = scrape_result['markdown']
                
                # Extract publication date using ArticleAnalyzer
                publication_date = self.article_analyzer.extract_publication_date(content)
                
                # Note: We're intentionally NOT saving to the database here to avoid topic issues
                # This is consistent with our fix to fetch_article_content
                
                return {
                    "content": content,
                    "source": self.extract_source(url),
                    "publication_date": publication_date,
                    "success": True
                }
            else:
                logger.warning(f"Unexpected response format from direct Firecrawl scrape for URL: {url}")
                return {
                    "content": "Failed to fetch article content. Unexpected response format.",
                    "source": self.extract_source(url),
                    "publication_date": datetime.datetime.now().date().isoformat(),
                    "success": False
                }
        except Exception as scrape_error:
            logger.error(f"Error in direct scrape: {str(scrape_error)}")
            return {
                "content": f"Failed to fetch article content: {str(scrape_error)}",
                "source": self.extract_source(url),
                "publication_date": datetime.datetime.now().date().isoformat(),
                "success": False
            }

    async def analyze_bulk_urls_stream(
        self,
        urls: List[str],
        summary_type: str,
        model_name: str,
        summary_length: int,
        summary_voice: str,
        topic: str,
        preserved_metadata: dict = None,
    ):
        """Yield analysis results one-by-one so the caller can stream them."""
        # Re-use the existing setup logic from analyze_bulk_urls -----------------
        logger.info(f"[stream] Starting analysis of {len(urls)} URLs with topic: {topic}")  # noqa: E501
        try:
            self.research.set_topic(topic)
            self.research.set_ai_model(model_name)
            
            # Initialize Firecrawl for batch scraping
            if not self.research.firecrawl_app:
                logger.info("[stream] Initializing Firecrawl for batch scraping...")
                self.research.firecrawl_app = self.research.initialize_firecrawl()
                if self.research.firecrawl_app:
                    logger.info("[stream] ✅ Firecrawl initialized successfully for batch operations")
                else:
                    logger.warning("[stream] ⚠️ Firecrawl initialization failed - will fallback to individual scraping")
            
            os.makedirs("cache", exist_ok=True)
            self.article_analyzer = ArticleAnalyzer(
                self.research.ai_model,
                use_cache=True,
            )
            
            # Initialize media bias module
            from app.models.media_bias import MediaBias
            media_bias = MediaBias(self.db)
            logger.info(f"[stream] Media bias module initialized, enabled: {media_bias.get_status().get('enabled', False)}")
            
            self.bluesky_collector = None
            try:
                self.bluesky_collector = CollectorFactory.get_collector('bluesky')
            except Exception as e:
                logger.warning(f"[stream] Failed to init BlueskyCollector: {str(e)}")
        except Exception as e:
            logger.error(f"[stream] Setup error: {str(e)}")
            raise

        # Iterate through URLs one-by-one and yield results ----------------------
        for url in urls:
            try:
                logger.debug(f"[stream] Processing URL: {url}")  # noqa: E501
                # --- identical fetching & analysing logic as in analyze_bulk_urls ---
                article_content = None
                if self.is_bluesky_url(url) and self.bluesky_collector:
                    try:
                        content_result = await self.bluesky_collector.fetch_article_content(url)
                        if not content_result:
                            raise ValueError(f"Failed to fetch Bluesky content for {url}")
                        article_content = {
                            "content": content_result.get("content", ""),
                            "source": content_result.get("source", self.extract_source(url)),
                            "publication_date": content_result.get("published_date", datetime.datetime.now().date().isoformat()),  # noqa: E501
                            "title": content_result.get("title", ""),
                        }
                        try:
                            self.db.save_raw_article(url, article_content["content"], topic)
                        except Exception:
                            pass
                    except Exception as bluesky_error:
                        raise ValueError(f"Bluesky error: {str(bluesky_error)}")
                else:
                    try:
                        article_content = await self.research.fetch_article_content(
                            url,
                            save_with_topic=True,
                        )
                        if not article_content or not article_content.get("content"):
                            raise ValueError(f"Failed to fetch valid content for URL: {url}")
                    except Exception as fetch_error:
                        if "FOREIGN KEY constraint failed" in str(fetch_error):
                            article_content = await self._direct_scrape(url)
                        else:
                            raise

                # Basic validation ------------------------------------------------
                if (
                    not article_content or
                    not article_content.get("content") or
                    article_content["content"].startswith("Article cannot be scraped") or  # noqa: E501
                    article_content["content"].startswith(
                        "Article cannot be scraped",
                    ) or
                    len(article_content.get("content", "").strip()) < 10
                ):
                    raise ValueError(f"Invalid or empty content for URL: {url}")

                # Title & publication date with preserved metadata override -------
                preserved_data = preserved_metadata.get(url, {}) if preserved_metadata else {}
                
                title = (
                    preserved_data.get("title") or
                    article_content.get("title") or
                    self.article_analyzer.extract_title(article_content["content"])
                )
                publication_date = (
                    preserved_data.get("publication_date") or
                    article_content.get("publication_date") or
                    self.article_analyzer.extract_publication_date(
                        article_content["content"],
                    )
                )
                
                # Use preserved source if available
                source = (
                    preserved_data.get("source") or 
                    article_content.get("source", self.extract_source(url))
                )

                result = self.article_analyzer.analyze_content(
                    article_text=article_content["content"],
                    title=title,
                    source=source,
                    uri=url,
                    summary_length=summary_length,
                    summary_voice=summary_voice,
                    summary_type=summary_type,
                    categories=self.research.CATEGORIES,
                    future_signals=self.research.FUTURE_SIGNALS,
                    sentiment_options=self.research.SENTIMENT,
                    time_to_impact_options=self.research.TIME_TO_IMPACT,
                    driver_types=self.research.DRIVER_TYPES,
                )
                result.update({
                    "news_source": source,
                    "publication_date": publication_date,
                    "submission_date": datetime.datetime.now().date().isoformat(),
                    "uri": url,
                    "analyzed": True,
                })
                
                # Apply any additional preserved metadata
                if preserved_data:
                    logger.info(f"[stream] Using preserved metadata for {url}: {preserved_data}")
                    if preserved_data.get('bias'):
                        result['bias'] = preserved_data['bias']
                    if preserved_data.get('factual_reporting'):
                        result['factual_reporting'] = preserved_data['factual_reporting']
                    if preserved_data.get('mbfc_credibility_rating'):
                        result['mbfc_credibility_rating'] = preserved_data['mbfc_credibility_rating']
                    if preserved_data.get('bias_country'):
                        result['bias_country'] = preserved_data['bias_country']
                    if preserved_data.get('media_type'):
                        result['media_type'] = preserved_data['media_type']
                    if preserved_data.get('popularity'):
                        result['popularity'] = preserved_data['popularity']
                
                # Add media bias data if not already present
                try:
                    # Try to get media bias data using the URL (more reliable)
                    bias_data = media_bias.get_bias_for_source(url)
                    if not bias_data:
                        # If URL lookup failed, try using the source name
                        bias_data = media_bias.get_bias_for_source(result["news_source"])
                        
                    if bias_data:
                        logger.info(f"[stream] Found media bias data for {url}: {bias_data.get('bias')}, {bias_data.get('factual_reporting')}")
                        result["bias"] = bias_data.get("bias", "")
                        result["factual_reporting"] = bias_data.get("factual_reporting", "")
                        result["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating", "")
                        result["bias_country"] = bias_data.get("country", "")
                        result["press_freedom"] = bias_data.get("press_freedom", "")
                        result["media_type"] = bias_data.get("media_type", "")
                        result["popularity"] = bias_data.get("popularity", "")
                    else:
                        logger.debug(f"[stream] No media bias data found for {url}")
                except Exception as bias_error:
                    logger.error(f"[stream] Error getting media bias data for {url}: {str(bias_error)}")
                    # Don't fail the entire process on bias lookup error
                
                logger.info(f"[stream] Finished URL: {url}")
                
                # ✅ ADD AUTOMATIC VECTOR INDEXING FOR STREAMING ANALYSIS
                try:
                    from app.vector_store import upsert_article
                    
                    # Create a copy of result for vector indexing
                    vector_article = result.copy()
                    
                    # Add raw article content if available (upsert_article looks for 'raw' field)
                    if article_content and article_content.get('content'):
                        vector_article['raw'] = article_content['content']
                    
                    # Ensure we have some content for indexing
                    if vector_article.get('raw') or vector_article.get('summary') or vector_article.get('title'):
                        # Index into vector database with correct function signature
                        upsert_article(vector_article)
                        logger.info(f"[stream] Successfully indexed analyzed article into vector database: {result.get('title', url)}")
                    else:
                        logger.warning(f"[stream] No content available for vector indexing during analysis: {url}")
                        
                except Exception as vector_error:
                    logger.error(f"[stream] Failed to index analyzed article into vector database: {str(vector_error)}")
                    # Don't fail the analysis if vector indexing fails
                    logger.warning("[stream] Article analyzed but not indexed in vector store")
                
                yield result
                # Give control back to event loop to flush stream quickly
                await asyncio.sleep(0)
            except Exception as e:
                logger.error(f"[stream] Error for URL {url}: {str(e)}")
                yield {
                    "uri": url,
                    "error": str(e),
                    "title": "Error",
                    "summary": (
                        f"Failed to analyse: {str(e)}",
                    ),
                    "sentiment": "N/A",
                    "future_signal": "N/A",
                    "future_signal_explanation": "N/A",
                    "time_to_impact": "N/A",
                    "time_to_impact_explanation": "N/A",
                    "driver_type": "N/A",
                    "driver_type_explanation": "N/A",
                    "category": "N/A",
                    "tags": [],
                    "news_source": "N/A",
                    "publication_date": datetime.datetime.now().date().isoformat(),
                    "submission_date": datetime.datetime.now().date().isoformat(),
                    "topic": topic,
                }

        logger.info("[stream] Completed streaming all URLs")

    async def analyze_single_article(self, url: str):  # noqa: D401
        """Analyze a single article.

        This is a thin wrapper so static analyzers see the attribute. It delegates
        to the Research component's `analyze_article` method.
        """
        try:
            article_content = await self.research.fetch_article_content(url)
            result = self.article_analyzer.analyze_content(
                article_text=article_content.get("content", ""),
                title=article_content.get("title", ""),
                source=article_content.get("source", self.extract_source(url)),
                uri=url,
                summary_length=50,
                summary_voice="neutral",
                summary_type="curious_ai",
                categories=self.research.CATEGORIES,
                future_signals=self.research.FUTURE_SIGNALS,
                sentiment_options=self.research.SENTIMENT,
                time_to_impact_options=self.research.TIME_TO_IMPACT,
                driver_types=self.research.DRIVER_TYPES,
            )
            
            # Add news_source if not present
            if "news_source" not in result:
                result["news_source"] = article_content.get("source", self.extract_source(url))
            
            # Add media bias data
            try:
                from app.models.media_bias import MediaBias
                media_bias = MediaBias(self.db)
                
                # Try to get media bias data using the URL (more reliable)
                bias_data = media_bias.get_bias_for_source(url)
                if not bias_data:
                    # If URL lookup failed, try using the source name
                    bias_data = media_bias.get_bias_for_source(result["news_source"])
                    
                if bias_data:
                    logger.info(f"Found media bias data for {url}: {bias_data.get('bias')}, {bias_data.get('factual_reporting')}")
                    result["bias"] = bias_data.get("bias", "")
                    result["factual_reporting"] = bias_data.get("factual_reporting", "")
                    result["mbfc_credibility_rating"] = bias_data.get("mbfc_credibility_rating", "")
                    result["bias_country"] = bias_data.get("country", "")
                    result["press_freedom"] = bias_data.get("press_freedom", "")
                    result["media_type"] = bias_data.get("media_type", "")
                    result["popularity"] = bias_data.get("popularity", "")
                else:
                    logger.debug(f"No media bias data found for {url}")
            except Exception as bias_error:
                logger.error(f"Error getting media bias data for {url}: {str(bias_error)}")
                # Don't fail the entire process on bias lookup error
            
            return result
        except Exception as exc:
            logger.error("Failed to analyse single article %s: %s", url, exc)
            return None
