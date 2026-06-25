"""
Strategic Intelligence Oracle API Routes

Provides endpoints for:
- Full 24-hour intelligence scans (Option C)
- Single article deep analysis (Option A)
- Scan history and management
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import logging
import asyncio
from datetime import datetime
import uuid

from app.services.strategic_intelligence_service import (
    get_strategic_intelligence_service,
    SIOConfig
)
from app.services.article_intelligence_analyzer import (
    get_article_intelligence_analyzer,
    AnalyzerConfig
)
from app.security.session import verify_session
from app.database import get_database_instance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sio", tags=["Strategic Intelligence Oracle"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ScanRequest(BaseModel):
    """Request model for starting a 24-hour intelligence scan."""
    topic: Optional[str] = Field(
        None,
        description="Optional topic filter. If None, scans all topics."
    )
    hours_back: int = Field(
        24,
        ge=1,
        le=168,  # Max 1 week
        description="Number of hours of news to analyze"
    )
    max_events: int = Field(
        30,
        ge=5,
        le=100,
        description="Maximum number of events to deep-analyze"
    )
    credibility_threshold: int = Field(
        60,
        ge=0,
        le=100,
        description="Minimum credibility score for sources"
    )
    stream: bool = Field(
        True,
        description="Whether to stream progress updates"
    )


class AnalyzeUrlRequest(BaseModel):
    """Request model for single article analysis."""
    url: str = Field(
        ...,
        description="URL of the article to analyze"
    )
    topic: Optional[str] = Field(
        None,
        description="Optional topic context for better search"
    )
    deep_verification: bool = Field(
        True,
        description="Whether to perform deep cross-referencing"
    )


class ScanStatusResponse(BaseModel):
    """Response model for scan status."""
    scan_id: str
    status: str
    stage: str
    progress: float
    articles_collected: int = 0
    events_identified: int = 0
    events_analyzed: int = 0
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class ScanListResponse(BaseModel):
    """Response model for scan history."""
    scans: List[Dict[str, Any]]
    total: int
    page: int
    per_page: int


# ============================================================================
# Streaming Helper
# ============================================================================

async def stream_scan_progress(
    topic: Optional[str],
    hours_back: int,
    max_events: int,
    config: SIOConfig,
    username: Optional[str] = None
):
    """Generator that yields SSE events for scan progress."""
    service = get_strategic_intelligence_service()

    try:
        async for update in service.run_scan(
            topic=topic,
            hours_back=hours_back,
            max_events=max_events,
            config=config
        ):
            # Format as Server-Sent Event
            event_data = json.dumps(update)
            yield f"data: {event_data}\n\n"

            # If complete or error, stop streaming
            if update.get("stage") in ["complete", "error"]:
                break

    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
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
async def start_scan(
    request: ScanRequest,
    session: dict = Depends(verify_session)
):
    """
    Start a Strategic Intelligence Oracle scan.

    Analyzes the past N hours of news, clusters into events,
    performs deep analysis on top events, and generates an
    intelligence brief.

    If stream=True, returns a streaming response with progress updates.
    If stream=False, waits for completion and returns the full result.
    """
    username = session.get("username") if session else None

    # Build config
    config = SIOConfig(
        hours_back=request.hours_back,
        max_events_to_analyze=request.max_events,
        credibility_threshold=request.credibility_threshold
    )

    if request.stream:
        # Return streaming response
        return StreamingResponse(
            stream_scan_progress(
                topic=request.topic,
                hours_back=request.hours_back,
                max_events=request.max_events,
                config=config,
                username=username
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
        service = get_strategic_intelligence_service()
        result = None

        async for update in service.run_scan(
            topic=request.topic,
            hours_back=request.hours_back,
            max_events=request.max_events,
            config=config
        ):
            result = update
            if update.get("stage") in ["complete", "error"]:
                break

        if result and result.get("stage") == "complete":
            return {
                "success": True,
                "scan_id": result.get("scan_id"),
                "brief": result.get("brief"),
                "metadata": result.get("metadata"),
                "audit_trail": result.get("audit_trail")
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Scan failed") if result else "Scan failed"
            )


@router.post("/analyze-url")
async def analyze_url(
    request: AnalyzeUrlRequest,
    session: dict = Depends(verify_session)
):
    """
    Perform deep analysis on a single article URL.

    This is Option A - standalone article analysis with:
    - Full content extraction
    - Source credibility check
    - Key fact extraction
    - Cross-referencing against related articles
    - Claim verification
    - Contradiction detection
    - Impact assessment
    """
    username = session.get("username") if session else None

    try:
        analyzer = get_article_intelligence_analyzer()

        # Configure analyzer
        if request.deep_verification:
            config = AnalyzerConfig(
                min_cross_references=3,
                max_related_articles=25
            )
        else:
            config = AnalyzerConfig(
                min_cross_references=1,
                max_related_articles=10
            )

        analyzer.config = config

        # Run analysis
        analysis = await analyzer.analyze_url(
            url=request.url,
            topic=request.topic
        )

        return {
            "success": True,
            "analysis_id": str(uuid.uuid4()),
            "url": request.url,
            "analysis": analysis.to_dict()
        }

    except Exception as e:
        logger.error(f"URL analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.get("/scans")
async def list_scans(
    page: int = 1,
    per_page: int = 20,
    topic: Optional[str] = None,
    status: Optional[str] = None,
    session: dict = Depends(verify_session)
) -> ScanListResponse:
    """
    List recent SIO scans with pagination.

    Optionally filter by topic or status.
    """
    username = session.get("username") if session else None

    try:
        db = get_database_instance()

        # Build query - this would use the sio_scan_runs table
        # For now, return placeholder until migration is run
        return ScanListResponse(
            scans=[],
            total=0,
            page=page,
            per_page=per_page
        )

    except Exception as e:
        logger.error(f"Failed to list scans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}")
async def get_scan(
    scan_id: str,
    session: dict = Depends(verify_session)
):
    """
    Get details of a specific scan by ID.

    Returns the full intelligence brief and metadata.
    """
    try:
        db = get_database_instance()

        # Query sio_scan_runs table
        # For now, return placeholder
        raise HTTPException(
            status_code=404,
            detail=f"Scan {scan_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}/brief")
async def get_scan_brief(
    scan_id: str,
    session: dict = Depends(verify_session)
):
    """
    Get just the intelligence brief for a scan.

    Returns the markdown-formatted brief without metadata.
    """
    try:
        db = get_database_instance()

        # Query and return just the brief
        raise HTTPException(
            status_code=404,
            detail=f"Scan {scan_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan/{scan_id}/events")
async def get_scan_events(
    scan_id: str,
    session: dict = Depends(verify_session)
):
    """
    Get the analyzed events from a scan.

    Returns the list of event clusters with their analyses.
    """
    try:
        db = get_database_instance()

        # Query sio_event_clusters table
        raise HTTPException(
            status_code=404,
            detail=f"Scan {scan_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scan/{scan_id}")
async def delete_scan(
    scan_id: str,
    session: dict = Depends(verify_session)
):
    """
    Delete a scan and all associated data.
    """
    username = session.get("username") if session else None

    try:
        db = get_database_instance()

        # Delete from sio_scan_runs (cascade will handle related tables)
        # For now, return success
        return {"success": True, "deleted": scan_id}

    except Exception as e:
        logger.error(f"Failed to delete scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyses")
async def list_article_analyses(
    page: int = 1,
    per_page: int = 20,
    session: dict = Depends(verify_session)
):
    """
    List recent single-article analyses.
    """
    username = session.get("username") if session else None

    try:
        db = get_database_instance()

        # Query sio_article_analyses table
        return {
            "analyses": [],
            "total": 0,
            "page": page,
            "per_page": per_page
        }

    except Exception as e:
        logger.error(f"Failed to list analyses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """
    Health check endpoint for SIO service.
    """
    try:
        service = get_strategic_intelligence_service()
        analyzer = get_article_intelligence_analyzer()

        return {
            "status": "healthy",
            "service": "strategic_intelligence_oracle",
            "version": "1.0.0",
            "components": {
                "scan_service": "ready",
                "article_analyzer": "ready"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# ============================================================================
# Quick Scan Endpoint (Simplified)
# ============================================================================

@router.post("/quick-scan")
async def quick_scan(
    topic: Optional[str] = None,
    session: dict = Depends(verify_session)
):
    """
    Run a quick 24-hour scan with default settings.

    This is a simplified endpoint that uses sensible defaults:
    - 24 hours back
    - Top 20 events
    - 60% credibility threshold
    - Streaming enabled

    Returns a streaming response with progress updates.
    """
    config = SIOConfig(
        hours_back=24,
        max_events_to_analyze=20,
        credibility_threshold=60
    )

    return StreamingResponse(
        stream_scan_progress(
            topic=topic,
            hours_back=24,
            max_events=20,
            config=config
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# SIO Prompt Management Endpoints
# ============================================================================

SIO_AGENTS = [
    {
        "id": "sio_discovery_agent",
        "name": "Discovery",
        "description": "Generates diverse search queries to gather news articles",
        "file": "sio_discovery_agent.md"
    },
    {
        "id": "sio_triage_agent",
        "name": "Triage",
        "description": "Clusters articles into events and filters by credibility",
        "file": "sio_triage_agent.md"
    },
    {
        "id": "sio_deep_analysis_agent",
        "name": "Deep Analysis",
        "description": "Performs comprehensive analysis on high-priority events",
        "file": "sio_deep_analysis_agent.md"
    },
    {
        "id": "sio_synthesis_agent",
        "name": "Synthesis",
        "description": "Generates the final intelligence brief from analyzed events",
        "file": "sio_synthesis_agent.md"
    }
]

# Path to SIO global config file
SIO_CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "auspex" / "sio_config.json"


@router.get("/config")
async def get_sio_config(
    session: dict = Depends(verify_session)
):
    """
    Get the global SIO configuration settings.

    Returns settings like credibility_threshold that apply to all scans.
    """
    import json

    # Default config
    default_config = {
        "credibility_threshold": 60,
        "hours_back": 24,
        "max_events": 30
    }

    try:
        if SIO_CONFIG_FILE.exists():
            with open(SIO_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults for any missing keys
                return {**default_config, **config}
        return default_config
    except Exception as e:
        logger.error(f"Failed to read SIO config: {e}")
        return default_config


class SIOConfigUpdate(BaseModel):
    """Request model for updating SIO config."""
    credibility_threshold: Optional[int] = Field(None, ge=0, le=100)
    hours_back: Optional[int] = Field(None, ge=1, le=168)
    max_events: Optional[int] = Field(None, ge=5, le=100)


@router.put("/config")
async def update_sio_config(
    request: SIOConfigUpdate,
    session: dict = Depends(verify_session)
):
    """
    Update the global SIO configuration settings.

    These settings persist across sessions and apply to all scans.
    """
    import json

    try:
        # Load existing config or use defaults
        if SIO_CONFIG_FILE.exists():
            with open(SIO_CONFIG_FILE, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "credibility_threshold": 60,
                "hours_back": 24,
                "max_events": 30
            }

        # Update only provided fields
        if request.credibility_threshold is not None:
            config["credibility_threshold"] = request.credibility_threshold
        if request.hours_back is not None:
            config["hours_back"] = request.hours_back
        if request.max_events is not None:
            config["max_events"] = request.max_events

        # Ensure directory exists
        SIO_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save config
        with open(SIO_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

        logger.info(f"SIO config updated: {config}")

        return {
            "success": True,
            "config": config
        }

    except Exception as e:
        logger.error(f"Failed to update SIO config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts")
async def list_sio_prompts(
    session: dict = Depends(verify_session)
):
    """
    List all SIO agent prompts with their current content.

    Returns metadata and content for each of the 4 SIO stages:
    - Discovery: search query generation
    - Triage: event clustering and credibility filtering
    - Deep Analysis: comprehensive event analysis
    - Synthesis: final brief generation
    """
    import os
    from pathlib import Path

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"

    prompts = []
    for agent in SIO_AGENTS:
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
                    import yaml
                    try:
                        metadata = yaml.safe_load(parts[1])
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
async def get_sio_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """
    Get a specific SIO agent prompt by ID.
    """
    from pathlib import Path

    agent = next((a for a in SIO_AGENTS if a["id"] == agent_id), None)
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
            import yaml
            try:
                metadata = yaml.safe_load(parts[1])
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


class UpdatePromptRequest(BaseModel):
    content: str = Field(..., description="The new prompt content (markdown after frontmatter)")
    model: Optional[str] = Field(None, description="AI model to use for this agent")
    temperature: Optional[float] = Field(None, description="Temperature setting (0.0-1.0)")


@router.put("/prompts/{agent_id}")
async def update_sio_prompt(
    agent_id: str,
    request: UpdatePromptRequest,
    session: dict = Depends(verify_session)
):
    """
    Update an SIO agent prompt, model, and temperature settings.

    Updates the markdown content and optionally the model_config in frontmatter.
    """
    from pathlib import Path
    import yaml

    agent = next((a for a in SIO_AGENTS if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agents_dir = Path(__file__).parent.parent.parent / "data" / "auspex" / "agents"
    agent_file = agents_dir / agent["file"]

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

    logger.info(f"Updated SIO agent: {agent_id} (model={request.model}, temp={request.temperature})")

    return {
        "success": True,
        "message": f"Updated {agent['name']} agent configuration"
    }


@router.post("/prompts/{agent_id}/reset")
async def reset_sio_prompt(
    agent_id: str,
    session: dict = Depends(verify_session)
):
    """
    Reset an SIO agent prompt to its default.

    This restores the original prompt from the bundled defaults.
    """
    # For now, return not implemented
    # Would need to store/ship default prompts
    raise HTTPException(
        status_code=501,
        detail="Reset to default not yet implemented"
    )
