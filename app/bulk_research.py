from typing import List, Dict
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

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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

    async def analyze_bulk_urls(self, urls: List[str], summary_type: str, 
                                 model_name: str, summary_length: int, 
                                 summary_voice: str, topic: str) -> List[Dict]:
        results = []
        logger.info(f"Starting analysis of {len(urls)} URLs with topic: {topic}")
        
        try:
            # Set the topic before starting analysis
            self.research.set_topic(topic)
            self.research.set_ai_model(model_name)
            
            # Create cache directory if it doesn't exist
            os.makedirs("cache", exist_ok=True)
            
            # Initialize ArticleAnalyzer with the AI model and caching
            self.article_analyzer = ArticleAnalyzer(self.research.ai_model, use_cache=True)
            
            # Initialize BlueskyCollector for handling Bluesky URLs
            self.bluesky_collector = None
            try:
                self.bluesky_collector = CollectorFactory.get_collector('bluesky')
                logger.info("BlueskyCollector initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize BlueskyCollector: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error setting up analysis: {str(e)}")
            raise ValueError(f"Error in setup: {str(e)}")

        for url in urls:
            try:
                logger.debug(f"Processing URL: {url} for topic: {topic}")
                
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
                results.append(result)
                logger.info(f"Successfully analyzed URL: {url}")
                
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
                
                # Validate required fields
                missing_fields = [field for field in required_fields if not article.get(field)]
                if missing_fields:
                    raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
                
                # Format tags if they're a string
                if isinstance(article['tags'], str):
                    article['tags'] = [tag.strip() for tag in article['tags'].split(',') if tag.strip()]
                
                # Ensure dates are in ISO format
                for date_field in ['publication_date', 'submission_date']:
                    if article.get(date_field):
                        try:
                            # Try to parse and reformat the date
                            date_obj = datetime.fromisoformat(article[date_field].replace('Z', '+00:00'))
                            article[date_field] = date_obj.date().isoformat()
                        except (ValueError, AttributeError):
                            logger.warning(f"Invalid date format for {date_field}: {article[date_field]}")
                            article[date_field] = datetime.datetime.now().date().isoformat()

                # Before saving, ensure analyzed is set
                if 'analyzed' not in article:
                    article['analyzed'] = True  # If it has all required fields, it's analyzed

                # Use the research instance to save the article
                saved_article = await self.research.save_article(article)
                logger.info(f"Successfully saved article: {article['uri']}")
                results["success"].append(saved_article)
                
            except Exception as e:
                logger.error(f"Error saving article {article.get('uri', 'Unknown URL')}: {str(e)}")
                logger.error(f"Article data: {json.dumps(article, indent=2)}")
                results["errors"].append({
                    "uri": article.get('uri', 'Unknown URL'),
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
                    await self.research.move_alert_to_articles(url)

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
            scrape_result = self.research.firecrawl_app.scrape_url(
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
