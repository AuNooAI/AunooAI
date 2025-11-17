"""Topic management routes and endpoints."""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database
from app.database_query_facade import DatabaseQueryFacade
from app.security.session import verify_session
from app.config.config import load_config, get_news_query, get_paper_query
import json
import os
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

# Setup templates
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

class DeleteTopicRequest(BaseModel):
    delete_articles: bool = False

@router.get("/topics")
async def get_topics_unified(
    with_articles: bool = False,
    include_config: bool = True
) -> List[Dict[str, Any]]:
    """
    Unified topic endpoint that combines config.json and database information.

    Args:
        with_articles: If True, only return topics that have articles in the database
        include_config: If True, include full topic configuration (categories, signals, etc.)
                       If False, return only name and description

    Returns:
        List of topic objects with requested information
    """
    try:
        # Load topics from config.json (source of truth for definitions)
        config = load_config()
        all_topics = config.get('topics', [])

        # If filtering to topics with articles, get database topics
        if with_articles:
            db = Database()
            facade = DatabaseQueryFacade(db, logger)
            db_topics_info = facade.get_topics_with_article_counts()
            db_topic_names = set(db_topics_info.keys())

            # Filter to only topics that exist in database
            all_topics = [t for t in all_topics if t['name'] in db_topic_names]

            # Enrich with database statistics
            for topic in all_topics:
                topic_name = topic['name']
                if topic_name in db_topics_info:
                    topic['article_count'] = db_topics_info[topic_name]['article_count']
                    topic['last_article_date'] = db_topics_info[topic_name]['last_article_date']

        # If not including full config, return minimal information
        if not include_config:
            return [
                {
                    "name": t['name'],
                    "description": t.get('description', ''),
                    **({"article_count": t.get('article_count', 0)} if with_articles else {}),
                    **({"last_article_date": t.get('last_article_date')} if with_articles else {})
                }
                for t in all_topics
            ]

        # Return full topic configuration
        return all_topics

    except Exception as e:
        logger.error(f"Error getting topics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
        keyword_cleanup_result = {}
        try:
            # Call the keyword monitoring API to delete groups
            from app.routes.keyword_monitor import delete_groups_by_topic
            keyword_cleanup_result = await delete_groups_by_topic(topic_name, db)
            logger.info(f"Keyword cleanup results: {keyword_cleanup_result}")
        except Exception as e:
            logger.error(f"Error deleting keyword groups for topic {topic_name}: {str(e)}")
        
        # Clean up articles if requested
        article_cleanup_result = {}
        if delete_request and delete_request.delete_articles:
            try:
                # Call the keyword monitoring API to delete articles
                from app.routes.keyword_monitor import delete_articles_by_topic
                article_cleanup_result = await delete_articles_by_topic(topic_name, db)
                logger.info(f"Article cleanup results: {article_cleanup_result}")
            except Exception as e:
                logger.error(f"Error deleting articles for topic {topic_name}: {str(e)}")
        
        # Try to clean up news monitoring settings if possible
        try:
            news_monitoring_path = os.path.join('app', 'config', 'news_monitoring.json')
            if os.path.exists(news_monitoring_path):
                with open(news_monitoring_path, 'r') as f:
                    news_monitoring = json.load(f)
                    
                # Remove the topic from news_filters and paper_filters if it exists
                news_filters_updated = False
                if 'news_filters' in news_monitoring and topic_name in news_monitoring['news_filters']:
                    del news_monitoring['news_filters'][topic_name]
                    news_filters_updated = True
                    
                paper_filters_updated = False
                if 'paper_filters' in news_monitoring and topic_name in news_monitoring['paper_filters']:
                    del news_monitoring['paper_filters'][topic_name]
                    paper_filters_updated = True
                    
                # Save the updated configuration
                if news_filters_updated or paper_filters_updated:
                    with open(news_monitoring_path, 'w') as f:
                        json.dump(news_monitoring, f, indent=2)
                    logger.info(f"Removed topic '{topic_name}' from news_monitoring.json")
        except Exception as e:
            logger.error(f"Error updating news_monitoring.json when deleting topic: {str(e)}")
        
        return {
            "message": f"Topic {topic_name} deleted successfully",
            "config_deleted": topic_found,
            "database_deleted": db_success,
            "keyword_groups_deleted": keyword_cleanup_result.get("groups_deleted", 0),
            "keywords_deleted": keyword_cleanup_result.get("keywords_deleted", 0),
            "keyword_alerts_deleted": keyword_cleanup_result.get("alerts_deleted", 0),
            "articles_deleted": article_cleanup_result.get("articles_deleted", 0),
            "article_alerts_deleted": article_cleanup_result.get("alerts_deleted", 0)
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