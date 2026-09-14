"""Admin JSON routes for MCP keys, OAuth clients and the call log.

No UI panel yet; ``scripts/mcp_keys.py`` covers the same operations from
the shell. Both dependencies are attached at the router so an anonymous
caller gets a 401 (not a login redirect) before the admin check runs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.security.session import require_admin, verify_session_api

from . import keys, store

router = APIRouter(
    prefix="/api/mcp-keys",
    tags=["mcp"],
    dependencies=[Depends(verify_session_api), Depends(require_admin)],
)


class MintKeyRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


@router.get("")
async def list_keys(username: str | None = Query(default=None)) -> list[dict[str, Any]]:
    rows = await asyncio.to_thread(store.list_api_keys, username)
    return [_serialise(r) for r in rows]


@router.post("", status_code=201)
async def mint_key(body: MintKeyRequest, request: Request) -> dict[str, Any]:
    """The plaintext key is in this response and nowhere else."""
    if not await asyncio.to_thread(store.user_exists_active, body.username):
        raise HTTPException(404, "no active user with that username")
    created_by = request.session.get("user") if hasattr(request, "session") else None
    plaintext, row = await asyncio.to_thread(
        lambda: keys.mint_key(
            username=body.username, name=body.name,
            expires_days=body.expires_days, created_by=created_by,
        )
    )
    return {**_serialise(row), "plaintext": plaintext}


@router.delete("/{key_id}")
async def revoke_key(key_id: int) -> dict[str, Any]:
    if not await asyncio.to_thread(store.revoke_api_key, key_id):
        raise HTTPException(404, "no active key with that id")
    return {"id": key_id, "revoked": True}


@router.get("/calls")
async def list_calls(
    username: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    rows = await asyncio.to_thread(store.list_tool_calls, username, limit)
    return [_serialise(r) for r in rows]


@router.get("/oauth-clients")
async def list_oauth_clients() -> list[dict[str, Any]]:
    rows = await asyncio.to_thread(store.list_clients)
    return [_serialise(r) for r in rows]


@router.delete("/oauth-clients/{client_id}")
async def delete_oauth_client(client_id: str) -> dict[str, Any]:
    """Removes the client and, through the cascades, its codes and refresh
    tokens. Access tokens already issued last at most one more hour."""
    if not await asyncio.to_thread(store.delete_client, client_id):
        raise HTTPException(404, "no such client")
    return {"client_id": client_id, "deleted": True}
