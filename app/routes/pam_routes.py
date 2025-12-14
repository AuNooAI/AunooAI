"""
Power, Attention & Money (PAM) API Routes

Provides endpoints for:
- Comprehensive PAM analysis
- 2030 trend monitoring
- Publisher positioning analysis
- Financial and regulatory event tracking
- Saved dashboards
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from app.services.pam_service import get_pam_service, TREND_DEFINITIONS, SCENARIOS_2030
from app.security.session import verify_session

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
        description="AI model to use for analysis"
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
    user: dict = Depends(verify_session)
):
    """
    Run comprehensive PAM (Power, Attention, Money) analysis.

    This endpoint analyzes the three fundamental flows reshaping the knowledge economy:
    - POWER: Who controls infrastructure, standards, regulatory frameworks
    - ATTENTION: Who captures mindshare, citations, AI visibility
    - MONEY: Where funding flows, who gets acquired, revenue concentration

    Returns analysis structured around the 5 Key Trends for 2030.
    """
    try:
        service = get_pam_service()

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
# Events Endpoints
# ============================================================================

@router.get("/events/financial")
async def get_financial_events(
    event_type: Optional[str] = None,
    days_back: int = Query(90, ge=7, le=365),
    min_value: Optional[int] = None,
    user: dict = Depends(verify_session)
):
    """
    Get M&A and funding events.
    """
    # TODO: Implement from pam_financial_events table
    return {
        "success": True,
        "data": {
            "events": [],
            "count": 0,
            "period": {"days_back": days_back}
        }
    }


@router.get("/events/regulatory")
async def get_regulatory_events(
    jurisdiction: Optional[str] = None,
    days_back: int = Query(90, ge=7, le=365),
    user: dict = Depends(verify_session)
):
    """
    Get regulatory developments.
    """
    # TODO: Implement from pam_regulatory_events table
    return {
        "success": True,
        "data": {
            "events": [],
            "count": 0,
            "period": {"days_back": days_back}
        }
    }


# ============================================================================
# Entity Endpoints
# ============================================================================

@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = None,
    sort_by: str = Query("overall_influence", regex="^(overall_influence|power_score|attention_score|money_score)$"),
    limit: int = Query(50, ge=10, le=200),
    user: dict = Depends(verify_session)
):
    """
    List tracked entities with PAM scores.
    """
    # TODO: Implement from pam_entities table
    return {
        "success": True,
        "data": {
            "entities": [],
            "count": 0
        }
    }


@router.get("/entities/{entity_id}")
async def get_entity_detail(
    entity_id: str,
    include_timeseries: bool = True,
    user: dict = Depends(verify_session)
):
    """
    Get detailed entity analysis.
    """
    # TODO: Implement from pam_entities and pam_metrics_timeseries
    raise HTTPException(status_code=404, detail="Entity not found")


@router.post("/entities/analyze")
async def analyze_entity(
    entity_name: str,
    entity_type: str = Query(..., regex="^(publisher|tech_company|research_institution|government)$"),
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


