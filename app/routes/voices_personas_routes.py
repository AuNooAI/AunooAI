"""Settings page for a site's Voices audience personas. Admins only.

The page edits one set per site: each audience's key, label, the definition
the model and Jev pick by, a short reason shown in Voices, and whether it is
a column, a button or hidden. Saving makes it the site's active set
(voices_persona_sets); the change applies to new posts at once and to past
posts after a re-read, which the page starts and shows the size of first.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.security.session import require_admin
from app.services import voices_personas, voices_reread

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Voices personas"])
templates = Jinja2Templates(directory="templates")
templates.env.auto_reload = True


def _user(session) -> str:
    u = session.get("user") if isinstance(session, dict) else None
    return (u.get("username") if isinstance(u, dict) else u) or "admin"


def _current() -> Dict[str, Any]:
    saved = voices_personas.saved_set()
    if saved is not None:
        return {"source": "saved", "set": saved.to_dict()}
    import os
    name = (os.getenv("VOICES_PERSONAS") or "").strip().lower()
    code = voices_personas.named_set(name) if name and name != "default" else None
    if code is not None:
        return {"source": f"code ({name})", "set": code.to_dict()}
    return {"source": "code (standard)", "set": voices_personas.standard_dict()}


def _role_counts() -> Dict[str, int]:
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        rows = conn.execute(text("""
            SELECT author_role, count(*) FROM articles
             WHERE author_role IS NOT NULL AND topic LIKE 'Brand Monitoring %'
               AND topic_alignment_score >= 0.4
               AND publication_date >= to_char(NOW() - INTERVAL '180 days', 'YYYY-MM-DD')
             GROUP BY 1
        """)).fetchall()
    finally:
        conn.close()
    return {r[0]: int(r[1]) for r in rows}


@router.get("/voices/personas")
async def personas_page(request: Request, session=Depends(require_admin)):
    return templates.TemplateResponse("voices_personas.html", {"request": request, "session": session})


@router.get("/api/voices/personas")
async def get_personas(session=Depends(require_admin)):
    cur = await asyncio.to_thread(_current)
    cur["presets"] = ["standard", *sorted(voices_personas.named_sets())]
    cur["counts"] = await asyncio.to_thread(_role_counts)
    return cur


@router.get("/api/voices/personas/preset/{name}")
async def get_preset(name: str, session=Depends(require_admin)):
    d = await asyncio.to_thread(voices_personas.preset, name)
    if d is None:
        raise HTTPException(status_code=404, detail="No such preset")
    return d


class PersonaSetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    audiences: List[Dict[str, Any]]
    guide: str = ""
    open_pairs: List[List[str]] = []
    person_roles: List[str] = []


@router.post("/api/voices/personas")
async def save_personas(body: PersonaSetBody, session=Depends(require_admin)):
    d = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    for a in d["audiences"]:
        a["key"] = (a.get("key") or "").strip().lower()
        a["group"] = (a.get("group") or "").strip().lower()
    problems = voices_personas.validate(d)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    new_id = await asyncio.to_thread(voices_personas.save, d, body.name, _user(session))
    _clear_voices_cache()
    logger.info("voices personas: set %r saved as #%s by %s", body.name, new_id, _user(session))
    return {"id": new_id, "saved": True}


@router.post("/api/voices/personas/reset")
async def reset_personas(session=Depends(require_admin)):
    await asyncio.to_thread(voices_personas.clear_saved, _user(session))
    _clear_voices_cache()
    return {"reset": True}


@router.get("/api/voices/personas/reread")
async def reread_info(session=Depends(require_admin)):
    est = await asyncio.to_thread(voices_reread.estimate)
    return {"estimate": est, "job": voices_reread.status()}


@router.post("/api/voices/personas/reread", status_code=202)
async def start_reread(session=Depends(require_admin)):
    if voices_reread.status().get("state") == "running":
        raise HTTPException(status_code=409, detail="A re-read is already running")
    voices_reread._job.update(state="running", done=0, total=0, written=0, error=None)
    asyncio.create_task(voices_reread.run(_user(session)))
    return {"started": True}


def _clear_voices_cache() -> None:
    try:
        from app.routes.brand_watcher_routes import bw_cache_clear
        bw_cache_clear()
    except Exception:  # noqa: BLE001 - the cache ages out anyway
        pass
