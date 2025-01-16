from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.core.shared import templates

router = APIRouter()

@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    return templates.TemplateResponse("config.html", {"request": request}) 