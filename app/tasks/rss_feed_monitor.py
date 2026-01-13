"""
RSS Feed Monitor - Background task for scheduled RSS feed fetching.
Each feed has its own schedule based on check_interval.
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
from sqlalchemy import text, select, update

from app.database import Database, get_database_instance
from app.database_models import t_rss_feeds, t_rss_feed_monitor_status
from app.collectors.rss_collector import RSSCollector

logger = logging.getLogger(__name__)

# Global status tracking
_monitor_status = {
    "running": False,
    "last_check_time": None,
    "feeds_checked": 0,
    "articles_fetched": 0,
    "last_error": None
}


def get_monitor_status() -> Dict:
    """Get the current status of the RSS feed monitor."""
    return _monitor_status.copy()


class RSSFeedMonitor:
    """Monitor for scheduled RSS feed fetching."""

    def __init__(self, db: Database):
        self.db = db
        self.check_interval_seconds = 60  # Check for due feeds every minute

    async def get_due_feeds(self) -> List[Dict]:
        """Get feeds that are due for checking based on their individual schedules."""
        try:
            now = datetime.now(timezone.utc)

            # Query for active feeds that are due
            query = select(t_rss_feeds).where(t_rss_feeds.c.is_active == True)

            conn = self.db._temp_get_connection()
            result = conn.execute(query)
            feeds = [dict(row._mapping) for row in result]

            due_feeds = []
            for feed in feeds:
                # Calculate if feed is due
                last_checked = feed.get('last_checked_at')
                interval = feed.get('check_interval', 60)
                unit = feed.get('interval_unit', 'minutes')

                # Convert interval to timedelta
                if unit == 'hours':
                    interval_delta = timedelta(hours=interval)
                elif unit == 'days':
                    interval_delta = timedelta(days=interval)
                else:  # minutes
                    interval_delta = timedelta(minutes=interval)

                # Check if due
                if last_checked is None:
                    # Never checked, is due
                    due_feeds.append(feed)
                elif now >= last_checked + interval_delta:
                    # Past due time
                    due_feeds.append(feed)

            return due_feeds

        except Exception as e:
            logger.error(f"Error getting due feeds: {e}")
            return []

    async def fetch_feed(self, feed: Dict) -> int:
        """Fetch articles from a single RSS feed."""
        feed_id = feed['id']
        feed_url = feed['url']
        topic = feed['topic']
        feed_name = feed['name']
        last_article_date = feed.get('last_article_date')
        relevance_threshold = feed.get('relevance_threshold', 0)
        default_factual_reporting = feed.get('default_factual_reporting')

        try:
            collector = RSSCollector()

            logger.info(f"Fetching RSS feed '{feed_name}' (ID: {feed_id})")

            # Fetch articles
            articles = await collector.fetch_feed(
                feed_url=feed_url,
                topic=topic,
                max_results=50,
                since=last_article_date
            )

            articles_count = len(articles)
            new_articles_count = 0
            logger.info(f"Found {articles_count} articles from feed '{feed_name}'")

            if articles:
                # Store articles using database facade (same as keyword monitor)
                for article in articles:
                    stored = await self._store_article(article, topic)
                    if stored:
                        new_articles_count += 1

                # Find newest article date
                newest_date = None
                for article in articles:
                    pub_date = collector._parse_date(article.get('published_date'))
                    if pub_date and (newest_date is None or pub_date > newest_date):
                        newest_date = pub_date

                # Run auto-ingest if enabled and we have new articles
                enriched_count = 0
                if new_articles_count > 0:
                    enriched_count = await self._run_auto_ingest(
                        articles, topic, relevance_threshold, default_factual_reporting
                    )

                # Update feed status
                update_stmt = update(t_rss_feeds).where(
                    t_rss_feeds.c.id == feed_id
                ).values(
                    last_checked_at=datetime.now(timezone.utc),
                    last_article_date=newest_date or datetime.now(timezone.utc),
                    articles_fetched=t_rss_feeds.c.articles_fetched + new_articles_count,
                    articles_enriched=t_rss_feeds.c.articles_enriched + enriched_count,
                    last_error=None,
                    updated_at=datetime.now(timezone.utc)
                )
            else:
                # No new articles
                update_stmt = update(t_rss_feeds).where(
                    t_rss_feeds.c.id == feed_id
                ).values(
                    last_checked_at=datetime.now(timezone.utc),
                    last_error=None,
                    updated_at=datetime.now(timezone.utc)
                )

            conn = self.db._temp_get_connection()
            conn.execute(update_stmt)
            conn.commit()

            return new_articles_count

        except Exception as e:
            logger.error(f"Error fetching feed '{feed_name}': {e}")

            # Update feed with error
            update_stmt = update(t_rss_feeds).where(
                t_rss_feeds.c.id == feed_id
            ).values(
                last_checked_at=datetime.now(timezone.utc),
                last_error=str(e)[:500],
                updated_at=datetime.now(timezone.utc)
            )

            conn = self.db._temp_get_connection()
            conn.execute(update_stmt)
            conn.commit()

            return 0

    async def _store_article(self, article: Dict, topic: str) -> bool:
        """Store an article directly (no keyword association for RSS)."""
        from sqlalchemy import insert as sql_insert
        from app.database_models import t_articles

        url = article.get('url', '').strip()
        if not url:
            return False

        try:
            # Check if article exists
            article_exists = self.db.facade.article_exists((url,))

            if not article_exists:
                # Store article directly
                conn = self.db._temp_get_connection()
                conn.execute(sql_insert(t_articles).values(
                    uri=url,
                    title=(article.get('title', '') or '')[:500],
                    news_source=(article.get('source', 'RSS') or 'RSS')[:200],
                    publication_date=article.get('published_date'),
                    summary=(article.get('summary', '') or '')[:2000],
                    topic=topic,
                    analyzed=False
                ))
                conn.commit()
                logger.debug(f"Stored RSS article: {url}")
                return True
            else:
                logger.debug(f"RSS article already exists: {url}")
                return False

        except Exception as e:
            logger.error(f"Error storing article: {e}")
            return False

    async def _run_auto_ingest(
        self,
        articles: List[Dict],
        topic: str,
        relevance_threshold: int = None,
        default_factual_reporting: str = None
    ) -> int:
        """Run enrichment pipeline for RSS articles.

        RSS feeds always run enrichment - they have their own relevance threshold
        and are not tied to the keyword monitor's auto-ingest setting.

        Args:
            articles: List of article data from RSS feed
            topic: Topic name for context
            relevance_threshold: Per-feed relevance threshold (0=skip filtering, 1-100=threshold %)
            default_factual_reporting: Factual reporting level to set on articles ('very high', 'high', etc.)

        Returns:
            Number of articles successfully enriched
        """
        try:
            from app.services.automated_ingest_service import AutomatedIngestService

            # RSS feeds always enrich - they have their own relevance threshold setting
            # (not tied to keyword monitor's auto-ingest setting)
            logger.info(f"Running enrichment pipeline for RSS articles in topic '{topic}'")
            ingest_service = AutomatedIngestService(self.db)

            # Get keywords for the topic
            topic_keywords = self.db.facade.get_monitored_keywords_for_topic((topic,))

            # Format articles for batch processing
            batch_articles = []
            for article in articles:
                article_url = article.get('url', '').strip()
                if article_url:
                    batch_articles.append({
                        'uri': article_url,
                        'url': article_url,
                        'title': article.get('title', ''),
                        'news_source': article.get('source', 'RSS'),  # Use news_source key for pipeline compatibility
                        'published_date': article.get('published_date'),
                        'summary': article.get('summary', ''),
                        'topic': topic  # Include topic for pipeline consistency
                    })

            if batch_articles:
                # Convert relevance_threshold from percentage (0-100) to decimal (0.0-1.0)
                # 0 = skip filtering, otherwise convert to decimal
                threshold_override = None
                if relevance_threshold is not None:
                    if relevance_threshold == 0:
                        threshold_override = 0  # Signal to skip filtering
                    else:
                        threshold_override = relevance_threshold / 100.0  # Convert to 0.0-1.0 range

                result = await ingest_service.process_articles_batch(
                    articles=batch_articles,
                    topic=topic,
                    keywords=topic_keywords,
                    relevance_threshold_override=threshold_override
                )
                saved = result.get('saved', 0)
                logger.info(f"Auto-ingest completed: {result}")

                # Apply default_factual_reporting to enriched articles if set
                if default_factual_reporting and saved > 0:
                    try:
                        from app.database_models import t_articles
                        article_uris = [a['uri'] for a in batch_articles if a.get('uri')]
                        if article_uris:
                            update_factual_stmt = update(t_articles).where(
                                t_articles.c.uri.in_(article_uris)
                            ).values(
                                factual_reporting=default_factual_reporting
                            )
                            conn = self.db._temp_get_connection()
                            conn.execute(update_factual_stmt)
                            conn.commit()
                            logger.info(f"Set factual_reporting='{default_factual_reporting}' for {len(article_uris)} RSS articles")
                    except Exception as fr_err:
                        logger.error(f"Failed to set factual_reporting on RSS articles: {fr_err}")

                # Create completion notification
                try:
                    self.db.facade.create_notification(
                        username=None,  # System-wide notification
                        type='auto_ingest_complete',
                        title='RSS Feed Complete',
                        message=f'Scheduled fetch: {len(articles)} articles, {saved} enriched',
                        link='/gather'
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to create RSS notification: {notif_err}")

                return saved

        except Exception as e:
            logger.error(f"Auto-ingest pipeline error: {e}")

        return 0

    def _update_monitor_status(
        self,
        is_running: Optional[bool] = None,
        last_check_time: Optional[datetime] = None,
        feeds_checked: Optional[int] = None,
        articles_fetched: Optional[int] = None,
        last_error: Optional[str] = None
    ):
        """Update the monitor status in database."""
        global _monitor_status

        try:
            updates = []
            params = {"id": 1}

            if is_running is not None:
                updates.append("is_running = :running")
                params["running"] = is_running
                _monitor_status["running"] = is_running

            if last_check_time is not None:
                updates.append("last_check_time = :last_check")
                params["last_check"] = last_check_time
                _monitor_status["last_check_time"] = last_check_time

            if feeds_checked is not None:
                updates.append("feeds_checked = :feeds")
                params["feeds"] = feeds_checked
                _monitor_status["feeds_checked"] = feeds_checked

            if articles_fetched is not None:
                updates.append("articles_fetched = :articles")
                params["articles"] = articles_fetched
                _monitor_status["articles_fetched"] = articles_fetched

            if last_error is not None:
                updates.append("last_error = :error")
                params["error"] = last_error[:500] if last_error else None
                _monitor_status["last_error"] = last_error
            elif last_error == "":
                updates.append("last_error = NULL")
                _monitor_status["last_error"] = None

            updates.append("updated_at = NOW()")

            if updates:
                conn = self.db._temp_get_connection()
                conn.execute(text(f"""
                    UPDATE rss_feed_monitor_status
                    SET {', '.join(updates)}
                    WHERE id = :id
                """), params)
                conn.commit()

        except Exception as e:
            logger.error(f"Error updating monitor status: {e}")

    async def run_check_cycle(self):
        """Run one check cycle - fetch all due feeds."""
        try:
            self._update_monitor_status(is_running=True)

            due_feeds = await self.get_due_feeds()

            if not due_feeds:
                self._update_monitor_status(
                    is_running=False,
                    last_check_time=datetime.now(timezone.utc)
                )
                return

            logger.info(f"Found {len(due_feeds)} RSS feeds due for checking")

            total_articles = 0
            for feed in due_feeds:
                try:
                    count = await self.fetch_feed(feed)
                    total_articles += count
                except Exception as e:
                    logger.error(f"Error processing feed {feed['id']}: {e}")

            self._update_monitor_status(
                is_running=False,
                last_check_time=datetime.now(timezone.utc),
                feeds_checked=len(due_feeds),
                articles_fetched=total_articles,
                last_error=""
            )

            logger.info(f"RSS feed check cycle complete: {len(due_feeds)} feeds, {total_articles} articles")

        except Exception as e:
            logger.error(f"Error in RSS feed check cycle: {e}")
            self._update_monitor_status(
                is_running=False,
                last_error=str(e)
            )


async def run_rss_feed_monitor():
    """Main entry point for the RSS feed monitor background task."""
    logger.info("Starting RSS feed monitor background task")

    try:
        db = get_database_instance()
        monitor = RSSFeedMonitor(db)

        while True:
            try:
                await monitor.run_check_cycle()
            except Exception as e:
                logger.error(f"Error in RSS feed monitor cycle: {e}")

            # Wait before next check (every minute)
            await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Fatal error in RSS feed monitor: {e}")
        raise
