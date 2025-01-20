from fastapi import FastAPI, HTTPException, Form, Request, Body, Query, Depends, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.collectors.newsapi_collector import NewsAPICollector
from app.collectors.arxiv_collector import ArxivCollector
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from app.database import Database, get_db
from app.research import Research
from app.analytics import Analytics
from app.report import Report
from app.analyze_db import AnalyzeDB 
from config.settings import config
from typing import Optional, List
from collections import Counter
from datetime import datetime, timedelta
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
from app.security.auth import User, get_current_active_user, verify_password
from app.routes import prompt_routes
from app.routes.web_routes import router as web_router
from app.routes.topic_routes import router as topic_router
from starlette.middleware.sessions import SessionMiddleware
from app.security.session import verify_session

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

# Initialize components
db = Database()
research = Research(db)
analytics = Analytics(db)
report = Report(db)
report_generator = Report(db)

#print("Config in main:", config)

# Add this after app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("FLASK_SECRET_KEY", "your-fallback-secret-key"),  # Using existing secret key from .env
)

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
    topic: str  # Add this line

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
        # Get user from database
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
        
        # Check if first login
        if user.get('is_first_login', True):
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
    db: Database = Depends(get_db)
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
    db: Database = Depends(get_db)
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
        print(f"Received article data: {article.dict()}")
        result = db.update_or_create_article(article.dict())
        print("Article saved successfully")
        return JSONResponse(content={"message": "Article saved successfully"})
    except Exception as e:
        print(f"Error saving article: {str(e)}")
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
        db.migrate_database()
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
    db.migrate_database()
    logger.info(f"Active database set to: {db.db_path}")

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
    end_date: Optional[str] = None
):
    """
    Collect articles from specified source.
    """
    try:
        collector = CollectorFactory.get_collector(source)
        
        # Convert date strings to datetime objects if provided
        start_date_obj = datetime.fromisoformat(start_date) if start_date else None
        end_date_obj = datetime.fromisoformat(end_date) if end_date else None
        
        articles = await collector.search_articles(
            query=query,
            topic=topic,
            max_results=max_results,
            start_date=start_date_obj,
            end_date=end_date_obj
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
async def dashboard(request: Request, session=Depends(verify_session)):
    try:
        db_info = db.get_database_info()
        config = load_config()
        topics = config.get('topics', [])

        # Prepare data for each topic
        topic_data = []
        for topic in topics:
            topic_id = topic['name']
            news_query = get_news_query(topic_id)
            paper_query = get_paper_query(topic_id)

            topic_data.append({
                "topic": topic_id,  # This is used as the ID in the frontend
                "name": topic_id,   # This is displayed as the title
                "news_query": news_query,
                "paper_query": paper_query
            })

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "topics": topic_data,
            "session": session
        })
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
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
async def database_editor_page(request: Request, session=Depends(verify_session)):
    try:
        # Get topics for the dropdown - using existing function referenced in:
        # main.py lines 805-825
        config = load_config()
        topics = [{"id": topic["name"], "name": topic["name"]} for topic in config["topics"]]
        
        return templates.TemplateResponse("database_editor.html", {
            "request": request,
            "topics": topics,
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
    count: int = Query(default=5, ge=1, le=20),  # Changed minimum to 1 to support single article fetch
    sortBy: str = Query(default="publishedAt", regex="^(relevancy|popularity|publishedAt)$"),
    offset: int = Query(default=0, ge=0)  # Added offset parameter
):
    try:
        news_query = get_news_query(topicId)
        paper_query = get_paper_query(topicId)

        latest_news = []
        latest_papers = []

        if news_query:
            news_collector = NewsAPICollector()
            latest_news = await news_collector.search_articles(
                query=news_query,
                topic=topicId,
                max_results=count + offset,  # Fetch extra articles to account for offset
                sort_by=sortBy
            )
            # Apply offset
            latest_news = latest_news[offset:offset + count]

        if paper_query:
            arxiv_collector = ArxivCollector()
            latest_papers = await arxiv_collector.search_articles(
                query=paper_query,
                topic=topicId,
                max_results=count + offset
            )
            # Apply offset
            latest_papers = latest_papers[offset:offset + count]

        latest_news_formatted = []
        for article in latest_news:
            try:
                raw_data = article.get('raw_data', {})
                formatted_article = {
                    "title": article.get('title', 'No title'),
                    "date": datetime.fromisoformat(article.get('published_date', datetime.now().isoformat())).strftime("%B %d, %Y %I:%M %p"),
                    "source": raw_data.get('source_name', 'Unknown'),
                    "summary": article.get('summary', 'No summary available'),
                    "url": article.get('url', '#'),
                    "author": article.get('authors', [])[0] if article.get('authors') else 'Unknown author',
                    "image_url": raw_data.get('url_to_image')
                }
                latest_news_formatted.append(formatted_article)
            except Exception as e:
                logger.error(f"Error formatting news article: {e}")
                logger.error(f"Problematic article data: {article}")
                continue

        latest_papers_formatted = []
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

        return JSONResponse(content={
            "latest_news": latest_news_formatted,
            "latest_papers": latest_papers_formatted
        })
    except Exception as e:
        logger.error(f"Error fetching latest news and papers: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail="Error fetching latest news and papers")

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
