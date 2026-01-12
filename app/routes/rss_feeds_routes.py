"""
API routes for RSS feed management.
Handles CRUD operations, feed testing, and manual fetch triggering.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

from app.database import get_database_instance
from app.security.session import verify_session
from app.collectors.rss_collector import RSSCollector
from sqlalchemy import select, insert, update, delete, text
from app.database_models import t_rss_feeds, t_rss_feed_monitor_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rss-feeds", tags=["rss-feeds"])


# Pydantic models for request/response
class RSSFeedCreate(BaseModel):
    name: str
    url: str
    topic: str
    description: Optional[str] = None
    is_active: bool = True
    check_interval: int = 60
    interval_unit: str = "minutes"
    relevance_threshold: int = 0  # 0 = skip filtering, 1-100 = threshold %


class RSSFeedUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    check_interval: Optional[int] = None
    interval_unit: Optional[str] = None
    relevance_threshold: Optional[int] = None


class RSSFeedResponse(BaseModel):
    id: int
    name: str
    url: str
    topic: str
    description: Optional[str]
    is_active: bool
    check_interval: int
    interval_unit: str
    relevance_threshold: int
    last_checked_at: Optional[datetime]
    last_article_date: Optional[datetime]
    articles_fetched: int
    articles_enriched: int
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


@router.get("")
async def list_rss_feeds(
    topic: Optional[str] = None,
    is_active: Optional[bool] = None,
    session=Depends(verify_session)
) -> Dict:
    """List all RSS feeds, optionally filtered by topic or active status."""
    try:
        db = get_database_instance()

        query = select(t_rss_feeds)

        if topic:
            query = query.where(t_rss_feeds.c.topic == topic)
        if is_active is not None:
            query = query.where(t_rss_feeds.c.is_active == is_active)

        query = query.order_by(t_rss_feeds.c.created_at.desc())

        conn = db._temp_get_connection()
        result = conn.execute(query)
        feeds = [dict(row._mapping) for row in result]

        # Convert datetime objects to ISO strings for JSON serialization
        for feed in feeds:
            for key in ['last_checked_at', 'last_article_date', 'created_at', 'updated_at']:
                if feed.get(key) and isinstance(feed[key], datetime):
                    feed[key] = feed[key].isoformat()

        return {"success": True, "feeds": feeds, "count": len(feeds)}

    except Exception as e:
        logger.error(f"Failed to list RSS feeds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{feed_id}")
async def get_rss_feed(feed_id: int, session=Depends(verify_session)) -> Dict:
    """Get a specific RSS feed by ID."""
    try:
        db = get_database_instance()

        query = select(t_rss_feeds).where(t_rss_feeds.c.id == feed_id)

        conn = db._temp_get_connection()
        result = conn.execute(query)
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="RSS feed not found")

        feed = dict(row._mapping)

        # Convert datetime objects
        for key in ['last_checked_at', 'last_article_date', 'created_at', 'updated_at']:
            if feed.get(key) and isinstance(feed[key], datetime):
                feed[key] = feed[key].isoformat()

        return {"success": True, "feed": feed}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get RSS feed {feed_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_rss_feed(feed: RSSFeedCreate, session=Depends(verify_session)) -> Dict:
    """Create a new RSS feed."""
    try:
        db = get_database_instance()

        # Validate feed URL
        test_result = await RSSCollector.test_feed_url(feed.url)
        if not test_result.get('valid'):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid RSS feed URL: {test_result.get('error', 'Unknown error')}"
            )

        # Insert the feed
        stmt = insert(t_rss_feeds).values(
            name=feed.name,
            url=feed.url,
            topic=feed.topic,
            description=feed.description,
            is_active=feed.is_active,
            check_interval=feed.check_interval,
            interval_unit=feed.interval_unit,
            relevance_threshold=feed.relevance_threshold,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        ).returning(t_rss_feeds.c.id)

        conn = db._temp_get_connection()
        result = conn.execute(stmt)
        feed_id = result.fetchone()[0]
        conn.commit()

        logger.info(f"Created RSS feed '{feed.name}' (ID: {feed_id})")

        return {
            "success": True,
            "message": "RSS feed created successfully",
            "feed_id": feed_id,
            "feed_info": {
                "title": test_result.get('title'),
                "entry_count": test_result.get('entry_count'),
                "feed_type": test_result.get('feed_type')
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create RSS feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{feed_id}")
async def update_rss_feed(
    feed_id: int,
    feed_update: RSSFeedUpdate,
    session=Depends(verify_session)
) -> Dict:
    """Update an existing RSS feed."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Check if feed exists
        check_query = select(t_rss_feeds).where(t_rss_feeds.c.id == feed_id)
        result = conn.execute(check_query)
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="RSS feed not found")

        # Build update dict with only provided values
        update_data = {k: v for k, v in feed_update.model_dump().items() if v is not None}

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # If URL is being updated, validate it
        if 'url' in update_data:
            test_result = await RSSCollector.test_feed_url(update_data['url'])
            if not test_result.get('valid'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid RSS feed URL: {test_result.get('error', 'Unknown error')}"
                )

        update_data['updated_at'] = datetime.now(timezone.utc)

        stmt = update(t_rss_feeds).where(
            t_rss_feeds.c.id == feed_id
        ).values(**update_data)

        conn.execute(stmt)
        conn.commit()

        logger.info(f"Updated RSS feed {feed_id}")

        return {"success": True, "message": "RSS feed updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update RSS feed {feed_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{feed_id}")
async def delete_rss_feed(feed_id: int, session=Depends(verify_session)) -> Dict:
    """Delete an RSS feed."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Check if feed exists
        check_query = select(t_rss_feeds).where(t_rss_feeds.c.id == feed_id)
        result = conn.execute(check_query)
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="RSS feed not found")

        # Delete the feed
        stmt = delete(t_rss_feeds).where(t_rss_feeds.c.id == feed_id)
        conn.execute(stmt)
        conn.commit()

        logger.info(f"Deleted RSS feed {feed_id}")

        return {"success": True, "message": "RSS feed deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete RSS feed {feed_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{feed_id}/test")
async def test_rss_feed(feed_id: int, session=Depends(verify_session)) -> Dict:
    """Test an RSS feed URL and return feed information."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Get the feed URL
        query = select(t_rss_feeds.c.url).where(t_rss_feeds.c.id == feed_id)
        result = conn.execute(query)
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="RSS feed not found")

        url = row[0]
        test_result = await RSSCollector.test_feed_url(url)

        return {"success": True, "test_result": test_result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test RSS feed {feed_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-url")
async def test_rss_url(data: Dict, session=Depends(verify_session)) -> Dict:
    """Test a feed URL before creating a feed."""
    try:
        url = data.get('url')
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        test_result = await RSSCollector.test_feed_url(url)

        return {"success": True, "test_result": test_result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test RSS URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{feed_id}/fetch")
async def fetch_rss_feed(
    feed_id: int,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
) -> Dict:
    """Manually trigger article fetch for a specific RSS feed."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Get the feed
        query = select(t_rss_feeds).where(t_rss_feeds.c.id == feed_id)
        result = conn.execute(query)
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="RSS feed not found")

        feed = dict(row._mapping)

        # Run fetch in background
        background_tasks.add_task(
            _fetch_feed_articles,
            feed_id=feed_id,
            feed_url=feed['url'],
            topic=feed['topic'],
            last_article_date=feed.get('last_article_date'),
            relevance_threshold=feed.get('relevance_threshold', 0)
        )

        return {
            "success": True,
            "message": f"Fetch started for feed '{feed['name']}'",
            "feed_id": feed_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start fetch for RSS feed {feed_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_feed_articles(
    feed_id: int,
    feed_url: str,
    topic: str,
    last_article_date: Optional[datetime] = None,
    relevance_threshold: int = 0
):
    """Background task to fetch articles from an RSS feed.

    Args:
        relevance_threshold: Per-feed relevance threshold (0=skip filtering, 1-100=threshold %)
    """
    try:
        from app.database import get_database_instance
        from app.services.automated_ingest_service import AutomatedIngestService
        from app.database_query_facade import DatabaseQueryFacade

        db = get_database_instance()
        collector = RSSCollector()

        logger.info(f"Fetching articles from RSS feed {feed_id}: {feed_url}")

        # Fetch articles from the feed
        articles = await collector.fetch_feed(
            feed_url=feed_url,
            topic=topic,
            max_results=50,
            since=last_article_date
        )

        logger.info(f"Found {len(articles)} articles from feed {feed_id}")
        new_articles_count = 0

        if articles:
            # Store articles using the database facade (same as keyword monitor)
            for article in articles:
                try:
                    article_url = article.get('url', '').strip()
                    if not article_url:
                        continue

                    # Check if article exists
                    article_exists = db.facade.article_exists((article_url,))

                    if not article_exists:
                        # Store article directly (no keyword association for RSS)
                        from sqlalchemy import insert as sql_insert
                        from app.database_models import t_articles

                        conn = db._temp_get_connection()
                        conn.execute(sql_insert(t_articles).values(
                            uri=article_url,
                            title=article.get('title', '')[:500] if article.get('title') else '',
                            news_source=article.get('source', 'RSS')[:200] if article.get('source') else 'RSS',
                            publication_date=article.get('published_date'),
                            summary=article.get('summary', '')[:2000] if article.get('summary') else '',
                            topic=topic,
                            analyzed=False
                        ))
                        conn.commit()
                        new_articles_count += 1
                        logger.info(f"Stored RSS article: {article_url}")
                    else:
                        logger.debug(f"RSS article already exists: {article_url}")

                except Exception as e:
                    logger.error(f"Error storing RSS article: {e}")
                    continue

            logger.info(f"Stored {new_articles_count} new articles from RSS feed {feed_id}")

            # Run auto-ingest pipeline if enabled and we have new articles
            enriched_count = 0
            if new_articles_count > 0:
                try:
                    ingest_service = AutomatedIngestService(db)

                    # Check if auto-ingest is enabled
                    settings = db.facade.get_or_create_keyword_monitor_settings()
                    auto_ingest_enabled = settings.get('auto_ingest_enabled', False) if settings else False

                    if auto_ingest_enabled:
                        logger.info(f"Running auto-ingest pipeline for {new_articles_count} RSS articles")
                        # Get keywords for the topic to use for relevance scoring
                        topic_keywords = db.facade.get_monitored_keywords_for_topic((topic,))

                        # Format articles for batch processing (needs 'uri' field)
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
                            if relevance_threshold == 0:
                                threshold_override = 0  # Signal to skip filtering
                            elif relevance_threshold > 0:
                                threshold_override = relevance_threshold / 100.0  # Convert to 0.0-1.0 range

                            # Process through batch enrichment pipeline
                            result = await ingest_service.process_articles_batch(
                                articles=batch_articles,
                                topic=topic,
                                keywords=topic_keywords,
                                relevance_threshold_override=threshold_override
                            )
                            enriched_count = result.get('saved', 0)
                            logger.info(f"Auto-ingest completed: {result}")

                            # Create completion notification
                            try:
                                db.facade.create_notification(
                                    username=None,  # System-wide notification
                                    type='auto_ingest_complete',
                                    title='RSS Feed Complete',
                                    message=f'Fetched {new_articles_count} articles, {enriched_count} enriched from RSS feed',
                                    link='/gather'
                                )
                            except Exception as notif_err:
                                logger.error(f"Failed to create RSS notification: {notif_err}")
                    else:
                        logger.info("Auto-ingest is disabled, skipping enrichment")
                        # Still notify about articles collected
                        try:
                            db.facade.create_notification(
                                username=None,
                                type='auto_ingest_complete',
                                title='RSS Feed Complete',
                                message=f'Fetched {new_articles_count} new articles from RSS feed (enrichment disabled)',
                                link='/gather'
                            )
                        except Exception as notif_err:
                            logger.error(f"Failed to create RSS notification: {notif_err}")
                except Exception as e:
                    logger.error(f"Auto-ingest pipeline error: {e}")

            # Update feed status
            newest_date = max(
                (collector._parse_date(a.get('published_date')) for a in articles if a.get('published_date')),
                default=None
            )

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

            conn = db._temp_get_connection()
            conn.execute(update_stmt)
            conn.commit()

        else:
            # No new articles, just update last_checked
            update_stmt = update(t_rss_feeds).where(
                t_rss_feeds.c.id == feed_id
            ).values(
                last_checked_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            conn = db._temp_get_connection()
            conn.execute(update_stmt)
            conn.commit()

        logger.info(f"Completed fetch for RSS feed {feed_id}: {new_articles_count} new articles")

    except Exception as e:
        logger.error(f"Error fetching RSS feed {feed_id}: {e}", exc_info=True)

        # Update feed with error
        try:
            db = get_database_instance()
            update_stmt = update(t_rss_feeds).where(
                t_rss_feeds.c.id == feed_id
            ).values(
                last_checked_at=datetime.now(timezone.utc),
                last_error=str(e)[:500],
                updated_at=datetime.now(timezone.utc)
            )

            conn = db._temp_get_connection()
            conn.execute(update_stmt)
            conn.commit()
        except Exception as update_err:
            logger.error(f"Failed to update feed error status: {update_err}")


@router.get("/status/monitor")
async def get_monitor_status(session=Depends(verify_session)) -> Dict:
    """Get RSS feed monitor status."""
    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        query = select(t_rss_feed_monitor_status).where(
            t_rss_feed_monitor_status.c.id == 1
        )

        result = conn.execute(query)
        row = result.fetchone()

        if row:
            status = dict(row._mapping)
            for key in ['last_check_time', 'next_check_time', 'created_at', 'updated_at']:
                if status.get(key) and isinstance(status[key], datetime):
                    status[key] = status[key].isoformat()
        else:
            status = {
                'is_running': False,
                'feeds_checked': 0,
                'articles_fetched': 0
            }

        # Get feed counts
        active_query = select(t_rss_feeds).where(t_rss_feeds.c.is_active == True)
        total_query = select(t_rss_feeds)

        active_count = len(list(conn.execute(active_query)))
        total_count = len(list(conn.execute(total_query)))

        status['active_feeds'] = active_count
        status['total_feeds'] = total_count

        return {"success": True, "status": status}

    except Exception as e:
        logger.error(f"Failed to get monitor status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
