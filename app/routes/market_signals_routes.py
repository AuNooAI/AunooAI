"""
Market Signals & Strategic Risks API Routes

Provides analysis endpoints for identifying market signals, risks,
opportunities, and timeline scenarios.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
import logging

from app.database import get_database_instance, Database
from app.security.session import verify_session
from app.services.auspex_service import get_auspex_service
from app.services.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-signals", tags=["Market Signals"])


@router.get("/analysis")
async def get_market_signals_analysis(
    topic: str = Query(..., description="Topic to analyze"),
    model: str = Query(..., description="AI model to use for analysis"),
    limit: int = Query(100, ge=10, le=500, description="Number of articles to analyze"),
    temperature: Optional[float] = Query(None, ge=0.0, le=2.0, description="Model temperature"),
    max_tokens: Optional[int] = Query(None, ge=100, le=10000, description="Maximum tokens"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Generate market signals and strategic risks analysis.

    Args:
        topic: Research topic name
        limit: Number of recent articles to analyze
        session: User session (authenticated)
        db: Database instance

    Returns:
        JSON with future_signals, risk_cards, opportunity_cards, and quotes
    """

    try:
        logger.info(f"Generating market signals analysis for topic: {topic}")

        # 1. Load prompt from data/prompts/market_signals/current.json
        prompt_data = PromptLoader.load_prompt("market_signals", "current")
        logger.info(f"Loaded prompt version: {prompt_data.get('version')}")

        # 2. Fetch recent articles for topic
        articles = db.facade.get_articles_by_topic(topic, limit=limit)

        if not articles:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No articles found for topic: {topic}"
            )

        logger.info(f"Fetched {len(articles)} articles for analysis")

        # 3. Prepare variables for prompt template
        variables = {
            "topic": topic,
            "article_count": len(articles),
            "date_range": "Last 30 days"
        }

        # 4. Fill prompt template
        system_prompt, user_prompt = PromptLoader.get_prompt_template(
            prompt_data,
            variables
        )

        # Add articles to user prompt
        articles_text = "\n\n".join([
            f"Title: {a.get('title', 'N/A')}\n"
            f"Publication: {a.get('news_source', 'N/A')}\n"
            f"Publication Date: {a.get('publication_date', 'N/A')}\n"
            f"URL: {a.get('uri', 'N/A')}\n"
            f"Summary: {a.get('summary', 'N/A')}\n"
            f"Sentiment: {a.get('sentiment', 'N/A')}\n"
            f"Category: {a.get('category', 'N/A')}\n"
            f"Future Signal: {a.get('future_signal', 'N/A')}"
            for a in articles[:50]  # Limit for token budget
        ])

        user_prompt = user_prompt.replace("{articles}", articles_text)

        # 5. Call Auspex service
        logger.info(f"Calling AuspexService for analysis with model: {model}")
        auspex = get_auspex_service()

        # Use config parameters from request, with prompt metadata as fallback defaults
        final_temperature = temperature if temperature is not None else prompt_data.get("metadata", {}).get("temperature", 0.7)
        final_max_tokens = max_tokens if max_tokens is not None else prompt_data.get("metadata", {}).get("max_tokens", 3000)

        analysis_json = await auspex.generate_structured_analysis(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,  # Use model from config modal, not prompt metadata
            temperature=final_temperature,
            max_tokens=final_max_tokens
        )

        # 6. Parse and validate response
        try:
            market_signals_data = json.loads(analysis_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"Response: {analysis_json[:500]}...")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI returned invalid JSON response"
            )

        # 7. Validate required fields
        required_fields = ["future_signals", "risk_cards", "opportunity_cards", "quotes"]
        for field in required_fields:
            if field not in market_signals_data:
                logger.warning(f"Missing required field: {field}")
                market_signals_data[field] = []

        # 8. Add metadata
        market_signals_data["meta"] = {
            "topic": topic,
            "article_count": len(articles),
            "analyzed_count": min(len(articles), 50),
            "prompt_version": prompt_data.get("version", "unknown"),
            "generated_at": datetime.utcnow().isoformat(),
            "model": model,  # Actual model used from config
            "temperature": final_temperature,
            "max_tokens": final_max_tokens
        }

        logger.info(f"Successfully generated market signals analysis with {len(market_signals_data.get('future_signals', []))} signals")

        return market_signals_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market signals analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@router.get("/topics")
async def get_available_topics(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get list of topics available for analysis.

    Returns:
        List of topic names
    """
    try:
        topics = db.facade.get_all_topics()
        topic_names = [t.get("name") for t in topics if t.get("name")]

        return {
            "success": True,
            "topics": topic_names,
            "count": len(topic_names)
        }
    except Exception as e:
        logger.error(f"Failed to get topics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve topics: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint for market signals service.

    Returns:
        Service health status
    """
    try:
        # Check if prompt exists
        prompt = PromptLoader.load_prompt("market_signals", "current")

        return {
            "status": "healthy",
            "service": "market_signals",
            "prompt_version": prompt.get("version"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "market_signals",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
