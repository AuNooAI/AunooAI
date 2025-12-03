"""
Executive Briefing API Routes

Provides endpoints for:
- Generating executive briefings from article analysis
- Managing briefing configuration and prompts
- Save/Load/Delete briefings
- Export (JSON, Markdown, HTML)
- Podcast generation
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import logging
from datetime import datetime, timedelta

from app.services.executive_briefing_service import (
    get_executive_briefing_service,
    EBConfig,
    DEFAULT_PERSONAS
)
from app.security.session import verify_session
from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/executive-briefing", tags=["Executive Briefing"])


# ============================================================================
# Request/Response Models
# ============================================================================

class EBScanRequest(BaseModel):
    """Request model for starting an executive briefing generation."""
    topic: str = Field(
        ...,
        description="Topic to generate executive briefing for"
    )
    persona: str = Field(
        "CEO",
        description="Executive persona (CEO/CMO/CTO/CISO or custom)"
    )
    article_count: int = Field(
        6,
        ge=1,
        le=8,
        description="Number of articles to include (1-8)"
    )
    days_back: int = Field(
        7,
        ge=1,
        le=90,
        description="Days of articles to consider"
    )
    custom_persona: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom persona configuration (overrides persona)"
    )
    include_synthesis: bool = Field(
        True,
        description="Whether to include synthesis stage"
    )
    include_podcast_script: bool = Field(
        False,
        description="Whether to generate a podcast script"
    )
    podcast_duration: str = Field(
        "short",
        description="Podcast script duration: short, medium, long"
    )
    stream: bool = Field(
        True,
        description="Whether to stream progress updates"
    )


# ============================================================================
# Streaming Helper
# ============================================================================

def fetch_articles_for_topic(topic: str, days_back: int = 7, limit: int = 100) -> List[Dict]:
    """Fetch recent articles for a topic from the database with enrichment data."""
    try:
        db = get_database_instance()
        facade = DatabaseQueryFacade(db, logger)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Use the facade's article fetching method (synchronous)
        articles = facade.get_articles_for_date_range(
            start_date=start_date,
            end_date=end_date,
            topic=topic,
            limit=limit
        )

        # Format articles for the briefing service
        formatted_articles = []
        for article in articles:
            enrichment = article.get("enrichment", {})
            if isinstance(enrichment, str):
                try:
                    enrichment = json.loads(enrichment)
                except:
                    enrichment = {}

            formatted_articles.append({
                "id": article.get("id"),
                "title": article.get("title", "Untitled"),
                "uri": article.get("uri") or article.get("url", ""),
                "url": article.get("uri") or article.get("url", ""),
                "news_source": article.get("news_source") or article.get("source", "Unknown"),
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "publication_date": article.get("publication_date") or article.get("published_at"),
                "date": article.get("publication_date") or article.get("published_at"),
                "summary": (article.get("summary", "") or "")[:800],
                "sentiment": article.get("sentiment", "neutral"),
                "bias": article.get("bias", "unknown"),
                "factual_reporting": article.get("factual_reporting", ""),
                "driver_type": article.get("driver_type", ""),
                "enrichment": enrichment
            })

        return formatted_articles
    except Exception as e:
        logger.warning(f"Failed to fetch articles for executive briefing: {e}")
        return []


async def stream_eb_progress(
    topic: str,
    articles: List[Dict],
    config: EBConfig
):
    """Generator that yields SSE events for executive briefing progress."""
    service = get_executive_briefing_service()

    try:
        async for update in service.run_generation(
            topic=topic,
            articles=articles,
            config=config
        ):
            # If complete, inject the article count into the response
            if update.get("stage") == "complete":
                update["total_articles"] = len(articles)

            # Format as Server-Sent Event
            event_data = json.dumps(update, default=str)
            yield f"data: {event_data}\n\n"

            # If complete or error, stop streaming
            if update.get("stage") in ["complete", "error"]:
                break

    except Exception as e:
        logger.error(f"Executive briefing stream error: {e}", exc_info=True)
        error_event = json.dumps({
            "stage": "error",
            "status": "failed",
            "error": str(e)
        })
        yield f"data: {error_event}\n\n"


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/scan")
async def start_eb_generation(
    request: EBScanRequest,
    session: dict = Depends(verify_session)
):
    """
    Start Executive Briefing generation.

    Analyzes articles to create persona-based executive briefings with
    actionable insights and strategic recommendations.

    If stream=True, returns a streaming response with progress updates.
    If stream=False, waits for completion and returns the full result.
    """
    # Fetch articles first
    articles = fetch_articles_for_topic(request.topic, days_back=request.days_back, limit=100)
    logger.info(f"Executive Briefing: Fetched {len(articles)} articles for topic '{request.topic}'")

    if len(articles) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient articles for executive briefing. Found {len(articles)}, need at least 3."
        )

    # Build config
    config = EBConfig(
        persona=request.persona,
        custom_persona=request.custom_persona,
        article_count=min(request.article_count, len(articles)),
        days_back=request.days_back,
        include_synthesis=request.include_synthesis,
        include_podcast_script=request.include_podcast_script,
        podcast_duration=request.podcast_duration
    )

    if request.stream:
        # Return streaming response
        return StreamingResponse(
            stream_eb_progress(
                topic=request.topic,
                articles=articles,
                config=config
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Run synchronously and return full result
        service = get_executive_briefing_service()
        result = None

        async for update in service.run_generation(
            topic=request.topic,
            articles=articles,
            config=config
        ):
            result = update
            if update.get("stage") in ["complete", "error"]:
                break

        if result and result.get("stage") == "complete":
            return {
                "success": True,
                "scan_id": result.get("scan_id"),
                "articles": result.get("articles"),
                "briefing_summary": result.get("briefing_summary"),
                "themes": result.get("themes"),
                "priority_actions": result.get("priority_actions"),
                "risk_summary": result.get("risk_summary"),
                "opportunity_summary": result.get("opportunity_summary"),
                "focus_areas": result.get("focus_areas"),
                "metadata": result.get("metadata"),
                "total_articles": len(articles)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Generation failed") if result else "Generation failed"
            )


@router.get("/health")
async def health_check():
    """Health check endpoint for Executive Briefing service."""
    try:
        service = get_executive_briefing_service()
        return {
            "status": "healthy",
            "service": "executive_briefing",
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# Executive Briefing Configuration Endpoints
# ============================================================================

EB_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "auspex" / "eb_config.json"


@router.get("/config")
async def get_eb_config(
    topic: Optional[str] = None,
    session: dict = Depends(verify_session)
):
    """
    Get the Executive Briefing configuration settings.

    If topic is provided, returns topic-specific config from database.
    Otherwise returns global config from file.
    """
    default_config = {
        "personas": DEFAULT_PERSONAS,
        "default_persona": "CEO",
        "default_article_count": 6,
        "default_days_back": 7,
        "include_synthesis": True,
        "agents": {
            "selection": {"model": None, "temperature": 0.3},
            "analysis": {"model": None, "temperature": 0.4},
            "synthesis": {"model": None, "temperature": 0.5}
        }
    }

    try:
        # Try topic-specific config from database first
        if topic:
            db = get_database_instance()
            topic_config = db.facade.get_eb_config(topic)
            if topic_config:
                return {**default_config, **topic_config}

        # Fall back to file-based config
        if EB_CONFIG_FILE.exists():
            with open(EB_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}

        return default_config
    except Exception as e:
        logger.error(f"Failed to read EB config: {e}")
        return default_config


@router.get("/config/defaults")
async def get_eb_defaults():
    """Get factory default Executive Briefing configuration."""
    return {
        "personas": DEFAULT_PERSONAS,
        "default_persona": "CEO",
        "default_article_count": 6,
        "default_days_back": 7,
        "include_synthesis": True,
        "agents": {
            "selection": {"model": None, "temperature": 0.3},
            "analysis": {"model": None, "temperature": 0.4},
            "synthesis": {"model": None, "temperature": 0.5}
        }
    }


class EBConfigUpdate(BaseModel):
    """Request model for updating Executive Briefing config."""
    topic: Optional[str] = Field(None, description="Topic to save config for (if topic-specific)")
    personas: Optional[Dict[str, Dict[str, str]]] = Field(None, description="Custom persona configurations")
    default_persona: Optional[str] = Field(None, description="Default persona to use")
    default_article_count: Optional[int] = Field(None, ge=1, le=8)
    default_days_back: Optional[int] = Field(None, ge=1, le=90)
    include_synthesis: Optional[bool] = None
    agents: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="Agent model/temperature settings")


@router.put("/config")
async def update_eb_config(
    request: EBConfigUpdate,
    session: dict = Depends(verify_session)
):
    """
    Update the Executive Briefing configuration settings.

    If topic is provided, saves to database (topic-specific).
    Otherwise saves to global config file.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    try:
        # Load existing config
        if request.topic:
            # Topic-specific config from database
            db = get_database_instance()
            config = db.facade.get_eb_config(request.topic) or {}
        else:
            # Global config from file
            if EB_CONFIG_FILE.exists():
                with open(EB_CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            else:
                config = {}

        # Update only provided fields
        if request.personas is not None:
            config["personas"] = request.personas
        if request.default_persona is not None:
            config["default_persona"] = request.default_persona
        if request.default_article_count is not None:
            config["default_article_count"] = request.default_article_count
        if request.default_days_back is not None:
            config["default_days_back"] = request.default_days_back
        if request.include_synthesis is not None:
            config["include_synthesis"] = request.include_synthesis
        if request.agents is not None:
            config["agents"] = request.agents

        # Save config
        if request.topic:
            # Save to database
            db.facade.update_eb_config(request.topic, username, config)
        else:
            # Save to file
            EB_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(EB_CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)

        logger.info(f"Executive Briefing config updated by user {username}")

        return {
            "success": True,
            "config": config
        }

    except Exception as e:
        logger.error(f"Failed to update EB config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Executive Briefing Prompt Management Endpoints
# ============================================================================

EB_AGENTS = [
    {
        "id": "eb_selection_agent",
        "name": "Selection",
        "description": "Scores and selects top N articles based on persona criteria",
        "file": "eb_selection_agent.md"
    },
    {
        "id": "eb_analysis_agent",
        "name": "Analysis",
        "description": "Generates executive analysis for each selected article",
        "file": "eb_analysis_agent.md"
    },
    {
        "id": "eb_synthesis_agent",
        "name": "Synthesis",
        "description": "Creates briefing summary, cross-article themes, priority actions",
        "file": "eb_synthesis_agent.md"
    },
    {
        "id": "eb_podcast_agent",
        "name": "Podcast",
        "description": "Generates professional podcast scripts from executive briefing content",
        "file": "eb_podcast_agent.md"
    }
]


@router.get("/prompts")
async def list_eb_prompts(
    session: dict = Depends(verify_session)
):
    """
    List all Executive Briefing agent prompts with their current content.
    """
    import yaml

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"

    prompts = []
    for agent in EB_AGENTS:
        agent_file = agents_dir / agent["file"]
        content = ""
        metadata = {}

        if agent_file.exists():
            with open(agent_file, 'r') as f:
                raw_content = f.read()

            # Parse frontmatter and content
            if raw_content.startswith('---'):
                parts = raw_content.split('---', 2)
                if len(parts) >= 3:
                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                    except:
                        metadata = {}
                    content = parts[2].strip()
                else:
                    content = raw_content
            else:
                content = raw_content

        prompts.append({
            "id": agent["id"],
            "name": agent["name"],
            "description": agent["description"],
            "content": content,
            "metadata": metadata
        })

    return {
        "success": True,
        "prompts": prompts
    }


@router.get("/prompts/{agent_id}")
async def get_eb_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """Get a specific Executive Briefing agent prompt by ID."""
    import yaml

    agent = next((a for a in EB_AGENTS if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"
    agent_file = agents_dir / agent["file"]

    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent file not found")

    with open(agent_file, 'r') as f:
        raw_content = f.read()

    content = ""
    metadata = {}

    if raw_content.startswith('---'):
        parts = raw_content.split('---', 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
            except:
                metadata = {}
            content = parts[2].strip()
        else:
            content = raw_content
    else:
        content = raw_content

    return {
        "success": True,
        "id": agent["id"],
        "name": agent["name"],
        "description": agent["description"],
        "content": content,
        "metadata": metadata,
        "raw": raw_content
    }


class UpdateEBPromptRequest(BaseModel):
    content: str = Field(..., description="The new prompt content (markdown after frontmatter)")
    model: Optional[str] = Field(None, description="AI model to use for this agent")
    temperature: Optional[float] = Field(None, description="Temperature setting (0.0-1.0)")


@router.put("/prompts/{agent_id}")
async def update_eb_prompt(
    agent_id: str,
    request: UpdateEBPromptRequest,
    session: dict = Depends(verify_session)
):
    """
    Update an Executive Briefing agent prompt, model, and temperature settings.
    """
    import yaml

    agent = next((a for a in EB_AGENTS if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"
    agent_file = agents_dir / agent["file"]

    # Read existing file or create new metadata
    metadata = {}
    if agent_file.exists():
        with open(agent_file, 'r') as f:
            raw_content = f.read()

        if raw_content.startswith('---'):
            parts = raw_content.split('---', 2)
            if len(parts) >= 3:
                try:
                    metadata = yaml.safe_load(parts[1]) or {}
                except:
                    metadata = {}

    # Update model_config if model or temperature provided
    if request.model is not None or request.temperature is not None:
        if 'model_config' not in metadata:
            metadata['model_config'] = {}

        if request.model is not None:
            metadata['model_config']['model'] = request.model

        if request.temperature is not None:
            metadata['model_config']['temperature'] = request.temperature

    # Ensure basic metadata exists
    if 'name' not in metadata:
        metadata['name'] = agent['id']
    if 'version' not in metadata:
        metadata['version'] = '1.0.0'
    if 'type' not in metadata:
        metadata['type'] = 'agent'
    if 'category' not in metadata:
        metadata['category'] = 'executive_briefing'

    # Rebuild the file with updated frontmatter
    frontmatter_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    new_content = f"---\n{frontmatter_str}---\n\n{request.content.strip()}\n"

    # Ensure directory exists
    agents_dir.mkdir(parents=True, exist_ok=True)

    with open(agent_file, 'w') as f:
        f.write(new_content)

    logger.info(f"Updated EB agent: {agent_id} (model={request.model}, temp={request.temperature})")

    return {
        "success": True,
        "message": f"Updated {agent['name']} agent configuration"
    }


# ============================================================================
# Saved Executive Briefings CRUD Endpoints
# ============================================================================

class SaveEBRequest(BaseModel):
    """Request model for saving an executive briefing."""
    topic: str = Field(..., description="Topic name")
    name: str = Field(..., min_length=1, max_length=255, description="Briefing name")
    description: Optional[str] = Field(None, description="Optional description")
    persona: str = Field(..., description="Executive persona used")
    article_count: int = Field(..., description="Number of articles requested")
    articles: List[Dict[str, Any]] = Field(..., description="The analyzed articles")
    briefing_summary: Optional[str] = Field(None, description="Synthesis narrative")
    themes: Optional[List[Dict[str, Any]]] = Field(None, description="Cross-article themes")
    priority_actions: Optional[List[Dict[str, Any]]] = Field(None, description="Recommended actions")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration used to generate")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Generation metadata")
    articles_used: Optional[int] = Field(None, description="Number of articles used")
    article_uris: Optional[List[str]] = Field(None, description="List of article URIs used")
    model_used: Optional[str] = Field(None, description="AI model used")


@router.post("/save")
async def save_executive_briefing(
    request: SaveEBRequest,
    session: dict = Depends(verify_session)
):
    """
    Save an executive briefing to the database.

    Creates a new saved briefing instance with articles and metadata.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()

    # Check for duplicate name
    existing = db.facade.get_saved_executive_briefings_for_topic(request.topic, username)
    if any(e["name"] == request.name for e in existing):
        raise HTTPException(409, f"Briefing '{request.name}' already exists for this topic")

    try:
        briefing_id = db.facade.create_saved_executive_briefing(
            topic=request.topic,
            username=username,
            name=request.name,
            persona=request.persona,
            article_count=request.article_count,
            articles=request.articles,
            briefing_summary=request.briefing_summary,
            themes=request.themes,
            priority_actions=request.priority_actions,
            config=request.config,
            metadata=request.metadata,
            articles_used=request.articles_used,
            article_uris=request.article_uris,
            model_used=request.model_used,
            description=request.description
        )

        logger.info(f"Saved executive briefing '{request.name}' (ID: {briefing_id}) for user '{username}'")

        return {
            "success": True,
            "briefing_id": briefing_id,
            "message": f"Briefing '{request.name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to save executive briefing: {e}")
        raise HTTPException(500, f"Failed to save briefing: {str(e)}")


@router.get("/saved/{topic}")
async def list_saved_executive_briefings(
    topic: str,
    session: dict = Depends(verify_session)
):
    """
    Get all saved executive briefings for a topic (current user only).

    Returns a list of briefing summaries sorted by creation date.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefings = db.facade.get_saved_executive_briefings_for_topic(topic, username)

    return {
        "success": True,
        "saved_briefings": briefings
    }


@router.get("/saved/load/{briefing_id}")
async def load_executive_briefing(
    briefing_id: int,
    session: dict = Depends(verify_session)
):
    """
    Load a specific saved executive briefing with full content.

    Returns complete briefing including articles and metadata.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_saved_executive_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    logger.info(f"Loaded executive briefing {briefing_id} for user '{username}'")

    return {
        "success": True,
        "briefing": briefing
    }


@router.delete("/saved/{briefing_id}")
async def delete_executive_briefing(
    briefing_id: int,
    session: dict = Depends(verify_session)
):
    """
    Delete a saved executive briefing.

    Removes the briefing. This action cannot be undone.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.delete_saved_executive_briefing(briefing_id, username)

    if not success:
        raise HTTPException(404, "Briefing not found or permission denied")

    logger.info(f"Deleted executive briefing {briefing_id} for user '{username}'")

    return {
        "success": True,
        "message": "Briefing deleted successfully"
    }


# ============================================================================
# Article Editing Endpoint
# ============================================================================

class UpdateArticleRequest(BaseModel):
    """Request model for updating an article within a briefing."""
    updates: Dict[str, Any] = Field(..., description="Fields to update in the article")


@router.put("/saved/{briefing_id}/article/{article_index}")
async def update_article(
    briefing_id: int,
    article_index: int,
    request: UpdateArticleRequest,
    session: dict = Depends(verify_session)
):
    """
    Update a specific article within a saved executive briefing.

    Allows inline editing of article attributes and user notes.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    success = db.facade.update_executive_briefing_article(
        briefing_id=briefing_id,
        username=username,
        article_index=article_index,
        article_updates=request.updates
    )

    if not success:
        raise HTTPException(404, "Briefing or article not found")

    logger.info(f"Updated article {article_index} in briefing {briefing_id}")

    return {
        "success": True,
        "message": "Article updated successfully"
    }


# ============================================================================
# Export Endpoints
# ============================================================================

@router.get("/saved/{briefing_id}/export")
async def export_executive_briefing(
    briefing_id: int,
    format: str = "json",
    session: dict = Depends(verify_session)
):
    """
    Export an executive briefing in various formats.

    Formats:
    - json: Full JSON export
    - markdown: Readable markdown document
    - html: HTML document for sharing
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    db = get_database_instance()
    briefing = db.facade.get_saved_executive_briefing_by_id(briefing_id, username)

    if not briefing:
        raise HTTPException(404, "Briefing not found")

    if format == "json":
        return Response(
            content=json.dumps(briefing, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=executive_briefing_{briefing_id}.json"
            }
        )

    elif format == "markdown":
        md_content = _generate_markdown_export(briefing)
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=executive_briefing_{briefing_id}.md"
            }
        )

    elif format == "html":
        html_content = _generate_html_export(briefing)
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=executive_briefing_{briefing_id}.html"
            }
        )

    else:
        raise HTTPException(400, f"Unknown export format: {format}")


def _generate_markdown_export(briefing: Dict) -> str:
    """Generate a markdown document from an executive briefing."""
    lines = []
    lines.append(f"# Executive Briefing: {briefing.get('name', 'Untitled')}")
    lines.append("")
    lines.append(f"**Topic:** {briefing.get('topic', 'Unknown')}")
    lines.append(f"**Persona:** {briefing.get('persona', 'CEO')}")
    lines.append(f"**Created:** {briefing.get('created_at', 'Unknown')}")
    lines.append(f"**Articles:** {briefing.get('articles_used', 0)}")
    lines.append("")

    if briefing.get('description'):
        lines.append(f"*{briefing.get('description')}*")
        lines.append("")

    # Briefing Summary
    if briefing.get('briefing_summary'):
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(briefing.get('briefing_summary'))
        lines.append("")

    # Themes
    themes = briefing.get('themes', [])
    if themes:
        lines.append("## Key Themes")
        lines.append("")
        for theme in themes:
            lines.append(f"### {theme.get('theme_name', 'Theme')}")
            lines.append(f"{theme.get('description', '')}")
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

    # Articles
    articles = briefing.get('articles', [])
    if articles:
        lines.append("## Articles")
        lines.append("")

        for i, article in enumerate(articles, 1):
            lines.append(f"### {i}. {article.get('title', 'Untitled')}")
            lines.append("")
            lines.append(f"**Source:** {article.get('source', 'Unknown')} | **Date:** {article.get('date', 'Unknown')}")
            lines.append("")

            if article.get('executive_takeaway'):
                lines.append(f"**Executive Takeaway:** {article.get('executive_takeaway')}")
                lines.append("")

            if article.get('summary'):
                lines.append(f"**Summary:** {article.get('summary')}")
                lines.append("")

            if article.get('strategic_relevance'):
                lines.append(f"**Strategic Relevance:** {article.get('strategic_relevance')}")
                lines.append("")

            # Classifications
            horizon = article.get('time_horizon', 'Medium')
            risk_opp = article.get('risk_opportunity', 'mixed').title()
            signal = article.get('signal_strength', 'moderate').title()
            lines.append(f"**Time Horizon:** {horizon} | **Assessment:** {risk_opp} | **Signal:** {signal}")
            lines.append("")

            # Actions
            actions = article.get('executive_action', [])
            if actions:
                lines.append("**Actions:**")
                for action in actions:
                    lines.append(f"- {action}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Risk/Opportunity Summary
    risk = briefing.get('risk_summary', {})
    opp = briefing.get('opportunity_summary', {})

    if risk or opp:
        lines.append("## Risk & Opportunity Assessment")
        lines.append("")

        if risk:
            level = risk.get('overall_risk_level', 'moderate').title()
            lines.append(f"**Risk Level:** {level}")
            for r in risk.get('key_risks', []):
                lines.append(f"- {r}")
            lines.append("")

        if opp:
            level = opp.get('overall_opportunity_level', 'moderate').title()
            lines.append(f"**Opportunity Level:** {level}")
            for o in opp.get('key_opportunities', []):
                lines.append(f"- {o}")
            lines.append("")

    lines.append("---")
    lines.append("*Exported from Executive Briefing Generator*")

    return "\n".join(lines)


def _generate_html_export(briefing: Dict) -> str:
    """Generate an HTML document from an executive briefing."""
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
    <title>Executive Briefing: {briefing.get('name', 'Untitled')}</title>
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


# ============================================================================
# Podcast Script Generation Endpoint
# ============================================================================

class GeneratePodcastScriptRequest(BaseModel):
    """Request model for LLM-powered podcast script generation."""
    topic: str = Field(..., description="Topic of the executive briefing")
    briefing_summary: str = Field(..., description="Executive summary text")
    themes: List[Dict[str, Any]] = Field(default_factory=list, description="Key themes from the briefing")
    priority_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Priority actions")
    articles: List[Dict[str, Any]] = Field(default_factory=list, description="Analyzed articles")
    duration: str = Field("short", description="Script duration: short, medium, long")
    model: str = Field("gpt-4o", description="LLM model to use for script generation")


EB_PODCAST_SCRIPT_PROMPT = """You are an expert podcast script writer creating an executive intelligence briefing.

Create a concise, engaging podcast script for an executive audience. The script should:
1. Be written for a single presenter (news bulletin style)
2. Open with a brief welcome and topic introduction
3. Summarize the key intelligence findings
4. Highlight the most important themes and their strategic implications
5. Mention specific priority actions executives should consider
6. Close with a brief sign-off

Guidelines:
- Keep the tone professional but engaging
- Focus on strategic implications, not just facts
- Make it conversational but authoritative
- Target duration: {duration_guidance}
- Do NOT include sound effects, music cues, or stage directions
- Do NOT include speaker tags like [Host] or timestamps
- Write as continuous prose that flows naturally when read aloud

Topic: {topic}

Executive Summary:
{briefing_summary}

Key Themes:
{themes_text}

Priority Actions:
{actions_text}

Generate a polished podcast script that an executive would want to listen to during their commute."""


@router.post("/generate-podcast-script")
async def generate_eb_podcast_script(
    request: GeneratePodcastScriptRequest,
    session: dict = Depends(verify_session)
):
    """
    Generate a podcast script from executive briefing data using an LLM.

    Takes the briefing summary, themes, and priority actions and creates
    a professional podcast script suitable for TTS conversion.
    """
    from app.ai_models import LiteLLMModel

    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    if not request.briefing_summary:
        raise HTTPException(400, "Briefing summary is required")

    # Duration guidance
    duration_map = {
        "short": "2-3 minutes (approximately 400-500 words)",
        "medium": "4-5 minutes (approximately 700-900 words)",
        "long": "7-10 minutes (approximately 1200-1500 words)"
    }
    duration_guidance = duration_map.get(request.duration, duration_map["short"])

    # Format themes
    themes_text = ""
    if request.themes:
        for i, theme in enumerate(request.themes[:5], 1):
            theme_name = theme.get('theme_name', 'Unknown Theme')
            description = theme.get('description', '')
            implication = theme.get('strategic_implication', '')
            themes_text += f"{i}. {theme_name}\n   {description}\n"
            if implication:
                themes_text += f"   Strategic Implication: {implication}\n"
            themes_text += "\n"
    else:
        themes_text = "No specific themes identified."

    # Format priority actions
    actions_text = ""
    if request.priority_actions:
        for i, action in enumerate(request.priority_actions[:5], 1):
            action_text = action.get('action', '')
            urgency = action.get('urgency', 'this_month').replace('_', ' ')
            rationale = action.get('rationale', '')
            actions_text += f"{i}. [{urgency.upper()}] {action_text}\n"
            if rationale:
                actions_text += f"   Rationale: {rationale}\n"
            actions_text += "\n"
    else:
        actions_text = "No specific actions recommended."

    # Load agent prompt and config if available
    agent_prompt = None
    agent_config = {}
    try:
        service = get_executive_briefing_service()
        agent_prompt = service._load_agent_prompt("eb_podcast_agent")
        agent_config = service._get_agent_config("eb_podcast_agent")
    except Exception as e:
        logger.warning(f"Could not load podcast agent config: {e}")

    # Build system prompt from agent or fallback
    if agent_prompt:
        system_prompt = agent_prompt
    else:
        system_prompt = EB_PODCAST_SCRIPT_PROMPT.format(
            duration_guidance=duration_guidance,
            topic=request.topic,
            briefing_summary=request.briefing_summary,
            themes_text=themes_text,
            actions_text=actions_text
        )

    # User message with briefing content
    user_message = f"""Generate a podcast script with these specifications:

Target Duration: {duration_guidance}

Topic: {request.topic}

Executive Summary:
{request.briefing_summary}

Key Themes:
{themes_text}

Priority Actions:
{actions_text}

Generate a polished podcast script that an executive would want to listen to during their commute."""

    try:
        # Use model from agent config or request
        model_name = agent_config.get('model', request.model)

        # Get the AI model
        model = LiteLLMModel.get_instance(model_name)
        if not model:
            raise HTTPException(500, f"Failed to initialize {model_name} model")

        # Generate the script
        if agent_prompt:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate the podcast script now."}
            ]

        logger.info(f"Generating EB podcast script for topic: {request.topic}, duration: {request.duration}, model: {model_name}")
        script = model.generate_response(messages)

        if not script:
            raise HTTPException(500, "Model returned empty response")

        logger.info(f"Generated EB podcast script, length: {len(script)} chars")

        return {
            "success": True,
            "script": script,
            "topic": request.topic,
            "duration": request.duration,
            "character_count": len(script),
            "model_used": model_name
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating EB podcast script: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to generate podcast script: {str(e)}")


# ============================================================================
# Podcast Generation Endpoint (Legacy)
# ============================================================================

class PodcastRequest(BaseModel):
    """Request model for podcast generation."""
    briefing_id: Optional[int] = Field(None, description="Saved briefing ID to generate podcast from")
    articles: Optional[List[Dict[str, Any]]] = Field(None, description="Articles to generate podcast from (if not using saved)")
    briefing_summary: Optional[str] = Field(None, description="Briefing summary for podcast script")
    voice_id: Optional[str] = Field(None, description="ElevenLabs voice ID")


@router.post("/podcast")
async def generate_podcast(
    request: PodcastRequest,
    session: dict = Depends(verify_session)
):
    """
    Generate an audio podcast from an executive briefing.

    Uses ElevenLabs to convert the briefing into audio format.
    """
    # Extract username from session
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")

    if not username:
        raise HTTPException(401, "User not authenticated")

    # Get briefing content
    if request.briefing_id:
        db = get_database_instance()
        briefing = db.facade.get_saved_executive_briefing_by_id(request.briefing_id, username)
        if not briefing:
            raise HTTPException(404, "Briefing not found")

        articles = briefing.get('articles', [])
        summary = briefing.get('briefing_summary', '')
    else:
        articles = request.articles or []
        summary = request.briefing_summary or ''

    if not articles and not summary:
        raise HTTPException(400, "No content provided for podcast generation")

    # Generate podcast script
    script_parts = []

    if summary:
        script_parts.append(f"Executive Briefing Summary. {summary}")

    for i, article in enumerate(articles[:6], 1):
        takeaway = article.get('executive_takeaway', '')
        if takeaway:
            script_parts.append(f"Article {i}. {article.get('title', 'Untitled')}. {takeaway}")

    script = " ".join(script_parts)

    # TODO: Integrate with ElevenLabs API for audio generation
    # For now, return a placeholder response
    return {
        "success": True,
        "message": "Podcast generation initiated",
        "script_preview": script[:500] + "..." if len(script) > 500 else script,
        "status": "pending",
        "note": "ElevenLabs integration pending"
    }
