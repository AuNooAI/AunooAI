"""Monitor keywords and collect matching news articles."""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.collectors.newsapi_collector import NewsAPICollector
from app.database import Database
import uuid

logger = logging.getLogger(__name__)

# Import AutomatedIngestService for auto-ingest functionality
try:
    from app.services.automated_ingest_service import AutomatedIngestService
except ImportError:
    logger.warning("AutomatedIngestService not available - auto-ingest features disabled")
    AutomatedIngestService = None

# Global variable to track task status
_background_task_status = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "next_check_time": None
}

# Global variable to track keyword monitor auto-ingest jobs
# This integrates with the job tracking system in keyword_monitor.py routes
_keyword_monitor_jobs = {}

class KeywordMonitorJob:
    """Job tracking for keyword monitor auto-ingest processing"""
    def __init__(self, job_id: str, topic: str, article_count: int):
        self.job_id = job_id
        self.topic = topic
        self.article_count = article_count
        self.status = "running"
        self.progress = 0
        self.results = None
        self.error = None
        self.started_at = datetime.utcnow()
        self.completed_at = None

def get_task_status() -> Dict:
    """Get the current status of the keyword monitor background task"""
    return _background_task_status.copy()

def get_keyword_monitor_jobs() -> Dict:
    """Get all active keyword monitor jobs for integration with badge system"""
    return _keyword_monitor_jobs.copy()

class KeywordMonitor:
    def __init__(self, db: Database):
        self.db = db
        self.collector = None
        self.last_collector_init_attempt = None
        # Initialize auto-ingest service if available
        self.auto_ingest_service = None
        if AutomatedIngestService:
            self.auto_ingest_service = AutomatedIngestService(db)

        self._load_settings()
        self.check_and_reset_counter()  # Check for reset during initialization

    def _load_settings(self):
        """Load settings from database"""
        try:
                settings = self.db.facade.get_or_create_keyword_monitor_settings()

                if settings:
                    self.check_interval = settings['check_interval'] * settings['interval_unit']  # interval * unit
                    self.search_fields = settings['search_fields']
                    self.language = settings['language']
                    self.sort_by = settings['sort_by']
                    self.page_size = settings['page_size']
                    self.is_enabled = settings['is_enabled']
                    self.daily_request_limit = settings['daily_request_limit']
                    self.search_date_range = settings['search_date_range'] or 7  # Default to 7 days if not set
                    self.provider = settings['provider'] or 'newsapi'  # Default to newsapi if not set
                else:
                    # Use defaults
                    self.check_interval = 900  # 15 minutes
                    self.search_fields = "title,description,content"
                    self.language = "en"
                    self.sort_by = "publishedAt"
                    self.page_size = 10
                    self.is_enabled = True
                    self.daily_request_limit = 100
                    self.search_date_range = 7  # Default to 7 days
                    self.provider = 'newsapi'  # Default provider

        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")
            # Use defaults
            self.check_interval = 900
            self.search_fields = "title,description,content"
            self.language = "en"
            self.sort_by = "publishedAt"
            self.page_size = 10
            self.is_enabled = True
            self.daily_request_limit = 100
            self.search_date_range = 7  # Default to 7 days
            self.provider = 'newsapi'  # Default provider

    def _init_collector(self):
        """Initialize the news collector based on settings"""
        try:
            provider = self.db.facade.get_keyword_monitoring_provider()

            if provider == 'thenewsapi':
                from app.collectors.thenewsapi_collector import TheNewsAPICollector
                self.collector = TheNewsAPICollector()
            elif provider == 'newsdata':
                from app.collectors.newsdata_collector import NewsdataCollector
                # Check if NewsData.io is configured before trying to initialize
                if not NewsdataCollector.is_configured():
                    raise ValueError("NewsData.io API key not configured in environment variables")
                self.collector = NewsdataCollector()
            elif provider == 'newsapi' or not provider:
                from app.collectors.newsapi_collector import NewsAPICollector
                # Check if NewsAPI key is configured
                import os
                newsapi_key = os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY')
                if not newsapi_key:
                    raise ValueError(f"NewsAPI key not configured. Current provider: '{provider}'. Please set provider to 'thenewsapi' or 'newsdata' if you don't have a NewsAPI key.")
                self.collector = NewsAPICollector(self.db)
            else:
                raise ValueError(f"Unknown provider '{provider}'. Valid options: 'newsapi', 'thenewsapi', 'newsdata'")

            self.last_collector_init_attempt = datetime.now()
            return True
        except Exception as e:
            logger.error(f"Error initializing collector: {str(e)}")
            return False

    def check_and_reset_counter(self):
        """Check if the API usage counter needs to be reset for a new day"""
        try:
            row = self.db.facade.get_keyword_monitoring_counter()

            if row:
                current_count, last_reset = row['requests_today'], row['last_reset_date']
                today = datetime.now().date().isoformat()

                if not last_reset or last_reset < today:
                    # Reset counter for new day
                    logger.info(f"Resetting API counter from {current_count} to 0 (last reset: {last_reset}, today: {today})")
                    self.db.facade.reset_keyword_monitoring_counter((today,))

                    # Also reset the collector's counter if it exists
                    if self.collector:
                        self.collector.requests_today = 0
                        logger.info("Reset collector's requests_today counter to 0")
                else:
                    logger.debug(f"No reset needed. Last reset: {last_reset}, today: {today}, current count: {current_count}")
        except Exception as e:
            logger.error(f"Error checking/resetting API counter: {str(e)}")

    async def check_keywords(self, group_id=None, progress_callback=None):
        """Check all keywords for new matches

        Args:
            group_id: Optional group ID to filter keywords by specific group
            progress_callback: Optional callback function(processed, current) for progress updates
        """
        if group_id:
            logger.info(f"Starting keyword check for group {group_id}...")
        else:
            logger.info("Starting keyword check for all groups...")
        new_articles_count = 0
        processed_keywords = 0

        try:
            # Check if counter needs reset before starting
            self.check_and_reset_counter()

            if not self._init_collector():
                logger.error("Failed to initialize collector, skipping check")
                return {"success": False, "error": "Failed to initialize collector", "new_articles": 0}
        except Exception as e:
            logger.error(f"Error in pre-check setup: {str(e)}", exc_info=True)
            return {"success": False, "error": f"Setup error: {str(e)}", "new_articles": 0}

        try:
            check_start_time = datetime.now().isoformat()

            self.db.facade.create_or_update_keyword_monitor_last_check((check_start_time, self.collector.requests_today))

            # Get keywords - filter by group_id if provided
            if group_id:
                keywords = self.db.facade.get_monitored_keywords_by_group_id(group_id)
                logger.info(f"Found {len(keywords)} keywords to check for group {group_id}")
            else:
                keywords = self.db.facade.get_monitored_keywords()
                logger.info(f"Found {len(keywords)} keywords to check")

            for keyword in keywords:
                # Extract from mapping object
                keyword_id = keyword['id']
                keyword_text = keyword['keyword']
                last_checked = keyword['last_checked']
                topic = keyword['topic']
                processed_keywords += 1

                # Report progress if callback provided
                if progress_callback:
                    progress_callback(processed_keywords, f"Checking: {keyword_text}")

                logger.info(
                    f"Checking keyword: {keyword_text} (topic: {topic}, "
                    f"requests_today: {self.collector.requests_today}/100)"
                )

                try:
                    # Calculate start_date based on search_date_range instead of last_checked
                    start_date = datetime.now() - timedelta(days=self.search_date_range)

                    logger.debug(f"Searching for articles with keyword: '{keyword_text}', topic: '{topic}', start_date: {start_date.isoformat()}")
                    articles = await self.collector.search_articles(
                        query=keyword_text,
                        topic=topic,
                        max_results=self.page_size,
                        start_date=start_date,  # Use calculated start_date
                        search_fields=self.search_fields,
                        language=self.language,
                        sort_by=self.sort_by
                    )

                    if not articles:
                        logger.warning(f"No articles found or error occurred for keyword: {keyword_text}")
                        continue

                    logger.info(f"Found {len(articles)} new articles for keyword: {keyword_text}")
                    # Log details of first few articles to help debug
                    for i, article in enumerate(articles[:3]):  # Log up to first 3 articles
                        logger.debug(f"Article {i+1}: title='{article.get('title', '')}', url='{article.get('url', '')}', published={article.get('published_date', '')}")

                    # FIRST: Process each article and save to database
                    for article in articles:
                        try:
                            article_url = article['url'].strip()

                            # Log article details for debugging
                            logger.debug(
                                f"Processing article: url={article_url}, "
                                f"title={article.get('title', '')}, "
                                f"source={article.get('source', '')}, "
                                f"published={article.get('published_date', '')}"
                            )

                            # First check if article exists outside transaction
                            article_exists = self.db.facade.article_exists((article_url,))

                            if article_exists:
                                logger.debug(f"Article already exists: {article_url}")

                            # Use shorter transaction by processing article individually
                            (inserted_new_article, alert_inserted, match_updated) = self.db.facade.create_article(article_exists, article_url,article, topic, keyword_id)
                            # Only count as new if we actually inserted or updated something
                            if inserted_new_article or alert_inserted or match_updated:
                                new_articles_count += 1
                                logger.info(f"Added/updated article: {article_url}")

                        except Exception as e:
                            logger.error(f"Error processing article {article_url}: {str(e)}")
                            continue

                    # SECOND: Now run auto-ingest pipeline on the saved articles
                    should_auto_ingest = self.should_auto_ingest()
                    logger.info(f"Auto-ingest check: enabled={should_auto_ingest}, articles_count={len(articles)}")

                    if should_auto_ingest:
                        try:
                            topic_keywords = self.db.facade.get_monitored_keywords_for_topic((topic,))
                            logger.info(f"Starting auto-ingest pipeline for {len(articles)} articles with {len(topic_keywords)} keywords")

                            auto_ingest_results = await self.auto_ingest_pipeline(articles, topic, topic_keywords)
                            logger.info(f"Auto-ingest pipeline completed. Results: {auto_ingest_results}")
                        except Exception as e:
                            logger.error(f"Auto-ingest pipeline failed: {e}", exc_info=True)

                    # Update last checked timestamp
                    self.db.facade.update_monitored_keyword_last_checked((datetime.now().isoformat(), keyword_id))

                    # After processing keywords, check and reset counter if needed before updating
                    self.check_and_reset_counter()

                    # Update request count in status
                    self.db.facade.update_keyword_monitor_counter((self.collector.requests_today,))
                except ValueError as e:
                    if "Rate limit exceeded" in str(e):
                        error_msg = "API daily request limit reached"
                        logger.error(error_msg)
                        self.db.facade.create_keyword_monitor_log_entry((check_start_time, error_msg, self.collector.requests_today if self.collector else 0))
                        return {"success": False, "error": error_msg, "new_articles": new_articles_count}
                    # Don't re-raise, return error response instead
                    logger.error(f"ValueError in keyword check: {str(e)}")
                    return {"success": False, "error": str(e), "new_articles": new_articles_count}

                # Continue to next keyword (don't return here)

            # Return summary results after processing all keywords
            return {
                "success": True,
                "new_articles": new_articles_count,
                "keywords_processed": processed_keywords
            }

        except Exception as e:
            logger.error(f"Error checking keywords: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "new_articles": new_articles_count}
        
        # Final safety net - this should never be reached, but just in case
        logger.error("check_keywords reached end without returning - this should not happen!")
        return {"success": False, "error": "Unexpected end of method", "new_articles": new_articles_count}

    def get_auto_ingest_settings(self) -> Dict[str, any]:
        """Get auto-ingest settings from database"""
        if not self.auto_ingest_service:
            return {"auto_ingest_enabled": False}
        return self.auto_ingest_service.get_auto_ingest_settings()

    def should_auto_ingest(self) -> bool:
        """Check if auto-ingest is enabled"""
        settings = self.get_auto_ingest_settings()
        return settings.get("auto_ingest_enabled", False)

    async def auto_ingest_pipeline(self, articles: List[Dict[str, any]], topic: str, keywords: List[str]) -> Dict[str, any]:
        """
        Run the auto-ingest pipeline on a batch of articles

        Args:
            articles: List of article dictionaries
            topic: Topic name for context
            keywords: List of keywords for relevance scoring

        Returns:
            Processing results dictionary
        """
        if not self.auto_ingest_service:
            logger.warning("Auto-ingest service not available")
            return {"success": False, "error": "Auto-ingest service not available"}

        if not self.should_auto_ingest():
            logger.debug("Auto-ingest is disabled, skipping pipeline")
            return {"success": True, "message": "Auto-ingest disabled", "processed": 0}

        # Create job tracking for badge system
        job_id = f"keyword-monitor-{uuid.uuid4()}"
        job = KeywordMonitorJob(job_id, topic, len(articles))
        _keyword_monitor_jobs[job_id] = job

        try:
            logger.info(f"Starting auto-ingest pipeline for {len(articles)} articles on topic '{topic}' (Job ID: {job_id})")

            # Convert articles to the format expected by the auto-ingest service
            # The news collector returns articles with 'url', 'source', etc.
            # but the auto-ingest service expects 'uri', 'news_source', etc.
            formatted_articles = []
            for article in articles:
                formatted_article = {
                    'uri': article.get('url', ''),
                    'title': article.get('title', ''),
                    'news_source': article.get('source', ''),
                    'publication_date': article.get('published_date', ''),
                    'summary': article.get('summary', ''),
                    'topic': topic,
                    'analyzed': False
                }
                formatted_articles.append(formatted_article)

            # Process articles through the automated pipeline
            results = await self.auto_ingest_service.process_articles_batch(formatted_articles, topic, keywords)

            # Update job status
            job.status = "completed"
            job.results = results
            job.completed_at = datetime.utcnow()

            # Schedule cleanup after 2 minutes
            asyncio.create_task(self._cleanup_job_after_delay(job_id, 120))

            logger.info(f"Auto-ingest pipeline completed: {results} (Job ID: {job_id})")
            return results

        except Exception as e:
            logger.error(f"Error in auto-ingest pipeline: {e} (Job ID: {job_id})")
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()

            # Schedule cleanup after 2 minutes even on failure
            asyncio.create_task(self._cleanup_job_after_delay(job_id, 120))

            return {"success": False, "error": str(e)}

    async def _cleanup_job_after_delay(self, job_id: str, delay_seconds: int):
        """Clean up completed job after a delay"""
        await asyncio.sleep(delay_seconds)
        if job_id in _keyword_monitor_jobs:
            logger.debug(f"Cleaning up keyword monitor job {job_id}")
            del _keyword_monitor_jobs[job_id]

async def run_keyword_monitor():
    """Background task to periodically check keywords"""
    global _background_task_status
    db = Database()
    monitor = KeywordMonitor(db)
    logger.info("Keyword monitor background task started")
    _background_task_status["running"] = True

    # Calculate next check time immediately
    next_check = datetime.now() + timedelta(seconds=monitor.check_interval)
    _background_task_status["next_check_time"] = next_check

    logger.info(f"Keyword monitor scheduled - first check in {monitor.check_interval} seconds at {next_check.strftime('%H:%M:%S')}")

    # Sleep first before starting the checking loop
    await asyncio.sleep(monitor.check_interval)
    
    # Track checkpoint intervals
    last_checkpoint = datetime.now()
    checkpoint_interval = 300  # 5 minutes

    while True:
        try:
            # Perform periodic WAL checkpoint to prevent WAL file growth
            current_time = datetime.now()
            if (current_time - last_checkpoint).total_seconds() >= checkpoint_interval:
                try:
                    db.perform_wal_checkpoint("PASSIVE")
                    last_checkpoint = current_time
                    logger.debug("Performed periodic WAL checkpoint")
                except Exception as checkpoint_error:
                    logger.warning(f"WAL checkpoint failed: {checkpoint_error}")
            
            # Check if polling is enabled
            is_enabled = db.facade.get_keyword_monitor_polling_enabled()

            if is_enabled:
                logger.info("Starting scheduled keyword check")
                _background_task_status["last_check_time"] = datetime.now()
                _background_task_status["last_error"] = None

                try:
                    result = await monitor.check_keywords()
                    if result.get("success", False):
                        logger.info(
                            f"Scheduled keyword check completed successfully. "
                            f"Found {result.get('new_articles', 0)} new articles."
                        )
                        # Perform WAL checkpoint after successful operations
                        try:
                            db.perform_wal_checkpoint("PASSIVE")
                        except Exception as checkpoint_error:
                            logger.warning(f"Post-operation WAL checkpoint failed: {checkpoint_error}")
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        logger.error(f"Scheduled keyword check failed: {error_msg}")
                        _background_task_status["last_error"] = error_msg
                except Exception as check_error:
                    error_msg = str(check_error)
                    logger.error(f"Error during scheduled keyword check: {error_msg}", exc_info=True)
                    _background_task_status["last_error"] = error_msg
            else:
                logger.debug("Keyword checking is disabled in settings, skipping check")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Keyword monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg
            # Sleep a short time before retrying after error to prevent CPU spinning
            await asyncio.sleep(30)

        try:
            # Refresh interval from settings in case it was changed
            settings = db.facade.get_keyword_monitor_interval()
            if settings:
                monitor.check_interval = settings[0] * settings[1]  # interval * unit
        except Exception as e:
            logger.error(f"Error refreshing check interval settings: {str(e)}", exc_info=True)
        
        # Calculate next check time
        next_check = datetime.now() + timedelta(seconds=monitor.check_interval)
        _background_task_status["next_check_time"] = next_check
        
        logger.debug(f"Sleeping for {monitor.check_interval} seconds until next keyword check")
        await asyncio.sleep(monitor.check_interval) 