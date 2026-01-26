"""Geopolitical Hotspots API Routes

REST API endpoints for the geopolitical hotspots analysis feature.
Provides map data, statistics, and insights for global threat monitoring.
"""

import logging
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.services.geopolitical_service import (
    get_geopolitical_service,
    extract_location_with_llm,
    generate_narrative_with_llm,
    THREAT_CATEGORIES,
    RISK_LEVELS
)
from app.security.session import verify_session, verify_session_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geopolitical-hotspots", tags=["geopolitical-hotspots"])


# Response models
class HotspotSummary(BaseModel):
    id: int
    location_name: str
    country_name: Optional[str]
    intensity_score: float
    risk_level: str
    primary_category: Optional[str]
    article_count: int
    trend: Optional[str]


class OverviewStats(BaseModel):
    total_hotspots: int
    by_risk_level: dict
    total_articles: int
    recent_articles: int
    countries_affected: int
    escalating_count: int
    de_escalating_count: int
    by_category: dict
    top_hotspots: List[HotspotSummary]


class MapHotspot(BaseModel):
    id: int
    location_name: str
    location_type: str
    country_code: Optional[str]
    country_name: Optional[str]
    latitude: float
    longitude: float
    intensity_score: float
    risk_level: str
    trend: Optional[str]
    article_count: int
    recent_article_count: int
    primary_category: Optional[str]
    tags: Optional[list]
    last_article_date: Optional[str]


class CountryStats(BaseModel):
    country_code: str
    country_name: str
    total_hotspots: int
    total_articles: int
    heat_value: float
    max_risk_level: Optional[str]
    primary_category: Optional[str]


class HotspotDetail(BaseModel):
    id: int
    location_name: str
    location_type: str
    country_code: Optional[str]
    country_name: Optional[str]
    latitude: float
    longitude: float
    intensity_score: float
    risk_level: str
    trend: Optional[str]
    article_count: int
    recent_article_count: int
    primary_category: Optional[str]
    tags: Optional[list]
    topic: Optional[str]
    last_article_date: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class HotspotArticle(BaseModel):
    uri: str
    title: Optional[str]
    source: Optional[str]
    publication_date: Optional[str]
    summary: Optional[str]
    category: Optional[str]
    sentiment: Optional[str]
    relevance_score: Optional[float]
    mention_type: Optional[str]


class TimelineDataPoint(BaseModel):
    date: str
    article_count: int
    avg_intensity: float
    hotspot_count: int


class RegionData(BaseModel):
    region: str
    hotspot_count: int
    article_count: int


class CategoryData(BaseModel):
    category: str
    count: int
    avg_intensity: float
    total_articles: int


# API Endpoints

@router.get("/overview")
async def get_overview(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get dashboard overview statistics."""
    try:
        service = get_geopolitical_service()
        stats = service.get_overview_stats(topic=topic, days_back=days_back)
        return stats
    except Exception as e:
        logger.error(f"Error getting overview stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/map-data")
async def get_map_data(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    categories: Optional[str] = Query(None, description="Comma-separated threat categories"),
    risk_levels: Optional[str] = Query(None, description="Comma-separated risk levels"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get all hotspots with coordinates for map display."""
    try:
        service = get_geopolitical_service()

        # Parse comma-separated filters
        cat_list = categories.split(',') if categories else None
        risk_list = risk_levels.split(',') if risk_levels else None

        hotspots = service.get_map_data(
            topic=topic,
            categories=cat_list,
            risk_levels=risk_list,
            days_back=days_back
        )
        return {"hotspots": hotspots}
    except Exception as e:
        logger.error(f"Error getting map data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/countries")
async def get_countries(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get country-level aggregation for choropleth map."""
    try:
        service = get_geopolitical_service()
        countries = service.get_countries_data(topic=topic)
        return {"countries": countries}
    except Exception as e:
        logger.error(f"Error getting country data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hotspots")
async def list_hotspots(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    categories: Optional[str] = Query(None, description="Comma-separated threat categories"),
    risk_levels: Optional[str] = Query(None, description="Comma-separated risk levels"),
    country_code: Optional[str] = Query(None, description="Filter by country code"),
    days_back: int = Query(30, description="Days to look back"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("intensity", description="Sort field: intensity, articles, recent, name, updated"),
    sort_order: str = Query("desc", description="Sort order: asc, desc")
):
    """Get paginated list of hotspots with filters."""
    try:
        service = get_geopolitical_service()

        # Parse comma-separated filters
        cat_list = categories.split(',') if categories else None
        risk_list = risk_levels.split(',') if risk_levels else None

        hotspots, total = service.get_hotspots(
            topic=topic,
            categories=cat_list,
            risk_levels=risk_list,
            country_code=country_code,
            days_back=days_back,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "hotspots": hotspots,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error listing hotspots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hotspot/{hotspot_id}")
async def get_hotspot(hotspot_id: int):
    """Get single hotspot by ID with full details."""
    try:
        service = get_geopolitical_service()
        hotspot = service.get_hotspot_by_id(hotspot_id)

        if not hotspot:
            raise HTTPException(status_code=404, detail="Hotspot not found")

        return hotspot
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hotspot {hotspot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hotspot/{hotspot_id}/articles")
async def get_hotspot_articles(
    hotspot_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get articles linked to a hotspot."""
    try:
        service = get_geopolitical_service()
        articles, total = service.get_hotspot_articles(
            hotspot_id=hotspot_id,
            page=page,
            page_size=page_size
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "articles": articles,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error getting hotspot articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline")
async def get_timeline(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get temporal trend data for hotspots."""
    try:
        service = get_geopolitical_service()
        data = service.get_timeline_data(topic=topic, days_back=days_back)
        return {"timeline": data}
    except Exception as e:
        logger.error(f"Error getting timeline data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regions")
async def get_regions(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get regional breakdown of hotspots."""
    try:
        service = get_geopolitical_service()
        data = service.get_regions_data(topic=topic)
        return {"regions": data}
    except Exception as e:
        logger.error(f"Error getting regions data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_categories(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get distribution by threat category."""
    try:
        service = get_geopolitical_service()
        data = service.get_category_distribution(topic=topic)
        return {"categories": data}
    except Exception as e:
        logger.error(f"Error getting category data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles")
async def get_all_articles(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    category: Optional[str] = Query(None, description="Filter by threat category"),
    hotspot_id: Optional[int] = Query(None, description="Filter by hotspot ID"),
    search: Optional[str] = Query(None, description="Search in title/summary"),
    sort_by: str = Query("date", description="Sort field: date, title, relevance, intensity"),
    sort_order: str = Query("desc", description="Sort order: asc, desc")
):
    """Get all articles linked to hotspots with filters and pagination."""
    try:
        service = get_geopolitical_service()
        articles, total = service.get_all_hotspot_articles(
            page=page,
            page_size=page_size,
            risk_level=risk_level,
            category=category,
            hotspot_id=hotspot_id,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "articles": articles,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error getting articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-counts")
async def get_daily_counts(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get daily article counts with rolling average for timeline chart."""
    try:
        service = get_geopolitical_service()
        data = service.get_daily_article_counts(topic=topic, days_back=days_back)
        return {"daily_counts": data}
    except Exception as e:
        import traceback
        logger.error(f"Error getting daily counts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/day-of-week")
async def get_day_of_week_distribution(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get article count distribution by day of week."""
    try:
        service = get_geopolitical_service()
        data = service.get_day_of_week_distribution(topic=topic, days_back=days_back)
        return {"distribution": data}
    except Exception as e:
        import traceback
        logger.error(f"Error getting day of week distribution: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/category-cooccurrence")
async def get_category_cooccurrence(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get category co-occurrence data for heatmap visualization."""
    try:
        service = get_geopolitical_service()
        data = service.get_category_cooccurrence(topic=topic)
        return data
    except Exception as e:
        logger.error(f"Error getting category co-occurrence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/category-trends")
async def get_category_trends(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(90, description="Days to look back"),
    granularity: str = Query("weekly", description="Granularity: weekly or monthly")
):
    """Get category breakdown over time periods."""
    try:
        service = get_geopolitical_service()
        data = service.get_category_trends(topic=topic, days_back=days_back, granularity=granularity)
        return {"trends": data}
    except Exception as e:
        logger.error(f"Error getting category trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actors")
async def get_actors(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get key actors/entities extracted from articles."""
    try:
        service = get_geopolitical_service()
        data = service.get_actors(topic=topic, days_back=days_back)
        return {"actors": data}
    except Exception as e:
        logger.error(f"Error getting actors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/escalation-markers")
async def get_escalation_markers(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get escalation indicators from article analysis."""
    try:
        service = get_geopolitical_service()
        data = service.get_escalation_markers(topic=topic, days_back=days_back)
        return data
    except Exception as e:
        logger.error(f"Error getting escalation markers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threat-categories")
async def get_threat_categories():
    """Get list of available threat categories."""
    return {"categories": THREAT_CATEGORIES}


@router.get("/risk-levels")
async def get_risk_levels():
    """Get list of available risk levels."""
    return {"risk_levels": RISK_LEVELS}


# ============================================================================
# Article Processing Endpoints
# ============================================================================

class ProcessingStats(BaseModel):
    total_curated_articles: int
    processed_articles: int
    unprocessed_articles: int
    total_hotspots: int
    processing_percentage: float


class ProcessArticlesRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500, description="Number of articles to process")
    model: str = Field("gpt-4o-mini", description="LLM model to use for location extraction")
    topic: Optional[str] = Field(None, description="Topic to process articles from (default: Geopolitical Hotspots)")
    process_all: bool = Field(False, description="If True, process all articles including already-processed ones")


class ProcessArticlesResponse(BaseModel):
    status: str
    message: str
    articles_processed: int = 0
    hotspots_created: int = 0
    hotspots_updated: int = 0
    articles_skipped: int = 0
    errors: int = 0


@router.get("/processing-stats")
async def get_processing_stats(
    topic: Optional[str] = Query(None, description="Topic to get stats for (default: Geopolitical Hotspots)"),
    session=Depends(verify_session_api)
):
    """Get statistics about article processing progress for a specific topic."""
    try:
        service = get_geopolitical_service()
        stats = service.get_processing_stats(topic=topic)
        return stats
    except Exception as e:
        logger.error(f"Error getting processing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-topics")
async def get_available_topics(session=Depends(verify_session_api)):
    """Get list of topics available for geopolitical processing with article counts."""
    try:
        service = get_geopolitical_service()
        topics = service.get_available_topics()
        return {"topics": topics}
    except Exception as e:
        logger.error(f"Error getting available topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Global state for tracking background processing
_processing_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "processed": 0,
    "created": 0,
    "updated": 0,
    "skipped": 0,
    "errors": 0,
    "last_error": None,
    "completed": False,
    "message": ""
}


def get_processing_status():
    """Get current processing status."""
    return _processing_status.copy()


async def _process_articles_background(
    articles: list,
    model: str,
    topic: Optional[str],
    process_all: bool
):
    """Background task to process articles."""
    global _processing_status

    service = get_geopolitical_service()
    topic_name = topic or "Geopolitical Hotspots"

    _processing_status["running"] = True
    _processing_status["total"] = len(articles)
    _processing_status["progress"] = 0
    _processing_status["processed"] = 0
    _processing_status["created"] = 0
    _processing_status["updated"] = 0
    _processing_status["skipped"] = 0
    _processing_status["errors"] = 0
    _processing_status["completed"] = False
    _processing_status["last_error"] = None
    _processing_status["message"] = f"Processing {len(articles)} articles..."

    try:
        for i, article in enumerate(articles):
            try:
                _processing_status["progress"] = i + 1

                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.3)

                # Extract location using LLM
                result = await extract_location_with_llm(
                    article['title'] or "",
                    article['summary'] or "",
                    article['category'] or "",
                    model
                )

                if result.get('no_location'):
                    _processing_status["skipped"] += 1
                    continue

                # Validate we have required fields
                if not result.get('location_name') or not result.get('latitude') or not result.get('longitude'):
                    _processing_status["skipped"] += 1
                    continue

                # Check if this will create or update
                from app.database import get_database_instance
                conn = get_database_instance().get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM geopolitical_hotspots
                    WHERE location_name = ? AND country_code = ?
                """, [result['location_name'], result.get('country_code')])
                existing = cursor.fetchone()
                cursor.close()
                conn.close()

                is_new = existing is None

                # Create or update hotspot (pass topic for new hotspots)
                hotspot_id = service.create_or_update_hotspot(result, topic=topic)

                # Link article to hotspot (uses UPSERT so works for reprocessing)
                service.link_article_to_hotspot(
                    hotspot_id,
                    article['uri'],
                    relevance_score=1.0,
                    mention_type='primary'
                )

                if is_new:
                    _processing_status["created"] += 1
                else:
                    _processing_status["updated"] += 1

                _processing_status["processed"] += 1
                logger.info(f"Processed ({i+1}/{len(articles)}): {article['title'][:40]}... -> {result['location_name']}")

            except Exception as e:
                _processing_status["errors"] += 1
                _processing_status["last_error"] = str(e)
                logger.warning(f"Error processing article {article['uri']}: {e}")

        # Update country stats after processing
        try:
            service.update_country_stats()
        except Exception as e:
            logger.warning(f"Failed to update country stats: {e}")

        _processing_status["completed"] = True
        _processing_status["message"] = f"Completed: {_processing_status['processed']} processed, {_processing_status['created']} created, {_processing_status['updated']} updated"
        logger.info(f"Background processing completed: {_processing_status}")

    except Exception as e:
        _processing_status["last_error"] = str(e)
        _processing_status["message"] = f"Error: {str(e)}"
        logger.error(f"Background processing error: {e}")

    finally:
        _processing_status["running"] = False


@router.get("/process-articles/status")
async def get_process_articles_status(session=Depends(verify_session_api)):
    """Get the current status of background article processing."""
    return get_processing_status()


@router.post("/process-articles", response_model=ProcessArticlesResponse)
async def process_articles(
    request: ProcessArticlesRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session_api)
):
    """
    Process curated articles to extract locations and create/update hotspots.
    Processing runs in the background to avoid timeouts.

    Args:
        request.topic: Topic to process articles from (default: Geopolitical Hotspots)
        request.process_all: If True, include already-processed articles (will reprocess and update)
    """
    global _processing_status

    # Check if already processing
    if _processing_status["running"]:
        return ProcessArticlesResponse(
            status="running",
            message=f"Processing already in progress: {_processing_status['progress']}/{_processing_status['total']} articles",
            articles_processed=_processing_status["processed"],
            hotspots_created=_processing_status["created"],
            hotspots_updated=_processing_status["updated"],
            articles_skipped=_processing_status["skipped"],
            errors=_processing_status["errors"]
        )

    service = get_geopolitical_service()

    try:
        # Get articles to process (may include already-processed if process_all=True)
        articles = service.get_unprocessed_articles(
            limit=request.batch_size,
            topic=request.topic,
            process_all=request.process_all
        )

        if not articles:
            return ProcessArticlesResponse(
                status="complete",
                message="No articles found to process"
            )

        topic_name = request.topic or "Geopolitical Hotspots"
        mode = "all" if request.process_all else "unprocessed"
        logger.info(f"Starting background processing of {len(articles)} {mode} articles from topic '{topic_name}'")

        # Start background processing
        background_tasks.add_task(
            _process_articles_background,
            articles,
            request.model,
            request.topic,
            request.process_all
        )

        return ProcessArticlesResponse(
            status="started",
            message=f"Started processing {len(articles)} articles in background. Poll /process-articles/status for progress.",
            articles_processed=0,
            hotspots_created=0,
            hotspots_updated=0,
            articles_skipped=0,
            errors=0
        )

    except Exception as e:
        logger.error(f"Error in process_articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unprocessed-articles")
async def get_unprocessed_articles(
    limit: int = Query(10, ge=1, le=100),
    topic: Optional[str] = Query(None, description="Topic to get articles from"),
    process_all: bool = Query(False, description="If True, include already-processed articles"),
    session=Depends(verify_session_api)
):
    """Preview articles that would be processed next."""
    try:
        service = get_geopolitical_service()
        articles = service.get_unprocessed_articles(
            limit=limit,
            topic=topic,
            process_all=process_all
        )
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error getting unprocessed articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-hotspots")
async def clear_hotspots(session=Depends(verify_session_api)):
    """Clear all hotspots, article links, narratives, and insights.

    Note: Processing status is determined by the hotspot_articles junction table,
    so deleting from that table allows articles to be reprocessed.
    """
    from app.database import get_database_instance

    try:
        conn = get_database_instance().get_connection()
        cursor = conn.cursor()

        # Clear article links first (this resets processing status since we use
        # LEFT JOIN to determine which articles are unprocessed)
        cursor.execute("DELETE FROM hotspot_articles")

        # Clear time-series and aggregation data
        cursor.execute("DELETE FROM hotspot_daily_stats")
        cursor.execute("DELETE FROM country_hotspot_stats")

        # Clear insights and narratives
        cursor.execute("DELETE FROM geopolitical_insights")
        cursor.execute("DELETE FROM geopolitical_narratives")

        # Finally clear the hotspots themselves
        cursor.execute("DELETE FROM geopolitical_hotspots")

        conn.commit()

        cursor.close()
        conn.close()

        return {"status": "success", "message": "All hotspots, narratives, and processing status cleared"}
    except Exception as e:
        logger.error(f"Error clearing hotspots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill-article-links")
async def backfill_article_links(session=Depends(verify_session_api)):
    """
    Backfill hotspot_articles by matching location names in article text.

    This is useful when hotspots exist with article_count > 0 but the actual
    links in hotspot_articles were never created. It searches for hotspot
    location names in article titles/summaries and creates the missing links.
    """
    try:
        service = get_geopolitical_service()
        stats = service.backfill_article_links()

        return {
            "status": "success",
            "message": f"Backfill complete: {stats['links_created']} article links created for {stats['hotspots_with_matches']} hotspots",
            **stats
        }
    except Exception as e:
        logger.error(f"Error backfilling article links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Narrative Endpoints
# ============================================================================

class NarrativeSummary(BaseModel):
    id: int
    executive_summary: Optional[str]
    hotspot_count: int
    article_count: int
    model_used: Optional[str]
    topic: Optional[str]
    generated_at: Optional[str]


class NarrativeDetail(BaseModel):
    id: int
    narrative_text: str
    executive_summary: Optional[str]
    regional_analysis: Optional[str]
    emerging_threats: Optional[str]
    outlook: Optional[str]
    hotspot_count: int
    article_count: int
    top_regions: Optional[list]
    top_categories: Optional[list]
    risk_breakdown: Optional[dict]
    model_used: Optional[str]
    topic: Optional[str]
    generated_at: Optional[str]


class GenerateNarrativeRequest(BaseModel):
    model: str = Field("gpt-4o-mini", description="LLM model to use for generation")
    topic: Optional[str] = Field(None, description="Optional topic filter")


@router.get("/narrative", response_model=Optional[NarrativeDetail])
async def get_latest_narrative(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get the most recent narrative."""
    try:
        service = get_geopolitical_service()
        narrative = service.get_latest_narrative(topic=topic)
        return narrative
    except Exception as e:
        logger.error(f"Error getting narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/narratives", response_model=List[NarrativeSummary])
async def get_narratives_history(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(10, ge=1, le=50, description="Number of narratives to return")
):
    """Get narrative history."""
    try:
        service = get_geopolitical_service()
        narratives = service.get_narratives_history(topic=topic, limit=limit)
        return narratives
    except Exception as e:
        logger.error(f"Error getting narratives: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-narrative")
async def generate_narrative(
    request: GenerateNarrativeRequest,
    session=Depends(verify_session_api)
):
    """Generate a new strategic intelligence narrative using LLM."""
    try:
        service = get_geopolitical_service()

        # Get current stats to feed to the LLM
        stats = service.get_overview_stats(topic=request.topic)

        if stats.get('total_hotspots', 0) == 0:
            return {
                "status": "error",
                "message": "No hotspots available to generate narrative"
            }

        logger.info(f"Generating narrative with {stats['total_hotspots']} hotspots using {request.model}")

        # Generate narrative with LLM
        narrative_sections = await generate_narrative_with_llm(stats, request.model)

        if 'error' in narrative_sections:
            raise HTTPException(status_code=500, detail=narrative_sections['error'])

        # Prepare data for saving
        narrative_data = {
            **narrative_sections,
            'hotspot_count': stats.get('total_hotspots', 0),
            'article_count': stats.get('total_articles', 0),
            'top_regions': [h.get('country_name') for h in stats.get('top_hotspots', []) if h.get('country_name')][:5],
            'top_categories': list(stats.get('by_category', {}).keys())[:5],
            'risk_breakdown': stats.get('by_risk_level', {}),
            'model_used': request.model,
            'topic': request.topic
        }

        # Save to database
        narrative_id = service.save_narrative(narrative_data)

        return {
            "status": "success",
            "message": "Narrative generated successfully",
            "narrative_id": narrative_id,
            "narrative": {
                'id': narrative_id,
                **narrative_data,
                'generated_at': None  # Will be set by database
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Scheduling Endpoints
# ============================================================================

class GeopoliticalScheduleCreate(BaseModel):
    name: str = Field(..., description="Name for the schedule")
    topic: Optional[str] = Field(None, description="Topic to process (default: Geopolitical Hotspots)")
    batch_size: int = Field(50, ge=1, le=500, description="Number of articles per run")
    model: str = Field("gpt-4o-mini", description="LLM model to use")
    process_all: bool = Field(False, description="Reprocess already-processed articles")
    schedule_enabled: bool = Field(True, description="Enable scheduling")
    schedule_type: str = Field("interval", description="Schedule type: 'interval' or 'daily'")
    schedule_interval: Optional[int] = Field(None, description="Interval value")
    schedule_unit: Optional[str] = Field("hours", description="Interval unit: 'minutes', 'hours', 'days'")
    schedule_time: Optional[str] = Field(None, description="Time for daily schedule (HH:MM)")
    notify_on_complete: bool = Field(True, description="Send notification when complete")
    notify_threshold: int = Field(1, ge=0, description="Min articles processed to notify")


class GeopoliticalScheduleUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    batch_size: Optional[int] = Field(None, ge=1, le=500)
    model: Optional[str] = None
    process_all: Optional[bool] = None
    schedule_enabled: Optional[bool] = None
    schedule_type: Optional[str] = None
    schedule_interval: Optional[int] = None
    schedule_unit: Optional[str] = None
    schedule_time: Optional[str] = None
    notify_on_complete: Optional[bool] = None
    notify_threshold: Optional[int] = Field(None, ge=0)


class GeopoliticalScheduleResponse(BaseModel):
    id: int
    name: str
    topic: Optional[str]
    batch_size: int
    model: str
    process_all: bool
    schedule_enabled: bool
    schedule_type: Optional[str]
    schedule_interval: Optional[int]
    schedule_unit: Optional[str]
    schedule_time: Optional[str]
    notify_on_complete: bool
    notify_threshold: int
    last_run_at: Optional[str]
    next_run_at: Optional[str]
    last_run_status: Optional[str]
    last_run_error: Optional[str]
    last_run_articles_processed: int
    last_run_hotspots_created: int
    last_run_hotspots_updated: int
    run_count: int
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/schedules")
async def list_schedules(session=Depends(verify_session_api)):
    """List all geopolitical hotspots processing schedules."""
    from app.database import get_database_instance
    from sqlalchemy import text

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, topic, batch_size, model, process_all,
                   schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time,
                   notify_on_complete, notify_threshold,
                   last_run_at, next_run_at, last_run_status, last_run_error,
                   last_run_articles_processed, last_run_hotspots_created, last_run_hotspots_updated,
                   run_count, created_at, updated_at
            FROM geopolitical_schedules
            ORDER BY created_at DESC
        """))
        schedules = []
        for row in result:
            row_dict = dict(row._mapping)
            # Convert datetime objects to ISO strings
            for key in ['last_run_at', 'next_run_at', 'created_at', 'updated_at']:
                if row_dict.get(key):
                    row_dict[key] = row_dict[key].isoformat()
            if row_dict.get('schedule_time'):
                row_dict['schedule_time'] = str(row_dict['schedule_time'])
            schedules.append(row_dict)
        conn.close()

        return {"schedules": schedules}
    except Exception as e:
        logger.error(f"Error listing schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedules")
async def create_schedule(
    schedule: GeopoliticalScheduleCreate,
    session=Depends(verify_session_api)
):
    """Create a new geopolitical hotspots processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import time as dt_time

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Parse schedule_time if provided
        schedule_time_val = None
        if schedule.schedule_time:
            try:
                parts = schedule.schedule_time.split(':')
                schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        # Calculate initial next_run_at
        from app.tasks.geopolitical_hotspots_monitor import calculate_next_run
        next_run = None
        if schedule.schedule_enabled:
            next_run = calculate_next_run(
                schedule.schedule_type,
                schedule.schedule_interval,
                schedule.schedule_unit,
                schedule_time_val
            )

        result = conn.execute(text("""
            INSERT INTO geopolitical_schedules
            (name, topic, batch_size, model, process_all,
             schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time,
             notify_on_complete, notify_threshold, next_run_at)
            VALUES (:name, :topic, :batch_size, :model, :process_all,
                    :schedule_enabled, :schedule_type, :schedule_interval, :schedule_unit, :schedule_time,
                    :notify_on_complete, :notify_threshold, :next_run_at)
            RETURNING id
        """), {
            "name": schedule.name,
            "topic": schedule.topic,
            "batch_size": schedule.batch_size,
            "model": schedule.model,
            "process_all": schedule.process_all,
            "schedule_enabled": schedule.schedule_enabled,
            "schedule_type": schedule.schedule_type,
            "schedule_interval": schedule.schedule_interval,
            "schedule_unit": schedule.schedule_unit,
            "schedule_time": schedule_time_val,
            "notify_on_complete": schedule.notify_on_complete,
            "notify_threshold": schedule.notify_threshold,
            "next_run_at": next_run
        })
        schedule_id = result.scalar()
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": "Schedule created successfully",
            "schedule_id": schedule_id,
            "next_run_at": next_run.isoformat() if next_run else None
        }
    except Exception as e:
        logger.error(f"Error creating schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    schedule: GeopoliticalScheduleUpdate,
    session=Depends(verify_session_api)
):
    """Update a geopolitical hotspots processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import time as dt_time

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build update query dynamically based on provided fields
        updates = []
        params = {"id": schedule_id}

        if schedule.name is not None:
            updates.append("name = :name")
            params["name"] = schedule.name

        if schedule.topic is not None:
            updates.append("topic = :topic")
            params["topic"] = schedule.topic if schedule.topic else None

        if schedule.batch_size is not None:
            updates.append("batch_size = :batch_size")
            params["batch_size"] = schedule.batch_size

        if schedule.model is not None:
            updates.append("model = :model")
            params["model"] = schedule.model

        if schedule.process_all is not None:
            updates.append("process_all = :process_all")
            params["process_all"] = schedule.process_all

        if schedule.schedule_enabled is not None:
            updates.append("schedule_enabled = :schedule_enabled")
            params["schedule_enabled"] = schedule.schedule_enabled

        if schedule.schedule_type is not None:
            updates.append("schedule_type = :schedule_type")
            params["schedule_type"] = schedule.schedule_type

        if schedule.schedule_interval is not None:
            updates.append("schedule_interval = :schedule_interval")
            params["schedule_interval"] = schedule.schedule_interval

        if schedule.schedule_unit is not None:
            updates.append("schedule_unit = :schedule_unit")
            params["schedule_unit"] = schedule.schedule_unit

        if schedule.schedule_time is not None:
            schedule_time_val = None
            if schedule.schedule_time:
                try:
                    parts = schedule.schedule_time.split(':')
                    schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
                except Exception:
                    pass
            updates.append("schedule_time = :schedule_time")
            params["schedule_time"] = schedule_time_val

        if schedule.notify_on_complete is not None:
            updates.append("notify_on_complete = :notify_on_complete")
            params["notify_on_complete"] = schedule.notify_on_complete

        if schedule.notify_threshold is not None:
            updates.append("notify_threshold = :notify_threshold")
            params["notify_threshold"] = schedule.notify_threshold

        updates.append("updated_at = NOW()")

        if not updates:
            return {"status": "success", "message": "No changes made"}

        # Recalculate next_run_at if scheduling changed
        if any(key in params for key in ['schedule_enabled', 'schedule_type', 'schedule_interval', 'schedule_unit', 'schedule_time']):
            # Get current values
            current = conn.execute(text("""
                SELECT schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time
                FROM geopolitical_schedules WHERE id = :id
            """), {"id": schedule_id}).mappings().first()

            if current:
                from app.tasks.geopolitical_hotspots_monitor import calculate_next_run
                s_enabled = params.get('schedule_enabled', current['schedule_enabled'])
                s_type = params.get('schedule_type', current['schedule_type'])
                s_interval = params.get('schedule_interval', current['schedule_interval'])
                s_unit = params.get('schedule_unit', current['schedule_unit'])
                s_time = params.get('schedule_time') if 'schedule_time' in params else current['schedule_time']

                if s_enabled:
                    next_run = calculate_next_run(s_type, s_interval, s_unit, s_time)
                    updates.append("next_run_at = :next_run_at")
                    params["next_run_at"] = next_run
                else:
                    updates.append("next_run_at = NULL")

        conn.execute(text(f"""
            UPDATE geopolitical_schedules
            SET {', '.join(updates)}
            WHERE id = :id
        """), params)
        conn.commit()
        conn.close()

        return {"status": "success", "message": "Schedule updated successfully"}
    except Exception as e:
        logger.error(f"Error updating schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    session=Depends(verify_session_api)
):
    """Delete a geopolitical hotspots processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text("""
            DELETE FROM geopolitical_schedules WHERE id = :id
        """), {"id": schedule_id})
        conn.commit()
        conn.close()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schedule not found")

        return {"status": "success", "message": "Schedule deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: int,
    session=Depends(verify_session_api)
):
    """Manually trigger a schedule to run immediately."""
    from app.database import Database
    from app.tasks.geopolitical_hotspots_monitor import run_schedule_now as _run_schedule_now

    try:
        db = Database()
        result = await _run_schedule_now(db, schedule_id)

        if not result.get("success"):
            if result.get("error") == "Schedule not found":
                raise HTTPException(status_code=404, detail="Schedule not found")
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

        return {
            "status": "success",
            "message": f"Schedule processed {result.get('articles_processed', 0)} articles",
            "articles_processed": result.get("articles_processed", 0),
            "hotspots_created": result.get("hotspots_created", 0),
            "hotspots_updated": result.get("hotspots_updated", 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedules/status")
async def get_monitor_status(session=Depends(verify_session_api)):
    """Get the current status of the geopolitical hotspots background monitor."""
    from app.tasks.geopolitical_hotspots_monitor import get_task_status

    try:
        status = get_task_status()
        # Convert datetime to ISO string if present
        if status.get("last_check_time"):
            status["last_check_time"] = status["last_check_time"].isoformat()
        return status
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
