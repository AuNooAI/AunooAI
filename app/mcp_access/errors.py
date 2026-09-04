"""Errors the MCP transport turns into JSON-RPC error objects."""

from __future__ import annotations

from typing import Any


class McpError(Exception):
    http_status = 500
    mcp_code = -32000

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class AuthError(McpError):
    http_status = 401
    mcp_code = -32001


class ToolError(McpError):
    http_status = 400
    mcp_code = -32003


class TimeoutToolError(ToolError):
    http_status = 504
