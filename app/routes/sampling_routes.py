"""
API routes for the sampling and filtering framework.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
import logging

from app.services.sampling import (
    get_registry,
    SamplingContext,
    ArticlePipeline
)
from app.services.sampling.pipeline import PipelineBuilder
from app.security.session import verify_session_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sampling", tags=["sampling"])


# Request/Response models
class FilterConfig(BaseModel):
    type: str
    params: Dict[str, Any] = Field(default_factory=dict)


class SamplingConfig(BaseModel):
    type: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PipelineRequest(BaseModel):
    """Request to execute a sampling pipeline."""
    articles: Optional[List[Dict]] = None  # If None, must provide topic to fetch
    topic: Optional[str] = None
    filters: List[FilterConfig] = Field(default_factory=list)
    sampling: Optional[SamplingConfig] = None
    limit: int = 50
    preset: Optional[str] = None  # Use a preset instead of custom config


class PipelineResponse(BaseModel):
    """Response from pipeline execution."""
    articles: List[Dict]
    count: int
    pipeline_name: str
    filters_applied: List[str]
    sampling_strategy: Optional[str]


class StrategyInfo(BaseModel):
    """Information about a registered strategy."""
    name: str
    description: str
    class_name: Optional[str] = Field(None, alias='class')


class PresetInfo(BaseModel):
    """Information about a registered preset."""
    name: str
    description: str
    filters: List[str]
    sampling: str


# Endpoints

@router.get("/strategies", response_model=List[StrategyInfo], dependencies=[Depends(verify_session_api)])
async def list_strategies():
    """List all available sampling strategies."""
    registry = get_registry()
    return registry.list_strategies()


@router.get("/filters", response_model=List[StrategyInfo], dependencies=[Depends(verify_session_api)])
async def list_filters():
    """List all available filter strategies."""
    registry = get_registry()
    return registry.list_filters()


@router.get("/scorers", response_model=List[StrategyInfo], dependencies=[Depends(verify_session_api)])
async def list_scorers():
    """List all available article scorers."""
    registry = get_registry()
    return registry.list_scorers()


@router.get("/presets", response_model=List[PresetInfo], dependencies=[Depends(verify_session_api)])
async def list_presets():
    """List all available pipeline presets."""
    registry = get_registry()
    return registry.list_presets()


@router.get("/presets/{preset_name}", dependencies=[Depends(verify_session_api)])
async def get_preset(preset_name: str):
    """Get details of a specific preset."""
    registry = get_registry()
    preset = registry.get_preset(preset_name)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_name}' not found")
    return preset


@router.post("/execute", response_model=PipelineResponse, dependencies=[Depends(verify_session_api)])
async def execute_pipeline(request: PipelineRequest):
    """
    Execute a sampling pipeline on articles.

    Either provide articles directly, or specify a topic to fetch from database.
    Can use a preset name or custom filter/sampling configuration.
    """
    registry = get_registry()

    # Build or get pipeline
    if request.preset:
        pipeline = registry.create_pipeline_from_preset(request.preset)
        if not pipeline:
            raise HTTPException(status_code=404, detail=f"Preset '{request.preset}' not found")
    else:
        # Build custom pipeline
        config = {
            'name': 'api_custom',
            'filters': [f.model_dump() for f in request.filters],
            'sampling': request.sampling.model_dump() if request.sampling else None
        }
        pipeline = registry.create_pipeline(config)

    # Get articles
    articles = request.articles
    if articles is None:
        if request.topic is None:
            raise HTTPException(
                status_code=400,
                detail="Must provide either articles or topic"
            )
        # Fetch from database
        articles = await _fetch_articles_for_topic(request.topic, request.limit * 2)

    # Create context
    context = SamplingContext(
        topic=request.topic if request.topic != '__all__' else None
    )

    # Execute pipeline
    result = pipeline.execute(articles, request.limit, context)

    return PipelineResponse(
        articles=result,
        count=len(result),
        pipeline_name=pipeline.name,
        filters_applied=[f.name for f in pipeline.filters],
        sampling_strategy=pipeline.sampler.name if pipeline.sampler else None
    )


@router.post("/sample", dependencies=[Depends(verify_session_api)])
async def quick_sample(
    topic: Optional[str] = Query(None, description="Topic to fetch articles for"),
    strategy: str = Query("recency_diversity", description="Sampling strategy name"),
    limit: int = Query(50, ge=1, le=500, description="Maximum articles to return"),
    days_back: Optional[int] = Query(None, ge=1, le=365, description="Filter to articles from last N days")
):
    """
    Quick sampling endpoint with minimal configuration.
    Fetches articles from database and applies a sampling strategy.
    """
    registry = get_registry()

    # Get strategy
    strategy_class = registry.get_strategy(strategy)
    if not strategy_class:
        # Try preset
        pipeline = registry.create_pipeline_from_preset(strategy)
        if not pipeline:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy or preset: {strategy}"
            )
    else:
        pipeline = ArticlePipeline(
            filters=[],
            sampler=strategy_class(),
            name=f"quick_{strategy}"
        )

    # Add date filter if specified
    if days_back:
        from app.services.sampling.filters import DateRangeFilter
        pipeline.filters.insert(0, DateRangeFilter(days_back=days_back))

    # Fetch articles
    articles = await _fetch_articles_for_topic(topic, limit * 3)

    # Create context
    context = SamplingContext(
        topic=topic if topic and topic != '__all__' else None
    )

    # Execute
    result = pipeline.execute(articles, limit, context)

    return {
        'articles': result,
        'count': len(result),
        'strategy': strategy,
        'topic': topic
    }


@router.get("/default-for-topic", dependencies=[Depends(verify_session_api)])
async def get_default_for_topic(
    topic: Optional[str] = Query(None, description="Topic name (None or __all__ for cross-topic)")
):
    """Get the recommended default pipeline for a topic."""
    registry = get_registry()

    if topic is None or topic == '__all__':
        preset_name = 'all_topics_default'
    else:
        preset_name = 'quality_first'

    preset = registry.get_preset(preset_name)

    return {
        'topic': topic,
        'recommended_preset': preset_name,
        'preset_config': preset
    }


async def _fetch_articles_for_topic(topic: Optional[str], limit: int) -> List[Dict]:
    """
    Fetch articles from database for a topic.

    Args:
        topic: Topic name (None or __all__ for all topics)
        limit: Maximum articles to fetch

    Returns:
        List of article dictionaries
    """
    from app.database_query_facade import DatabaseQueryFacade

    try:
        db = DatabaseQueryFacade()

        # Handle cross-topic mode
        topic_for_query = None if (topic is None or topic == '__all__') else topic

        # Fetch recent articles
        articles = db.get_recent_articles_by_topic(
            topic_name=topic_for_query,
            limit=limit
        )

        # Convert to dict format if needed
        result = []
        for article in articles:
            if isinstance(article, dict):
                result.append(article)
            else:
                # Assume it's a row/tuple-like object
                result.append(dict(article) if hasattr(article, 'keys') else article._asdict())

        return result

    except Exception as e:
        logger.error(f"Error fetching articles for topic '{topic}': {e}")
        return []
