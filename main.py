from fastapi import FastAPI, HTTPException, Form, Request, Body, Query, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from database import Database, get_db
from research import Research
from analytics import Analytics
from report import Report
from analyze_db import AnalyzeDB 
from config.settings import config
from typing import Optional, List
from collections import Counter
from datetime import datetime, timedelta
from dependencies import get_research
import logging
import traceback
from pydantic import BaseModel, Field
import asyncio
import markdown
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Initialize components
db = Database()
print(f"Database initialized and updated in main.py: {db.db_path}")
research = Research(db)
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
    research: Research = Depends(get_research)
):
    try:
        result = await research.analyze_article(
            uri=articleUrl,
            article_text=articleContent,
            summary_length=summaryLength,
            summary_voice=summaryVoice,
            summary_type=summaryType
        )
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in research_post: {str(e)}", exc_info=True)
        raise HTTPException(status_code=422, detail=str(e))

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_route(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})

@app.get("/api/analytics")
def get_analytics_data(timeframe: str = Query(...), category: str = Query(...)):
    logger.info(f"Received analytics request: timeframe={timeframe}, category={category}")
    try:
        data = analytics.get_analytics_data(timeframe, category)
        logger.info("Analytics data retrieved successfully")
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Error in get_analytics_data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/report", response_class=HTMLResponse)
async def report_route(request: Request):
    return templates.TemplateResponse("report.html", {"request": request})

@app.get("/config", response_class=HTMLResponse)
async def config_route(request: Request):
    return templates.TemplateResponse("config.html", {"request": request})

@app.get("/api/search_articles")
async def search_articles(
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
        category, future_signal, sentiment, tags_list, keyword,
        pub_date_start, pub_date_end, page, per_page
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
    categories = await research.get_categories()
    logging.debug(f"Returning categories: {categories}")
    return categories

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
async def get_latest_articles():
    logger.debug("Received request for latest articles")
    try:
        articles = db.get_recent_articles(limit=10)
        logger.debug(f"Retrieved {len(articles)} articles")
        return JSONResponse(content=articles)
    except Exception as e:
        logger.error(f"Error fetching latest articles: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
