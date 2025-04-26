from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session  # Changed import
from app.core.shared import templates  # type: ignore

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
