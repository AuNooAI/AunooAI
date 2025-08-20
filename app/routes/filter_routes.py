"""Vantage Desk Filter API Routes"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_database_instance, Database
from app.security.session import verify_session_api
from app.services.filter_service import FilterService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/filters", tags=["filters"])


# ------------------------------------------------------------------
# helper to build user_key like service suggestion
# ------------------------------------------------------------------

def build_user_key(session: dict) -> str:
    if session.get("oauth_user"):
        oauth_user = session["oauth_user"]
        return f"{oauth_user['provider']}:{oauth_user['email'].lower()}"
    return f"local:{session['user'].lower()}"

# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _parse_group_id(group_id: Optional[str]) -> Optional[int]:
    """Convert path param to Optional[int], treating 'null'/'none'/'' as None."""
    if group_id is None:
        return None
    gid = str(group_id).strip().lower()
    if gid in ("null", "none", "", "undefined"):
        return None
    try:
        return int(gid)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/{group_id}")
async def get_filters(
    group_id: Optional[str] = None,
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Return the saved filter preset for the current user and group.

    Accepts numeric group_id or string values like 'null' to indicate None.
    """
    parsed_group_id = _parse_group_id(group_id)
    logger.info(f"Get filters called for group_id={group_id} (parsed={parsed_group_id})")
    logger.info(f"Session data: {session}")
    
    user_key = build_user_key(session)
    logger.info(f"Generated user_key: {user_key}")
    
    service = FilterService(db)
    filters = service.get_filters(user_key, parsed_group_id)
    logger.info(f"Retrieved filters: {filters}")
    
    if not filters:
        return {"success": True, "filters": None}
    # Remove internal columns
    filters.pop("id", None)
    filters.pop("user_key", None)
    return {"success": True, "filters": filters}


@router.post("/{group_id}")
async def upsert_filters(
    group_id: str,
    payload: Dict[str, Any],
    db: Database = Depends(get_database_instance),
    session = Depends(verify_session_api)
):
    """Create or update the filter preset for the current user and group."""
    parsed_group_id = _parse_group_id(group_id)
    logger.info(f"Upsert filters called for group_id={group_id} (parsed={parsed_group_id})")
    logger.info(f"Session data: {session}")
    
    user_key = build_user_key(session)
    logger.info(f"Generated user_key: {user_key}")
    
    service = FilterService(db)
    try:
        response = service.upsert_filters(user_key, parsed_group_id, payload)
        logger.info(f"Service response: {response}")
        if response:
            return {"success": True}
        else:
            return {"success": False, "error": "Failed to save filters"}
    except Exception as e:
        logger.error(f"Failed to upsert filters: {e}")
        raise HTTPException(status_code=500, detail="Failed to save filters")

