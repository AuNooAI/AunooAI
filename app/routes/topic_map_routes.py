from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.security.session import verify_session
from app.database import Database
from app.schemas.topic_map import TopicMap

# Setup templates instance (shared throughout the app)
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/api/topic-map", tags=["topic-map"])


@router.get("/{topic_name}")
async def get_topic_map(topic_name: str, session=Depends(verify_session)):
    """Fetch a previously saved topic map."""
    db = Database()
    map_data = db.get_topic_map(topic_name)
    if map_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No map found for topic '{topic_name}'",
        )
    return JSONResponse(content=map_data)


@router.post("/", status_code=201)
async def upsert_topic_map(payload: TopicMap, session=Depends(verify_session)):
    """Create or update a topic map definition."""
    db = Database()
    db.save_topic_map(payload.model_dump())
    return {"ok": True, "topic_name": payload.topic_name}


# ---------- UI Page ---------- #
page_router = APIRouter(tags=["topic-map-page"])


@page_router.get("/topic-map-editor", response_class=HTMLResponse)
async def topic_map_editor(
    request: Request,
    topic: str | None = None,
    session=Depends(verify_session),
):
    """Render the drag-and-drop topic map editor."""
    return templates.TemplateResponse(
        "topic_map_editor.html",
        {
            "request": request,
            "topic": topic,
            "session": request.session,
        },
    )


# Alias route with underscore for backwards-compatibility
@page_router.get(
    "/topic_map_editor",
    response_class=HTMLResponse,
)
async def topic_map_editor_alias(
    request: Request,
    topic: str | None = None,
    session=Depends(verify_session),
):
    """Alias to `topic_map_editor` using underscore URL."""
    return await topic_map_editor(request=request, topic=topic, session=session) 