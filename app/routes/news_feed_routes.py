from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from typing import Optional
import logging
from datetime import datetime, timedelta
import json
import asyncio
import secrets
import string
import hashlib

from app.database import Database, get_database_instance
from app.services.news_feed_service import get_news_feed_service
from app.schemas.news_feed import NewsFeedRequest, NewsFeedResponse
from app.database_query_facade import DatabaseQueryFacade

router = APIRouter(prefix="/api/news-feed", tags=["news-feed"])
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True  # Force template reload on changes
templates.env.cache = {}  # Disable template compilation cache


@router.get("/available-dates")
async def get_available_dates(
    db: Database = Depends(get_database_instance)
):
    """Get dates that have articles available"""
    logger.info("Starting available-dates request")
    try:
        logger.info("Executing query for available dates")
        # Use the same filtering criteria as the news feed service including spam filtering
        query = """
        SELECT DATE(publication_date) as date, COUNT(*) as count 
        FROM articles 
        WHERE publication_date IS NOT NULL 
        AND category IS NOT NULL
        AND sentiment IS NOT NULL 
        AND bias IS NOT NULL
        AND factual_reporting IS NOT NULL
        AND title NOT LIKE '%Call@%'
        AND title NOT LIKE '%+91%'
        AND title NOT LIKE '%best%agency%'
        AND title NOT LIKE '%#1%'
        AND summary NOT LIKE '%Call@%'
        AND summary NOT LIKE '%phone%number%'
        AND news_source NOT LIKE '%medium.com/@%'
        GROUP BY DATE(publication_date) 
        ORDER BY date DESC 
        LIMIT 60
        """
        
        results = db.fetch_all(query)
        logger.info(f"Query completed, got {len(results)} results")
        
        # Convert to list of dictionaries
        available_dates = []
        for row in results:
            if hasattr(row, 'keys'):  # Handle Row objects
                date_dict = dict(row)
            else:
                date_dict = {"date": row[0], "count": row[1]}
            available_dates.append(date_dict)
        
        logger.info(f"Processed {len(available_dates)} available dates")
        return {"success": True, "dates": available_dates}
        
    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/daily")
async def generate_daily_news_feed(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(50, ge=10, le=200, description="Maximum articles to analyze"),
    model: str = Query("gpt-4.1-mini", description="AI model to use for generation"),
    include_bias_analysis: bool = Query(True, description="Include bias and factuality analysis"),
    db: Database = Depends(get_database_instance)
):
    """Generate daily news feed with overview and six articles report"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=max_articles,
            include_bias_analysis=include_bias_analysis,
            model=model
        )
        
        # Generate feed
        news_feed_service = get_news_feed_service(db)
        feed_response = await news_feed_service.generate_daily_feed(request)
        
        logger.info(f"Generated news feed for {target_date or 'today'} with {len(feed_response.overview.top_stories)} stories")
        
        return feed_response
        
    except ValueError as e:
        logger.error(f"Validation error in news feed generation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating news feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/articles")
async def get_news_articles_only(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_range: Optional[str] = Query("24h", description="Date range: 24h, 7d, 30d, 3m, 1y, all, or custom"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(1000, ge=10, le=10000),
    model: str = Query("gpt-4.1-mini"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    profile_id: Optional[int] = Query(None, description="Organizational profile ID for contextualized analysis"),
    starred_articles: Optional[str] = Query(None, description="Comma-separated URIs of starred articles"),
    db: Database = Depends(get_database_instance)
):
    """Get paginated article list similar to topic dashboard"""

    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Create request
        request = NewsFeedRequest(
            date=target_date,
            date_range=date_range,
            topic=topic,
            max_articles=max_articles,
            model=model,
            profile_id=profile_id
        )

        # Calculate SQL pagination parameters
        offset = (page - 1) * per_page
        limit = per_page

        # Generate article list - fetch ONLY the requested page from database
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date_range(
            date_range or "24h",
            max_articles,  # Kept for backwards compatibility
            topic,
            target_date,
            None,  # bias_filter
            offset,  # SQL OFFSET for pagination
            limit    # SQL LIMIT for pagination
        )
        
        if not articles_data:
            # Get the actual total count even when no articles returned (due to max_articles limit)
            actual_total = await news_feed_service._get_total_articles_count_for_date_range(
                date_range or "24h",
                request.topic,
                target_date
            )
            # Return empty result instead of 404
            return {
                "articles": {
                    "items": [],
                    "total_items": actual_total,
                    "total_articles": actual_total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (actual_total + per_page - 1) // per_page if actual_total > 0 else 0,
                    "date": (target_date or datetime.now()).isoformat()
                }
            }
        
        article_list = await news_feed_service._generate_article_list(articles_data, target_date or datetime.now(), request, page=page, per_page=per_page)
        
        return {"articles": article_list}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating news overview: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/six-articles")
async def get_six_articles_report(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_range: Optional[str] = Query("24h", description="Date range: 24h, 7d, 30d, 3m, 1y, all, or custom"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    max_articles: int = Query(50, ge=20, le=200),
    model: str = Query("gpt-4.1-mini"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    profile_id: Optional[int] = Query(None, description="Organizational profile ID for contextualized analysis"),
    starred_articles: Optional[str] = Query(None, description="Comma-separated URIs of starred articles"),
    persona: Optional[str] = Query("CEO", description="Target persona: CEO, CMO, CTO, CISO, or Custom"),
    article_count: int = Query(6, ge=1, le=8, description="Number of articles to select (1-8)"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance),
    force_regenerate: bool = Query(False, description="Bypass cache and regenerate fresh output")
):
    """Generate only the six articles detailed report"""

    try:
        # Get user_id from session for loading custom config
        user_id = session.get("user_id")

        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Parse starred articles if provided
        starred_uris = None
        if starred_articles:
            starred_uris = [uri.strip() for uri in starred_articles.split(',') if uri.strip()]
            logger.info(f"Received {len(starred_uris)} starred articles for six articles generation")

        # Create request with user_id
        request = NewsFeedRequest(
            date=target_date,
            date_range=date_range,
            topic=topic,
            max_articles=max_articles,
            model=model,
            profile_id=profile_id,
            persona=persona,
            article_count=article_count,
            starred_articles=starred_uris,
            user_id=user_id
        )
        
        # Generate only six articles report
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date_range(
            date_range or "24h",
            max_articles,
            topic,
            target_date
        )
        
        if not articles_data:
            # Return empty result instead of 404
            return {"six_articles": []}
        
        if force_regenerate:
            # Generate fresh and update caches implicitly via cached method write path
            six_articles = await news_feed_service._generate_six_articles_with_political_analysis(articles_data, target_date or datetime.now(), request)
            # Best-effort: write to cache for subsequent loads
            try:
                await news_feed_service._generate_six_articles_report_cached(articles_data, target_date or datetime.now(), request)
            except Exception as _:
                pass
        else:
            six_articles = await news_feed_service._generate_six_articles_report_cached(articles_data, target_date or datetime.now(), request)
        
        logger.info(f"Generated {len(six_articles)} six articles")
        if six_articles and len(six_articles) > 0:
            logger.info(f"First article has related_articles: {bool(six_articles[0].get('related_articles'))}")
            if six_articles[0].get('related_articles'):
                logger.info(f"First article related_articles count: {len(six_articles[0]['related_articles'])}")
        
        return {"six_articles": six_articles}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating six articles report: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- HTML Page Routes ---------- #
page_router = APIRouter(tags=["news-feed-pages"])


@page_router.get("/news-feed", response_class=HTMLResponse)
async def news_feed_page(request: Request, session=Depends(verify_session)):
    """Render the main news feed page (modernized v2)"""
    return templates.TemplateResponse("news_feed_new.html", {
        "request": request,
        "page_title": "News Narrator",
        "show_share_button": True,
        "session": session,
        "current_page": "investigate"
    })


@page_router.get("/news-feed-v2", response_class=HTMLResponse)
async def news_feed_v2_page(request: Request, session=Depends(verify_session)):
    """Render the NEW modernized news feed page (v2 - Proof of Concept)"""
    return templates.TemplateResponse("news_feed_new.html", {
        "request": request,
        "page_title": "News Narrator v2 - Proof of Concept",
        "show_share_button": True,
        "session": session,
        "current_page": "investigate"
    })


@page_router.get("/news-feed/overview", response_class=HTMLResponse)
async def news_overview_page(
    request: Request,
    session=Depends(verify_session),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Render the news overview page"""
    return templates.TemplateResponse("news_overview.html", {
        "request": request,
        "date": date,
        "page_title": "Daily News Overview",
        "show_share_button": True,
        "session": session
    })


@page_router.get("/news-feed/six-articles", response_class=HTMLResponse)
async def six_articles_page(
    request: Request,
    session=Depends(verify_session),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Render the six articles detailed report page"""
    return templates.TemplateResponse("six_articles.html", {
        "request": request,
        "date": date,
        "page_title": "Six Most Interesting Articles",
        "show_share_button": True,
        "session": {}  # Empty session for public access
    })


@router.get("/markdown/overview")
async def get_overview_markdown(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get news overview in markdown format"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=30,
            model="gpt-4.1-mini"
        )
        
        # Generate overview
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date(
            target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            request.max_articles,
            request.topic
        )
        
        if not articles_data:
            raise HTTPException(status_code=404, detail="No articles found")
        
        overview = await news_feed_service._generate_overview(articles_data, target_date or datetime.now(), request)
        
        # Convert to markdown
        markdown_content = _convert_overview_to_markdown(overview)
        
        return {"markdown": markdown_content, "overview": overview}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating markdown overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown/six-articles")
async def get_six_articles_markdown(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    db: Database = Depends(get_database_instance)
):
    """Get six articles report in markdown format"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create request
        request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=50,
            model="gpt-4.1-mini"
        )
        
        # Generate six articles report
        news_feed_service = get_news_feed_service(db)
        articles_data = await news_feed_service._get_articles_for_date(
            target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            request.max_articles,
            request.topic
        )
        
        if not articles_data:
            raise HTTPException(status_code=404, detail="No articles found")
        
        six_articles = await news_feed_service._generate_six_articles_report(articles_data, target_date or datetime.now(), request)
        
        # Convert to markdown
        markdown_content = _convert_six_articles_to_markdown(six_articles)
        
        return {"markdown": markdown_content, "six_articles": six_articles}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating markdown six articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/six-articles/config")
async def get_six_articles_config(
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """
    Get Six Articles configuration (system prompt, personas, format spec)
    Returns user-specific config or defaults if none exists
    """
    try:
        username = session.get("user")

        # Try to load user-specific config from database
        config = db.facade.get_six_articles_config(username)

        if config:
            return config

        # Return defaults if no custom config exists
        default_config = {
            "systemPrompt": None,  # Will use hardcoded default in service
            "personas": {
                "CEO": {
                    "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
                    "riskAppetite": "moderate",
                    "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
                },
                "CMO": {
                    "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
                    "riskAppetite": "high",
                    "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
                },
                "CTO": {
                    "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
                    "riskAppetite": "high",
                    "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
                },
                "CISO": {
                    "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
                    "riskAppetite": "low",
                    "focus": "security risks, compliance requirements, threat mitigation, and data protection"
                }
            },
            "formatSpec": None  # Will use hardcoded default in service
        }

        return default_config

    except Exception as e:
        logger.error(f"Error retrieving Six Articles config: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve configuration")


@router.post("/six-articles/config")
async def save_six_articles_config(
    config: dict,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """
    Save Six Articles configuration (system prompt, personas, format spec)
    Stored per-user in database
    """
    try:
        username = session.get("user")

        # Validate config structure
        if "personas" in config:
            required_personas = ["CEO", "CMO", "CTO", "CISO"]
            for persona in required_personas:
                if persona not in config["personas"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Missing required persona: {persona}"
                    )

        # Save to database
        success = db.facade.save_six_articles_config(username, config)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

        logger.info(f"Six Articles config saved for user {username}")
        return {"status": "success", "message": "Configuration saved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving Six Articles config: {e}")
        raise HTTPException(status_code=500, detail="Failed to save configuration")


@router.get("/six-articles/config/defaults")
async def get_six_articles_defaults(session=Depends(verify_session)):
    """
    Get default Six Articles configuration
    Useful for reset functionality
    """
    default_config = {
        "systemPrompt": None,  # Indicates use of hardcoded default
        "personas": {
            "CEO": {
                "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
                "riskAppetite": "moderate",
                "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
            },
            "CMO": {
                "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
                "riskAppetite": "high",
                "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
            },
            "CTO": {
                "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
                "riskAppetite": "high",
                "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
            },
            "CISO": {
                "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
                "riskAppetite": "low",
                "focus": "security risks, compliance requirements, threat mitigation, and data protection"
            }
        },
        "formatSpec": None  # Indicates use of hardcoded default
    }

    return default_config


def _convert_overview_to_markdown(overview) -> str:
    """Convert overview to markdown format"""
    
    markdown_lines = []
    
    # Title and date
    markdown_lines.append(f"# {overview.title}")
    markdown_lines.append(f"*{overview.date.strftime('%A, %B %d, %Y')}*")
    markdown_lines.append("")
    
    # Top stories
    for i, story in enumerate(overview.top_stories, 1):
        markdown_lines.append(f"## {i}. {story.headline}")
        markdown_lines.append("")
        markdown_lines.append(story.summary)
        markdown_lines.append("")
        
        if story.topic_description:
            markdown_lines.append(f"**Why it matters:** {story.topic_description}")
            markdown_lines.append("")
        
        # Primary source
        if story.primary_article.source.name:
            source_info = story.primary_article.source.name
            if story.primary_article.source.bias:
                source_info += f" ({story.primary_article.source.bias.value})"
            markdown_lines.append(f"**Source:** {source_info}")
            
        # Related articles
        if story.related_articles:
            markdown_lines.append("**More coverage:**")
            for related in story.related_articles:
                bias_info = f" ({related.bias.value})" if related.bias else ""
                markdown_lines.append(f"- {related.source}{bias_info}: {related.title}")
        
        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")
    
    # Footer
    markdown_lines.append(f"*Generated at {overview.generated_at.strftime('%H:%M UTC')} from {overview.total_articles_analyzed} articles*")
    
    return "\n".join(markdown_lines)


def _convert_six_articles_to_markdown(six_articles) -> str:
    """Convert six articles report to markdown format"""
    
    markdown_lines = []
    
    # Title and date
    markdown_lines.append(f"# {six_articles.title}")
    markdown_lines.append(f"*{six_articles.date.strftime('%A, %B %d, %Y')}*")
    markdown_lines.append("")
    
    # Executive summary
    if six_articles.executive_summary:
        markdown_lines.append("## Executive Summary")
        markdown_lines.append("")
        markdown_lines.append(six_articles.executive_summary)
        markdown_lines.append("")
    
    # Key themes
    if six_articles.key_themes:
        markdown_lines.append("## Key Themes")
        markdown_lines.append("")
        for theme in six_articles.key_themes:
            markdown_lines.append(f"- {theme}")
        markdown_lines.append("")
    
    # Articles
    markdown_lines.append("## Featured Articles")
    markdown_lines.append("")
    
    for i, article in enumerate(six_articles.articles, 1):
        markdown_lines.append(f"### {i}. {article.headline}")
        markdown_lines.append("")
        markdown_lines.append(article.summary)
        markdown_lines.append("")
        
        if article.topic_description:
            markdown_lines.append(f"**Analysis:** {article.topic_description}")
            markdown_lines.append("")
        
        # Source and bias info
        source_info = article.primary_article.source.name
        if article.primary_article.source.bias:
            source_info += f" (Bias: {article.primary_article.source.bias.value})"
        if article.primary_article.source.factuality:
            source_info += f" (Factuality: {article.primary_article.source.factuality.value})"
        
        markdown_lines.append(f"**Source:** {source_info}")
        markdown_lines.append("")
        
        # Perspective breakdown
        if article.perspective_breakdown:
            markdown_lines.append("**Different Perspectives:**")
            for perspective, points in article.perspective_breakdown.items():
                if points:
                    markdown_lines.append(f"- **{perspective.title()}:** {', '.join(points)}")
            markdown_lines.append("")
        
        # Related coverage
        if article.related_articles:
            markdown_lines.append("**Related Coverage:**")
            for related in article.related_articles:
                bias_info = f" ({related.bias.value})" if related.bias else ""
                markdown_lines.append(f"- {related.source}{bias_info}: {related.title}")
        
        markdown_lines.append("")
        markdown_lines.append("---")
        markdown_lines.append("")
    
    # Bias distribution
    if six_articles.bias_distribution:
        markdown_lines.append("## Source Bias Distribution")
        markdown_lines.append("")
        for bias, count in six_articles.bias_distribution.items():
            if count > 0:
                markdown_lines.append(f"- {bias.title()}: {count} articles")
        markdown_lines.append("")
    
    # Footer
    markdown_lines.append(f"*Generated at {six_articles.generated_at.strftime('%H:%M UTC')}*")
    
    return "\n".join(markdown_lines)


def generate_share_token() -> str:
    """Generate a random share token for secure URLs"""
    # Generate a random 12-character token using letters and numbers
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(12))


@router.post("/share")
async def create_shared_feed(
    request: Request,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    topic: Optional[str] = Query(None, description="Optional topic filter"),
    feed_type: str = Query("overview", description="Type of feed: overview or six-articles"),
    db: Database = Depends(get_database_instance)
):
    """Create a shareable link for a news feed"""
    
    try:
        # Parse date if provided
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Generate the feed first to ensure it exists
        feed_request = NewsFeedRequest(
            date=target_date,
            topic=topic,
            max_articles=50 if feed_type == "six-articles" else 30,
            model="gpt-4.1-mini"
        )
        
        news_feed_service = get_news_feed_service(db)
        
        if feed_type == "overview":
            articles_data = await news_feed_service._get_articles_for_date(
                target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                feed_request.max_articles,
                feed_request.topic
            )
            
            if not articles_data:
                raise HTTPException(status_code=404, detail="No articles found for the specified criteria")
            
            try:
                feed_data = await news_feed_service._generate_article_list(articles_data, target_date or datetime.now(), feed_request)
                feed_json = json.dumps(feed_data, default=str)
            except Exception as e:
                logger.error(f"Error generating article list for sharing: {e}")
                raise HTTPException(status_code=500, detail=f"Error generating feed data: {str(e)}")
            
        elif feed_type == "six-articles":
            articles_data = await news_feed_service._get_articles_for_date(
                target_date or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                feed_request.max_articles,
                feed_request.topic
            )
            
            if not articles_data:
                raise HTTPException(status_code=404, detail="No articles found for the specified criteria")
            
            try:
                feed_data = await news_feed_service._generate_six_articles_report(articles_data, target_date or datetime.now(), feed_request)
                feed_json = json.dumps(feed_data, default=str)
            except Exception as e:
                logger.error(f"Error generating six articles for sharing: {e}")
                raise HTTPException(status_code=500, detail=f"Error generating feed data: {str(e)}")
            
        else:
            raise HTTPException(status_code=400, detail="Invalid feed_type. Use 'overview' or 'six-articles'")
        
        # Generate share token
        share_token = generate_share_token()
        
        # Create shared feeds table if it doesn't exist
        try:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS shared_news_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                share_token TEXT UNIQUE NOT NULL,
                feed_type TEXT NOT NULL,
                feed_data TEXT NOT NULL,
                date_filter TEXT,
                topic_filter TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
            """
            db.execute_query(create_table_query)
        except Exception as e:
            logger.error(f"Error creating shared_news_feeds table: {e}")
            raise HTTPException(status_code=500, detail=f"Database setup error: {str(e)}")
        
        # Calculate expiration (30 days from now)
        expires_at = datetime.now() + timedelta(days=30)
        
        # Store the shared feed
        try:
            insert_query = """
            INSERT INTO shared_news_feeds 
            (share_token, feed_type, feed_data, date_filter, topic_filter, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            
            db.execute_query(insert_query, (
                share_token,
                feed_type,
                feed_json,
                date,
                topic,
                expires_at.isoformat()
            ))
        except Exception as e:
            logger.error(f"Error storing shared feed: {e}")
            raise HTTPException(status_code=500, detail=f"Database storage error: {str(e)}")
        
        # Generate shareable URLs
        base_url = str(request.url).replace(str(request.url.path), "")
        share_url = f"{base_url}/shared/{share_token}"
        
        return {
            "success": True,
            "share_token": share_token,
            "share_url": share_url,
            "expires_at": expires_at.isoformat(),
            "feed_type": feed_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shared feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/shared/{share_token}", response_class=HTMLResponse)
async def view_shared_feed(
    request: Request,
    share_token: str,
    db: Database = Depends(get_database_instance)
):
    """View a shared news feed"""
    
    try:
        # Look up the shared feed
        query = """
        SELECT feed_type, feed_data, date_filter, topic_filter, expires_at, access_count
        FROM shared_news_feeds 
        WHERE share_token = ?
        """
        
        result = db.fetch_one(query, (share_token,))
        
        if not result:
            raise HTTPException(status_code=404, detail="Shared feed not found")
        
        feed_type, feed_data_json, date_filter, topic_filter, expires_at, access_count = result
        
        # Check if expired
        if expires_at:
            expires_date = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_date:
                raise HTTPException(status_code=410, detail="Shared feed has expired")
        
        # Increment access count
        update_query = "UPDATE shared_news_feeds SET access_count = access_count + 1 WHERE share_token = ?"
        db.execute_query(update_query, (share_token,))
        
        # Parse feed data
        feed_data = json.loads(feed_data_json)
        
        # Render appropriate template
        if feed_type == "overview":
            return templates.TemplateResponse("shared_news_overview.html", {
                "request": request,
                "feed_data": feed_data,
                "date_filter": date_filter,
                "topic_filter": topic_filter,
                "page_title": f"Shared News Overview - {feed_data.get('title', 'Daily News')}",
                "share_token": share_token,
                "is_shared": True,
                "session": {}  # Empty session for public access
            })
        elif feed_type == "six-articles":
            return templates.TemplateResponse("shared_six_articles.html", {
                "request": request,
                "feed_data": feed_data,
                "date_filter": date_filter,
                "topic_filter": topic_filter,
                "page_title": f"Shared Report - {feed_data.get('title', 'Six Articles')}",
                "share_token": share_token,
                "is_shared": True,
                "session": {}  # Empty session for public access
            })
        else:
            raise HTTPException(status_code=400, detail="Invalid feed type")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing shared feed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/api/shared/{share_token}")
async def get_shared_feed_data(
    share_token: str,
    db: Database = Depends(get_database_instance)
):
    """Get shared feed data as JSON"""
    
    try:
        # Look up the shared feed
        query = """
        SELECT feed_type, feed_data, date_filter, topic_filter, expires_at, access_count
        FROM shared_news_feeds 
        WHERE share_token = ?
        """
        
        result = db.fetch_one(query, (share_token,))
        
        if not result:
            raise HTTPException(status_code=404, detail="Shared feed not found")
        
        feed_type, feed_data_json, date_filter, topic_filter, expires_at, access_count = result
        
        # Check if expired
        if expires_at:
            expires_date = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_date:
                raise HTTPException(status_code=410, detail="Shared feed has expired")
        
        # Increment access count
        update_query = "UPDATE shared_news_feeds SET access_count = access_count + 1 WHERE share_token = ?"
        db.execute_query(update_query, (share_token,))
        
        # Parse and return feed data
        feed_data = json.loads(feed_data_json)
        
        return {
            "success": True,
            "feed_type": feed_type,
            "feed_data": feed_data,
            "date_filter": date_filter,
            "topic_filter": topic_filter,
            "access_count": access_count + 1,
            "share_token": share_token
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shared feed data: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/category-icons")
async def get_category_icons(
    categories: Optional[str] = Query(None, description="Comma-separated list of categories"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Get category icons (Font Awesome icon classes) for given categories.

    Icons are either pre-defined or generated once and stored in the database.
    Returns a mapping of category -> icon HTML string.
    """
    try:
        # Pre-defined category icons (Font Awesome)
        predefined_icons = {
            'Technology': '<i class="fas fa-laptop-code"></i>',
            'Business': '<i class="fas fa-briefcase"></i>',
            'Politics': '<i class="fas fa-landmark"></i>',
            'Science': '<i class="fas fa-flask"></i>',
            'Health': '<i class="fas fa-heartbeat"></i>',
            'Environment': '<i class="fas fa-leaf"></i>',
            'Education': '<i class="fas fa-graduation-cap"></i>',
            'Entertainment': '<i class="fas fa-film"></i>',
            'Sports': '<i class="fas fa-football-ball"></i>',
            'Economy': '<i class="fas fa-chart-line"></i>',
            'Finance': '<i class="fas fa-dollar-sign"></i>',
            'Security': '<i class="fas fa-shield-alt"></i>',
            'Military': '<i class="fas fa-fighter-jet"></i>',
            'International': '<i class="fas fa-globe"></i>',
            'Law': '<i class="fas fa-gavel"></i>',
            'Society': '<i class="fas fa-users"></i>',
            'Culture': '<i class="fas fa-palette"></i>',
            'Transportation': '<i class="fas fa-car"></i>',
            'Energy': '<i class="fas fa-bolt"></i>',
            'Space': '<i class="fas fa-rocket"></i>',
            'AI': '<i class="fas fa-robot"></i>',
            'Uncategorized': '<i class="fas fa-folder"></i>'
        }

        icon_map = {}

        # If specific categories requested
        if categories:
            category_list = [c.strip() for c in categories.split(',') if c.strip()]
        else:
            # Return all predefined icons
            return {
                "success": True,
                "icons": predefined_icons
            }

        # Build icon map for requested categories
        for category in category_list:
            # Check predefined first
            if category in predefined_icons:
                icon_map[category] = predefined_icons[category]
            else:
                # Try partial match
                found = False
                for key, icon in predefined_icons.items():
                    if key.lower() in category.lower() or category.lower() in key.lower():
                        icon_map[category] = icon
                        found = True
                        break

                # Use default if no match
                if not found:
                    icon_map[category] = '<i class="fas fa-file-alt"></i>'

        return {
            "success": True,
            "icons": icon_map
        }

    except Exception as e:
        logger.error(f"Error getting category icons: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate-category-icon")
async def generate_category_icon(
    category: str = Query(..., description="Category name"),
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Generate an AI-created icon for a category using DALL-E or similar.

    This endpoint will generate a unique icon image for custom categories
    and store it in the database/filesystem for future use.

    Note: This requires DALL-E API access and incurs costs.
    For now, we return Font Awesome icon classes as a lightweight alternative.
    """
    try:
        # TODO: Implement AI image generation using DALL-E when needed
        # For now, return a sensible Font Awesome icon

        # Simple keyword matching for common themes
        category_lower = category.lower()
        icon_html = '<i class="fas fa-file-alt"></i>'  # default

        theme_icons = {
            'tech': '<i class="fas fa-microchip"></i>',
            'cyber': '<i class="fas fa-user-secret"></i>',
            'data': '<i class="fas fa-database"></i>',
            'cloud': '<i class="fas fa-cloud"></i>',
            'mobile': '<i class="fas fa-mobile-alt"></i>',
            'web': '<i class="fas fa-globe"></i>',
            'code': '<i class="fas fa-code"></i>',
            'software': '<i class="fas fa-laptop-code"></i>',
            'hardware': '<i class="fas fa-server"></i>',
            'network': '<i class="fas fa-network-wired"></i>',
            'crypto': '<i class="fas fa-lock"></i>',
            'medical': '<i class="fas fa-stethoscope"></i>',
            'legal': '<i class="fas fa-balance-scale"></i>',
            'money': '<i class="fas fa-money-bill"></i>',
            'trade': '<i class="fas fa-exchange-alt"></i>',
            'climate': '<i class="fas fa-cloud-sun"></i>',
            'food': '<i class="fas fa-utensils"></i>',
            'travel': '<i class="fas fa-plane"></i>',
            'automotive': '<i class="fas fa-car"></i>',
            'real estate': '<i class="fas fa-home"></i>',
            'retail': '<i class="fas fa-shopping-cart"></i>',
            'manufacturing': '<i class="fas fa-industry"></i>',
            'agriculture': '<i class="fas fa-tractor"></i>',
            'media': '<i class="fas fa-newspaper"></i>',
            'telecom': '<i class="fas fa-phone"></i>',
            'research': '<i class="fas fa-microscope"></i>'
        }

        for keyword, icon in theme_icons.items():
            if keyword in category_lower:
                icon_html = icon
                break

        return {
            "success": True,
            "category": category,
            "icon": icon_html,
            "method": "font-awesome"  # vs "ai-generated" when DALL-E is implemented
        }

    except Exception as e:
        logger.error(f"Error generating category icon: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
