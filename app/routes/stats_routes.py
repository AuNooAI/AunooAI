from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database, get_database_instance
from app.security.session import verify_session
from datetime import datetime
import logging
import os

# Set up logger
logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Add custom filters
def timeago_filter(value):
    if not value:
        return ""
    try:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            dt = value
            
        now = datetime.now()
        diff = dt - now
        
        # Handle future dates
        if diff.total_seconds() > 0:
            seconds = int(diff.total_seconds())
            if seconds < 60:
                return f"in {seconds} seconds"
            minutes = seconds // 60
            if minutes < 60:
                return f"in {minutes} minute{'s' if minutes != 1 else ''}"
            hours = minutes // 60
            if hours < 24:
                return f"in {hours} hour{'s' if hours != 1 else ''}"
            days = hours // 24
            return f"in {days} day{'s' if days != 1 else ''}"
        
        # Handle past dates
        seconds = int(abs(diff.total_seconds()))
        if seconds < 60:
            return f"{seconds} seconds ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        return f"{days} day{'s' if days != 1 else ''} ago"
    except Exception as e:
        logger.error(f"Error in timeago filter: {str(e)}")
        return str(value)

# Register the filter
templates.env.filters["timeago"] = timeago_filter

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request, 
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    try:
        # Test database connection
        db_status = {"status": "error", "message": "Disconnected"}
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")  # Simple test query
                db_status = {"status": "success", "message": "Connected"}
        except Exception as e:
            logger.error(f"Database connection error: {str(e)}")
            db_status = {"status": "error", "message": str(e)}

        # Test API status by checking the providers
        api_status = {"status": "error", "message": "Unavailable"}
        try:
            # Check if any provider is configured
            providers_configured = False
            for provider_key in ['PROVIDER_NEWSAPI_KEY', 'PROVIDER_THENEWSAPI_KEY', 'PROVIDER_FIRECRAWL_KEY']:
                if os.getenv(provider_key):
                    providers_configured = True
                    break

            if not providers_configured:
                api_status = {"status": "warning", "message": "Not Configured"}
            else:
                # Get current API usage
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT requests_today, last_error
                        FROM keyword_monitor_status 
                        WHERE id = 1
                    """)
                    result = cursor.fetchone()
                    if result:
                        requests_today = result[0] or 0
                        last_error = result[1]
                        
                        # Default daily limit (can be made configurable)
                        daily_limit = 100
                        
                        if last_error and ("Rate limit exceeded" in last_error or "limit reached" in last_error):
                            api_status = {"status": "warning", "message": "Rate Limited"}
                        elif requests_today >= daily_limit:
                            api_status = {"status": "warning", "message": "Near Limit"}
                        else:
                            api_status = {"status": "success", "message": "Operational"}
                    else:
                        api_status = {"status": "success", "message": "Operational"}

        except Exception as e:
            logger.error(f"API status check error: {str(e)}")
            api_status = {"status": "error", "message": str(e)}

        # Get last check time
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT last_check_time FROM keyword_monitor_status WHERE id = 1")
                result = cursor.fetchone()
                last_check_time = result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting last check time: {str(e)}")
            last_check_time = None

        # Collect statistics
        stats = {
            'total_articles': await db.get_total_articles(),
            'articles_today': await db.get_articles_today(),
            'keyword_groups': await db.get_keyword_group_count(),
            'topics': await db.get_topic_count()
        }

        # Get topic statistics
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    topic,
                    COUNT(*) as article_count,
                    MAX(submission_date) as last_article_date
                FROM articles 
                WHERE topic IS NOT NULL AND topic != ''
                GROUP BY topic 
                ORDER BY last_article_date DESC
            """)
            active_topics = [
                {
                    "name": row[0],
                    "article_count": row[1],
                    "last_article_date": row[2]
                }
                for row in cursor.fetchall()
            ]

        return templates.TemplateResponse("index.html", {
            "request": request,
            "stats": stats,
            "session": session,
            "last_check_time": last_check_time,
            "db_status": db_status,
            "api_status": api_status,
            "active_topics": active_topics
        })
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 