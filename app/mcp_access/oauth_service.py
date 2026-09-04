"""OAuth 2.1 helpers: pure functions plus two tiny in-process stores.

Access tokens are HS256 JWTs signed with the site's ``NORN_SECRET_KEY``.
They carry ``aud = <base_url>/mcp`` so nothing else the app signs can be
mistaken for one. Refresh tokens, client secrets and authorization codes
are opaque random strings; only their sha256 is stored.

PKCE is S256 only, as OAuth 2.1 requires.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt

from . import config


# ─── Hashing ────────────────────────────────────────────────────────────────

def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_client_secret(stored_hash: str | None, presented: str | None) -> bool:
    if not stored_hash or not presented:
        return False
    return hmac.compare_digest(stored_hash, hash_secret(presented))


def verify_pkce(code_challenge: str | None, code_verifier: str | None) -> bool:
    """``code_challenge == BASE64URL(SHA256(code_verifier))`` without padding."""
    if not code_challenge or not code_verifier:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(expected, code_challenge)


def validate_redirect_uri(uri: str) -> bool:
    """https anywhere, or plain http on the loopback host (Claude Desktop
    registers ``http://127.0.0.1:<port>/callback``)."""
    if not isinstance(uri, str):
        return False
    if uri.startswith("https://"):
        return True
    for host in ("localhost", "127.0.0.1"):
        if uri == f"http://{host}" or uri.startswith(f"http://{host}:") \
                or uri.startswith(f"http://{host}/"):
            return True
    return False


# ─── Tokens ─────────────────────────────────────────────────────────────────

def mint_access_token(
    *,
    username: str,
    client_id: str,
    scope: str = config.WORKSPACE_SCOPE,
    ttl=config.ACCESS_TOKEN_TTL,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": config.issuer(),
        "aud": config.mcp_audience(),
        "sub": username.lower(),
        "client_id": client_id,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, config.signing_secret(), algorithm="HS256")


def decode_access_token(token: str | None) -> dict[str, Any] | None:
    """Claims on success, None on any failure. Callers fall through to the
    static-key lookup on None, so this must never raise for bad input."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            config.signing_secret(),
            algorithms=["HS256"],
            audience=config.mcp_audience(),
            issuer=config.issuer(),
        )
    except (JWTError, RuntimeError, ValueError):
        return None
    if not isinstance(claims, dict):
        return None
    if not claims.get("sub") or not claims.get("client_id"):
        return None
    return claims


def mint_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_secret(raw)


def generate_authorization_code() -> str:
    return secrets.token_urlsafe(32)


def generate_client_id() -> str:
    return secrets.token_urlsafe(24)


def generate_client_secret() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_secret(raw)


# ─── In-process state ───────────────────────────────────────────────────────
#
# The app runs one uvicorn worker, so a dict is enough for the five minutes
# between /oauth/authorize and the consent decision. A restart in that window
# shows "consent link has expired"; the user clicks Connect again.

class PendingConsentStore:
    def __init__(self, ttl_seconds: float | None = None) -> None:
        self._ttl = ttl_seconds or config.PENDING_CONSENT_TTL.total_seconds()
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _sweep(self, now: float) -> None:
        dead = [k for k, (exp, _) in self._items.items() if exp <= now]
        for k in dead:
            self._items.pop(k, None)

    def put(self, payload: dict[str, Any]) -> str:
        request_id = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            self._items[request_id] = (now + self._ttl, dict(payload))
        return request_id

    def peek(self, request_id: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            item = self._items.get(request_id)
            return dict(item[1]) if item else None

    def pop(self, request_id: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            item = self._items.pop(request_id, None)
            return dict(item[1]) if item else None


class RateLimiter:
    """Token bucket per key (client IP). Protects the two anonymous OAuth
    endpoints from a script registering clients in a loop."""

    def __init__(self, rate_per_minute: int = 30, burst: int | None = None) -> None:
        self._rate = rate_per_minute / 60.0
        self._burst = float(burst or rate_per_minute)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._burst, now))
            tokens = min(self._burst, tokens + (now - last) * self._rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > 10000:
                stale = [k for k, (_, t) in self._buckets.items() if now - t > 600]
                for k in stale:
                    self._buckets.pop(k, None)
            return True
