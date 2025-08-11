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
    return (DatabaseQueryFacade(db, logger)).get_is_keyword_monitor_enabled()

def get_last_check_time() -> Optional[datetime]:
    return (DatabaseQueryFacade(db, logger)).get_keyword_monitor_last_check_time()

def get_unread_alerts() -> List[Dict]:
    alerts_data = (DatabaseQueryFacade(db, logger)).get_unread_alerts()
    return [
        {
            'id': row[0],
            'group_id': row[1],
            'detected_at': row[2],
            'matched_keyword': row[3],
            'article': {
                'uri': row[4],
                'title': row[5],
                'url': row[6],
                'source': row[7],
                'publication_date': row[8],
                'summary': row[9],
                'category': row[10],
                'sentiment': row[11],
                'driver_type': row[12],
                'time_to_impact': row[13],
                'future_signal': row[14],
                'bias': row[15],
                'factual_reporting': row[16],
                'mbfc_credibility_rating': row[17],
                'bias_country': row[18],
                'press_freedom': row[19],
                'media_type': row[20],
                'popularity': row[21]
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
            (DatabaseQueryFacade(db, logger)).delete_keyword_alerts_by_article_url(uri)

            # Check if keyword_article_matches table exists and delete from there too
            if (DatabaseQueryFacade(db, logger)).check_if_keyword_article_matches_table_exists():
                (DatabaseQueryFacade(db, logger)).delete_keyword_alerts_by_article_url_from_new_table(uri)

            # Then delete the article
            if (DatabaseQueryFacade(db, logger)).delete_article_by_url(uri) > 0:
                deleted_count += 1

            # Return both the deleted articles count and affected alerts count
            return {
                "status": "success", 
                "deleted_count": deleted_count,
            }
    except Exception as e:
        logger.error(f"Error in bulk_delete_articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 