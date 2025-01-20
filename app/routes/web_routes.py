from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session  # Changed import
from app.core.shared import templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

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
