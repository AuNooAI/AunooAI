"""Main FastAPI application file."""

from fastapi import FastAPI, Request, Form, Query, Body, Depends, HTTPException, status  # Add this import at the top with other FastAPI imports
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.collectors.newsapi_collector import NewsAPICollector
from app.collectors.arxiv_collector import ArxivCollector
from app.collectors.bluesky_collector import BlueskyCollector
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from app.database import Database, get_database_instance
from app.research import Research
from app.analytics import Analytics
from app.report import Report
from app.analyze_db import AnalyzeDB 
from app.config.settings import config
from typing import Optional, List
from collections import Counter
from datetime import datetime, timedelta, timezone
from app.dependencies import get_research, get_analytics, get_report  # Add at top of file
import logging
import traceback
from pydantic import BaseModel, Field
import asyncio
import markdown
import json
import importlib
from app.ai_models import get_ai_model, get_available_models, ai_get_available_models
from app.bulk_research import BulkResearch
from app.config.config import load_config, get_topic_config, get_news_query, set_news_query, get_paper_query, set_paper_query, load_news_monitoring, save_news_monitoring
import os
from dotenv import load_dotenv
from app.collectors.collector_factory import CollectorFactory
import importlib
import ssl
import uvicorn
from app.middleware.https_redirect import HTTPSRedirectMiddleware
from app.routes.prompt_routes import router as prompt_router
from app.security.auth import User, get_current_active_user, verify_password, get_password_hash
from app.routes import prompt_routes
from app.routes.web_routes import router as web_router
from app.routes.topic_routes import router as topic_router
from app.routes.api_routes import router as api_router  # Add this line for api_routes
from starlette.middleware.sessions import SessionMiddleware
from app.security.session import verify_session
from app.routes.keyword_monitor import router as keyword_monitor_router, page_router as keyword_monitor_page_router, get_alerts
from app.routes.keyword_alerts import router as keyword_alerts_router
from app.tasks.keyword_monitor import run_keyword_monitor
import sqlite3
from app.routes import database  # Make sure this import exists
from app.routes.stats_routes import router as stats_router
from app.routes.background_tasks import router as background_tasks_router
from app.routes.auto_ingest import router as auto_ingest_router
# from app.routes.news_feed_routes import router as news_feed_router  # Now registered via app factory
from app.routes.chat_routes import router as chat_router
from app.routes.database import router as database_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.dashboard_cache_routes import router as dashboard_cache_router
import shutil
from app.utils.app_info import get_app_info
from starlette.templating import _TemplateResponse  # Add this import at the top
from app.routes.onboarding_routes import router as onboarding_router
from app.startup import initialize_application
from app.routes.podcast_routes import router as podcast_router
from app.routes.vector_routes import router as vector_router
from app.routes.saved_searches import router as saved_searches_router
# Removed scenario routes - no longer needed
# Removed topic_map routes - no longer needed
from app.routes.auspex_routes import router as auspex_router
# Removed newsletter routes - no longer needed
from app.routes.dataset_routes import router as dataset_router
from app.routes.keyword_monitor_api import router as keyword_monitor_api_router
from app.routes.oauth_routes import router as oauth_router
from app.routes.websocket_routes import router as websocket_router
from app.routes.user_management_routes import router as user_management_router  # Multi-user support (Added 2025-10-21)

# ElevenLabs SDK imports used in podcast endpoints
from elevenlabs import ElevenLabs, PodcastConversationModeData, PodcastTextSource
from elevenlabs.studio import (
    BodyCreatePodcastV1StudioPodcastsPostMode_Conversation,
    BodyCreatePodcastV1StudioPodcastsPostMode_Bulletin,
)

# Set up logging
logger = logging.getLogger(__name__)

# Use our app factory pattern (with lifespan management in app_factory.py)
from app.core.app_factory import create_app
app = create_app()

# Get templates from app state (configured by app factory)
templates = app.state.templates

# Initialize components (database is already in app.state)
db = app.state.db

# Newsletter routers - REMOVED

# Import media bias routes
from app.routes import media_bias_routes

# Test routes - REMOVED

# Add dataset router
app.include_router(dataset_router)

# Register media bias routes
app.include_router(media_bias_routes.router)  # Add the new media bias routes

# Test routes - REMOVED

# Add Auspex routes
app.include_router(auspex_router)

# Include API routes
app.include_router(api_router, prefix="/api")  # Add this line to include the API router

# Add routes
app.include_router(keyword_monitor_router)
app.include_router(keyword_monitor_page_router)
app.include_router(keyword_monitor_api_router, prefix="/api")
app.include_router(keyword_alerts_router, prefix="/api")  # Bulk delete articles endpoint
app.include_router(onboarding_router)
app.include_router(user_management_router)  # User management API (Added 2025-10-21)

class ArticleData(BaseModel):
    title: str
    news_source: str
    uri: str
    publication_date: str
    summary: str
    category: str
    future_signal: str
    future_signal_explanation: str
    sentiment: str
    sentiment_explanation: str
    time_to_impact: str
    time_to_impact_explanation: str
    tags: List[str]  # This ensures tags is always a list
    driver_type: str
    driver_type_explanation: str
    submission_date: str = Field(default_factory=lambda: datetime.now().isoformat())
    topic: str

class AddModelRequest(BaseModel):
    model_name: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)

    class Config:
        protected_namespaces = ()

class RemoveModelRequest(BaseModel):
    model_name: str = Field(..., alias="model_name")
    provider: str

    class Config:
        protected_namespaces = ()

class NewsAPIConfig(BaseModel):
    api_key: str = Field(..., min_length=1)

    class Config:
        alias_generator = lambda string: string.lower()
        populate_by_name = True

class DiaAPIConfig(BaseModel):
    """Configuration payload for Dia TTS service.

    The `api_key` is required, but the service URL can be omitted and will
    default to the existing value (or be left unset) if an empty string or
    `null` is provided. Making `url` optional prevents 422 validation errors
    when the user only wants to update the API key.
    """

    api_key: str = Field(..., min_length=1, alias="api_key")
    url: Optional[str] = Field(None, alias="url")

    class Config:
        alias_generator = lambda s: s.lower()  # type: ignore
        populate_by_name = True

# Only add HTTPS redirect in production
if os.getenv('ENVIRONMENT') == 'production':
    app.add_middleware(HTTPSRedirectMiddleware)

# Include the prompt router
app.include_router(prompt_router)
logger.info("Prompt routes included")

# Include routers
app.include_router(web_router)  # Web routes at root level
app.include_router(topic_router)  # Topic routes
app.include_router(keyword_monitor_router)
app.include_router(keyword_monitor_page_router)
app.include_router(onboarding_router)
app.include_router(saved_searches_router)  # Saved searches
app.include_router(websocket_router, prefix="/keyword-monitor")  # WebSocket routes for real-time updates
app.include_router(vector_router)  # Vector/AI analysis routes (already has /api prefix)
app.include_router(background_tasks_router)  # Background task management routes
app.include_router(auto_ingest_router)  # Auto-ingest pipeline routes
# app.include_router(news_feed_router)  # News feed routes - Now registered via app factory
app.include_router(dashboard_cache_router)  # Dashboard cache and export routes

def get_template_context(request: Request, additional_context: dict = None) -> dict:
    """Create a base template context with common variables."""
    # Get fresh app info
    app_info = get_app_info()
    logger.debug(f"Creating template context with app_info: {app_info}")

    context = {
        "request": request,
        "app_info": app_info
    }

    if additional_context:
        # Allow overwriting of all keys - routes should provide enhanced session
        for key, value in additional_context.items():
            if key not in ["request", "app_info"]:  # Only protect request and app_info
                context[key] = value

    logger.debug(f"Final template context: {context}")
    return context

# Add this with your other dependencies
async def get_template_context_dependency(request: Request):
    """Dependency that provides a template context with app_info."""
    return get_template_context(request)

# Then update route handlers to use it
@app.get("/", response_class=HTMLResponse)
async def root(
    request: Request, 
    session=Depends(verify_session),
    context=Depends(get_template_context_dependency)
):
    try:
        db_info = db.get_database_info()
        config = load_config()
        
        # Get topics from config.json
        config_topics = {topic["name"]: topic for topic in config["topics"]}
        
        # Get topics from database with article counts and last article dates
        db_topics = db.facade.get_topics_with_article_counts()
        
        # Prepare active topics list
        active_topics = []
        for topic_name, topic_data in config_topics.items():
            # Create entry with defaults
            topic_info = {
                "name": topic_name,
                "article_count": 0,
                "last_article_date": None
            }
            
            # Update with database info if available
            if topic_name in db_topics:
                topic_info["article_count"] = db_topics[topic_name]["article_count"]
                topic_info["last_article_date"] = db_topics[topic_name]["last_article_date"]
            
            active_topics.append(topic_info)
        
        # Merge the base context with additional data
        context.update({
            "db_info": db_info,
            "active_topics": active_topics,
            "session": session  # Add session to template context
        })
        
        return templates.TemplateResponse("index.html", context)
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        "login.html",
        {"request": request}  # The template class will automatically add session
    )

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        # Check for admin/admin credentials
        if username == "admin" and password == "admin":
            # Get or create admin user
            user = db.get_user(username)
            if not user:
                # Create admin user with force_password_change flag
                hashed_password = get_password_hash(password)
                db.create_user(username, hashed_password, force_password_change=True)
                user = db.get_user(username)
            elif not user.get('force_password_change'):
                # If admin/admin is used but force_password_change is False, force it again
                db.set_force_password_change(username, True)
                user = db.get_user(username)
        else:
            # Get user from database for non-admin login
            user = db.get_user(username)
            
        logger.debug(f"Login attempt for user: {username}")
        logger.debug(f"User found in database: {user is not None}")
        
        if not user:
            logger.warning(f"User not found: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "Invalid credentials"
                },
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        is_valid = verify_password(password, user['password'])
        logger.debug(f"Password verification result: {is_valid}")

        if not is_valid:
            logger.warning(f"Invalid password for user: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "Invalid credentials"
                },
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        request.session["user"] = username
        
        # Check if password change is required
        if user.get('force_password_change'):
            return RedirectResponse(url="/change_password", status_code=status.HTTP_302_FOUND)
        elif not user.get('completed_onboarding'):
            return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)
            
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"}
        )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/research", response_class=HTMLResponse)
async def research_get(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse(
        "research.html", 
        get_template_context(request)
    )

@app.post("/research")
async def research_post(
    request: Request,
    session=Depends(verify_session),  # Add session dependency
    articleUrl: str = Form(...),
    articleContent: Optional[str] = Form(None),
    summaryLength: str = Form(...),
    summaryVoice: str = Form(...),
    summaryType: str = Form(...),
    selectedTopic: str = Form(...),
    modelName: str = Form(...),
    preservedMetadata: Optional[str] = Form(None),
    research: Research = Depends(get_research)
):
    try:
        # Parse preserved metadata if available
        preserved_data = {}
        if preservedMetadata:
            try:
                preserved_data = json.loads(preservedMetadata)
                logger.info(f"Using preserved metadata: {preserved_data}")
            except json.JSONDecodeError:
                logger.warning("Failed to parse preserved metadata, proceeding with full analysis")
        
        if not modelName:
            # If no model is available, return basic article information without analysis
            article_info = await research.fetch_article_content(articleUrl)
            return JSONResponse(content={
                "title": preserved_data.get('title') or "Article title not available",
                "news_source": preserved_data.get('source') or article_info.get("source", "Unknown"),
                "uri": articleUrl,
                "publication_date": preserved_data.get('publication_date') or article_info.get("publication_date", "Unknown"),
                "summary": "Analysis not available. No AI model selected.",
                "topic": selectedTopic
            })
        
        # Perform analysis with preserved metadata consideration
        if preserved_data:
            result = await analyze_with_preserved_metadata(
                research=research,
                url=articleUrl,
                content=articleContent,
                topic=selectedTopic,
                model_name=modelName,
                summary_type=summaryType,
                summary_voice=summaryVoice,
                summary_length=summaryLength,
                preserved_data=preserved_data
            )
        else:
            # Full analysis including metadata extraction
            result = await research.analyze_article(
                uri=articleUrl,
                article_text=articleContent,
                summary_length=summaryLength,
                summary_voice=summaryVoice,
                summary_type=summaryType,
                topic=selectedTopic,
                model_name=modelName
            )
        
        return JSONResponse(content=result)
    except ValueError as e:
        logger.error(f"Error in research_post: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in research_post: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def analyze_with_preserved_metadata(research, url, content, topic, model_name, summary_type, summary_voice, summary_length, preserved_data):
    """Analyze article using preserved metadata, only extracting missing fields"""
    
    # Start with preserved metadata
    result = {
        'uri': url,
        'title': preserved_data.get('title'),
        'news_source': preserved_data.get('source'),
        'publication_date': preserved_data.get('publication_date'),
        'bias': preserved_data.get('bias'),
        'factual_reporting': preserved_data.get('factual_reporting'),
        'mbfc_credibility_rating': preserved_data.get('mbfc_credibility_rating'),
        'bias_country': preserved_data.get('bias_country'),
        'media_type': preserved_data.get('media_type'),
        'popularity': preserved_data.get('popularity')
    }
    
    # Only extract metadata that's missing
    if not result['title'] or not result['news_source']:
        logger.info("Some metadata missing, extracting with LLM...")
        full_analysis = await research.analyze_article(
            uri=url,
            article_text=content,
            summary_length=summary_length,
            summary_voice=summary_voice,
            summary_type=summary_type,
            topic=topic,
            model_name=model_name
        )
        
        # Only use extracted values if preserved values are missing
        if not result['title']:
            result['title'] = full_analysis.get('title')
        if not result['news_source']:
            result['news_source'] = full_analysis.get('news_source')
        if not result['publication_date']:
            result['publication_date'] = full_analysis.get('publication_date')
        
        # Always get content analysis from full analysis
        content_fields = [
            'summary', 'category', 'sentiment', 'sentiment_explanation',
            'future_signal', 'future_signal_explanation', 'driver_type',
            'driver_type_explanation', 'time_to_impact', 'time_to_impact_explanation',
            'tags'
        ]
        
        for field in content_fields:
            if field in full_analysis:
                result[field] = full_analysis[field]
    else:
        # We have all metadata, just do content analysis
        content_analysis = await research.analyze_article(
            uri=url,
            article_text=content,
            summary_length=summary_length,
            summary_voice=summary_voice,
            summary_type=summary_type,
            topic=topic,
            model_name=model_name
        )
        
        # Extract only content analysis fields
        content_fields = [
            'summary', 'category', 'sentiment', 'sentiment_explanation',
            'future_signal', 'future_signal_explanation', 'driver_type',
            'driver_type_explanation', 'time_to_impact', 'time_to_impact_explanation',
            'tags'
        ]
        
        for field in content_fields:
            if field in content_analysis:
                result[field] = content_analysis[field]
    
    return result
    
@app.get("/bulk-research", response_class=HTMLResponse)
async def bulk_research_get(
    request: Request,
    session=Depends(verify_session),
    urlList: str = Query(None),
    topic: str = Query(None)
):
    return templates.TemplateResponse("bulk_research.html", {
        "request": request,
        "session": request.session,
        "prefilled_urls": urlList or "",
        "selected_topic": topic or ""
    })

@app.post("/api/bulk-research")
async def bulk_research_post(
    data: dict,
    research: Research = Depends(get_research),
    db: Database = Depends(get_database_instance)
):
    try:
        # Validate required topic
        topic = data.get('topic')
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")

        # Get model name from request or use first available model
        model_name = data.get('model_name')
        if not model_name:
            available_models = research.get_available_models()
            if not available_models:
                raise HTTPException(status_code=400, detail="No AI models available")
            model_name = available_models[0]['name']

        # Validate and convert summary_length to integer
        summary_length = data.get("summary_length", "50")  # Default to 50 words
        try:
            summary_length = int(summary_length)
            if summary_length < 1:
                raise ValueError("Summary length must be a positive integer")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid summary length: {str(e)}")

        bulk_research = BulkResearch(db, research=research)
        results = await bulk_research.analyze_bulk_urls(
            urls=data.get("urls", []),
            summary_type=data.get("summary_type", "curious_ai"),
            model_name=model_name,
            summary_length=summary_length,
            summary_voice=data.get("summary_voice", "neutral"),
            topic=topic
        )
        
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return JSONResponse(content={
            "batch_id": batch_id, 
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Bulk research error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-bulk-articles")
async def save_bulk_articles(
    data: dict,
    research: Research = Depends(get_research),
    db: Database = Depends(get_database_instance)
):
    articles = data.get('articles', [])
    bulk_research = BulkResearch(db)
    results = await bulk_research.save_bulk_articles(articles)
    return JSONResponse(content=results)

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_route(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse(
        "analytics.html", 
        get_template_context(request)
    )

@app.get("/api/analytics")
def get_analytics_data(
    timeframe: str = Query(...),
    category: Optional[List[str]] = Query(None),
    topic: str = Query(...),
    sentiment: Optional[List[str]] = Query(None),
    timeToImpact: Optional[List[str]] = Query(None),
    driverType: Optional[List[str]] = Query(None),
    curated: bool = Query(True),
    analytics: Analytics = Depends(get_analytics)
):
    logger.info(f"Received analytics request: timeframe={timeframe}, category={category}, topic={topic}, filters={sentiment},{timeToImpact},{driverType}, curated={curated}")
    try:
        cat_param = category[0] if category and len(category) == 1 else category
        data = analytics.get_analytics_data(
            timeframe=timeframe, 
            category=cat_param, 
            topic=topic,
            sentiment=sentiment[0] if sentiment and len(sentiment) == 1 else sentiment,
            time_to_impact=timeToImpact[0] if timeToImpact and len(timeToImpact) == 1 else timeToImpact,
            driver_type=driverType[0] if driverType and len(driverType) == 1 else driverType,
            curated=curated
        )
        logger.info("Analytics data retrieved successfully")
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in get_analytics_data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, session=Depends(verify_session)):
    """Display configuration page"""
    try:
        config = load_config()
        models = config.get("ai_models", [])
        
        # Get currently configured providers
        providers = await get_providers()
        
        # Check if Bluesky is configured
        bluesky_configured = (
            os.getenv('PROVIDER_BLUESKY_USERNAME') is not None and
            os.getenv('PROVIDER_BLUESKY_PASSWORD') is not None
        )
        
        return templates.TemplateResponse(
            "config.html",
            get_template_context(request, {
                "models": models,
                "providers": providers,
                "session": session,
                "bluesky_configured": bluesky_configured
            })
        )
    except Exception as e:
        logger.error(f"Error loading config page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users-test", response_class=HTMLResponse)
async def users_test_page(request: Request, session=Depends(verify_session)):
    """Test page for user management debugging"""
    return templates.TemplateResponse(
        "users_test.html",
        get_template_context(request, {"session": session})
    )

@app.post("/config/add_model")
async def add_model(model_data: AddModelRequest):
    """Add a new model configuration by setting the appropriate environment variable."""
    try:
        logger.info(f"Adding model {model_data.model_name} for provider {model_data.provider}")
        # Get the environment variable name based on the model and provider
        
        # The format we'll use for environment variables is:
        # PROVIDER_API_KEY_MODEL_NAME
        # E.g., OPENAI_API_KEY_GPT_4, ANTHROPIC_API_KEY_CLAUDE_3_OPUS
        
        provider = model_data.provider.upper()
        model_name = model_data.model_name
        
        # Normalize model name for the environment variable:
        # - Convert hyphens to underscores
        # - Usually all uppercase, but preserve dots if present
        normalized_model = model_name.replace('-', '_').upper()
        
        # For models with dots like GPT-3.5-TURBO or CLAUDE-3.5-SONNET
        # Properly handle the dots in the environment variable name
        if '.' in model_name:
            env_var_name = f"{provider}_API_KEY_{normalized_model}"
        else:
            env_var_name = f"{provider}_API_KEY_{normalized_model}"
        
        # Support common format conversions used in the codebase
        common_formats = [env_var_name]
        
        # Save environment variable(s)
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        logger.info(f"Saving to .env file at: {env_path}")
        
        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []
        
        # Check if the environment variable already exists and update it
        env_var_updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_var_name}="):
                # Use single quotes for environment variables to be consistent
                lines[i] = f"{env_var_name}='{model_data.api_key}'\n"
                env_var_updated = True
                break
        
        # If not updated, add it
        if not env_var_updated:
            # Add at the end, use single quotes to match existing format
            lines.append(f"{env_var_name}='{model_data.api_key}'\n")
        
        # Write back to .env file
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)
        
        # Set the environment variable in the current process
        os.environ[env_var_name] = model_data.api_key
        
        # Reload environment variables to ensure they take effect immediately
        load_dotenv(dotenv_path=env_path, override=True)
        
        # Debug log
        masked_key = model_data.api_key[:4] + "..." + model_data.api_key[-4:] if len(model_data.api_key) > 8 else "***"
        logger.info(f"Added model {model_data.model_name} with environment variable {env_var_name}={masked_key}")
        
        # This updated model will show in the list of available models in AI Models service
        
        return JSONResponse(content={"message": f"Model {model_data.model_name} added successfully"})

    except Exception as e:
        logger.error(f"Error adding model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/remove_model")
async def remove_model(model_data: RemoveModelRequest):
    """Remove model configuration from .env file and environment."""
    try:
        model_name = model_data.model_name
        provider = model_data.provider.upper()
        logger.info(f"Removing model {model_name} for provider {provider}")
        
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()
        
        # Remove all variants of the model's API key
        filtered_lines = []
        model_keys_removed = []
        
        # Normalize model name for matching
        normalized_model = model_name.replace('-', '_').upper()
        normalized_model_with_dots = model_name.replace('-', '_').upper()
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                filtered_lines.append(line)
                continue
                
            # Get just the variable name before the equals sign
            if '=' not in line_stripped:
                filtered_lines.append(line)
                continue
                
            key_name = line_stripped.split('=')[0]
            
            # Handle models with dots in the name (like gpt-3.5-turbo)
            # Create a few common patterns to match against
            env_var_prefix = f"{provider}_API_KEY_"
            
            should_remove = False
            
            # Direct match check
            if key_name.startswith(env_var_prefix):
                # Extract the model part of the key
                model_part = key_name[len(env_var_prefix):]
                
                # Convert to lowercase for case-insensitive comparison
                model_part_lower = model_part.lower()
                normalized_model_lower = normalized_model.lower()
                
                # Different ways the model might be formatted in env vars
                model_patterns = [
                    model_name.upper(),                           # GPT-3.5-TURBO
                    model_name.replace('-', '_').upper(),         # GPT_3_5_TURBO
                    model_name.replace('-', '.').upper(),         # GPT.3.5.TURBO
                    model_name.replace('-', '').upper(),          # GPT35TURBO
                    model_name.replace('.', '_').replace('-', '_').upper()  # GPT_3_5_TURBO
                ]
                
                # Special pattern for models with dots
                if '.' in model_name:
                    # Replace dots with underscores while preserving the dots position
                    dot_preserved_pattern = ''.join([c if c != '.' else '_' for c in model_name.upper()])
                    model_patterns.append(dot_preserved_pattern)
                    
                    # Version with dots preserved exactly
                    model_patterns.append(model_name.replace('-', '_').upper())
                
                # Check if the key contains any of our model patterns
                if any(pattern in model_part for pattern in model_patterns):
                    should_remove = True
                # Also check more flexible pattern matching
                elif model_name.lower().replace('-', '').replace('.', '') in model_part_lower.replace('_', ''):
                    should_remove = True
            
            if should_remove:
                model_keys_removed.append(key_name)
                logger.info(f"Removing env var: {key_name}")
                
                # Also remove from environment
                if key_name in os.environ:
                    del os.environ[key_name]
                    logger.info(f"Removed from environment: {key_name}")
            else:
                filtered_lines.append(line)
        
        # Write back to .env file
        with open(env_path, "w") as env_file:
            env_file.write(''.join(filtered_lines))
            if filtered_lines and not filtered_lines[-1].endswith('\n'):
                env_file.write('\n')
        
        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)
        
        # Also clean up any other related model environment variables
        try:
            from app.ai_models import clean_outdated_model_env_vars
            clean_outdated_model_env_vars()
        except Exception as e:
            logger.warning(f"Could not clean outdated model environment variables: {str(e)}")
        
        logger.info(f"Removed model {model_name} ({provider}). Keys removed: {model_keys_removed}")
        return JSONResponse(content={"message": f"Model {model_data.model_name} removed successfully"})
        
    except Exception as e:
        logger.error(f"Error removing model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search_articles")
async def search_articles(
    topic: Optional[str] = Query(None),
    category: Optional[List[str]] = Query(None),
    future_signal: Optional[List[str]] = Query(None),
    sentiment: Optional[List[str]] = Query(None),
    tags: Optional[str] = None,
    keyword: Optional[str] = None,
    dateRange: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    page: int = Query(1),
    per_page: int = Query(10),
    date_type: str = Query('publication'),  # Default to 'publication'
    session=Depends(verify_session)  # Add authentication
):
    pub_date_start, pub_date_end = None, None
    
    if dateRange:
        end_date = datetime.now()
        if dateRange != 'all' and dateRange != 'custom':
            start_date = end_date - timedelta(days=int(dateRange))
            pub_date_start = start_date.strftime('%Y-%m-%d')
            pub_date_end = end_date.strftime('%Y-%m-%d')
        elif dateRange == 'custom':
            pub_date_start = startDate
            pub_date_end = endDate

    # Determine which date field to use based on date_type
    date_field = 'publication_date' if date_type == 'publication' else 'submission_date'
    
    tags_list = tags.split(',') if tags else None
    articles, total_count = db.search_articles(
        topic=topic,  # Add topic parameter
        category=category,
        future_signal=future_signal,
        sentiment=sentiment,
        tags=tags_list,
        keyword=keyword,
        date_field=date_field,
        pub_date_start=pub_date_start,
        pub_date_end=pub_date_end,
        page=page,
        per_page=per_page
    )
    return JSONResponse(content={"articles": articles, "total_count": total_count, "page": page, "per_page": per_page})

@app.post("/api/generate_report")
async def generate_report(
    request: Request,
    report: Report = Depends(get_report)
):
    try:
        data = await request.json()
        article_ids = data.get('article_ids', [])
        custom_sections = data.get('custom_sections')  # Don't provide a default here
        
        logger.info(f"Received article IDs: {article_ids}")
        logger.info(f"Received custom sections: {custom_sections}")
        
        content = report.generate_report(article_ids, custom_sections)
        html = markdown.markdown(content)
        
        return JSONResponse(content={
            "content": content,
            "html": html
        })
        
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        logger.error(f"Request data: {data}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/api/save_report")
async def save_report(request: Request):
    data = await request.json()
    report_content = data.get('content', '')
    report_id = db.save_report(report_content)
    return JSONResponse(content={"report_id": report_id})

@app.post("/api/markdown_to_html")
async def markdown_to_html(request: Request):
    data = await request.json()
    markdown_text = data.get('markdown', '')
    html = markdown.markdown(markdown_text)
    return JSONResponse(content={"html": html})

@app.post("/api/save_article")
async def save_article(article: ArticleData):
    try:
        logger.info(f"Received article data: {article.dict()}")
        result = db.save_article(article.dict())
        return JSONResponse(content=result)
    except HTTPException as he:
        logger.error(f"HTTP error saving article: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error saving article: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/categories")
async def get_categories(topic: Optional[str] = None, research: Research = Depends(get_research), session=Depends(verify_session)):
    try:
        categories = await research.get_categories(topic)
        logger.info(f"Retrieved categories for topic {topic}: {categories}")
        return categories
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.get("/api/future_signals")
async def get_future_signals(topic: Optional[str] = None, research: Research = Depends(get_research), session=Depends(verify_session)):
    return await research.get_future_signals(topic)

@app.get("/api/sentiments")
async def get_sentiments(topic: Optional[str] = None, research: Research = Depends(get_research), session=Depends(verify_session)):
    return await research.get_sentiments(topic)

@app.get("/api/time_to_impact")
async def get_time_to_impact(topic: Optional[str] = None, research: Research = Depends(get_research)):
    return await research.get_time_to_impact(topic)

@app.get("/api/latest_articles")
async def get_latest_articles(
    topic_name: Optional[str] = None, 
    limit: Optional[int] = Query(10, ge=1),
    research: Research = Depends(get_research)
):
    try:
        logger.info(f"API request for latest articles - topic: {topic_name}, limit: {limit}")
        if topic_name:
            articles = research.get_recent_articles_by_topic(topic_name, limit=limit)
            logger.info(f"Retrieved {len(articles)} articles for topic {topic_name}")
        else:
            articles = await research.get_recent_articles(limit=limit)
            logger.info(f"Retrieved {len(articles)} articles (no topic filter)")
        return JSONResponse(content=articles)
    except Exception as e:
        logger.error(f"Error fetching latest articles: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching latest articles")

@app.get("/api/article")
async def get_article(
    uri: str,
    research: Research = Depends(get_research)
):
    try:
        # First try to get the article from the database
        article = db.get_article(uri)
        
        # If the article exists, return it
        if article:
            return JSONResponse(content=article)
        
        # If the article doesn't exist, try to fetch it
        logger.info(f"Article not found in database, attempting to fetch/scrape: {uri}")
        try:
            # First try to fetch from raw_articles
            raw_article = research.get_existing_article_content(uri)
            if raw_article:
                logger.info(f"Found raw article content for {uri}")
                return JSONResponse(
                    content={
                        "message": "Article found in raw content but not fully analyzed",
                        "content": raw_article,
                        "status": "raw_only"
                    }
                )
                
            # If not in raw_articles either, try to scrape it
            logger.info(f"No raw content found, attempting to scrape: {uri}")
            scraped_result = await research.scrape_article(uri)
            
            if "error" in scraped_result:
                error_msg = scraped_result.get("error", "Unknown error")
                logger.error(f"Error scraping article: {error_msg}")
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": error_msg,
                        "message": "Article not found and could not be scraped",
                        "details": scraped_result.get("content", "")
                    }
                )
            
            return JSONResponse(
                content={
                    "message": "Article scraped successfully but not yet analyzed",
                    "content": scraped_result,
                    "status": "scraped_only"
                }
            )
            
        except Exception as fetch_error:
            logger.error(f"Error fetching/scraping article: {str(fetch_error)}", exc_info=True)
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Article not found",
                    "message": f"Article not found and could not be fetched: {str(fetch_error)}"
                }
            )
    except Exception as e:
        logger.error(f"Error in get_article endpoint: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Server error",
                "message": f"An unexpected error occurred: {str(e)}"
            }
        )

@app.delete("/api/article")
async def delete_article(
    uri: str,
    research: Research = Depends(get_research)
):
    logger.info(f"Received delete request for article with URI: {uri}")
    try:
        success = research.delete_article(uri)
        if success:
            logger.info(f"Successfully deleted article with URI: {uri}")
            return JSONResponse(content={"message": "Article deleted successfully"})
        else:
            logger.warning(f"Article with URI {uri} not found or not deleted")
            raise HTTPException(status_code=404, detail="Article not found")
    except Exception as e:
        logger.error(f"Error deleting article: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug_settings")
async def debug_settings():
    try:
        settings_dict = {key: value for key, value in config.items() if not key.startswith('__')}
        return JSONResponse(content=settings_dict)
    except Exception as e:
        logger.error(f"Error in debug_settings: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(e)}"})

@app.get("/api/debug_articles")
async def debug_articles():
    try:
        db.facade.debug_articles()
        return JSONResponse(content={"article_count": len(articles), "articles": articles})
    except Exception as e:
        logger.error(f"Error in debug_articles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class DatabaseCreate(BaseModel):
    name: str

class DatabaseActivate(BaseModel):
    name: str

class ConfigItem(BaseModel):
    content: str

@app.get("/api/databases")
async def get_databases():
    try:
        databases = db.get_databases()
        return JSONResponse(content=databases)
    except Exception as e:
        logger.error(f"Error fetching databases: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/databases")
async def create_database(database: DatabaseCreate):
    try:
        new_database = db.create_database(database.name)
        return JSONResponse(content=new_database)
    except Exception as e:
        logger.error(f"Error creating database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/active-database")
async def set_active_database(database: DatabaseActivate):
    try:
        result = db.set_active_database(database.name)
        db.migrate_db()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error setting active database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/databases/{name}")
async def delete_database(name: str):
    try:
        # Get a fresh database instance
        database = Database()
        
        # Check if trying to delete active database
        active_db = database.get_active_database()
        if name == active_db:
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete active database. Please switch to another database first."
            )
            
        result = database.delete_database(name)
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Error deleting database: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/{item_name}")
async def get_config_item(item_name: str):
    try:
        content = db.get_config_item(item_name)
        return JSONResponse(content={"content": content})
    except Exception as e:
        logger.error(f"Error fetching config item: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/{item_name}")
async def save_config_item(item_name: str, item: ConfigItem):
    try:
        db.save_config_item(item_name, item.content)
        return JSONResponse(content={"message": f"{item_name} saved successfully"})
    except Exception as e:
        logger.error(f"Error saving config item: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database-info")
async def get_database_info():
    try:
        info = db.get_database_info()
        return JSONResponse(content=info)
    except Exception as e:
        logger.error(f"Error fetching database info: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/active-database")
async def get_active_database():
    try:
        active_db = Database.get_active_database()
        return JSONResponse(content={"name": active_db})
    except Exception as e:
        logger.error(f"Error getting active database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fetch_article_content")
async def fetch_article_content(uri: str, research: Research = Depends(get_research), save: bool = Query(True)):
    return await research.fetch_article_content(uri, save_with_topic=save)

@app.get("/api/get_existing_article_content")
async def get_existing_article_content(uri: str, research: Research = Depends(get_research)):
    return research.get_existing_article_content(uri)

@app.get("/api/scrape_article")
async def scrape_article(
    uri: str,
    research: Research = Depends(get_research)
):
    try:
        logger.info(f"Received scrape request for URI: {uri}")
        
        if not uri:
            logger.warning("Empty URI provided for scraping")
            return JSONResponse(
                status_code=400,
                content={"error": "Empty URL provided", "message": "Please provide a valid URL"}
            )
            
        if not uri.startswith(('http://', 'https://')):
            logger.warning(f"Invalid URI format: {uri}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid URL format", "message": "URL must start with http:// or https://"}
            )
            
        result = await research.scrape_article(uri)
        
        if "error" in result:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Error scraping article: {error_msg}")
            return JSONResponse(
                status_code=500,
                content={"error": error_msg, "message": result.get("content", "Failed to scrape article")}
            )
            
        return result
    except Exception as e:
        logger.error(f"Unexpected error in scrape_article endpoint: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Server error", "message": f"An unexpected error occurred: {str(e)}"}
        )

@app.get("/fetch_article_content")
async def fetch_article_content(url: str):
    try:
        result = await research.fetch_article_content(url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/driver_types")
async def get_driver_types(
    topic: Optional[str] = None,
    research: Research = Depends(get_research)
):
    return await research.get_driver_types(topic)

@app.get("/api/integrated_analysis")
async def get_integrated_analysis(timeframe: str = Query("all"), category: str = Query(None)):
    logger.info(f"Received request for integrated analysis. Timeframe: {timeframe}, Category: {category}")
    try:
        analyze_db = AnalyzeDB(db)
        data = analyze_db.get_integrated_analysis(timeframe, category)
        logger.info(f"Integrated analysis data: {json.dumps(data)}")
        if not data:
            logger.warning("No data returned from get_integrated_analysis")
            return JSONResponse(content={"error": "No data available"}, status_code=404)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in get_integrated_analysis: {str(e)}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/topics")
async def get_topics(session=Depends(verify_session)):
    """Get list of available topics."""
    # Load fresh config each time
    config = load_config()
    topics = [{"name": topic['name']} for topic in config['topics']]
    #logger.debug(f"Returning topics: {topics}")
    return topics

@app.get("/api/ai_models")
def get_ai_models():
    return get_available_models()  # Return models with configured API keys

@app.get("/api/ai_models_config")
async def get_ai_models_config():
    config = load_config()
    #logger.info(f"Full configuration: {config}")
    models = config.get("ai_models", [])
    #logger.info(f"AI models config: {models}")
    return {"ai_models": models}

@app.get("/api/available_models")
def get_available_models_endpoint():
    return get_available_models()  # Return models with configured API keys

@app.get("/api/debug_ai_config")
async def debug_ai_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'ai_config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return JSONResponse(content={"config": config, "path": config_path})
    except Exception as e:
        return JSONResponse(content={"error": str(e), "path": config_path}, status_code=500)

@app.get("/api/categories/{topic_name}")
async def get_categories_for_topic(topic_name: str):
    """Get categories for a specific topic."""
    try:
        # Import the necessary functions from config module
        from app.config.config import load_config, get_topic_config
        
        # Load the config and get topic-specific configuration
        config = load_config()
        topic_config = get_topic_config(config, topic_name)
        
        logger.debug(f"Retrieved categories for topic {topic_name}: {topic_config['categories']}")
        return JSONResponse(content=topic_config['categories'])
    except ValueError as e:
        logger.error(f"Error getting categories for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error getting categories for topic {topic_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/collect_articles")
async def collect_articles(
    source: str,
    query: str,
    topic: str,
    max_results: int = Query(10, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    language: str = Query("en", min_length=2, max_length=2),
    locale: Optional[str] = None,
    domains: Optional[str] = None,
    exclude_domains: Optional[str] = None,
    sort_by: Optional[str] = None,
    source_ids: Optional[str] = None,
    exclude_source_ids: Optional[str] = None,
    categories: Optional[str] = None,
    exclude_categories: Optional[str] = None,
    search_fields: Optional[str] = None,
    page: int = Query(1, ge=1),
    db: Database = Depends(get_database_instance)  # Add database dependency
):
    try:
        collector = CollectorFactory.get_collector(source, db)  # Pass db instance
        
        # Convert date strings to datetime objects if provided
        start_date_obj = datetime.fromisoformat(start_date) if start_date else None
        end_date_obj = datetime.fromisoformat(end_date) if end_date else None
        
        # Convert comma-separated strings to lists
        domains_list = domains.split(',') if domains else None
        exclude_domains_list = exclude_domains.split(',') if exclude_domains else None
        source_ids_list = source_ids.split(',') if source_ids else None
        exclude_source_ids_list = exclude_source_ids.split(',') if exclude_source_ids else None
        categories_list = categories.split(',') if categories else None
        exclude_categories_list = exclude_categories.split(',') if exclude_categories else None
        search_fields_list = search_fields.split(',') if search_fields else None
        
        articles = await collector.search_articles(
            query=query,
            topic=topic,
            max_results=max_results,
            start_date=start_date_obj,
            end_date=end_date_obj,
            language=language,
            locale=locale,
            domains=domains_list,
            exclude_domains=exclude_domains_list,
            sort_by=sort_by,
            source_ids=source_ids_list,
            exclude_source_ids=exclude_source_ids_list,
            categories=categories_list,
            exclude_categories=exclude_categories_list,
            search_fields=search_fields_list,
            page=page
        )
        
        # Get media bias data for articles
        try:
            # Import here to avoid circular imports
            from app.models.media_bias import MediaBias
            media_bias = MediaBias(db)
            
            # Add media bias data to each article
            for article in articles:
                source_url = article.get('url', '')
                source_name = article.get('source', '')
                
                # Try to get media bias data first from URL, then from source name
                bias_data = media_bias.get_bias_for_source(source_url)
                if not bias_data:
                    bias_data = media_bias.get_bias_for_source(source_name)
                    
                # Add bias data to article if found
                if bias_data:
                    article['bias'] = bias_data.get('bias', '')
                    article['factual_reporting'] = bias_data.get('factual_reporting', '')
                    article['mbfc_credibility_rating'] = bias_data.get('mbfc_credibility_rating', '')
                    article['bias_country'] = bias_data.get('country', '')
                    article['press_freedom'] = bias_data.get('press_freedom', '')
                    article['media_type'] = bias_data.get('media_type', '')
                    article['popularity'] = bias_data.get('popularity', '')
        except Exception as bias_error:
            logger.warning(f"Error enriching articles with media bias data: {str(bias_error)}")
            # Continue without media bias data
        
        return JSONResponse(content={
            "source": source,
            "query": query,
            "topic": topic,
            "article_count": len(articles),
            "articles": articles
        })
        
    except Exception as e:
        logger.error(f"Error collecting articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available_sources")
async def get_available_sources():
    """Get list of available article sources."""
    return JSONResponse(content=CollectorFactory.get_available_sources())

@app.get("/collect", response_class=HTMLResponse)
async def collect_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("collect.html", {
        "request": request,
        "session": request.session
    })

@app.post("/config/newsapi")
async def save_newsapi_config(config: NewsAPIConfig):
    """Save NewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        env_var_name = 'PROVIDER_NEWSAPI_KEY'

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Update or add the key
        new_line = f'{env_var_name}="{config.api_key}"\n'
        key_found = False

        for i, line in enumerate(lines):
            if line.startswith(f'{env_var_name}='):
                lines[i] = new_line
                key_found = True
                break

        if not key_found:
            lines.append(new_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update environment
        os.environ[env_var_name] = config.api_key
        
        # Use explicit JSONResponse
        return JSONResponse(
            status_code=200,
            content={"message": "NewsAPI configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving NewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config/newsapi")
async def get_newsapi_config():
    """Get NewsAPI configuration status."""
    try:
        # Force reload of environment variables
        load_dotenv(override=True)
        
        newsapi_key = os.getenv('PROVIDER_NEWSAPI_KEY')
        
        return JSONResponse(
            status_code=200,
            content={
                "configured": bool(newsapi_key),
                "message": "NewsAPI is configured" if newsapi_key else "NewsAPI is not configured"
            }
        )

    except Exception as e:
        logger.error(f"Error in get_newsapi_config: {str(e)}")
        logger.error(f"Error checking NewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/newsapi")
async def remove_newsapi_config():
    """Remove NewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()

        # Remove the primary and secondary API key lines
        lines = [line for line in lines if not (
            line.startswith('PROVIDER_NEWSAPI_KEY=') or 
            line.startswith('NEWSAPI_KEY=')
        )]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_NEWSAPI_KEY' in os.environ:
            del os.environ['PROVIDER_NEWSAPI_KEY']
        if 'NEWSAPI_KEY' in os.environ:
            del os.environ['NEWSAPI_KEY']

        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)

        return {"message": "NewsAPI configuration removed successfully"}

    except Exception as e:
        logger.error(f"Error removing NewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/create_topic", response_class=HTMLResponse)
async def create_topic_page(request: Request, session=Depends(verify_session)):
    config = load_config()
    
    # Gather examples from existing topics
    example_topics = [topic['name'] for topic in config['topics']]
    example_categories = list(set(cat for topic in config['topics'] for cat in topic['categories']))
    example_signals = list(set(signal for topic in config['topics'] for signal in topic['future_signals']))
    example_sentiments = list(set(sent for topic in config['topics'] for sent in topic['sentiment']))
    example_time_to_impact = list(set(time for topic in config['topics'] for time in topic['time_to_impact']))
    example_driver_types = list(set(driver for topic in config['topics'] for driver in topic['driver_types']))
    
    return templates.TemplateResponse("create_topic.html", {
        "request": request,
        "session": request.session,
        "example_topics": example_topics,
        "example_categories": example_categories,
        "example_signals": example_signals,
        "example_sentiments": example_sentiments,
        "example_time_to_impact": example_time_to_impact,
        "example_driver_types": example_driver_types
    })

@app.post("/api/create_topic")
async def create_topic(topic_data: dict):
    try:
        config = load_config()
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
        
        # Load existing config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check if updating existing topic
        existing_topic_index = next((i for i, topic in enumerate(config['topics']) 
                               if topic['name'] == topic_data['name']), None)
        
        # Save to database first
        db = Database()
        if existing_topic_index is not None:
            # Update in database
            db.update_topic(topic_data['name'])
            config['topics'][existing_topic_index] = topic_data
        else:
            # Create in database
            db.create_topic(topic_data['name'])
            # Add to config
            config['topics'].append(topic_data)
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # ADD THIS SECTION only - for news_monitoring.json update
        news_monitoring_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                           'config', 'news_monitoring.json')
        try:
            with open(news_monitoring_path, 'r') as f:
                news_monitoring = json.load(f)
                
            # Add the new topic to news_filters and paper_filters if it doesn't exist
            topic_name = topic_data['name']
            
            if topic_name not in news_monitoring['news_filters']:
                news_monitoring['news_filters'][topic_name] = f'"{topic_name}"'
                
            if topic_name not in news_monitoring['paper_filters']:
                news_monitoring['paper_filters'][topic_name] = f'"{topic_name}"'
                
            # Save the updated configuration
            with open(news_monitoring_path, 'w') as f:
                json.dump(news_monitoring, f, indent=2)
                
            logger.info(f"Added topic '{topic_name}' to news_monitoring.json")
            
        except Exception as e:
            logger.error(f"Error updating news_monitoring.json: {str(e)}")
            # Continue without failing if this part encounters issues
        
        return {"status": "success", "message": "Topic created successfully"}
        
    except Exception as e:
        logger.error(f"Error creating/updating topic: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating/updating topic: {str(e)}")

@app.get("/api/topic/{topic_name}")
async def get_topic_config(topic_name: str):
    """Get configuration for a specific topic."""
    try:
        config = load_config()
        topic_config = next((topic for topic in config['topics'] if topic['name'] == topic_name), None)
        if not topic_config:
            raise HTTPException(status_code=404, detail="Topic not found")
        return JSONResponse(content=topic_config)
    except Exception as e:
        logger.error(f"Error getting topic config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/providers")
async def get_providers():
    """Get all configured providers."""
    config = load_config()
    return JSONResponse(content={"providers": config.get("providers", [])})

@app.post("/api/research/bulk")
async def bulk_research_endpoint(
    request: Request,
    data: dict = Body(
        ...,
        examples=[{
            "urls": ["https://example.com/article1", "https://example.com/article2"],
            "topic": "AI and Machine Learning",
            "summary_type": "curious_ai",
            "model_name": "gpt-4",
            "summary_length": "medium",
            "summary_voice": "neutral"
        }]
    )
):
    try:
        bulk_research = BulkResearch(db)
        results = await bulk_research.analyze_bulk_urls(
            urls=data.get("urls", []),
            summary_type=data.get("summary_type", "curious_ai"),
            model_name=data.get("model_name", "gpt-4"),
            summary_length=data.get("summary_length", "medium"),
            summary_voice=data.get("summary_voice", "neutral"),
            topic=data.get("topic")
        )
        
        # Generate a unique batch ID
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return {"batch_id": batch_id, "results": results}
        
    except Exception as e:
        logger.error(f"Bulk research error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates")
async def get_templates():
    """Get all available report templates."""
    try:
        templates = report.get_all_templates()
        return JSONResponse(content={"templates": templates})
    except Exception as e:
        logger.error(f"Error getting templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates/{name}")
async def get_template(name: str):
    """Get a specific template by name."""
    try:
        template = report.get_template(name)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return JSONResponse(content={"content": template})
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/templates")
async def save_template(template_data: dict = Body(...)):
    """Save or update a template."""
    try:
        name = template_data.get("name")
        content = template_data.get("content")
        if not name or not content:
            raise HTTPException(status_code=400, detail="Name and content are required")
        
        success = report.save_template(name, content)
        return JSONResponse(content={"success": success})
    except Exception as e:
        logger.error(f"Error saving template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/markdown_to_html")
async def markdown_to_html(data: dict = Body(...)):
    """Convert markdown to HTML for preview."""
    try:
        markdown_text = data.get("markdown", "")
        html = markdown.markdown(markdown_text, extensions=['extra'])
        return JSONResponse(content={"html": html})
    except Exception as e:
        logger.error(f"Error converting markdown to HTML: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates/sections/{name}")
async def get_section_template(name: str):
    """Get a specific section template."""
    try:
        section_content = report.load_section_template(name)
        if not section_content:
            raise HTTPException(status_code=404, detail="Section template not found")
        return JSONResponse(content={"content": section_content})
    except Exception as e:
        logger.error(f"Error getting section template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/templates/save")
async def save_template(data: dict = Body(...)):
    """Save a new template with selected sections."""
    try:
        name = data.get("name")
        sections = data.get("sections", [])
        
        if not name:
            raise HTTPException(status_code=400, detail="Template name is required")
            
        success = report.save_template(name, sections)
        return JSONResponse(content={"success": success})
    except Exception as e:
        logger.error(f"Error saving template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates/{template_name}")
async def get_template(template_name: str):
    """Get a specific template content."""
    try:
        logger.debug(f"Fetching template: {template_name}")
        content = report.get_template(template_name)
        if not content:
            logger.warning(f"Template not found: {template_name}")
            raise HTTPException(status_code=404, detail="Template not found")
        logger.debug(f"Template content length: {len(content)}")
        return JSONResponse(content={"content": content})
    except Exception as e:
        logger.error(f"Error getting template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/topics/{topic_name}/articles")
async def get_topic_articles(
    topic_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    try:
        articles = db.get_recent_articles_by_topic(
            topic_name=topic_name,
            start_date=start_date,
            end_date=end_date,
            limit=1000  # Set a high limit for initial load
        )
        return {"articles": articles}
    except Exception as e:
        logger.error(f"Error fetching topic articles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/topics/{topic_name}/stats")
async def get_topic_stats(topic_name: str):
    try:
        # Get article count for topic
        article_count = db.get_article_count_by_topic(topic_name)
        
        # Get latest article date
        latest_article = db.get_latest_article_date_by_topic(topic_name)
        
        return {
            "articleCount": article_count,
            "latestArticle": latest_article
        }
    except Exception as e:
        logger.error(f"Error fetching topic stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/topic/{topic_id}")
async def delete_topic(topic_id: str, delete_articles: bool = Body(False)):
    try:
        db = Database()
        if delete_articles:
            result = db.delete_topic_with_articles(topic_id)
        else:
            result = db.delete_topic(topic_id)
            
        if not result:
            raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
            
        # Remove topic from config
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        # Find and remove topic
        config['topics'] = [topic for topic in config['topics'] if topic['name'] != topic_id]
        
        # Save updated config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # ADD THIS SECTION only - for news_monitoring.json update
        news_monitoring_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                           'config', 'news_monitoring.json')
        try:
            with open(news_monitoring_path, 'r') as f:
                news_monitoring = json.load(f)
                
            # Remove the topic from news_filters and paper_filters if it exists
            if topic_id in news_monitoring['news_filters']:
                del news_monitoring['news_filters'][topic_id]
                
            if topic_id in news_monitoring['paper_filters']:
                del news_monitoring['paper_filters'][topic_id]
                
            # Save the updated configuration
            with open(news_monitoring_path, 'w') as f:
                json.dump(news_monitoring, f, indent=2)
                
            logger.info(f"Removed topic '{topic_id}' from news_monitoring.json")
            
        except Exception as e:
            logger.error(f"Error updating news_monitoring.json when deleting topic: {str(e)}")
            # Continue without failing if this part encounters issues
        
        return {"success": True, "message": "Topic deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting topic: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting topic: {str(e)}")

@app.get("/database-editor", response_class=HTMLResponse)
async def database_editor_page(
    request: Request, 
    topic: Optional[str] = None,
    session=Depends(verify_session)
):
    try:
        # Get topics for the dropdown
        config = load_config()
        topics = [{"id": topic["name"], "name": topic["name"]} for topic in config["topics"]]
        
        # Log the topic parameter for debugging
        logger.debug(f"Database editor accessed with topic: {topic}")
        
        return templates.TemplateResponse("database_editor.html", {
            "request": request,
            "topics": topics,
            "selected_topic": topic,  # Pass the selected topic to the template
            "session": session
        })
    except Exception as e:
        logger.error(f"Database editor error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config/firecrawl")
async def get_firecrawl_config():
    """Get Firecrawl configuration status."""
    try:
        # Force reload of environment variables
        load_dotenv(override=True)
        
        firecrawl_key = os.getenv('PROVIDER_FIRECRAWL_KEY')
        
        return JSONResponse(
            status_code=200,
            content={
                "configured": bool(firecrawl_key),
                "message": "Firecrawl is configured" if firecrawl_key else "Firecrawl is not configured"
            }
        )

    except Exception as e:
        logger.error(f"Error in get_firecrawl_config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/firecrawl")
async def remove_firecrawl_config():
    """Remove Firecrawl configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()

        # Remove the primary and secondary API key lines
        lines = [line for line in lines if not (
            line.startswith('PROVIDER_FIRECRAWL_KEY=') or 
            line.startswith('FIRECRAWL_API_KEY=')
        )]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_FIRECRAWL_KEY' in os.environ:
            del os.environ['PROVIDER_FIRECRAWL_KEY']
        if 'FIRECRAWL_API_KEY' in os.environ:
            del os.environ['FIRECRAWL_API_KEY']

        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)

        return {"message": "Firecrawl configuration removed successfully"}

    except Exception as e:
        logger.error(f"Error removing Firecrawl configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update-news-query")
async def update_news_query(query: str = Body(...), topicId: str = Body(...)):
    try:
        set_news_query(query, topicId)
        return JSONResponse(content={"message": "News query updated successfully"})
    except Exception as e:
        logger.error(f"Error updating news query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update-paper-query")
async def update_paper_query(query: str = Body(...), topicId: str = Body(...)):
    try:
        config = load_news_monitoring()
        config["paper_filters"][topicId] = query
        save_news_monitoring(config)
        return JSONResponse(content={"message": "Paper query updated successfully"})
    except Exception as e:
        logger.error(f"Error updating paper query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update-keyword")
async def update_keyword(request: Request):
    data = await request.json()
    topic_id = data.get('topic_id')
    keyword_type = data.get('keyword_type')
    new_keyword = data.get('new_keyword')
    
    try:
        if keyword_type == 'news':
            set_news_query(topic_id, new_keyword)  # Modified to include topic_id
        elif keyword_type == 'paper':
            set_paper_query(topic_id, new_keyword)  # Modified to include topic_id
        else:
            raise ValueError(f"Invalid keyword type: {keyword_type}")
            
        # Clear any cached results for this topic
        # Add cache invalidation here if you have caching
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Error updating keyword: {str(e)}")
        return {"success": False, "error": str(e)}

@app.get("/change_password", response_class=HTMLResponse)
async def change_password_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse(
        "change_password.html",
        get_template_context(request, {"session": request.session})
    )

@app.post("/change_password")
async def change_password(
    request: Request,
    session=Depends(verify_session),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    try:
        username = request.session.get("user")
        user = db.get_user(username)
        
        if not verify_password(current_password, user['password']):
            return templates.TemplateResponse(
                "change_password.html",
                get_template_context(request, {
                    "session": request.session,
                    "error": "Current password is incorrect"
                })
            )
            
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "change_password.html",
                get_template_context(request, {
                    "session": request.session,
                    "error": "New passwords do not match"
                })
            )
            
        # Update password and first login status
        db.update_user_password(username, new_password)
        
        # Check if onboarding has been completed
        user = db.get_user(username)  # Refresh user data
        if not user.get('completed_onboarding'):
            return RedirectResponse(url="/onboarding", status_code=status.HTTP_302_FOUND)
        
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        return templates.TemplateResponse(
            "change_password.html",
            get_template_context(request, {
                "session": request.session,
                "error": "An error occurred while changing password"
            })
        )

@app.get("/api/topic-options/{topic}")
async def get_topic_options(topic: str):
    """Get all options (categories, future signals, sentiments, time to impact) for a topic."""
    try:
        analyze_db = AnalyzeDB(db)
        options = analyze_db.get_topic_options(topic)
        return JSONResponse(content=options)
    except Exception as e:
        logger.error(f"Error getting topic options: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/api/change-password")
async def api_change_password(request: Request):
    try:
        data = await request.json()
        username = request.session.get("user")
        if not username:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        user = db.get_user(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        if not verify_password(data["current_password"], user["password"]):
            return JSONResponse(
                status_code=400,
                content={"detail": "Current password is incorrect"}
            )
            
        # Update password
        success = db.update_user_password(username, data["new_password"])
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update password")
        
        # Check if onboarding has been completed
        user = db.get_user(username)  # Refresh user data
        if not user.get('completed_onboarding'):
            return JSONResponse(
                content={
                    "message": "Password updated successfully",
                    "redirect": "/onboarding"
                }
            )
            
        return JSONResponse(content={"message": "Password updated successfully"})
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while changing password")

@app.post("/api/databases/backup")
async def backup_database(backup_name: str = None):
    try:
        result = db.backup_database(backup_name)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error backing up database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/databases/reset")
async def reset_database():
    try:
        result = db.reset_database()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error resetting database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/firecrawl")
async def save_firecrawl_config(config: NewsAPIConfig):  # Reusing the same model since structure is identical
    """Save Firecrawl configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        env_var_name = 'PROVIDER_FIRECRAWL_KEY'

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Update or add the key
        new_line = f'{env_var_name}="{config.api_key}"\n'
        key_found = False

        for i, line in enumerate(lines):
            if line.startswith(f'{env_var_name}='):
                lines[i] = new_line
                key_found = True
                break

        if not key_found:
            lines.append(new_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update environment
        os.environ[env_var_name] = config.api_key
        
        return JSONResponse(
            status_code=200,
            content={"message": "Firecrawl configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving Firecrawl configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/keyword-monitor", response_class=HTMLResponse)
async def keyword_monitor_page(request: Request, session=Depends(verify_session)):
    try:
        rows = db.facade.get_monitor_page_keywords()

        # Group the results
        groups = {}
        for row in rows:
            group_id = row['id']
            if group_id not in groups:
                groups[group_id] = {
                    'id': group_id,
                    'name': row['name'],
                    'topic': row['topic'],
                    'keywords': []
                }
            if row['keyword_id']:
                groups[group_id]['keywords'].append({
                    'id': row['keyword_id'],
                    'keyword': row['keyword']
                })

        # Get topics from config instead of database
        config = load_config()
        topics = [{"id": topic["name"], "name": topic["name"]}
                 for topic in config.get("topics", [])]

        return templates.TemplateResponse(
            "keyword_monitor.html",
            get_template_context(request, {
                "keyword_groups": list(groups.values()),
                "topics": topics,
                "session": session,
                "current_page": "gather"
            })
        )
    except Exception as e:
        logger.error(f"Error in keyword monitor page: {str(e)}")
        logger.error(traceback.format_exc())  # Add this to get full traceback
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config/thenewsapi")
async def get_thenewsapi_config():
    """Get TheNewsAPI configuration status."""
    try:
        # Force reload of environment variables
        load_dotenv(override=True)
        
        thenewsapi_key = os.getenv('PROVIDER_THENEWSAPI_KEY')
        
        return JSONResponse(
            status_code=200,
            content={
                "configured": bool(thenewsapi_key),
                "message": "TheNewsAPI is configured" if thenewsapi_key else "TheNewsAPI is not configured"
            }
        )

    except Exception as e:
        logger.error(f"Error in get_thenewsapi_config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config/newsdata")
async def get_newsdata_config():
    """Get NewsData.io configuration status."""
    try:
        # Force reload of environment variables
        load_dotenv(override=True)
        
        newsdata_key = os.getenv('PROVIDER_NEWSDATA_API_KEY') or os.getenv('NEWSDATA_API_KEY')
        
        return JSONResponse(
            status_code=200,
            content={
                "configured": bool(newsdata_key),
                "message": "NewsData.io is configured" if newsdata_key else "NewsData.io is not configured"
            }
        )

    except Exception as e:
        logger.error(f"Error in get_newsdata_config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/thenewsapi")
async def save_thenewsapi_config(config: NewsAPIConfig):  # Reusing the same model since structure is identical
    """Save TheNewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        primary_env_var = 'PROVIDER_THENEWSAPI_KEY'
        secondary_env_var = 'THENEWSAPI_KEY'  # For backward compatibility

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Update or add the primary key
        primary_line = f'{primary_env_var}="{config.api_key}"\n'
        secondary_line = f'{secondary_env_var}="{config.api_key}"\n'
        
        primary_found = False
        secondary_found = False

        for i, line in enumerate(lines):
            if line.startswith(f'{primary_env_var}='):
                lines[i] = primary_line
                primary_found = True
            elif line.startswith(f'{secondary_env_var}='):
                lines[i] = secondary_line
                secondary_found = True

        if not primary_found:
            lines.append(primary_line)
        if not secondary_found:
            lines.append(secondary_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update environment variables
        os.environ[primary_env_var] = config.api_key
        os.environ[secondary_env_var] = config.api_key
        
        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)
        
        return JSONResponse(
            status_code=200,
            content={"message": "TheNewsAPI configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving TheNewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/newsdata")
async def save_newsdata_config(config: NewsAPIConfig):  # Reusing the same model since structure is identical
    """Save NewsData.io configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        primary_env_var = 'PROVIDER_NEWSDATA_API_KEY'
        secondary_env_var = 'NEWSDATA_API_KEY'  # For backward compatibility

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Update or add the primary key
        primary_line = f'{primary_env_var}="{config.api_key}"\n'
        secondary_line = f'{secondary_env_var}="{config.api_key}"\n'
        
        primary_found = False
        secondary_found = False

        for i, line in enumerate(lines):
            if line.startswith(f'{primary_env_var}='):
                lines[i] = primary_line
                primary_found = True
            elif line.startswith(f'{secondary_env_var}='):
                lines[i] = secondary_line
                secondary_found = True

        if not primary_found:
            lines.append(primary_line)
        if not secondary_found:
            lines.append(secondary_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update environment variables
        os.environ[primary_env_var] = config.api_key
        os.environ[secondary_env_var] = config.api_key
        
        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)
        
        return JSONResponse(
            status_code=200,
            content={"message": "NewsData.io configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving NewsData.io configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/thenewsapi")
async def remove_thenewsapi_config():
    """Remove TheNewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()

        # Remove the primary and secondary API key lines
        lines = [line for line in lines if not (
            line.startswith('PROVIDER_THENEWSAPI_KEY=') or 
            line.startswith('THENEWSAPI_KEY=')
        )]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_THENEWSAPI_KEY' in os.environ:
            del os.environ['PROVIDER_THENEWSAPI_KEY']
        if 'THENEWSAPI_KEY' in os.environ:
            del os.environ['THENEWSAPI_KEY']

        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)

        return {"message": "TheNewsAPI configuration removed successfully"}

    except Exception as e:
        logger.error(f"Error removing TheNewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/newsdata")
async def remove_newsdata_config():
    """Remove NewsData.io configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()

        # Remove the primary and secondary API key lines
        lines = [line for line in lines if not (
            line.startswith('PROVIDER_NEWSDATA_API_KEY=') or 
            line.startswith('NEWSDATA_API_KEY=')
        )]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_NEWSDATA_API_KEY' in os.environ:
            del os.environ['PROVIDER_NEWSDATA_API_KEY']
        if 'NEWSDATA_API_KEY' in os.environ:
            del os.environ['NEWSDATA_API_KEY']

        # Reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)

        return {"message": "NewsData.io configuration removed successfully"}

    except Exception as e:
        logger.error(f"Error removing NewsData.io configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this with the other endpoints
@app.get("/api/models")
async def get_models_endpoint(session=Depends(verify_session)):
    """Get list of available AI models."""
    try:
        models = get_available_models()  # Return configured models with API keys
        return JSONResponse(content=models)
    except Exception as e:
        logger.error(f"Error getting available models: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.middleware("http")
async def add_app_info(request: Request, call_next):
    """Add app info to all templates."""
    response = await call_next(request)
    
    # Check specifically for template responses
    if isinstance(response, _TemplateResponse):
        # Get fresh app info
        app_info = get_app_info()
        
        # Update context with app info
        if "app_info" not in response.context:
            response.context["app_info"] = app_info
    
    return response

@app.get("/api/app-info")
async def api_app_info():
    """Get application information."""
    return JSONResponse(content=get_app_info())

@app.post("/api/reload_environment")
async def reload_environment():
    """Force reload environment variables and reinitialize components that use them."""
    try:
        # Path to .env file
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        logger.info(f"Reloading environment from {env_path}")
        
        # Force reload environment variables
        load_dotenv(dotenv_path=env_path, override=True)
        
        # Reload AI model settings
        try:
            from app.ai_models import ensure_model_env_vars, get_available_models
            ensure_model_env_vars()
            available_models = get_available_models()
            logger.info(f"Reloaded AI model environment: {len(available_models)} models available")
        except Exception as e:
            logger.error(f"Error reloading AI models: {str(e)}")
        
        # Reload Research instance if it exists
        try:
            # Get the global research instance
            research_instance = get_research()
            
            # Use the new reload_environment method
            if research_instance:
                success = research_instance.reload_environment()
                if success:
                    logger.info("Research instance reloaded successfully")
                else:
                    logger.warning("Research instance reload did not complete successfully")
            else:
                logger.warning("No Research instance found to reload")
        except Exception as e:
            logger.error(f"Error reloading Research instance: {str(e)}")
        
        # Log which keys are present in the environment
        api_keys = {
            "NewsAPI": os.environ.get("PROVIDER_NEWSAPI_KEY") or os.environ.get("NEWSAPI_KEY"),
            "Firecrawl": os.environ.get("PROVIDER_FIRECRAWL_KEY") or os.environ.get("FIRECRAWL_API_KEY"),
            "TheNewsAPI": os.environ.get("PROVIDER_THENEWSAPI_KEY") or os.environ.get("THENEWSAPI_KEY"),
            "OpenAI": os.environ.get("OPENAI_API_KEY"),
            "Anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "HuggingFace": os.environ.get("HUGGINGFACE_API_KEY"),
            "Gemini": os.environ.get("GEMINI_API_KEY")
        }
        
        # Mask keys for logging
        masked_keys = {}
        for provider, key in api_keys.items():
            if key:
                masked_key = key[:4] + "..." + key[-4:] if len(key) > 8 else "[SET]"
                masked_keys[provider] = masked_key
            else:
                masked_keys[provider] = None
                
        logger.info(f"Environment reloaded. API keys present: {masked_keys}")
        
        return JSONResponse(
            content={
                "message": "Environment reloaded successfully",
                "keys_available": {provider: bool(key) for provider, key in api_keys.items()}
            }
        )
    except Exception as e:
        logger.error(f"Error reloading environment: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reloading environment: {str(e)}")

@app.get("/podcastdirector", response_class=HTMLResponse)
async def podcastdirector_page(request: Request, session=Depends(verify_session)):
    context = get_template_context(request)
    return templates.TemplateResponse("podcastdirector.html", context)

@app.get("/api/articles/search")
async def search_articles_for_podcast(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    date_type: str = Query('publication', description="Type of date to filter by"),
    topic: Optional[str] = None,
    category: Optional[List[str]] = Query(None),
    future_signal: Optional[List[str]] = Query(None),
    sentiment: Optional[List[str]] = Query(None),
    tags: Optional[str] = None,
    dateRange: Optional[str] = None,
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    db: Database = Depends(get_database_instance)
):
    try:
        pub_date_start, pub_date_end = None, None
        
        if dateRange:
            end_date = datetime.now()
            if dateRange != 'all' and dateRange != 'custom':
                start_date = end_date - timedelta(days=int(dateRange))
                pub_date_start = start_date.strftime('%Y-%m-%d')
                pub_date_end = end_date.strftime('%Y-%m-%d')
            elif dateRange == 'custom':
                pub_date_start = startDate
                pub_date_end = endDate

        # Determine which date field to use based on date_type
        date_field = 'publication_date' if date_type == 'publication' else 'submission_date'
        
        tags_list = tags.split(',') if tags else None
        articles, total_count = db.search_articles(
            topic=topic,
            category=category,
            future_signal=future_signal,
            sentiment=sentiment,
            tags=tags_list,
            keyword=q,  # Use the query parameter as keyword
            date_field=date_field,
            pub_date_start=pub_date_start,
            pub_date_end=pub_date_end,
            page=page,
            per_page=per_page
        )

        # Format the response for the podcast director
        formatted_articles = []
        for article in articles:
            formatted_articles.append({
                "uri": article.get('uri'),
                "title": article.get('title'),
                "summary": article.get('summary'),
                "sentiment": article.get('sentiment'),
                "time_to_impact": article.get('time_to_impact'),
                "driver_type": article.get('driver_type'),
                "publication_date": article.get('publication_date'),
                "news_source": article.get('news_source'),
                "url": article.get('url', article.get('uri')),
                "category": article.get('category'),
                "future_signal": article.get('future_signal')
            })
        
        return JSONResponse(content={
            "articles": formatted_articles,
            "total_count": total_count,
            "page": page,
            "per_page": per_page
        })
        
    except Exception as e:
        logger.error(f"Error searching articles for podcast: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/podcast/list")
async def list_podcasts(db: Database = Depends(get_database_instance)):
    """Get list of generated podcasts."""
    try:
        # Get all completed podcasts
        podcasts = []
        for row in db.facade.get_all_completed_podcasts():
            podcasts.append({
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "audio_url": row[3],
                "transcript": row[4]
            })

        return JSONResponse(content=podcasts)
            
    except Exception as e:
        logger.error(f"Error listing podcasts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/podcast/create")
async def create_podcast(
    data: dict = Body(...),
    db: Database = Depends(get_database_instance)
):
    """Create a new podcast using ElevenLabs API."""
    try:
        # Log raw request data
        logger.debug(f"Raw request data: {data}")

        # ------------------------------------------------------------------
        # ✨ Backwards‑compatibility shim
        # Front‑end pages like podcastdirector.html may still
        # send a simple list of URIs under `article_uris` instead of the newer
        # `articles` list (each item is an object with a `uri` field).
        # If `articles` is missing but `article_uris` exists, convert the list
        # so downstream logic remains unchanged.
        # ------------------------------------------------------------------
        if "articles" not in data and "article_uris" in data:
            # Ensure it is a list before processing
            uris = data.get("article_uris", []) or []
            # Only accept strings to avoid malformed payloads
            if isinstance(uris, list):
                data["articles"] = [{"uri": uri} for uri in uris if isinstance(uri, str)]
            else:
                logger.warning("`article_uris` field is not a list: %s", type(uris))
                data["articles"] = []
        # ------------------------------------------------------------------

        # Check for API key
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            logger.error("ELEVENLABS_API_KEY not found in environment variables")
            raise HTTPException(
                status_code=500,
                detail="ElevenLabs API key not configured. Please add ELEVENLABS_API_KEY to your environment variables."
            )
        logger.debug("Found ElevenLabs API key")

        # Log incoming data (excluding sensitive info)
        logger.info(f"Creating podcast with title: {data.get('title')}, mode: {data.get('mode')}")
        logger.info(f"Selected articles: {len(data.get('articles', []))}")
        logger.debug(f"Voice IDs - Host: {data.get('host_voice_id')}, Guest: {data.get('guest_voice_id')}")
        logger.debug(f"Quality preset: {data.get('quality_preset')}, Duration scale: {data.get('duration_scale')}")
        
        # Initialize ElevenLabs client
        try:
            client = ElevenLabs(api_key=api_key)
            logger.debug("Successfully initialized ElevenLabs client")
        except Exception as e:
            logger.error(f"Error initializing ElevenLabs client: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize ElevenLabs client: {str(e)}"
            )
        
        # Get articles from database using their URIs
        articles = []
        for article_data in data.get('articles', []):
            article = db.get_article(article_data['uri'])
            if article:
                articles.append(article)
            else:
                logger.warning(f"Article not found in database: {article_data['uri']}")

        if not articles:
            logger.error("No articles found in database")
            raise HTTPException(status_code=404, detail="Articles not found in database")
            
        # Generate podcast script
        try:
            script = generate_podcast_script(
                articles=articles,
                mode=data.get('mode', 'conversation'),
                title=data.get('title', 'AI News Update')
            )
            logger.debug(f"Generated script length: {len(script)} characters")
            logger.debug(f"Script preview: {script[:500]}...")
        except Exception as e:
            logger.error(f"Error generating podcast script: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate podcast script: {str(e)}"
            )
        
        # Create podcast based on mode
        try:
            if data.get('mode') == 'conversation':
                if not data.get('host_voice_id') or not data.get('guest_voice_id'):
                    raise ValueError("Missing voice IDs for conversation mode")
                    
                mode = BodyCreatePodcastV1StudioPodcastsPostMode_Conversation(
                    conversation=PodcastConversationModeData(
                        host_voice_id=data.get('host_voice_id'),
                        guest_voice_id=data.get('guest_voice_id'),
                    ),
                )
                logger.debug("Created conversation mode configuration")
            else:
                mode = BodyCreatePodcastV1StudioPodcastsPostMode_Bulletin()
                logger.debug("Created bulletin mode configuration")
            
            # ElevenLabs expects `source` to be a **list** of items where each
            # item is either a `PodcastTextSource` or `PodcastURLSource`.
            # Create podcast
            logger.debug("Sending request to ElevenLabs API...")
            response = client.studio.create_podcast(
                model_id="21m00Tcm4TlvDq8ikWAM",  # Default model ID
                mode=mode,
                source=PodcastTextSource(text=script),
                quality_preset=data.get('quality_preset', 'standard'),
                duration_scale=data.get('duration_scale', 'default')
            )
            
            logger.info("Successfully created podcast with ElevenLabs")
            logger.debug(f"ElevenLabs response: {response}")
            
        except Exception as e:
            logger.error(f"Error creating podcast with ElevenLabs: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create podcast with ElevenLabs: {str(e)}"
            )
        
        # Save podcast to database
        try:
            podcast_id = response.get('project', {}).get('project_id')
            if not podcast_id:
                raise ValueError("No podcast ID received from ElevenLabs")
                
            db.facade.create_podcast((
                    podcast_id,
                    data.get('title'),
                    json.dumps(data),
                    json.dumps([a['uri'] for a in articles])
                ))
            
            logger.info(f"Successfully saved podcast {podcast_id} to database")
            return JSONResponse(content={"podcast_id": podcast_id})
            
        except Exception as e:
            logger.error(f"Error saving podcast to database: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save podcast to database: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in create_podcast: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )

@app.get("/api/podcast/status/{podcast_id}")
async def get_podcast_status(
    podcast_id: str,
    db: Database = Depends(get_database_instance)
):
    """Get the status of a podcast."""
    try:
        # Initialize ElevenLabs client
        client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
        
        # Get podcast status from ElevenLabs
        response = client.studio.get_podcast(podcast_id)
        project = response.get('project', {})
        
        # Map ElevenLabs status to our status
        status_mapping = {
            'default': 'processing',
            'completed': 'completed',
            'failed': 'failed'
        }
        
        status = status_mapping.get(project.get('state', 'default'), 'processing')
        
        # If completed, get the audio URL and transcript
        audio_url = None
        transcript = None
        if status == 'completed':
            audio_url = project.get('audio_url')
            transcript = project.get('transcript')
            
            # Update database with completed status
            db.facade.update_podcast_status(('completed', audio_url, transcript, podcast_id))
        
        return JSONResponse(content={
            "status": status,
            "audio_url": audio_url,
            "transcript": transcript,
            "progress": project.get('creation_meta', {}).get('creation_progress', 0)
        })
        
    except Exception as e:
        logger.error(f"Error getting podcast status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def generate_podcast_script(articles: list, mode: str, title: str) -> str:
    """Generate a podcast script from articles."""
    script = f"Welcome to {title}!\n\n"
    
    if mode == 'conversation':
        # Generate conversational script
        for article in articles:
            script += f"Host: Let's discuss this interesting article titled '{article.get('title')}'.\n"
            script += f"Guest: Yes, this is fascinating. The article discusses {article.get('summary')}.\n"
            script += f"Host: What's particularly interesting is that {article.get('future_signal')}.\n"
            script += f"Guest: And the sentiment seems to be {article.get('sentiment')}.\n\n"
    else:
        # Generate bulletin style script
        for article in articles:
            script += f"Our next story: {article.get('title')}.\n"
            script += f"{article.get('summary')}\n"
            script += f"This development suggests that {article.get('future_signal')}.\n\n"
    
    script += "Thank you for listening!"
    return script

@app.get("/follow-flow", response_class=HTMLResponse)
async def follow_flow_route(request: Request, session=Depends(verify_session)):
    """Render the Follow the Flow Gantt chart page."""
    return templates.TemplateResponse(
        "follow_flow.html",
        get_template_context(request)
    )

@app.get("/api/flow_data")
async def get_flow_data(
    timeframe: str = Query("all", description="Timeframe in days or 'all' for no limit"),
    topic: Optional[str] = Query(None, description="Topic name to filter by"),
    limit: int = Query(500, ge=1, le=2000, description="Maximum number of articles to return"),
    db: Database = Depends(get_database_instance)
):
    """Return flow data for Gantt chart visualisation.

    Each record contains the source, category, sentiment, and driver_type for an article.
    """
    logger.info("Fetching flow data: timeframe=%s, topic=%s, limit=%s", timeframe, topic, limit)

    rows = db.facade.get_flow_data(topic, timeframe, limit)

    data = [
        {
            "source": row[0],
            "category": row[1],
            "sentiment": row[2],
            "driver_type": row[3],
            "submission_date": row[4],
        } for row in rows
    ]
    logger.info("Returning %d flow records", len(data))
    return JSONResponse(content=data)

@app.post("/config/dia")
async def save_dia_config(config: DiaAPIConfig):
    """Persist Dia API key and base URL to the .env file and runtime env."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
        # Filter out old DIA_* entries
        lines = [l for l in lines if not l.startswith("DIA_API_KEY=") and not l.startswith("DIA_TTS_URL=")]
        # Append new values
        lines.append(f"DIA_API_KEY={config.api_key}\n")
        if config.url:  # Only persist URL if provided
            lines.append(f"DIA_TTS_URL={config.url}\n")
        with open(env_path, 'w') as f:
            f.writelines(lines)
        # Update in-memory environment
        os.environ["DIA_API_KEY"] = config.api_key
        if config.url:
            os.environ["DIA_TTS_URL"] = config.url
        return JSONResponse(content={"message": "Dia API configuration saved successfully"})
    except Exception as e:
        logger.error(f"Error saving Dia config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config/dia")
async def get_dia_config():
    """Return Dia configuration status and current URL (if set)."""
    try:
        dia_key = os.getenv("DIA_API_KEY")
        dia_url = os.getenv("DIA_TTS_URL")
        key_present = bool(dia_key)
        return JSONResponse(
            content={
                "configured": key_present,
                "url": dia_url or "",
                "message": "Dia API is configured" if key_present else "Dia API is not configured"
            }
        )
    except Exception as e:
        logger.error(f"Error getting Dia config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/config/dia")
async def remove_dia_config():
    """Remove Dia configuration from .env and runtime environment."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            lines = [l for l in lines if not l.startswith("DIA_API_KEY=") and not l.startswith("DIA_TTS_URL=")]
            with open(env_path, 'w') as f:
                f.writelines(lines)
        # Clear runtime env vars
        os.environ.pop("DIA_API_KEY", None)
        os.environ.pop("DIA_TTS_URL", None)
        return JSONResponse(content={"message": "Dia API configuration removed"})
    except Exception as e:
        logger.error(f"Error removing Dia config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# ElevenLabs Provider Configuration Endpoints
# ---------------------------------------------------------------------------

# Re-use NewsAPIConfig schema since only `api_key` is required

ELEVEN_ENV_VAR = "ELEVENLABS_API_KEY"


@app.post("/config/elevenlabs")
async def save_elevenlabs_config(config: NewsAPIConfig):
    """Save ElevenLabs API key to .env and environment."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")

        # Read existing .env lines (if any)
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        new_line = f'{ELEVEN_ENV_VAR}="{config.api_key}"\n'
        key_found = False

        for idx, line in enumerate(lines):
            if line.startswith(f"{ELEVEN_ENV_VAR}="):
                lines[idx] = new_line
                key_found = True
                break

        if not key_found:
            lines.append(new_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update current process env so runtime picks up immediately
        os.environ[ELEVEN_ENV_VAR] = config.api_key

        return JSONResponse(
            status_code=200,
            content={
                "message": "ElevenLabs configuration saved successfully"
            },
        )

    except Exception as exc:
        logger.error("Error saving ElevenLabs configuration: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/config/elevenlabs")
async def get_elevenlabs_config():
    """Return whether ElevenLabs API key is configured."""
    try:
        # Reload .env to capture external edits
        load_dotenv(override=True)
        key_present = bool(os.getenv(ELEVEN_ENV_VAR))
        return JSONResponse(
            status_code=200,
            content={
                "configured": key_present,
                "message": (
                    "ElevenLabs is configured" if key_present else "ElevenLabs is not configured"
                ),
            },
        )
    except Exception as exc:
        logger.error("Error in get_elevenlabs_config: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/config/elevenlabs")
async def remove_elevenlabs_config():
    """Remove ElevenLabs API key from .env and environment."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")

        # Read lines
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        lines = [ln for ln in lines if not ln.startswith(f"{ELEVEN_ENV_VAR}=")]

        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from runtime env
        os.environ.pop(ELEVEN_ENV_VAR, None)

        load_dotenv(dotenv_path=env_path, override=True)

        return JSONResponse(
            status_code=200,
            content={
                "message": "ElevenLabs configuration removed successfully"
            },
        )

    except Exception as exc:
        logger.error("Error removing ElevenLabs configuration: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

class BlueskyConfig(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

    class Config:
        alias_generator = lambda string: string.lower()
        populate_by_name = True

@app.post("/config/bluesky")
async def save_bluesky_config(config: BlueskyConfig):
    """Save Bluesky configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        username_var = 'PROVIDER_BLUESKY_USERNAME'
        password_var = 'PROVIDER_BLUESKY_PASSWORD'

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Update or add the username
        username_line = f'{username_var}="{config.username}"\n'
        username_found = False

        # Update or add the password
        password_line = f'{password_var}="{config.password}"\n'
        password_found = False

        for i, line in enumerate(lines):
            if line.startswith(f'{username_var}='):
                lines[i] = username_line
                username_found = True
            elif line.startswith(f'{password_var}='):
                lines[i] = password_line
                password_found = True

        if not username_found:
            lines.append(username_line)
        if not password_found:
            lines.append(password_line)

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Update environment
        os.environ[username_var] = config.username
        os.environ[password_var] = config.password
        
        return JSONResponse(
            status_code=200,
            content={"message": "Bluesky configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving Bluesky configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/config/bluesky")
async def get_bluesky_config():
    """Get Bluesky configuration."""
    try:
        username = os.environ.get("PROVIDER_BLUESKY_USERNAME", "")
        password = os.environ.get("PROVIDER_BLUESKY_PASSWORD", "")
        configured = bool(username and password)
        
        # Return the username and whether password exists, but not the password itself
        return JSONResponse(
            status_code=200,
            content={
                "configured": configured,
                "username": username if configured else "",
                "has_password": bool(password),
                "message": "Bluesky is configured" if configured else "Bluesky is not configured"
            }
        )
    except Exception as e:
        logger.error(f"Error getting Bluesky configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/bluesky")
async def remove_bluesky_config():
    """Remove Bluesky configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        username_var = 'PROVIDER_BLUESKY_USERNAME'
        password_var = 'PROVIDER_BLUESKY_PASSWORD'

        # Read existing content
        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except FileNotFoundError:
            lines = []

        # Remove the config lines
        new_lines = [line for line in lines if not (line.startswith(f'{username_var}=') or 
                                                   line.startswith(f'{password_var}='))]
        
        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(new_lines)
            
        # Remove from environment
        if username_var in os.environ:
            del os.environ[username_var]
        if password_var in os.environ:
            del os.environ[password_var]
            
        return JSONResponse(
            status_code=200,
            content={"message": "Bluesky configuration removed successfully"}
        )
            
    except Exception as e:
        logger.error(f"Error removing Bluesky configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Streaming bulk research endpoint – returns NDJSON (one JSON per line)
# ---------------------------------------------------------------------------


@app.post("/api/bulk-research-stream")
async def bulk_research_stream(
    request: Request,
    research: Research = Depends(get_research),
    db: Database = Depends(get_database_instance),
):
    """Stream article analyses as NDJSON so the client can render incrementally."""
    try:
        data = await request.json()

        topic = data.get("topic")
        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")

        model_name = data.get("model_name")
        if not model_name:
            available_models = research.get_available_models()
            if not available_models:
                raise HTTPException(status_code=400, detail="No AI models available")
            model_name = available_models[0]["name"]

        try:
            summary_length = int(data.get("summary_length", 50))
        except ValueError:
            summary_length = 50

        # Get preserved metadata if available
        preserved_metadata = data.get("preservedMetadata", [])
        
        # Create lookup for preserved metadata
        metadata_lookup = {}
        for meta in preserved_metadata:
            if meta.get('url'):
                metadata_lookup[meta['url']] = meta

        bulk_research = BulkResearch(db, research=research)

        async def result_generator():
            async for item in bulk_research.analyze_bulk_urls_stream(
                urls=data.get("urls", []),
                summary_type=data.get("summary_type", "curious_ai"),
                model_name=model_name,
                summary_length=summary_length,
                summary_voice=data.get("summary_voice", "neutral"),
                topic=topic,
                preserved_metadata=metadata_lookup,
            ):
                # Apply preserved metadata if available
                if item.get('uri') in metadata_lookup:
                    preserved_data = metadata_lookup[item['uri']]
                    logger.info(f"Using preserved metadata for {item['uri']}: {preserved_data}")
                    
                    # Override with preserved metadata
                    if preserved_data.get('title'):
                        item['title'] = preserved_data['title']
                    if preserved_data.get('source'):
                        item['news_source'] = preserved_data['source']
                    if preserved_data.get('publication_date'):
                        item['publication_date'] = preserved_data['publication_date']
                
                yield (json.dumps(item) + "\n").encode("utf-8")
                # Give the event loop a chance to send the chunk immediately
                await asyncio.sleep(0)

        return StreamingResponse(result_generator(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"bulk-research-stream error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Check if SSL certificates exist
    cert_file = "cert.pem"
    key_file = "key.pem"
    use_ssl = os.path.exists(cert_file) and os.path.exists(key_file)
    
    if use_ssl:
        # Run with SSL if certificates are available
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert_file, keyfile=key_file)
        
        logger.info("Starting server with SSL on https://0.0.0.0:10000")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=10000,
            ssl_keyfile=key_file,
            ssl_certfile=cert_file,
            reload=True
        )
    else:
        # Run without SSL if certificates are not available
        logger.info("SSL certificates not found. Starting server without SSL on http://0.0.0.0:8010")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8010,
            reload=True
        )

# Insert near other config routes, e.g., after get_topics endpoint
@app.get("/api/config", response_class=JSONResponse)
async def api_get_full_config():
    """Return the full application configuration (topics, providers, etc.)."""
    try:
        cfg = load_config()
        return JSONResponse(content=cfg)
    except Exception as exc:
        logger.error("Error fetching full config: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

# Add a direct route for newsletter topics
@app.get("/api/newsletter/topics")
async def get_newsletter_topics():
    """Get available topics for newsletter compilation."""
    try:
        logger = logging.getLogger(__name__)
        logger.info("Newsletter topics endpoint called")
        
        # Try to identify calling client for debugging
        request = getattr(get_newsletter_topics, '_request', None)
        if request:
            client_info = f"Client: {request.client.host}:{request.client.port}" if hasattr(request, 'client') else "Unknown client"
            logger.info(f"Request from {client_info}")
            logger.info(f"Request headers: {dict(request.headers)}")
        
        # Debug: log path to config file
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
        logger.info(f"Loading config from: {config_path}")
        
        try:
            # Load config to get topics
            config = load_config()
            logger.info(f"Config loaded, keys: {list(config.keys())}")
            logger.info(f"Topics in config: {len(config.get('topics', []))}")
            
            # Extract topics
            topics = [topic["name"] for topic in config.get("topics", [])]
            logger.info(f"Extracted topic names: {topics}")
        except Exception as config_err:
            logger.error(f"Error loading topics from config: {str(config_err)}", exc_info=True)
            # Fallback to static list on config error
            topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
            logger.warning(f"Using fallback topics after config error: {topics}")
        
        # Fallback to static list if no topics found
        if not topics:
            logger.warning("No topics found in config, returning static list")
            topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        
        logger.info(f"Returning topics for newsletter: {topics}")
        return topics
        
    except Exception as e:
        logger.error(f"Error getting topics for newsletter: {str(e)}", exc_info=True)
        # Return static list on error
        static_topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        logger.info(f"Returning static topics due to error: {static_topics}")
        return static_topics

# Add a direct route for newsletter content types
@app.get("/api/newsletter/content_types")
async def get_newsletter_content_types():
    """Get available content types for newsletter compilation."""
    logger = logging.getLogger(__name__)
    logger.info("Newsletter content types endpoint called")
    
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
         "description": "List of key articles with links"},
        {"id": "latest_podcast", "name": "Latest Podcast", 
         "description": "Link to the latest podcast for the topic"}
    ]
    return content_types

# Add a very simple debug endpoint for testing topic loading
@app.get("/api/debug/topics")
async def debug_topics():
    """Simple debug endpoint that returns a static list of topics."""
    logger = logging.getLogger(__name__)
    logger.info("Debug topics endpoint called")
    topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
    return topics

@app.get("/submit-article", response_class=HTMLResponse)
async def submit_article_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse(
        "submit_article.html", 
        get_template_context(request)
    )

# Removed auspex-status route and test routes - no longer needed

# Route moved to app/routes/forecast_chart_routes.py to avoid duplication
