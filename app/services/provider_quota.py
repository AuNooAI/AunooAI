"""The quota guard a collector calls around every paid provider request.

Thin wrapper over the host-wide ``SharedLedger`` so collectors stay short:

    guard = QuotaGuard("newsapi", api_key)
    blocked = guard.check()          # a CollectionResult, or None to proceed
    if blocked: return blocked
    ... send request ...
    guard.ok() / guard.exhausted(retry_after=..., detail=...) / guard.error()

``check`` reserves one unit; ``exhausted`` pauses the key for every site on
the host. Both repositories carry this file unchanged.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work package 20.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping, Optional

from app.collectors.contracts import CollectionResult
from app.services.shared_ledger import get_ledger, parse_retry_after

logger = logging.getLogger(__name__)

_EXHAUSTION_PHRASES = (
    "rate limit", "ratelimit", "too many requests", "usage limit",
    "exceeded your assigned api credits", "api credits", "quota",
    "limit reached", "rateLimited".lower(),
)


def looks_exhausted(status: Optional[int], body: Any = None, code: Optional[str] = None) -> bool:
    """True when a provider answer means the key is out of budget: HTTP 429,
    a known error code, or an exhaustion phrase in the body."""
    if status == 429:
        return True
    if code and str(code).lower() in ("ratelimited", "rate_limited", "quota_exceeded", "usage_limit"):
        return True
    text = ""
    if isinstance(body, Mapping):
        for key in ("message", "error", "detail", "results"):
            val = body.get(key)
            if isinstance(val, Mapping):
                val = val.get("message")
            if val:
                text += f" {val}"
    elif body is not None:
        text = str(body)
    low = text.lower()
    return any(p in low for p in _EXHAUSTION_PHRASES)


class QuotaGuard:
    def __init__(self, provider: str, key: Optional[str], *, tenant: Optional[str] = None,
                 scope: Optional[str] = None):
        self.provider = provider
        self.key = key
        self.tenant = tenant
        self.scope = scope
        self._ledger = None

    @property
    def ledger(self):
        if self._ledger is None:
            self._ledger = get_ledger()
        return self._ledger

    def check(self, units: int = 1) -> Optional[CollectionResult]:
        """Reserve budget. Returns a quota-exhausted result to hand back when
        the request must not be sent, else None."""
        try:
            res = self.ledger.reserve(self.provider, self.key, tenant=self.tenant, units=units)
        except Exception as exc:  # noqa: BLE001
            # A broken ledger must not stop collection; it only loses sharing.
            logger.warning("quota ledger unavailable for %s: %s", self.provider, exc)
            return None
        if res.ok:
            return None
        why = {"exhausted": "key paused after a provider rate-limit response",
               "budget": "period budget spent across all sites",
               "share": "this site's share spent and nothing left to borrow"}.get(res.reason, res.reason)
        out = CollectionResult.quota_exhausted(self.provider, res.exhausted_until, message=f"{self.provider}: {why}",
                                               scope=self.scope)
        out.diagnostics.update({"quota_reason": res.reason, "quota_used": res.used, "quota_budget": res.budget,
                                "quota_period_start": res.period_start, "tenant_used": res.tenant_used,
                                "tenant_share": res.tenant_share, "key": res.fingerprint})
        out.counts.quota_skipped += 1
        return out

    def ok(self) -> None:
        try:
            self.ledger.record_response(self.provider, self.key, "ok", tenant=self.tenant)
        except Exception:  # noqa: BLE001
            pass

    def error(self, detail: str = "") -> None:
        try:
            self.ledger.record_response(self.provider, self.key, "error", detail=detail, tenant=self.tenant)
        except Exception:  # noqa: BLE001
            pass

    def exhausted(self, *, retry_after: Any = None, reset_at: Optional[datetime] = None,
                  detail: str = "") -> Optional[datetime]:
        """Pause the key for every site. ``retry_after`` may be a header
        value (seconds or HTTP date) or a number of seconds."""
        try:
            seconds = parse_retry_after(retry_after) if retry_after is not None else None
            return self.ledger.record_response(self.provider, self.key, "quota", retry_after_seconds=seconds,
                                               reset_at=reset_at, detail=detail, tenant=self.tenant)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quota ledger unavailable for %s: %s", self.provider, exc)
            return None

    def result_for_exhaustion(self, until: Optional[datetime], detail: str = "") -> CollectionResult:
        out = CollectionResult.quota_exhausted(self.provider, until, message=detail or None, scope=self.scope)
        out.counts.quota_skipped += 1
        return out


class HostGuard:
    """Same shape for hosts that rate-limit by client address (reddit.com)."""

    def __init__(self, host: str, *, tenant: Optional[str] = None):
        self.host = host
        self.tenant = tenant

    def check(self) -> Optional[CollectionResult]:
        try:
            res = get_ledger().host_acquire(self.host, tenant=self.tenant)
        except Exception as exc:  # noqa: BLE001
            logger.warning("host budget unavailable for %s: %s", self.host, exc)
            return None
        if res.ok:
            return None
        out = CollectionResult.quota_exhausted(f"host:{self.host}", res.exhausted_until,
                                               message=f"{self.host}: {res.reason}")
        out.counts.quota_skipped += 1
        return out

    def rate_limited(self, retry_after: Any = None) -> Optional[datetime]:
        try:
            return get_ledger().host_record_429(self.host, retry_after_seconds=parse_retry_after(retry_after),
                                                tenant=self.tenant)
        except Exception:  # noqa: BLE001
            return None
