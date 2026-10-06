"""Trust Signals for this site's articles, rated by the saas Skills API.

The five per-article ratings (Source, Claims, Origin, Spread, Owner) depend
on data only the saas service keeps current: the Media Bias/Fact Check
record for 8,000-odd outlets, the beneficial-owner map, republication
history and claim verdicts. This site holds its own articles and only a few
of those fields, so ``get_trust_signals`` sends the article URLs to saas's
``get_trust_signals_for_urls`` and returns what comes back, with this
site's title attached where the URI is one of ours.

Configuration: ``SAAS_SKILLS_URL`` (the saas base URL) and
``SAAS_SKILLS_KEY`` (a saas workspace key). Without both the tool is not
listed. Answers are cached for an hour per URL, because the outlet-level
stations change rarely and an assistant tends to ask twice.

A station with tone ``neutral`` was not measured. For a URL saas does not
hold that is Claims, Origin and Spread, and the entry says so in ``note``.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from sqlalchemy import text

from . import config
from .errors import ToolError
from .tools import ToolSpec

MAX_URIS = 25
CACHE_TTL_SECONDS = 3600
CACHE_MAX_ENTRIES = 2000
REMOTE_TIMEOUT_SECONDS = 25.0

_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}

SPECS: dict[str, ToolSpec] = {
    "get_trust_signals": ToolSpec(
        name="get_trust_signals",
        description=(
            "The five Trust Signals for an article: ① Source (outlet bias, "
            "factual record, credibility) ② Claims ③ Origin (AI-written?) "
            "④ Spread (republication, owner concentration) ⑤ Owner (who owns "
            "the outlet). Pass one uri or up to 25 uris as other tools return "
            "them. Rated by the Aunoo trust service from the outlet's Media "
            "Bias/Fact Check record and ownership map; Claims, Origin and "
            "Spread are measured only for articles that service also holds, "
            "otherwise they read neutral. Neutral means NOT measured, never "
            "clean. Read-only and free."
        ),
        properties={
            "uri": {"type": "string", "description": "Article URI, for one article"},
            "uris": {"type": "array", "items": {"type": "string"},
                     "description": "Up to 25 article URIs, rated in one call"},
            "window_hours": {"type": "integer", "default": 72, "minimum": 1, "maximum": 720,
                             "description": "Look-back for the Claims and Spread republication counts"},
        },
        timeout=REMOTE_TIMEOUT_SECONDS + 5,
        max_bytes=128 * 1024,
        needs_saas=True,
    ),
}


def _clean(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    u = raw.strip().split("#", 1)[0]
    return u if u.lower().startswith(("http://", "https://")) else None


def _local_titles_sync(uris: list[str]) -> dict[str, dict[str, Any]]:
    """{uri: {title, news_source, publication_date}} for the URIs this site holds."""
    from app.database import get_database_instance
    conn = get_database_instance()._temp_get_connection()
    try:
        rows = conn.execute(text(
            "SELECT uri, title, news_source, publication_date FROM articles WHERE uri = ANY(:u)"
        ), {"u": uris}).fetchall()
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return {r[0]: {"title": r[1], "news_source": r[2],
                   "publication_date": str(r[3]) if r[3] else None} for r in rows}


async def _post(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """One call to the saas Skills REST endpoint. Returns the dispatcher payload
    ``{"truncated": bool, "data": ...}``; HTTP and auth failures become ToolErrors."""
    import httpx
    url = f"{config.saas_skills_url()}/api/v1/skills/workspace/run"
    headers = {
        "Authorization": f"Bearer {config.saas_skills_key()}",
        "User-Agent": f"aunoo-mcp/{config.host_name()}",
    }
    try:
        async with httpx.AsyncClient(timeout=REMOTE_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json={"tool": tool, "arguments": arguments}, headers=headers)
    except httpx.HTTPError as exc:
        raise ToolError(f"trust service unreachable: {type(exc).__name__}")
    if resp.status_code != 200:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        detail = body.get("detail") if isinstance(body, dict) else None
        message = (detail or {}).get("message") if isinstance(detail, dict) else None
        raise ToolError(f"trust service returned {resp.status_code}: {message or resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError:
        raise ToolError("trust service returned a non-JSON body")
    if not isinstance(payload, dict) or "data" not in payload:
        raise ToolError("trust service returned an unexpected shape")
    return payload


def _cache_get(uri: str, hours: int) -> dict[str, Any] | None:
    hit = _cache.get((uri, hours))
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _cache_put(uri: str, hours: int, entry: dict[str, Any]) -> None:
    if len(_cache) >= CACHE_MAX_ENTRIES:
        now = time.monotonic()
        for k in [k for k, v in _cache.items() if v[0] <= now]:
            _cache.pop(k, None)
        if len(_cache) >= CACHE_MAX_ENTRIES:
            _cache.clear()
    _cache[(uri, hours)] = (time.monotonic() + CACHE_TTL_SECONDS, entry)


async def get_trust_signals(ctx=None, uri: str | None = None, uris: list[str] | None = None,
                            window_hours: int = 72) -> dict[str, Any]:
    wanted: list[str] = []
    invalid: list[Any] = []
    for raw in ([uri] if uri is not None else []) + list(uris or []):
        u = _clean(raw)
        if u is None:
            invalid.append(raw)
        elif u not in wanted:
            wanted.append(u)
    if not wanted:
        raise ToolError("pass uri or uris (http(s) URLs as the other tools return them)")
    if len(wanted) > MAX_URIS:
        raise ToolError(f"at most {MAX_URIS} uris per call, got {len(wanted)}")
    hours = max(1, min(int(window_hours or 72), 720))

    entries: dict[str, dict[str, Any]] = {}
    to_fetch = []
    for u in wanted:
        cached = _cache_get(u, hours)
        if cached is not None:
            entries[u] = dict(cached, cached=True)
        else:
            to_fetch.append(u)

    remote: dict[str, Any] = {}
    if to_fetch:
        payload = await _post("get_trust_signals_for_urls", {"urls": to_fetch, "window_hours": hours})
        if payload.get("truncated"):
            raise ToolError("trust service answer was truncated; ask for fewer uris")
        remote = payload.get("data") or {}
        for entry in remote.get("articles") or []:
            u = entry.get("url")
            if isinstance(u, str):
                entries[u] = entry
                _cache_put(u, hours, entry)
        invalid.extend(remote.get("invalid") or [])

    local = await asyncio.to_thread(_local_titles_sync, wanted)
    out = []
    for u in wanted:
        entry = entries.get(u)
        if entry is None:
            continue
        entry = dict(entry)
        if u in local:
            entry["local_article"] = local[u]
        out.append(entry)

    return {
        "window_hours": hours,
        "rated_by": urlparse(config.saas_skills_url()).netloc,
        "articles": out,
        "invalid": invalid,
        "tone_key": remote.get("tone_key") or {
            "pass": "healthy", "warn": "worth a look", "fail": "a problem",
            "neutral": "not assessed — absence of a measurement, not a clean bill",
        },
    }


HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "get_trust_signals": get_trust_signals,
}
