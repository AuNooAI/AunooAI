"""Self-service routes behind the settings page's Connectors tab.

A signed-in user manages their own keys and their own connected apps here.
Cross-user administration stays in admin_routes.py.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.security.session import verify_session_api

from . import config, keys, recipes, store, tools

router = APIRouter(prefix="/api/mcp/me", tags=["mcp"], dependencies=[Depends(verify_session_api)])


class MintOwnKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    expires_days: int | None = Field(default=90, ge=1, le=3650)


def _username(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "not signed in")
    return str(user).lower()


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}


@router.get("/install")
async def install_info(request: Request) -> dict[str, Any]:
    """Everything the tab needs to render the connect instructions."""
    url = config.mcp_audience()
    placeholder = "aunoo_<your key>"
    return {
        "mcp_url": url,
        "site": config.host_name(),
        "username": _username(request),
        "tools": [t.name for t in tools.available_tools()],
        "prompts": [r["name"] for r in recipes.list_recipes()],
        "snippets": {
            "claude_code": f'claude mcp add --transport http aunoo-{config.host_name().split(".")[0]} {url} --header "Authorization: Bearer {placeholder}"',
            "cursor": json.dumps({"mcpServers": {"aunoo": {"url": url, "headers": {"Authorization": f"Bearer {placeholder}"}}}}, indent=2),
            "claude_desktop": json.dumps({"mcpServers": {"aunoo": {"command": "npx", "args": ["-y", "mcp-remote", url, "--header", f"Authorization: Bearer {placeholder}"]}}}, indent=2),
            "claude_ai": f"Settings → Connectors → Add custom connector → URL {url}. Leave the client fields empty, sign in when the browser opens, click Allow.",
        },
    }


@router.get("/keys")
async def my_keys(request: Request) -> list[dict[str, Any]]:
    rows = await asyncio.to_thread(store.list_api_keys, _username(request))
    return [_serialise(r) for r in rows]


@router.post("/keys", status_code=201)
async def mint_my_key(body: MintOwnKeyRequest, request: Request) -> dict[str, Any]:
    """The plaintext appears in this response only."""
    username = _username(request)
    plaintext, row = await asyncio.to_thread(
        lambda: keys.mint_key(username=username, name=body.name,
                              expires_days=body.expires_days, created_by=username)
    )
    return {**_serialise(row), "plaintext": plaintext}


@router.delete("/keys/{key_id}")
async def revoke_my_key(key_id: int, request: Request) -> dict[str, Any]:
    if not await asyncio.to_thread(store.revoke_api_key_for_user, key_id, _username(request)):
        raise HTTPException(404, "no active key of yours with that id")
    return {"id": key_id, "revoked": True}


@router.get("/connections")
async def my_connections(request: Request) -> list[dict[str, Any]]:
    username = _username(request)
    rows, last = await asyncio.gather(
        asyncio.to_thread(store.list_user_connections, username),
        asyncio.to_thread(store.last_call_per_client, username),
    )
    out = []
    for r in rows:
        r = dict(r)
        r["last_used_at"] = last.get(r["client_id"])
        out.append(_serialise(r))
    return out


@router.delete("/connections/{client_id}")
async def disconnect(client_id: str, request: Request) -> dict[str, Any]:
    n = await asyncio.to_thread(store.revoke_user_connection, _username(request), client_id)
    if not n:
        raise HTTPException(404, "no active connection to that app")
    return {"client_id": client_id, "revoked_tokens": n}
