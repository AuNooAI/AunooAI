"""Synchronous database access for the MCP tables.

Every function here blocks on psycopg2. Request handlers call them through
``asyncio.to_thread`` so the event loop stays free; the CLI calls them
directly. Uses the facade's fetch helpers, which commit and release the
connection before returning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, insert, select, update

from app.database_models import (
    t_mcp_api_keys,
    t_mcp_tool_calls,
    t_oauth_authorization_codes,
    t_oauth_clients,
    t_oauth_refresh_tokens,
    t_users,
)


def _facade():
    # Imported here so that importing app.mcp (for route tests) does not
    # open the database pool.
    from app.database import get_database_instance
    return get_database_instance().facade


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(mapping) -> dict[str, Any] | None:
    return dict(mapping) if mapping is not None else None


def _rows(mappings) -> list[dict[str, Any]]:
    return [dict(m) for m in mappings]


# ─── Users ──────────────────────────────────────────────────────────────────

def get_user(username: str | None) -> dict[str, Any] | None:
    if not username:
        return None
    return _facade().get_user_by_username(username)


# ─── API keys ───────────────────────────────────────────────────────────────

_KEY_PUBLIC_COLS = (
    t_mcp_api_keys.c.id, t_mcp_api_keys.c.username, t_mcp_api_keys.c.name,
    t_mcp_api_keys.c.key_prefix, t_mcp_api_keys.c.is_active,
    t_mcp_api_keys.c.created_at, t_mcp_api_keys.c.expires_at,
    t_mcp_api_keys.c.last_used_at, t_mcp_api_keys.c.revoked_at,
    t_mcp_api_keys.c.created_by,
)


def insert_api_key(*, username: str, name: str, key_prefix: str, key_hash: str,
                   expires_at: datetime | None, created_by: str | None) -> dict[str, Any]:
    stmt = insert(t_mcp_api_keys).values(
        username=username, name=name, key_prefix=key_prefix, key_hash=key_hash,
        expires_at=expires_at, created_by=created_by, is_active=True,
    ).returning(*_KEY_PUBLIC_COLS)
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_insert_api_key", mappings=True)
    return _row(row)


def get_api_key_by_hash(key_hash: str) -> dict[str, Any] | None:
    stmt = select(t_mcp_api_keys).where(t_mcp_api_keys.c.key_hash == key_hash)
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_get_api_key", mappings=True)
    return _row(row)


def list_api_keys(username: str | None = None, include_inactive: bool = True) -> list[dict[str, Any]]:
    stmt = select(*_KEY_PUBLIC_COLS)
    if username:
        stmt = stmt.where(t_mcp_api_keys.c.username == username.lower())
    if not include_inactive:
        stmt = stmt.where(t_mcp_api_keys.c.is_active.is_(True))
    stmt = stmt.order_by(t_mcp_api_keys.c.created_at.desc())
    return _rows(_facade()._fetchall_with_rollback(stmt, operation_name="mcp_list_api_keys", mappings=True))


def revoke_api_key(key_id: int) -> bool:
    stmt = (
        update(t_mcp_api_keys)
        .where(t_mcp_api_keys.c.id == key_id, t_mcp_api_keys.c.is_active.is_(True))
        .values(is_active=False, revoked_at=_now())
        .returning(t_mcp_api_keys.c.id)
    )
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_revoke_api_key", mappings=True)
    return row is not None


def touch_api_key(key_id: int) -> None:
    stmt = update(t_mcp_api_keys).where(t_mcp_api_keys.c.id == key_id).values(last_used_at=_now())
    _facade()._execute_with_rollback(stmt, operation_name="mcp_touch_api_key")


# ─── Audit ──────────────────────────────────────────────────────────────────

def insert_tool_call(row: dict[str, Any]) -> None:
    _facade()._execute_with_rollback(insert(t_mcp_tool_calls).values(**row),
                                     operation_name="mcp_insert_tool_call")


def list_tool_calls(username: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    stmt = select(t_mcp_tool_calls)
    if username:
        stmt = stmt.where(t_mcp_tool_calls.c.username == username.lower())
    stmt = stmt.order_by(t_mcp_tool_calls.c.id.desc()).limit(max(1, min(int(limit), 1000)))
    return _rows(_facade()._fetchall_with_rollback(stmt, operation_name="mcp_list_tool_calls", mappings=True))


# ─── OAuth clients ──────────────────────────────────────────────────────────

def insert_client(*, client_id: str, client_secret_hash: str, client_name: str,
                  redirect_uris: list[str]) -> None:
    stmt = insert(t_oauth_clients).values(
        client_id=client_id, client_secret_hash=client_secret_hash,
        client_name=client_name, redirect_uris=list(redirect_uris),
    )
    _facade()._execute_with_rollback(stmt, operation_name="mcp_insert_client")


def get_client(client_id: str | None) -> dict[str, Any] | None:
    if not client_id:
        return None
    stmt = select(t_oauth_clients).where(t_oauth_clients.c.client_id == client_id)
    return _row(_facade()._fetchone_with_rollback(stmt, operation_name="mcp_get_client", mappings=True))


def list_clients() -> list[dict[str, Any]]:
    stmt = select(
        t_oauth_clients.c.client_id, t_oauth_clients.c.client_name,
        t_oauth_clients.c.redirect_uris, t_oauth_clients.c.created_at,
    ).order_by(t_oauth_clients.c.created_at.desc())
    return _rows(_facade()._fetchall_with_rollback(stmt, operation_name="mcp_list_clients", mappings=True))


def delete_client(client_id: str) -> bool:
    stmt = delete(t_oauth_clients).where(t_oauth_clients.c.client_id == client_id).returning(t_oauth_clients.c.client_id)
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_delete_client", mappings=True)
    return row is not None


# ─── Authorization codes ────────────────────────────────────────────────────

def insert_auth_code(*, code: str, client_id: str, username: str, redirect_uri: str,
                     scope: str, code_challenge: str, code_challenge_method: str,
                     expires_at: datetime) -> None:
    stmt = insert(t_oauth_authorization_codes).values(
        code=code, client_id=client_id, username=username.lower(), redirect_uri=redirect_uri,
        scope=scope, code_challenge=code_challenge, code_challenge_method=code_challenge_method,
        expires_at=expires_at,
    )
    _facade()._execute_with_rollback(stmt, operation_name="mcp_insert_auth_code")


def get_auth_code(code: str) -> dict[str, Any] | None:
    stmt = select(t_oauth_authorization_codes).where(t_oauth_authorization_codes.c.code == code)
    return _row(_facade()._fetchone_with_rollback(stmt, operation_name="mcp_get_auth_code", mappings=True))


def consume_auth_code(code: str) -> bool:
    """Mark the code used. Returns False if it was already used, so two
    racing token requests cannot both succeed."""
    stmt = (
        update(t_oauth_authorization_codes)
        .where(t_oauth_authorization_codes.c.code == code,
               t_oauth_authorization_codes.c.consumed_at.is_(None))
        .values(consumed_at=_now())
        .returning(t_oauth_authorization_codes.c.code)
    )
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_consume_auth_code", mappings=True)
    return row is not None


# ─── Refresh tokens ─────────────────────────────────────────────────────────

def insert_refresh_token(*, token_hash: str, client_id: str, username: str,
                         scope: str, expires_at: datetime) -> None:
    stmt = insert(t_oauth_refresh_tokens).values(
        token_hash=token_hash, client_id=client_id, username=username.lower(),
        scope=scope, expires_at=expires_at,
    )
    _facade()._execute_with_rollback(stmt, operation_name="mcp_insert_refresh_token")


def get_refresh_token(token_hash: str) -> dict[str, Any] | None:
    stmt = select(t_oauth_refresh_tokens).where(t_oauth_refresh_tokens.c.token_hash == token_hash)
    return _row(_facade()._fetchone_with_rollback(stmt, operation_name="mcp_get_refresh_token", mappings=True))


def revoke_refresh_token(token_hash: str) -> None:
    stmt = update(t_oauth_refresh_tokens).where(t_oauth_refresh_tokens.c.token_hash == token_hash).values(revoked_at=_now())
    _facade()._execute_with_rollback(stmt, operation_name="mcp_revoke_refresh_token")


def user_exists_active(username: str) -> bool:
    stmt = select(t_users.c.username).where(t_users.c.username == username.lower(), t_users.c.is_active.is_(True))
    row = _facade()._fetchone_with_rollback(stmt, operation_name="mcp_user_exists", mappings=True)
    return row is not None
