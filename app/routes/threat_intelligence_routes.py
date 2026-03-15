"""Threat Intelligence API Routes

REST API endpoints for the threat intelligence analysis feature.
Provides threat tracking, actor management, IOC extraction, and LLM-powered analysis.
"""

import logging
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.services.threat_intelligence_service import (
    get_threat_intelligence_service,
    extract_threat_with_llm,
    generate_narrative_with_llm,
    THREAT_CATEGORIES,
    SEVERITY_LEVELS,
    ACTOR_TYPES,
    TARGET_INDUSTRIES
)
from app.security.session import verify_session, verify_session_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threat-intelligence", tags=["threat-intelligence"])


# ============================================================================
# Response Models
# ============================================================================

class ThreatSummary(BaseModel):
    id: int
    threat_name: str
    threat_type: str
    severity_level: str
    severity_score: float
    threat_actor_name: Optional[str]
    article_count: int
    trend: Optional[str]


class OverviewStats(BaseModel):
    total_threats: int
    by_severity: dict
    total_articles: int
    recent_articles: int
    total_actors: int
    escalating_count: int
    declining_count: int
    new_threats: int
    by_type: dict
    top_threats: List[ThreatSummary]


class ThreatDetail(BaseModel):
    id: int
    threat_name: str
    threat_type: str
    threat_subtype: Optional[str]
    severity_level: str
    severity_score: float
    trend: Optional[str]
    threat_actor_id: Optional[int]
    threat_actor_name: Optional[str]
    attributed_country: Optional[str]
    attributed_country_name: Optional[str]
    target_countries: Optional[list]
    target_latitude: Optional[float]
    target_longitude: Optional[float]
    target_industries: Optional[list]
    cve_ids: Optional[list]
    mitre_techniques: Optional[list]
    malware_families: Optional[list]
    first_seen_date: Optional[str]
    last_seen_date: Optional[str]
    article_count: int
    recent_article_count: int
    description: Optional[str]
    tags: Optional[list]


class ActorSummary(BaseModel):
    id: int
    name: str
    aliases: Optional[list]
    actor_type: str
    attributed_country: Optional[str]
    attributed_country_name: Optional[str]
    sophistication_level: Optional[str]
    threat_count: int
    article_count: int


class ArticleWithThreats(BaseModel):
    uri: str
    title: Optional[str]
    source: Optional[str]
    publication_date: Optional[str]
    summary: Optional[str]
    category: Optional[str]
    sentiment: Optional[str]
    relevance_score: Optional[float]
    threat_id: Optional[int]
    threat_name: Optional[str]
    severity_level: str
    threat_type: Optional[str]
    severity_score: Optional[float]


# ============================================================================
# Overview & Stats Endpoints
# ============================================================================

@router.get("/overview")
async def get_overview(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get dashboard overview statistics."""
    try:
        service = get_threat_intelligence_service()
        stats = service.get_overview_stats(topic=topic, days_back=days_back)
        return stats
    except Exception as e:
        logger.error(f"Error getting overview stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threat-categories")
async def get_threat_categories():
    """Get list of available threat categories."""
    return {"categories": THREAT_CATEGORIES}


@router.get("/severity-levels")
async def get_severity_levels():
    """Get list of available severity levels."""
    return {"severity_levels": SEVERITY_LEVELS}


@router.get("/actor-types")
async def get_actor_types():
    """Get list of available threat actor types."""
    return {"actor_types": ACTOR_TYPES}


@router.get("/target-industries")
async def get_target_industries():
    """Get list of target industries."""
    return {"industries": TARGET_INDUSTRIES}


# ============================================================================
# Threats Endpoints
# ============================================================================

@router.get("/map-data")
async def get_map_data(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    threat_types: Optional[str] = Query(None, description="Comma-separated threat types"),
    severity_levels: Optional[str] = Query(None, description="Comma-separated severity levels"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get all threats with coordinates for map display."""
    try:
        service = get_threat_intelligence_service()

        type_list = threat_types.split(',') if threat_types else None
        severity_list = severity_levels.split(',') if severity_levels else None

        threats = service.get_map_data(
            topic=topic,
            threat_types=type_list,
            severity_levels=severity_list,
            days_back=days_back
        )
        return {"threats": threats}
    except Exception as e:
        logger.error(f"Error getting map data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threats")
async def list_threats(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    threat_types: Optional[str] = Query(None, description="Comma-separated threat types"),
    severity_levels: Optional[str] = Query(None, description="Comma-separated severity levels"),
    actor_id: Optional[int] = Query(None, description="Filter by threat actor ID"),
    days_back: int = Query(30, description="Days to look back"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("severity", description="Sort field: severity, articles, name, type, updated"),
    sort_order: str = Query("desc", description="Sort order: asc, desc")
):
    """Get paginated list of threats with filters."""
    try:
        service = get_threat_intelligence_service()

        type_list = threat_types.split(',') if threat_types else None
        severity_list = severity_levels.split(',') if severity_levels else None

        threats, total = service.get_threats(
            topic=topic,
            threat_types=type_list,
            severity_levels=severity_list,
            actor_id=actor_id,
            days_back=days_back,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "threats": threats,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error listing threats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threat/{threat_id}")
async def get_threat(threat_id: int):
    """Get single threat by ID with full details."""
    try:
        service = get_threat_intelligence_service()
        threat = service.get_threat_by_id(threat_id)

        if not threat:
            raise HTTPException(status_code=404, detail="Threat not found")

        return threat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting threat {threat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/threat/{threat_id}/articles")
async def get_threat_articles(
    threat_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get articles linked to a threat."""
    try:
        service = get_threat_intelligence_service()
        articles, total = service.get_threat_articles(
            threat_id=threat_id,
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
        logger.error(f"Error getting threat articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Threat Actors Endpoints
# ============================================================================

@router.get("/actors")
async def list_actors(
    actor_type: Optional[str] = Query(None, description="Filter by actor type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("threat_count", description="Sort field: threat_count, article_count, name, sophistication, last_active"),
    sort_order: str = Query("desc", description="Sort order: asc, desc")
):
    """Get paginated list of threat actors."""
    try:
        service = get_threat_intelligence_service()
        actors, total = service.get_actors(
            actor_type=actor_type,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "actors": actors,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error listing actors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actor/{actor_id}")
async def get_actor(actor_id: int):
    """Get single threat actor by ID with full details."""
    try:
        service = get_threat_intelligence_service()
        actor = service.get_actor_by_id(actor_id)

        if not actor:
            raise HTTPException(status_code=404, detail="Actor not found")

        return actor
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting actor {actor_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actor/{actor_id}/threats")
async def get_actor_threats(
    actor_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get threats associated with a threat actor."""
    try:
        service = get_threat_intelligence_service()
        threats, total = service.get_actor_threats(
            actor_id=actor_id,
            page=page,
            page_size=page_size
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "threats": threats,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error getting actor threats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Timeline & Analysis Endpoints
# ============================================================================

@router.get("/timeline")
async def get_timeline(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get temporal trend data for threats."""
    try:
        service = get_threat_intelligence_service()
        data = service.get_timeline_data(topic=topic, days_back=days_back)
        return {"timeline": data}
    except Exception as e:
        logger.error(f"Error getting timeline data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-counts")
async def get_daily_counts(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(30, description="Days to look back")
):
    """Get daily article counts with rolling average."""
    try:
        service = get_threat_intelligence_service()
        data = service.get_daily_counts(topic=topic, days_back=days_back)
        return {"daily_counts": data}
    except Exception as e:
        logger.error(f"Error getting daily counts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_categories_data(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get distribution by threat type."""
    try:
        service = get_threat_intelligence_service()
        data = service.get_category_distribution(topic=topic)
        return {"categories": data}
    except Exception as e:
        logger.error(f"Error getting category data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/category-trends")
async def get_category_trends(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    days_back: int = Query(90, description="Days to look back"),
    granularity: str = Query("weekly", description="Granularity: weekly or monthly")
):
    """Get threat type breakdown over time periods."""
    try:
        service = get_threat_intelligence_service()
        data = service.get_category_trends(topic=topic, days_back=days_back, granularity=granularity)
        return {"trends": data}
    except Exception as e:
        logger.error(f"Error getting category trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ttp-analysis")
async def get_ttp_analysis(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    session=Depends(verify_session_api)
):
    """Get MITRE ATT&CK technique breakdown."""
    try:
        service = get_threat_intelligence_service()
        data = service.get_ttp_analysis(topic=topic)
        return data
    except Exception as e:
        logger.error(f"Error getting TTP analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# IOCs Endpoints
# ============================================================================

@router.get("/iocs")
async def list_iocs(
    indicator_type: Optional[str] = Query(None, description="Filter by IOC type"),
    threat_id: Optional[int] = Query(None, description="Filter by threat ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page")
):
    """Get IOCs with filters."""
    try:
        service = get_threat_intelligence_service()
        iocs, total = service.get_iocs(
            indicator_type=indicator_type,
            threat_id=threat_id,
            page=page,
            page_size=page_size
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "iocs": iocs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error listing IOCs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Campaigns Endpoints
# ============================================================================

@router.get("/campaigns")
async def list_campaigns(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page")
):
    """Get campaigns with filters."""
    try:
        service = get_threat_intelligence_service()
        campaigns, total = service.get_campaigns(
            is_active=is_active,
            page=page,
            page_size=page_size
        )

        total_pages = (total + page_size - 1) // page_size

        return {
            "campaigns": campaigns,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    except Exception as e:
        logger.error(f"Error listing campaigns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Articles Endpoints
# ============================================================================

@router.get("/articles")
async def get_all_articles(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    severity_level: Optional[str] = Query(None, description="Filter by severity level"),
    threat_type: Optional[str] = Query(None, description="Filter by threat type"),
    threat_id: Optional[int] = Query(None, description="Filter by threat ID"),
    search: Optional[str] = Query(None, description="Search in title/summary"),
    sort_by: str = Query("date", description="Sort field: date, title, relevance, severity"),
    sort_order: str = Query("desc", description="Sort order: asc, desc")
):
    """Get all articles linked to threats with filters and pagination."""
    try:
        service = get_threat_intelligence_service()
        articles, total = service.get_all_threat_articles(
            page=page,
            page_size=page_size,
            severity_level=severity_level,
            threat_type=threat_type,
            threat_id=threat_id,
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


# ============================================================================
# Processing Endpoints
# ============================================================================

class ProcessingStats(BaseModel):
    total_curated_articles: int
    processed_articles: int
    unprocessed_articles: int
    total_threats: int
    total_actors: int
    processing_percentage: float


class ProcessArticlesRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500, description="Number of articles to process")
    model: str = Field("gpt-4o-mini", description="LLM model to use for threat extraction")
    topic: Optional[str] = Field(None, description="Topic to process articles from")
    process_all: bool = Field(False, description="If True, process all articles including already-processed ones")


class ProcessArticlesResponse(BaseModel):
    status: str
    message: str
    articles_processed: int = 0
    threats_created: int = 0
    threats_updated: int = 0
    articles_skipped: int = 0
    errors: int = 0


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
    "message": "",
    "current_article": None,
    "actors_identified": 0
}


def get_processing_status():
    """Get current processing status in frontend-expected format."""
    status = _processing_status.copy()

    # Convert to frontend expected format
    if status["running"]:
        status_str = "processing"
    elif status["completed"]:
        status_str = "completed"
    elif status["last_error"]:
        status_str = "failed"
    else:
        status_str = "idle"

    return {
        "status": status_str,
        "processed": status["processed"],
        "total_articles": status["total"],
        "threats_extracted": status["created"],
        "actors_identified": status.get("actors_identified", 0),
        "current_article": status.get("current_article"),
        "error": status["last_error"]
    }


async def _process_articles_background(
    articles: list,
    model: str,
    topic: Optional[str],
    process_all: bool
):
    """Background task to process articles for threat extraction."""
    global _processing_status

    service = get_threat_intelligence_service()
    topic_name = topic or "Threat Intelligence"

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
    _processing_status["current_article"] = None
    _processing_status["actors_identified"] = 0
    _processing_status["message"] = f"Processing {len(articles)} articles..."

    try:
        for i, article in enumerate(articles):
            try:
                _processing_status["progress"] = i + 1
                _processing_status["current_article"] = article.get('title', '')[:100]

                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.3)

                # Extract threat using LLM
                result = await extract_threat_with_llm(
                    article['title'] or "",
                    article['summary'] or "",
                    article['category'] or "",
                    model
                )

                if result.get('no_threat'):
                    _processing_status["skipped"] += 1
                    continue

                # Validate we have required fields
                if not result.get('threat_name') or not result.get('threat_type'):
                    _processing_status["skipped"] += 1
                    continue

                # Check if this will create or update
                from app.database import get_database_instance
                conn = get_database_instance().get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM threat_intel_threats
                    WHERE threat_name = ?
                """, [result['threat_name']])
                existing = cursor.fetchone()
                cursor.close()
                conn.close()

                is_new = existing is None

                # Create or update threat
                threat_id = service.create_or_update_threat(result, topic=topic)

                # Link article to threat
                service.link_article_to_threat(
                    threat_id,
                    article['uri'],
                    relevance_score=1.0,
                    mention_type='primary'
                )

                if is_new:
                    _processing_status["created"] += 1
                else:
                    _processing_status["updated"] += 1

                _processing_status["processed"] += 1
                logger.info(f"Processed ({i+1}/{len(articles)}): {article['title'][:40]}... -> {result['threat_name']}")

            except Exception as e:
                _processing_status["errors"] += 1
                _processing_status["last_error"] = str(e)
                logger.warning(f"Error processing article {article['uri']}: {e}")

        _processing_status["completed"] = True
        _processing_status["current_article"] = None
        _processing_status["message"] = f"Completed: {_processing_status['processed']} processed, {_processing_status['created']} created, {_processing_status['updated']} updated"
        logger.info(f"Background processing completed: {_processing_status}")

    except Exception as e:
        _processing_status["last_error"] = str(e)
        _processing_status["current_article"] = None
        _processing_status["message"] = f"Error: {str(e)}"
        logger.error(f"Background processing error: {e}")

    finally:
        _processing_status["running"] = False


@router.get("/processing-stats")
async def get_processing_stats_endpoint(
    topic: Optional[str] = Query(None, description="Topic to get stats for"),
    session=Depends(verify_session_api)
):
    """Get statistics about article processing progress."""
    try:
        service = get_threat_intelligence_service()
        stats = service.get_processing_stats(topic=topic)
        return stats
    except Exception as e:
        logger.error(f"Error getting processing stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-topics")
async def get_available_topics(session=Depends(verify_session_api)):
    """Get list of topics available for threat intelligence processing."""
    try:
        service = get_threat_intelligence_service()
        topics = service.get_available_topics()
        return {"topics": topics}
    except Exception as e:
        logger.error(f"Error getting available topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    Process curated articles to extract threats and create/update threat entities.
    Processing runs in the background to avoid timeouts.
    """
    global _processing_status

    # Check if already processing
    if _processing_status["running"]:
        return ProcessArticlesResponse(
            status="running",
            message=f"Processing already in progress: {_processing_status['progress']}/{_processing_status['total']} articles",
            articles_processed=_processing_status["processed"],
            threats_created=_processing_status["created"],
            threats_updated=_processing_status["updated"],
            articles_skipped=_processing_status["skipped"],
            errors=_processing_status["errors"]
        )

    service = get_threat_intelligence_service()

    try:
        # Get articles to process
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

        topic_name = request.topic or "Threat Intelligence"
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
            threats_created=0,
            threats_updated=0,
            articles_skipped=0,
            errors=0
        )

    except Exception as e:
        logger.error(f"Error in process_articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Narrative Endpoints
# ============================================================================

class NarrativeDetail(BaseModel):
    id: int
    narrative_text: str
    executive_summary: Optional[str]
    threat_landscape: Optional[str]
    emerging_threats: Optional[str]
    recommendations: Optional[str]
    threat_count: int
    article_count: int
    top_threat_types: Optional[list]
    top_actors: Optional[list]
    severity_breakdown: Optional[dict]
    model_used: Optional[str]
    topic: Optional[str]
    generated_at: Optional[str]


class GenerateNarrativeRequest(BaseModel):
    model: str = Field("gpt-4o-mini", description="LLM model to use for generation")
    topic: Optional[str] = Field(None, description="Optional topic filter")


@router.get("/narrative")
async def get_latest_narrative(
    topic: Optional[str] = Query(None, description="Filter by topic")
):
    """Get the most recent narrative."""
    try:
        service = get_threat_intelligence_service()
        narrative = service.get_latest_narrative(topic=topic)
        return narrative
    except Exception as e:
        logger.error(f"Error getting narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-narrative")
async def generate_narrative(
    request: GenerateNarrativeRequest,
    session=Depends(verify_session_api)
):
    """Generate a new threat intelligence narrative using LLM."""
    try:
        service = get_threat_intelligence_service()

        # Get current stats to feed to the LLM
        stats = service.get_overview_stats(topic=request.topic)

        if stats.get('total_threats', 0) == 0:
            return {
                "status": "error",
                "message": "No threats available to generate narrative"
            }

        logger.info(f"Generating narrative with {stats['total_threats']} threats using {request.model}")

        # Generate narrative with LLM
        narrative_sections = await generate_narrative_with_llm(stats, request.model)

        if 'error' in narrative_sections:
            raise HTTPException(status_code=500, detail=narrative_sections['error'])

        # Prepare data for saving
        narrative_data = {
            **narrative_sections,
            'threat_count': stats.get('total_threats', 0),
            'article_count': stats.get('total_articles', 0),
            'top_threat_types': list(stats.get('by_type', {}).keys())[:5],
            'top_actors': [t.get('threat_actor_name') for t in stats.get('top_threats', []) if t.get('threat_actor_name')][:5],
            'severity_breakdown': stats.get('by_severity', {}),
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
                'generated_at': None
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

class ThreatIntelScheduleCreate(BaseModel):
    name: str = Field(..., description="Name for the schedule")
    topic: Optional[str] = Field(None, description="Topic to process")
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


class ThreatIntelScheduleUpdate(BaseModel):
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


@router.get("/schedules")
async def list_schedules(session=Depends(verify_session_api)):
    """List all threat intelligence processing schedules."""
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
                   last_run_articles_processed, last_run_threats_created, last_run_threats_updated,
                   run_count, created_at, updated_at
            FROM threat_intel_schedules
            ORDER BY created_at DESC
        """))
        schedules = []
        for row in result:
            row_dict = dict(row._mapping)
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
    schedule: ThreatIntelScheduleCreate,
    session=Depends(verify_session_api)
):
    """Create a new threat intelligence processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import time as dt_time

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        schedule_time_val = None
        if schedule.schedule_time:
            try:
                parts = schedule.schedule_time.split(':')
                schedule_time_val = dt_time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        # Calculate initial next_run_at
        from app.tasks.threat_intelligence_monitor import calculate_next_run
        next_run = None
        if schedule.schedule_enabled:
            next_run = calculate_next_run(
                schedule.schedule_type,
                schedule.schedule_interval,
                schedule.schedule_unit,
                schedule_time_val
            )

        result = conn.execute(text("""
            INSERT INTO threat_intel_schedules
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
    schedule: ThreatIntelScheduleUpdate,
    session=Depends(verify_session_api)
):
    """Update a threat intelligence processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import time as dt_time

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

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
            current = conn.execute(text("""
                SELECT schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time
                FROM threat_intel_schedules WHERE id = :id
            """), {"id": schedule_id}).mappings().first()

            if current:
                from app.tasks.threat_intelligence_monitor import calculate_next_run
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
            UPDATE threat_intel_schedules
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
    """Delete a threat intelligence processing schedule."""
    from app.database import get_database_instance
    from sqlalchemy import text

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text("""
            DELETE FROM threat_intel_schedules WHERE id = :id
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
    from app.tasks.threat_intelligence_monitor import run_schedule_now as _run_schedule_now

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
            "threats_created": result.get("threats_created", 0),
            "threats_updated": result.get("threats_updated", 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedules/status")
async def get_monitor_status(session=Depends(verify_session_api)):
    """Get the current status of the threat intelligence background monitor."""
    from app.tasks.threat_intelligence_monitor import get_task_status

    try:
        status = get_task_status()
        if status.get("last_check_time"):
            status["last_check_time"] = status["last_check_time"].isoformat()
        return status
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
