"""Turn an ``Authorization`` header into an ``McpAuthContext``.

Order: OAuth access JWT first (cheap, no database hit until the user
lookup), then the static ``aunoo_…`` key. Either way the owning user must
still exist and be active, so deactivating a user cuts off every key and
token they hold.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from . import keys, oauth_service, store
from .errors import AuthError


@dataclass(frozen=True)
class McpAuthContext:
    username: str
    role: str
    auth_kind: str                 # "api_key" | "oauth"
    api_key_id: int | None = None
    oauth_client_id: str | None = None
    scope: str = "mcp:workspace"


def _require_active_user(user: dict | None) -> dict:
    if not user or not user.get("is_active", True):
        raise AuthError("user is inactive or unknown")
    return user


async def _oauth_context(token: str) -> McpAuthContext | None:
    claims = oauth_service.decode_access_token(token)
    if claims is None:
        return None
    user = _require_active_user(await asyncio.to_thread(store.get_user, claims["sub"]))
    return McpAuthContext(
        username=user["username"],
        role=user.get("role") or "user",
        auth_kind="oauth",
        oauth_client_id=str(claims.get("client_id")),
        scope=str(claims.get("scope") or "mcp:workspace"),
    )


async def _api_key_context(token: str) -> McpAuthContext:
    row = await asyncio.to_thread(store.get_api_key_by_hash, keys.hash_token(token))
    if row is None or not row.get("is_active"):
        raise AuthError("api key not recognised")
    expires_at = row.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise AuthError("api key expired")
    user = _require_active_user(await asyncio.to_thread(store.get_user, row["username"]))
    return McpAuthContext(
        username=user["username"],
        role=user.get("role") or "user",
        auth_kind="api_key",
        api_key_id=int(row["id"]),
    )


async def authenticate(authorization_header: str | None) -> McpAuthContext:
    token = keys.strip_bearer(authorization_header)
    if not token:
        raise AuthError("missing or malformed Authorization header")
    ctx = await _oauth_context(token)
    if ctx is not None:
        return ctx
    return await _api_key_context(token)
