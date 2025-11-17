from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
from app.security.session import verify_session
from datetime import datetime, timezone
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
        # Convert input value to timezone-aware datetime
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                # Handle other date string formats if needed
                try:
                    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Try parsing as date only
                    dt = datetime.strptime(value, '%Y-%m-%d')
                    dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Handle datetime objects - make them timezone-aware if they aren't
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Get current time in UTC (timezone-aware)
        now = datetime.now(timezone.utc)

        # Both are now timezone-aware, safe to subtract
        diff = now - dt
        
        # Handle future dates
        if diff.total_seconds() < 0:
            seconds = abs(int(diff.total_seconds()))
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
        seconds = int(diff.total_seconds())
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
        try:
            db.facade.test_data_select()
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
                result = db.facade.get_rate_limit_status()
                if result:
                    requests_today = result['requests_today'] or 0
                    last_error = result['last_error']

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

        # Collect statistics
        stats = {
            'total_articles': await db.get_total_articles(),
            'articles_today': await db.get_articles_today(),
            'keyword_groups': await db.get_keyword_group_count(),
            'topics': await db.get_topic_count()
        }

        # Get topic statistics
        active_topics = [
            {
                "name": row['topic'],
                "article_count": row['article_count'],
                "last_article_date": row['last_article_date']
            }
            for row in db.facade.get_topic_statistics()
        ]

        # Get last check time with proper timezone format
        try:
            last_check_time = db.facade.get_last_check_time_using_timezone_format()
        except Exception as e:
            logger.error(f"Error getting last check time: {str(e)}")
            last_check_time = None

        # Serve the Bootstrap Operations HQ dashboard (Community edition)
        # React version available at /trend-convergence for Enterprise
        return templates.TemplateResponse("index.html", {
            "request": request,
            "stats": stats,
            "session": session,
            "last_check_time": last_check_time,
            "db_status": db_status,
            "api_status": api_status,
            "active_topics": active_topics,
            "current_page": "home"  # Highlights "Operations HQ" in left sidebar
        })
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 