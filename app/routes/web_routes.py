from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session  # Changed import
from app.core.shared import templates  # type: ignore
from app.config.config import load_config # Added
import logging # Added

logger = logging.getLogger(__name__) # Added
router = APIRouter()

@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("config.html", {
        "request": request,
        "session": request.session
    })

@router.get("/promptmanager", response_class=HTMLResponse)
async def prompt_manager_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("promptmanager.html", {
        "request": request,
        "session": request.session
    })

@router.get("/vector-analysis", response_class=HTMLResponse)
async def vector_analysis_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("vector_analysis.html", {
        "request": request,
        "session": request.session
    })

@router.get("/topic-dashboard", response_class=HTMLResponse)
async def topic_dashboard_page(request: Request, session=Depends(verify_session)):
    """Serves the main page for the per-topic dashboard."""
    try:
        config = load_config()
        # Extract just the names for the dropdown
        topics = sorted([topic['name'] for topic in config.get('topics', [])])
        
        # Pass the list of topic names to the template
        return templates.TemplateResponse("topic_dashboard.html", {
            "request": request,
            "topics": topics,
            "session": request.session
        })
    except Exception as e:
        logger.error(f"Error loading topic dashboard page: {e}", exc_info=True)
        # Optionally, return an error template or raise HTTPException
        # For simplicity, returning an empty topic list for now
        return templates.TemplateResponse("topic_dashboard.html", {
            "request": request,
            "topics": [],
            "session": request.session,
            "error": "Could not load topics."
        }) 
