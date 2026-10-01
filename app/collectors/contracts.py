"""What one collection run reports back: outcome, coverage, counts, errors.

Before this module a collector returned a list of articles, and an empty list
meant "nothing new", "the provider refused us", "the feed is broken" and "we
ran out of quota" all at once. The caller then marked the source as polled
and moved its watermark forward, so a failed interval was never retried.

``CollectionResult`` separates those outcomes. A background task reads
``status`` and ``coverage_complete`` to decide whether the checkpoint may
move, keeps ``continuation`` when the run stopped early, and writes the whole
thing to the run record (work package 14). Compatibility wrappers may still
hand a plain list to code that has not moved yet; they build the list from
``items``.

This file is identical in the monolith and the SaaS repository. Keep it free
of imports from either application so it stays that way.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 1, 14 and 28.
"""
from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Vocabulary. Stable strings: they are written to run records and alerted on.
# ---------------------------------------------------------------------------

STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUSES = (STATUS_SUCCESS, STATUS_PARTIAL, STATUS_FAILED)

# Error categories (work package 28). Every failure maps to one of these.
ERR_TIMEOUT = "timeout"
ERR_CONNECTION = "connection"
ERR_DNS = "dns"
ERR_HTTP_4XX = "http_4xx"
ERR_HTTP_5XX = "http_5xx"
ERR_PARSE = "parse"
ERR_QUOTA = "quota_exhausted"
ERR_UNSUPPORTED_QUERY = "unsupported_query"
ERR_TRANSPORT_TIMEOUT = "transport_timeout"
ERR_CANCELLED = "cancelled"
ERR_AUTH = "auth"
ERR_BLOCKED = "blocked"
ERR_CONFIG = "configuration"
ERR_UNKNOWN = "unknown"

# Why coverage stopped short of the interval.
TRUNC_PROVIDER_LIMIT = "provider_limit"
TRUNC_TIME_BUDGET = "time_budget"
TRUNC_QUOTA = "quota"
TRUNC_RETENTION = "retention_limit"
TRUNC_NO_DATE_FILTER = "provider_no_date_filter"
TRUNC_PARSE_PARTIAL = "parse_partial"

#: Status codes that are a provider or network hiccup, not a bad query.
#: arXiv answers 406 in bursts to a query that returns 200 a minute later
#: (work package 24); 429 and 503 are the usual transient codes.
TRANSIENT_HTTP_STATUSES = frozenset({406, 408, 425, 429, 500, 502, 503, 504})


@dataclass
class CollectionCounts:
    """Adapter counts describe what was received and rejected; ingest counts
    describe what was written. An adapter never reports database inserts."""

    received: int = 0
    invalid: int = 0
    filtered: int = 0
    duplicate: int = 0
    inserted: int = 0
    updated: int = 0
    associated: int = 0
    quarantined: int = 0
    #: Candidates the rejected-candidate ledger answered without a new
    #: evaluation (work package 19). Neither a duplicate nor a filter.
    already_rejected: int = 0
    #: Rows skipped because a shared key is out of quota (work package 20).
    quota_skipped: int = 0
    #: Rows not attempted because their own cooldown had not passed.
    deferred: int = 0

    def add(self, **kw: int) -> "CollectionCounts":
        for k, v in kw.items():
            setattr(self, k, getattr(self, k) + int(v or 0))
        return self

    def as_dict(self) -> Dict[str, int]:
        return asdict(self)


@dataclass
class CollectionResult:
    """The outcome of one collection run over one fixed interval.

    ``items`` are the valid normalized records collected so far, whether the
    run finished or not. ``coverage_complete`` is only true when every page or
    entry inside ``interval_start``..``interval_end`` was processed.
    """

    status: str = STATUS_SUCCESS
    items: List[Dict[str, Any]] = field(default_factory=list)
    interval_start: Optional[datetime] = None
    interval_end: Optional[datetime] = None
    coverage_complete: bool = True
    #: Opaque provider cursor or local batch position to resume from.
    continuation: Optional[Dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
    counts: CollectionCounts = field(default_factory=CollectionCounts)
    truncated_reason: Optional[str] = None
    provider: Optional[str] = None
    #: What was collected: a feed id, a keyword, a category. Diagnostics only.
    scope: Optional[str] = None
    #: Some entries were lost to a recoverable parse error (work package 29).
    parse_partial: bool = False
    #: Cache validators the caller may commit once the items are persisted
    #: (work package 16). The adapter never writes them itself.
    proposed_validators: Dict[str, Any] = field(default_factory=dict)
    #: Anything the run record should keep: query translation, provider
    #: notes, per-route outcomes. Never credentials.
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # -- constructors -------------------------------------------------------

    @classmethod
    def ok(cls, items: Optional[List[Dict[str, Any]]] = None, **kw: Any) -> "CollectionResult":
        return cls(status=STATUS_SUCCESS, items=list(items or []), **kw)

    @classmethod
    def partial(cls, items: Optional[List[Dict[str, Any]]], *, truncated_reason: str,
                continuation: Optional[Dict[str, Any]] = None, **kw: Any) -> "CollectionResult":
        return cls(status=STATUS_PARTIAL, items=list(items or []), coverage_complete=False,
                   truncated_reason=truncated_reason, continuation=continuation,
                   retryable=True, **kw)

    @classmethod
    def failure(cls, error_code: str, message: str, *, retryable: bool,
                items: Optional[List[Dict[str, Any]]] = None,
                truncated_reason: Optional[str] = None,
                continuation: Optional[Dict[str, Any]] = None, **kw: Any) -> "CollectionResult":
        if not message:
            # An empty reason is the gap work package 28 names; refuse it.
            message = error_code
        return cls(status=STATUS_FAILED, items=list(items or []), coverage_complete=False,
                   error_code=error_code, error_message=message, retryable=retryable,
                   truncated_reason=truncated_reason, continuation=continuation, **kw)

    @classmethod
    def from_exception(cls, exc: BaseException, *, host: Optional[str] = None,
                       items: Optional[List[Dict[str, Any]]] = None,
                       continuation: Optional[Dict[str, Any]] = None, **kw: Any) -> "CollectionResult":
        code, message, retryable = classify_exception(exc, host=host)
        truncated = TRUNC_QUOTA if code == ERR_QUOTA else None
        return cls.failure(code, message, retryable=retryable, items=items,
                           continuation=continuation, truncated_reason=truncated, **kw)

    @classmethod
    def quota_exhausted(cls, provider: str, until: Optional[datetime] = None,
                        message: str = "", **kw: Any) -> "CollectionResult":
        msg = message or f"{provider} quota exhausted"
        if until is not None:
            msg = f"{msg} until {until.isoformat()}"
        res = cls.failure(ERR_QUOTA, msg, retryable=True, truncated_reason=TRUNC_QUOTA,
                          provider=provider, **kw)
        if until is not None:
            res.diagnostics["quota_exhausted_until"] = until.isoformat()
        return res

    # -- reading ------------------------------------------------------------

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_SUCCESS

    @property
    def failed(self) -> bool:
        return self.status == STATUS_FAILED

    @property
    def may_advance_checkpoint(self) -> bool:
        """Only a genuinely complete interval moves coverage forward. A 429,
        a timeout, a parse error or an exhausted budget never does, whatever
        it managed to return on the way."""
        return self.status == STATUS_SUCCESS and self.coverage_complete and not self.parse_partial

    def mark_started(self) -> "CollectionResult":
        self.started_at = self.started_at or datetime.now(timezone.utc)
        return self

    def mark_finished(self) -> "CollectionResult":
        self.finished_at = datetime.now(timezone.utc)
        return self

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return None

    def to_record(self) -> Dict[str, Any]:
        """The run-record view: everything except the items themselves."""
        return {
            "provider": self.provider,
            "scope": self.scope,
            "status": self.status,
            "interval_start": _iso(self.interval_start),
            "interval_end": _iso(self.interval_end),
            "coverage_complete": bool(self.coverage_complete),
            "continuation": self.continuation,
            "error_code": self.error_code,
            "error_message": (self.error_message or "")[:1000] or None,
            "retryable": bool(self.retryable),
            "truncated_reason": self.truncated_reason,
            "parse_partial": bool(self.parse_partial),
            "counts": self.counts.as_dict(),
            "item_count": len(self.items),
            "diagnostics": dict(self.diagnostics),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "duration_ms": self.duration_ms,
        }

    def merge(self, other: "CollectionResult") -> "CollectionResult":
        """Fold a second route's outcome into this one (work package 10: a
        failed route must not masquerade as a complete combined run)."""
        self.items.extend(other.items)
        for k, v in other.counts.as_dict().items():
            self.counts.add(**{k: v})
        if other.status == STATUS_FAILED and self.status == STATUS_SUCCESS:
            self.status = STATUS_PARTIAL if self.items or other.items else STATUS_FAILED
        elif other.status == STATUS_PARTIAL and self.status == STATUS_SUCCESS:
            self.status = STATUS_PARTIAL
        if not other.coverage_complete:
            self.coverage_complete = False
        self.parse_partial = self.parse_partial or other.parse_partial
        if other.error_code and not self.error_code:
            self.error_code, self.error_message = other.error_code, other.error_message
        self.retryable = self.retryable or other.retryable
        if other.truncated_reason and not self.truncated_reason:
            self.truncated_reason = other.truncated_reason
        if other.continuation:
            self.continuation = {**(self.continuation or {}), **other.continuation}
        routes = self.diagnostics.setdefault("routes", [])
        routes.append({"scope": other.scope, "status": other.status,
                       "error_code": other.error_code, "items": len(other.items)})
        return self


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


# ---------------------------------------------------------------------------
# Error classification (work package 28)
# ---------------------------------------------------------------------------

_QUOTA_PHRASES = (
    "rate limit", "ratelimit", "too many requests", "quota", "usage limit",
    "exceeded your assigned api credits", "credits", "limit reached",
)


def host_of(url: Optional[str]) -> Optional[str]:
    try:
        return (urlsplit(url or "").hostname or None)
    except ValueError:
        return None


def _status_of(exc: BaseException) -> Optional[int]:
    """The HTTP status an exception carries, for httpx, aiohttp, requests and
    the plain ``status``/``status_code`` attributes other clients use."""
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if isinstance(value, int) and 100 <= value <= 599:
                return value
    return None


def _host_of_exception(exc: BaseException) -> Optional[str]:
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None) if request is not None else None
    if url is None:
        url = getattr(exc, "url", None)
    if url is not None:
        return host_of(str(url))
    return None


def classify_exception(exc: BaseException, *, host: Optional[str] = None
                       ) -> "tuple[str, str, bool]":
    """``(error_code, message, retryable)`` for any exception.

    The message always names the exception class and, for HTTP errors, the
    status code and host. httpx timeouts stringify to an empty string, which
    is how 210 feed failures were logged as "failed:" with nothing after it.
    """
    name = type(exc).__name__
    text = str(exc) or ""
    host = host or _host_of_exception(exc)
    where = f" host={host}" if host else ""
    status = _status_of(exc)
    lname = name.lower()
    ltext = text.lower()

    def msg(code: str) -> str:
        parts = [f"{name}"]
        if status:
            parts.append(f"HTTP {status}")
        if text:
            parts.append(text[:300])
        return f"{code}: " + " ".join(parts) + where

    if isinstance(exc, asyncio.CancelledError):
        return ERR_CANCELLED, msg(ERR_CANCELLED), True
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, socket.timeout)) or "timeout" in lname:
        return ERR_TIMEOUT, msg(ERR_TIMEOUT), True
    if isinstance(exc, socket.gaierror) or "nameresolution" in lname or "gaierror" in lname \
            or "name or service not known" in ltext or "nodename nor servname" in ltext \
            or "temporary failure in name resolution" in ltext:
        return ERR_DNS, msg(ERR_DNS), True
    if status is not None:
        if status == 429 or (status == 403 and any(p in ltext for p in _QUOTA_PHRASES)):
            return ERR_QUOTA, msg(ERR_QUOTA), True
        if status in (401, 403):
            return ERR_AUTH, msg(ERR_AUTH), False
        if status in TRANSIENT_HTTP_STATUSES:
            return ERR_HTTP_5XX if status >= 500 else ERR_HTTP_4XX, msg("transient"), True
        if 400 <= status < 500:
            return ERR_HTTP_4XX, msg(ERR_HTTP_4XX), False
        if status >= 500:
            return ERR_HTTP_5XX, msg(ERR_HTTP_5XX), True
    if any(p in ltext for p in _QUOTA_PHRASES):
        return ERR_QUOTA, msg(ERR_QUOTA), True
    if "connect" in lname or "connectionreset" in lname or "remotedisconnected" in lname \
            or isinstance(exc, (ConnectionError, OSError)) and not isinstance(exc, FileNotFoundError):
        return ERR_CONNECTION, msg(ERR_CONNECTION), True
    if "parse" in lname or "xml" in lname or "json" in lname or "decode" in lname \
            or "not well-formed" in ltext or "could not be parsed" in ltext:
        return ERR_PARSE, msg(ERR_PARSE), False
    if "unsupported_query" in ltext:
        return ERR_UNSUPPORTED_QUERY, msg(ERR_UNSUPPORTED_QUERY), False
    return ERR_UNKNOWN, msg(ERR_UNKNOWN), False


def describe_exception(exc: BaseException, *, host: Optional[str] = None) -> str:
    """A never-empty one-line description for ``last_error`` style fields."""
    return classify_exception(exc, host=host)[1]


def is_transient_status(status: Optional[int]) -> bool:
    return status in TRANSIENT_HTTP_STATUSES
