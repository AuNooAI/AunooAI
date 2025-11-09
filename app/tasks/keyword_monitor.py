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
        self.collector = None  # Legacy single collector (deprecated)
        self.collectors = {}  # Dictionary of collectors {provider_name: collector_instance}
        self.active_providers = []  # List of active provider names
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
                    self.check_interval = 1440  # 24 hours
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
            self.check_interval = 1440  # 24 hours
            self.search_fields = "title,description,content"
            self.language = "en"
            self.sort_by = "publishedAt"
            self.page_size = 10
            self.is_enabled = True
            self.daily_request_limit = 100
            self.search_date_range = 7  # Default to 7 days
            self.provider = 'newsapi'  # Default provider

    def _create_collector(self, provider: str):
        """Factory method to create individual collector instance"""
        import os

        if provider == 'newsapi':
            from app.collectors.newsapi_collector import NewsAPICollector
            newsapi_key = os.getenv('PROVIDER_NEWSAPI_API_KEY') or os.getenv('PROVIDER_NEWSAPI_KEY')
            if not newsapi_key:
                raise ValueError(f"NewsAPI key not configured. Please set PROVIDER_NEWSAPI_API_KEY environment variable.")
            return NewsAPICollector(self.db)

        elif provider == 'thenewsapi':
            from app.collectors.thenewsapi_collector import TheNewsAPICollector
            return TheNewsAPICollector()

        elif provider == 'newsdata':
            from app.collectors.newsdata_collector import NewsdataCollector
            if not NewsdataCollector.is_configured():
                raise ValueError("NewsData.io API key not configured in environment variables")
            return NewsdataCollector()

        elif provider == 'bluesky':
            from app.collectors.bluesky_collector import BlueskyCollector
            return BlueskyCollector()

        elif provider == 'semantic_scholar':
            from app.collectors.semantic_scholar_collector import SemanticScholarCollector
            return SemanticScholarCollector()

        elif provider == 'arxiv':
            from app.collectors.arxiv_collector import ArxivCollector
            return ArxivCollector()

        else:
            raise ValueError(f"Unknown provider '{provider}'. Valid options: 'newsapi', 'thenewsapi', 'newsdata', 'bluesky', 'semantic_scholar', 'arxiv'")

    def _init_collectors(self):
        """Initialize all selected collectors (multi-collector support)"""
        try:
            import json

            # Get providers from database as JSON array
            providers_json = self.db.facade.get_keyword_monitoring_providers()
            self.active_providers = json.loads(providers_json)

            logger.info(f"Initializing collectors for providers: {self.active_providers}")

            self.collectors = {}
            initialized_count = 0

            for provider in self.active_providers:
                try:
                    collector = self._create_collector(provider)
                    if collector:
                        self.collectors[provider] = collector
                        initialized_count += 1
                        logger.info(f"✓ Initialized collector: {provider}")
                except Exception as e:
                    logger.error(f"✗ Failed to initialize {provider}: {e}")
                    # Continue with other collectors

            if initialized_count == 0:
                logger.error("No collectors were initialized successfully")
                return False

            # Also set first collector as legacy self.collector for backward compatibility
            if self.collectors:
                self.collector = list(self.collectors.values())[0]

            self.last_collector_init_attempt = datetime.now()
            logger.info(f"Successfully initialized {initialized_count}/{len(self.active_providers)} collectors")
            return True

        except Exception as e:
            logger.error(f"Error initializing collectors: {str(e)}")
            return False

    def _init_collector(self):
        """Legacy method - now delegates to _init_collectors for multi-collector support"""
        return self._init_collectors()

    def _deduplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles based on URL, prioritizing providers with better metadata"""
        seen_urls = {}
        unique_articles = []

        # Provider priority: newsapi > thenewsapi > newsdata > semantic_scholar/bluesky > arxiv
        provider_priority = {
            'newsapi': 5,
            'thenewsapi': 4,
            'newsdata': 3,
            'semantic_scholar': 2,
            'bluesky': 2,
            'arxiv': 1
        }

        for article in articles:
            url = article.get('url', '').strip()
            if not url:
                continue

            if url not in seen_urls:
                seen_urls[url] = article
                unique_articles.append(article)
            else:
                # Article already exists - keep the one from higher priority provider
                existing = seen_urls[url]

                current_priority = provider_priority.get(
                    article.get('collector_source', ''), 0
                )
                existing_priority = provider_priority.get(
                    existing.get('collector_source', ''), 0
                )

                if current_priority > existing_priority:
                    # Replace with higher priority version
                    seen_urls[url] = article
                    unique_articles = [
                        a for a in unique_articles if a.get('url') != url
                    ]
                    unique_articles.append(article)

        logger.info(
            f"Deduplicated {len(articles)} articles → {len(unique_articles)} unique articles"
        )
        return unique_articles

    async def _search_with_collector(
        self,
        provider: str,
        collector,
        keyword_text: str,
        topic: str,
        start_date: datetime
    ) -> List[Dict]:
        """Search with individual collector, handling errors gracefully"""
        try:
            logger.info(f"Searching with {provider} for keyword: '{keyword_text}'...")

            articles = await collector.search_articles(
                query=keyword_text,
                topic=topic,
                max_results=self.page_size,
                start_date=start_date,
                search_fields=self.search_fields,
                language=self.language,
                sort_by=self.sort_by
            )

            # Tag articles with provider source
            for article in articles:
                article['collector_source'] = provider

            logger.info(f"{provider}: Found {len(articles)} articles")
            return articles

        except Exception as e:
            logger.error(f"{provider} search failed: {e}")
            return []

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

    async def check_keywords(self, group_id=None, progress_callback=None, username=None):
        """Check all keywords for new matches

        Args:
            group_id: Optional group ID to filter keywords by specific group
            progress_callback: Optional callback function(processed, current) for progress updates
            username: Optional username for notifications
        """
        self.username = username  # Store for notification use
        if group_id:
            logger.info(f"Starting keyword check for group {group_id}...")
        else:
            logger.info("Starting keyword check for all groups...")
        new_articles_count = 0
        processed_keywords = 0

        # CRITICAL FIX: Clean up any poisoned connections before heavy processing
        # This prevents "Can't reconnect until invalid transaction is rolled back" errors
        try:
            self.db.reset_poisoned_connections()
        except Exception as e:
            logger.warning(f"Connection cleanup failed: {e}")

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

                    # MULTI-COLLECTOR: Search across all active collectors in parallel
                    search_tasks = []
                    for provider, collector in self.collectors.items():
                        task = self._search_with_collector(
                            provider=provider,
                            collector=collector,
                            keyword_text=keyword_text,
                            topic=topic,
                            start_date=start_date
                        )
                        search_tasks.append(task)

                    # Execute all searches in parallel
                    results = await asyncio.gather(*search_tasks, return_exceptions=True)

                    # Combine results from all collectors
                    all_articles = []
                    for i, result in enumerate(results):
                        provider = list(self.collectors.keys())[i]

                        if isinstance(result, Exception):
                            logger.error(f"{provider} search failed: {result}")
                            continue

                        all_articles.extend(result)

                    # Deduplicate articles across providers
                    articles = self._deduplicate_articles(all_articles)

                    if not articles:
                        logger.warning(f"No articles found or error occurred for keyword: {keyword_text}")
                        continue

                    logger.info(f"Found {len(articles)} unique articles for keyword: {keyword_text} (from {len(all_articles)} total across collectors)")
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

                            # Check if auto-regenerate reports is enabled
                            if auto_ingest_results.get("saved", 0) > 0:
                                try:
                                    auto_regenerate = self.db.facade.get_auto_regenerate_reports_setting()

                                    if auto_regenerate:
                                        logger.info(f"Auto-regenerate enabled: regenerating Six Articles for topic '{topic}'")

                                        # Run regeneration in background task to avoid blocking
                                        asyncio.create_task(
                                            self._regenerate_six_articles_background(topic)
                                        )

                                        logger.info(f"Six Articles regeneration task created for topic '{topic}'")

                                except Exception as regen_err:
                                    logger.error(f"Six Articles regeneration failed: {regen_err}", exc_info=True)
                                    # Don't fail autocollect if regeneration fails

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

    async def _regenerate_six_articles_background(self, topic: str):
        """Regenerate Six Articles, Insights, and Highlights for default/first user in background"""
        try:
            from datetime import datetime, timedelta

            logger.info(f"Starting content regeneration (Six Articles + Insights + Highlights) for topic: {topic}")

            # Get first user with Six Articles config, or just first user
            first_user = self.db.facade.get_first_user_with_six_articles_config()

            if not first_user:
                # Fallback: get any user
                all_users = self.db.facade.get_all_users()
                if all_users and len(all_users) > 0:
                    first_user = all_users[0]

            if not first_user:
                logger.warning("No users found for content regeneration")
                return

            username = first_user.get('username')
            user_id = first_user.get('id') or first_user.get('user_id')
            logger.info(f"Regenerating content for user: {username}")

            # Invalidate old caches first
            self.db.facade.invalidate_six_articles_cache_for_topic(topic)
            self.db.facade.invalidate_insights_cache_for_topic(topic)

            # Load user config
            config = self.db.facade.get_six_articles_config(username) or {}
            model = config.get('model', 'gpt-4o-mini')

            # === 1. Regenerate Six Articles ===
            try:
                from app.services.news_feed_service import NewsFeedService
                from app.schemas.news_feed import NewsFeedRequest

                persona = config.get('persona', 'CEO')
                article_count = config.get('article_count', 6)

                news_feed_service = NewsFeedService(self.db)

                request = NewsFeedRequest(
                    date=None,  # Uses today
                    date_range="24h",
                    topic=topic,
                    max_articles=50,
                    model=model,
                    persona=persona,
                    article_count=article_count,
                    user_id=user_id,
                    force_regenerate=True
                )

                target_date = datetime.now()
                articles_data = await news_feed_service._get_articles_for_date_range(
                    "24h", 50, topic, target_date
                )

                if articles_data:
                    six_articles = await news_feed_service._generate_six_articles_report_cached(
                        articles_data, target_date, request
                    )
                    logger.info(f"Successfully regenerated {len(six_articles)} Six Articles for topic '{topic}'")
                else:
                    logger.warning(f"No articles found for Six Articles regeneration for topic '{topic}'")
            except Exception as six_err:
                logger.error(f"Six Articles regeneration failed: {six_err}", exc_info=True)

            # === 2. Regenerate Article Insights (Narratives) ===
            try:
                from app.routes.dashboard_routes import get_article_insights, get_topic_articles

                # Calculate date range (24 hours back)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=1)
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')

                # Create a mock session for the dependency
                mock_session = {'user': {'username': username}}

                logger.info(f"Regenerating article insights for topic '{topic}'")
                insights = await get_article_insights(
                    topic_name=topic,
                    db=self.db,
                    start_date=start_date_str,
                    end_date=end_date_str,
                    days_limit=1,
                    force_regenerate=True,
                    model=model,
                    session=mock_session
                )
                logger.info(f"Successfully regenerated {len(insights)} article insight themes for topic '{topic}'")
            except Exception as insights_err:
                logger.error(f"Article insights regeneration failed: {insights_err}", exc_info=True)

            # === 3. Regenerate Incident Tracking (Highlights) ===
            try:
                from app.routes.vector_routes import analyze_incidents
                from pydantic import BaseModel, Field
                from typing import Optional, List

                # Create request model inline to avoid import issues
                class IncidentRequest(BaseModel):
                    topic: Optional[str] = None
                    topics: Optional[List[str]] = None
                    days_limit: int = 1
                    start_date: Optional[str] = None
                    end_date: Optional[str] = None
                    max_articles: int = 100
                    model: str = 'gpt-4o-mini'
                    force_regenerate: bool = True
                    domain: Optional[str] = None
                    profile_id: Optional[int] = None
                    test_articles: Optional[List] = None

                    def get_topics_list(self):
                        if self.topics:
                            return self.topics
                        if self.topic:
                            return [self.topic]
                        return []

                # Calculate date range (24 hours back)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=1)
                start_date_str = start_date.strftime('%Y-%m-%d')
                end_date_str = end_date.strftime('%Y-%m-%d')

                incident_req = IncidentRequest(
                    topic=topic,
                    days_limit=1,
                    start_date=start_date_str,
                    end_date=end_date_str,
                    max_articles=100,
                    model=model,
                    force_regenerate=True
                )

                logger.info(f"Regenerating incident tracking (highlights) for topic '{topic}'")
                incidents = await analyze_incidents(
                    req=incident_req,
                    session=mock_session
                )

                if incidents and 'items' in incidents:
                    logger.info(f"Successfully regenerated {len(incidents['items'])} incident highlights for topic '{topic}'")
                else:
                    logger.info(f"Incident tracking regeneration completed for topic '{topic}'")
            except Exception as incidents_err:
                logger.error(f"Incident tracking regeneration failed: {incidents_err}", exc_info=True)

            # Create notification
            if username:
                try:
                    self.db.facade.create_notification(
                        username=username,
                        type='reports_regenerated',
                        title='Dashboard Content Updated',
                        message=f'Fresh Six Articles, Insights, and Highlights generated for "{topic}" with new autocollected articles.',
                        link='/news-feed'
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to create regeneration notification: {notif_err}")

        except Exception as e:
            logger.error(f"Content background regeneration failed: {e}", exc_info=True)

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