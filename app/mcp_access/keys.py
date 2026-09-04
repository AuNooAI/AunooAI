"""Static bearer keys: ``aunoo_`` + 32 random bytes, stored as sha256."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

KEY_PREFIX = "aunoo_"
PREFIX_DISPLAY_CHARS = 10


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def strip_bearer(header_value: str | None) -> str | None:
    """Return the token from ``Bearer <token>``, or None if malformed."""
    if not header_value:
        return None
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def new_plaintext() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def mint_key(
    *,
    username: str,
    name: str,
    expires_days: int | None = None,
    created_by: str | None = None,
) -> tuple[str, dict]:
    """Create a key row and return ``(plaintext, row)``.

    The plaintext exists only in the return value. Callers print or send it
    once and never store it.
    """
    from . import store

    plaintext = new_plaintext()
    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(expires_days))
    row = store.insert_api_key(
        username=username.lower(),
        name=name,
        key_prefix=plaintext[:PREFIX_DISPLAY_CHARS],
        key_hash=hash_token(plaintext),
        expires_at=expires_at,
        created_by=(created_by or "").lower() or None,
    )
    return plaintext, row
