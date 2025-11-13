"""
Saved Dashboards API Routes

Provides REST API endpoints for managing saved Trend Convergence dashboard instances.
Each saved dashboard stores configuration, article datasets, and cached analysis results.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.database import get_database_instance
from app.security.session import verify_session

router = APIRouter(prefix="/api/saved-dashboards", tags=["saved_dashboards"])
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================

class SaveDashboardRequest(BaseModel):
    """Request model for saving a new dashboard"""
    topic: str = Field(..., description="Topic name")
    name: str = Field(..., min_length=1, max_length=255, description="Dashboard name")
    description: Optional[str] = Field(None, description="Optional description")
    config: Dict[str, Any] = Field(..., description="Analysis configuration from frontend")
    article_uris: List[str] = Field(..., description="List of article URIs used in analysis")
    tab_data: Dict[str, Any] = Field(..., description="Cached data for all tabs")
    profile_snapshot: Optional[Dict[str, Any]] = Field(None, description="Organizational profile snapshot")


class UpdateDashboardRequest(BaseModel):
    """Request model for updating dashboard metadata"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    tab_data: Optional[Dict[str, Any]] = None


class SavedDashboardSummary(BaseModel):
    """Lightweight summary for dropdown list"""
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    articles_analyzed: Optional[int]
    model_used: Optional[str]
    auto_generated: bool = False


class SavedDashboardFull(BaseModel):
    """Complete dashboard data for loading"""
    id: int
    topic: str
    name: str
    description: Optional[str]
    config: Dict[str, Any]
    article_uris: List[str]
    consensus_data: Optional[Dict[str, Any]]
    strategic_data: Optional[Dict[str, Any]]
    timeline_data: Optional[Dict[str, Any]]
    signals_data: Optional[Dict[str, Any]]
    horizons_data: Optional[Dict[str, Any]]
    profile_snapshot: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime
    articles_analyzed: Optional[int]
    model_used: Optional[str]
    auto_generated: bool = False


# ==================== API Endpoints ====================

@router.post("/save")
async def save_dashboard(
    request: SaveDashboardRequest,
    session = Depends(verify_session),
    db = Depends(get_database_instance)
):
    """
    Save current dashboard state with all tab data.

    Creates a new saved dashboard instance with the current configuration,
    article dataset, and cached analysis results for all tabs.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    # Extract metadata from config
    articles_analyzed = request.config.get('article_count') or len(request.article_uris)
    model_used = request.config.get('model', 'unknown')

    # Check for duplicate name
    existing = db.facade.get_saved_dashboards_for_topic(
        request.topic,
        username
    )
    if any(d["name"] == request.name for d in existing):
        raise HTTPException(409, f"Dashboard '{request.name}' already exists for this topic")

    try:
        # Create dashboard
        dashboard_id = db.facade.create_saved_dashboard(
            topic=request.topic,
            username=username,
            name=request.name,
            config=request.config,
            article_uris=request.article_uris,
            tab_data=request.tab_data,
            profile_snapshot=request.profile_snapshot,
            description=request.description,
            articles_analyzed=articles_analyzed,
            model_used=model_used
        )

        logger.info(f"Saved dashboard '{request.name}' (ID: {dashboard_id}) for user '{username}'")

        return {
            "success": True,
            "dashboard_id": dashboard_id,
            "message": f"Dashboard '{request.name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Failed to save dashboard: {e}")
        raise HTTPException(500, f"Failed to save dashboard: {str(e)}")


@router.get("/topic/{topic}")
async def list_dashboards_for_topic(
    topic: str,
    session = Depends(verify_session),
    db = Depends(get_database_instance)
) -> List[SavedDashboardSummary]:
    """
    Get all saved dashboards for a topic (current user only).

    Returns a list of dashboard summaries sorted by last access time.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    dashboards = db.facade.get_saved_dashboards_for_topic(topic, username)
    return dashboards


@router.get("/{dashboard_id}")
async def load_dashboard(
    dashboard_id: int,
    session = Depends(verify_session),
    db = Depends(get_database_instance)
) -> SavedDashboardFull:
    """
    Load a specific saved dashboard with all data.

    Returns complete dashboard including config, article URIs, and all tab data.
    Updates the last_accessed_at timestamp.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    dashboard = db.facade.get_saved_dashboard_by_id(dashboard_id, username)

    if not dashboard:
        raise HTTPException(404, "Dashboard not found")

    # Update access timestamp
    db.facade.update_dashboard_access_time(dashboard_id)

    logger.info(f"Loaded dashboard {dashboard_id} for user '{username}'")
    return dashboard


@router.put("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: int,
    request: UpdateDashboardRequest,
    session = Depends(verify_session),
    db = Depends(get_database_instance)
):
    """
    Update saved dashboard metadata or cached data.

    Allows updating name, description, and tab data.
    The updated_at timestamp is automatically updated by database trigger.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    # Verify ownership
    dashboard = db.facade.get_saved_dashboard_by_id(dashboard_id, username)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")

    # Check for name conflict if renaming
    if request.name and request.name != dashboard['name']:
        existing = db.facade.get_saved_dashboards_for_topic(
            dashboard['topic'],
            username
        )
        if any(d["name"] == request.name and d["id"] != dashboard_id for d in existing):
            raise HTTPException(409, f"Dashboard '{request.name}' already exists")

    success = db.facade.update_saved_dashboard(
        dashboard_id,
        name=request.name,
        description=request.description,
        tab_data=request.tab_data
    )

    if not success:
        raise HTTPException(500, "Failed to update dashboard")

    return {"success": True, "message": "Dashboard updated successfully"}


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: int,
    session = Depends(verify_session),
    db = Depends(get_database_instance)
):
    """
    Delete a saved dashboard.

    Removes the dashboard and all its cached data. This action cannot be undone.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    success = db.facade.delete_saved_dashboard(dashboard_id, username)

    if not success:
        raise HTTPException(404, "Dashboard not found or permission denied")

    logger.info(f"Deleted dashboard {dashboard_id} for user '{username}'")
    return {"success": True, "message": "Dashboard deleted successfully"}


@router.get("/recent/list")
async def get_recent_dashboards(
    limit: int = Query(10, ge=1, le=50),
    session = Depends(verify_session),
    db = Depends(get_database_instance)
) -> List[SavedDashboardSummary]:
    """
    Get recently accessed dashboards across all topics.

    Returns dashboards sorted by last access time, limited to specified count.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    dashboards = db.facade.get_recent_saved_dashboards(username, limit)
    return dashboards


@router.get("/search")
async def search_dashboards(
    q: str = Query(..., min_length=1, description="Search query"),
    session = Depends(verify_session),
    db = Depends(get_database_instance)
) -> List[SavedDashboardSummary]:
    """
    Search saved dashboards using PostgreSQL full-text search.

    Searches dashboard names and descriptions using PostgreSQL's GIN index
    for fast full-text search capabilities.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    results = db.facade.search_saved_dashboards(username, q)
    return results


@router.get("/stats")
async def get_user_dashboard_stats(
    session = Depends(verify_session),
    db = Depends(get_database_instance)
):
    """
    Get aggregate dashboard statistics for current user.

    Uses PostgreSQL window functions for efficient aggregation.
    Returns: total_dashboards, unique_topics, total_articles, last_activity
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    stats = db.facade.get_dashboard_stats(username)
    return {
        "success": True,
        "stats": stats
    }


@router.post("/{dashboard_id}/clone")
async def clone_dashboard(
    dashboard_id: int,
    new_name: str = Query(..., description="Name for cloned dashboard"),
    session = Depends(verify_session),
    db = Depends(get_database_instance)
):
    """
    Clone an existing dashboard with a new name.

    Useful for creating variations or temporal comparisons.
    JSONB and TEXT[] data is efficiently copied using PostgreSQL.
    """
    # Extract username from session (handles both nested and OAuth formats)
    user = session.get("user")
    if user and isinstance(user, dict):
        username = user.get("username")
    else:
        username = session.get("username")  # OAuth fallback

    if not username:
        raise HTTPException(401, "User not authenticated")

    # Load original dashboard
    original = db.facade.get_saved_dashboard_by_id(dashboard_id, username)
    if not original:
        raise HTTPException(404, "Dashboard not found")

    # Check if new name already exists
    existing = db.facade.get_saved_dashboards_for_topic(
        original['topic'],
        username
    )
    if any(d["name"] == new_name for d in existing):
        raise HTTPException(409, f"Dashboard '{new_name}' already exists")

    try:
        # Create clone
        new_id = db.facade.create_saved_dashboard(
            topic=original['topic'],
            username=username,
            name=new_name,
            config=original['config'],
            article_uris=original['article_uris'],
            tab_data={
                'consensus': original.get('consensus_data'),
                'strategic': original.get('strategic_data'),
                'timeline': original.get('timeline_data'),
                'signals': original.get('signals_data'),
                'horizons': original.get('horizons_data')
            },
            profile_snapshot=original.get('profile_snapshot'),
            description=f"Cloned from: {original['name']}",
            articles_analyzed=original.get('articles_analyzed'),
            model_used=original.get('model_used')
        )

        logger.info(f"Cloned dashboard {dashboard_id} as '{new_name}' (ID: {new_id}) for user '{username}'")

        return {
            "success": True,
            "dashboard_id": new_id,
            "message": f"Cloned dashboard as '{new_name}'"
        }
    except Exception as e:
        logger.error(f"Failed to clone dashboard: {e}")
        raise HTTPException(500, f"Failed to clone dashboard: {str(e)}")
