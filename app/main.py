"""Main FastAPI application file."""

from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.collectors.newsapi_collector import NewsAPICollector
from app.collectors.arxiv_collector import ArxivCollector
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from app.database import Database, get_database_instance
from app.research import Research
from app.analytics import Analytics
from app.report import Report
from app.analyze_db import AnalyzeDB 
from config.settings import config
from typing import Optional, List
from collections import Counter
from datetime import datetime, timedelta, timezone
from app.dependencies import get_research
import logging
import traceback
from pydantic import BaseModel, Field
import asyncio
import markdown
import json
import importlib
from app.ai_models import get_ai_model, get_available_models as ai_get_available_models
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
from starlette.middleware.sessions import SessionMiddleware
from app.security.session import verify_session
from app.routes.keyword_monitor import router as keyword_monitor_router, get_alerts
from app.tasks.keyword_monitor import run_keyword_monitor
import sqlite3
from app.routes import database  # Make sure this import exists
from app.routes.stats_routes import router as stats_router
from app.routes.chat_routes import router as chat_router
from app.routes.database import router as database_router

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Add custom filters
def datetime_filter(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    return value.strftime('%Y-%m-%d %H:%M:%S')

def timeago_filter(value):
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

# Register the filters
templates.env.filters["datetime"] = datetime_filter
templates.env.filters["timeago"] = timeago_filter

# Initialize components
db = Database()
research = Research(db)
analytics = Analytics(db)
report = Report(db)
report_generator = Report(db)

# Add this after app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("FLASK_SECRET_KEY", "your-fallback-secret-key"),  # Using existing secret key from .env
)

# Add this line to include the database routes
app.include_router(database.router)

# Add this with your other router includes
app.include_router(stats_router)

# Add this with the other router includes
app.include_router(chat_router)

# Add this near the other router includes
app.include_router(database_router)

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

@app.get("/", response_class=HTMLResponse)
async def root(request: Request, session=Depends(verify_session)):
    try:
        db_info = db.get_database_info()
        config = load_config()
        topics = [{"id": topic["name"], "name": topic["name"]} for topic in config["topics"]]
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "db_info": db_info,
            "topics": topics,
            "session": session
        })
    except Exception as e:
        logger.error(f"Index page error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "session": request.session  # Add session to template context
    })

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
        
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": request.session,
                "error": "An error occurred during login"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/research", response_class=HTMLResponse)
async def research_get(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("research.html", {
        "request": request,
        "session": request.session
    })

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
    research: Research = Depends(get_research)
):
    try:
        if not modelName:
            # If no model is available, return basic article information without analysis
            article_info = await research.fetch_article_content(articleUrl)
            return JSONResponse(content={
                "title": "Article title not available",
                "news_source": article_info.get("source", "Unknown"),
                "uri": articleUrl,
                "publication_date": article_info.get("publication_date", "Unknown"),
                "summary": "Analysis not available. No AI model selected.",
                "topic": selectedTopic
            })
        
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

@app.post("/bulk-research", response_class=HTMLResponse)
async def bulk_research_post(
    request: Request,
    session=Depends(verify_session),
    urlList: str = Form(...),
    topic: str = Form(...)
):
    return templates.TemplateResponse("bulk_research.html", {
        "request": request,
        "session": request.session,
        "prefilled_urls": urlList,
        "selected_topic": topic
    })

@app.post("/api/bulk-research")
async def bulk_research_post(
    data: dict,
    research: Research = Depends(get_research),
    db: Database = Depends(get_database_instance)
):
    urls = data.get('urls', [])
    summary_type = data.get('summaryType', 'curious_ai')
    model_name = data.get('modelName', 'gpt-3.5-turbo')
    summary_length = data.get('summaryLength', '50')
    summary_voice = data.get('summaryVoice', 'neutral')
    topic = data.get('topic')  # Get the topic from the request

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    bulk_research = BulkResearch(db)
    results = await bulk_research.analyze_bulk_urls(
        urls=urls,
        summary_type=summary_type,
        model_name=model_name,
        summary_length=summary_length,
        summary_voice=summary_voice,
        topic=topic  # Pass the topic to the analysis function
    )

    return JSONResponse(content=results)

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
    return templates.TemplateResponse("analytics.html", {"request": request, "session": request.session})

@app.get("/api/analytics")
def get_analytics_data(
    timeframe: str = Query(...),
    category: str = Query(None),  # Make category optional
    topic: str = Query(...)
):
    logger.info(f"Received analytics request: timeframe={timeframe}, category={category}, topic={topic}")
    try:
        data = analytics.get_analytics_data(timeframe=timeframe, category=category, topic=topic)
        logger.info("Analytics data retrieved successfully")
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in get_analytics_data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/report", response_class=HTMLResponse)
async def report_route(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("report.html", {"request": request, "session": request.session})

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    models = ai_get_available_models()
    return templates.TemplateResponse("config.html", {"request": request, "models": models})

@app.post("/config/add_model")
async def add_model(model_data: AddModelRequest):
    """Add model configuration to .env file only."""
    try:
        logger.info(f"Received request to add model: {model_data.dict()}")
        
        if not model_data.model_name or not model_data.provider or not model_data.api_key:
            raise HTTPException(status_code=400, detail="All fields are required")

        # Create environment variable name
        env_var_name = f"{model_data.provider.upper()}_API_KEY_{model_data.model_name.replace('-', '_').upper()}"
        
        # Update .env file
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if not os.path.exists(env_path):
            open(env_path, 'a').close()

        try:
            with open(env_path, "r") as env_file:
                lines = env_file.readlines()
        except Exception as e:
            lines = []

        # Update or add the key
        new_line = f'{env_var_name}="{model_data.api_key}"\n'
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
        os.environ[env_var_name] = model_data.api_key
        
        return JSONResponse(content={"message": f"Model {model_data.model_name} added successfully"})

    except Exception as e:
        logger.error(f"Error adding model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/config/remove_model")
async def remove_model(model_data: RemoveModelRequest):
    env_var_name = f"{model_data.provider.upper()}_API_KEY_{model_data.model_name.replace('-', '_').upper()}"
    if env_var_name in os.environ:
        del os.environ[env_var_name]
    
    # Update .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    with open(env_path, "r") as env_file:
        lines = env_file.readlines()
    
    # Remove the specified model and any empty lines
    with open(env_path, "w") as env_file:
        env_file.writelines(line for line in lines if not line.startswith(env_var_name) and line.strip())
    
    # Reload environment variables
    load_dotenv(override=True)
    
    return JSONResponse(content={"message": f"Model {model_data.model_name} removed successfully"})

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
async def generate_report(request: Request):
    try:
        data = await request.json()
        article_ids = data.get('article_ids', [])
        custom_sections = data.get('custom_sections')  # Don't provide a default here
        
        logger.info(f"Received article IDs: {article_ids}")
        logger.info(f"Received custom sections: {custom_sections}")
        
        report_generator = Report(db)
        content = report_generator.generate_report(article_ids, custom_sections)
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
        result = await db.save_article(article.dict())  # Use the async save_article method
        return JSONResponse(content=result)
    except HTTPException as he:
        logger.error(f"HTTP error saving article: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error saving article: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/categories")
async def get_categories(topic: Optional[str] = None, research: Research = Depends(get_research)):
    try:
        categories = await research.get_categories(topic)
        logger.info(f"Retrieved categories for topic {topic}: {categories}")
        return categories
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.get("/api/future_signals")
async def get_future_signals(topic: Optional[str] = None, research: Research = Depends(get_research)):
    return await research.get_future_signals(topic)

@app.get("/api/sentiments")
async def get_sentiments(topic: Optional[str] = None, research: Research = Depends(get_research)):
    return await research.get_sentiments(topic)

@app.get("/api/time_to_impact")
async def get_time_to_impact(topic: Optional[str] = None, research: Research = Depends(get_research)):
    return await research.get_time_to_impact(topic)

@app.get("/api/latest_articles")
async def get_latest_articles(
    topic_name: Optional[str] = None, 
    limit: Optional[int] = Query(10, ge=1)
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
async def get_article(uri: str):
    try:
        article = db.get_article(uri)
        if article is None:
            raise HTTPException(status_code=404, detail="Article not found")
        return JSONResponse(content=article)
    except Exception as e:
        logger.error(f"Error fetching article: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/article")
async def delete_article(uri: str):
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
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles")
            articles = cursor.fetchall()
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
        result = db.delete_database(name)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error deleting database: {str(e)}", exc_info=True)
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

@app.on_event("startup")
def startup_event():
    global db
    db = Database()
    db.migrate_db()
    logger.info(f"Active database set to: {db.db_path}")
    asyncio.create_task(run_keyword_monitor())

@app.get("/api/fetch_article_content")
async def fetch_article_content(uri: str):
    return await research.fetch_article_content(uri)

@app.get("/api/get_existing_article_content")
async def get_existing_article_content(uri: str):
    return research.get_existing_article_content(uri)

@app.get("/api/scrape_article")
async def scrape_article(uri: str):
    return await research.scrape_article(uri)

@app.get("/fetch_article_content")
async def fetch_article_content(url: str):
    try:
        result = await research.fetch_article_content(url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/driver_types")
async def get_driver_types(topic: Optional[str] = None, research: Research = Depends(get_research)):
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
async def get_topics():
    """Get list of available topics."""
    # Load fresh config each time
    config = load_config()
    topics = [{"name": topic['name']} for topic in config['topics']]
    #logger.debug(f"Returning topics: {topics}")
    return topics

@app.get("/api/ai_models")
def get_ai_models():
    return ai_get_available_models()  # Use the function from ai_models.py

@app.get("/api/ai_models_config")
async def get_ai_models_config():
    config = load_config()
    #logger.info(f"Full configuration: {config}")
    models = config.get("ai_models", [])
    #logger.info(f"AI models config: {models}")
    return {"ai_models": models}

@app.get("/api/available_models")
def get_available_models():
    return ai_get_available_models()  # Use the function from ai_models.py

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

        # Remove the NEWSAPI_KEY line
        lines = [line for line in lines if not line.startswith('PROVIDER_NEWSAPI_KEY=')]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_NEWSAPI_KEY' in os.environ:
            del os.environ['PROVIDER_NEWSAPI_KEY']

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
        from app.config.config import load_config
        config = load_config()  # Load using the same method
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
        
        # Load existing config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check if updating existing topic
        existing_topic_index = next((i for i, topic in enumerate(config['topics']) 
                                   if topic['name'] == topic_data['name']), None)
        if existing_topic_index is not None:
            config['topics'][existing_topic_index] = topic_data
        else:
            config['topics'].append(topic_data)
        
        # Save updated config
        with open(config_path, 'w+') as f:
            f.seek(0)
            json.dump(config, f, indent=2)
            f.truncate()
        
        return {"message": "Topic saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        example={
            "urls": ["https://example.com/article1", "https://example.com/article2"],
            "topic": "AI and Machine Learning",
            "summary_type": "curious_ai",
            "model_name": "gpt-4",
            "summary_length": "medium",
            "summary_voice": "neutral"
        }
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

@app.post("/api/generate_report")
async def generate_report(request: Request):
    try:
        data = await request.json()
        article_ids = data.get('article_ids', [])
        custom_sections = data.get('custom_sections')  # Don't provide a default here
        
        logger.info(f"Received article IDs: {article_ids}")
        logger.info(f"Received custom sections: {custom_sections}")
        
        report_generator = Report(db)
        content = report_generator.generate_report(article_ids, custom_sections)
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

@app.get("/api/report_templates")
async def get_report_templates():
    try:
        with open('app/config/templates.json', 'r') as f:
            templates = json.load(f)
        return templates['report_sections']
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report_templates/{section}")
async def update_report_template(section: str, template: dict = Body(...)):
    try:
        with open('app/config/templates.json', 'r') as f:
            templates = json.load(f)
        
        templates['report_sections'][section] = template['content']
        
        with open('app/config/templates.json', 'w') as f:
            json.dump(templates, f, indent=2)
            
        return {"message": "Template updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Database = Depends(get_database_instance),
    session=Depends(verify_session)  # Add session verification
):
    try:
        # Get rate limit status
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT requests_today, last_error 
                FROM keyword_monitor_status 
                WHERE id = 1
            """)
            row = cursor.fetchone()
            requests_today = row[0] if row else 0
            last_error = row[1] if row and len(row) > 1 else None
            
            # Check if rate limited
            is_rate_limited = (
                last_error and 
                ("Rate limit exceeded" in last_error or "limit reached" in last_error)
            )

        # Get topics from config
        config = load_config()
        topics = []
        for topic in config.get('topics', []):
            topic_id = topic['name']
            news_query = get_news_query(topic_id)
            paper_query = get_paper_query(topic_id)
            
            topics.append({
                "topic": topic_id,  # Used as ID in frontend
                "name": topic_id,   # Displayed as title
                "news_query": news_query,
                "paper_query": paper_query
            })

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "topics": topics,
                "last_error": last_error if is_rate_limited else None,
                "is_rate_limited": is_rate_limited,
                "requests_today": requests_today,
                "session": session  # Add session to template context
            }
        )

    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
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

@app.delete("/api/topics/{topic_name}")
async def delete_topic(topic_name: str):
    try:
        success = db.delete_topic(topic_name)
        if success:
            return {"message": "Topic deleted successfully"}
        raise HTTPException(status_code=404, detail="Topic not found")
    except Exception as e:
        logger.error(f"Error deleting topic: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

        # Remove the FIRECRAWL_KEY line
        lines = [line for line in lines if not line.startswith('PROVIDER_FIRECRAWL_KEY=')]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_FIRECRAWL_KEY' in os.environ:
            del os.environ['PROVIDER_FIRECRAWL_KEY']

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

@app.get("/api/latest-news-and-papers")
async def get_latest_news_and_papers(
    topicId: str,
    count: int = 5,
    sortBy: str = "publishedAt",
    db: Database = Depends(get_database_instance)
):
    try:
        # Initialize collectors with database instance
        news_collector = NewsAPICollector(db)
        arxiv_collector = ArxivCollector()
        
        # Get news query for topic
        news_query = get_news_query(topicId)
        if not news_query:
            news_query = topicId
            
        # Get papers query for topic    
        papers_query = get_paper_query(topicId)
        if not papers_query:
            papers_query = topicId

        latest_news_formatted = []
        try:
            # Get news articles
            latest_news = await news_collector.search_articles(
                query=news_query,
                max_results=count,
                sort_by=sortBy
            )
            
            # Format news articles
            for article in latest_news:
                try:
                    raw_data = article.get('raw_data', {})
                    formatted_article = {
                        "title": article.get('title', 'No title'),
                        "date": datetime.fromisoformat(article.get('published_date', datetime.now().isoformat())).strftime("%B %d, %Y %I:%M %p"),
                        "source": article.get('news_source', 'Unknown'),
                        "summary": article.get('summary', 'No summary available'),
                        "url": article.get('url', '#'),
                        "author": raw_data.get('author', 'Unknown author'),
                        "image_url": raw_data.get('url_to_image')
                    }
                    latest_news_formatted.append(formatted_article)
                except Exception as e:
                    logger.error(f"Error formatting news article: {e}")
                    continue
                    
        except ValueError as e:
            if "Rate limit exceeded" in str(e) or "limit reached" in str(e):
                # Log the rate limit but continue with papers
                logger.warning(f"NewsAPI rate limit reached: {str(e)}")
            else:
                raise

        # Get papers (continue even if news failed)
        latest_papers_formatted = []
        try:
            latest_papers = await arxiv_collector.search_articles(
                query=papers_query,
                topic=topicId,  # Add the missing topic parameter
                max_results=count
            )
            
            # Format papers
            for article in latest_papers:
                try:
                    formatted_article = {
                        "title": article.get('title', 'No title'),
                        "date": datetime.fromisoformat(article.get('published_date', datetime.now().isoformat())).strftime("%B %d, %Y"),
                        "authors": article.get('authors', []),
                        "summary": article.get('summary', 'No summary available'),
                        "url": article.get('url', '#')
                    }
                    latest_papers_formatted.append(formatted_article)
                except Exception as e:
                    logger.error(f"Error formatting paper article: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching papers: {str(e)}")

        return {
            "latest_news": latest_news_formatted,
            "latest_papers": latest_papers_formatted
        }

    except Exception as e:
        logger.error(f"Error fetching latest news and papers: {str(e)}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
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
        {"request": request, "session": request.session}
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
                {
                    "request": request,
                    "session": request.session,
                    "error": "Current password is incorrect"
                }
            )
            
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "change_password.html",
                {
                    "request": request,
                    "session": request.session,
                    "error": "New passwords do not match"
                }
            )
            
        # Update password and first login status
        db.update_user_password(username, new_password)
        
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        return templates.TemplateResponse(
            "change_password.html",
            {
                "request": request,
                "session": request.session,
                "error": "An error occurred while changing password"
            }
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
        with db.get_connection() as conn:
            # First, make the connection row factory return dictionaries
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get keyword groups and their keywords
            cursor.execute("""
                SELECT kg.id, kg.name, kg.topic, 
                       mk.id as keyword_id, 
                       mk.keyword
                FROM keyword_groups kg
                LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                ORDER BY kg.name, mk.keyword
            """)
            rows = cursor.fetchall()
            
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
                {
                    "request": request,
                    "keyword_groups": list(groups.values()),
                    "topics": topics,
                    "session": session
                }
            )
    except Exception as e:
        logger.error(f"Error in keyword monitor page: {str(e)}")
        logger.error(traceback.format_exc())  # Add this to get full traceback
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/keyword-alerts", response_class=HTMLResponse)
async def keyword_alerts_page(request: Request, session=Depends(verify_session)):
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Define status colors mapping
            status_colors = {
                'NEW': 'primary',
                'Exploding': 'danger',
                'Surging': 'warning',
                'Growing': 'success',
                'Stable': 'secondary',
                'Declining': 'info',
                'No Data': 'secondary'
            }
            
            # Get the last check time
            cursor.execute("""
                SELECT 
                    MAX(last_checked) as last_check_time,
                    (SELECT check_interval FROM keyword_monitor_settings WHERE id = 1) as check_interval,
                    (SELECT interval_unit FROM keyword_monitor_settings WHERE id = 1) as interval_unit,
                    (SELECT last_error FROM keyword_monitor_status WHERE id = 1) as last_error,
                    (SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1) as is_enabled
                FROM monitored_keywords
            """)
            row = cursor.fetchone()
            last_check = row[0]
            check_interval = row[1] if row[1] else 15
            interval_unit = row[2] if row[2] else 60  # Default to minutes
            last_error = row[3]
            is_enabled = row[4] if row[4] is not None else True  # Default to enabled

            # Format the display interval
            if interval_unit == 3600:  # Hours
                display_interval = f"{check_interval} hour{'s' if check_interval != 1 else ''}"
            elif interval_unit == 86400:  # Days
                display_interval = f"{check_interval} day{'s' if check_interval != 1 else ''}"
            else:  # Minutes
                display_interval = f"{check_interval} minute{'s' if check_interval != 1 else ''}"

            # Calculate next check time
            now = datetime.now()
            if last_check:
                last_check_time = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                next_check = last_check_time + timedelta(seconds=check_interval * interval_unit)
                
                # Only show next check time if it's in the future
                if next_check > now:
                    next_check_time = next_check.isoformat()
                else:
                    next_check_time = now.isoformat()
            else:
                last_check_time = None
                next_check_time = now.isoformat()

            # Format the last_check_time for display
            display_last_check = last_check_time.strftime('%Y-%m-%d %H:%M:%S') if last_check_time else None

            # Get all groups with their alerts and status
            cursor.execute("""
                WITH alert_counts AS (
                    SELECT 
                        kg.id as group_id,
                        COUNT(DISTINCT ka.id) as unread_count
                    FROM keyword_groups kg
                    LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                    LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id AND ka.is_read = 0
                    GROUP BY kg.id
                )
                SELECT 
                    kg.id,
                    kg.name,
                    kg.topic,
                    ac.unread_count,
                    (
                        SELECT GROUP_CONCAT(keyword, '||')
                        FROM monitored_keywords
                        WHERE group_id = kg.id
                    ) as keywords
                FROM keyword_groups kg
                LEFT JOIN alert_counts ac ON kg.id = ac.group_id
                ORDER BY ac.unread_count DESC, kg.name
            """)
            
            groups_data = cursor.fetchall()
            
            # Get alerts for each group
            groups = []
            for group_id, name, topic, unread_count, keywords in groups_data:
                cursor.execute("""
                    SELECT 
                        ka.id,
                        ka.detected_at,
                        ka.article_uri,
                        a.title,
                        a.uri as url,
                        a.news_source,
                        a.publication_date,
                        a.summary,
                        mk.keyword as matched_keyword
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN articles a ON ka.article_uri = a.uri
                    WHERE mk.group_id = ? AND ka.is_read = 0
                    ORDER BY ka.detected_at DESC
                """, (group_id,))
                
                alerts = [
                    {
                        'id': alert_id,
                        'detected_at': detected_at,
                        'article': {
                            'uri': article_uri,
                            'title': title,
                            'url': url,
                            'source': news_source,
                            'publication_date': publication_date,
                            'summary': summary
                        },
                        'matched_keyword': matched_keyword
                    }
                    for alert_id, detected_at, article_uri, title, url, news_source, 
                        publication_date, summary, matched_keyword in cursor.fetchall()
                ]
                
                growth_status = 'No Data'
                if unread_count:
                    growth_status = 'NEW'  # We'll make it more sophisticated later
                
                groups.append({
                    'id': group_id,
                    'name': name,
                    'topic': topic,
                    'alerts': alerts,
                    'keywords': keywords.split('||') if keywords else [],
                    'growth_status': growth_status,
                    'unread_count': unread_count or 0
                })
            
            return templates.TemplateResponse(
                "keyword_alerts.html",
                {
                    "request": request,
                    "groups": groups,
                    "last_check_time": display_last_check,
                    "display_interval": display_interval,
                    "next_check_time": next_check_time,
                    "last_error": last_error,
                    "session": session,
                    "now": now.isoformat(),
                    "is_enabled": is_enabled,
                    "status_colors": status_colors  # Add this line
                }
            )
            
    except Exception as e:
        logger.error(f"Error loading keyword alerts page: {str(e)}\n{traceback.format_exc()}")
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

@app.post("/config/thenewsapi")
async def save_thenewsapi_config(config: NewsAPIConfig):  # Reusing the same model since structure is identical
    """Save TheNewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        env_var_name = 'PROVIDER_THENEWSAPI_KEY'

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
            content={"message": "TheNewsAPI configuration saved successfully"}
        )

    except Exception as e:
        logger.error(f"Error saving TheNewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/config/thenewsapi")
async def remove_thenewsapi_config():
    """Remove TheNewsAPI configuration."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        
        # Read existing content
        with open(env_path, "r") as env_file:
            lines = env_file.readlines()

        # Remove the THENEWSAPI_KEY line
        lines = [line for line in lines if not line.startswith('PROVIDER_THENEWSAPI_KEY=')]

        # Write back to .env
        with open(env_path, "w") as env_file:
            env_file.writelines(lines)

        # Remove from current environment
        if 'PROVIDER_THENEWSAPI_KEY' in os.environ:
            del os.environ['PROVIDER_THENEWSAPI_KEY']

        return {"message": "TheNewsAPI configuration removed successfully"}

    except Exception as e:
        logger.error(f"Error removing TheNewsAPI configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Add this with the other endpoints
@app.get("/api/models")
async def get_available_models(session=Depends(verify_session)):
    """Get list of available AI models."""
    try:
        models = ai_get_available_models()
        return JSONResponse(content=models)
    except Exception as e:
        logger.error(f"Error getting available models: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain('cert.pem', keyfile='key.pem')
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8010,
        ssl_keyfile="key.pem",
        ssl_certfile="cert.pem",
        reload=True
    )
