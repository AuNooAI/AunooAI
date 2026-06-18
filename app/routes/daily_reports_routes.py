"""
Desk Briefings API Routes (Briefing Desk Feature)

Provides endpoints for:
- Creating and managing curated briefings
- Adding/removing articles and incidents to briefings
- Generating AI synthesis when finalizing
- Exporting briefings in various formats
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any


def get_base_url(http_request: Request) -> str:
    """Extract base URL from the request (e.g., https://wileytest.aunoo.ai)."""
    return str(http_request.url).replace(str(http_request.url.path), "").rstrip("/")
import json
import logging
import urllib.parse
from datetime import datetime

from app.security.session import verify_session, verify_session_api
from app.database import get_database_instance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/desk-briefings", tags=["Desk Briefings"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateBriefingRequest(BaseModel):
    """Request model for creating a new desk briefing."""
    name: str = Field(..., min_length=1, max_length=255, description="Briefing name")
    description: Optional[str] = Field(None, description="Optional description")
    topic: Optional[str] = Field(None, description="Optional topic association")


class AutoComposeRequest(BaseModel):
    """Request model for auto-composing a daily briefing."""
    topics: Optional[List[str]] = Field(
        None,
        description="Topics to compose from. Falls back to the stored daily_briefing_topics setting when omitted.",
    )
    min_confidence: float = Field(0.6, ge=0.0, le=1.0, description="Emerging-topic confidence floor")
    min_alignment: float = Field(0.7, ge=0.0, le=1.0, description="Article topic_alignment_score floor")
    days_back: int = Field(7, ge=1, le=30, description="Look-back window in days")
    run_detection: bool = Field(True, description="Run Emerging Topics detection before staging")
    model: str = Field("gpt-5.4", description="Model for detection")


class ComposeConfigRequest(BaseModel):
    """Request model for saving the default daily-briefing topic set."""
    topics: List[str] = Field(default_factory=list, description="Selected topic names")


class UpdateBriefingRequest(BaseModel):
    """Request model for updating briefing metadata."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New name")
    description: Optional[str] = Field(None, description="New description")


class ArticleAnalysis(BaseModel):
    """Analysis data for an article."""
    key_insight: Optional[str] = None
    executive_takeaway: Optional[str] = None
    strategic_relevance: Optional[str] = None
    category: Optional[str] = None
    time_horizon: Optional[str] = None
    risk_opportunity: Optional[str] = None
    signal_strength: Optional[str] = None


class AddArticleRequest(BaseModel):
    """Request model for adding an article to a briefing."""
    uri: str = Field(..., description="Article URI")
    title: str = Field(..., description="Article title")
    summary: Optional[str] = Field(None, description="Article summary")
    source: Optional[str] = Field(None, description="Source name")
    publication_date: Optional[str] = Field(None, description="Publication date")
    topic: Optional[str] = Field(None, description="Topic the article came from")
    url: Optional[str] = Field(None, description="Article URL")
    sentiment: Optional[str] = Field(None, description="Sentiment analysis")
    bias: Optional[str] = Field(None, description="Political bias")
    category: Optional[str] = Field(None, description="Category")
    analysis: Optional[ArticleAnalysis] = Field(None, description="Article analysis data")


class IncidentAnalysis(BaseModel):
    """Analysis data for an incident."""
    key_insight: Optional[str] = None
    strategic_relevance: Optional[str] = None
    category: Optional[str] = None
    time_horizon: Optional[str] = None
    risk_opportunity: Optional[str] = None
    plausibility: Optional[str] = None
    source_quality: Optional[str] = None
    credibility_summary: Optional[str] = None


class AddIncidentRequest(BaseModel):
    """Request model for adding an incident to a briefing."""
    # All fields first
    name: Optional[str] = Field(None, description="Incident name")
    title: Optional[str] = Field(None, description="Incident title")
    type: Optional[str] = Field(None, description="Incident type")
    significance: Optional[str] = Field(None, description="Significance level")
    description: Optional[str] = Field(None, description="Description")
    summary: Optional[str] = Field(None, description="Summary")
    topic: Optional[str] = Field(None, description="Topic the incident came from")
    timeline: Optional[str] = Field(None, description="Timeline")
    first_seen: Optional[str] = Field(None, description="First seen date")
    last_seen: Optional[str] = Field(None, description="Last seen date")
    entities: Optional[List[str]] = Field(None, description="Related entities")
    article_uris: Optional[List[str]] = Field(None, description="Related article URIs")
    organizational_relevance: Optional[str] = Field(None, description="Organizational relevance")
    strategic_relevance: Optional[str] = Field(None, description="Strategic relevance (alias for organizational)")
    plausibility: Optional[str] = Field(None, description="Plausibility assessment")
    source_quality: Optional[str] = Field(None, description="Source quality")
    credibility_summary: Optional[str] = Field(None, description="Credibility summary")
    investigation_leads: Optional[List[str]] = Field(None, description="Investigation leads")
    analyst_notes: Optional[List[Dict[str, Any]]] = Field(None, description="Analyst notes")
    analysis: Optional[IncidentAnalysis] = Field(None, description="Incident analysis data")

    # Validators after all fields
    @field_validator('entities', 'article_uris', 'investigation_leads', mode='before')
    @classmethod
    def convert_string_to_list(cls, v):
        """Convert string values to list (AI sometimes returns strings instead of lists)."""
        if v is None:
            return None
        if isinstance(v, str):
            # Split by semicolons or newlines if present, otherwise wrap in list
            if ';' in v:
                return [item.strip() for item in v.split(';') if item.strip()]
            elif '\n' in v:
                return [item.strip() for item in v.split('\n') if item.strip()]
            else:
                return [v.strip()] if v.strip() else None
        return v

    @field_validator('timeline', 'first_seen', 'last_seen', 'significance', mode='before')
    @classmethod
    def coerce_to_string(cls, v):
        """Coerce structured values to a string.

        Incident sources sometimes provide these as objects/lists (e.g.
        timeline = {"announced": "2026-06-17"}) rather than plain strings. The
        briefing stores and renders them as text, so flatten instead of
        rejecting the request with a 422.
        """
        if v is None or isinstance(v, str):
            return v
        if isinstance(v, dict):
            return "; ".join(f"{k}: {val}" for k, val in v.items())
        if isinstance(v, (list, tuple)):
            return "; ".join(str(item) for item in v)
        return str(v)

    @model_validator(mode='after')
    def ensure_name_from_title(self):
        """Ensure name is set from title if not provided."""
        if not self.name:
            if self.title and str(self.title).strip():
                self.name = str(self.title).strip()
            else:
                self.name = "Unnamed Incident"
        return self


class FinalizeBriefingRequest(BaseModel):
    """Request model for finalizing a briefing."""
    model: str = Field("gpt-5.4", description="AI model to use for synthesis")
    organizational_profile: Optional[str] = Field(None, description="Organizational profile name for context")
    persona: Optional[str] = Field(None, description="Persona/role for tailored recommendations")


class UpdateSynthesisRequest(BaseModel):
    """Request model for updating briefing synthesis."""
    synthesis: str = Field(..., description="Updated synthesis text (markdown supported)")


class UpdateThemesRequest(BaseModel):
    """Request model for updating briefing themes."""
    themes: List[Dict[str, Any]] = Field(..., description="Updated themes list")


class ShareBriefingEmailRequest(BaseModel):
    """Request model for sharing a briefing via email."""
    to_email: str = Field(..., description="Recipient email address")
    include_pdf: Optional[bool] = Field(None, description="Force PDF attachment (auto-detected if not set)")
    message: Optional[str] = Field(None, description="Optional personal message")


# ============================================================================
# Helper Functions
# ============================================================================

def _get_username_from_session(session: dict) -> str:
    """Extract username from session."""
    user = session.get("user")
    if user and isinstance(user, dict):
        return user.get("username")
    return session.get("username")


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.get("")
async def list_briefings(session: dict = Depends(verify_session)):
    """
    List all desk briefings for the current user.

    Returns briefing summaries sorted by update date.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefings = db.facade.get_desk_briefings_for_user(username)

    return {
        "success": True,
        "briefings": briefings
    }


@router.post("")
async def create_briefing(
    request: CreateBriefingRequest,
    session: dict = Depends(verify_session)
):
    """
    Create a new desk briefing.

    Creates an empty briefing that can have articles and incidents added.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()

    # Check for duplicate name
    existing = db.facade.get_desk_briefings_for_user(username)
    if any(b["name"] == request.name for b in existing):
        raise HTTPException(409, f"Briefing '{request.name}' already exists")

    try:
        briefing_id = db.facade.create_desk_briefing(
            name=request.name,
            username=username,
            description=request.description,
            topic=request.topic
        )

        logger.info(f"Created desk briefing '{request.name}' (ID: {briefing_id}) for user '{username}'")

        return {
            "success": True,
            "briefing_id": briefing_id,
            "message": f"Briefing '{request.name}' created successfully"
        }
    except Exception as e:
        logger.error(f"Failed to create desk briefing: {e}")
        raise HTTPException(500, f"Failed to create briefing: {str(e)}")


def _get_stored_daily_briefing_topics(db) -> List[str]:
    """Read the configured daily-briefing topic set from emerging_topics_settings."""
    from sqlalchemy import text
    conn = db._temp_get_connection()
    try:
        row = conn.execute(text(
            "SELECT daily_briefing_topics FROM emerging_topics_settings WHERE id = 1"
        )).mappings().first()
        if row and row["daily_briefing_topics"]:
            topics = row["daily_briefing_topics"]
            if isinstance(topics, str):
                topics = json.loads(topics)
            return [t for t in topics if t]
        return []
    finally:
        conn.close()


@router.post("/auto-compose")
async def auto_compose_briefing(
    request: AutoComposeRequest,
    session: dict = Depends(verify_session_api)
):
    """
    Auto-compose a draft daily briefing.

    Creates a new DRAFT briefing, runs Emerging Topics detection for each named
    topic, and stages detected topics (above a confidence floor) plus relevant
    News Feed articles (above a topic-alignment floor) for the user to curate.
    Falls back to the stored daily_briefing_topics setting when no topics given.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()

    topics = request.topics or _get_stored_daily_briefing_topics(db)
    if not topics:
        raise HTTPException(
            400,
            "No topics provided and no daily_briefing_topics configured.",
        )

    from app.services.daily_briefing_compose_service import compose_daily_briefing

    try:
        summary = await compose_daily_briefing(
            db,
            username,
            topics,
            min_confidence=request.min_confidence,
            min_alignment=request.min_alignment,
            days_back=request.days_back,
            run_detection=request.run_detection,
            model=request.model,
        )
        return summary
    except Exception as e:
        logger.error(f"Auto-compose failed: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to compose briefing: {str(e)}")


@router.post("/auto-compose/stream")
async def auto_compose_briefing_stream(
    request: AutoComposeRequest,
    session: dict = Depends(verify_session_api)
):
    """
    Auto-compose a draft daily briefing, streaming staged progress as SSE.

    Pipeline: create draft -> gather recent articles -> detect emerging topics ->
    detect incidents -> LLM-curate the briefing-worthy items -> stage into draft.
    Each stage emits a `data: {json}` progress event; ends with `[DONE]`.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    topics = request.topics or _get_stored_daily_briefing_topics(db)
    if not topics:
        raise HTTPException(400, "No topics provided and no daily_briefing_topics configured.")

    from app.services.daily_briefing_compose_service import compose_daily_briefing_stream

    async def stream():
        try:
            async for evt in compose_daily_briefing_stream(
                db, username, topics,
                days_back=request.days_back,
                run_detection=request.run_detection,
                model=request.model,
            ):
                yield f"data: {json.dumps(evt)}\n\n"
        except Exception as e:
            logger.error(f"Auto-compose stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'stage': 'error', 'status': 'failed', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/compose-config")
async def get_compose_config(session: dict = Depends(verify_session_api)):
    """Return the configured topics plus the saved default selection for compose."""
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    from app.config.config import load_config
    config = load_config()
    available = [
        {"name": t["name"], "description": t.get("description", "")}
        for t in config.get("topics", [])
        if t.get("name")
    ]

    db = get_database_instance()
    selected = _get_stored_daily_briefing_topics(db)
    return {"available_topics": available, "selected_topics": selected}


@router.post("/compose-config")
async def save_compose_config(
    request: ComposeConfigRequest,
    session: dict = Depends(verify_session_api)
):
    """Save the default daily-briefing topic set (upsert emerging_topics_settings)."""
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    from sqlalchemy import text
    db = get_database_instance()
    topics = [t for t in request.topics if t]
    conn = db._temp_get_connection()
    try:
        conn.execute(text("""
            INSERT INTO emerging_topics_settings (id, daily_briefing_topics)
            VALUES (1, CAST(:topics AS jsonb))
            ON CONFLICT (id) DO UPDATE
                SET daily_briefing_topics = CAST(:topics AS jsonb),
                    updated_at = NOW()
        """), {"topics": json.dumps(topics)})
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "selected_topics": topics}


@router.get("/count")
async def get_draft_count(session: dict = Depends(verify_session)):
    """
    Get count of draft briefings for the current user.

    Used for displaying badge count in the UI.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    count = db.facade.get_draft_desk_briefings_count(username)

    return {
        "success": True,
        "draft_count": count
    }


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: int,
    session: dict = Depends(verify_session)
):
    """
    Get a specific desk briefing with full content.

    Returns complete briefing including articles, incidents, and synthesis.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_desk_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    return {
        "success": True,
        "briefing": briefing
    }


@router.put("/{briefing_id}")
async def update_briefing(
    briefing_id: int,
    request: UpdateBriefingRequest,
    session: dict = Depends(verify_session)
):
    """
    Update briefing name or description.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.update_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        name=request.name,
        description=request.description
    )

    if not success:
        raise HTTPException(404, "Briefing not found or update failed")

    return {
        "success": True,
        "message": "Briefing updated successfully"
    }


@router.delete("/{briefing_id}")
async def delete_briefing(
    briefing_id: int,
    session: dict = Depends(verify_session)
):
    """
    Delete a desk briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.delete_desk_briefing(briefing_id, username)

    if not success:
        raise HTTPException(404, "Briefing not found or permission denied")

    logger.info(f"Deleted desk briefing {briefing_id} for user '{username}'")

    return {
        "success": True,
        "message": "Briefing deleted successfully"
    }


# ============================================================================
# Article Management Endpoints
# ============================================================================

@router.post("/{briefing_id}/articles")
async def add_article(
    briefing_id: int,
    request: AddArticleRequest,
    session: dict = Depends(verify_session)
):
    """
    Add an article to a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    article_data = {
        "uri": request.uri,
        "title": request.title,
        "summary": request.summary,
        "source": request.source,
        "publication_date": request.publication_date,
        "topic": request.topic,
        "url": request.url or request.uri,
        "sentiment": request.sentiment,
        "bias": request.bias,
        "category": request.category,
        "added_at": datetime.utcnow().isoformat(),
        "analysis": request.analysis.model_dump() if request.analysis else None
    }

    db = get_database_instance()
    success = db.facade.add_article_to_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        article_data=article_data
    )

    if not success:
        raise HTTPException(400, "Failed to add article. Briefing may be finalized or not found.")

    return {
        "success": True,
        "message": "Article added to briefing"
    }


@router.delete("/{briefing_id}/articles/{article_uri:path}")
async def remove_article(
    briefing_id: int,
    article_uri: str,
    session: dict = Depends(verify_session)
):
    """
    Remove an article from a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.remove_article_from_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        article_uri=article_uri
    )

    if not success:
        raise HTTPException(404, "Article not found in briefing or briefing is finalized")

    return {
        "success": True,
        "message": "Article removed from briefing"
    }


# ============================================================================
# Incident Management Endpoints
# ============================================================================

@router.post("/{briefing_id}/incidents")
async def add_incident(
    briefing_id: int,
    request: AddIncidentRequest,
    session: dict = Depends(verify_session)
):
    """
    Add an incident to a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    incident_data = {
        "name": request.name,
        "title": request.title or request.name,
        "type": request.type,
        "significance": request.significance,
        "description": request.description,
        "summary": request.summary,
        "topic": request.topic,
        "timeline": request.timeline,
        "first_seen": request.first_seen,
        "last_seen": request.last_seen,
        "entities": request.entities,
        "article_uris": request.article_uris,
        # Use organizational_relevance or strategic_relevance (alias)
        "organizational_relevance": request.organizational_relevance or request.strategic_relevance,
        "strategic_relevance": request.strategic_relevance or request.organizational_relevance,
        "plausibility": request.plausibility,
        "source_quality": request.source_quality,
        "credibility_summary": request.credibility_summary,
        "investigation_leads": request.investigation_leads,
        "analyst_notes": request.analyst_notes,
        "added_at": datetime.utcnow().isoformat(),
        "analysis": request.analysis.model_dump() if request.analysis else None
    }

    db = get_database_instance()
    success = db.facade.add_incident_to_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        incident_data=incident_data
    )

    if not success:
        raise HTTPException(400, "Failed to add incident. Briefing may be finalized or not found.")

    return {
        "success": True,
        "message": "Incident added to briefing"
    }


@router.delete("/{briefing_id}/incidents/{incident_name}")
async def remove_incident(
    briefing_id: int,
    incident_name: str,
    session: dict = Depends(verify_session)
):
    """
    Remove an incident from a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.remove_incident_from_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        incident_name=incident_name
    )

    if not success:
        raise HTTPException(404, "Incident not found in briefing or briefing is finalized")

    return {
        "success": True,
        "message": "Incident removed from briefing"
    }


# ============================================================================
# Emerging Topics Management Endpoints
# ============================================================================

class AddEmergingTopicRequest(BaseModel):
    """Request model for adding an emerging topic to a briefing."""
    name: str = Field(..., description="Topic name/label")
    summary: Optional[str] = Field(None, description="Topic summary")
    description: Optional[str] = Field(None, description="Topic description")
    why_emerging: Optional[str] = Field(None, description="Why this topic is emerging")
    key_takeaway: Optional[str] = Field(None, description="Key takeaway")
    article_count: Optional[int] = Field(None, description="Number of articles")
    velocity: Optional[str] = Field(None, description="Topic velocity")
    trend_score: Optional[Dict[str, Any]] = Field(None, description="Trend score data")
    key_entities: Optional[List[str]] = Field(None, description="Key entities")
    representative_keywords: Optional[List[str]] = Field(None, description="Representative keywords")
    key_themes: Optional[List[str]] = Field(None, description="Key themes")
    topic: Optional[str] = Field(None, description="Parent topic")
    # Rich analysis fields
    implications: Optional[Dict[str, Any]] = Field(None, description="Strategic and operational implications")
    organization_implications: Optional[Dict[str, Any]] = Field(None, description="Organization-specific implications")
    signals: Optional[Dict[str, Any]] = Field(None, description="Early/strong/weak signals")
    actors: Optional[Dict[str, Any]] = Field(None, description="Companies, people, organizations involved")
    events: Optional[Dict[str, Any]] = Field(None, description="Trigger events, timeline, current status")
    # Source articles with links
    source_articles: Optional[List[Dict[str, Any]]] = Field(None, description="Source articles with title, url, source, date")


@router.post("/{briefing_id}/emerging-topics")
async def add_emerging_topic(
    briefing_id: int,
    request: AddEmergingTopicRequest,
    session: dict = Depends(verify_session)
):
    """
    Add an emerging topic to a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    topic_data = {
        "name": request.name,
        "summary": request.summary,
        "description": request.description,
        "why_emerging": request.why_emerging,
        "key_takeaway": request.key_takeaway,
        "article_count": request.article_count,
        "velocity": request.velocity,
        "trend_score": request.trend_score,
        "key_entities": request.key_entities,
        "representative_keywords": request.representative_keywords,
        "key_themes": request.key_themes,
        "topic": request.topic,
        "implications": request.implications,
        "organization_implications": request.organization_implications,
        "signals": request.signals,
        "actors": request.actors,
        "events": request.events,
        "source_articles": request.source_articles,
        "added_at": datetime.utcnow().isoformat()
    }

    db = get_database_instance()
    success = db.facade.add_emerging_topic_to_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        topic_data=topic_data
    )

    if not success:
        raise HTTPException(400, "Failed to add emerging topic. Briefing may be finalized or not found.")

    return {
        "success": True,
        "message": "Emerging topic added to briefing"
    }


@router.delete("/{briefing_id}/emerging-topics/{topic_name}")
async def remove_emerging_topic(
    briefing_id: int,
    topic_name: str,
    session: dict = Depends(verify_session)
):
    """
    Remove an emerging topic from a briefing.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.remove_emerging_topic_from_desk_briefing(
        briefing_id=briefing_id,
        username=username,
        topic_name=topic_name
    )

    if not success:
        raise HTTPException(404, "Emerging topic not found in briefing or briefing is finalized")

    return {
        "success": True,
        "message": "Emerging topic removed from briefing"
    }


# ============================================================================
# Finalize Endpoint (AI Synthesis)
# ============================================================================

@router.post("/{briefing_id}/finalize")
async def finalize_briefing(
    briefing_id: int,
    request: FinalizeBriefingRequest,
    session: dict = Depends(verify_session)
):
    """
    Finalize a briefing by generating AI synthesis.

    Returns a streaming response with progress updates.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_desk_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    if briefing.get("status") == "finalized":
        raise HTTPException(400, "Briefing is already finalized")

    articles = briefing.get("articles", [])
    incidents = briefing.get("incidents", [])

    if len(articles) == 0 and len(incidents) == 0:
        raise HTTPException(400, "Cannot finalize an empty briefing")

    # Import the synthesis service
    from app.services.daily_report_service import get_daily_report_service

    async def stream_finalize():
        service = get_daily_report_service()
        try:
            async for update in service.generate_synthesis(
                briefing_name=briefing.get("name"),
                articles=articles,
                incidents=incidents,
                model=request.model,
                organizational_profile=request.organizational_profile,
                persona=request.persona
            ):
                event_data = json.dumps(update, default=str)
                yield f"data: {event_data}\n\n"

                # Save on completion
                if update.get("stage") == "complete":
                    db.facade.finalize_desk_briefing(
                        briefing_id=briefing_id,
                        username=username,
                        synthesis=update.get("synthesis", ""),
                        themes=update.get("themes", []),
                        priority_actions=update.get("priority_actions", []),
                        metadata=update.get("metadata", {}),
                        model_used=request.model
                    )

                if update.get("stage") in ["complete", "error"]:
                    break

        except Exception as e:
            logger.error(f"Finalize briefing stream error: {e}", exc_info=True)
            error_event = json.dumps({
                "stage": "error",
                "status": "failed",
                "error": str(e)
            })
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        stream_finalize(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.put("/{briefing_id}/synthesis")
async def update_synthesis(
    briefing_id: int,
    request: UpdateSynthesisRequest,
    session: dict = Depends(verify_session)
):
    """
    Update the synthesis text of a finalized briefing.

    Allows editing the AI-generated synthesis while preserving other fields.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.update_desk_briefing_synthesis(
        briefing_id=briefing_id,
        username=username,
        synthesis=request.synthesis
    )

    if not success:
        raise HTTPException(404, "Briefing not found or update failed")

    logger.info(f"Updated synthesis for briefing {briefing_id}")

    return {
        "success": True,
        "message": "Synthesis updated successfully"
    }


class UpdatePriorityActionsRequest(BaseModel):
    """Request model for updating briefing priority actions."""
    priority_actions: List[Dict[str, Any]] = Field(..., description="List of priority actions")


@router.post("/{briefing_id}/reopen")
async def reopen_briefing(
    briefing_id: int,
    session: dict = Depends(verify_session)
):
    """
    Reopen a finalized briefing to allow adding more content.

    Changes status from 'finalized' back to 'draft'.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.reopen_desk_briefing(briefing_id, username)

    if not success:
        raise HTTPException(404, "Briefing not found or already a draft")

    logger.info(f"Reopened briefing {briefing_id} for user '{username}'")

    return {
        "success": True,
        "message": "Briefing reopened - you can now add more content"
    }


@router.put("/{briefing_id}/priority-actions")
async def update_priority_actions(
    briefing_id: int,
    request: UpdatePriorityActionsRequest,
    session: dict = Depends(verify_session)
):
    """
    Update the priority actions of a finalized briefing.

    Allows editing AI-generated priority actions while preserving other fields.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.update_desk_briefing_priority_actions(
        briefing_id=briefing_id,
        username=username,
        priority_actions=request.priority_actions
    )

    if not success:
        raise HTTPException(404, "Briefing not found or update failed")

    logger.info(f"Updated priority actions for briefing {briefing_id}")

    return {
        "success": True,
        "message": "Priority actions updated successfully"
    }


@router.put("/{briefing_id}/themes")
async def update_themes(
    briefing_id: int,
    request: UpdateThemesRequest,
    session: dict = Depends(verify_session)
):
    """
    Update the themes of a briefing.

    Allows editing AI-generated themes while preserving other fields.
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.update_desk_briefing_themes(
        briefing_id=briefing_id,
        username=username,
        themes=request.themes
    )

    if not success:
        raise HTTPException(404, "Briefing not found or update failed")

    logger.info(f"Updated themes for briefing {briefing_id}")

    return {
        "success": True,
        "message": "Themes updated successfully"
    }


@router.post("/{briefing_id}/share")
async def share_briefing_via_email(
    http_request: Request,
    briefing_id: int,
    request: ShareBriefingEmailRequest,
    session: dict = Depends(verify_session)
):
    """
    Share a briefing via email.

    If the briefing is short (under 2000 chars synthesis), sends inline HTML.
    If longer or include_pdf=True, attaches a PDF.
    """
    from app.services.email_service import get_email_service
    base_url = get_base_url(http_request)

    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_desk_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    email_service = get_email_service()
    if not email_service:
        raise HTTPException(503, "Email service not configured")

    # Determine if we should use PDF
    synthesis_length = len(briefing.get('synthesis', '') or '')
    total_items = (
        len(briefing.get('articles', [])) +
        len(briefing.get('incidents', [])) +
        len(briefing.get('emerging_topics', []))
    )

    # Build rich HTML email with all content
    try:
        html_body = _build_full_email_body(briefing, base_url, request.message)
        subject = f"[AuNoo AI] Briefing: {briefing.get('name', 'Untitled')}"

        # Use the email service to send (not async)
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=html_body
        )

        if not success:
            raise HTTPException(500, "Failed to send email")

        logger.info(f"Shared briefing {briefing_id} via email to {request.to_email}")

        return {
            "success": True,
            "message": f"Briefing shared successfully to {request.to_email}",
            "method": "inline_html"
        }

    except Exception as e:
        logger.error(f"Failed to share briefing via email: {e}")
        raise HTTPException(500, f"Failed to send email: {str(e)}")


def _build_email_summary(briefing: Dict, personal_message: Optional[str] = None) -> str:
    """Build a summary email body when PDF is attached."""
    lines = []
    lines.append('<div style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; max-width: 600px; margin: 0 auto;">')
    lines.append('<div style="background: linear-gradient(135deg, #ec4899, #8b5cf6); padding: 20px; border-radius: 8px 8px 0 0;">')
    lines.append(f'<h1 style="color: white; margin: 0; font-size: 22px;">Briefing: {briefing.get("name", "Untitled")}</h1>')
    lines.append('</div>')
    lines.append('<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">')

    if personal_message:
        lines.append(f'<p style="color: #333; margin-bottom: 15px; padding: 10px; background: #fff; border-left: 3px solid #ec4899; border-radius: 4px;">{personal_message}</p>')

    # Summary stats
    lines.append('<p style="color: #666; margin: 0 0 10px 0;">This briefing contains:</p>')
    lines.append('<ul style="color: #333; margin: 0 0 15px 0;">')
    if briefing.get('articles_count'):
        lines.append(f'<li>{briefing.get("articles_count")} Articles</li>')
    if briefing.get('incidents_count'):
        lines.append(f'<li>{briefing.get("incidents_count")} Incidents</li>')
    if briefing.get('emerging_topics_count'):
        lines.append(f'<li>{briefing.get("emerging_topics_count")} Emerging Topics</li>')
    lines.append('</ul>')

    # Brief synthesis excerpt
    if briefing.get('synthesis'):
        excerpt = briefing.get('synthesis', '')[:300]
        if len(briefing.get('synthesis', '')) > 300:
            excerpt += '...'
        lines.append(f'<p style="color: #333; font-style: italic; padding: 10px; background: #fff; border-radius: 4px;">"{excerpt}"</p>')

    lines.append('<p style="color: #666; margin-top: 15px;"><strong>See the attached PDF for the full briefing.</strong></p>')
    lines.append('</div>')
    lines.append('<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e9ecef; border-top: none;">')
    lines.append('<p style="color: #666; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong> Briefing Desk</p>')
    lines.append('</div>')
    lines.append('</div>')

    return '\n'.join(lines)


def _build_full_email_body(briefing: Dict, base_url: str, personal_message: Optional[str] = None) -> str:
    """Build a full inline email body with rich formatting matching incident style."""
    lines = []
    lines.append('<div style="font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; max-width: 600px; margin: 0 auto;">')

    # Header with gradient
    lines.append('<div style="background: linear-gradient(135deg, #ec4899, #8b5cf6); padding: 20px; border-radius: 8px 8px 0 0;">')
    lines.append(f'<h1 style="color: white; margin: 0; font-size: 22px;">📋 {briefing.get("name", "Untitled")}</h1>')
    # Status badge
    status = briefing.get('status', 'draft')
    status_color = '#10b981' if status == 'finalized' else '#6b7280'
    lines.append(f'<span style="display: inline-block; background: {status_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin-top: 8px; text-transform: uppercase;">{status}</span>')
    lines.append('</div>')

    lines.append('<div style="background: #fff; padding: 20px; border: 1px solid #e9ecef; border-top: none;">')

    # Personal message
    if personal_message:
        lines.append(f'<div style="background: #fdf2f8; padding: 15px; border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #ec4899;">')
        lines.append(f'<p style="margin: 0; color: #333; font-style: italic;">"{personal_message}"</p>')
        lines.append('</div>')

    # Executive Summary
    if briefing.get('synthesis'):
        lines.append('<div style="background: #f0fdf4; padding: 15px; border-radius: 4px; margin-bottom: 20px; border-left: 4px solid #22c55e;">')
        lines.append('<h3 style="color: #166534; margin: 0 0 8px 0; font-size: 14px;">📝 Executive Summary</h3>')
        synthesis = briefing.get('synthesis', '').replace('\n', '<br>')
        lines.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{synthesis}</p>')
        lines.append('</div>')

    # Key Themes
    themes = briefing.get('themes', [])
    if themes:
        lines.append('<div style="margin-bottom: 20px;">')
        lines.append('<h3 style="color: #1a1a2e; font-size: 14px; margin: 0 0 10px 0; padding-bottom: 5px; border-bottom: 2px solid #8b5cf6;">🎯 Key Themes</h3>')
        for theme in themes:
            lines.append(f'<div style="background: #f5f3ff; padding: 12px; border-radius: 4px; margin-bottom: 8px; border-left: 3px solid #8b5cf6;">')
            lines.append(f'<strong style="color: #5b21b6;">{theme.get("theme_name", "Theme")}</strong>')
            if theme.get('description'):
                lines.append(f'<p style="color: #333; margin: 5px 0 0 0; font-size: 13px;">{theme.get("description")}</p>')
            lines.append('</div>')
        lines.append('</div>')

    # SECTION 1: Incidents (moved up)
    incidents = briefing.get('incidents', [])
    if incidents:
        lines.append('<div style="margin-bottom: 20px; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        lines.append(f'<h3 style="color: #1a1a2e; font-size: 14px; margin: 0 0 12px 0;">🚨 Incidents ({len(incidents)})</h3>')
        for incident in incidents[:5]:
            name = incident.get('name', incident.get('title', 'Unnamed'))
            inc_type = incident.get('type', '')
            significance = incident.get('significance', '')
            description = incident.get('description', incident.get('summary', ''))
            entities = incident.get('entities', [])
            strategic = incident.get('strategic_relevance', '')
            article_uris = incident.get('article_uris', [])

            lines.append('<div style="background: white; padding: 12px; border-radius: 4px; margin-bottom: 10px; border: 1px solid #e9ecef; border-left: 4px solid #667eea;">')
            lines.append(f'<div style="font-weight: 600; color: #333; margin-bottom: 6px;">{name}</div>')

            # Type and significance badges
            badges = []
            if inc_type:
                type_color = {"incident": "#dc3545", "event": "#0d6efd", "expertise": "#6f42c1", "trend": "#198754"}.get(inc_type.lower(), "#6c757d")
                badges.append(f'<span style="background: {type_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{inc_type}</span>')
            if significance:
                sig_color = {"high": "#dc3545", "medium": "#ffc107", "low": "#28a745"}.get(significance.lower(), "#6c757d")
                sig_text_color = "#000" if significance.lower() == "medium" else "#fff"
                badges.append(f'<span style="background: {sig_color}; color: {sig_text_color}; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{significance}</span>')
            if badges:
                lines.append(f'<div style="margin-bottom: 8px;">{" ".join(badges)}</div>')

            if description:
                lines.append(f'<p style="margin: 0 0 8px 0; color: #555; font-size: 13px; line-height: 1.4;">{description[:250]}{"..." if len(description) > 250 else ""}</p>')

            # Strategic relevance
            if strategic:
                lines.append(f'<div style="background: #e3f2fd; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                lines.append(f'<strong style="color: #1565c0; font-size: 11px;">STRATEGIC RELEVANCE:</strong>')
                lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{strategic[:200]}{"..." if len(strategic) > 200 else ""}</p>')
                lines.append('</div>')

            # Organizational relevance
            org_relevance = incident.get('organizational_relevance', '')
            if org_relevance:
                lines.append(f'<div style="background: #fce7f3; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                lines.append(f'<strong style="color: #9d174d; font-size: 11px;">ORGANIZATIONAL RELEVANCE:</strong>')
                lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{org_relevance[:200]}{"..." if len(org_relevance) > 200 else ""}</p>')
                lines.append('</div>')

            # Investigation leads
            inv_leads = incident.get('investigation_leads', [])
            if inv_leads:
                lines.append(f'<div style="background: #fefce8; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                lines.append(f'<strong style="color: #854d0e; font-size: 11px;">INVESTIGATION LEADS:</strong>')
                lines.append('<ul style="margin: 4px 0 0 0; padding-left: 16px; color: #333; font-size: 12px;">')
                for lead in inv_leads[:3]:
                    lines.append(f'<li>{lead[:100]}{"..." if len(lead) > 100 else ""}</li>')
                if len(inv_leads) > 3:
                    lines.append(f'<li style="color: #666; font-style: italic;">...and {len(inv_leads) - 3} more</li>')
                lines.append('</ul></div>')

            # Entities
            if entities:
                lines.append('<div style="margin-top: 8px;">')
                for entity in entities[:5]:
                    lines.append(f'<span style="background: #e8eaf6; color: #3f51b5; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-right: 4px;">{entity}</span>')
                if len(entities) > 5:
                    lines.append(f'<span style="color: #666; font-size: 10px;">+{len(entities) - 5} more</span>')
                lines.append('</div>')

            # Related article links
            if article_uris:
                lines.append(f'<div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #e9ecef;">')
                lines.append(f'<strong style="color: #4b5563; font-size: 11px;">RELATED ARTICLES ({len(article_uris)}):</strong>')
                for uri in article_uris[:3]:
                    lines.append(f'<div style="margin-top: 4px;"><a href="{uri}" style="color: #1976d2; font-size: 11px; text-decoration: none;">📄 {uri[:60]}{"..." if len(uri) > 60 else ""}</a></div>')
                if len(article_uris) > 3:
                    lines.append(f'<div style="color: #666; font-size: 10px; margin-top: 4px;">...and {len(article_uris) - 3} more articles</div>')
                lines.append('</div>')

            # Add explore link
            encoded_incident = urllib.parse.quote(name)
            lines.append(f'<div style="margin-top: 10px; text-align: right;">')
            lines.append(f'<a href="{base_url}/explore?tab=highlights&q={encoded_incident}" style="color: #667eea; font-size: 11px; text-decoration: none;">Explore this incident →</a>')
            lines.append('</div>')

            lines.append('</div>')

        if len(incidents) > 5:
            lines.append(f'<p style="color: #666; font-size: 12px; font-style: italic;">...and {len(incidents) - 5} more incidents</p>')
        lines.append('</div>')

    # SECTION 2: Emerging Topics
    topics = briefing.get('emerging_topics', [])
    if topics:
        lines.append('<div style="margin-bottom: 20px; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        lines.append(f'<h3 style="color: #1a1a2e; font-size: 14px; margin: 0 0 12px 0;">📈 Emerging Topics ({len(topics)})</h3>')
        for topic in topics[:5]:
            label = topic.get('name', 'Unknown Topic')
            description = topic.get('summary', '') or topic.get('description', '')
            trend_score_data = topic.get('trend_score', {})
            if isinstance(trend_score_data, dict):
                score = trend_score_data.get('composite', 0) or 0
                urgency = trend_score_data.get('urgency', '')
            else:
                score = trend_score_data or 0
                urgency = ''
            velocity = topic.get('velocity', '')
            why_emerging = topic.get('why_emerging', '')
            key_takeaway = topic.get('key_takeaway', '')
            key_entities = topic.get('key_entities', [])
            keywords = topic.get('representative_keywords', [])
            key_themes = topic.get('key_themes', [])
            parent_topic = topic.get('topic', '')
            implications = topic.get('implications', {})
            org_implications = topic.get('organization_implications', {})
            signals = topic.get('signals', {})
            actors = topic.get('actors', {})
            events = topic.get('events', {})

            lines.append('<div style="background: #fffbeb; padding: 12px; border-radius: 4px; margin-bottom: 10px; border: 1px solid #fde68a; border-left: 4px solid #f59e0b;">')
            lines.append(f'<div style="font-weight: 600; color: #333; margin-bottom: 6px;">{label}</div>')

            # Score, velocity, and urgency badges
            badges = []
            if score:
                score_color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 40 else "#6b7280"
                badges.append(f'<span style="background: {score_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">Score: {score}</span>')
            if urgency:
                urgency_color = "#dc2626" if urgency == "high" else "#f59e0b" if urgency == "medium" else "#6b7280"
                badges.append(f'<span style="background: {urgency_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; text-transform: uppercase;">{urgency} urgency</span>')
            if velocity:
                badges.append(f'<span style="background: #6366f1; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">Velocity: {velocity}</span>')
            article_count = topic.get('article_count')
            if article_count:
                badges.append(f'<span style="background: #0d9488; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{article_count} articles</span>')
            if parent_topic:
                badges.append(f'<span style="background: #7c3aed; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px;">{parent_topic}</span>')
            if badges:
                lines.append(f'<div style="margin-bottom: 8px;">{" ".join(badges)}</div>')

            if description:
                lines.append(f'<p style="margin: 0 0 8px 0; color: #555; font-size: 13px; line-height: 1.4;">{description[:350]}{"..." if len(description) > 350 else ""}</p>')

            # Key themes
            if key_themes:
                themes_str = ", ".join(key_themes[:5])
                lines.append(f'<div style="margin: 8px 0;"><strong style="color: #4b5563; font-size: 11px;">THEMES:</strong> <span style="color: #555; font-size: 12px;">{themes_str}</span></div>')

            # Key entities
            if key_entities:
                entities_str = ", ".join(key_entities[:6])
                if len(key_entities) > 6:
                    entities_str += f" (+{len(key_entities) - 6} more)"
                lines.append(f'<div style="margin: 8px 0;"><strong style="color: #4b5563; font-size: 11px;">KEY ENTITIES:</strong> <span style="color: #555; font-size: 12px;">{entities_str}</span></div>')

            # Actors (companies, people, orgs)
            if actors:
                actor_parts = []
                if actors.get('companies'):
                    actor_parts.append(f"Companies: {', '.join(actors['companies'][:3])}")
                if actors.get('people'):
                    actor_parts.append(f"People: {', '.join(actors['people'][:3])}")
                if actors.get('organizations'):
                    actor_parts.append(f"Orgs: {', '.join(actors['organizations'][:3])}")
                if actor_parts:
                    lines.append(f'<div style="margin: 8px 0;"><strong style="color: #4b5563; font-size: 11px;">ACTORS:</strong> <span style="color: #555; font-size: 12px;">{" | ".join(actor_parts)}</span></div>')

            # Keywords
            if keywords:
                keywords_html = " ".join([f'<span style="background: #e5e7eb; color: #374151; padding: 1px 6px; border-radius: 10px; font-size: 10px; margin-right: 4px;">{kw}</span>' for kw in keywords[:8]])
                lines.append(f'<div style="margin: 8px 0;">{keywords_html}</div>')

            # Key takeaway
            if key_takeaway:
                lines.append(f'<div style="background: #ecfdf5; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                lines.append(f'<strong style="color: #047857; font-size: 11px;">KEY TAKEAWAY:</strong>')
                lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{key_takeaway[:250]}{"..." if len(key_takeaway) > 250 else ""}</p>')
                lines.append('</div>')

            # Why emerging
            if why_emerging:
                lines.append(f'<div style="background: #fef3c7; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                lines.append(f'<strong style="color: #92400e; font-size: 11px;">WHY THIS IS EMERGING:</strong>')
                lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{why_emerging[:250]}{"..." if len(why_emerging) > 250 else ""}</p>')
                lines.append('</div>')

            # Implications
            if implications:
                impl_parts = []
                if implications.get('strategic'):
                    impl_parts.append(f"Strategic: {implications['strategic'][:100]}...")
                if implications.get('operational'):
                    impl_parts.append(f"Operational: {implications['operational'][:100]}...")
                if impl_parts:
                    lines.append(f'<div style="background: #dbeafe; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                    lines.append(f'<strong style="color: #1e40af; font-size: 11px;">IMPLICATIONS:</strong>')
                    for part in impl_parts:
                        lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{part}</p>')
                    lines.append('</div>')

            # Organization implications
            if org_implications:
                org_parts = []
                if org_implications.get('relevance'):
                    org_parts.append(org_implications['relevance'][:150])
                if org_implications.get('recommended_actions'):
                    actions_list = org_implications['recommended_actions']
                    if isinstance(actions_list, list) and actions_list:
                        org_parts.append(f"Actions: {'; '.join(actions_list[:2])}")
                if org_parts:
                    lines.append(f'<div style="background: #fce7f3; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                    lines.append(f'<strong style="color: #9d174d; font-size: 11px;">FOR YOUR ORGANIZATION:</strong>')
                    for part in org_parts:
                        lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{part}</p>')
                    lines.append('</div>')

            # Signals
            if signals:
                signal_parts = []
                if signals.get('early_signals'):
                    early = signals['early_signals']
                    if isinstance(early, list) and early:
                        signal_parts.append(f"Early: {', '.join(early[:2])}")
                if signals.get('strong_signals'):
                    strong = signals['strong_signals']
                    if isinstance(strong, list) and strong:
                        signal_parts.append(f"Strong: {', '.join(strong[:2])}")
                if signal_parts:
                    lines.append(f'<div style="margin: 8px 0;"><strong style="color: #4b5563; font-size: 11px;">SIGNALS:</strong> <span style="color: #555; font-size: 12px;">{" | ".join(signal_parts)}</span></div>')

            # Events
            if events:
                if events.get('trigger_event'):
                    lines.append(f'<div style="margin: 8px 0;"><strong style="color: #4b5563; font-size: 11px;">TRIGGER:</strong> <span style="color: #555; font-size: 12px;">{events["trigger_event"][:100]}</span></div>')
                # Timeline events
                timeline = events.get('timeline', [])
                if timeline:
                    lines.append(f'<div style="background: #f3f4f6; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                    lines.append(f'<strong style="color: #4b5563; font-size: 11px;">TIMELINE:</strong>')
                    for evt in timeline[:3]:
                        if isinstance(evt, dict):
                            evt_date = evt.get('date', '')
                            evt_text = evt.get('event', '')
                            lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 11px;">• {evt_date}: {evt_text[:80]}{"..." if len(evt_text) > 80 else ""}</p>')
                        elif isinstance(evt, str):
                            lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 11px;">• {evt[:100]}{"..." if len(evt) > 100 else ""}</p>')
                    lines.append('</div>')

            # Source articles with links
            source_articles = topic.get('source_articles', [])
            if source_articles:
                lines.append(f'<div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #fde68a;">')
                lines.append(f'<strong style="color: #92400e; font-size: 11px;">📰 SOURCE ARTICLES ({len(source_articles)}):</strong>')
                for art in source_articles[:5]:
                    art_title = art.get('title', 'Untitled')
                    art_url = art.get('url', '')
                    art_source = art.get('source', 'Unknown')
                    art_date = art.get('date', '')
                    if art_date:
                        art_date = art_date[:10]  # Just the date part
                    if art_url:
                        lines.append(f'<div style="margin-top: 6px;"><a href="{art_url}" style="color: #1976d2; font-size: 12px; text-decoration: none; font-weight: 500;">{art_title[:60]}{"..." if len(art_title) > 60 else ""}</a></div>')
                        lines.append(f'<div style="color: #666; font-size: 10px;">{art_source} • {art_date}</div>')
                    else:
                        lines.append(f'<div style="margin-top: 6px; color: #333; font-size: 12px;">{art_title[:60]}{"..." if len(art_title) > 60 else ""}</div>')
                        lines.append(f'<div style="color: #666; font-size: 10px;">{art_source} • {art_date}</div>')
                if len(source_articles) > 5:
                    lines.append(f'<div style="color: #666; font-size: 10px; margin-top: 4px;">...and {len(source_articles) - 5} more articles</div>')
                lines.append('</div>')

            # Add explore link
            encoded_topic = urllib.parse.quote(label)
            lines.append(f'<div style="margin-top: 10px; text-align: right;">')
            lines.append(f'<a href="{base_url}/explore?tab=emerging&q={encoded_topic}" style="color: #8b5cf6; font-size: 11px; text-decoration: none;">Explore this topic →</a>')
            lines.append('</div>')

            lines.append('</div>')

        if len(topics) > 5:
            lines.append(f'<p style="color: #666; font-size: 12px; font-style: italic;">...and {len(topics) - 5} more emerging topics</p>')
        lines.append('</div>')

    # SECTION 3: Priority Actions
    actions = briefing.get('priority_actions', [])
    if actions:
        lines.append('<div style="margin-bottom: 20px; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        lines.append('<h3 style="color: #1a1a2e; font-size: 14px; margin: 0 0 10px 0; padding-bottom: 5px; border-bottom: 2px solid #dc3545;">⚡ Strategic Considerations</h3>')
        urgency_colors = {
            'immediate': '#dc3545',
            'this_week': '#fd7e14',
            'this_month': '#ffc107',
            'this_quarter': '#6c757d'
        }
        urgency_bg = {
            'immediate': '#fee2e2',
            'this_week': '#ffedd5',
            'this_month': '#fef9c3',
            'this_quarter': '#f3f4f6'
        }
        for action in actions:
            urgency = action.get('urgency', 'this_month')
            color = urgency_colors.get(urgency, '#6c757d')
            bg = urgency_bg.get(urgency, '#f3f4f6')
            label = urgency.replace('_', ' ').title()
            lines.append(f'<div style="background: {bg}; padding: 10px; border-radius: 4px; margin-bottom: 8px; border-left: 3px solid {color};">')
            lines.append(f'<span style="background: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; text-transform: uppercase;">{label}</span>')
            lines.append(f'<p style="margin: 6px 0 0 0; color: #333;">{action.get("action", "")}</p>')
            if action.get('rationale'):
                lines.append(f'<p style="margin: 4px 0 0 0; color: #666; font-size: 12px; font-style: italic;">{action.get("rationale")}</p>')
            lines.append('</div>')
        lines.append('</div>')

    # SECTION 4: Articles (moved to end)
    articles = briefing.get('articles', [])
    if articles:
        lines.append('<div style="margin-bottom: 20px; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        lines.append(f'<h3 style="color: #1a1a2e; font-size: 14px; margin: 0 0 12px 0;">📰 Articles ({len(articles)})</h3>')
        for i, article in enumerate(articles[:5], 1):
            title = article.get('title', 'Untitled')
            source = article.get('source', article.get('news_source', 'Unknown'))
            url = article.get('uri', article.get('url', ''))
            category = article.get('category', '')
            analysis = article.get('analysis', {})

            lines.append('<div style="background: #f8f9fa; padding: 12px; border-radius: 4px; margin-bottom: 10px; border: 1px solid #e9ecef;">')

            # Title with link
            if url:
                lines.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. <a href="{url}" style="color: #1976d2; text-decoration: none;">{title}</a></div>')
            else:
                lines.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. {title}</div>')

            # Source and category badges
            badge_line = f'<span style="color: #666; font-size: 12px;">{source}</span>'
            if category:
                badge_line += f' <span style="background: #e8eaf6; color: #3f51b5; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-left: 4px;">{category}</span>'
            lines.append(f'<div style="margin-bottom: 6px;">{badge_line}</div>')

            # Summary
            summary = article.get('summary', '')
            if summary:
                lines.append(f'<p style="margin: 6px 0; color: #555; font-size: 13px; line-height: 1.4;">{summary[:200]}{"..." if len(summary) > 200 else ""}</p>')

            # Rich analysis data if available
            if analysis:
                if analysis.get('executive_takeaway'):
                    lines.append(f'<div style="background: #e3f2fd; padding: 8px; border-radius: 4px; margin-top: 8px;">')
                    lines.append(f'<strong style="color: #1565c0; font-size: 11px;">KEY TAKEAWAY:</strong>')
                    lines.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 12px;">{analysis.get("executive_takeaway")}</p>')
                    lines.append('</div>')
                if analysis.get('strategic_relevance'):
                    lines.append(f'<p style="margin: 6px 0 0 0; color: #666; font-size: 11px;"><strong>Strategic:</strong> {analysis.get("strategic_relevance")[:150]}...</p>')

            lines.append('</div>')

        if len(articles) > 5:
            lines.append(f'<p style="color: #666; font-size: 12px; font-style: italic;">...and {len(articles) - 5} more articles</p>')
        lines.append('</div>')

    # Action buttons
    lines.append('<div style="margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 8px; text-align: center;">')
    lines.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    # Use solid background color for email client compatibility (gradients often don't work)
    lines.append(f'<a href="{base_url}/explore" style="display: inline-block; background-color: #8b5cf6; color: #ffffff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin-right: 10px;">Chat with Auspex</a>')
    lines.append(f'<a href="{base_url}/explore?tab=briefing-desk" style="display: inline-block; background-color: #ec4899; color: #ffffff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500;">View Briefing Desk</a>')
    lines.append('</div>')

    lines.append('</div>')  # Close main content

    # Footer
    lines.append('<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e9ecef; border-top: none;">')
    lines.append('<p style="color: #666; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong> Briefing Desk</p>')
    lines.append('</div>')
    lines.append('</div>')

    return '\n'.join(lines)


# ============================================================================
# Export Endpoint
# ============================================================================

@router.get("/{briefing_id}/export")
async def export_briefing(
    briefing_id: int,
    format: str = "json",
    session: dict = Depends(verify_session)
):
    """
    Export a briefing in various formats.

    Formats:
    - json: Full JSON export with all rich data
    - markdown: Readable markdown document with analysis
    - html: HTML document for sharing
    - pdf: Structured PDF document
    """
    username = _get_username_from_session(session)
    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_desk_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    # Sanitize name for filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in briefing.get('name', 'briefing'))[:50]

    if format == "json":
        return Response(
            content=json.dumps(briefing, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={safe_name}.json"
            }
        )

    elif format == "markdown":
        md_content = _generate_markdown_export(briefing)
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename={safe_name}.md"
            }
        )

    elif format == "html":
        html_content = _generate_html_export(briefing)
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename={safe_name}.html"
            }
        )

    elif format == "pdf":
        pdf_content = _generate_pdf_export(briefing)
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={safe_name}.pdf"
            }
        )

    else:
        raise HTTPException(400, f"Unknown export format: {format}. Supported: json, markdown, html, pdf")


def _generate_markdown_export(briefing: Dict, include_rich_data: bool = True) -> str:
    """Generate a markdown document from a desk briefing with full rich data."""
    lines = []
    lines.append(f"# Briefing: {briefing.get('name', 'Untitled')}")
    lines.append("")

    if briefing.get('description'):
        lines.append(f"*{briefing.get('description')}*")
        lines.append("")

    # Metadata
    lines.append(f"**Status:** {briefing.get('status', 'draft').title()}")
    if briefing.get('finalized_at'):
        lines.append(f"**Finalized:** {briefing.get('finalized_at')}")
    lines.append(f"**Created:** {briefing.get('created_at', 'Unknown')}")

    counts = []
    if briefing.get('articles_count', 0):
        counts.append(f"{briefing.get('articles_count')} Articles")
    if briefing.get('incidents_count', 0):
        counts.append(f"{briefing.get('incidents_count')} Incidents")
    if briefing.get('emerging_topics_count', 0):
        counts.append(f"{briefing.get('emerging_topics_count')} Emerging Topics")
    if counts:
        lines.append(f"**Content:** {' | '.join(counts)}")
    if briefing.get('model_used'):
        lines.append(f"**AI Model:** {briefing.get('model_used')}")
    lines.append("")

    # Executive Summary
    if briefing.get('synthesis'):
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(briefing.get('synthesis'))
        lines.append("")

    # Key Themes
    themes = briefing.get('themes', [])
    if themes:
        lines.append("## Key Themes")
        lines.append("")
        for theme in themes:
            lines.append(f"### {theme.get('theme_name', 'Theme')}")
            lines.append(f"{theme.get('description', '')}")
            if theme.get('supporting_items'):
                items = theme.get('supporting_items')
                if isinstance(items, list):
                    lines.append(f"**Supporting Evidence:** {', '.join(items)}")
            if theme.get('strategic_implication'):
                lines.append(f"**Strategic Implication:** {theme.get('strategic_implication')}")
            lines.append("")

    # Priority Actions
    actions = briefing.get('priority_actions', [])
    if actions:
        lines.append("## Priority Actions")
        lines.append("")
        for action in actions:
            urgency = action.get('urgency', 'this_month').replace('_', ' ').title()
            lines.append(f"- **[{urgency}]** {action.get('action', '')}")
            if action.get('rationale'):
                lines.append(f"  - *{action.get('rationale')}*")
        lines.append("")

    # Articles with rich analysis data
    articles = briefing.get('articles', [])
    if articles:
        lines.append("## Articles")
        lines.append("")
        for i, article in enumerate(articles, 1):
            lines.append(f"### {i}. {article.get('title', 'Untitled')}")
            lines.append("")

            # Basic metadata
            meta = []
            if article.get('source'):
                meta.append(f"**Source:** {article.get('source')}")
            if article.get('publication_date'):
                meta.append(f"**Date:** {article.get('publication_date')}")
            if article.get('topic'):
                meta.append(f"**Topic:** {article.get('topic')}")
            if meta:
                lines.append(" | ".join(meta))
                lines.append("")

            # URL
            if article.get('url'):
                lines.append(f"**URL:** {article.get('url')}")
                lines.append("")

            # Summary
            if article.get('summary'):
                lines.append(f"{article.get('summary')}")
                lines.append("")

            # Rich analysis data
            if include_rich_data:
                analysis = article.get('analysis', {})
                if analysis:
                    lines.append("**Analysis:**")
                    if analysis.get('key_insight'):
                        lines.append(f"- *Key Insight:* {analysis.get('key_insight')}")
                    if analysis.get('strategic_relevance'):
                        lines.append(f"- *Strategic Relevance:* {analysis.get('strategic_relevance')}")
                    if analysis.get('category'):
                        lines.append(f"- *Category:* {analysis.get('category')}")
                    if analysis.get('time_horizon'):
                        lines.append(f"- *Time Horizon:* {analysis.get('time_horizon')}")
                    if analysis.get('risk_opportunity'):
                        lines.append(f"- *Risk/Opportunity:* {analysis.get('risk_opportunity')}")
                    lines.append("")

                # Additional article metadata
                if article.get('sentiment'):
                    lines.append(f"**Sentiment:** {article.get('sentiment')}")
                if article.get('bias'):
                    lines.append(f"**Bias:** {article.get('bias')}")
                if article.get('category'):
                    lines.append(f"**Category:** {article.get('category')}")

            lines.append("---")
            lines.append("")

    # Incidents with rich analysis data
    incidents = briefing.get('incidents', [])
    if incidents:
        lines.append("## Incidents")
        lines.append("")
        for i, incident in enumerate(incidents, 1):
            lines.append(f"### {i}. {incident.get('name', 'Untitled')}")
            lines.append("")

            # Basic metadata
            meta = []
            if incident.get('type'):
                meta.append(f"**Type:** {incident.get('type')}")
            if incident.get('significance'):
                meta.append(f"**Significance:** {incident.get('significance')}")
            if incident.get('topic'):
                meta.append(f"**Topic:** {incident.get('topic')}")
            if meta:
                lines.append(" | ".join(meta))
                lines.append("")

            # Timeline
            if incident.get('timeline'):
                lines.append(f"**Timeline:** {incident.get('timeline')}")
                lines.append("")

            # Description/Summary
            if incident.get('summary') or incident.get('description'):
                lines.append(f"{incident.get('summary') or incident.get('description')}")
                lines.append("")

            # Entities
            if incident.get('entities'):
                entities = incident.get('entities')
                if isinstance(entities, list) and entities:
                    lines.append(f"**Key Entities:** {', '.join(entities)}")
                    lines.append("")

            # Rich analysis data
            if include_rich_data:
                analysis = incident.get('analysis', {})
                if analysis:
                    lines.append("**Analysis:**")
                    if analysis.get('key_insight'):
                        lines.append(f"- *Key Insight:* {analysis.get('key_insight')}")
                    if analysis.get('strategic_relevance'):
                        lines.append(f"- *Strategic Relevance:* {analysis.get('strategic_relevance')}")
                    if analysis.get('category'):
                        lines.append(f"- *Category:* {analysis.get('category')}")
                    if analysis.get('time_horizon'):
                        lines.append(f"- *Time Horizon:* {analysis.get('time_horizon')}")
                    if analysis.get('risk_opportunity'):
                        lines.append(f"- *Risk/Opportunity:* {analysis.get('risk_opportunity')}")
                    lines.append("")

            lines.append("---")
            lines.append("")

    # Emerging Topics
    emerging_topics = briefing.get('emerging_topics', [])
    if emerging_topics:
        lines.append("## Emerging Topics")
        lines.append("")
        for i, topic in enumerate(emerging_topics, 1):
            lines.append(f"### {i}. {topic.get('name', 'Untitled Topic')}")
            lines.append("")

            # Metadata
            meta = []
            if topic.get('article_count'):
                meta.append(f"**Articles:** {topic.get('article_count')}")
            if topic.get('velocity'):
                meta.append(f"**Velocity:** {topic.get('velocity')}")
            if topic.get('topic'):
                meta.append(f"**Topic Area:** {topic.get('topic')}")
            if meta:
                lines.append(" | ".join(meta))
                lines.append("")

            # Summary
            if topic.get('summary'):
                lines.append(topic.get('summary'))
                lines.append("")

            # Why Emerging
            if topic.get('why_emerging'):
                lines.append(f"**Why Emerging:** {topic.get('why_emerging')}")
                lines.append("")

            # Key Takeaway
            if topic.get('key_takeaway'):
                lines.append(f"**Key Takeaway:** {topic.get('key_takeaway')}")
                lines.append("")

            # Trend Score
            if include_rich_data and topic.get('trend_score'):
                score = topic.get('trend_score')
                if isinstance(score, dict):
                    lines.append("**Trend Scores:**")
                    if score.get('composite'):
                        lines.append(f"- *Composite:* {score.get('composite')}")
                    if score.get('volume'):
                        lines.append(f"- *Volume:* {score.get('volume')}")
                    if score.get('velocity'):
                        lines.append(f"- *Velocity:* {score.get('velocity')}")
                    if score.get('diversity'):
                        lines.append(f"- *Diversity:* {score.get('diversity')}")
                    if score.get('novelty'):
                        lines.append(f"- *Novelty:* {score.get('novelty')}")
                    if score.get('urgency'):
                        lines.append(f"- *Urgency:* {score.get('urgency')}")
                    lines.append("")

            # Key Entities
            if topic.get('key_entities'):
                entities = topic.get('key_entities')
                if isinstance(entities, list) and entities:
                    lines.append(f"**Key Entities:** {', '.join(entities)}")
                    lines.append("")

            # Keywords
            if topic.get('representative_keywords'):
                keywords = topic.get('representative_keywords')
                if isinstance(keywords, list) and keywords:
                    lines.append(f"**Keywords:** {', '.join(keywords)}")
                    lines.append("")

            lines.append("---")
            lines.append("")

    lines.append("---")
    lines.append("*Exported from Briefing Desk - AuNoo AI*")

    return "\n".join(lines)


def _generate_html_export(briefing: Dict) -> str:
    """Generate an HTML document from a desk briefing."""
    md_content = _generate_markdown_export(briefing)

    # Simple markdown to HTML conversion
    html_body = md_content
    html_body = html_body.replace("\n\n", "</p><p>")
    html_body = html_body.replace("\n", "<br>")
    html_body = f"<p>{html_body}</p>"

    # Convert headers
    import re
    html_body = re.sub(r'<p>### (.*?)</p>', r'<h3>\1</h3>', html_body)
    html_body = re.sub(r'<p>## (.*?)</p>', r'<h2>\1</h2>', html_body)
    html_body = re.sub(r'<p># (.*?)</p>', r'<h1>\1</h1>', html_body)

    # Convert bold
    html_body = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_body)

    # Convert italic
    html_body = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_body)

    # Convert list items
    html_body = re.sub(r'<br>- (.*?)(?=<br>|</p>)', r'<li>\1</li>', html_body)
    html_body = html_body.replace('<li>', '<ul><li>').replace('</li></p>', '</li></ul></p>')

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Briefing: {briefing.get('name', 'Untitled')}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px; line-height: 1.6; color: #333; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #4a6fa5; padding-bottom: 15px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        h3 {{ color: #0f3460; }}
        strong {{ color: #4a6fa5; }}
        ul {{ margin: 10px 0; padding-left: 25px; }}
        li {{ margin: 5px 0; }}
        hr {{ border: none; border-top: 1px solid #eee; margin: 20px 0; }}
        .meta {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""

    return html


def _generate_pdf_export(briefing: Dict) -> bytes:
    """Generate a structured PDF document from a desk briefing."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
            Table, TableStyle, HRFlowable
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        from reportlab.lib import colors
        import io
    except ImportError:
        raise HTTPException(500, "PDF export requires reportlab. Install with: pip install reportlab")

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )

    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'BriefingTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=HexColor('#ec4899'),
        spaceAfter=10,
        alignment=TA_CENTER
    )
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#1a1a2e'),
        spaceBefore=20,
        spaceAfter=10,
        borderColor=HexColor('#ec4899'),
        borderWidth=1,
        borderPadding=5
    )
    subsection_style = ParagraphStyle(
        'SubsectionHeader',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=HexColor('#333'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BriefingBody',
        parent=styles['BodyText'],
        fontSize=10,
        textColor=HexColor('#333'),
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        leading=14
    )
    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['BodyText'],
        fontSize=9,
        textColor=HexColor('#666'),
        spaceAfter=4
    )
    insight_style = ParagraphStyle(
        'InsightText',
        parent=styles['BodyText'],
        fontSize=9,
        textColor=HexColor('#ec4899'),
        leftIndent=15,
        spaceAfter=4
    )
    urgency_colors = {
        'immediate': HexColor('#dc3545'),
        'this_week': HexColor('#fd7e14'),
        'this_month': HexColor('#ffc107'),
        'this_quarter': HexColor('#6c757d')
    }

    # Title
    elements.append(Paragraph(f"Briefing: {briefing.get('name', 'Untitled')}", title_style))

    if briefing.get('description'):
        elements.append(Paragraph(f"<i>{briefing.get('description')}</i>", meta_style))

    elements.append(Spacer(1, 10))

    # Metadata table
    meta_data = []
    meta_data.append(['Status:', briefing.get('status', 'draft').title()])
    if briefing.get('finalized_at'):
        meta_data.append(['Finalized:', str(briefing.get('finalized_at'))[:19]])
    meta_data.append(['Created:', str(briefing.get('created_at', 'Unknown'))[:19]])
    if briefing.get('model_used'):
        meta_data.append(['AI Model:', briefing.get('model_used')])

    counts = []
    if briefing.get('articles_count'):
        counts.append(f"{briefing.get('articles_count')} Articles")
    if briefing.get('incidents_count'):
        counts.append(f"{briefing.get('incidents_count')} Incidents")
    if briefing.get('emerging_topics_count'):
        counts.append(f"{briefing.get('emerging_topics_count')} Emerging Topics")
    if counts:
        meta_data.append(['Content:', ' | '.join(counts)])

    if meta_data:
        meta_table = Table(meta_data, colWidths=[80, 400])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#666')),
            ('TEXTCOLOR', (1, 0), (1, -1), HexColor('#333')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta_table)

    elements.append(HRFlowable(width="100%", color=HexColor('#eee'), thickness=1, spaceBefore=15, spaceAfter=15))

    # Executive Summary
    if briefing.get('synthesis'):
        elements.append(Paragraph("Executive Summary", section_style))
        # Handle markdown-style formatting
        synthesis_text = briefing.get('synthesis', '')
        synthesis_text = synthesis_text.replace('**', '<b>').replace('*', '<i>')
        for para in synthesis_text.split('\n\n'):
            if para.strip():
                elements.append(Paragraph(para.strip(), body_style))
        elements.append(Spacer(1, 10))

    # Key Themes
    themes = briefing.get('themes', [])
    if themes:
        elements.append(Paragraph("Key Themes", section_style))
        for theme in themes:
            elements.append(Paragraph(f"<b>{theme.get('theme_name', 'Theme')}</b>", subsection_style))
            if theme.get('description'):
                elements.append(Paragraph(theme.get('description'), body_style))
            if theme.get('supporting_items'):
                items = theme.get('supporting_items')
                if isinstance(items, list):
                    elements.append(Paragraph(f"<i>Supporting: {', '.join(items)}</i>", meta_style))
            if theme.get('strategic_implication'):
                elements.append(Paragraph(f"<b>Strategic Implication:</b> {theme.get('strategic_implication')}", insight_style))
        elements.append(Spacer(1, 10))

    # Priority Actions
    actions = briefing.get('priority_actions', [])
    if actions:
        elements.append(Paragraph("Priority Actions", section_style))
        for action in actions:
            urgency = action.get('urgency', 'this_month')
            urgency_label = urgency.replace('_', ' ').title()
            urgency_color = urgency_colors.get(urgency, HexColor('#6c757d'))

            action_style = ParagraphStyle(
                'ActionText',
                parent=body_style,
                leftIndent=10,
                bulletIndent=0,
            )
            elements.append(Paragraph(
                f"<font color='{urgency_color.hexval()}'><b>[{urgency_label}]</b></font> {action.get('action', '')}",
                action_style
            ))
            if action.get('rationale'):
                elements.append(Paragraph(f"<i>{action.get('rationale')}</i>", meta_style))
        elements.append(Spacer(1, 10))

    # Articles
    articles = briefing.get('articles', [])
    if articles:
        elements.append(Paragraph(f"Articles ({len(articles)})", section_style))
        for i, article in enumerate(articles, 1):
            title = article.get('title', 'Untitled')
            url = article.get('url') or article.get('uri', '')
            # Make title a clickable link if URL is available
            if url and url.startswith('http'):
                elements.append(Paragraph(f"<b>{i}. <a href='{url}' color='blue'>{title}</a></b>", subsection_style))
            else:
                elements.append(Paragraph(f"<b>{i}. {title}</b>", subsection_style))

            meta_parts = []
            if article.get('source'):
                meta_parts.append(f"Source: {article.get('source')}")
            if article.get('publication_date'):
                meta_parts.append(f"Date: {article.get('publication_date')}")
            if article.get('category'):
                meta_parts.append(f"Category: {article.get('category')}")
            if article.get('topic'):
                meta_parts.append(f"Topic: {article.get('topic')}")
            if meta_parts:
                elements.append(Paragraph(' | '.join(meta_parts), meta_style))

            if article.get('summary'):
                elements.append(Paragraph(article.get('summary'), body_style))

            # Analysis
            analysis = article.get('analysis', {}) or {}
            if analysis.get('executive_takeaway'):
                elements.append(Paragraph(f"<b>Why It Matters:</b> {analysis.get('executive_takeaway')}", insight_style))
            if analysis.get('key_insight'):
                elements.append(Paragraph(f"<b>Key Insight:</b> {analysis.get('key_insight')}", insight_style))
            if analysis.get('strategic_relevance'):
                elements.append(Paragraph(f"<b>Strategic Relevance:</b> {analysis.get('strategic_relevance')}", insight_style))
            if analysis.get('time_horizon'):
                elements.append(Paragraph(f"<b>Time Horizon:</b> {analysis.get('time_horizon')}", meta_style))
            if analysis.get('risk_opportunity'):
                elements.append(Paragraph(f"<b>Risk/Opportunity:</b> {analysis.get('risk_opportunity')}", meta_style))

            elements.append(Spacer(1, 8))

    # Incidents
    incidents = briefing.get('incidents', [])
    if incidents:
        elements.append(Paragraph(f"Incidents ({len(incidents)})", section_style))
        for i, incident in enumerate(incidents, 1):
            elements.append(Paragraph(f"<b>{i}. {incident.get('name', 'Untitled')}</b>", subsection_style))

            meta_parts = []
            if incident.get('type'):
                meta_parts.append(f"Type: {incident.get('type')}")
            if incident.get('significance'):
                meta_parts.append(f"Significance: {incident.get('significance')}")
            if incident.get('topic'):
                meta_parts.append(f"Topic: {incident.get('topic')}")
            if meta_parts:
                elements.append(Paragraph(' | '.join(meta_parts), meta_style))

            if incident.get('summary') or incident.get('description'):
                elements.append(Paragraph(incident.get('summary') or incident.get('description'), body_style))

            # Organizational/Strategic relevance
            org_relevance = incident.get('organizational_relevance') or incident.get('strategic_relevance')
            if org_relevance:
                elements.append(Paragraph(f"<b>Strategic Relevance:</b> {org_relevance}", insight_style))

            # Plausibility and source quality badges
            quality_parts = []
            if incident.get('plausibility'):
                quality_parts.append(f"Plausibility: {incident.get('plausibility')}")
            if incident.get('source_quality'):
                quality_parts.append(f"Source Quality: {incident.get('source_quality')}")
            if quality_parts:
                elements.append(Paragraph(' | '.join(quality_parts), meta_style))

            if incident.get('credibility_summary'):
                elements.append(Paragraph(f"<b>Credibility:</b> {incident.get('credibility_summary')}", meta_style))

            # Timeline info
            timeline_parts = []
            if incident.get('first_seen'):
                timeline_parts.append(f"First seen: {incident.get('first_seen')}")
            if incident.get('last_seen'):
                timeline_parts.append(f"Last seen: {incident.get('last_seen')}")
            if timeline_parts:
                elements.append(Paragraph(' | '.join(timeline_parts), meta_style))

            # Entities
            if incident.get('entities'):
                entities = incident.get('entities', [])
                if entities:
                    elements.append(Paragraph(f"<b>Key Entities:</b> {', '.join(entities[:10])}", meta_style))

            # Investigation leads
            if incident.get('investigation_leads'):
                leads = incident.get('investigation_leads', [])
                if leads:
                    elements.append(Paragraph("<b>Investigation Leads:</b>", meta_style))
                    for lead in leads[:5]:
                        elements.append(Paragraph(f"• {lead}", meta_style))

            # Analyst notes
            if incident.get('analyst_notes'):
                notes = incident.get('analyst_notes', [])
                if notes:
                    elements.append(Paragraph("<b>Analyst Notes:</b>", meta_style))
                    for note in notes[:3]:
                        analyst = note.get('analyst', 'Unknown')
                        comment = note.get('comment', '')
                        timestamp = note.get('timestamp', '')[:10] if note.get('timestamp') else ''
                        elements.append(Paragraph(f"• [{timestamp}] {analyst}: {comment[:200]}", meta_style))

            # Analysis (nested)
            analysis = incident.get('analysis', {}) or {}
            if analysis.get('key_insight'):
                elements.append(Paragraph(f"<b>Key Insight:</b> {analysis.get('key_insight')}", insight_style))

            elements.append(Spacer(1, 8))

    # Emerging Topics
    emerging_topics = briefing.get('emerging_topics', [])
    if emerging_topics:
        elements.append(Paragraph(f"Emerging Topics ({len(emerging_topics)})", section_style))
        for i, topic in enumerate(emerging_topics, 1):
            elements.append(Paragraph(f"<b>{i}. {topic.get('name', 'Untitled')}</b>", subsection_style))

            meta_parts = []
            if topic.get('article_count'):
                meta_parts.append(f"{topic.get('article_count')} articles")
            if topic.get('velocity'):
                meta_parts.append(f"Velocity: {topic.get('velocity')}")
            if meta_parts:
                elements.append(Paragraph(' | '.join(meta_parts), meta_style))

            if topic.get('summary'):
                elements.append(Paragraph(topic.get('summary'), body_style))

            if topic.get('key_takeaway'):
                elements.append(Paragraph(f"<b>Key Takeaway:</b> {topic.get('key_takeaway')}", insight_style))

            if topic.get('why_emerging'):
                elements.append(Paragraph(f"<b>Why Emerging:</b> {topic.get('why_emerging')}", insight_style))

            # Key entities
            if topic.get('key_entities'):
                entities = topic.get('key_entities', [])
                if entities:
                    elements.append(Paragraph(f"<b>Key Entities:</b> {', '.join(entities[:10])}", meta_style))

            # Trend score details
            trend_score = topic.get('trend_score', {})
            if isinstance(trend_score, dict) and trend_score:
                score_parts = []
                if trend_score.get('composite'):
                    score_parts.append(f"Composite: {trend_score.get('composite')}")
                if trend_score.get('urgency'):
                    score_parts.append(f"Urgency: {trend_score.get('urgency')}")
                if score_parts:
                    elements.append(Paragraph(f"<b>Trend Score:</b> {' | '.join(score_parts)}", meta_style))

            elements.append(Spacer(1, 8))

    # Footer
    elements.append(HRFlowable(width="100%", color=HexColor('#eee'), thickness=1, spaceBefore=20, spaceAfter=10))
    elements.append(Paragraph("<i>Exported from Briefing Desk - AuNoo AI</i>", meta_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
