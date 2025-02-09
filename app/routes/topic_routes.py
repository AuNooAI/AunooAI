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

# Setup templates
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger(__name__)

router = APIRouter()

@router.delete("/topic/{topic_name}")
async def delete_topic(topic_name: str, request: Request, session=Depends(verify_session)):
    try:
        logger.debug(f"Starting delete_topic for {topic_name}")
        logger.debug(f"Session object type: {type(session)}")
        
        # Create database instance
        database = Database()
        logger.debug(f"Created database instance of type: {type(database)}")
        
        # 1. Delete from config file
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.json')
        logger.debug(f"Config path: {config_path}")
        
        # Load existing config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Find and remove the topic
        topics = config.get('topics', [])
        topic_found = False
        
        for i, topic in enumerate(topics):
            if topic['name'] == topic_name:
                topics.pop(i)
                topic_found = True
                logger.debug(f"Topic {topic_name} found and removed from config")
                break
        
        # 2. Delete from database regardless of config file status
        # This ensures we clean up any orphaned data
        logger.debug("Attempting to delete topic from database")
        db_success = database.delete_topic(topic_name)
        logger.debug(f"Database deletion result: {db_success}")
        
        if not topic_found and not db_success:
            # If topic wasn't found in either config or database
            logger.debug(f"Topic {topic_name} not found in config or database")
            raise HTTPException(status_code=404, detail=f"Topic {topic_name} not found in config or database")
        
        # If topic was found in config, save the updated config
        if topic_found:
            logger.debug("Saving updated config file")
            config['topics'] = topics
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        
        # Return success if topic was deleted from either config or database
        logger.debug("Delete operation completed successfully")
        return JSONResponse(content={
            "message": f"Topic {topic_name} deleted successfully",
            "config_deleted": topic_found,
            "database_deleted": db_success
        })
        
    except Exception as e:
        logger.error(f"Error deleting topic: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Error details: {str(e.__dict__)}")
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