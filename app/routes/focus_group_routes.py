"""
Synthetic Focus Group API Routes

Provides endpoints for:
- Generating synthetic stakeholder personas from article analysis
- Managing focus group configuration and prompts
- Save/Load/Delete focus groups
- Persona editing
- Export (JSON, Markdown, PDF)
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import logging
from datetime import datetime, timedelta

from app.services.focus_group_service import (
    get_focus_group_service,
    FGConfig
)
from app.security.session import verify_session, verify_session_api
from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/focus-groups", tags=["Focus Groups"])


# ============================================================================
# Request/Response Models
# ============================================================================

class FGScanRequest(BaseModel):
    """Request model for starting a focus group generation."""
    topic: str = Field(
        ...,
        description="Topic to generate focus group personas for"
    )
    max_personas: int = Field(
        6,
        ge=1,
        le=6,
        description="Maximum number of personas to generate (1-6)"
    )
    min_evidence_threshold: int = Field(
        2,
        ge=1,
        le=5,
        description="Minimum article mentions required to create a persona"
    )
    include_demographics: bool = Field(
        True,
        description="Include demographic attributes in personas"
    )
    include_psychographics: bool = Field(
        True,
        description="Include psychographic attributes in personas"
    )
    include_voice: bool = Field(
        True,
        description="Include voice/querying attributes for future LLM interaction"
    )
    stream: bool = Field(
        True,
        description="Whether to stream progress updates"
    )


# ============================================================================
# Streaming Helper
# ============================================================================

def fetch_articles_for_topic(topic: str, days_back: int = 30, limit: int = 100) -> List[Dict]:
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

        # Format articles for the focus group service
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
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "published_at": article.get("publication_date") or article.get("published_at"),
                "summary": (article.get("summary", "") or "")[:500],
                "enrichment": enrichment
            })

        return formatted_articles
    except Exception as e:
        logger.warning(f"Failed to fetch articles for focus group: {e}")
        return []


async def stream_fg_progress(
    topic: str,
    articles: List[Dict],
    config: FGConfig
):
    """Generator that yields SSE events for focus group progress."""
    service = get_focus_group_service()

    try:
        async for update in service.run_generation(
            topic=topic,
            articles=articles,
            config=config
        ):
            # If complete, inject the article count into the response
            if update.get("stage") == "complete":
                update["article_count"] = len(articles)

            # Format as Server-Sent Event
            event_data = json.dumps(update, default=str)
            yield f"data: {event_data}\n\n"

            # If complete or error, stop streaming
            if update.get("stage") in ["complete", "error"]:
                break

    except Exception as e:
        logger.error(f"Focus group stream error: {e}", exc_info=True)
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
async def start_fg_generation(
    request: FGScanRequest,
    session: dict = Depends(verify_session)
):
    """
    Start Synthetic Focus Group generation.

    Analyzes articles to discover stakeholder personas with rich
    psychographic profiles (15-20 attributes each).

    If stream=True, returns a streaming response with progress updates.
    If stream=False, waits for completion and returns the full result.
    """
    # Fetch articles first
    articles = fetch_articles_for_topic(request.topic, days_back=30, limit=100)
    logger.info(f"Focus Group: Fetched {len(articles)} articles for topic '{request.topic}'")

    if len(articles) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient articles for focus group analysis. Found {len(articles)}, need at least 5."
        )

    # Build config
    config = FGConfig(
        max_personas=request.max_personas,
        min_evidence_threshold=request.min_evidence_threshold,
        include_demographics=request.include_demographics,
        include_psychographics=request.include_psychographics,
        include_voice=request.include_voice
    )

    if request.stream:
        # Return streaming response
        return StreamingResponse(
            stream_fg_progress(
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
        service = get_focus_group_service()
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
                "personas": result.get("personas"),
                "focus_group_summary": result.get("focus_group_summary"),
                "interaction_dynamics": result.get("interaction_dynamics"),
                "metadata": result.get("metadata"),
                "article_count": len(articles)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Generation failed") if result else "Generation failed"
            )


@router.get("/health", dependencies=[Depends(verify_session_api)])
async def health_check():
    """Health check endpoint for Focus Group service."""
    try:
        service = get_focus_group_service()
        return {
            "status": "healthy",
            "service": "focus_group",
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# Focus Group Configuration Endpoints
# ============================================================================

FG_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "auspex" / "fg_config.json"


@router.get("/config")
async def get_fg_config(
    session: dict = Depends(verify_session)
):
    """
    Get the global Focus Group configuration settings.
    """
    default_config = {
        "max_personas": 6,
        "min_evidence_threshold": 2,
        "include_demographics": True,
        "include_psychographics": True,
        "include_voice": True
    }

    try:
        if FG_CONFIG_FILE.exists():
            with open(FG_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        return default_config
    except Exception as e:
        logger.error(f"Failed to read FG config: {e}")
        return default_config


class FGConfigUpdate(BaseModel):
    """Request model for updating Focus Group config."""
    max_personas: Optional[int] = Field(None, ge=1, le=6)
    min_evidence_threshold: Optional[int] = Field(None, ge=1, le=5)
    include_demographics: Optional[bool] = None
    include_psychographics: Optional[bool] = None
    include_voice: Optional[bool] = None


@router.put("/config")
async def update_fg_config(
    request: FGConfigUpdate,
    session: dict = Depends(verify_session)
):
    """
    Update the global Focus Group configuration settings.
    """
    try:
        # Load existing config or use defaults
        if FG_CONFIG_FILE.exists():
            with open(FG_CONFIG_FILE, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "max_personas": 6,
                "min_evidence_threshold": 2,
                "include_demographics": True,
                "include_psychographics": True,
                "include_voice": True
            }

        # Update only provided fields
        if request.max_personas is not None:
            config["max_personas"] = request.max_personas
        if request.min_evidence_threshold is not None:
            config["min_evidence_threshold"] = request.min_evidence_threshold
        if request.include_demographics is not None:
            config["include_demographics"] = request.include_demographics
        if request.include_psychographics is not None:
            config["include_psychographics"] = request.include_psychographics
        if request.include_voice is not None:
            config["include_voice"] = request.include_voice

        # Ensure directory exists
        FG_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save config
        with open(FG_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"Focus Group config updated: {config}")

        return {
            "success": True,
            "config": config
        }

    except Exception as e:
        logger.error(f"Failed to update FG config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Focus Group Prompt Management Endpoints
# ============================================================================

FG_AGENTS = [
    {
        "id": "fg_discovery_agent",
        "name": "Discovery",
        "description": "Extracts stakeholder mentions from articles using enrichment data",
        "file": "fg_discovery_agent.md"
    },
    {
        "id": "fg_clustering_agent",
        "name": "Clustering",
        "description": "Groups mentions into distinct persona archetypes (1-6 based on evidence)",
        "file": "fg_clustering_agent.md"
    },
    {
        "id": "fg_profiling_agent",
        "name": "Profiling",
        "description": "Builds rich psychographic profiles for each discovered archetype",
        "file": "fg_profiling_agent.md"
    },
    {
        "id": "fg_synthesis_agent",
        "name": "Synthesis",
        "description": "Creates focus group dynamics - consensus, tensions, diversity",
        "file": "fg_synthesis_agent.md"
    }
]


@router.get("/prompts")
async def list_fg_prompts(
    session: dict = Depends(verify_session)
):
    """
    List all Focus Group agent prompts with their current content.
    """
    import yaml

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"

    prompts = []
    for agent in FG_AGENTS:
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
async def get_fg_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """Get a specific Focus Group agent prompt by ID."""
    import yaml

    agent = next((a for a in FG_AGENTS if a["id"] == agent_id), None)
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


class UpdateFGPromptRequest(BaseModel):
    content: str = Field(..., description="The new prompt content (markdown after frontmatter)")
    model: Optional[str] = Field(None, description="AI model to use for this agent")
    temperature: Optional[float] = Field(None, description="Temperature setting (0.0-1.0)")


@router.put("/prompts/{agent_id}")
async def update_fg_prompt(
    agent_id: str,
    request: UpdateFGPromptRequest,
    session: dict = Depends(verify_session)
):
    """
    Update a Focus Group agent prompt, model, and temperature settings.
    """
    import yaml

    agent = next((a for a in FG_AGENTS if a["id"] == agent_id), None)
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
        metadata['category'] = 'focus_group'

    # Rebuild the file with updated frontmatter
    frontmatter_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    new_content = f"---\n{frontmatter_str}---\n\n{request.content.strip()}\n"

    # Ensure directory exists
    agents_dir.mkdir(parents=True, exist_ok=True)

    with open(agent_file, 'w') as f:
        f.write(new_content)

    logger.info(f"Updated FG agent: {agent_id} (model={request.model}, temp={request.temperature})")

    return {
        "success": True,
        "message": f"Updated {agent['name']} agent configuration"
    }


# ============================================================================
# Saved Focus Groups CRUD Endpoints
# ============================================================================

class SaveFGRequest(BaseModel):
    """Request model for saving a focus group."""
    topic: str = Field(..., description="Topic name")
    name: str = Field(..., min_length=1, max_length=255, description="Focus group name")
    description: Optional[str] = Field(None, description="Optional description")
    personas: List[Dict[str, Any]] = Field(..., description="The generated personas")
    focus_group_summary: Optional[str] = Field(None, description="Focus group narrative summary")
    interaction_dynamics: Optional[Dict[str, Any]] = Field(None, description="Consensus areas, tension points, etc.")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration used to generate")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Generation metadata")
    articles_used: Optional[int] = Field(None, description="Number of articles used")
    article_uris: Optional[List[str]] = Field(None, description="List of article URIs used")
    model_used: Optional[str] = Field(None, description="AI model used")
    persona_count: Optional[int] = Field(None, description="Number of personas")


@router.post("/save")
async def save_focus_group(
    request: SaveFGRequest,
    session: dict = Depends(verify_session)
):
    """
    Save a focus group to the database.

    Creates a new saved focus group instance with personas and metadata.
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
    existing = db.facade.get_saved_focus_groups_for_topic(request.topic, username)
    if any(e["name"] == request.name for e in existing):
        raise HTTPException(409, f"Focus group '{request.name}' already exists for this topic")

    try:
        fg_id = db.facade.create_saved_focus_group(
            topic=request.topic,
            username=username,
            name=request.name,
            personas=request.personas,
            focus_group_summary=request.focus_group_summary,
            interaction_dynamics=request.interaction_dynamics,
            config=request.config,
            metadata=request.metadata,
            articles_used=request.articles_used,
            article_uris=request.article_uris,
            model_used=request.model_used,
            persona_count=request.persona_count,
            description=request.description
        )

        logger.info(f"Saved focus group '{request.name}' (ID: {fg_id}) for user '{username}'")

        return {
            "success": True,
            "focus_group_id": fg_id,
            "message": f"Focus group '{request.name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to save focus group: {e}")
        raise HTTPException(500, f"Failed to save focus group: {str(e)}")


@router.get("/saved/{topic}")
async def list_saved_focus_groups(
    topic: str,
    session: dict = Depends(verify_session)
):
    """
    Get all saved focus groups for a topic (current user only).

    Returns a list of focus group summaries sorted by creation date.
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
    fg_list = db.facade.get_saved_focus_groups_for_topic(topic, username)

    return {
        "success": True,
        "saved_focus_groups": fg_list
    }


@router.get("/saved/load/{focus_group_id}")
async def load_focus_group(
    focus_group_id: int,
    session: dict = Depends(verify_session)
):
    """
    Load a specific saved focus group with full content.

    Returns complete focus group including personas and metadata.
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
    fg = db.facade.get_saved_focus_group_by_id(focus_group_id, username)

    if not fg:
        raise HTTPException(404, "Focus group not found")

    logger.info(f"Loaded focus group {focus_group_id} for user '{username}'")

    return {
        "success": True,
        "focus_group": fg
    }


@router.delete("/saved/{focus_group_id}")
async def delete_focus_group(
    focus_group_id: int,
    session: dict = Depends(verify_session)
):
    """
    Delete a saved focus group.

    Removes the focus group. This action cannot be undone.
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
    success = db.facade.delete_saved_focus_group(focus_group_id, username)

    if not success:
        raise HTTPException(404, "Focus group not found or permission denied")

    logger.info(f"Deleted focus group {focus_group_id} for user '{username}'")

    return {
        "success": True,
        "message": "Focus group deleted successfully"
    }


# ============================================================================
# Persona Editing Endpoint
# ============================================================================

class UpdatePersonaRequest(BaseModel):
    """Request model for updating a persona within a focus group."""
    updates: Dict[str, Any] = Field(..., description="Fields to update in the persona")


@router.put("/saved/{focus_group_id}/persona/{persona_id}")
async def update_persona(
    focus_group_id: int,
    persona_id: str,
    request: UpdatePersonaRequest,
    session: dict = Depends(verify_session)
):
    """
    Update a specific persona within a saved focus group.

    Allows inline editing of persona attributes and user notes.
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
    success = db.facade.update_focus_group_persona(
        focus_group_id=focus_group_id,
        username=username,
        persona_id=persona_id,
        persona_updates=request.updates
    )

    if not success:
        raise HTTPException(404, "Focus group or persona not found")

    logger.info(f"Updated persona {persona_id} in focus group {focus_group_id}")

    return {
        "success": True,
        "message": "Persona updated successfully"
    }


# ============================================================================
# Export Endpoints
# ============================================================================

@router.get("/saved/{focus_group_id}/export")
async def export_focus_group(
    focus_group_id: int,
    format: str = "json",
    session: dict = Depends(verify_session)
):
    """
    Export a focus group in various formats.

    Formats:
    - json: Full JSON export
    - markdown: Readable markdown document
    - pdf: PDF document (requires additional setup)
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
    fg = db.facade.get_saved_focus_group_by_id(focus_group_id, username)

    if not fg:
        raise HTTPException(404, "Focus group not found")

    if format == "json":
        return Response(
            content=json.dumps(fg, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=focus_group_{focus_group_id}.json"
            }
        )

    elif format == "markdown":
        md_content = _generate_markdown_export(fg)
        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=focus_group_{focus_group_id}.md"
            }
        )

    elif format == "pdf":
        # PDF generation would require additional libraries like reportlab or weasyprint
        raise HTTPException(501, "PDF export not yet implemented")

    else:
        raise HTTPException(400, f"Unknown export format: {format}")


def _generate_markdown_export(fg: Dict) -> str:
    """Generate a markdown document from a focus group."""
    lines = []
    lines.append(f"# Focus Group: {fg.get('name', 'Untitled')}")
    lines.append("")
    lines.append(f"**Topic:** {fg.get('topic', 'Unknown')}")
    lines.append(f"**Created:** {fg.get('created_at', 'Unknown')}")
    lines.append(f"**Personas:** {fg.get('persona_count', 0)}")
    lines.append(f"**Articles Analyzed:** {fg.get('articles_used', 0)}")
    lines.append("")

    if fg.get('description'):
        lines.append(f"*{fg.get('description')}*")
        lines.append("")

    # Focus Group Summary
    if fg.get('focus_group_summary'):
        lines.append("## Focus Group Summary")
        lines.append("")
        lines.append(fg.get('focus_group_summary'))
        lines.append("")

    # Personas
    personas = fg.get('personas', [])
    if personas:
        lines.append("## Personas")
        lines.append("")

        for i, persona in enumerate(personas, 1):
            lines.append(f"### {i}. {persona.get('name', 'Unknown')} - {persona.get('archetype', 'Unknown')}")
            lines.append("")
            lines.append(f"**Role:** {persona.get('role_title', 'Unknown')} | **Sector:** {persona.get('sector', 'Unknown')}")
            lines.append("")

            # Values & Attitudes
            lines.append("**Values & Attitudes:**")
            lines.append(f"- Primary Values: {', '.join(persona.get('primary_values', []))}")
            lines.append(f"- Risk Tolerance: {persona.get('risk_tolerance', 0.5):.1f}")
            lines.append(f"- Change Receptivity: {persona.get('change_receptivity', 'unknown')}")
            lines.append(f"- Technology Stance: {persona.get('technology_stance', 'unknown')}")
            lines.append("")

            # Concerns
            lines.append("**Concerns:**")
            lines.append(f"- Primary: {', '.join(persona.get('primary_concerns', []))}")
            lines.append(f"- Fear Triggers: {', '.join(persona.get('fear_triggers', []))}")
            lines.append(f"- Opportunities: {', '.join(persona.get('opportunity_interests', []))}")
            lines.append("")

            # Voice
            if persona.get('voice_description'):
                lines.append("**Voice:**")
                lines.append(f"{persona.get('voice_description')}")
                lines.append("")

            if persona.get('typical_questions'):
                lines.append("**Typical Questions:**")
                for q in persona.get('typical_questions', []):
                    lines.append(f"- {q}")
                lines.append("")

            if persona.get('user_notes'):
                lines.append("**User Notes:**")
                lines.append(f"_{persona.get('user_notes')}_")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Interaction Dynamics
    dynamics = fg.get('interaction_dynamics', {})
    if dynamics:
        lines.append("## Interaction Dynamics")
        lines.append("")

        if dynamics.get('consensus_areas'):
            lines.append("### Consensus Areas")
            for area in dynamics.get('consensus_areas', []):
                lines.append(f"- **{area.get('topic', 'Unknown')}**: {area.get('description', '')}")
            lines.append("")

        if dynamics.get('tension_points'):
            lines.append("### Tension Points")
            for tension in dynamics.get('tension_points', []):
                lines.append(f"- **{tension.get('topic', 'Unknown')}**: {tension.get('description', '')}")
            lines.append("")

        if dynamics.get('key_insight'):
            lines.append("### Key Insight")
            lines.append(dynamics.get('key_insight'))
            lines.append("")

        if dynamics.get('blind_spots'):
            lines.append("### Blind Spots")
            for blind_spot in dynamics.get('blind_spots', []):
                lines.append(f"- {blind_spot}")
            lines.append("")

    lines.append("---")
    lines.append("*Exported from Synthetic Focus Group Generator*")

    return "\n".join(lines)
