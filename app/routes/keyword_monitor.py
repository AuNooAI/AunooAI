from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_database_instance
from app.tasks.keyword_monitor import KeywordMonitor
import logging
import json
import traceback
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Set up logger
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keyword-monitor")

class KeywordGroup(BaseModel):
    name: str
    topic: str

class Keyword(BaseModel):
    group_id: int
    keyword: str

class KeywordMonitorSettings(BaseModel):
    check_interval: int
    interval_unit: int
    search_fields: str
    language: str
    sort_by: str
    page_size: int
    daily_request_limit: int = 100

class PollingToggle(BaseModel):
    enabled: bool

@router.post("/groups")
async def create_group(group: KeywordGroup, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                (group.name, group.topic)
            )
            conn.commit()
            return {"id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/keywords")
async def add_keyword(keyword: Keyword, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO monitored_keywords (group_id, keyword) VALUES (?, ?)",
                (keyword.group_id, keyword.keyword)
            )
            conn.commit()
            return {"id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/keywords/{keyword_id}")
async def delete_keyword(keyword_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_keywords WHERE id = ?", (keyword_id,))
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM keyword_groups WHERE id = ?", (group_id,))
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE keyword_alerts SET is_read = 1 WHERE id = ?",
                (alert_id,)
            )
            conn.commit()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/check-now")
async def check_keywords_now(db=Depends(get_database_instance)):
    """Manually trigger a keyword check"""
    try:
        monitor = KeywordMonitor(db)
        await monitor.check_keywords()
        return {"success": True, "message": "Keyword check completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
async def get_alerts(db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get the last check time and error
            cursor.execute("""
                SELECT last_check_time, last_error
                FROM keyword_monitor_status
                WHERE id = 1
            """)
            status = cursor.fetchone()
            last_check_time = status[0] if status else None
            last_error = status[1] if status and len(status) > 1 else None
            
            # Get all unread alerts with article and keyword info
            cursor.execute("""
                SELECT 
                    ka.id as alert_id,
                    ka.detected_at,
                    mk.keyword,
                    kg.id as group_id,
                    kg.name as group_name,
                    kg.topic,
                    a.uri,
                    a.title,
                    a.news_source,
                    a.publication_date,
                    a.summary
                FROM keyword_alerts ka
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                JOIN keyword_groups kg ON mk.group_id = kg.id
                JOIN articles a ON ka.article_uri = a.uri
                WHERE ka.is_read = 0
                ORDER BY ka.detected_at DESC
            """)
            
            alerts = cursor.fetchall()
            
            # Group alerts by keyword group
            groups = {}
            for alert in alerts:
                group_id = alert[3]  # group_id from the query
                if group_id not in groups:
                    groups[group_id] = {
                        'id': group_id,
                        'name': alert[4],  # group_name
                        'topic': alert[5],  # topic
                        'alerts': []
                    }
                
                groups[group_id]['alerts'].append({
                    'id': alert[0],  # alert_id
                    'detected_at': alert[1],
                    'keyword': alert[2],
                    'article': {
                        'url': alert[6],  # uri
                        'title': alert[7],
                        'source': alert[8],
                        'publication_date': alert[9],
                        'summary': alert[10]
                    }
                })
            
            return templates.TemplateResponse(
                "keyword_alerts.html",
                {
                    "request": request,
                    "groups": groups,
                    "last_check_time": last_check_time,
                    "last_error": last_error,
                    "session": session
                }
            )
            
    except Exception as e:
        logger.error(f"Error fetching keyword alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/settings")
async def get_settings(db=Depends(get_database_instance)):
    """Get keyword monitor settings"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current settings
            cursor.execute("""
                SELECT 
                    check_interval,
                    interval_unit,
                    search_fields,
                    language,
                    sort_by,
                    page_size,
                    is_enabled,
                    daily_request_limit
                FROM keyword_monitor_settings 
                WHERE id = 1
            """)
            settings = cursor.fetchone()
            
            # Count total keywords for recommendation
            cursor.execute("SELECT COUNT(*) FROM monitored_keywords")
            total_keywords = cursor.fetchone()[0]
            
            return {
                "check_interval": settings[0] if settings else 15,
                "interval_unit": settings[1] if settings else 60,
                "search_fields": settings[2] if settings else "title,description,content",
                "language": settings[3] if settings else "en",
                "sort_by": settings[4] if settings else "publishedAt",
                "page_size": settings[5] if settings else 10,
                "is_enabled": settings[6] if settings else True,
                "daily_request_limit": settings[7] if settings else 100,
                "total_keywords": total_keywords
            }
            
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/settings")
async def save_settings(settings: KeywordMonitorSettings, db=Depends(get_database_instance)):
    """Save keyword monitor settings"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_monitor_settings (
                    id INTEGER PRIMARY KEY,
                    check_interval INTEGER NOT NULL,
                    interval_unit INTEGER NOT NULL,
                    search_fields TEXT NOT NULL,
                    language TEXT NOT NULL,
                    sort_by TEXT NOT NULL,
                    page_size INTEGER NOT NULL,
                    daily_request_limit INTEGER NOT NULL
                )
            """)
            
            # Update or insert settings
            cursor.execute("""
                INSERT OR REPLACE INTO keyword_monitor_settings (
                    id, check_interval, interval_unit, search_fields,
                    language, sort_by, page_size, daily_request_limit
                ) VALUES (
                    1, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                settings.check_interval,
                settings.interval_unit,
                settings.search_fields,
                settings.language,
                settings.sort_by,
                settings.page_size,
                settings.daily_request_limit
            ))
            
            conn.commit()
            return {"success": True}
            
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trends")
async def get_trends(db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, get all groups with their unread alerts count
            cursor.execute("""
                SELECT 
                    kg.id,
                    kg.name,
                    kg.topic,
                    COUNT(DISTINCT ka.id) as unread_count,
                    MAX(ka.detected_at) as latest_alert
                FROM keyword_groups kg
                LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id AND ka.is_read = 0
                GROUP BY kg.id, kg.name, kg.topic
            """)
            
            results = cursor.fetchall()
            logger.debug(f"Initial query results: {results}")
            
            trends = {}
            for row in results:
                group_id, name, topic, unread_count, latest_alert = row
                
                growth_status = 'No Data'
                if unread_count > 0:
                    growth_status = 'NEW'
                    
                trends[name] = {
                    'id': group_id,
                    'name': name,
                    'topic': topic,
                    'counts': [1] if unread_count > 0 else [],  # Single point for new alerts
                    'unread_alerts': unread_count,
                    'growth_status': growth_status
                }
            
            logger.debug(f"Final trends data: {json.dumps(trends, indent=2, default=str)}")
            return trends
            
    except Exception as e:
        logger.error(f"Error getting trends: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/toggle-polling")
async def toggle_polling(toggle: PollingToggle, db=Depends(get_database_instance)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First check if settings exist
            cursor.execute("SELECT 1 FROM keyword_monitor_settings WHERE id = 1")
            exists = cursor.fetchone() is not None
            
            if exists:
                # Just update is_enabled if settings exist
                cursor.execute("""
                    UPDATE keyword_monitor_settings 
                    SET is_enabled = ?
                    WHERE id = 1
                """, (toggle.enabled,))
            else:
                # Insert with defaults if no settings exist
                cursor.execute("""
                    INSERT INTO keyword_monitor_settings (
                        id,
                        check_interval,
                        interval_unit,
                        search_fields,
                        language,
                        sort_by,
                        page_size,
                        is_enabled
                    ) VALUES (
                        1,
                        15,
                        60,
                        'title,description,content',
                        'en',
                        'publishedAt',
                        10,
                        ?
                    )
                """, (toggle.enabled,))
            
            conn.commit()
            return {"status": "success", "enabled": toggle.enabled}
            
    except Exception as e:
        logger.error(f"Error toggling polling: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 