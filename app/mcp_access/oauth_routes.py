"""OAuth 2.1 endpoints for the MCP server (RFC 8414, 9728, 7591, 7636).

Flow as the claude.ai connector drives it:

1. ``GET /.well-known/oauth-protected-resource`` and
   ``GET /.well-known/oauth-authorization-server`` for discovery.
2. ``POST /oauth/register`` to get a client id and secret.
3. Browser: ``GET /oauth/authorize`` (redirects to ``/login?next=`` when
   there is no session) then ``/oauth/consent`` where the user clicks Allow.
4. ``POST /oauth/token`` exchanges the code (with PKCE) for a one-hour JWT
   and a 90-day refresh token; later calls use ``grant_type=refresh_token``.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.security.session import verify_session

from . import config, oauth_service as svc, store, tools

logger = logging.getLogger(__name__)

router = APIRouter()

pending_consent = svc.PendingConsentStore()
_register_limiter = svc.RateLimiter(rate_per_minute=30)
_token_limiter = svc.RateLimiter(rate_per_minute=60)


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


def _session_user(request: Request) -> str | None:
    try:
        user = request.session.get("user")
    except AssertionError:  # SessionMiddleware absent (bare test app)
        return None
    return user.lower() if isinstance(user, str) and user else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ─── Discovery ──────────────────────────────────────────────────────────────

@router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict[str, Any]:
    base = config.base_url()
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [config.WORKSPACE_SCOPE],
    }


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata() -> dict[str, Any]:
    base = config.base_url()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "scopes_supported": [config.WORKSPACE_SCOPE],
    }


# ─── Dynamic client registration ────────────────────────────────────────────

@router.post("/oauth/register", status_code=201)
async def register_client(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Anonymous by spec (RFC 7591); rate limited per client IP."""
    if not _register_limiter.allow(_client_ip(request)):
        raise HTTPException(429, "too many registrations; try again in a minute")
    if not isinstance(body, dict):
        raise HTTPException(400, "body must be a JSON object")
    client_name = body.get("client_name")
    redirect_uris = body.get("redirect_uris")
    if not isinstance(client_name, str) or not client_name.strip():
        raise HTTPException(400, "client_name required (non-empty string)")
    if not isinstance(redirect_uris, list) or not redirect_uris:
        raise HTTPException(400, "redirect_uris required (non-empty array)")
    for uri in redirect_uris:
        if not svc.validate_redirect_uri(uri):
            raise HTTPException(
                400, f"redirect_uri must be https:// or http://localhost / http://127.0.0.1 (got: {uri!r})",
            )

    client_id = svc.generate_client_id()
    raw_secret, secret_hash = svc.generate_client_secret()
    await asyncio.to_thread(
        store.insert_client,
        client_id=client_id, client_secret_hash=secret_hash,
        client_name=client_name.strip()[:200], redirect_uris=list(redirect_uris),
    )
    logger.info("mcp oauth: registered client %s (%s), %d redirect uri(s)",
                client_id, client_name.strip(), len(redirect_uris))
    return {
        "client_id": client_id,
        "client_secret": raw_secret,
        "client_name": client_name.strip(),
        "redirect_uris": list(redirect_uris),
        "client_id_issued_at": int(datetime.now(timezone.utc).timestamp()),
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }


# ─── Authorize + consent ────────────────────────────────────────────────────

@router.get("/oauth/authorize")
async def authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: str = Query(""),
    scope: str = Query(config.WORKSPACE_SCOPE),
) -> RedirectResponse:
    """Validate the request, then send the browser to login (if needed) and
    the consent page. Nothing is granted here."""
    if response_type != "code":
        raise HTTPException(400, "response_type must be 'code'")
    if code_challenge_method != "S256":
        raise HTTPException(400, "code_challenge_method must be 'S256'")
    if not code_challenge:
        raise HTTPException(400, "code_challenge is required")

    client = await asyncio.to_thread(store.get_client, client_id)
    if client is None:
        raise HTTPException(400, "unknown client_id")
    if redirect_uri not in (client.get("redirect_uris") or []):
        raise HTTPException(400, "redirect_uri not registered for this client")

    username = _session_user(request)
    if not username:
        next_url = "/oauth/authorize?" + urlencode({
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "state": state,
            "scope": scope,
        })
        return RedirectResponse(url=f"/login?next={quote(next_url, safe='')}", status_code=302)

    request_id = pending_consent.put({
        "client_id": client_id,
        "client_name": client.get("client_name") or client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state,
        "scope": scope or config.WORKSPACE_SCOPE,
        "username": username,
    })
    return RedirectResponse(url=f"/oauth/consent?request_id={request_id}", status_code=302)


def _render_consent(request: Request, context: dict[str, Any], status_code: int = 200):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "mcp_consent.html",
        {"request": request, "session": request.session, **context},
        status_code=status_code,
    )


@router.get("/oauth/consent")
async def consent_page(request: Request, request_id: str = Query(""), session=Depends(verify_session)):
    pending = pending_consent.peek(request_id) if request_id else None
    if pending is None:
        return _render_consent(request, {"error": "This consent link has expired. Go back to the app that asked to connect and try again."}, 404)
    if pending["username"] != _session_user(request):
        return _render_consent(request, {"error": "This connection request was started by a different user."}, 403)
    return _render_consent(request, {
        "request_id": request_id,
        "client_name": pending["client_name"],
        "redirect_host": urlparse(pending["redirect_uri"]).netloc or pending["redirect_uri"],
        "username": pending["username"],
        "site": config.host_name(),
        "tools": [t.name for t in tools.available_tools()],
        "access_hours": int(config.ACCESS_TOKEN_TTL.total_seconds() // 3600),
        "refresh_days": config.REFRESH_TOKEN_TTL.days,
    })


@router.post("/oauth/consent")
async def consent_decision(
    request: Request,
    request_id: str = Form(...),
    decision: str = Form(...),
    session=Depends(verify_session),
):
    if decision not in ("allow", "deny"):
        raise HTTPException(400, "decision must be 'allow' or 'deny'")
    pending = pending_consent.pop(request_id)
    if pending is None:
        return _render_consent(request, {"error": "This consent link has expired. Go back to the app that asked to connect and try again."}, 404)
    if pending["username"] != _session_user(request):
        return _render_consent(request, {"error": "This connection request was started by a different user."}, 403)

    redirect = pending["redirect_uri"]
    state = pending.get("state") or ""
    if decision == "deny":
        params = {"error": "access_denied"}
        if state:
            params["state"] = state
        return RedirectResponse(url=f"{redirect}?{urlencode(params)}", status_code=302)

    code = svc.generate_authorization_code()
    await asyncio.to_thread(
        store.insert_auth_code,
        code=code, client_id=pending["client_id"], username=pending["username"],
        redirect_uri=redirect, scope=pending["scope"],
        code_challenge=pending["code_challenge"],
        code_challenge_method=pending["code_challenge_method"],
        expires_at=datetime.now(timezone.utc) + config.AUTHORIZATION_CODE_TTL,
    )
    logger.info("mcp oauth: %s granted client %s", pending["username"], pending["client_id"])
    params = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(url=f"{redirect}?{urlencode(params)}", status_code=302)


# ─── Token ──────────────────────────────────────────────────────────────────

def _basic_auth(request: Request) -> tuple[str, str] | None:
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header.split(None, 1)[1].strip()).decode("utf-8")
    except (ValueError, IndexError):
        return None
    if ":" not in raw:
        return None
    cid, _, secret = raw.partition(":")
    return cid, secret


def _token_error(error: str, description: str | None = None, status: int = 400) -> JSONResponse:
    body: dict[str, Any] = {"error": error}
    if description:
        body["error_description"] = description
    return JSONResponse(body, status_code=status)


def _token_response(access: str, scope: str, refresh: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(config.ACCESS_TOKEN_TTL.total_seconds()),
        "scope": scope,
    }
    if refresh:
        body["refresh_token"] = refresh
    return JSONResponse(body)


@router.post("/oauth/token")
async def token(request: Request) -> JSONResponse:
    """Client secret plus PKCE are checked inside; rate limited per IP."""
    if not _token_limiter.allow(_client_ip(request)):
        return _token_error("slow_down", "too many token requests", 429)
    form = await request.form()
    grant_type = form.get("grant_type")
    if grant_type not in ("authorization_code", "refresh_token"):
        return _token_error("unsupported_grant_type")

    basic = _basic_auth(request)
    if basic is not None:
        client_id, client_secret = basic
    else:
        client_id = str(form.get("client_id") or "")
        client_secret = str(form.get("client_secret") or "")
    if not client_id or not client_secret:
        return _token_error("invalid_client", "client auth missing", 401)
    client = await asyncio.to_thread(store.get_client, client_id)
    if client is None or not svc.verify_client_secret(client.get("client_secret_hash"), client_secret):
        return _token_error("invalid_client", status=401)

    now = datetime.now(timezone.utc)

    if grant_type == "authorization_code":
        code = str(form.get("code") or "")
        code_verifier = str(form.get("code_verifier") or "")
        redirect_uri = str(form.get("redirect_uri") or "")
        if not code or not code_verifier or not redirect_uri:
            return _token_error("invalid_request")
        row = await asyncio.to_thread(store.get_auth_code, code)
        if (
            row is None
            or row.get("consumed_at") is not None
            or _as_utc(row.get("expires_at")) <= now
            or row.get("client_id") != client_id
            or row.get("redirect_uri") != redirect_uri
        ):
            return _token_error("invalid_grant")
        if not svc.verify_pkce(row.get("code_challenge"), code_verifier):
            return _token_error("invalid_grant", "pkce mismatch")
        if not await asyncio.to_thread(store.consume_auth_code, code):
            return _token_error("invalid_grant")

        username = row["username"]
        scope = row.get("scope") or config.WORKSPACE_SCOPE
        access = svc.mint_access_token(username=username, client_id=client_id, scope=scope)
        raw_refresh, refresh_hash = svc.mint_refresh_token()
        await asyncio.to_thread(
            store.insert_refresh_token,
            token_hash=refresh_hash, client_id=client_id, username=username,
            scope=scope, expires_at=now + config.REFRESH_TOKEN_TTL,
        )
        return _token_response(access, scope, raw_refresh)

    raw_refresh = str(form.get("refresh_token") or "")
    if not raw_refresh:
        return _token_error("invalid_request")
    row = await asyncio.to_thread(store.get_refresh_token, svc.hash_secret(raw_refresh))
    if (
        row is None
        or row.get("revoked_at") is not None
        or _as_utc(row.get("expires_at")) <= now
        or row.get("client_id") != client_id
    ):
        return _token_error("invalid_grant")
    if not await asyncio.to_thread(store.user_exists_active, row["username"]):
        return _token_error("invalid_grant", "user inactive")
    scope = row.get("scope") or config.WORKSPACE_SCOPE
    access = svc.mint_access_token(username=row["username"], client_id=client_id, scope=scope)
    return _token_response(access, scope)
