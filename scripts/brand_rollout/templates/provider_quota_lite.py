"""Shared provider quota for the older collectors (no CollectionResult).

Several sites on this host share one NewsAPI, NewsData and TheNewsAPI key,
but each site counted its own requests in memory and swallowed the
provider's 429, so the keys were refused all day (6 Oct 2026 wileytest
review). This adapter puts those collectors on the host-wide ledger that
canonical's collectors already use (app/services/shared_ledger.py, spec
docs/COLLECTOR_DATA_QUALITY_SPEC.md work package 20):

    quota_allows(provider, key)   before a request: False means do not send
                                  (key paused after a quota answer, or the
                                  period budget or this site's share is spent)
    quota_note(provider, key, status, message)
                                  after an error answer: a quota answer
                                  pauses the key for every site on the host

A broken ledger never stops collection; it only loses the sharing.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

_EXHAUSTION_PHRASES = (
    "rate limit", "ratelimit", "too many requests", "usage limit",
    "exceeded your assigned api credits", "api credits", "quota", "limit reached",
)


def looks_exhausted(status: Optional[int], body: Any = None) -> bool:
    if status == 429:
        return True
    text = ""
    if isinstance(body, Mapping):
        for k in ("message", "error", "detail", "results", "code"):
            v = body.get(k)
            if isinstance(v, Mapping):
                v = v.get("message")
            if v:
                text += f" {v}"
    elif body is not None:
        text = str(body)
    low = text.lower()
    return any(p in low for p in _EXHAUSTION_PHRASES)


def quota_allows(provider: str, key: Optional[str]) -> bool:
    try:
        from app.services.shared_ledger import get_ledger
        res = get_ledger().reserve(provider, key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quota ledger unavailable for %s: %s", provider, exc)
        return True
    if not res.ok:
        logger.warning("%s: request not sent (%s; shared ledger)", provider, res.reason)
    return bool(res.ok)


def quota_note(provider: str, key: Optional[str], status: Optional[int], message: Any = "") -> None:
    try:
        if not looks_exhausted(status, message):
            return
        from app.services.shared_ledger import get_ledger
        until = get_ledger().record_response(provider, key, "quota", detail=str(message)[:300])
        logger.warning("%s: quota answer (HTTP %s); key paused for all sites until %s", provider, status, until)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quota ledger unavailable for %s: %s", provider, exc)
