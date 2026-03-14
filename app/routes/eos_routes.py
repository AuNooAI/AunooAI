"""
Extreme Outlier Scenarios (EOS) API Routes

Provides endpoints for:
- Generating extreme outlier scenarios (Black Swan, Contrarian, Wild Card)
- Managing EOS agent prompts
- Configuration management
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import logging
from datetime import datetime, timedelta

from app.services.extreme_outlier_service import (
    get_extreme_outlier_service,
    EOSConfig
)
from app.security.session import verify_session
from app.database import get_database_instance
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/eos", tags=["Extreme Outlier Scenarios"])


# ============================================================================
# Request/Response Models
# ============================================================================

class EOSScanRequest(BaseModel):
    """Request model for starting an EOS generation."""
    topic: str = Field(
        ...,
        description="Topic to generate outlier scenarios for (must have existing analysis)"
    )
    scenario_count: int = Field(
        5,
        ge=1,
        le=10,
        description="Number of scenarios to generate"
    )
    include_black_swans: bool = Field(
        True,
        description="Include Black Swan scenarios (unpredictable high-impact)"
    )
    include_contrarian: bool = Field(
        True,
        description="Include Contrarian scenarios (against consensus)"
    )
    include_wild_cards: bool = Field(
        True,
        description="Include Wild Card scenarios (low probability disruptions)"
    )
    time_horizon: str = Field(
        "mid",
        description="Time horizon focus: near (0-2y), mid (2-5y), long (5-10y)"
    )
    source_analysis: Optional[Dict] = Field(
        None,
        description="Existing analysis data to build scenarios from"
    )
    stream: bool = Field(
        True,
        description="Whether to stream progress updates"
    )


# ============================================================================
# Streaming Helper
# ============================================================================

def fetch_articles_for_topic(topic: str, days_back: int = 30, limit: int = 100) -> List[Dict]:
    """Fetch recent articles for a topic from the database."""
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

        # Format articles for frontend
        formatted_articles = []
        for article in articles:
            formatted_articles.append({
                "id": article.get("id"),
                "title": article.get("title", "Untitled"),
                "uri": article.get("uri") or article.get("url", ""),
                "source": article.get("news_source") or article.get("source", "Unknown"),
                "published_at": article.get("publication_date") or article.get("published_at"),
                "summary": (article.get("summary", "") or "")[:200]
            })

        return formatted_articles
    except Exception as e:
        logger.warning(f"Failed to fetch articles for EOS: {e}")
        return []


async def stream_eos_progress(
    topic: str,
    source_analysis: Dict,
    config: EOSConfig
):
    """Generator that yields SSE events for EOS progress."""
    service = get_extreme_outlier_service()

    # Pre-fetch articles for this topic
    articles = fetch_articles_for_topic(topic, days_back=30, limit=100)
    logger.info(f"EOS: Fetched {len(articles)} articles for topic '{topic}'")

    try:
        async for update in service.run_generation(
            topic=topic,
            source_analysis=source_analysis,
            config=config,
            raw_articles=articles
        ):
            # If complete, inject the articles into the response
            if update.get("stage") == "complete":
                update["articles"] = articles

            # Format as Server-Sent Event
            event_data = json.dumps(update, default=str)
            yield f"data: {event_data}\n\n"

            # If complete or error, stop streaming
            if update.get("stage") in ["complete", "error"]:
                break

    except Exception as e:
        logger.error(f"EOS stream error: {e}", exc_info=True)
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
async def start_eos_generation(
    request: EOSScanRequest,
    session: dict = Depends(verify_session)
):
    """
    Start Extreme Outlier Scenarios generation.

    Analyzes existing trend convergence data and generates
    Black Swan, Contrarian, and Wild Card scenarios.

    If stream=True, returns a streaming response with progress updates.
    If stream=False, waits for completion and returns the full result.
    """
    # Build config
    config = EOSConfig(
        scenario_count=request.scenario_count,
        include_black_swans=request.include_black_swans,
        include_contrarian=request.include_contrarian,
        include_wild_cards=request.include_wild_cards,
        time_horizon=request.time_horizon
    )

    # Use provided source analysis or empty dict
    source_analysis = request.source_analysis or {}

    if request.stream:
        # Return streaming response
        return StreamingResponse(
            stream_eos_progress(
                topic=request.topic,
                source_analysis=source_analysis,
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
        service = get_extreme_outlier_service()
        result = None

        # Fetch articles for non-streaming response
        articles = fetch_articles_for_topic(request.topic, days_back=30, limit=100)

        async for update in service.run_generation(
            topic=request.topic,
            source_analysis=source_analysis,
            config=config,
            raw_articles=articles
        ):
            result = update
            if update.get("stage") in ["complete", "error"]:
                break

        if result and result.get("stage") == "complete":
            return {
                "success": True,
                "scan_id": result.get("scan_id"),
                "scenarios": result.get("scenarios"),
                "metadata": result.get("metadata"),
                "articles": articles
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Generation failed") if result else "Generation failed"
            )


@router.get("/health")
async def health_check():
    """Health check endpoint for EOS service."""
    try:
        service = get_extreme_outlier_service()
        return {
            "status": "healthy",
            "service": "extreme_outlier_scenarios",
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# EOS Configuration Endpoints
# ============================================================================

# Path to EOS config file
EOS_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "auspex" / "eos_config.json"


@router.get("/config")
async def get_eos_config(
    session: dict = Depends(verify_session)
):
    """
    Get the global EOS configuration settings.
    """
    # Default config
    default_config = {
        "scenario_count": 5,
        "include_black_swans": True,
        "include_contrarian": True,
        "include_wild_cards": True,
        "time_horizon": "mid"
    }

    try:
        if EOS_CONFIG_FILE.exists():
            with open(EOS_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        return default_config
    except Exception as e:
        logger.error(f"Failed to read EOS config: {e}")
        return default_config


class EOSConfigUpdate(BaseModel):
    """Request model for updating EOS config."""
    scenario_count: Optional[int] = Field(None, ge=1, le=10)
    include_black_swans: Optional[bool] = None
    include_contrarian: Optional[bool] = None
    include_wild_cards: Optional[bool] = None
    time_horizon: Optional[str] = None


@router.put("/config")
async def update_eos_config(
    request: EOSConfigUpdate,
    session: dict = Depends(verify_session)
):
    """
    Update the global EOS configuration settings.
    """
    try:
        # Load existing config or use defaults
        if EOS_CONFIG_FILE.exists():
            with open(EOS_CONFIG_FILE, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "scenario_count": 5,
                "include_black_swans": True,
                "include_contrarian": True,
                "include_wild_cards": True,
                "time_horizon": "mid"
            }

        # Update only provided fields
        if request.scenario_count is not None:
            config["scenario_count"] = request.scenario_count
        if request.include_black_swans is not None:
            config["include_black_swans"] = request.include_black_swans
        if request.include_contrarian is not None:
            config["include_contrarian"] = request.include_contrarian
        if request.include_wild_cards is not None:
            config["include_wild_cards"] = request.include_wild_cards
        if request.time_horizon is not None:
            config["time_horizon"] = request.time_horizon

        # Ensure directory exists
        EOS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save config
        with open(EOS_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"EOS config updated: {config}")

        return {
            "success": True,
            "config": config
        }

    except Exception as e:
        logger.error(f"Failed to update EOS config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EOS Prompt Management Endpoints
# ============================================================================

EOS_AGENTS = [
    {
        "id": "eos_weak_signals_agent",
        "name": "Weak Signals",
        "description": "Detects faint patterns and overlooked signals in trend data",
        "file": "eos_weak_signals_agent.md"
    },
    {
        "id": "eos_amplification_agent",
        "name": "Amplification",
        "description": "Models how weak signals could cascade into major disruptions",
        "file": "eos_amplification_agent.md"
    },
    {
        "id": "eos_scenario_building_agent",
        "name": "Scenario Building",
        "description": "Constructs detailed extreme outlier scenario narratives",
        "file": "eos_scenario_building_agent.md"
    },
    {
        "id": "eos_implications_agent",
        "name": "Implications",
        "description": "Generates strategic hedging recommendations and early warning indicators",
        "file": "eos_implications_agent.md"
    }
]


@router.get("/prompts")
async def list_eos_prompts(
    session: dict = Depends(verify_session)
):
    """
    List all EOS agent prompts with their current content.

    Returns metadata and content for each of the 4 EOS stages:
    - Weak Signals: Pattern detection in existing analysis
    - Amplification: Cascade modeling
    - Scenario Building: Narrative construction
    - Implications: Strategic recommendations
    """
    import yaml

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"

    prompts = []
    for agent in EOS_AGENTS:
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
async def get_eos_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """Get a specific EOS agent prompt by ID."""
    import yaml

    agent = next((a for a in EOS_AGENTS if a["id"] == agent_id), None)
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


class UpdateEOSPromptRequest(BaseModel):
    content: str = Field(..., description="The new prompt content (markdown after frontmatter)")
    model: Optional[str] = Field(None, description="AI model to use for this agent")
    temperature: Optional[float] = Field(None, description="Temperature setting (0.0-1.0)")


@router.put("/prompts/{agent_id}")
async def update_eos_prompt(
    agent_id: str,
    request: UpdateEOSPromptRequest,
    session: dict = Depends(verify_session)
):
    """
    Update an EOS agent prompt, model, and temperature settings.
    """
    import yaml

    agent = next((a for a in EOS_AGENTS if a["id"] == agent_id), None)
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
        metadata['category'] = 'extreme_outlier_scenarios'

    # Rebuild the file with updated frontmatter
    frontmatter_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    new_content = f"---\n{frontmatter_str}---\n\n{request.content.strip()}\n"

    # Ensure directory exists
    agents_dir.mkdir(parents=True, exist_ok=True)

    with open(agent_file, 'w') as f:
        f.write(new_content)

    logger.info(f"Updated EOS agent: {agent_id} (model={request.model}, temp={request.temperature})")

    return {
        "success": True,
        "message": f"Updated {agent['name']} agent configuration"
    }


# ============================================================================
# Saved EOS Endpoints (following saved_newsletters pattern)
# ============================================================================

class SaveEOSRequest(BaseModel):
    """Request model for saving an EOS analysis."""
    topic: str = Field(..., description="Topic name")
    name: str = Field(..., min_length=1, max_length=255, description="EOS analysis name")
    description: Optional[str] = Field(None, description="Optional description")
    scenarios: List[Dict[str, Any]] = Field(..., description="The generated scenarios")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration used to generate")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Analysis metadata")
    articles_used: Optional[int] = Field(None, description="Number of articles used")
    article_uris: Optional[List[str]] = Field(None, description="List of article URIs used")
    model_used: Optional[str] = Field(None, description="AI model used")
    time_horizon: Optional[str] = Field(None, description="Time horizon setting")
    scenario_count: Optional[int] = Field(None, description="Number of scenarios")


@router.post("/save")
async def save_eos(
    request: SaveEOSRequest,
    session: dict = Depends(verify_session)
):
    """
    Save an EOS analysis to the database.

    Creates a new saved EOS instance with scenarios and metadata.
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
    existing = db.facade.get_saved_eos_for_topic(request.topic, username)
    if any(e["name"] == request.name for e in existing):
        raise HTTPException(409, f"EOS analysis '{request.name}' already exists for this topic")

    try:
        eos_id = db.facade.create_saved_eos(
            topic=request.topic,
            username=username,
            name=request.name,
            scenarios=request.scenarios,
            config=request.config,
            metadata=request.metadata,
            articles_used=request.articles_used,
            article_uris=request.article_uris,
            model_used=request.model_used,
            time_horizon=request.time_horizon,
            scenario_count=request.scenario_count,
            description=request.description
        )

        logger.info(f"Saved EOS '{request.name}' (ID: {eos_id}) for user '{username}'")

        return {
            "success": True,
            "eos_id": eos_id,
            "message": f"EOS analysis '{request.name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to save EOS: {e}")
        raise HTTPException(500, f"Failed to save EOS analysis: {str(e)}")


@router.get("/saved/{topic}")
async def list_saved_eos(
    topic: str,
    session: dict = Depends(verify_session)
):
    """
    Get all saved EOS analyses for a topic (current user only).

    Returns a list of EOS summaries sorted by creation date.
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
    eos_list = db.facade.get_saved_eos_for_topic(topic, username)

    return {
        "success": True,
        "saved_eos": eos_list
    }


@router.get("/saved/load/{eos_id}")
async def load_eos(
    eos_id: int,
    session: dict = Depends(verify_session)
):
    """
    Load a specific saved EOS analysis with full content.

    Returns complete EOS including scenarios and metadata.
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
    eos = db.facade.get_saved_eos_by_id(eos_id, username)

    if not eos:
        raise HTTPException(404, "EOS analysis not found")

    logger.info(f"Loaded EOS {eos_id} for user '{username}'")

    return {
        "success": True,
        "eos": eos
    }


@router.delete("/saved/{eos_id}")
async def delete_eos(
    eos_id: int,
    session: dict = Depends(verify_session)
):
    """
    Delete a saved EOS analysis.

    Removes the EOS analysis. This action cannot be undone.
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
    success = db.facade.delete_saved_eos(eos_id, username)

    if not success:
        raise HTTPException(404, "EOS analysis not found or permission denied")

    logger.info(f"Deleted EOS {eos_id} for user '{username}'")

    return {
        "success": True,
        "message": "EOS analysis deleted successfully"
    }
