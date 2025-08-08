from fastapi import APIRouter, Query, Depends, HTTPException
from app.database import get_database_instance, Database
from app.database_query_facade import DatabaseQueryFacade

from app.security.session import verify_session
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/enriched_articles")
async def get_enriched_articles(
    limit: int = Query(10, description="Maximum number of articles to return"),
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)
):
    """
    Get the most recently enriched articles (articles that have a category)
    
    Args:
        limit: Maximum number of articles to return
        db: Database instance
        
    Returns:
        List of enriched articles
    """
    try:
        return (DatabaseQueryFacade(db, logger)).enriched_articles(limit)
    except Exception as e:
        logger.error(f"Error fetching enriched articles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        ) 