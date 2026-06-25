"""
Power, Attention & Money (PAM) API Routes

Provides endpoints for:
- Comprehensive PAM analysis
- 2030 trend monitoring
- Publisher positioning analysis
- Financial and regulatory event tracking
- Saved dashboards
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import asyncio
import os
from datetime import datetime

from app.services.pam_service import get_pam_service, TREND_DEFINITIONS, SCENARIOS_2030
from app.security.session import verify_session
from app.config.settings import AUSPEX_DIR, AUSPEX_AGENTS_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pam", tags=["Power Attention Money"])

# Note: PAM is accessed as a tab within /trend-convergence, not as standalone page


# ============================================================================
# Request/Response Models
# ============================================================================

class PAMAnalysisRequest(BaseModel):
    """Request model for PAM analysis."""
    topic: Optional[str] = Field(
        None,
        description="Topic to focus analysis on"
    )
    analysis_type: str = Field(
        "comprehensive",
        description="Type of analysis: comprehensive, power, attention, or money"
    )
    entity_type: str = Field(
        "publisher",
        description="Entity type to focus on: publisher, tech_company, research_institution, government"
    )
    time_horizon: str = Field(
        "1_year",
        description="Time horizon: current, 6_months, 1_year, 5_years, 2030"
    )
    trend_focus: List[str] = Field(
        default=["T1", "T2", "T3", "T4", "T5"],
        description="Which 2030 trends to analyze (T1-T5)"
    )
    days_back: int = Field(
        90,
        ge=7,
        le=365,
        description="Days of articles to analyze"
    )
    article_limit: int = Field(
        100,
        ge=20,
        le=500,
        description="Maximum articles to analyze"
    )
    model: Optional[str] = Field(
        None,
        description="AI model to use for analysis (applies to all agents unless overridden)"
    )
    # New configurable parameters
    relevance_threshold: float = Field(
        0.65,
        ge=0.3,
        le=0.9,
        description="Max cosine distance for article relevance (lower = stricter)"
    )
    articles_per_topic: Optional[int] = Field(
        None,
        ge=5,
        le=100,
        description="Articles per topic (overrides article_limit calculation)"
    )
    enable_external_data: bool = Field(
        True,
        description="Fetch external data from Semantic Scholar, Google Search"
    )
    parallel_agents: bool = Field(
        True,
        description="Run pillar agents in parallel (faster but more resource intensive)"
    )
    # Per-pillar model overrides
    power_model: Optional[str] = Field(
        None,
        description="Model override for Power agent"
    )
    attention_model: Optional[str] = Field(
        None,
        description="Model override for Attention agent"
    )
    money_model: Optional[str] = Field(
        None,
        description="Model override for Money agent"
    )
    trend_model: Optional[str] = Field(
        None,
        description="Model override for Trend interpretation agent"
    )


class TrendStatusRequest(BaseModel):
    """Request model for trend status."""
    trend_ids: List[str] = Field(
        default=["T1", "T2", "T3", "T4", "T5"],
        description="Trend IDs to analyze"
    )
    days_back: int = Field(
        30,
        ge=7,
        le=90,
        description="Days to look back"
    )
    topic: Optional[str] = Field(
        None,
        description="Optional topic filter"
    )


class PublisherPositionRequest(BaseModel):
    """Request model for publisher positioning analysis."""
    publisher_name: Optional[str] = Field(
        None,
        description="Specific publisher to analyze, or None for industry-wide"
    )
    pillar_focus: str = Field(
        "all",
        description="Which pillar to focus on: trust, infrastructure, connector, or all"
    )
    topic: Optional[str] = Field(
        None,
        description="Optional topic context"
    )


class SaveDashboardRequest(BaseModel):
    """Request model for saving a dashboard."""
    name: str = Field(..., description="Dashboard name")
    description: Optional[str] = Field(None, description="Dashboard description")
    topic: Optional[str] = Field(None, description="Topic filter")
    config: Dict[str, Any] = Field(default_factory=dict, description="Dashboard configuration")
    power_analysis: Optional[Dict] = Field(None, description="Power analysis data")
    attention_analysis: Optional[Dict] = Field(None, description="Attention analysis data")
    money_analysis: Optional[Dict] = Field(None, description="Money analysis data")
    trend_analysis: Optional[Dict] = Field(None, description="Trend analysis data")
    scenario_analysis: Optional[Dict] = Field(None, description="Scenario analysis data")


class PAMScoreResponse(BaseModel):
    """Response model for PAM scores."""
    power_score: float
    attention_score: float
    money_score: float
    overall_score: float
    threat_level: str


# ============================================================================
# Core Analysis Endpoints
# ============================================================================

@router.post("/analyze")
async def run_pam_analysis(
    request: PAMAnalysisRequest,
    use_v2: bool = Query(True, description="Use agent-based v2 architecture (parallel agents, external data)"),
    user: dict = Depends(verify_session)
):
    """
    Run comprehensive PAM (Power, Attention, Money) analysis.

    This endpoint analyzes the three fundamental flows reshaping the knowledge economy:
    - POWER: Who controls infrastructure, standards, regulatory frameworks
    - ATTENTION: Who captures mindshare, citations, AI visibility
    - MONEY: Where funding flows, who gets acquired, revenue concentration

    Returns analysis structured around the 5 Key Trends for 2030.

    v2.0 Features (use_v2=true):
    - Parallel pillar agents with optional different models
    - External data from Semantic Scholar (citations) and Google Search (funding/M&A)
    - TrendCalculator for repeatable, measurable trend scoring
    - Configurable prompts loaded from markdown files
    - Data source indicators in results
    """
    try:
        service = get_pam_service()

        if use_v2:
            # Use new agent-based architecture
            result = await service.run_agent_based_analysis(
                topic=request.topic,
                analysis_type=request.analysis_type,
                entity_type=request.entity_type,
                time_horizon=request.time_horizon,
                trend_focus=request.trend_focus,
                days_back=request.days_back,
                article_limit=request.article_limit,
                model=request.model,
                username=user.get("username"),
                # v2 specific parameters
                relevance_threshold=request.relevance_threshold,
                articles_per_topic=request.articles_per_topic,
                enable_external_data=request.enable_external_data,
                parallel_agents=request.parallel_agents,
                power_model=request.power_model,
                attention_model=request.attention_model,
                money_model=request.money_model,
                trend_model=request.trend_model
            )
        else:
            # Legacy v1 analysis
            result = await service.run_comprehensive_analysis(
                topic=request.topic,
                analysis_type=request.analysis_type,
                entity_type=request.entity_type,
                time_horizon=request.time_horizon,
                trend_focus=request.trend_focus,
                days_back=request.days_back,
                article_limit=request.article_limit,
                model=request.model,
                username=user.get("username")
            )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"PAM analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executive-summary")
async def get_executive_summary(
    topic: Optional[str] = None,
    days_back: int = Query(30, ge=7, le=90),
    user: dict = Depends(verify_session)
):
    """
    Get executive summary with KPIs for PAM dashboard.

    Returns high-level scores and key insights without full analysis.
    """
    try:
        service = get_pam_service()

        # Run a lighter analysis for executive summary
        result = await service.run_comprehensive_analysis(
            topic=topic,
            analysis_type="comprehensive",
            days_back=days_back,
            article_limit=50,
            username=user.get("username")
        )

        return {
            "success": True,
            "data": {
                "executive_summary": result.get("executive_summary"),
                "scores": result.get("scores"),
                "trend_highlights": [
                    {
                        "id": t.get("id"),
                        "name": t.get("name"),
                        "score": t.get("score"),
                        "velocity": t.get("velocity")
                    }
                    for t in result.get("trend_analysis", {}).get("trends", [])[:3]
                ],
                "articles_analyzed": result.get("articles_analyzed"),
                "generated_at": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Executive summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Trend Monitoring Endpoints
# ============================================================================

@router.get("/trends")
async def get_trend_status(
    trend_ids: List[str] = Query(default=["T1", "T2", "T3", "T4", "T5"]),
    days_back: int = Query(30, ge=7, le=90),
    topic: Optional[str] = None,
    user: dict = Depends(verify_session)
):
    """
    Get current status of 2030 trends.

    Returns score, velocity, and key drivers for each trend.
    """
    try:
        service = get_pam_service()

        result = await service.get_trend_status(
            trend_ids=trend_ids,
            days_back=days_back,
            topic=topic
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Trend status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends/definitions")
async def get_trend_definitions():
    """
    Get definitions for all 2030 trends.

    Returns the 5 key trends with descriptions and keywords.
    """
    return {
        "success": True,
        "data": {
            "trends": [
                {
                    "id": tid,
                    "name": t["name"],
                    "short_name": t["short_name"],
                    "description": t["description"],
                    "dimension": t["dimension"],
                    "keywords": t["keywords"][:5]  # Top 5 keywords
                }
                for tid, t in TREND_DEFINITIONS.items()
            ]
        }
    }


# ============================================================================
# Cached Reports Endpoints
# ============================================================================

@router.get("/cached/latest")
async def get_cached_pam_report(
    topic: Optional[str] = Query(None, description="Topic filter (null for all topics)")
):
    """
    Get the latest cached PAM report.

    Returns the most recently generated PAM analysis for quick loading.
    """
    try:
        from app.services.dashboard_cache_service import DashboardCacheService
        from app.database import get_database_instance

        db = get_database_instance()
        cache_service = DashboardCacheService(db)

        # Get latest PAM report
        cached = await cache_service.get_latest_dashboard('pam', topic or 'all_topics')

        if not cached:
            return {
                "success": True,
                "data": None,
                "message": "No cached PAM report found"
            }

        return {
            "success": True,
            "data": cached
        }

    except Exception as e:
        logger.error(f"Failed to get cached PAM report: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": None
        }


@router.get("/cached/list")
async def list_cached_pam_reports(
    limit: int = Query(10, ge=1, le=50, description="Maximum reports to return")
):
    """
    List all cached PAM reports.

    Returns metadata for recent PAM analyses.
    """
    try:
        from app.database import get_database_instance
        from starlette.concurrency import run_in_threadpool

        db = get_database_instance()

        # Get all PAM cached reports
        all_cached = await run_in_threadpool(
            db.facade.list_dashboard_cache,
            limit * 3  # Get more to filter
        )

        # Filter to only PAM reports
        pam_reports = [
            r for r in all_cached
            if r.get('dashboard_type') == 'pam'
        ][:limit]

        return {
            "success": True,
            "data": {
                "reports": pam_reports,
                "total": len(pam_reports)
            }
        }

    except Exception as e:
        logger.error(f"Failed to list cached PAM reports: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": {"reports": [], "total": 0}
        }


@router.get("/trends/{trend_id}")
async def get_single_trend(
    trend_id: str,
    days_back: int = Query(30, ge=7, le=90),
    topic: Optional[str] = None,
    user: dict = Depends(verify_session)
):
    """
    Get detailed analysis for a single trend.
    """
    if trend_id not in TREND_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"Trend {trend_id} not found")

    try:
        service = get_pam_service()

        result = await service.get_trend_status(
            trend_ids=[trend_id],
            days_back=days_back,
            topic=topic
        )

        trend_data = next(
            (t for t in result.get("trends", []) if t.get("id") == trend_id),
            None
        )

        if not trend_data:
            raise HTTPException(status_code=404, detail="Trend analysis not found")

        return {
            "success": True,
            "data": {
                "trend": trend_data,
                "definition": TREND_DEFINITIONS[trend_id],
                "articles_analyzed": result.get("articles_analyzed"),
                "generated_at": result.get("generated_at")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Single trend analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Publisher Positioning Endpoints
# ============================================================================

@router.post("/publisher-position")
async def analyze_publisher_position(
    request: PublisherPositionRequest,
    user: dict = Depends(verify_session)
):
    """
    Analyze publisher strategic positioning across the three value pillars.

    The three pillars are:
    - TRUST: Peer review integrity, verification, AI detection
    - INFRASTRUCTURE: APIs, metadata, rights management, AI-ready content
    - CONNECTOR: Author relationships, community, workflow integration
    """
    try:
        service = get_pam_service()

        result = await service.analyze_publisher_position(
            publisher_name=request.publisher_name,
            pillar_focus=request.pillar_focus,
            topic=request.topic
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Publisher position analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/publisher-pillars")
async def get_publisher_pillars():
    """
    Get definitions for the three publisher value pillars.
    """
    from app.services.pam_service import PUBLISHER_PILLARS

    return {
        "success": True,
        "data": {
            "pillars": [
                {
                    "id": pid,
                    "name": p["name"],
                    "description": p["description"],
                    "components": p["components"]
                }
                for pid, p in PUBLISHER_PILLARS.items()
            ]
        }
    }


# ============================================================================
# Scenario Endpoints
# ============================================================================

@router.get("/scenarios")
async def get_scenarios():
    """
    Get 2030 scenario definitions and current probabilities.
    """
    return {
        "success": True,
        "data": {
            "scenarios": [
                {
                    "id": sid,
                    "name": s["name"],
                    "description": s["description"],
                    "regulation": s["regulation"],
                    "concentration": s["concentration"],
                    "base_probability": s["probability"]
                }
                for sid, s in SCENARIOS_2030.items()
            ],
            "axes": {
                "x": {"name": "Market Concentration", "low": "Dispersed", "high": "Concentrated"},
                "y": {"name": "Regulation Level", "low": "Minimal", "high": "Strong"}
            }
        }
    }


@router.get("/scenarios/current")
async def get_current_scenario_analysis(
    topic: Optional[str] = None,
    days_back: int = Query(30, ge=7, le=90),
    user: dict = Depends(verify_session)
):
    """
    Get current scenario analysis based on recent trends.
    """
    try:
        service = get_pam_service()

        result = await service.run_comprehensive_analysis(
            topic=topic,
            analysis_type="comprehensive",
            days_back=days_back,
            article_limit=50,
            username=user.get("username")
        )

        return {
            "success": True,
            "data": {
                "scenario_analysis": result.get("scenario_analysis"),
                "trend_analysis": result.get("trend_analysis"),
                "generated_at": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Scenario analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Dashboard Management Endpoints
# ============================================================================

@router.get("/dashboards")
async def list_dashboards(
    user: dict = Depends(verify_session)
):
    """
    List saved PAM dashboards for current user.
    """
    # TODO: Implement database query for saved dashboards
    return {
        "success": True,
        "data": {
            "dashboards": [],
            "count": 0
        }
    }


@router.post("/dashboards/save")
async def save_dashboard(
    request: SaveDashboardRequest,
    user: dict = Depends(verify_session)
):
    """
    Save current PAM dashboard configuration and data.
    """
    # TODO: Implement database save
    dashboard_id = f"pam_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    return {
        "success": True,
        "data": {
            "dashboard_id": dashboard_id,
            "name": request.name,
            "created_at": datetime.now().isoformat()
        }
    }


@router.get("/dashboards/{dashboard_id}")
async def load_dashboard(
    dashboard_id: str,
    user: dict = Depends(verify_session)
):
    """
    Load a saved PAM dashboard.
    """
    # TODO: Implement database query
    raise HTTPException(status_code=404, detail="Dashboard not found")


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    user: dict = Depends(verify_session)
):
    """
    Delete a saved PAM dashboard.
    """
    # TODO: Implement database delete
    return {
        "success": True,
        "message": f"Dashboard {dashboard_id} deleted"
    }


# ============================================================================
# Metrics Endpoints
# ============================================================================

@router.get("/metrics/power")
async def get_power_metrics(
    entity_id: Optional[str] = None,
    days_back: int = Query(365, ge=30, le=730),
    user: dict = Depends(verify_session)
):
    """
    Get power-related metrics over time.
    """
    # TODO: Implement metrics query from pam_metrics_timeseries
    return {
        "success": True,
        "data": {
            "metrics": [],
            "period": {"days_back": days_back}
        }
    }


@router.get("/metrics/attention")
async def get_attention_metrics(
    entity_id: Optional[str] = None,
    days_back: int = Query(365, ge=30, le=730),
    user: dict = Depends(verify_session)
):
    """
    Get attention-related metrics over time.
    """
    # TODO: Implement metrics query
    return {
        "success": True,
        "data": {
            "metrics": [],
            "period": {"days_back": days_back}
        }
    }


@router.get("/metrics/money")
async def get_money_metrics(
    entity_id: Optional[str] = None,
    days_back: int = Query(365, ge=30, le=730),
    user: dict = Depends(verify_session)
):
    """
    Get money-related metrics over time.
    """
    # TODO: Implement metrics query
    return {
        "success": True,
        "data": {
            "metrics": [],
            "period": {"days_back": days_back}
        }
    }


# ============================================================================
# Trending History Endpoints
# ============================================================================

@router.get("/trends/history")
async def get_pam_trend_history(
    days_back: int = Query(90, ge=7, le=365),
    topic: Optional[str] = Query(None, description="Topic filter for trend history"),
    user: dict = Depends(verify_session)
):
    """
    Get historical trend scores for charting.

    Returns T1-T5 scores over time for trend analysis and visualization.
    """
    try:
        service = get_pam_service()
        result = await service.get_trend_history(days_back=days_back, topic=topic)

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Failed to get trend history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/history")
async def get_pam_metrics_history(
    metric_names: List[str] = Query(
        default=['power_score', 'attention_score', 'money_score', 'overall_score'],
        description="Metric names to retrieve"
    ),
    days_back: int = Query(90, ge=7, le=365),
    user: dict = Depends(verify_session)
):
    """
    Get historical metric values for trending analysis.

    Returns PAM dimension scores and trend scores over time.
    Available metrics: power_score, attention_score, money_score, overall_score,
    t1_score, t2_score, t3_score, t4_score, t5_score
    """
    try:
        service = get_pam_service()
        result = await service.get_metrics_history(
            metric_names=metric_names,
            days_back=days_back
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/dataset")
async def get_analysis_dataset(
    run_id: str,
    user: dict = Depends(verify_session)
):
    """
    Get the article dataset used for a specific analysis run.

    Returns all articles used in the analysis, grouped by pillar.
    """
    try:
        service = get_pam_service()
        result = await service.get_run_dataset(run_id)

        if result.get('error'):
            raise HTTPException(status_code=404, detail=result['error'])

        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Data Management Endpoints
# ============================================================================

@router.get("/tracking/stats")
async def get_tracking_stats(
    user: dict = Depends(verify_session)
):
    """
    Get statistics about tracked PAM data.

    Returns counts of trend snapshots, metrics, article datasets, and cached queries.
    """
    try:
        service = get_pam_service()
        stats = await service.get_tracking_stats()

        return {
            "success": True,
            "data": stats
        }

    except Exception as e:
        logger.error(f"Failed to get tracking stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tracking/reset")
async def reset_tracking_data(
    confirm: bool = Query(False, description="Must be true to actually reset data"),
    user: dict = Depends(verify_session)
):
    """
    Reset all PAM tracking data.

    WARNING: This will delete all trend snapshots, metrics timeseries, article datasets, and cached queries.
    Set confirm=true to actually perform the reset.
    """
    try:
        service = get_pam_service()
        result = await service.reset_tracking_data(confirm=confirm)

        return {
            "success": result.get('success', False),
            "data": result
        }

    except Exception as e:
        logger.error(f"Failed to reset tracking data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Entity Endpoints (Monitored Brands/Entities for Brand Visibility)
# ============================================================================

class MonitoredEntityRequest(BaseModel):
    """Request model for adding a monitored entity."""
    entity_name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field("brand", pattern="^(brand|publisher|tech_company|research_institution|government|competitor)$")
    entity_subtype: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = None,
    sort_by: str = Query("entity_name", pattern="^(entity_name|overall_influence|power_score|attention_score|money_score|created_at)$"),
    limit: int = Query(100, ge=10, le=500),
    user: dict = Depends(verify_session)
):
    """
    List monitored entities (brands) for brand visibility tracking.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build query
        where_clause = ""
        params = {"limit": limit}
        if entity_type:
            where_clause = "WHERE entity_type = :entity_type"
            params["entity_type"] = entity_type

        query = f"""
            SELECT id, entity_name, entity_type, entity_subtype,
                   power_score, attention_score, money_score, overall_influence,
                   metadata, last_analyzed, created_at
            FROM pam_entities
            {where_clause}
            ORDER BY {sort_by} DESC NULLS LAST
            LIMIT :limit
        """

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        entities = []
        for row in rows:
            entities.append({
                "id": row[0],
                "entity_name": row[1],
                "entity_type": row[2],
                "entity_subtype": row[3],
                "power_score": row[4],
                "attention_score": row[5],
                "money_score": row[6],
                "overall_influence": row[7],
                "metadata": row[8],
                "last_analyzed": row[9].isoformat() if row[9] else None,
                "created_at": row[10].isoformat() if row[10] else None
            })

        return {
            "success": True,
            "data": {
                "entities": entities,
                "count": len(entities)
            }
        }

    except Exception as e:
        logger.error(f"Failed to list entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entities")
async def create_entity(
    request: MonitoredEntityRequest,
    user: dict = Depends(verify_session)
):
    """
    Add a new monitored entity (brand) for brand visibility tracking.
    """
    from sqlalchemy import text
    from app.database import get_database_instance
    import uuid

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        entity_id = str(uuid.uuid4())

        query = """
            INSERT INTO pam_entities (id, entity_name, entity_type, entity_subtype, metadata, created_at, updated_at)
            VALUES (:id, :name, :type, :subtype, :metadata, NOW(), NOW())
            ON CONFLICT (entity_name, entity_type) DO UPDATE SET
                entity_subtype = EXCLUDED.entity_subtype,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """

        import json
        result = conn.execute(text(query), {
            "id": entity_id,
            "name": request.entity_name,
            "type": request.entity_type,
            "subtype": request.entity_subtype,
            "metadata": json.dumps(request.metadata) if request.metadata else None
        })
        conn.commit()

        returned_id = result.fetchone()[0]

        return {
            "success": True,
            "data": {
                "id": returned_id,
                "entity_name": request.entity_name,
                "entity_type": request.entity_type
            },
            "message": f"Entity '{request.entity_name}' added for monitoring"
        }

    except Exception as e:
        logger.error(f"Failed to create entity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}")
async def get_entity_detail(
    entity_id: str,
    include_timeseries: bool = True,
    user: dict = Depends(verify_session)
):
    """
    Get detailed entity analysis.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        query = """
            SELECT id, entity_name, entity_type, entity_subtype,
                   power_score, attention_score, money_score, overall_influence,
                   trust_pillar_score, infrastructure_pillar_score, connector_pillar_score,
                   pillar_details, strategic_position, threat_exposure, opportunity_score,
                   strengths, vulnerabilities, strategic_recommendations,
                   metadata, data_sources, last_analyzed, created_at, updated_at
            FROM pam_entities
            WHERE id = :id
        """

        result = conn.execute(text(query), {"id": entity_id})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Entity not found")

        entity = {
            "id": row[0],
            "entity_name": row[1],
            "entity_type": row[2],
            "entity_subtype": row[3],
            "scores": {
                "power": row[4],
                "attention": row[5],
                "money": row[6],
                "overall": row[7]
            },
            "pillars": {
                "trust": row[8],
                "infrastructure": row[9],
                "connector": row[10],
                "details": row[11]
            },
            "strategic_position": row[12],
            "threat_exposure": row[13],
            "opportunity_score": row[14],
            "strengths": row[15],
            "vulnerabilities": row[16],
            "recommendations": row[17],
            "metadata": row[18],
            "data_sources": row[19],
            "last_analyzed": row[20].isoformat() if row[20] else None,
            "created_at": row[21].isoformat() if row[21] else None
        }

        return {
            "success": True,
            "data": entity
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str,
    user: dict = Depends(verify_session)
):
    """
    Remove a monitored entity.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        query = "DELETE FROM pam_entities WHERE id = :id RETURNING entity_name"
        result = conn.execute(text(query), {"id": entity_id})
        conn.commit()

        deleted = result.fetchone()
        if not deleted:
            raise HTTPException(status_code=404, detail="Entity not found")

        return {
            "success": True,
            "message": f"Entity '{deleted[0]}' removed from monitoring"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete entity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entities/analyze")
async def analyze_entity(
    entity_name: str,
    entity_type: str = Query(..., pattern="^(publisher|tech_company|research_institution|government)$"),
    user: dict = Depends(verify_session)
):
    """
    Run PAM analysis for a specific entity.
    """
    try:
        service = get_pam_service()

        result = await service.analyze_publisher_position(
            publisher_name=entity_name,
            pillar_focus="all"
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"Entity analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Pillar Query Management Endpoints
# ============================================================================

@router.get("/pillar-queries")
async def list_pillar_queries(
    user: dict = Depends(verify_session)
):
    """
    List all cached pillar queries.

    Returns the semantic search queries used for each PAM pillar.
    """
    try:
        service = get_pam_service()
        queries = {}

        for pillar in ["power", "attention", "money"]:
            cached = await service._get_cached_pillar_queries(pillar)
            queries[pillar] = {
                "queries": cached if cached else [],
                "is_cached": cached is not None
            }

        return {
            "success": True,
            "data": queries
        }

    except Exception as e:
        logger.error(f"Failed to list pillar queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pillar-queries/{pillar}")
async def get_pillar_queries(
    pillar: str,
    user: dict = Depends(verify_session)
):
    """
    Get cached queries for a specific pillar.
    """
    if pillar not in ["power", "attention", "money"]:
        raise HTTPException(status_code=400, detail="Invalid pillar. Must be: power, attention, money")

    try:
        service = get_pam_service()
        cached = await service._get_cached_pillar_queries(pillar)

        return {
            "success": True,
            "data": {
                "pillar": pillar,
                "queries": cached if cached else [],
                "is_cached": cached is not None
            }
        }

    except Exception as e:
        logger.error(f"Failed to get pillar queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdatePillarQueriesRequest(BaseModel):
    """Request to update pillar queries."""
    queries: List[str] = Field(..., min_items=5, max_items=15)


@router.put("/pillar-queries/{pillar}")
async def update_pillar_queries(
    pillar: str,
    request: UpdatePillarQueriesRequest,
    user: dict = Depends(verify_session)
):
    """
    Update cached queries for a pillar.
    """
    if pillar not in ["power", "attention", "money"]:
        raise HTTPException(status_code=400, detail="Invalid pillar")

    try:
        service = get_pam_service()
        await service._save_pillar_queries(pillar, request.queries, "manual_update")

        return {
            "success": True,
            "message": f"Updated {len(request.queries)} queries for {pillar} pillar"
        }

    except Exception as e:
        logger.error(f"Failed to update pillar queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pillar-queries/{pillar}")
async def delete_pillar_queries(
    pillar: str,
    user: dict = Depends(verify_session)
):
    """
    Delete cached queries for a pillar (will regenerate on next analysis).
    """
    if pillar not in ["power", "attention", "money"]:
        raise HTTPException(status_code=400, detail="Invalid pillar")

    try:
        from app.database import get_database_instance
        db = get_database_instance()

        db.execute_query(
            "UPDATE pam_pillar_queries SET is_active = FALSE WHERE pillar = ?",
            (pillar,)
        )

        return {
            "success": True,
            "message": f"Deleted cached queries for {pillar} pillar. Will regenerate on next analysis."
        }

    except Exception as e:
        logger.error(f"Failed to delete pillar queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pillar-queries/{pillar}/regenerate")
async def regenerate_pillar_queries(
    pillar: str,
    model: Optional[str] = Query(None, description="Model to use for generation"),
    user: dict = Depends(verify_session)
):
    """
    Force regenerate queries for a pillar.
    """
    if pillar not in ["power", "attention", "money"]:
        raise HTTPException(status_code=400, detail="Invalid pillar")

    try:
        service = get_pam_service()
        queries = await service._generate_pillar_queries(
            pillar,
            model=model or "gpt-5.4-mini",
            force_regenerate=True
        )

        return {
            "success": True,
            "data": {
                "pillar": pillar,
                "queries": queries,
                "regenerated": True
            }
        }

    except Exception as e:
        logger.error(f"Failed to regenerate pillar queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Prompt Management Endpoints
# ============================================================================

@router.get("/prompts")
async def list_pam_prompts(
    user: dict = Depends(verify_session)
):
    """
    List all PAM agent prompts.
    """
    import yaml

    prompts = []

    try:
        for filename in os.listdir(AUSPEX_AGENTS_DIR):
            if filename.startswith("pam_") and filename.endswith(".md"):
                filepath = os.path.join(AUSPEX_AGENTS_DIR, filename)
                with open(filepath, 'r') as f:
                    content = f.read()

                # Parse YAML frontmatter
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        frontmatter = yaml.safe_load(content[3:end])
                        prompts.append({
                            "id": filename.replace(".md", ""),
                            "name": frontmatter.get("name", filename),
                            "description": frontmatter.get("description", ""),
                            "model": frontmatter.get("model_config", {}).get("model", "gpt-5.4-mini"),
                            "temperature": frontmatter.get("model_config", {}).get("temperature", 0.3),
                            "version": frontmatter.get("version", "1.0.0")
                        })

        return {
            "success": True,
            "data": {"prompts": prompts}
        }

    except Exception as e:
        logger.error(f"Failed to list PAM prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/{prompt_id}")
async def get_pam_prompt(
    prompt_id: str,
    user: dict = Depends(verify_session)
):
    """
    Get a specific PAM agent prompt with full content.
    """
    import os
    import yaml

    filepath = os.path.join(AUSPEX_AGENTS_DIR, f"{prompt_id}.md")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        metadata = {}
        body = content

        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                metadata = yaml.safe_load(content[3:end])
                body = content[end + 3:].strip()

        return {
            "success": True,
            "data": {
                "id": prompt_id,
                "metadata": metadata,
                "content": body,
                "raw": content
            }
        }

    except Exception as e:
        logger.error(f"Failed to get prompt {prompt_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdatePromptRequest(BaseModel):
    """Request to update a prompt."""
    content: str = Field(..., description="New markdown content (after frontmatter)")
    model: Optional[str] = Field(None, description="Model override")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperature override")


@router.put("/prompts/{prompt_id}")
async def update_pam_prompt(
    prompt_id: str,
    request: UpdatePromptRequest,
    user: dict = Depends(verify_session)
):
    """
    Update a PAM agent prompt.
    """
    import os
    import yaml

    filepath = os.path.join(AUSPEX_AGENTS_DIR, f"{prompt_id}.md")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")

    try:
        # Read existing file
        with open(filepath, 'r') as f:
            content = f.read()

        metadata = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                metadata = yaml.safe_load(content[3:end])

        # Update model config if provided
        if "model_config" not in metadata:
            metadata["model_config"] = {}

        if request.model:
            metadata["model_config"]["model"] = request.model
        if request.temperature is not None:
            metadata["model_config"]["temperature"] = request.temperature

        # Rebuild file
        new_content = "---\n"
        new_content += yaml.dump(metadata, default_flow_style=False)
        new_content += "---\n\n"
        new_content += request.content

        with open(filepath, 'w') as f:
            f.write(new_content)

        return {
            "success": True,
            "message": f"Updated prompt {prompt_id}"
        }

    except Exception as e:
        logger.error(f"Failed to update prompt {prompt_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Configuration Endpoints
# ============================================================================

@router.get("/config")
async def get_pam_config(
    user: dict = Depends(verify_session)
):
    """
    Get PAM configuration.
    """
    import json

    config_path = os.path.join(AUSPEX_DIR, "pam_config.json")

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        return {
            "success": True,
            "data": config
        }

    except FileNotFoundError:
        return {
            "success": True,
            "data": {},
            "message": "No custom config found, using defaults"
        }
    except Exception as e:
        logger.error(f"Failed to get PAM config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class UpdatePAMConfigRequest(BaseModel):
    """Request to update PAM config."""
    defaults: Optional[Dict[str, Any]] = None
    agents: Optional[Dict[str, Dict[str, Any]]] = None
    external_data: Optional[Dict[str, Dict[str, Any]]] = None
    trend_calculator: Optional[Dict[str, Any]] = None
    score_calculation: Optional[Dict[str, Any]] = None


@router.put("/config")
async def update_pam_config(
    request: UpdatePAMConfigRequest,
    user: dict = Depends(verify_session)
):
    """
    Update PAM configuration.
    """
    import json

    config_path = os.path.join(AUSPEX_DIR, "pam_config.json")

    try:
        # Read existing config
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {}

        # Update only provided fields
        if request.defaults:
            config["defaults"] = {**config.get("defaults", {}), **request.defaults}
        if request.agents:
            config["agents"] = {**config.get("agents", {}), **request.agents}
        if request.external_data:
            config["external_data"] = {**config.get("external_data", {}), **request.external_data}
        if request.trend_calculator:
            config["trend_calculator"] = {**config.get("trend_calculator", {}), **request.trend_calculator}
        if request.score_calculation:
            config["score_calculation"] = {**config.get("score_calculation", {}), **request.score_calculation}

        # Write updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

        return {
            "success": True,
            "message": "PAM config updated",
            "data": config
        }

    except Exception as e:
        logger.error(f"Failed to update PAM config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/provider-status")
async def get_provider_status():
    """
    Get status of external data providers.

    Returns availability and configuration of:
    - Google Search (requires API key)
    - Semantic Scholar (works without key, rate-limited)
    """
    from app.services.pam_service import PAMService
    service = PAMService()
    return service.get_provider_status()


# ============================================================================
# Keyword Presets Endpoints
# ============================================================================

@router.get("/presets")
async def get_keyword_presets(user: dict = Depends(verify_session)):
    """
    Get available keyword presets and the currently selected preset.

    Returns:
    - available: List of presets with name, description
    - current: The currently active preset name
    """
    import json

    config_path = os.path.join(AUSPEX_DIR, "pam_config.json")

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        deep_search = config.get("deep_search_keywords", {})
        presets_config = deep_search.get("presets", {})
        current_preset = config.get("keyword_preset", "scholarly_publishing")

        # Build list of available presets
        available = []
        for name, preset_data in presets_config.items():
            available.append({
                "name": name,
                "description": preset_data.get("description", ""),
                "keywords_count": {
                    "cost_dynamics": len(preset_data.get("cost_dynamics", [])),
                    "ma_activity": len(preset_data.get("ma_activity", [])),
                    "regulatory": len(preset_data.get("regulatory", [])),
                },
                "entities": list(preset_data.get("entity_variations", {}).keys())
            })

        return {
            "data": {
                "available": available,
                "current": current_preset
            }
        }
    except Exception as e:
        logger.error(f"Failed to get presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SetPresetRequest(BaseModel):
    """Request to set the active keyword preset."""
    preset: str = Field(..., description="Name of the preset to activate")


@router.put("/presets")
async def set_keyword_preset(
    request: SetPresetRequest,
    user: dict = Depends(verify_session)
):
    """
    Set the active keyword preset for PAM analysis.
    """
    import json

    config_path = os.path.join(AUSPEX_DIR, "pam_config.json")

    try:
        # Read current config
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Validate preset exists
        presets = config.get("deep_search_keywords", {}).get("presets", {})
        if request.preset not in presets:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset: {request.preset}. Available: {list(presets.keys())}"
            )

        # Update preset
        config["keyword_preset"] = request.preset

        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

        logger.info(f"Set keyword preset to: {request.preset}")

        return {
            "status": "success",
            "data": {
                "preset": request.preset,
                "description": presets[request.preset].get("description", "")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Specialized Database Search Endpoints
# ============================================================================

class SpecializedSearchRequest(BaseModel):
    """Request for specialized database searches."""
    limit: int = Field(100, ge=10, le=500, description="Maximum articles to return")
    topic_filter: Optional[str] = Field(None, description="Optional topic to filter by")


class SpecializedSearchResult(BaseModel):
    """Result from specialized database search."""
    articles: List[Dict[str, Any]]
    total_found: int
    search_type: str
    keywords_matched: Dict[str, int]


@router.post("/search/ma-activity")
async def search_ma_activity(
    request: SpecializedSearchRequest = SpecializedSearchRequest(),
    user: dict = Depends(verify_session)
):
    """
    Search entire database for M&A activity articles.

    Searches for:
    - Acquisitions and mergers
    - Funding rounds (Series A, B, C, etc.)
    - Investment announcements
    - Market consolidation signals

    No date filter - searches entire database.
    """
    import json
    from app.database import get_database_instance

    # M&A keywords to search
    ma_keywords = [
        'acquisition', 'acquires', 'acquired', 'acquire',
        'merger', 'merges', 'merged', 'merge',
        'funding', 'raises', 'raised', 'investment',
        'series a', 'series b', 'series c', 'series d',
        'ipo', 'valuation', 'unicorn',
        'buyout', 'takeover', 'consolidation',
        'deal', 'transaction'
    ]

    try:
        from sqlalchemy import text
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build search query with OR conditions for all keywords
        # Note: articles table uses 'summary' not 'content'
        keyword_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in ma_keywords
        ])

        # Optional topic filter
        topic_filter = ""
        params = {"limit": request.limit}
        if request.topic_filter:
            topic_filter = "AND (LOWER(title) LIKE :topic_filter OR LOWER(summary) LIKE :topic_filter)"
            params["topic_filter"] = f'%{request.topic_filter.lower()}%'

        query = f"""
            SELECT uri, title, summary, news_source, publication_date, analyzed
            FROM articles
            WHERE ({keyword_conditions}) {topic_filter}
            ORDER BY publication_date DESC NULLS LAST
            LIMIT :limit
        """

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        # Count keyword matches
        keyword_counts: Dict[str, int] = {kw: 0 for kw in ma_keywords}
        articles = []

        for row in rows:
            article = {
                'uri': row[0],
                'title': row[1],
                'summary': row[2][:500] if row[2] else '',  # Truncate summary
                'source': row[3],
                'publication_date': row[4] or '',
                'analyzed': row[5]
            }
            articles.append(article)

            # Count which keywords matched
            text = (row[1] or '').lower() + ' ' + (row[2] or '').lower()
            for kw in ma_keywords:
                if kw in text:
                    keyword_counts[kw] += 1

        # Filter out zero counts
        keyword_counts = {k: v for k, v in keyword_counts.items() if v > 0}

        return {
            "success": True,
            "data": {
                "articles": articles,
                "total_found": len(articles),
                "search_type": "ma_activity",
                "keywords_matched": keyword_counts
            }
        }

    except Exception as e:
        logger.error(f"M&A search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/regulation")
async def search_regulation_articles(
    request: SpecializedSearchRequest = SpecializedSearchRequest(),
    user: dict = Depends(verify_session)
):
    """
    Search entire database for regulation/policy articles.

    Searches for:
    - AI regulations (EU AI Act, etc.)
    - Copyright law and licensing
    - Compliance requirements
    - Government policy
    - Legal developments

    No date filter - searches entire database.
    """
    import json
    from app.database import get_database_instance

    # Regulation keywords to search
    regulation_keywords = [
        'regulation', 'regulatory', 'regulator',
        'eu ai act', 'ai act', 'legislation',
        'copyright', 'licensing', 'intellectual property',
        'compliance', 'policy', 'policies',
        'government', 'legal', 'lawsuit', 'court',
        'antitrust', 'ftc', 'doj', 'enforcement',
        'privacy', 'gdpr', 'data protection',
        'transparency', 'accountability', 'audit',
        'executive order', 'bill', 'law'
    ]

    try:
        from sqlalchemy import text
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build search query with OR conditions for all keywords
        # Note: articles table uses 'summary' not 'content'
        keyword_conditions = " OR ".join([
            f"(LOWER(title) LIKE '%{kw}%' OR LOWER(summary) LIKE '%{kw}%')"
            for kw in regulation_keywords
        ])

        # Optional topic filter
        topic_filter = ""
        params = {"limit": request.limit}
        if request.topic_filter:
            topic_filter = "AND (LOWER(title) LIKE :topic_filter OR LOWER(summary) LIKE :topic_filter)"
            params["topic_filter"] = f'%{request.topic_filter.lower()}%'

        query = f"""
            SELECT uri, title, summary, news_source, publication_date, analyzed
            FROM articles
            WHERE ({keyword_conditions}) {topic_filter}
            ORDER BY publication_date DESC NULLS LAST
            LIMIT :limit
        """

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        # Count keyword matches
        keyword_counts: Dict[str, int] = {kw: 0 for kw in regulation_keywords}
        articles = []

        for row in rows:
            article = {
                'uri': row[0],
                'title': row[1],
                'summary': row[2][:500] if row[2] else '',  # Truncate summary
                'source': row[3],
                'publication_date': row[4] or '',
                'analyzed': row[5]
            }
            articles.append(article)

            # Count which keywords matched
            text = (row[1] or '').lower() + ' ' + (row[2] or '').lower()
            for kw in regulation_keywords:
                if kw in text:
                    keyword_counts[kw] += 1

        # Filter out zero counts
        keyword_counts = {k: v for k, v in keyword_counts.items() if v > 0}

        return {
            "success": True,
            "data": {
                "articles": articles,
                "total_found": len(articles),
                "search_type": "regulation",
                "keywords_matched": keyword_counts
            }
        }

    except Exception as e:
        logger.error(f"Regulation search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Event Extraction Endpoints
# ============================================================================

class ExtractionRequest(BaseModel):
    """Request model for event extraction."""
    days_back: int = Field(30, ge=7, le=365)
    batch_size: int = Field(50, ge=10, le=100)
    max_articles: int = Field(500, ge=50, le=2000)
    model: Optional[str] = Field(None, description="Model to use for extraction (e.g., gpt-5.4-mini, gpt-5.4)")


@router.post("/events/extract")
async def run_event_extraction(
    request: ExtractionRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(verify_session)
):
    """
    Trigger background event extraction from articles.

    Extracts M&A events, funding rounds, and regulatory events into dedicated tables
    for faster querying during PAM analysis.
    """
    from app.services.pam_event_extraction_service import get_pam_event_extraction_service

    try:
        service = get_pam_event_extraction_service()

        # Set model if specified
        if request.model:
            service.set_model(request.model)

        # Run extraction in background
        async def run_extraction():
            return await service.run_extraction_cycle(
                days_back=request.days_back,
                batch_size=request.batch_size,
                max_articles=request.max_articles,
            )

        background_tasks.add_task(lambda: asyncio.run(run_extraction()))

        return {
            "success": True,
            "message": f"Event extraction started for last {request.days_back} days",
            "model": request.model or service._model,
            "max_articles": request.max_articles
        }

    except Exception as e:
        logger.error(f"Failed to start event extraction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/financial")
async def get_financial_events(
    event_type: Optional[str] = Query(None, description="Filter by event type (acquisition, merger, funding_round, ipo)"),
    days_back: int = Query(90, ge=7, le=365),
    limit: int = Query(50, ge=10, le=200),
    user: dict = Depends(verify_session)
):
    """
    Get extracted financial events (M&A, funding, IPOs).
    """
    from app.services.pam_event_extraction_service import get_pam_event_extraction_service

    try:
        service = get_pam_event_extraction_service()
        events = await service.get_recent_financial_events(
            event_type=event_type,
            days_back=days_back,
            limit=limit
        )

        return {
            "success": True,
            "data": {
                "events": events,
                "total": len(events),
                "filters": {
                    "event_type": event_type,
                    "days_back": days_back
                }
            }
        }

    except Exception as e:
        logger.error(f"Failed to get financial events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/regulatory")
async def get_regulatory_events(
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction (EU, US, UK, etc.)"),
    days_back: int = Query(90, ge=7, le=365),
    limit: int = Query(50, ge=10, le=200),
    user: dict = Depends(verify_session)
):
    """
    Get extracted regulatory events.
    """
    from app.services.pam_event_extraction_service import get_pam_event_extraction_service

    try:
        service = get_pam_event_extraction_service()
        events = await service.get_recent_regulatory_events(
            jurisdiction=jurisdiction,
            days_back=days_back,
            limit=limit
        )

        return {
            "success": True,
            "data": {
                "events": events,
                "total": len(events),
                "filters": {
                    "jurisdiction": jurisdiction,
                    "days_back": days_back
                }
            }
        }

    except Exception as e:
        logger.error(f"Failed to get regulatory events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/summary")
async def get_events_summary(
    days_back: int = Query(30, ge=7, le=365),
    user: dict = Depends(verify_session)
):
    """
    Get summary of all extracted events.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    try:
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Financial events summary
        fin_query = f"""
            SELECT
                event_type,
                COUNT(*) as count,
                COUNT(DISTINCT acquirer) as unique_acquirers,
                COUNT(DISTINCT target) as unique_targets,
                SUM(deal_value_usd) as total_deal_value
            FROM pam_financial_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
            GROUP BY event_type
            ORDER BY count DESC
        """
        fin_result = conn.execute(text(fin_query))
        fin_rows = fin_result.fetchall()

        financial_summary = {
            "by_type": [
                {
                    "event_type": row[0],
                    "count": row[1],
                    "unique_acquirers": row[2],
                    "unique_targets": row[3],
                    "total_deal_value": row[4]
                }
                for row in fin_rows
            ],
            "total_events": sum(row[1] for row in fin_rows)
        }

        # Regulatory events summary
        reg_query = f"""
            SELECT
                jurisdiction,
                event_type,
                COUNT(*) as count,
                AVG(t4_impact_score) as avg_impact
            FROM pam_regulatory_events
            WHERE event_date >= CURRENT_DATE - INTERVAL '{days_back} days'
            GROUP BY jurisdiction, event_type
            ORDER BY count DESC
        """
        reg_result = conn.execute(text(reg_query))
        reg_rows = reg_result.fetchall()

        regulatory_summary = {
            "by_jurisdiction_type": [
                {
                    "jurisdiction": row[0],
                    "event_type": row[1],
                    "count": row[2],
                    "avg_impact": round(row[3], 2) if row[3] else None
                }
                for row in reg_rows
            ],
            "total_events": sum(row[2] for row in reg_rows)
        }

        return {
            "success": True,
            "data": {
                "financial": financial_summary,
                "regulatory": regulatory_summary,
                "days_back": days_back
            }
        }

    except Exception as e:
        logger.error(f"Failed to get events summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
