from fastapi import APIRouter, Query, Depends, HTTPException
from app.database import get_database_instance, Database
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/enriched_articles")
async def get_enriched_articles(
    limit: int = Query(10, description="Maximum number of articles to return"),
    db: Database = Depends(get_database_instance)
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
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Query for articles that have a non-null and non-empty category
            query = """
                SELECT *
                FROM articles
                WHERE category IS NOT NULL AND category != ''
                ORDER BY submission_date DESC
                LIMIT ?
            """
            
            cursor.execute(query, (limit,))
            articles = []
            
            for row in cursor.fetchall():
                # Convert row to dictionary
                article_dict = {}
                for idx, col in enumerate(cursor.description):
                    article_dict[col[0]] = row[idx]
                
                # Process tags
                if article_dict.get('tags'):
                    article_dict['tags'] = article_dict['tags'].split(',')
                else:
                    article_dict['tags'] = []
                
                articles.append(article_dict)
            
            return articles
    except Exception as e:
        logger.error(f"Error fetching enriched articles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error: {str(e)}"
        ) 