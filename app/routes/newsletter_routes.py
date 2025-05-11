"""Routes for newsletter compilation and distribution."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.templating import Jinja2Templates

from app.database import Database, get_database_instance
from app.schemas.newsletter import NewsletterRequest, NewsletterResponse
from app.services.newsletter_service import NewsletterService
from app.dependencies import get_newsletter_service
from app.security.session import verify_session
from app.config.config import load_config

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["newsletter"])


@router.get("/api/newsletter/topics")
async def get_newsletter_topics():
    """Get available topics for newsletter compilation."""
    try:
        logger.info("Newsletter topics endpoint called")
        
        # Load config to get topics
        config = load_config()
        topics = [topic["name"] for topic in config.get("topics", [])]
        
        # Fallback to static list if no topics found
        if not topics:
            logger.warning("No topics found in config, returning static list")
            topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        
        logger.info(f"Returning topics for newsletter: {topics}")
        return JSONResponse(content=topics)
        
    except Exception as e:
        logger.error(f"Error getting topics for newsletter: {str(e)}", exc_info=True)
        # Return static list on error
        static_topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        logger.info(f"Returning static topics due to error: {static_topics}")
        return JSONResponse(content=static_topics)


@router.get("/api/newsletter/content_types")
async def get_newsletter_content_types():
    """Get available content types for newsletter compilation."""
    content_types = [
        {"id": "topic_summary", "name": "Topic Summary", 
         "description": "AI-generated summary of the topic"},
        {"id": "key_charts", "name": "Key Charts", 
         "description": "Relevant charts from analytics"},
        {"id": "trend_analysis", "name": "Trend Analysis", 
         "description": "AI-generated trend analysis"},
        {"id": "article_insights", "name": "Article Insights", 
         "description": "Thematic analysis of articles"},
        {"id": "key_articles", "name": "Key Articles", 
         "description": "List of key articles with links and 'why it merits attention'"},
        {"id": "latest_podcast", "name": "Latest Podcast", 
         "description": "Link and summary for the latest podcast"},
        {"id": "ethical_societal_impact", "name": "Ethical & Societal Impact",
         "description": "Analysis of ethical and societal implications"},
        {"id": "business_impact", "name": "Business Impact",
         "description": "Analysis of business implications and opportunities"},
        {"id": "market_impact", "name": "Market Impact",
         "description": "Analysis of market trends and competitive landscape"}
    ]
    return JSONResponse(content=content_types)


@router.post("/api/newsletter/compile", response_model=NewsletterResponse)
async def compile_newsletter(
    request: NewsletterRequest,
    db: Database = Depends(get_database_instance),
    newsletter_service: NewsletterService = Depends(get_newsletter_service)
):
    """
    Compile newsletter content based on provided parameters.
    
    The endpoint accepts:
    - frequency: daily, weekly, monthly
    - topics: list of topics to include
    - content_types: list of content types to include
    - start_date: optional start date (if not provided, calculated based on frequency)
    - end_date: optional end date (if not provided, defaults to today)
    
    Returns compiled markdown content.
    """
    logger.info(f"Received newsletter compilation request: {request}")
    
    try:
        # Compile the newsletter
        compiled_markdown = await newsletter_service.compile_newsletter(request)
        
        # Return the response
        return NewsletterResponse(
            message="Newsletter compilation successful",
            compiled_markdown=compiled_markdown,
            request_payload=request
        )
        
    except Exception as e:
        logger.error(f"Error compiling newsletter: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error compiling newsletter: {str(e)}")


@router.post("/api/newsletter/markdown_to_html")
async def convert_markdown_to_html(markdown_content: str):
    """Convert markdown content to HTML for preview."""
    import markdown
    
    try:
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content, 
            extensions=["tables", "fenced_code"]
        )
        
        return JSONResponse(content={"html_content": html_content})
        
    except Exception as e:
        logger.error(f"Error converting markdown to HTML: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error converting markdown to HTML: {str(e)}"
        )


# Page router for rendering HTML templates
page_router = APIRouter(tags=["newsletter_pages"])


@page_router.get("/newsletter_compiler", response_class=HTMLResponse)
async def newsletter_page(
    request: Request,
    session=Depends(verify_session)
):
    """
    Render the newsletter compilation page.
    
    This endpoint renders the newsletter_compiler.html template.
    """
    from app.main import get_template_context
    
    # Initialize templates
    templates = Jinja2Templates(directory="templates")
    
    # Create template context
    context = get_template_context(request)
    
    # Render the template
    return templates.TemplateResponse("newsletter_compiler.html", context) 