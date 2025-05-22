from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging
from app.database import Database
from app.security.session import verify_session
from app.tasks import keyword_monitor
from datetime import datetime

router = APIRouter()
db = Database()
logger = logging.getLogger(__name__)

@router.get("/keyword-monitor/status")
async def get_monitor_status(session: dict = Depends(verify_session)):
    """Get status of the keyword monitor background task"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get background task status
            bg_task_status = keyword_monitor.get_task_status()
            
            # Get current settings
            cursor.execute("""
                SELECT is_enabled, daily_request_limit
                FROM keyword_monitor_settings WHERE id = 1
            """)
            settings_row = cursor.fetchone()
            settings = {
                "is_enabled": bool(settings_row[0]) if settings_row else True,
                "daily_request_limit": settings_row[1] if settings_row else 100
            }
            
            # Get current API usage
            cursor.execute("""
                SELECT requests_today, last_reset_date
                FROM keyword_monitor_status WHERE id = 1
            """)
            api_row = cursor.fetchone()
            api_usage = {
                "requests_today": api_row[0] if api_row else 0,
                "limit": settings["daily_request_limit"],
                "last_reset": api_row[1] if api_row else None
            }
            
            return {
                "background_task": bg_task_status,
                "settings": settings,
                "api_usage": api_usage
            }
    except Exception as e:
        logger.error(f"Error getting monitor status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/keyword-monitor/reset-api-counter")
async def reset_api_counter(session: dict = Depends(verify_session)):
    """Manually reset the API usage counter"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current count for logging
            cursor.execute("SELECT requests_today FROM keyword_monitor_status WHERE id = 1")
            row = cursor.fetchone()
            current_count = row[0] if row else 0
            
            # Reset the counter
            today = datetime.now().date().isoformat()
            cursor.execute("""
                UPDATE keyword_monitor_status 
                SET requests_today = 0,
                    last_reset_date = ?
                WHERE id = 1
            """, (today,))
            conn.commit()
            
            logger.info(f"API counter manually reset from {current_count} to 0")
            
            return {
                "success": True,
                "message": f"API counter reset from {current_count} to 0",
                "reset_date": today
            }
    except Exception as e:
        logger.error(f"Error resetting API counter: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 