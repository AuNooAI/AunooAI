"""Routes for newsletter compilation and distribution."""
import logging
import asyncio
from typing import Dict, List, Optional
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.templating import Jinja2Templates

from app.database import Database, get_database_instance
from app.schemas.newsletter import NewsletterRequest, NewsletterResponse, NewsletterPromptTemplate, NewsletterPromptUpdate, ProgressUpdate
from app.services.newsletter_service import NewsletterService
from app.dependencies import get_newsletter_service
from app.security.session import verify_session
from app.config.config import load_config

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["newsletter"])

# Store active newsletter compilations and their progress
active_compilations: Dict[str, Dict] = {}
# Store WebSocket connections for progress updates
active_connections: Dict[str, List[WebSocket]] = {}


@router.get("/api/newsletter/topics")
async def get_newsletter_topics():
    """Get available topics for newsletter compilation."""
    try:
        logger.info("Newsletter topics endpoint called")
        
        # Load config to get topics
        config = load_config()
        topics = [topic["name"] for topic in config.get("topics", [])]
        
        # Fallback to static list if no topics found
        if not topics:
            logger.warning("No topics found in config, returning static list")
            topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        
        logger.info(f"Returning topics for newsletter: {topics}")
        return JSONResponse(content=topics)
        
    except Exception as e:
        logger.error(f"Error getting topics for newsletter: {str(e)}", exc_info=True)
        # Return static list on error
        static_topics = ["AI and Machine Learning", "Trend Monitoring", "Competitor Analysis"]
        logger.info(f"Returning static topics due to error: {static_topics}")
        return JSONResponse(content=static_topics)


@router.get("/api/newsletter/content_types")
async def get_newsletter_content_types():
    """Get available content types for newsletter compilation."""
    content_types = [
        {"id": "topic_summary", "name": "Topic Summary", 
         "description": "AI-generated overview of recent developments about your selected topic, including key trends, important developments, and citations to source materials. Provides a comprehensive picture of what's happening."},
        {"id": "key_charts", "name": "Key Charts", 
         "description": "Visual data representations showing sentiment trends over time and future signals analysis. Helps visualize patterns and directions within the topic data that might not be apparent from reading articles alone."},
        {"id": "trend_analysis", "name": "Trend Analysis", 
         "description": "In-depth analysis of emerging trends, sentiment patterns, and signals based on article metadata. Identifies patterns across multiple sources to spot industry movements, changes in sentiment, and future implications."},
        {"id": "article_insights", "name": "Article Insights", 
         "description": "Thematic grouping of articles organized by key trends or subtopics. Automatically discovers and presents the major themes across your articles, with the most relevant sources highlighted for each theme."},
        {"id": "key_articles", "name": "Key Articles", 
         "description": "Curated list of the most important articles about your topic, with links, source attribution, and a brief explanation of why each article merits attention. Helps identify must-read content among all available sources."},
        {"id": "latest_podcast", "name": "Latest Podcast", 
         "description": "Link and summary of the most recent podcast related to the selected topic, with key takeaways highlighted. Includes audio link when available and an AI-generated summary of the content."},
        {"id": "ethical_societal_impact", "name": "Ethical & Societal Impact",
         "description": "Analysis of ethical considerations, societal implications, and potential impacts on different communities or demographics. Explores how the topic affects various stakeholders and identifies potential ethical concerns."},
        {"id": "business_impact", "name": "Business Impact",
         "description": "Assessment of business opportunities, threats, market changes, and strategic considerations for organizational planning. Identifies how the topic might affect business operations, strategy, and decision-making."},
        {"id": "market_impact", "name": "Market Impact",
         "description": "Analysis of competitive landscape, market trends, industry disruptions, and positioning implications. Explores how the topic is changing market dynamics and what it means for competitive positioning."}
    ]
    return JSONResponse(content=content_types)


@router.post("/api/newsletter/compile", response_model=NewsletterResponse)
async def compile_newsletter(
    request: NewsletterRequest,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_database_instance),
    newsletter_service: NewsletterService = Depends(get_newsletter_service)
):
    """
    Compile newsletter content based on provided parameters.
    
    The endpoint accepts:
    - frequency: daily, weekly, monthly
    - topics: list of topics to include
    - content_types: list of content types to include
    - start_date: optional start date (if not provided, calculated based on frequency)
    - end_date: optional end date (if not provided, defaults to today)
    
    Returns compiled markdown content.
    """
    logger.info(f"Received newsletter compilation request: {request}")
    
    try:
        # Generate a unique ID for this compilation
        import uuid
        compilation_id = str(uuid.uuid4())
        
        # Create entry for progress tracking
        active_compilations[compilation_id] = {
            "status": "in_progress",
            "progress": 0.0,
            "current_step": "Initializing",
            "message": "Starting newsletter compilation",
            "result": None
        }
        
        # Compile the newsletter in background
        background_tasks.add_task(
            compile_newsletter_background,
            compilation_id,
            request,
            newsletter_service
        )
        
        # Return the response with compilation ID for progress tracking
        return NewsletterResponse(
            message=f"Newsletter compilation started with ID: {compilation_id}",
            compiled_markdown=None,
            request_payload=request
        )
        
    except Exception as e:
        logger.error(f"Error starting newsletter compilation: {str(e)}", exc_info=True)
        # Return a response with an error message but don't raise an HTTP exception
        # This allows the frontend to handle the error gracefully
        return NewsletterResponse(
            message=f"Error compiling newsletter: {str(e)}",
            compiled_markdown=f"# Newsletter Compilation Error\n\n{str(e)}",
            request_payload=request
        )


async def compile_newsletter_background(
    compilation_id: str,
    request: NewsletterRequest,
    newsletter_service: NewsletterService
):
    """Background task to compile newsletter and update progress."""
    try:
        # Set the newsletter service to track progress
        newsletter_service.set_progress_callback(
            lambda progress, step, message: update_compilation_progress(
                compilation_id, progress, step, message
            )
        )
        
        # Update progress to indicate we're starting
        update_compilation_progress(
            compilation_id, 0.0, "Starting compilation", "Preparing data sources"
        )
        
        # Compile the newsletter
        compiled_markdown = await newsletter_service.compile_newsletter(request)
        
        # Store the compiled result
        active_compilations[compilation_id]["result"] = compiled_markdown
        
        # Update progress to indicate completion
        update_compilation_progress(
            compilation_id, 100.0, "Compilation complete", "Newsletter is ready"
        )
        
    except Exception as e:
        logger.error(f"Error in background newsletter compilation: {str(e)}", exc_info=True)
        error_markdown = f"# Newsletter Compilation Error\n\n{str(e)}"
        active_compilations[compilation_id]["result"] = error_markdown
        update_compilation_progress(
            compilation_id, 100.0, "Error", f"Error compiling newsletter: {str(e)}"
        )


def update_compilation_progress(
    compilation_id: str,
    progress: Optional[float],
    step: str,
    message: Optional[str] = None
):
    """Update the progress of a newsletter compilation."""
    if compilation_id in active_compilations:
        # If progress is None, keep the current progress value
        if progress is not None:
            active_compilations[compilation_id].update({
                "status": "in_progress" if progress < 100 else "completed",
                "progress": progress,
                "current_step": step,
                "message": message or ""
            })
        else:
            # Only update step and message, preserve progress
            current_progress = active_compilations[compilation_id].get("progress", 0)
            active_compilations[compilation_id].update({
                "status": "in_progress" if current_progress < 100 else "completed",
                "current_step": step,
                "message": message or ""
            })
        
        # Notify all connected websocket clients for this compilation
        if compilation_id in active_connections:
            update = ProgressUpdate(
                status=active_compilations[compilation_id]["status"],
                progress=active_compilations[compilation_id]["progress"],
                current_step=step,
                message=message
            )
            
            for connection in active_connections[compilation_id]:
                asyncio.create_task(send_progress_update(connection, update))


async def send_progress_update(websocket: WebSocket, update: ProgressUpdate):
    """Send a progress update to a connected WebSocket client."""
    try:
        await websocket.send_json(update.dict())
    except Exception as e:
        logger.error(f"Error sending WebSocket update: {str(e)}")


@router.get("/api/newsletter/progress/{compilation_id}")
async def get_compilation_progress(compilation_id: str):
    """Get the current progress of a newsletter compilation."""
    if compilation_id not in active_compilations:
        raise HTTPException(status_code=404, detail="Compilation ID not found")
    
    compilation = active_compilations[compilation_id]
    
    # If compilation is complete, include the result
    if compilation["status"] == "completed" and compilation["result"]:
        result = compilation["result"]
    else:
        result = None
    
    return JSONResponse(content={
        "status": compilation["status"],
        "progress": compilation["progress"],
        "current_step": compilation["current_step"],
        "message": compilation["message"],
        "result": result
    })


@router.websocket("/ws/newsletter/progress/{compilation_id}")
async def websocket_compilation_progress(websocket: WebSocket, compilation_id: str):
    """WebSocket endpoint for real-time newsletter compilation progress updates."""
    await websocket.accept()
    
    # Initialize connection list for this compilation if it doesn't exist
    if compilation_id not in active_connections:
        active_connections[compilation_id] = []
    
    # Add this connection to the list
    active_connections[compilation_id].append(websocket)
    
    try:
        # Send initial state
        if compilation_id in active_compilations:
            compilation = active_compilations[compilation_id]
            update = ProgressUpdate(
                status=compilation["status"],
                progress=compilation["progress"],
                current_step=compilation["current_step"],
                message=compilation["message"]
            )
            await websocket.send_json(update.dict())
        
        # Keep connection open until client disconnects
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        # Remove connection when client disconnects
        if compilation_id in active_connections:
            active_connections[compilation_id].remove(websocket)
            # Clean up empty connection lists
            if not active_connections[compilation_id]:
                del active_connections[compilation_id]


@router.post("/api/newsletter/markdown_to_html")
async def convert_markdown_to_html(markdown_content: str):
    """Convert markdown content to HTML for preview."""
    import markdown
    
    try:
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content, 
            extensions=["tables", "fenced_code"]
        )
        
        return JSONResponse(content={"html_content": html_content})
        
    except Exception as e:
        logger.error(f"Error converting markdown to HTML: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error converting markdown to HTML: {str(e)}"
        )


@router.get("/api/newsletter/prompts", response_model=List[NewsletterPromptTemplate])
async def get_all_prompts(db: Database = Depends(get_database_instance)):
    """Get all newsletter prompt templates."""
    try:
        prompts = db.get_all_newsletter_prompts()
        return prompts
    except Exception as e:
        logger.error(f"Error getting newsletter prompts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting newsletter prompts: {str(e)}"
        )


@router.get("/api/newsletter/prompts/{content_type_id}", response_model=NewsletterPromptTemplate)
async def get_prompt(content_type_id: str, db: Database = Depends(get_database_instance)):
    """Get a specific newsletter prompt template."""
    try:
        prompt = db.get_newsletter_prompt(content_type_id)
        if not prompt:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt for content type '{content_type_id}' not found"
            )
        return prompt
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting newsletter prompt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting newsletter prompt: {str(e)}"
        )


@router.put("/api/newsletter/prompts/{content_type_id}")
async def update_prompt(
    content_type_id: str,
    prompt_update: NewsletterPromptUpdate,
    db: Database = Depends(get_database_instance)
):
    """Update a specific newsletter prompt template."""
    try:
        success = db.update_newsletter_prompt(
            content_type_id,
            prompt_update.prompt_template,
            prompt_update.description
        )
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update prompt for content type '{content_type_id}'"
            )
        
        return {"message": f"Prompt for '{content_type_id}' updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating newsletter prompt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error updating newsletter prompt: {str(e)}"
        )


@router.post("/api/newsletter/save")
async def save_newsletter(
    request: Request,
    db: Database = Depends(get_database_instance)
):
    """
    Save a newsletter to the server.
    
    Args:
        request: The request containing content and filename
        db: Database instance
        
    Returns:
        JSONResponse with success message and file path
    """
    try:
        # Get data from request
        data = await request.json()
        content = data.get('content')
        filename = data.get('filename')
        
        if not content or not filename:
            return JSONResponse(
                content={"error": "Missing content or filename"},
                status_code=400
            )
            
        # Create newsletters directory if it doesn't exist
        newsletters_dir = os.path.join("data", "newsletters")
        os.makedirs(newsletters_dir, exist_ok=True)
        
        # Ensure filename has .md extension
        if not filename.endswith('.md'):
            filename = f"{filename}.md"
            
        # Save file
        file_path = os.path.join(newsletters_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        # Return success
        return JSONResponse(
            content={
                "success": True,
                "message": f"Newsletter saved successfully to {file_path}",
                "file_path": file_path,
                "file_name": filename
            }
        )
        
    except Exception as e:
        logger.error(f"Error saving newsletter: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"error": f"Failed to save newsletter: {str(e)}"},
            status_code=500
        )


# Page router for rendering HTML templates
page_router = APIRouter(tags=["newsletter_pages"])


@page_router.get("/newsletter_compiler", response_class=HTMLResponse)
async def newsletter_page(
    request: Request,
    session=Depends(verify_session)
):
    """
    Render the newsletter compilation page.
    
    This endpoint renders the newsletter_compiler.html template.
    """
    from app.main import get_template_context
    
    # Initialize templates
    templates = Jinja2Templates(directory="templates")
    
    # Create template context
    context = get_template_context(request)
    
    # Render the template
    return templates.TemplateResponse("newsletter_compiler.html", context) 