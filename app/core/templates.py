"""Custom template configuration for the application."""

import logging
from datetime import datetime, timezone
from fastapi.templating import Jinja2Templates
from app.utils.app_info import get_app_info

logger = logging.getLogger(__name__)


class AppInfoJinja2Templates(Jinja2Templates):
    """Custom Jinja2Templates class that always includes app_info and session."""
    
    def TemplateResponse(self, name, context, *args, **kwargs):
        # Always get fresh app info for every template response
        app_info = get_app_info()
        
        # Ensure session is always available in templates
        if "session" not in context:
            context["session"] = context["request"].session if hasattr(context["request"], "session") else {}
            
        # Add app_info to context
        context["app_info"] = app_info
        
        return super().TemplateResponse(name, context, *args, **kwargs)


def datetime_filter(value):
    """Template filter for formatting datetime values."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    return value.strftime('%Y-%m-%d %H:%M:%S')


def timeago_filter(value):
    """Template filter for showing relative time (timeago)."""
    if not value:
        return ""
    try:
        now = datetime.now(timezone.utc)
        
        # Convert input value to timezone-aware datetime
        if isinstance(value, str):
            try:
                # Try parsing as ISO format with timezone
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                try:
                    # Try parsing as simple datetime
                    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                    dt = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    # Try parsing as date only
                    dt = datetime.strptime(value, '%Y-%m-%d')
                    dt = dt.replace(tzinfo=timezone.utc)
        else:
            # If it's already a datetime object
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        
        # Ensure both datetimes are timezone-aware
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        
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


def setup_templates():
    """Setup Jinja2 templates with custom class and filters."""
    templates = AppInfoJinja2Templates(directory="templates")
    
    # Register custom filters
    templates.env.filters["datetime"] = datetime_filter
    templates.env.filters["timeago"] = timeago_filter
    
    return templates