from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.security.session import verify_session  
from typing import Optional
from fastapi.templating import Jinja2Templates

# This will be set by the main app - for now use a fallback
templates: Optional[Jinja2Templates] = None

def set_templates(template_instance: Jinja2Templates):
    """Set the templates instance for this router."""
    global templates
    templates = template_instance  
from app.config.config import load_config  
import logging  

logger = logging.getLogger(__name__)  
router = APIRouter()


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse("config.html", {
        "request": request,
        "session": session  # Use the verified session, not request.session
    })


@router.get("/promptmanager", response_class=HTMLResponse)
async def prompt_manager_page(
    request: Request, 
    session=Depends(verify_session)
):
    return templates.TemplateResponse("promptmanager.html", {
        "request": request,
        "session": request.session
    })


@router.get("/vector-analysis", response_class=HTMLResponse)
async def vector_analysis_page(
    request: Request, 
    session=Depends(verify_session)
):
    return templates.TemplateResponse("vector_analysis.html", {
        "request": request,
        "session": request.session
    })


@router.get("/vector-analysis-improved", response_class=HTMLResponse)
async def vector_analysis_improved_page(
    request: Request, 
    session=Depends(verify_session)
):
    """Enhanced vector analysis page with improved performance and UX."""
    return templates.TemplateResponse("vector_analysis_improved.html", {
        "request": request,
        "session": request.session
    })


@router.get("/topic-dashboard", response_class=HTMLResponse)
async def topic_dashboard_page(
    request: Request, 
    session=Depends(verify_session)
):
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


@router.get("/unified-feed", response_class=HTMLResponse)
async def unified_feed_dashboard(
    request: Request, 
    session=Depends(verify_session)
):
    """Serves the new unified feed dashboard."""
    try:
        logger.info("Loading unified feed dashboard")
        return templates.TemplateResponse("unified_feed_dashboard.html", {
            "request": request,
            "session": request.session
        })
    except Exception as e:
        logger.error(f"Error loading unified feed dashboard: {e}", exc_info=True)
        return templates.TemplateResponse("unified_feed_dashboard.html", {
            "request": request,
            "session": request.session,
            "error": "Could not load unified feed dashboard."
        })


@router.get("/feed-manager", response_class=HTMLResponse)
async def feed_group_manager(
    request: Request, 
    session=Depends(verify_session)
):
    """Serves the feed group management interface."""
    try:
        logger.info("Loading feed group manager")
        return templates.TemplateResponse("feed_group_manager.html", {
            "request": request,
            "session": request.session
        })
    except Exception as e:
        logger.error(f"Error loading feed group manager: {e}", exc_info=True)
        return templates.TemplateResponse("feed_group_manager.html", {
            "request": request,
            "session": request.session,
            "error": "Could not load feed group manager."
        }) 


@router.get("/model-bias-arena", response_class=HTMLResponse)
async def model_bias_arena_page(
    request: Request,
    session=Depends(verify_session)
):
    """Serves the model bias arena interface."""
    try:
        logger.info("Loading model bias arena")
        return templates.TemplateResponse("model_bias_arena.html", {
            "request": request,
            "session": request.session
        })
    except Exception as e:
        logger.error(f"Error loading model bias arena: {e}", exc_info=True)
        return templates.TemplateResponse("model_bias_arena.html", {
            "request": request,
            "session": request.session,
            "error": "Could not load model bias arena."
        })


@router.get("/consensus-analysis", response_class=HTMLResponse)
async def consensus_analysis_page(
    request: Request,
    session=Depends(verify_session)
):
    """Serves the consensus analysis dashboard interface."""
    try:
        logger.info("Loading consensus analysis dashboard")
        config = load_config()
        # Extract topic names for the dropdown
        topics = sorted([topic['name'] for topic in config.get('topics', [])])

        return templates.TemplateResponse("consensus_analysis.html", {
            "request": request,
            "topics": topics,
            "session": request.session
        })
    except Exception as e:
        logger.error(f"Error loading consensus analysis dashboard: {e}", exc_info=True)
        return templates.TemplateResponse("consensus_analysis.html", {
            "request": request,
            "topics": [],
            "session": request.session,
            "error": "Could not load consensus analysis dashboard."
        })
