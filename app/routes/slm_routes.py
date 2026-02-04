"""
SLM (Small Language Model) Routes

API endpoints for testing and using the trained SLM models:
- Hybrid Relevance Service (embedding + classifier + LLM fallback)
- Summarization Service (coming soon)
- Enrichment Service (coming soon)
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config.settings import TRAINING_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slm", tags=["SLM Models"])


# Request/Response Models
class RelevanceRequest(BaseModel):
    topic: str = Field(..., description="The topic to check relevance against")
    title: str = Field(..., description="Article title")
    summary: str = Field(..., description="Article summary or content")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Score threshold for relevance")
    use_llm_fallback: bool = Field(default=True, description="Use LLM for uncertain scores")
    force_llm: bool = Field(default=False, description="Force LLM-only scoring")


class RelevanceResponse(BaseModel):
    topic: str
    relevant: bool
    score: float
    embedding_score: Optional[float]
    classifier_score: Optional[float]
    llm_score: Optional[float]
    method: str
    confidence: str


class BatchRelevanceRequest(BaseModel):
    topic: str = Field(..., description="The topic to check relevance against")
    articles: List[dict] = Field(..., description="List of articles with 'title' and 'summary' keys")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class ServiceStatusResponse(BaseModel):
    embedding_loaded: bool
    classifier_loaded: bool
    embedding_model: Optional[str]
    cached_topics: List[str]
    classifier_weight: float
    embedding_weight: float


# Lazy load the service to avoid startup delays
_hybrid_service = None

def get_service():
    global _hybrid_service
    if _hybrid_service is None:
        from app.services.hybrid_relevance_service import get_hybrid_relevance_service
        _hybrid_service = get_hybrid_relevance_service()
    return _hybrid_service


@router.get("/status", response_model=ServiceStatusResponse)
async def get_slm_status():
    """Get the status of SLM services."""
    try:
        service = get_service()
        return service.get_status()
    except Exception as e:
        logger.error(f"Error getting SLM status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relevance/load")
async def load_models():
    """Load all relevance models (embedding + classifier)."""
    try:
        service = get_service()
        result = service.load_models()
        return {
            "status": "ok",
            "models_loaded": result,
            "service_status": service.get_status()
        }
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relevance/score", response_model=RelevanceResponse)
async def score_relevance(request: RelevanceRequest):
    """
    Score article relevance using the hybrid approach.

    The hybrid system combines:
    1. Embedding similarity (works for any topic, zero-shot)
    2. Fine-tuned classifier (more accurate for trained topics)
    3. LLM fallback (for uncertain scores in 0.3-0.7 range)

    Combined score = 0.6 * classifier + 0.4 * embedding
    """
    try:
        service = get_service()

        # Ensure models are loaded
        if not service.is_available():
            service.load_models()

        result = service.score_relevance(
            topic=request.topic,
            title=request.title,
            summary=request.summary,
            threshold=request.threshold,
            use_llm_fallback=request.use_llm_fallback,
            force_llm=request.force_llm
        )

        return RelevanceResponse(**result)

    except Exception as e:
        logger.error(f"Error scoring relevance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relevance/batch")
async def score_relevance_batch(request: BatchRelevanceRequest):
    """
    Score multiple articles for relevance.

    Each article should have 'title' and 'summary' keys.
    """
    try:
        service = get_service()

        if not service.is_available():
            service.load_models()

        # Add topic to each article
        articles = [
            {"topic": request.topic, **article}
            for article in request.articles
        ]

        results = service.score_batch(articles, threshold=request.threshold)

        return {
            "topic": request.topic,
            "total": len(results),
            "relevant_count": sum(1 for r in results if r["relevant"]),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error in batch scoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relevance/test")
async def test_relevance(
    topic: str = Query(..., description="Topic to test"),
    title: str = Query(..., description="Article title"),
    summary: str = Query(..., description="Article summary"),
):
    """
    Quick test endpoint for relevance scoring (GET method for easy browser testing).

    Example:
    /api/slm/relevance/test?topic=AI&title=OpenAI releases GPT-5&summary=New model announced
    """
    try:
        service = get_service()

        if not service.is_available():
            service.load_models()

        result = service.score_relevance(
            topic=topic,
            title=title,
            summary=summary,
            use_llm_fallback=False  # Skip LLM for quick tests
        )

        return result

    except Exception as e:
        logger.error(f"Error in test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training-topics")
async def get_training_topics():
    """Get list of topics the classifier was trained on."""
    try:
        import pandas as pd
        from pathlib import Path

        data_dir = Path(TRAINING_DIR)
        train_file = data_dir / "relevance_train.json"

        if not train_file.exists():
            return {"topics": [], "message": "Training data not found"}

        df = pd.read_json(train_file)
        topic_counts = df['topic'].value_counts().to_dict()

        return {
            "total_samples": len(df),
            "unique_topics": len(topic_counts),
            "topics": [
                {"topic": topic, "sample_count": count}
                for topic, count in topic_counts.items()
            ]
        }

    except Exception as e:
        logger.error(f"Error getting training topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
