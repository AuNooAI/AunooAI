"""Main FastAPI application file - Restored with architectural improvements."""

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, Request, Form, Query, Body, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
import json
import asyncio
import markdown
import sqlite3
import shutil

# Import our architectural improvements
from app.core.app_factory import create_app

# Import all the dependencies from the original main.py
from app.database import Database, get_database_instance
from app.research import Research
from app.analytics import Analytics
from app.report import Report
from app.analyze_db import AnalyzeDB
from app.config.settings import config
from app.dependencies import get_research, get_analytics, get_report
from app.ai_models import get_ai_model, get_available_models as ai_get_available_models
from app.bulk_research import BulkResearch
from app.config.config import load_config, get_topic_config, get_news_query, set_news_query, get_paper_query, set_paper_query, load_news_monitoring, save_news_monitoring
from app.collectors.collector_factory import CollectorFactory
from app.collectors.newsapi_collector import NewsAPICollector
from app.collectors.arxiv_collector import ArxivCollector
from app.collectors.bluesky_collector import BlueskyCollector
from app.security.auth import User, get_current_active_user, verify_password, get_password_hash
from app.security.session import verify_session
from app.tasks.keyword_monitor import run_keyword_monitor
from app.utils.app_info import get_app_info

logger = logging.getLogger(__name__)

# Create the FastAPI app using our factory pattern
app = create_app()

# Get templates from app state
templates = app.state.templates

# Pydantic models - copy all from original
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
    tags: List[str]
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
    api_key: str = Field(..., min_length=1, alias="api_key")
    url: Optional[str] = Field(None, alias="url")

    class Config:
        alias_generator = lambda s: s.lower()
        populate_by_name = True

class DatabaseCreate(BaseModel):
    name: str

class DatabaseActivate(BaseModel):
    name: str

class ConfigItem(BaseModel):
    content: str

# Helper function
def get_template_context(request: Request, additional_context: dict = None) -> dict:
    """Create a base template context with common variables."""
    app_info = get_app_info()
    
    context = {
        "request": request,
        "app_info": app_info,
        "session": request.session if hasattr(request, "session") else {}
    }
    
    if additional_context:
        context.update(additional_context)
    
    return context


# NOTE: Most routes will be handled by the registered routers in app_factory
# We only need to add routes that are NOT in the existing route modules

# Home page (if not in web_routes)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session=Depends(verify_session)):
    """Main dashboard page."""
    try:
        db = app.state.db
        
        # Get database info
        db_info = db.get_database_info()
        
        # Get topic info from config and database
        config_topics = config.get('topics', [])
        
        db_topics = {}
        try:
            topic_data = db.get_topic_statistics()
            db_topics = {topic['name']: topic for topic in topic_data}
        except Exception as e:
            logger.warning(f"Error fetching topic statistics: {str(e)}")
        
        active_topics = []
        for topic_config in config_topics:
            topic_name = topic_config.get('name', 'Unknown')
            topic_info = {
                "name": topic_name,
                "article_count": 0,
                "last_article_date": None
            }
            
            if topic_name in db_topics:
                topic_info["article_count"] = db_topics[topic_name]["article_count"]
                topic_info["last_article_date"] = db_topics[topic_name]["last_article_date"]
            
            active_topics.append(topic_info)
        
        context = get_template_context(request, {
            "db_info": db_info,
            "active_topics": active_topics,
            "session": session
        })
        
        return templates.TemplateResponse("index.html", context)
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: This main.py now uses the app_factory pattern with proper router registration
# All other routes should be handled by the registered router modules
# If specific routes are still missing, they should be added to the appropriate router modules