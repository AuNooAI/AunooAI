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


def clean_publication_date(date_str):
    """Clean publication date by extracting only the date portion"""
    if not date_str:
        return ""
    
    import re
    
    # If it's already a clean date format, return as is
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
        return date_str.strip()
    
    # Extract ISO date format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?', date_str)
    if iso_match:
        return iso_match.group(1)
    
    # Extract DD/MM/YYYY format
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_str)
    if date_match:
        # Convert DD/MM/YYYY to YYYY-MM-DD
        date_parts = date_match.group(1).split('/')
        if len(date_parts) == 3:
            day, month, year = date_parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # Extract MM-DD-YYYY or MM/DD/YYYY format
    us_date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})', date_str)
    if us_date_match:
        date_parts = re.split(r'[-/]', us_date_match.group(1))
        if len(date_parts) == 3:
            month, day, year = date_parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # If we can't parse it cleanly, return empty string
    return ""

def build_analysis_url_filter(article, topic):
    """Template filter for building analysis URLs with metadata preservation"""
    from urllib.parse import urlencode
    
    # Handle both dictionary and object formats
    if isinstance(article, dict):
        params = {
            'url': article.get('url', '') or article.get('uri', ''),
            'topic': topic
        }
        
        # Add metadata if available
        if article.get('title'):
            params['title'] = article['title']
        if article.get('source'):
            params['source'] = article['source']
        if article.get('publication_date'):
            params['publication_date'] = clean_publication_date(article['publication_date'])
        if article.get('summary'):
            params['summary'] = article['summary']
            
        # Add media bias data if available
        if article.get('bias'):
            params['bias'] = article['bias']
        if article.get('factual_reporting'):
            params['factual_reporting'] = article['factual_reporting']
        if article.get('mbfc_credibility_rating'):
            params['mbfc_credibility_rating'] = article['mbfc_credibility_rating']
        if article.get('bias_country'):
            params['bias_country'] = article['bias_country']
        if article.get('media_type'):
            params['media_type'] = article['media_type']
        if article.get('popularity'):
            params['popularity'] = article['popularity']
    else:
        # Handle object format
        params = {
            'url': getattr(article, 'url', '') or getattr(article, 'uri', ''),
            'topic': topic
        }
        
        # Add metadata if available
        if hasattr(article, 'title') and article.title:
            params['title'] = article.title
        if hasattr(article, 'source') and article.source:
            params['source'] = article.source
        if hasattr(article, 'publication_date') and article.publication_date:
            params['publication_date'] = clean_publication_date(article.publication_date)
        if hasattr(article, 'summary') and article.summary:
            params['summary'] = article.summary
            
        # Add media bias data if available
        if hasattr(article, 'bias') and article.bias:
            params['bias'] = article.bias
        if hasattr(article, 'factual_reporting') and article.factual_reporting:
            params['factual_reporting'] = article.factual_reporting
        if hasattr(article, 'mbfc_credibility_rating') and article.mbfc_credibility_rating:
            params['mbfc_credibility_rating'] = article.mbfc_credibility_rating
        if hasattr(article, 'bias_country') and article.bias_country:
            params['bias_country'] = article.bias_country
        if hasattr(article, 'media_type') and article.media_type:
            params['media_type'] = article.media_type
        if hasattr(article, 'popularity') and article.popularity:
            params['popularity'] = article.popularity
    
    return urlencode(params)


def setup_templates():
    """Setup Jinja2 templates with custom class and filters."""
    templates = AppInfoJinja2Templates(directory="templates")

    # Enable auto-reload and disable caching for development
    templates.env.auto_reload = True
    templates.env.cache = {}

    # Register custom filters
    templates.env.filters["datetime"] = datetime_filter
    templates.env.filters["timeago"] = timeago_filter
    templates.env.filters["build_analysis_url"] = build_analysis_url_filter

    return templates