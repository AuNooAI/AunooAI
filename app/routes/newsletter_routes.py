"""Routes for newsletter compilation and distribution."""
import logging
import asyncio
from typing import Dict, List, Optional
import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    Request, 
    BackgroundTasks, 
    WebSocket, 
    WebSocketDisconnect, 
    Body
)
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from starlette.templating import Jinja2Templates

from app.database import Database, get_database_instance
from app.schemas.newsletter import (
    NewsletterRequest, 
    NewsletterResponse, 
    NewsletterPromptTemplate, 
    NewsletterPromptUpdate, 
    ProgressUpdate
)
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

# Define the path for saved newsletters
NEWSLETTERS_DIR = Path("data/newsletters")
if not NEWSLETTERS_DIR.exists():
    NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)


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
        # Validate time period - make sure it's not too restrictive
        if request.start_date and request.end_date:
            from datetime import date, timedelta
            
            # Calculate time difference
            time_diff = request.end_date - request.start_date
            
            # If date range is less than 2 days and not "daily" frequency
            if time_diff.days < 2 and request.frequency != "daily":
                logger.warning(f"Very short time period selected: {time_diff.days} days.")
                
                # For frequencies other than daily, suggest expanding the time range
                if request.frequency == "weekly" and time_diff.days < 5:
                    return NewsletterResponse(
                        message=f"For weekly newsletters, we recommend a time period of at least 5 days to ensure enough content. You selected {time_diff.days} days.",
                        compiled_markdown=f"# Time Period Warning\n\nFor weekly newsletters, we recommend a time period of at least 5 days to ensure enough content.\n\nYou selected {time_diff.days} days ({request.start_date} to {request.end_date}).\n\nPlease adjust your date range and try again.",
                        request_payload=request
                    )
                elif request.frequency == "monthly" and time_diff.days < 15:
                    return NewsletterResponse(
                        message=f"For monthly newsletters, we recommend a time period of at least 15 days to ensure enough content. You selected {time_diff.days} days.",
                        compiled_markdown=f"# Time Period Warning\n\nFor monthly newsletters, we recommend a time period of at least 15 days to ensure enough content.\n\nYou selected {time_diff.days} days ({request.start_date} to {request.end_date}).\n\nPlease adjust your date range and try again.",
                        request_payload=request
                    )
        
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
    """Get a specific newsletter prompt template.
    
    Available prompt template variables:
    - {topic} - The current topic being processed
    - {article_data} - Formatted article data with titles, URLs, sources, etc.
    - {articles} - Alternative way to access article data
    - {formatted_date} - Current date in human-readable format (e.g., "January 1, 2025")
    - {start_date} - Start date for newsletter content (format: YYYY-MM-DD)
    - {end_date} - End date for newsletter content (format: YYYY-MM-DD)
    - {frequency} - Newsletter frequency (daily, weekly, monthly)
    - {topics} - Comma-separated list of all newsletter topics
    - {content_instructions} - Special instructions for this content type
    - {article_count} - Number of articles available for processing
    
    Note: For certain content types, additional specialized variables may be available.
    Always ensure your prompt includes strong guidance against hallucinating article sources.
    """
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
    """Update a specific newsletter prompt template.
    
    Available prompt template variables:
    - {topic} - The current topic being processed
    - {article_data} - Formatted article data with titles, URLs, sources, etc.
    - {articles} - Alternative way to access article data
    - {formatted_date} - Current date in human-readable format (e.g., "January 1, 2025")
    - {start_date} - Start date for newsletter content (format: YYYY-MM-DD)
    - {end_date} - End date for newsletter content (format: YYYY-MM-DD)
    - {frequency} - Newsletter frequency (daily, weekly, monthly)
    - {topics} - Comma-separated list of all newsletter topics
    - {content_instructions} - Special instructions for this content type
    - {article_count} - Number of articles available for processing
    
    Note: For certain content types, additional specialized variables may be available.
    Always ensure your prompt includes strong guidance against hallucinating article sources.
    """
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
    content: str = Body(..., embed=True),
    filename: str = Body(..., embed=True),
    db: Database = Depends(get_database_instance)
):
    """
    Save a newsletter to the server.
    
    Args:
        content: The markdown content of the newsletter
        filename: The filename to save as
        db: Database instance
        
    Returns:
        JSONResponse with success message and file ID
    """
    try:
        # Validate input
        if not content or not filename:
            logger.error("Missing content or filename in save request")
            return JSONResponse(
                content={"success": False, "error": "Missing content or filename"},
                status_code=400
            )
        
        # Ensure filename has .md extension
        if not filename.endswith('.md'):
            filename = f"{filename}.md"
            
        # Create newsletters directory if it doesn't exist
        NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)
            
        # Create a unique newsletter ID and timestamp
        newsletter_id = f"{int(time.time())}"
        timestamp = datetime.now().isoformat()
        
        # Save file
        file_path = NEWSLETTERS_DIR / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Create metadata file
        metadata = {
            "id": newsletter_id,
            "filename": filename,
            "date": timestamp,
            "file_path": str(file_path)
        }

        metadata_path = NEWSLETTERS_DIR / f"{newsletter_id}.meta.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
            
        # Return success
        return JSONResponse(
            content={
                "success": True,
                "message": f"Newsletter saved successfully as {filename}",
                "newsletter_id": newsletter_id,
                "file_path": str(file_path),
                "file_name": filename
            }
        )
        
    except Exception as e:
        logger.error(f"Error saving newsletter: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"success": False, "error": f"Failed to save newsletter: {str(e)}"},
            status_code=500
        )


@router.get("/api/newsletter/saved")
async def get_saved_newsletters():
    """
    Get a list of all saved newsletters.
    
    Returns:
        List of saved newsletter metadata
    """
    try:
        logger.info("Fetching all saved newsletters")
        
        # Ensure directory exists
        NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Newsletters directory: {NEWSLETTERS_DIR}")
        
        # Find all .meta.json files
        metadata_files = list(NEWSLETTERS_DIR.glob("*.meta.json"))
        logger.info(f"Found {len(metadata_files)} metadata files")
        
        if not metadata_files:
            logger.info("No newsletter metadata files found")
            return []
        
        # Log the files found for debugging
        for meta_file in metadata_files:
            logger.debug(f"Found metadata file: {meta_file}")
        
        # Load metadata for each newsletter
        newsletters = []
        for meta_file in metadata_files:
            try:
                logger.debug(f"Processing metadata file: {meta_file}")
                
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    
                newsletter_id = metadata.get("id", "unknown")
                logger.debug(f"Loaded metadata for newsletter ID: {newsletter_id}")
                    
                # Check if the newsletter markdown file exists
                file_path = Path(metadata.get("file_path", ""))
                if file_path.exists():
                    logger.debug(f"Newsletter file exists: {file_path}")
                    newsletters.append(metadata)
                else:
                    logger.warning(f"Newsletter file not found: {file_path}")
                    # If file doesn't exist, remove the metadata
                    logger.info(f"Removing orphaned metadata file: {meta_file}")
                    meta_file.unlink(missing_ok=True)
                    
            except Exception as e:
                logger.error(f"Error reading newsletter metadata {meta_file}: {str(e)}")
                continue
        
        logger.info(f"Returning {len(newsletters)} newsletters")
        return newsletters
        
    except Exception as e:
        logger.error(f"Error getting saved newsletters: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting saved newsletters: {str(e)}"
        )


@router.get("/api/newsletter/saved/{newsletter_id}")
async def get_saved_newsletter(newsletter_id: str):
    """
    Get a specific saved newsletter by ID.
    
    Args:
        newsletter_id: The newsletter ID
        
    Returns:
        Newsletter content and metadata
    """
    try:
        # Look for metadata file
        metadata_path = NEWSLETTERS_DIR / f"{newsletter_id}.meta.json"
        
        if not metadata_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Newsletter with ID {newsletter_id} not found"
            )
            
        # Load metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
            
        # Load content
        file_path = Path(metadata.get("file_path", ""))
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Newsletter file not found at {file_path}"
            )
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Return newsletter data
        return {
            **metadata,
            "content": content
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting saved newsletter: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting saved newsletter: {str(e)}"
        )


@router.delete("/api/newsletter/saved/{newsletter_id}")
async def delete_saved_newsletter(newsletter_id: str):
    """
    Delete a saved newsletter by ID.
    
    Args:
        newsletter_id: The newsletter ID
        
    Returns:
        Success message
    """
    try:
        logger.info(f"Request to delete newsletter with ID: {newsletter_id}")
        
        # Look for metadata file
        metadata_path = NEWSLETTERS_DIR / f"{newsletter_id}.meta.json"
        
        if not metadata_path.exists():
            logger.warning(f"Newsletter metadata file not found: {metadata_path}")
            raise HTTPException(
                status_code=404,
                detail=f"Newsletter with ID {newsletter_id} not found"
            )
        
        logger.info(f"Found metadata file at {metadata_path}")
            
        # Load metadata to get file path
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                
            logger.info(f"Loaded metadata: {metadata}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in metadata file {metadata_path}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Invalid newsletter metadata: {str(e)}"
            )
            
        # Delete content file
        file_path = Path(metadata.get("file_path", ""))
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Deleted newsletter file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting newsletter file {file_path}: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error deleting newsletter file: {str(e)}"
                )
        else:
            logger.warning(f"Newsletter file not found: {file_path}")
            
        # Delete metadata file
        try:
            metadata_path.unlink()
            logger.info(f"Deleted metadata file: {metadata_path}")
        except Exception as e:
            logger.error(f"Error deleting metadata file {metadata_path}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error deleting newsletter metadata: {str(e)}"
            )
            
        # Return success
        logger.info(f"Newsletter with ID {newsletter_id} deleted successfully")
        return {"success": True, "message": f"Newsletter with ID {newsletter_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting saved newsletter: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting saved newsletter: {str(e)}"
        )


@router.post("/api/newsletter/export_pdf")
async def export_pdf(markdown_content: str = Body(..., embed=True)):
    """
    Export newsletter as PDF.
    
    Args:
        markdown_content: The markdown content to convert to PDF
        
    Returns:
        PDF file as a stream
    """
    try:
        import markdown
        import pdfkit
        from io import BytesIO
        
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content, 
            extensions=["tables", "fenced_code"]
        )
        
        # Add HTML wrapper with styles
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Newsletter</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                h1, h2, h3 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
                img {{ max-width: 100%; height: auto; }}
                .chart {{ max-width: 500px; margin: 15px auto; }}
                code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Generate PDF using pdfkit
        pdf = pdfkit.from_string(full_html, False)
        
        # Return PDF as stream
        return StreamingResponse(
            BytesIO(pdf),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=newsletter.pdf"}
        )
        
    except Exception as e:
        logger.error(f"Error exporting PDF: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting PDF: {str(e)}"
        )


@router.post("/api/newsletter/send_email")
async def send_email(
    recipients: List[str] = Body(...),
    subject: str = Body(...),
    markdown_content: str = Body(...)
):
    """
    Send newsletter via email.
    
    Args:
        recipients: List of email addresses
        subject: Email subject
        markdown_content: The markdown content of the newsletter
        
    Returns:
        Success status and message
    """
    try:
        import markdown
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        
        # Validate email addresses
        if not recipients:
            return JSONResponse(
                content={"success": False, "error": "No recipients provided"},
                status_code=400
            )
        
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content, 
            extensions=["tables", "fenced_code"]
        )
        
        # Add HTML wrapper with styles
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                h1, h2, h3 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
                img {{ max-width: 100%; height: auto; }}
                .chart {{ max-width: 500px; margin: 15px auto; }}
                code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Load config
        config = load_config()
        smtp_config = config.get("smtp", {})
        
        # Extract SMTP settings
        smtp_server = smtp_config.get("server", "smtp.gmail.com")
        smtp_port = smtp_config.get("port", 587)
        smtp_username = smtp_config.get("username", "")
        smtp_password = smtp_config.get("password", "")
        sender_email = smtp_config.get("sender_email", smtp_username)
        
        # Create email message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = ", ".join(recipients)
        
        # Add body parts
        text_part = MIMEText(markdown_content, "plain")
        html_part = MIMEText(full_html, "html")
        message.attach(text_part)
        message.attach(html_part)
        
        # Send the email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        
        return JSONResponse(content={
            "success": True,
            "message": f"Email sent successfully to {len(recipients)} recipient(s)"
        })
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"success": False, "error": f"Failed to send email: {str(e)}"},
            status_code=500
        )


@router.get("/api/newsletter/podcasts")
async def get_podcasts(db: Database = Depends(get_database_instance)):
    """Get available podcasts for newsletter inclusion."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Get column information to handle table schema dynamically
            cursor.execute("PRAGMA table_info(podcasts)")
            table_info = cursor.fetchall()
            column_names = [col[1] for col in table_info]  # Column name is at index 1
            
            # Build a query that works with the available columns
            # Base columns we need
            select_columns = ["id", "title", "created_at"]
            if "audio_url" in column_names:
                select_columns.append("audio_url")
            if "topic" in column_names:
                select_columns.append("topic")
            
            # Execute query to get recent podcasts
            cursor.execute(
                f"""
                SELECT {', '.join(select_columns)}
                FROM podcasts
                ORDER BY created_at DESC
                LIMIT 20
                """
            )
            
            podcasts = cursor.fetchall()
            
            # Format results
            result = []
            for podcast in podcasts:
                podcast_dict = {}
                for i, col in enumerate(select_columns):
                    podcast_dict[col] = podcast[i]
                result.append(podcast_dict)
            
            return result
            
    except Exception as e:
        logger.error(f"Error getting podcasts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting podcasts: {str(e)}"
        )


@router.get("/api/newsletter/articles/search")
async def search_articles(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    topic: Optional[str] = None,
    limit: int = 20,
    db: Database = Depends(get_database_instance)
):
    """
    Search for articles based on query, date range, and topic.
    
    Args:
        query: Search query string
        start_date: Optional start date in format YYYY-MM-DD
        end_date: Optional end date in format YYYY-MM-DD
        topic: Optional topic filter
        limit: Maximum number of results to return (default: 20)
        
    Returns:
        List of articles matching the search criteria
    """
    try:
        logger.info(f"Searching for articles with query: '{query}', topic: '{topic}', dates: {start_date} to {end_date}")
        
        # Validate date formats if provided
        if start_date:
            try:
                datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid start_date format. Use YYYY-MM-DD."
                )
                
        if end_date:
            try:
                datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid end_date format. Use YYYY-MM-DD."
                )
        
        # Build search query
        search_conditions = []
        params = []
        
        if query:
            # Add fuzzy search on title and summary
            search_conditions.append("(title LIKE ? OR summary LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        
        if topic:
            search_conditions.append("topic = ?")
            params.append(topic)
            
        if start_date:
            search_conditions.append("publication_date >= ?")
            params.append(start_date)
            
        if end_date:
            search_conditions.append("publication_date <= ?")
            params.append(end_date)
            
        # Construct the WHERE clause
        where_clause = " AND ".join(search_conditions) if search_conditions else "1=1"
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            query = f"""
                SELECT * FROM articles 
                WHERE {where_clause}
                ORDER BY publication_date DESC
                LIMIT {limit}
            """
            
            cursor.execute(query, params)
            articles = cursor.fetchall()
            
            # Convert to list of dictionaries with column names
            column_names = [description[0] for description in cursor.description]
            result = []
            
            for row in articles:
                article_dict = dict(zip(column_names, row))
                result.append(article_dict)
                
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching articles: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error searching articles: {str(e)}"
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