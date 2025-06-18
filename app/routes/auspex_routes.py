from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import json
import logging
from datetime import datetime

from app.services.auspex_service import get_auspex_service
from app.security.session import verify_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auspex", tags=["Auspex"])

# Request/Response Models
class SuggestRequest(BaseModel):
    kind: str = Field(...)
    scenario_name: str = Field(...)
    scenario_description: str | None = None

class ChatSessionRequest(BaseModel):
    topic: str = Field(..., description="Topic for the chat session")
    title: str | None = Field(None, description="Optional title for the chat")

class ChatMessageRequest(BaseModel):
    chat_id: int = Field(..., description="Chat session ID")
    message: str = Field(..., description="User message")
    model: str | None = Field(None, description="Model to use for response")
    limit: int | None = Field(50, description="Number of articles to analyze (auto-sized based on context)")
    tools_config: dict | None = Field(None, description="Individual tool configuration settings")

class PromptRequest(BaseModel):
    name: str = Field(..., description="Unique prompt name")
    title: str = Field(..., description="Display title")
    content: str = Field(..., description="Prompt content")
    description: str | None = Field(None, description="Optional description")

class PromptUpdateRequest(BaseModel):
    title: str | None = Field(None, description="Updated title")
    content: str | None = Field(None, description="Updated content")
    description: str | None = Field(None, description="Updated description")

# Legacy endpoint for backward compatibility
@router.post("/block-options", status_code=status.HTTP_200_OK)
async def suggest_block_options(req: SuggestRequest, session=Depends(verify_session)):
    """Return list of option suggestions for a building-block."""
    auspex = get_auspex_service()
    return {
        "options": auspex.suggest_options(req.kind, req.scenario_name, req.scenario_description),
    }

# Chat Session Management
@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(req: ChatSessionRequest, session=Depends(verify_session)):
    """Create a new Auspex chat session."""
    logger.info(f"Creating chat session for topic: {req.topic}, title: {req.title}")
    
    auspex = get_auspex_service()
    user_id = session.get('user')  # Get user from session
    logger.info(f"User ID: {user_id}")
    
    chat_id = await auspex.create_chat_session(
        topic=req.topic,
        user_id=user_id,
        title=req.title
    )
    
    logger.info(f"Created chat session with ID: {chat_id}")
    
    return {
        "chat_id": chat_id,
        "topic": req.topic,
        "title": req.title or f"Chat about {req.topic}",
        "message": "Chat session created successfully"
    }

@router.get("/chat/sessions", status_code=status.HTTP_200_OK)
async def get_chat_sessions(
    topic: Optional[str] = None,
    limit: int = 50,
    session=Depends(verify_session)
):
    """Get user's chat sessions."""
    auspex = get_auspex_service()
    user_id = session.get('user')
    
    sessions = auspex.get_chat_sessions(topic=topic, user_id=user_id, limit=limit)
    return {
        "sessions": sessions,
        "total": len(sessions)
    }

@router.get("/chat/sessions/{chat_id}/messages", status_code=status.HTTP_200_OK)
async def get_chat_history(chat_id: int, session=Depends(verify_session)):
    """Get chat history for a session."""
    auspex = get_auspex_service()
    
    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(chat_id)
    if not chat_info:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    user_id = session.get('user')
    if chat_info['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = auspex.get_chat_history(chat_id)
    # Filter out system messages for client
    user_messages = [msg for msg in messages if msg['role'] != 'system']
    
    return {
        "chat_id": chat_id,
        "messages": user_messages,
        "total_messages": len(user_messages)
    }

@router.delete("/chat/sessions/{chat_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(chat_id: int, session=Depends(verify_session)):
    """Delete a chat session."""
    auspex = get_auspex_service()
    
    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(chat_id)
    if not chat_info:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    user_id = session.get('user')
    if chat_info['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = auspex.delete_chat_session(chat_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete chat session")
    
    return {"message": "Chat session deleted successfully"}

# Chat Messaging
@router.post("/chat/message", status_code=status.HTTP_200_OK)
async def send_chat_message(req: ChatMessageRequest, session=Depends(verify_session)):
    """Send a message to Auspex and get streaming response."""
    logger.info(f"Received chat message - chat_id: {req.chat_id}, message: '{req.message}', model: {req.model}")
    
    auspex = get_auspex_service()
    
    # Verify user owns this chat
    chat_info = auspex.db.get_auspex_chat(req.chat_id)
    if not chat_info:
        logger.error(f"Chat session not found for chat_id: {req.chat_id}")
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    user_id = session.get('user')
    if chat_info['user_id'] != user_id:
        logger.error(f"Access denied - user {user_id} trying to access chat owned by {chat_info['user_id']}")
        raise HTTPException(status_code=403, detail="Access denied")
    
    logger.info(f"Chat verification successful - topic: {chat_info['topic']}, user: {user_id}")
    
    async def generate_response():
        """Generate streaming response."""
        try:
            logger.info(f"Starting chat_with_tools for chat_id: {req.chat_id}")
            async for chunk in auspex.chat_with_tools(req.chat_id, req.message, req.model, req.limit, req.tools_config):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            logger.info("Chat response completed successfully")
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

# Prompt Management
@router.get("/prompts", status_code=status.HTTP_200_OK)
async def get_prompts(session=Depends(verify_session)):
    """Get all available Auspex prompts."""
    auspex = get_auspex_service()
    prompts = auspex.get_all_prompts()
    
    return {
        "prompts": prompts,
        "total": len(prompts)
    }

@router.get("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def get_prompt(prompt_name: str, session=Depends(verify_session)):
    """Get a specific prompt."""
    auspex = get_auspex_service()
    prompt = auspex.get_system_prompt(prompt_name)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    return prompt

@router.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(req: PromptRequest, session=Depends(verify_session)):
    """Create a new Auspex prompt."""
    auspex = get_auspex_service()
    user_id = session.get('user')
    
    try:
        prompt_id = auspex.create_prompt(
            name=req.name,
            title=req.title,
            content=req.content,
            description=req.description,
            user_created=user_id
        )
        
        return {
            "id": prompt_id,
            "name": req.name,
            "message": "Prompt created successfully"
        }
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="Prompt name already exists")
        raise HTTPException(status_code=500, detail="Failed to create prompt")

@router.put("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def update_prompt(prompt_name: str, req: PromptUpdateRequest, session=Depends(verify_session)):
    """Update an Auspex prompt."""
    auspex = get_auspex_service()
    
    # Check if prompt exists
    existing = auspex.get_system_prompt(prompt_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    success = auspex.update_prompt(
        name=prompt_name,
        title=req.title,
        content=req.content,
        description=req.description
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update prompt")
    
    return {"message": "Prompt updated successfully"}

@router.delete("/prompts/{prompt_name}", status_code=status.HTTP_200_OK)
async def delete_prompt(prompt_name: str, session=Depends(verify_session)):
    """Delete an Auspex prompt."""
    auspex = get_auspex_service()
    
    # Check if prompt exists and is not default
    existing = auspex.get_system_prompt(prompt_name)
    if not existing:
        raise HTTPException(status_code=404, detail="Prompt not found")
    
    if existing.get('is_default'):
        raise HTTPException(status_code=400, detail="Cannot delete default prompt")
    
    success = auspex.delete_prompt(prompt_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete prompt")
    
    return {"message": "Prompt deleted successfully"}

# System Information
@router.get("/system/info", status_code=status.HTTP_200_OK)
async def get_system_info(session=Depends(verify_session)):
    """Get Auspex system information."""
    auspex = get_auspex_service()
    
    # Get available topics
    topics = auspex.db.get_topics()
    
    # Get prompt count
    prompts = auspex.get_all_prompts()
    
    return {
        "version": "2.0.0",
        "features": {
            "tools_integration": True,
            "chat_persistence": True,
            "prompt_management": True,
            "streaming_responses": True,
            "real_time_news": True,
            "sentiment_analysis": True,
            "category_analysis": True,
            "semantic_search": True,
            "diversity_filtering": True,
            "structured_analysis": True,
            "follow_up_queries": True
        },
        "available_topics": topics,
        "available_prompts": len(prompts),
        "tools": [
            "search_news",
            "get_topic_articles", 
            "analyze_sentiment_trends",
            "get_article_categories",
            "search_articles_by_keywords",
            "semantic_search_and_analyze",
            "follow_up_query"
        ],
        "status": "operational"
    }

# Diagnostic endpoint
@router.get("/debug/test-tools", status_code=status.HTTP_200_OK)
async def test_auspex_tools(session=Depends(verify_session)):
    """Test Auspex tools functionality."""
    auspex = get_auspex_service()
    results = {
        "database_check": False,
        "tools_service_check": False,
        "topic_articles_test": {"success": False, "error": None},
        "sentiment_analysis_test": {"success": False, "error": None},
        "categories_test": {"success": False, "error": None}
    }
    
    try:
        # Test database connection
        topics = auspex.db.get_topics()
        results["database_check"] = True
        results["available_topics"] = len(topics)
        
        # Test tools service
        tools = auspex.tools
        results["tools_service_check"] = tools is not None
        
        if tools and len(topics) > 0:
            test_topic = topics[0]['name']
            
            # Test topic articles
            try:
                result = await tools.get_topic_articles(test_topic, limit=5)
                results["topic_articles_test"]["success"] = "error" not in result
                results["topic_articles_test"]["article_count"] = result.get("total_articles", 0)
                if "error" in result:
                    results["topic_articles_test"]["error"] = result["error"]
            except Exception as e:
                results["topic_articles_test"]["error"] = str(e)
            
            # Test sentiment analysis
            try:
                result = await tools.analyze_sentiment_trends(test_topic, "month")
                results["sentiment_analysis_test"]["success"] = "error" not in result
                results["sentiment_analysis_test"]["article_count"] = result.get("total_articles", 0)
                if "error" in result:
                    results["sentiment_analysis_test"]["error"] = result["error"]
            except Exception as e:
                results["sentiment_analysis_test"]["error"] = str(e)
            
            # Test categories
            try:
                result = await tools.get_article_categories(test_topic)
                results["categories_test"]["success"] = "error" not in result
                results["categories_test"]["category_count"] = len(result.get("category_distribution", {}))
                if "error" in result:
                    results["categories_test"]["error"] = result["error"]
            except Exception as e:
                results["categories_test"]["error"] = str(e)
                
    except Exception as e:
        results["general_error"] = str(e)
    
    return {
        "status": "test_completed",
        "timestamp": datetime.now().isoformat(),
        "results": results
    } 