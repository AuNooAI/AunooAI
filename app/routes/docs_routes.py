"""Serve inline product documentation (changelog, roadmap, how-it-works
pages) as markdown so the React UI can render them under top-level tabs.

The set of documents is whitelisted — this is *not* a generic file server.
Each named doc maps to a single file on disk:

    name                          → file
    changelog                     → CHANGELOG.md
    roadmap                       → ROADMAP.md
    how-it-works-topics           → docs/how_it_works_topics.md
    how-it-works-forecast-tracker → docs/how_it_works_forecast_tracker.md
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from app.security.session import verify_session_api

logger = logging.getLogger(__name__)

router = APIRouter()


_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Whitelist — name → relative path inside the project root.
_DOC_PATHS: dict[str, str] = {
    "changelog": "CHANGELOG.md",
    "roadmap": "ROADMAP.md",
    "how-it-works-topics": "docs/how_it_works_topics.md",
    "how-it-works-forecast-tracker": "docs/how_it_works_forecast_tracker.md",
    "brand-watcher-help": "docs/brand_watcher_help.md",
}


@router.get("/api/docs/{name}", dependencies=[Depends(verify_session_api)])
async def get_doc(name: str):
    """Return ``{name, content, path}`` for a whitelisted doc, 404 otherwise.

    The content is the raw Markdown — the client renders it.
    """
    rel = _DOC_PATHS.get(name)
    if not rel:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown doc '{name}'. Available: {sorted(_DOC_PATHS.keys())}"
            ),
        )
    path = _PROJECT_ROOT / rel
    if not path.exists():
        # Whitelisted but the source file was not deployed — fall back to a
        # one-line placeholder rather than 500ing the page.
        logger.warning("Doc file %s not present on disk", path)
        return {
            "name": name,
            "path": rel,
            "content": (
                f"# {name}\n\n_This document has not been deployed on this "
                f"tenant yet._\n"
            ),
        }
    try:
        return {
            "name": name,
            "path": rel,
            "content": path.read_text(encoding="utf-8"),
        }
    except Exception as e:
        logger.error("Failed to read doc %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Could not read doc: {e}")
