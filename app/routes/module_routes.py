"""API endpoints for analysis module configuration."""

import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.security.session import verify_session
from app.core.modules import get_all_modules, get_enabled_module_ids, set_module_enabled

logger = logging.getLogger(__name__)

router = APIRouter()


class ToggleRequest(BaseModel):
    enabled: bool


def _build_module_list():
    """Build the full module list with enabled flags."""
    enabled_ids = set(get_enabled_module_ids())
    modules = []
    for m in get_all_modules():
        modules.append({
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "tab_id": m.frontend_tab_id,
            "tab_label": m.frontend_tab_label,
            "tab_icon": m.frontend_tab_icon,
            "has_model": m.model_path is not None,
            "model_available": (
                os.path.isdir(m.model_path) if m.model_path else None
            ),
            "enabled": m.id in enabled_ids,
        })
    return modules


@router.get("/api/modules")
async def list_modules(session=Depends(verify_session)):
    """Return metadata about all analysis modules with enabled state."""
    return {"modules": _build_module_list()}


@router.put("/api/modules/{module_id}/toggle")
async def toggle_module(module_id: str, body: ToggleRequest, session=Depends(verify_session)):
    """Enable or disable a module. Persists to module_config table."""
    # Validate module exists
    all_ids = {m.id for m in get_all_modules()}
    if module_id not in all_ids:
        raise HTTPException(status_code=404, detail=f"Unknown module: {module_id}")

    user = session.get("user") if isinstance(session, dict) else None
    username = user.get("username") if isinstance(user, dict) else user
    set_module_enabled(module_id, body.enabled, username)
    return {"modules": _build_module_list()}
