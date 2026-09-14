"""Run one tool call: check args, run it off the event loop with a timeout,
cap the result, and always write an audit row."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from typing import Any, Awaitable, Callable

from . import config, store, tools
from .auth import McpAuthContext
from .errors import McpError, TimeoutToolError, ToolError

logger = logging.getLogger(__name__)

_TOOL_SLOTS: asyncio.Semaphore | None = None


def _slots() -> asyncio.Semaphore:
    global _TOOL_SLOTS
    if _TOOL_SLOTS is None:
        _TOOL_SLOTS = asyncio.Semaphore(config.MAX_CONCURRENT_TOOL_CALLS)
    return _TOOL_SLOTS


def coerce_arguments(spec: tools.ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Some clients (mcp-remote) send every value as a string. Convert by
    the schema's declared type so ``limit="10"`` does not blow up as
    ``str * int`` inside the tool."""
    out = dict(arguments)
    for key, prop in spec.properties.items():
        if key not in out or out[key] is None:
            continue
        wanted = prop.get("type")
        raw = out[key]
        try:
            if wanted == "integer" and isinstance(raw, str):
                out[key] = int(raw.strip())
            elif wanted == "number" and isinstance(raw, str):
                out[key] = float(raw.strip())
            elif wanted == "boolean" and isinstance(raw, str):
                out[key] = raw.strip().lower() in {"true", "1", "yes"}
            elif wanted == "array" and isinstance(raw, str):
                out[key] = [s.strip() for s in raw.split(",") if s.strip()]
        except (TypeError, ValueError):
            raise ToolError(f"argument {key!r} must be a {wanted}, got {raw!r}")
    missing = [k for k in spec.required if out.get(k) in (None, "", [])]
    if missing:
        raise ToolError(f"missing required argument(s): {', '.join(missing)}")
    return out


def filter_kwargs_to_signature(fn: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    accepted = {p.name for p in sig.parameters.values()}
    return {k: v for k, v in kwargs.items() if k in accepted}


# The UI never shows an article whose topic alignment is below this; a topic's
# keyword collection pulls in name-collisions ("second nature", Juniper
# Networks) that the relevance step scores near zero and the views hide. The
# MCP tools returned them anyway, so an assistant reading a brand topic saw
# iOS release notes and college football (oviva, 14 Sep 2026). Same gate here,
# applied to any list of article rows in a tool result. Unscored rows pass.
RELEVANCE_FLOOR = 0.4
_ARTICLE_LIST_KEYS = ("articles", "results", "sample_articles", "related_articles")


def _row_alignment(row: Any) -> float | None:
    if not isinstance(row, dict):
        return None
    for key in ("topic_alignment_score", "alignment", "relevance"):
        v = row.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def gate_low_relevance(result: Any) -> Any:
    """Drop article rows scored below RELEVANCE_FLOOR from a tool result."""
    if not isinstance(result, dict):
        return result
    dropped = 0
    for key in _ARTICLE_LIST_KEYS:
        rows = result.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        kept = [r for r in rows if (a := _row_alignment(r)) is None or a >= RELEVANCE_FLOOR]
        if len(kept) != len(rows):
            dropped += len(rows) - len(kept)
            result[key] = kept
            for count_key in ("total_articles", "total_results", "count", "total"):
                if isinstance(result.get(count_key), int):
                    result[count_key] = len(kept)
    if dropped:
        result["filtered_low_relevance"] = dropped
    return result


def cap_payload(payload: Any, *, max_bytes: int) -> dict[str, Any]:
    """Cap on a UTF-8 boundary so a cut never yields invalid text."""
    serialised = json.dumps(payload, default=str, ensure_ascii=False)
    encoded = serialised.encode("utf-8")
    if len(encoded) <= max_bytes:
        return {"truncated": False, "data": payload}
    cap = max(0, max_bytes - len(config.TRUNCATION_MARKER.encode("utf-8")) - 64)
    safe = encoded[:cap].decode("utf-8", errors="ignore")
    return {
        "truncated": True,
        "marker": config.TRUNCATION_MARKER,
        "data": safe,
        "byte_count": len(encoded),
    }


async def _run_tool(fn: Callable[..., Awaitable[dict]], kwargs: dict[str, Any], timeout: float) -> Any:
    """Run the tool coroutine on a worker thread with its own event loop.

    The Auspex tools are ``async def`` but do synchronous database work
    inside, which would freeze this process's loop if awaited directly.
    Creating the coroutine inside the thread keeps it bound to that
    thread's loop.
    """
    async with _slots():
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: asyncio.run(fn(**kwargs))),
            timeout=timeout,
        )


def _status_for(exc: BaseException) -> str:
    if isinstance(exc, TimeoutToolError):
        return "timeout"
    return "error"


async def record_tool_call(ctx: McpAuthContext, **fields: Any) -> None:
    row = {
        "username": ctx.username,
        "api_key_id": ctx.api_key_id,
        "oauth_client_id": ctx.oauth_client_id,
        "auth_kind": ctx.auth_kind,
        **fields,
    }
    try:
        await asyncio.to_thread(store.insert_tool_call, row)
        if ctx.api_key_id:
            await asyncio.to_thread(store.touch_api_key, ctx.api_key_id)
    except Exception:  # noqa: BLE001 — audit must never break a call
        logger.exception("mcp: failed to record tool call")


async def dispatch(
    ctx: McpAuthContext,
    *,
    tool_name: str,
    arguments: dict[str, Any] | None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    arguments = arguments or {}
    request_bytes = len(json.dumps(arguments, default=str).encode("utf-8"))
    status = "ok"
    error_code: str | None = None
    response_bytes: int | None = None
    try:
        spec, fn = tools.resolve(tool_name)
        args = coerce_arguments(spec, arguments)
        args["ctx"] = ctx
        kwargs = filter_kwargs_to_signature(fn, args)
        try:
            if spec.method is None:
                result = await asyncio.wait_for(fn(**kwargs), timeout=spec.timeout)
            else:
                result = await _run_tool(fn, kwargs, spec.timeout)
        except asyncio.TimeoutError:
            raise TimeoutToolError(f"{tool_name} timed out after {spec.timeout:.0f}s")
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("mcp: tool %s failed", tool_name)
            raise ToolError(f"{tool_name} failed: {type(exc).__name__}")
        result = gate_low_relevance(result)
        payload = cap_payload(result, max_bytes=spec.max_bytes)
        response_bytes = len(json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8"))
        return payload
    except BaseException as exc:
        status = _status_for(exc)
        error_code = type(exc).__name__
        raise
    finally:
        await record_tool_call(
            ctx,
            tool_name=tool_name[:64],
            status=status,
            error_code=error_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            user_agent=(user_agent or "")[:400] or None,
        )
