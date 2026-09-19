"""Thin client for TypeSafe's System One API (the Jev decision model).

Jev is not a text generator. You send a ``state`` (string or JSON) and a map of
typed questions (choice / score / noul) and get one typed answer per question:
a probability distribution over the options you defined, never prose. See
https://docs.typesafe.ai/api for the request and answer shapes.

This module never raises. A missing key, a timeout, a 429 or a malformed body
all return ``None`` so a caller can treat Jev as optional. Every call is also
written to ``llm_usage_log`` (use_case, tokens, cost) through the same queue
the litellm callbacks use, so Jev spend shows up in the same ledger.

Env:
    TYPESAFE_API_KEY   required to enable anything
    TYPESAFE_MODEL     default ``jev-1.13.0`` (pin a version, not ``jev-latest``,
                       so tuned thresholds do not move under you)
    TYPESAFE_TIMEOUT_S default 6
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"
# Published price, input tokens only; output tokens are free. Update if the
# price page changes: https://docs.typesafe.ai/models
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000


def api_key() -> Optional[str]:
    key = (os.getenv("TYPESAFE_API_KEY") or "").strip()
    return key or None


def is_configured() -> bool:
    return api_key() is not None


def model_name() -> str:
    return (os.getenv("TYPESAFE_MODEL") or DEFAULT_MODEL).strip()


def system_one(
    state: Any,
    questions: Dict[str, Dict[str, Any]],
    *,
    use_case: str = "typesafe_client:system_one",
    timeout_s: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """POST one state + questions to Jev. Returns the parsed response body
    (``model``, ``answers``, ``usage``) or ``None`` on any failure."""
    key = api_key()
    if not key:
        return None
    timeout = timeout_s if timeout_s is not None else float(os.getenv("TYPESAFE_TIMEOUT_S", "6"))
    model = model_name()
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    status, err, out = "error", None, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        if not isinstance(out, dict) or "answers" not in out:
            err = f"unexpected body: {str(out)[:200]}"
            out = None
        else:
            status = "success"
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:300].decode("utf-8", "replace")
        except Exception:
            detail = ""
        err = f"HTTP {e.code} {detail}"
    except Exception as e:  # noqa: BLE001 — timeouts, DNS, JSON
        err = repr(e)
    latency_ms = int((time.monotonic() - started) * 1000)
    if err:
        logger.warning("TypeSafe call failed (%s, %d ms): %s", use_case, latency_ms, err)
    _log_usage(use_case, out, model, latency_ms, status, err)
    return out


def _log_usage(use_case: str, out: Optional[dict], model: str, latency_ms: int,
               status: str, err: Optional[str]) -> None:
    """Write one ledger row through the llm_usage_logger queue. Best effort."""
    try:
        from app.services.llm_usage_logger import _enqueue
        usage = (out or {}).get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        resolved = (out or {}).get("model") or model
        _enqueue((
            use_case, model, resolved, "typesafe",
            prompt_tokens, completion_tokens, prompt_tokens + completion_tokens,
            round(prompt_tokens * USD_PER_INPUT_TOKEN, 8), latency_ms, status,
            (err or "")[:2000] or None, datetime.now(timezone.utc),
        ))
    except Exception:  # noqa: BLE001 — never let logging break a call
        logger.debug("TypeSafe usage logging failed", exc_info=True)
