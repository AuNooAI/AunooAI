"""Topic management routes and endpoints."""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database
from app.security.session import verify_session
from app.config.config import load_config, get_news_query, get_paper_query
import json
import os
import logging
from typing import Optional
from pydantic import BaseModel

# Setup templates
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

class DeleteTopicRequest(BaseModel):
    delete_articles: bool = False

@router.delete("/topic/{topic_name}")
async def delete_topic(topic_name: str, request: Request, delete_request: DeleteTopicRequest = None, session=Depends(verify_session)):
    try:
        # Load config
        config = load_config()
        config_path = 'app/config/config.json'
        
        # Get topics list
        topics = config.get('topics', [])
        
        # Find and remove topic from config
        topic_found = False
        topics = [t for t in topics if t['name'] != topic_name]
        if len(topics) < len(config.get('topics', [])):
            topic_found = True
        
        # Delete from database
        db = Database()
        db_success = db.delete_topic(topic_name)
        
        if not topic_found and not db_success:
            logger.debug(f"Topic {topic_name} not found in config or database")
            raise HTTPException(status_code=404, detail=f"Topic {topic_name} not found in config or database")
        
        # Save updated config if topic was found
        if topic_found:
            logger.debug("Saving updated config file")
            config['topics'] = topics
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        # Clean up keyword groups associated with this topic
        keyword_groups_deleted = 0
        try:
            # Call the keyword monitoring API to delete groups
            from app.routes.keyword_monitor import delete_groups_by_topic
            result = await delete_groups_by_topic(topic_name, db)
            keyword_groups_deleted = result.get("groups_deleted", 0)
        except Exception as e:
            logger.error(f"Error deleting keyword groups for topic {topic_name}: {str(e)}")
        
        # Clean up articles if requested
        articles_deleted = 0
        if delete_request and delete_request.delete_articles:
            try:
                # Call the keyword monitoring API to delete articles
                from app.routes.keyword_monitor import delete_articles_by_topic
                result = await delete_articles_by_topic(topic_name, db)
                articles_deleted = result.get("articles_deleted", 0)
            except Exception as e:
                logger.error(f"Error deleting articles for topic {topic_name}: {str(e)}")
        
        return {
            "message": f"Topic {topic_name} deleted successfully",
            "config_deleted": topic_found,
            "database_deleted": db_success,
            "keyword_groups_deleted": keyword_groups_deleted,
            "articles_deleted": articles_deleted
        }
        
    except Exception as e:
        logger.error(f"Error deleting topic: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/create-topic", response_class=HTMLResponse)
async def create_topic_page(
    request: Request,
    topic: Optional[str] = None,
    session=Depends(verify_session)
):
    try:
        # Get example topics from config
        config = load_config()
        example_topics = [topic["name"] for topic in config.get("topics", [])]
        
        return templates.TemplateResponse("create_topic.html", {
            "request": request,
            "example_topics": example_topics,
            "session": session
        })
    except Exception as e:
        logger.error(f"Error loading create topic page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/topic/{topic_name}")
async def get_topic(topic_name: str, request: Request, session=Depends(verify_session)):
    try:
        # Load the config
        config = load_config()
        
        # Find the topic in the config
        topic_data = None
        for topic in config.get('topics', []):
            if topic['name'] == topic_name:
                topic_data = topic
                break
        
        if not topic_data:
            raise HTTPException(status_code=404, detail=f"Topic {topic_name} not found")
            
        # Get the queries
        news_query = get_news_query(topic_name)
        paper_query = get_paper_query(topic_name)
        
        # Make sure all fields are present
        response_data = {
            "name": topic_data.get("name", ""),
            "categories": topic_data.get("categories", []),
            "future_signals": topic_data.get("future_signals", []),
            "sentiment": topic_data.get("sentiment", []),
            "time_to_impact": topic_data.get("time_to_impact", []),
            "driver_types": topic_data.get("driver_types", []),
            "news_query": news_query,
            "paper_query": paper_query
        }
        
        return JSONResponse(content=response_data)
        
    except Exception as e:
        logger.error(f"Error getting topic data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 