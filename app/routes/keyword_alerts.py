from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Optional
from datetime import datetime
import logging

from pydantic import BaseModel
from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.security.session import verify_session, verify_session_api, verify_session_api

router = APIRouter()
db = Database()
logger = logging.getLogger(__name__)

# Set up templates
templates = Jinja2Templates(directory="templates")

@router.get("/keyword-alerts-old", response_class=HTMLResponse)
async def keyword_alerts_page_old(
    request: Request, 
    session: Dict = Depends(verify_session)
) -> HTMLResponse:
    """Legacy route - replaced by keyword_monitor.py implementation"""
    try:
        monitor_enabled = get_monitor_settings()
        last_check_time = get_last_check_time()
        alerts = get_unread_alerts()

        return templates.TemplateResponse(
            "keyword_alerts.html",
            {
                "request": request,
                "session": session,
                "alerts": alerts,
                "last_check_time": last_check_time,
                "settings": {"is_enabled": monitor_enabled}
            }
        )

    except Exception as e:
        logger.error(f"Error loading keyword alerts page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def get_monitor_settings() -> bool:
    return db.facade.get_is_keyword_monitor_enabled()

def get_last_check_time() -> Optional[datetime]:
    return db.facade.get_keyword_monitor_last_check_time()

def get_unread_alerts() -> List[Dict]:
    alerts_data = db.facade.get_unread_alerts()
    return [
        {
            'id': row['id'],
            'group_id': row['group_id'],
            'detected_at': row['detected_at'],
            'matched_keyword': row['matched_keyword'],
            'article': {
                'uri': row['uri'],
                'title': row['title'],
                'url': row['url'],
                'source': row['source'],
                'publication_date': row['publication_date'],
                'summary': row['summary'],
                'category': row['category'],
                'sentiment': row['sentiment'],
                'driver_type': row['driver_type'],
                'time_to_impact': row['time_to_impact'],
                'future_signal': row['future_signal'],
                'bias': row['bias'],
                'factual_reporting': row['factual_reporting'],
                'mbfc_credibility_rating': row['mbfc_credibility_rating'],
                'bias_country': row['bias_country'],
                'press_freedom': row['press_freedom'],
                'media_type': row['media_type'],
                'popularity': row['popularity']
            }
        }
        for row in alerts_data
    ] 

class DeleteArticlesRequest(BaseModel):
    uris: List[str]

@router.delete("/bulk_delete_articles")
async def bulk_delete_articles(
    request: DeleteArticlesRequest,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session_api)
):
    try:
        deleted_count = 0

        for uri in request.uris:
            # First delete related keyword alerts
            db.facade.delete_keyword_alerts_by_article_url(uri)

            # Check if keyword_article_matches table exists and delete from there too
            if db.facade.check_if_keyword_article_matches_table_exists():
                db.facade.delete_keyword_alerts_by_article_url_from_new_table(uri)

            # Then delete the article
            if db.facade.delete_article_by_url(uri) > 0:
                deleted_count += 1

        # Return both the deleted articles count and affected alerts count
        return {
            "status": "success",
            "deleted_count": deleted_count,
        }
    except Exception as e:
        logger.error(f"Error in bulk_delete_articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 