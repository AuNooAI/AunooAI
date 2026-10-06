"""Site-level constants for the MCP server.

One place for the public base URL (which the OAuth issuer, audience and
discovery documents all derive from) so the value cannot drift between
modules the way it did in the saas tree.
"""

from __future__ import annotations

import os
from datetime import timedelta
from urllib.parse import urlparse

PROTOCOL_VERSION = "2024-11-05"
# Versions we will echo back if the client asks for one of them. Claude.ai
# sends the newest; older clients send nothing.
ACCEPTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}

SERVER_VERSION = "0.1.0"

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=90)
AUTHORIZATION_CODE_TTL = timedelta(minutes=5)
PENDING_CONSENT_TTL = timedelta(minutes=5)

WORKSPACE_SCOPE = "mcp:workspace"

# Default per-call limits. Tool-specific overrides live in tools.py.
TOOL_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 32 * 1024
TRUNCATION_MARKER = "…truncated; narrow the query or lower the limit"

# How many tool calls may run at once. Each one occupies a worker thread
# for its whole duration (the Auspex tools do synchronous database work),
# and a timed-out call keeps its thread until it finishes on its own.
MAX_CONCURRENT_TOOL_CALLS = 4


def base_url() -> str:
    """Public origin of this site, without a trailing slash.

    ``APP_URL`` is the documented variable. ``DOMAIN`` is the fallback every
    tenant .env carries. The last resort keeps imports working in a test
    process that has neither.
    """
    raw = (os.getenv("APP_URL") or "").strip().rstrip("/")
    if raw:
        return raw
    domain = (os.getenv("DOMAIN") or "").strip().rstrip("/")
    if domain:
        if domain.startswith("http://") or domain.startswith("https://"):
            return domain
        return f"https://{domain}"
    return "http://localhost"


def host_name() -> str:
    return urlparse(base_url()).netloc or base_url()


def mcp_audience() -> str:
    return f"{base_url()}/mcp"


def issuer() -> str:
    return base_url()


def server_name() -> str:
    return f"Aunoo — {host_name()}"


def signing_secret() -> str:
    """Secret for OAuth access tokens. Same key the app uses for its own
    JWTs (``app/security/auth.py``), so one rotation covers both."""
    secret = os.getenv("NORN_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "NORN_SECRET_KEY is not set; the MCP OAuth flow cannot sign tokens"
        )
    return secret


def google_search_configured() -> bool:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
    cse = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    return bool(key and cse)


def saas_skills_url() -> str:
    """Base URL of the saas Skills API that rates outlets and articles for this
    site (Trust Signals). Empty when the site has no saas key."""
    return (os.getenv("SAAS_SKILLS_URL") or "").strip().rstrip("/")


def saas_skills_key() -> str:
    return (os.getenv("SAAS_SKILLS_KEY") or "").strip()


def saas_skills_configured() -> bool:
    return bool(saas_skills_url() and saas_skills_key())
