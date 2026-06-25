"""Routes for the Gather page - React-based keyword monitoring management."""

import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.security.session import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gather"])
templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True  # Reload templates on changes


@router.get("/gather", response_class=HTMLResponse)
async def gather_page(request: Request, session: dict = Depends(verify_session)):
    """Render the Gather React application."""
    return templates.TemplateResponse(
        "gather_react.html",
        {"request": request, "session": session}
    )
