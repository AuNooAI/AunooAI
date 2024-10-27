from fastapi import FastAPI, HTTPException, Form, Request, Body, Query, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
from app.ai_models import get_ai_model, get_available_models as ai_get_available_models
from app.bulk_research import BulkResearch
from app.config.config import load_config, get_topic_config  # Add get_topic_config import
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Initialize components
db = Database()
research = Research(db)
print(f"Database initialized and updated in main.py: {db.db_path}")
logging.debug(f"Created Research instance with categories: {research.CATEGORIES}")
analytics = Analytics(db)
report = Report(db)
report_generator = Report(db)

print("Config in main:", config)

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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    print("Index route accessed")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/research", response_class=HTMLResponse)
async def research_get(request: Request):
    return templates.TemplateResponse("research.html", {"request": request})

@app.post("/research")
async def research_post(
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
async def bulk_research_get(request: Request):
    return templates.TemplateResponse("bulk_research.html", {"request": request})

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
    bulk_research = BulkResearch(db, research)
    results = await bulk_research.save_bulk_articles(articles)
    return JSONResponse(content=results)

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_route(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})

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
async def report_route(request: Request):
    return templates.TemplateResponse("report.html", {"request": request})

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    models = ai_get_available_models()
    return templates.TemplateResponse("config.html", {"request": request, "models": models})

@app.post("/config/add_model")
async def add_model(model_data: AddModelRequest):
    try:
        logger.info(f"Received request to add model: {model_data.dict()}")
        logger.info(f"Model name: {model_data.model_name}")
        logger.info(f"Provider: {model_data.provider}")
        logger.info(f"API key length: {len(model_data.api_key) if model_data.api_key else 0}")
        
        # Check for missing fields
        missing_fields = []
        if not model_data.model_name:
            missing_fields.append("model_name")
        if not model_data.provider:
            missing_fields.append("provider")
        if not model_data.api_key:
            missing_fields.append("api_key")
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return JSONResponse(content={"error": error_msg}, status_code=422)

        # Check if the model exists in the configuration
        available_models = ai_get_available_models()
        logger.info(f"Available models: {available_models}")
        
        # Remove the provider from the model name if it's included
        model_name = model_data.model_name.split(' (')[0]
        
        model_exists = any(model['name'] == model_name and model['provider'] == model_data.provider for model in available_models)
        
        if not model_exists:
            # Instead of returning an error, we'll add the model to the configuration
            logger.info(f"Model {model_name} ({model_data.provider}) not found in configuration. Adding it.")
            config_path = os.path.join(os.path.dirname(__file__), 'config', 'ai_config.json')
            with open(config_path, 'r+') as f:
                config = json.load(f)
                config['ai_models'].append({"name": model_name, "provider": model_data.provider})
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()

        env_var_name = f"{model_data.provider.upper()}_API_KEY_{model_name.replace('-', '_').upper()}"
        
        # Update .env file
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if not os.path.exists(env_path):
            error_msg = ".env file not found"
            logger.error(error_msg)
            return JSONResponse(content={"error": error_msg}, status_code=500)

        logger.info(f"Updating .env file at: {env_path}")
        
        try:
            with open(env_path, "a") as env_file:
                env_file.write(f'\n{env_var_name}="{model_data.api_key}"\n')
            logger.info(f"Successfully updated .env file")
        except IOError as e:
            error_msg = f"Error writing to .env file: {str(e)}"
            logger.error(error_msg)
            return JSONResponse(content={"error": error_msg}, status_code=500)

        # Update the environment variable in the current process
        os.environ[env_var_name] = model_data.api_key
        
        # Reload environment variables
        load_dotenv(override=True)
        
        logger.info(f"Model {model_name} added successfully")
        return JSONResponse(content={"message": f"Model {model_name} added successfully"}, status_code=200)
    except Exception as e:
        logger.error(f"Error adding model: {str(e)}", exc_info=True)
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Error args: {e.args}")
        logger.error(f"Request data: {model_data.dict()}")
        return JSONResponse(content={"error": f"Unexpected error: {str(e)}"}, status_code=500)

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
    per_page: int = Query(10)
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

    tags_list = tags.split(',') if tags else None
    articles, total_count = db.search_articles(
        topic=topic,  # Add topic parameter
        category=category,
        future_signal=future_signal,
        sentiment=sentiment,
        tags=tags_list,
        keyword=keyword,
        pub_date_start=pub_date_start,
        pub_date_end=pub_date_end,
        page=page,
        per_page=per_page
    )
    return JSONResponse(content={"articles": articles, "total_count": total_count, "page": page, "per_page": per_page})

@app.post("/api/generate_report")
async def generate_report(request: Request):
    data = await request.json()
    article_ids = data.get('article_ids', [])
    print(f"Received article IDs: {article_ids}")
    report_content = report_generator.generate_report(article_ids)
    return JSONResponse(content={"content": report_content})

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
async def get_categories(research: Research = Depends(get_research)):
    logger.debug("Entering get_categories endpoint")
    try:
        categories = await research.get_categories()
        logger.info(f"Retrieved categories: {categories}")
        return categories
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching categories: {str(e)}")

@app.get("/api/future_signals")
async def get_future_signals():
    return JSONResponse(content=config.get('future_signals', []))

@app.get("/api/sentiments")
async def get_sentiments():
    return JSONResponse(content=config.get('sentiment', []))

@app.get("/api/time_to_impact")
async def get_time_to_impact():
    return JSONResponse(content=config.get('time_to_impact', []))

@app.get("/api/latest_articles")
async def get_latest_articles(topic_name: Optional[str] = None):
    try:
        if topic_name:
            articles = research.get_recent_articles_by_topic(topic_name)
        else:
            articles = await research.get_recent_articles()
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
    print(f"Active database set to: {db.db_path}")

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
async def get_driver_types(research: Research = Depends(get_research)):
    return await research.get_driver_types()

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
    topics = research.get_topics()
    logger.debug(f"Returning topics: {topics}")  # Add debug logging
    return [{"name": topic} for topic in topics]  # Return list of objects with name property

@app.get("/api/ai_models")
def get_ai_models():
    return ai_get_available_models()  # Use the function from ai_models.py

@app.get("/api/ai_models_config")
async def get_ai_models_config():
    config = load_config()
    logger.info(f"Full configuration: {config}")
    models = config.get("ai_models", [])
    logger.info(f"AI models config: {models}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

