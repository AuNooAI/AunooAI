from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from app.database import Database
from app.security.session import verify_session
import json
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

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