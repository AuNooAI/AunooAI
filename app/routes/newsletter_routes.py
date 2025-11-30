"""
Newsletter Generation Routes
SSE streaming endpoint for newsletter generation with the newsletter_generator plugin
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import get_database_instance
from app.services.tool_loader import get_tool_loader
from app.services.auspex_tools import get_auspex_tools_service
from app.services.tool_plugin_base import get_tool_registry
from app.ai_models import LiteLLMModel
from app.vector_store import search_articles as vector_search_articles
from app.security.session import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/newsletter", tags=["newsletter"])


class NewsletterGenerateRequest(BaseModel):
    topic: str
    days_back: int = 7
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    deep_dive_topic: Optional[str] = None
    model: Optional[str] = None


class AgentConfig(BaseModel):
    """Configuration for a single agent."""
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class NewsletterConfigUpdate(BaseModel):
    """Request model for updating Newsletter config."""
    title: Optional[str] = None
    intro: Optional[str] = None
    days_back: Optional[int] = Field(None, ge=1, le=30)
    deep_dive_topic: Optional[str] = None
    section_limits: Optional[Dict[str, int]] = None
    agents: Optional[Dict[str, AgentConfig]] = None


# Path to newsletter config file
NEWSLETTER_CONFIG_FILE = Path("/home/orochford/tenants/testbed.aunoo.ai/data/auspex/newsletter_config.json")


def load_newsletter_config() -> Dict[str, Any]:
    """Load newsletter config from JSON file."""
    default_config = {
        "title": "Weekly Intelligence Digest",
        "intro": "",
        "days_back": 7,
        "deep_dive_topic": "",
        "agents": {
            "deep_dive": {"model": "gpt-4.1", "temperature": 0.3, "max_tokens": 4000},
            "main_newsletter": {"model": "gpt-4.1", "temperature": 0.5, "max_tokens": 8000}
        }
    }

    if NEWSLETTER_CONFIG_FILE.exists():
        try:
            with open(NEWSLETTER_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading newsletter config: {e}")
            return default_config
    return default_config


def save_newsletter_config(config: Dict[str, Any]) -> None:
    """Save newsletter config to JSON file."""
    NEWSLETTER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NEWSLETTER_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_ai_model_getter(model_name: str = None):
    """Get AI model function for the newsletter generator."""
    def getter(name: str = None):
        actual_name = name or model_name or 'gpt-4.1'
        return LiteLLMModel(actual_name)
    return getter


@router.post("/generate")
async def generate_newsletter(request: Request, body: NewsletterGenerateRequest):
    """
    Generate a newsletter with SSE streaming progress updates.

    Streams events:
    - stage: fetching/categorizing/generating/complete
    - progress: 0-1 progress within stage
    - articles_found: count during fetching
    - categorized_count: count during categorizing
    - chunk: text chunk during generation
    - newsletter: final content on complete
    - articles: available articles list on complete
    """

    async def generate():
        logger.info(f"📰 Starting newsletter generation for topic: {body.topic}")
        db = get_database_instance()
        tool_registry = get_tool_registry()

        try:
            # Get the newsletter generator from tool registry (plugin system)
            logger.info("📰 Getting newsletter_generator from tool registry...")
            tool_def = tool_registry.get_tool("newsletter_generator")
            logger.info(f"📰 Tool definition: {tool_def}")
            if not tool_def:
                yield f"data: {json.dumps({'stage': 'error', 'error': 'Newsletter generator plugin not found'})}\n\n"
                return

            handler = tool_registry.get_handler("newsletter_generator")
            logger.info(f"📰 Handler: {handler}")
            if not handler:
                yield f"data: {json.dumps({'stage': 'error', 'error': 'No handler for newsletter generator'})}\n\n"
                return

            # Stage 1: Fetching - send initial event
            yield f"data: {json.dumps({'stage': 'fetching', 'progress': 0, 'status': 'started'})}\n\n"
            await asyncio.sleep(0.1)

            # Prepare context
            context = {
                "db": db,
                "vector_store": vector_search_articles,
                "ai_model": get_ai_model_getter(body.model),
                "topic": body.topic,
                "model": body.model or "gpt-4.1",
            }

            # Prepare params
            params = {
                "topic": body.topic,
                "days_back": body.days_back,
            }
            if body.start_date:
                params["start_date"] = body.start_date
            if body.end_date:
                params["end_date"] = body.end_date
            if body.deep_dive_topic:
                params["deep_dive_topic"] = body.deep_dive_topic

            # Stage 1 progress simulation (actual fetching happens inside execute)
            yield f"data: {json.dumps({'stage': 'fetching', 'progress': 0.3})}\n\n"
            await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'stage': 'fetching', 'progress': 0.6})}\n\n"
            await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'stage': 'fetching', 'progress': 1.0, 'articles_found': 100})}\n\n"

            # Stage 2: Categorizing
            yield f"data: {json.dumps({'stage': 'categorizing', 'progress': 0})}\n\n"
            await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'stage': 'categorizing', 'progress': 0.5, 'categorized_count': 50})}\n\n"
            await asyncio.sleep(0.1)
            yield f"data: {json.dumps({'stage': 'categorizing', 'progress': 1.0, 'categorized_count': 100})}\n\n"

            # Stage 3: Generating
            yield f"data: {json.dumps({'stage': 'generating', 'progress': 0})}\n\n"

            # Execute via tool_registry
            logger.info(f"📰 Executing newsletter_generator with params: {params}")
            result = await tool_registry.execute_tool("newsletter_generator", params, context)
            logger.info(f"📰 Result: success={result.success}, error={result.error}")

            if not result.success:
                yield f"data: {json.dumps({'stage': 'error', 'error': result.error or 'Generation failed'})}\n\n"
                return

            # Send generating progress
            yield f"data: {json.dumps({'stage': 'generating', 'progress': 0.8})}\n\n"
            await asyncio.sleep(0.1)

            # Prepare articles list for frontend
            articles = []
            # The result.data contains the newsletter output
            result_data = result.data if result.data else {}

            # Stage 4: Complete
            yield f"data: {json.dumps({'stage': 'generating', 'progress': 1.0})}\n\n"
            await asyncio.sleep(0.1)

            complete_data = {
                "stage": "complete",
                "status": "success",
                "newsletter": result_data.get("analysis", ""),
                "article_count": result_data.get("article_count", 0),
                "articles_used": result_data.get("articles_used", 0),
                "section_counts": result_data.get("section_counts", {}),
                "metatrends": result_data.get("metatrends", []),
                "deep_dive_topic": result_data.get("deep_dive_topic", ""),
                "articles": articles,
            }
            yield f"data: {json.dumps(complete_data)}\n\n"

        except Exception as e:
            logger.error(f"Newsletter generation error: {e}", exc_info=True)
            yield f"data: {json.dumps({'stage': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/config")
async def get_newsletter_config(
    session: dict = Depends(verify_session)
):
    """Get the current newsletter configuration."""
    tool_registry = get_tool_registry()
    tool_def = tool_registry.get_tool("newsletter_generator")

    # Get plugin config (static settings like section limits)
    plugin_config = tool_def.config if tool_def and hasattr(tool_def, 'config') else {}

    # Get user config (dynamic settings like title, model preferences)
    user_config = load_newsletter_config()

    # Merge section_limits: user config takes precedence over plugin defaults
    default_section_limits = plugin_config.get("section_limits", {})
    user_section_limits = user_config.get("section_limits", {})
    merged_section_limits = {**default_section_limits, **user_section_limits}

    return {
        # User configurable settings
        "title": user_config.get("title", "Weekly Intelligence Digest"),
        "intro": user_config.get("intro", ""),
        "days_back": user_config.get("days_back", 7),
        "deep_dive_topic": user_config.get("deep_dive_topic", ""),
        "agents": user_config.get("agents", {
            "deep_dive": {"model": "gpt-4.1", "temperature": 0.3, "max_tokens": 4000},
            "main_newsletter": {"model": "gpt-4.1", "temperature": 0.5, "max_tokens": 8000}
        }),
        # Section limits (user overrides plugin defaults)
        "section_limits": merged_section_limits,
        # Plugin settings (read-only)
        "version": plugin_config.get("version", "2.0.0"),
        "model": plugin_config.get("model", "gpt-4.1"),
        "max_articles_to_fetch": plugin_config.get("max_articles_to_fetch", 200),
        "min_articles_required": plugin_config.get("min_articles_required", 20),
        "sections": plugin_config.get("sections", {}),
    }


@router.put("/config")
async def update_newsletter_config(
    request: NewsletterConfigUpdate,
    session: dict = Depends(verify_session)
):
    """Update newsletter configuration settings."""
    try:
        # Load existing config
        config = load_newsletter_config()

        # Update provided fields
        if request.title is not None:
            config["title"] = request.title
        if request.intro is not None:
            config["intro"] = request.intro
        if request.days_back is not None:
            config["days_back"] = request.days_back
        if request.deep_dive_topic is not None:
            config["deep_dive_topic"] = request.deep_dive_topic
        if request.section_limits is not None:
            config["section_limits"] = request.section_limits
        if request.agents is not None:
            # Merge agent configs
            existing_agents = config.get("agents", {})
            for agent_name, agent_config in request.agents.items():
                if agent_name not in existing_agents:
                    existing_agents[agent_name] = {}
                agent_dict = agent_config.model_dump(exclude_none=True)
                existing_agents[agent_name].update(agent_dict)
            config["agents"] = existing_agents

        # Save config
        save_newsletter_config(config)

        logger.info(f"Newsletter config updated: {config}")
        return {"success": True, "config": config}
    except Exception as e:
        logger.error(f"Error updating newsletter config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Newsletter Prompt Management Endpoints (following SIO pattern)
# ============================================================================

NEWSLETTER_AGENTS = [
    {
        "id": "newsletter_deep_dive_agent",
        "name": "Deep Dive",
        "description": "Generates deep dive analysis with consensus and credibility evaluation",
        "file": "newsletter_deep_dive_agent.md"
    },
    {
        "id": "newsletter_main_agent",
        "name": "Main Newsletter",
        "description": "Generates the full newsletter with The News, Deep Dive, Weird Sh*t, Must Reads, Metatrends, and Market Updates",
        "file": "newsletter_main_agent.md"
    }
]

AGENTS_DIR = Path("/home/orochford/tenants/testbed.aunoo.ai/data/auspex/agents")


def parse_agent_file(file_path: Path) -> tuple[str, dict]:
    """Parse an agent .md file and return content and metadata."""
    import yaml

    if not file_path.exists():
        return "", {}

    with open(file_path, 'r') as f:
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

    return content, metadata


@router.get("/prompts")
async def list_newsletter_prompts(
    session: dict = Depends(verify_session)
):
    """
    List all Newsletter agent prompts with their current content.

    Returns metadata and content for each Newsletter stage:
    - Deep Dive: in-depth analysis with consensus evaluation
    - Main Newsletter: full newsletter generation
    """
    prompts = []
    for agent in NEWSLETTER_AGENTS:
        agent_file = AGENTS_DIR / agent["file"]
        content, metadata = parse_agent_file(agent_file)

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
async def get_newsletter_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """Get a specific Newsletter agent prompt by ID."""
    agent = next((a for a in NEWSLETTER_AGENTS if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent_file = AGENTS_DIR / agent["file"]

    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent file not found")

    with open(agent_file, 'r') as f:
        raw_content = f.read()

    content, metadata = parse_agent_file(agent_file)

    return {
        "success": True,
        "id": agent["id"],
        "name": agent["name"],
        "description": agent["description"],
        "content": content,
        "metadata": metadata,
        "raw": raw_content
    }


class UpdatePromptRequest(BaseModel):
    """Request model for updating an agent prompt."""
    content: str = Field(..., description="The new prompt content (markdown after frontmatter)")
    model: Optional[str] = Field(None, description="AI model to use for this agent")
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description="Temperature setting (0.0-1.0)")


@router.put("/prompts/{agent_id}")
async def update_newsletter_prompt(
    agent_id: str,
    request: UpdatePromptRequest,
    session: dict = Depends(verify_session)
):
    """
    Update a Newsletter agent prompt, model, and temperature settings.

    Updates the markdown content and optionally the model_config in frontmatter.
    """
    import yaml

    agent = next((a for a in NEWSLETTER_AGENTS if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent_file = AGENTS_DIR / agent["file"]

    if not agent_file.exists():
        raise HTTPException(status_code=404, detail=f"Agent file not found")

    # Read existing file to get frontmatter
    with open(agent_file, 'r') as f:
        raw_content = f.read()

    metadata = {}
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

    # Rebuild the file with updated frontmatter
    frontmatter_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    new_content = f"---\n{frontmatter_str}---\n\n{request.content.strip()}\n"

    with open(agent_file, 'w') as f:
        f.write(new_content)

    logger.info(f"Updated Newsletter agent: {agent_id} (model={request.model}, temp={request.temperature})")

    return {
        "success": True,
        "message": f"Updated {agent['name']} agent configuration"
    }


# ============================================================================
# Saved Newsletters Endpoints (following saved_dashboards pattern)
# ============================================================================

class SaveNewsletterRequest(BaseModel):
    """Request model for saving a newsletter."""
    topic: str = Field(..., description="Topic name")
    name: str = Field(..., min_length=1, max_length=255, description="Newsletter name")
    description: Optional[str] = Field(None, description="Optional description")
    newsletter_content: str = Field(..., description="The generated newsletter content (markdown)")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration used to generate")
    days_back: Optional[int] = Field(None, description="Days back setting")
    deep_dive_topic: Optional[str] = Field(None, description="Deep dive topic if specified")
    deep_dive_analysis: Optional[str] = Field(None, description="Deep dive analysis content")
    articles_used: Optional[int] = Field(None, description="Number of articles used")
    article_uris: Optional[list] = Field(None, description="List of article URIs used")
    model_used: Optional[str] = Field(None, description="AI model used")


@router.post("/save")
async def save_newsletter(
    request: SaveNewsletterRequest,
    session: dict = Depends(verify_session)
):
    """
    Save a generated newsletter to the database.

    Creates a new saved newsletter instance with content and metadata.
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
    existing = db.facade.get_saved_newsletters_for_topic(request.topic, username)
    if any(n["name"] == request.name for n in existing):
        raise HTTPException(409, f"Newsletter '{request.name}' already exists for this topic")

    try:
        newsletter_id = db.facade.create_saved_newsletter(
            topic=request.topic,
            username=username,
            name=request.name,
            newsletter_content=request.newsletter_content,
            config=request.config,
            days_back=request.days_back,
            deep_dive_topic=request.deep_dive_topic,
            deep_dive_analysis=request.deep_dive_analysis,
            articles_used=request.articles_used,
            article_uris=request.article_uris,
            model_used=request.model_used,
            description=request.description
        )

        logger.info(f"Saved newsletter '{request.name}' (ID: {newsletter_id}) for user '{username}'")

        return {
            "success": True,
            "newsletter_id": newsletter_id,
            "message": f"Newsletter '{request.name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to save newsletter: {e}")
        raise HTTPException(500, f"Failed to save newsletter: {str(e)}")


@router.get("/saved/{topic}")
async def list_saved_newsletters(
    topic: str,
    session: dict = Depends(verify_session)
):
    """
    Get all saved newsletters for a topic (current user only).

    Returns a list of newsletter summaries sorted by creation date.
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
    newsletters = db.facade.get_saved_newsletters_for_topic(topic, username)

    return {
        "success": True,
        "newsletters": newsletters
    }


@router.get("/saved/load/{newsletter_id}")
async def load_newsletter(
    newsletter_id: int,
    session: dict = Depends(verify_session)
):
    """
    Load a specific saved newsletter with full content.

    Returns complete newsletter including content and metadata.
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
    newsletter = db.facade.get_saved_newsletter_by_id(newsletter_id, username)

    if not newsletter:
        raise HTTPException(404, "Newsletter not found")

    logger.info(f"Loaded newsletter {newsletter_id} for user '{username}'")

    return {
        "success": True,
        "newsletter": newsletter
    }


@router.delete("/saved/{newsletter_id}")
async def delete_newsletter(
    newsletter_id: int,
    session: dict = Depends(verify_session)
):
    """
    Delete a saved newsletter.

    Removes the newsletter. This action cannot be undone.
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
    success = db.facade.delete_saved_newsletter(newsletter_id, username)

    if not success:
        raise HTTPException(404, "Newsletter not found or permission denied")

    logger.info(f"Deleted newsletter {newsletter_id} for user '{username}'")

    return {
        "success": True,
        "message": "Newsletter deleted successfully"
    }
