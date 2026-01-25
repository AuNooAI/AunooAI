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
from app.security.session import verify_session

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


class ProcessArticlesResponse(BaseModel):
    status: str
    message: str
    articles_processed: int = 0
    hotspots_created: int = 0
    hotspots_updated: int = 0
    articles_skipped: int = 0
    errors: int = 0


@router.get("/processing-stats", response_model=ProcessingStats)
async def get_processing_stats(session=Depends(verify_session)):
    """Get statistics about article processing progress."""
    try:
        service = get_geopolitical_service()
        stats = service.get_processing_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting processing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-articles", response_model=ProcessArticlesResponse)
async def process_articles(
    request: ProcessArticlesRequest,
    background_tasks: BackgroundTasks,
    session=Depends(verify_session)
):
    """
    Process curated articles to extract locations and create/update hotspots.
    Only processes articles with populated category and sentiment fields.
    """
    service = get_geopolitical_service()

    try:
        # Get unprocessed articles
        articles = service.get_unprocessed_articles(limit=request.batch_size)

        if not articles:
            return ProcessArticlesResponse(
                status="complete",
                message="No unprocessed articles found"
            )

        logger.info(f"Processing {len(articles)} articles for geopolitical hotspots")

        stats = {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0
        }

        for article in articles:
            try:
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.3)

                # Extract location using LLM
                result = await extract_location_with_llm(
                    article['title'] or "",
                    article['summary'] or "",
                    article['category'] or "",
                    request.model
                )

                if result.get('no_location'):
                    stats["skipped"] += 1
                    logger.debug(f"No location found for: {article['title'][:50]}")
                    continue

                # Validate we have required fields
                if not result.get('location_name') or not result.get('latitude') or not result.get('longitude'):
                    stats["skipped"] += 1
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

                # Create or update hotspot
                hotspot_id = service.create_or_update_hotspot(result)

                # Link article to hotspot
                service.link_article_to_hotspot(
                    hotspot_id,
                    article['uri'],
                    relevance_score=1.0,
                    mention_type='primary'
                )

                if is_new:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1

                stats["processed"] += 1
                logger.info(f"Processed: {article['title'][:40]}... -> {result['location_name']}")

            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"Error processing article {article['uri']}: {e}")

        # Update country stats after processing
        try:
            service.update_country_stats()
        except Exception as e:
            logger.warning(f"Failed to update country stats: {e}")

        return ProcessArticlesResponse(
            status="success",
            message=f"Processed {stats['processed']} articles",
            articles_processed=stats["processed"],
            hotspots_created=stats["created"],
            hotspots_updated=stats["updated"],
            articles_skipped=stats["skipped"],
            errors=stats["errors"]
        )

    except Exception as e:
        logger.error(f"Error in process_articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unprocessed-articles")
async def get_unprocessed_articles(
    limit: int = Query(10, ge=1, le=100),
    session=Depends(verify_session)
):
    """Preview unprocessed articles that would be processed next."""
    try:
        service = get_geopolitical_service()
        articles = service.get_unprocessed_articles(limit=limit)
        return {"articles": articles, "count": len(articles)}
    except Exception as e:
        logger.error(f"Error getting unprocessed articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear-hotspots")
async def clear_hotspots(session=Depends(verify_session)):
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
    session=Depends(verify_session)
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
