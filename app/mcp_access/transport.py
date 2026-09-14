"""JSON-RPC 2.0 over ``POST /mcp``.

Handles ``initialize``, ``ping``, ``tools/list``, ``tools/call``,
``prompts/list`` and ``prompts/get``. Notifications (no ``id``) get a 202
with no body. Every other method authenticates first; a missing or bad
token gets a 401 with a ``WWW-Authenticate`` header that points at the
OAuth discovery document, which is what makes the claude.ai connector UI
start its login flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from . import config, dispatcher, recipes, tools
from .auth import authenticate
from .errors import McpError

logger = logging.getLogger(__name__)

router = APIRouter()


def _www_authenticate_header() -> dict[str, str]:
    return {
        "WWW-Authenticate": (
            'Bearer realm="aunoo-mcp", '
            f'resource_metadata="{config.base_url()}/.well-known/oauth-protected-resource"'
        ),
    }


def _ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _err(rpc_id: Any, *, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": err}


def _error_response(rpc_id: Any, exc: McpError) -> JSONResponse:
    return JSONResponse(
        _err(rpc_id, code=exc.mcp_code, message=exc.message, data=exc.detail or None),
        status_code=exc.http_status,
        headers=_www_authenticate_header() if exc.http_status == 401 else None,
    )


def _tool_text_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, default=str, ensure_ascii=False)}],
        "isError": False,
    }


def _tools_for_listing() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "inputSchema": tools.input_schema(t)}
        for t in tools.available_tools()
    ]


def _protocol_version(request: Request, params: dict[str, Any]) -> str:
    asked = request.headers.get("mcp-protocol-version") or params.get("protocolVersion")
    if isinstance(asked, str) and asked in config.ACCEPTED_PROTOCOL_VERSIONS:
        return asked
    return config.PROTOCOL_VERSION


def _instructions() -> str:
    names = ", ".join(r["name"] for r in recipes.list_recipes())
    return (
        f"You are connected to {config.server_name()}, a news intelligence site. "
        "Call list_capabilities first to learn the topic names; pass them "
        "exactly as returned. Prefer the article tools over training-time "
        f"guesses for current events. Named playbooks ({names}) are available "
        "via prompts/list."
    )


async def _handle(request: Request, authorization: str | None) -> JSONResponse:
    try:
        envelope = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(_err(None, code=-32700, message="parse error"), status_code=400)
    if not isinstance(envelope, dict) or envelope.get("jsonrpc") != "2.0":
        return JSONResponse(_err(None, code=-32600, message="invalid request"), status_code=400)

    rpc_id = envelope.get("id")
    method = envelope.get("method")
    params = envelope.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if rpc_id is None:
        return Response(status_code=202)

    if not authorization:
        return JSONResponse(
            _err(rpc_id, code=-32001, message="authorization required"),
            status_code=401,
            headers=_www_authenticate_header(),
        )
    try:
        ctx = await authenticate(authorization)
    except McpError as exc:
        return _error_response(rpc_id, exc)

    if method == "initialize":
        return JSONResponse(_ok(rpc_id, {
            "protocolVersion": _protocol_version(request, params),
            "capabilities": {
                "tools": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": config.server_name(), "version": config.SERVER_VERSION},
            "instructions": _instructions(),
        }))

    if method == "ping":
        return JSONResponse(_ok(rpc_id, {}))

    if method == "tools/list":
        return JSONResponse(_ok(rpc_id, {"tools": _tools_for_listing()}))

    if method == "prompts/list":
        return JSONResponse(_ok(rpc_id, {"prompts": recipes.list_recipes()}))

    if method == "prompts/get":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return JSONResponse(_err(rpc_id, code=-32602, message="params.name required"), status_code=400)
        if not isinstance(arguments, dict):
            return JSONResponse(_err(rpc_id, code=-32602, message="params.arguments must be an object"), status_code=400)
        messages = recipes.render_recipe(name, arguments)
        if messages is None:
            return JSONResponse(_err(rpc_id, code=-32602, message=f"unknown prompt: {name!r}"), status_code=404)
        recipe = recipes.get_recipe(name)
        return JSONResponse(_ok(rpc_id, {
            "description": recipe.description if recipe else "",
            "messages": messages,
        }))

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return JSONResponse(_err(rpc_id, code=-32602, message="params.name required"), status_code=400)
        if not isinstance(arguments, dict):
            return JSONResponse(_err(rpc_id, code=-32602, message="params.arguments must be an object"), status_code=400)
        try:
            payload = await dispatcher.dispatch(
                ctx, tool_name=name, arguments=arguments,
                user_agent=request.headers.get("user-agent"),
            )
        except McpError as exc:
            return _error_response(rpc_id, exc)
        return JSONResponse(_ok(rpc_id, _tool_text_content(payload)))

    return JSONResponse(_err(rpc_id, code=-32601, message=f"method not found: {method!r}"), status_code=404)


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """MCP JSON-RPC endpoint. Authenticates inside: bearer key or OAuth JWT."""
    return await _handle(request, authorization)


@router.get("/mcp")
async def mcp_get() -> JSONResponse:
    """Streamable-HTTP clients probe GET for a server-push stream. We have
    none; say so instead of letting the request fall through."""
    return JSONResponse({"error": "use POST with a JSON-RPC 2.0 body"}, status_code=405)


@router.delete("/mcp")
async def mcp_delete() -> Response:
    """Session close from streamable-HTTP clients. Nothing to close."""
    return Response(status_code=204)
