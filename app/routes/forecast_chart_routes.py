"""
Routes for evidence-based forecast chart generation.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.forecast_chart_service import get_forecast_chart_service
from app.security.session import verify_session

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

def _convert_timeframe_to_days(timeframe: str) -> int:
    """Convert timeframe string to number of days."""
    timeframe = timeframe.lower().strip()
    
    # Handle predefined timeframes
    timeframe_mapping = {
        '1d': 1,
        '1w': 7,
        '1m': 30,
        '90d': 90,
        '180d': 180,
        '365d': 365,
        # Legacy support
        '1': 1,
        '7': 7,
        '30': 30,
        '90': 90,
        '180': 180,
        '365': 365
    }
    
    if timeframe in timeframe_mapping:
        return timeframe_mapping[timeframe]
    
    # Handle custom day values (e.g., "45d" or "45")
    try:
        if timeframe.endswith('d'):
            return int(timeframe[:-1])
        else:
            return int(timeframe)
    except ValueError:
        logger.warning(f"Invalid timeframe '{timeframe}', defaulting to 365 days")
        return 365

router = APIRouter(prefix="/api/forecast-charts", tags=["forecast-charts"])

# Add a separate router for the web page (without API prefix)
web_router = APIRouter(tags=["forecast-charts-web"])

@web_router.get("/forecast-chart", response_class=HTMLResponse)
async def forecast_chart_page(request: Request):
    """Serve the forecast chart interface page."""
    return templates.TemplateResponse("forecast_chart.html", {"request": request})

@web_router.get("/consensus-analysis", response_class=HTMLResponse)
async def consensus_analysis_page(request: Request, session=Depends(verify_session)):
    """Serve the consensus analysis interface page."""
    from app.main import get_template_context
    return templates.TemplateResponse("consensus_analysis.html", get_template_context(request, {"session": session}))

@router.get("/generate/{topic}")
async def generate_forecast_chart(
    topic: str,
    timeframe: str = Query(default="365d", description="Timeframe: 1d, 1w, 1m, 90d, 180d, 365d, or custom days"),
    title_prefix: str = Query(default="AI & Machine Learning", description="Prefix for chart title"),
    interactive: bool = Query(default=False, description="Generate interactive chart with tooltips"),
    categories: Optional[str] = Query(default=None, description="Comma-separated list of categories to include"),
    clusters: Optional[str] = Query(default=None, description="Comma-separated list of clusters to include")
):
    """
    Generate an evidence-based forecast chart for a specific topic.
    
    Args:
        topic: The topic to analyze and generate forecast for
        timeframe: Time period for data collection (default: 365 days)
        title_prefix: Prefix for the chart title
        interactive: Generate interactive chart with hover tooltips
        
    Returns:
        JSON response with base64 encoded chart image or HTML for interactive chart
    """
    try:
        service = get_forecast_chart_service()
        
        # Convert timeframe to days
        timeframe_days = _convert_timeframe_to_days(timeframe)
        
        # Parse categories and clusters
        selected_categories = categories.split(',') if categories else None
        selected_clusters = clusters.split(',') if clusters else None
        
        chart_data = await service.generate_evidence_based_forecast_chart(
            topic=topic,
            timeframe=str(timeframe_days),
            title_prefix=title_prefix,
            interactive=interactive,
            selected_categories=selected_categories,
            selected_clusters=selected_clusters
        )
        
        return JSONResponse(
            content={
                "success": True,
                "chart_data": chart_data,
                "topic": topic,
                "timeframe": timeframe,
                "interactive": interactive,
                "message": f"Forecast chart generated successfully for topic: {topic}"
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating forecast chart for topic {topic}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate forecast chart: {str(e)}"
        )

@router.get("/topics")
async def get_available_topics():
    """
    Get list of available topics that have data for forecast generation.
    
    Returns:
        JSON response with available topics
    """
    try:
        service = get_forecast_chart_service()
        
        # Get topics that actually have categories and data
        available_topics = await service.get_topics_with_categories()
        
        return JSONResponse(
            content={
                "success": True,
                "topics": available_topics,
                "message": f"Found {len(available_topics)} topics with forecast data available"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving available topics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve topics: {str(e)}"
        )

@router.get("/categories/{topic}")
async def get_topic_categories(topic: str):
    """
    Get available categories for a specific topic.
    
    Args:
        topic: The topic to get categories for
        
    Returns:
        JSON response with available categories
    """
    try:
        service = get_forecast_chart_service()
        
        # Get categories from the analyzer
        from app.analyze_db import AnalyzeDB
        from app.database import get_database_instance
        
        db = get_database_instance()
        analyzer = AnalyzeDB(db)
        
        topic_options = analyzer.get_topic_options(topic)
        categories = topic_options.get('categories', [])
        
        return JSONResponse(
            content={
                "success": True,
                "categories": categories,
                "topic": topic,
                "message": f"Found {len(categories)} categories for topic: {topic}"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving categories for topic {topic}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve categories: {str(e)}"
        )

@router.get("/clusters/{topic}")
async def get_topic_clusters(topic: str):
    """
    Get available clusters for a specific topic.
    
    Args:
        topic: The topic to get clusters for
        
    Returns:
        JSON response with available clusters
    """
    try:
        # TODO: Implement cluster functionality when available
        # For now, return empty list
        clusters = []
        
        return JSONResponse(
            content={
                "success": True,
                "clusters": clusters,
                "topic": topic,
                "message": f"Cluster functionality coming soon for topic: {topic}"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving clusters for topic {topic}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve clusters: {str(e)}"
        )

@router.get("/consensus-types")
async def get_consensus_types():
    """
    Get detailed information about consensus types and their meanings.
    
    Returns:
        JSON response with consensus type explanations
    """
    try:
        service = get_forecast_chart_service()
        
        return JSONResponse(
            content={
                "success": True,
                "consensus_types": service.consensus_types,
                "message": "Consensus type information retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving consensus types: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve consensus types: {str(e)}"
        ) 