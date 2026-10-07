"""Fetch a page through Firecrawl when a site blocks this server.

Some vendor sites refuse this server's address outright, whatever user agent
it sends: HelloBetter, Voy and Juniper (Oviva's market) and BlinkOps (whose
blog feed stopped on 17 Jul 2026) all answer 403 to every request. Firecrawl
fetches from elsewhere and returns the page as served, so a feed comes back
as its XML.

Used only as a fallback after a direct fetch was refused, so it is billed for
blocked sites alone. On whenever ``FIRECRAWL_API_KEY`` is set; set
``FIRECRAWL_FALLBACK=0`` to turn it off.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

#: Answers that mean "not you", not "not here": a bot wall, a rate limit, a
#: challenge page served as unavailable.
BLOCKED_STATUSES = frozenset({403, 429, 503})

_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT = 90.0


def _key() -> str:
    return (os.getenv("FIRECRAWL_API_KEY") or "").strip().strip('"').strip("'")


def available() -> bool:
    """Whether the fallback may be used: a key is set and it is not off."""
    return bool(_key()) and os.getenv("FIRECRAWL_FALLBACK", "1").strip() != "0"


def is_blocked(status: int) -> bool:
    return int(status or 0) in BLOCKED_STATUSES


async def fetch_raw(url: str) -> Optional[Tuple[int, str]]:
    """``(status, raw body)`` for ``url`` as Firecrawl saw it, or None when
    the fallback is off or Firecrawl did not return the page."""
    if not available():
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _SCRAPE_URL,
                headers={"Authorization": f"Bearer {_key()}"},
                json={"url": url, "formats": ["rawHtml"]})
        body = resp.json() if resp.content else {}
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("firecrawl fetch failed for %s: %s", url, exc)
        return None
    if resp.status_code != 200 or not body.get("success"):
        logger.warning("firecrawl refused %s: HTTP %s %s", url, resp.status_code,
                       str(body.get("error") or "")[:200])
        return None
    data = body.get("data") or {}
    raw = data.get("rawHtml") or ""
    status = int((data.get("metadata") or {}).get("statusCode") or 200)
    if not raw or status >= 400:
        logger.warning("firecrawl got HTTP %s and %d bytes for %s", status, len(raw), url)
        return None
    logger.info("fetched %s through firecrawl (%d bytes)", url, len(raw))
    return status, raw
