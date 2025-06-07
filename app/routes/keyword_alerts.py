from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Optional
from datetime import datetime
import logging

from pydantic import BaseModel
from app.database import Database, get_database_instance
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
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            monitor_enabled = get_monitor_settings(cursor)
            last_check_time = get_last_check_time(cursor) 
            alerts = get_unread_alerts(cursor)
            
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

def get_monitor_settings(cursor) -> bool:
    cursor.execute("SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1")
    settings = cursor.fetchone()
    return bool(settings[0]) if settings else False

def get_last_check_time(cursor) -> Optional[datetime]:
    cursor.execute("SELECT MAX(check_time) FROM keyword_monitor_checks")
    last_check = cursor.fetchone()[0]
    return last_check if last_check else None

def get_unread_alerts(cursor) -> List[Dict]:
    cursor.execute("""
        SELECT 
            ka.id,
            ka.group_id,
            ka.detected_at,
            ka.matched_keyword,
            a.uri,
            a.title,
            a.url,
            a.source,
            a.publication_date,
            a.summary,
            a.category,
            a.sentiment,
            a.driver_type,
            a.time_to_impact,
            a.future_signal,
            a.bias,
            a.factual_reporting,
            a.mbfc_credibility_rating,
            a.bias_country,
            a.press_freedom,
            a.media_type,
            a.popularity
        FROM keyword_alerts ka
        JOIN articles a ON ka.article_uri = a.uri
        WHERE ka.read = 0
        ORDER BY ka.detected_at DESC
    """)
    
    alerts_data = cursor.fetchall()
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
        with db.get_connection() as conn:
            cursor = conn.cursor()
            deleted_count = 0
            
            for uri in request.uris:
                # First delete related keyword alerts
                cursor.execute("DELETE FROM keyword_alerts WHERE article_uri = ?", (uri,))
                
                # Check if keyword_article_matches table exists and delete from there too
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='keyword_article_matches'
                """)
                if cursor.fetchone():
                    cursor.execute("DELETE FROM keyword_article_matches WHERE article_uri = ?", (uri,))
                
                # Then delete the article
                cursor.execute("DELETE FROM articles WHERE uri = ?", (uri,))
                if cursor.rowcount > 0:
                    deleted_count += 1
            
            conn.commit()
            
            # Return both the deleted articles count and affected alerts count
            return {
                "status": "success", 
                "deleted_count": deleted_count,
            }
    except Exception as e:
        logger.error(f"Error in bulk_delete_articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 