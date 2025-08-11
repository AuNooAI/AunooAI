from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import logging
from app.database import Database
from app.security.session import verify_session
from app.tasks import keyword_monitor
from datetime import datetime
from app.database_query_facade import DatabaseQueryFacade

router = APIRouter()
db = Database()
logger = logging.getLogger(__name__)

@router.get("/keyword-monitor/status")
async def get_monitor_status(session: dict = Depends(verify_session)):
    """Get status of the keyword monitor background task"""
    try:
        # Get background task status
        bg_task_status = keyword_monitor.get_task_status()

        # Get current settings
        settings_row = (DatabaseQueryFacade(db, logger)).get_keyword_monitor_is_enabled_and_daily_request_limit()
        settings = {
            "is_enabled": bool(settings_row[0]) if settings_row else True,
            "daily_request_limit": settings_row[1] if settings_row else 100
        }

        # Get current API usage
        api_row = (DatabaseQueryFacade(db, logger)).get_request_count_for_today()
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
            # Get current count for logging
            row = (DatabaseQueryFacade(db, logger)).get_keyword_monitor_is_enabled_and_daily_request_limit()
            current_count = row[0] if row else 0
            
            # Reset the counter
            today = datetime.now().date().isoformat()
            (DatabaseQueryFacade(db, logger)).reset_keyword_monitoring_counter((today,))
            
            logger.info(f"API counter manually reset from {current_count} to 0")
            
            return {
                "success": True,
                "message": f"API counter reset from {current_count} to 0",
                "reset_date": today
            }
    except Exception as e:
        logger.error(f"Error resetting API counter: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 