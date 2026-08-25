"""LLM usage ledger — records every litellm call into ``llm_usage_log``.

Port of the saas ``llm_usage_log`` pattern to the monolith. The monolith has
no per-call cost tracking; the July 2026 AWS bill surprise (~$8.6k estimated,
untracked Bedrock-primary tenants) is why this exists.

Design:
  * One global litellm success/failure callback pair, registered once at app
    startup via :func:`install`. This is the single choke point — it catches
    Router calls, direct ``litellm.completion``/``acompletion`` calls, and the
    ~17 modules that pass bare ``gpt-*`` aliases without going through
    ``AIModelFactory``.
  * Callbacks only normalize + enqueue (thread-safe, non-blocking). A daemon
    thread batches inserts every few seconds over its own psycopg2
    connection, so no event loop is ever blocked and a DB hiccup can never
    break an LLM call. Queue is bounded; on overflow rows are dropped and
    counted rather than backing up the app.
  * ``use_case`` is caller attribution, captured **at call time** rather than
    at callback time. litellm runs its callbacks on its own worker threads
    (``ThreadPoolExecutor-0_0``, ``asyncio_0``), where none of the app's frames
    are on the stack, so reading the stack from inside a callback returns
    "unknown" for every asynchronous call — which is most of them. Instead
    :func:`install` wraps ``litellm.completion``/``acompletion`` so the caller
    is read from the live stack before the request leaves the app, and tucked
    into litellm's ``metadata`` where the callback can find it again. The old
    stack walk stays as the fallback for any path the wrapper misses.

Query it exactly like saas:
  SELECT use_case, model, count(*), sum(cost_usd) FROM llm_usage_log
  WHERE created_at > now() - interval '7 days' GROUP BY 1,2 ORDER BY 4 DESC;
"""

from __future__ import annotations

import functools
import logging
import os
import queue
import threading
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

#: Key under which the calling site is tucked into litellm ``metadata``.
_USE_CASE_KEY = "aunoo_use_case"

_QUEUE: "queue.Queue[tuple]" = queue.Queue(maxsize=10_000)
_DROPPED = 0
_INSTALLED = False
_FLUSH_INTERVAL_SEC = 5.0
_BATCH_MAX = 500

# Fallback price table (USD per 1M tokens, input/output) for when litellm
# can't cost a call. Substring-matched against the resolved model id.
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "nova-pro": (0.80, 3.20),
    "nova-lite": (0.06, 0.24),
    "nova-micro": (0.035, 0.14),
    "mistral-large": (0.80, 4.00),
    "llama3-3-70b": (0.06, 0.24),
    "gpt-5.4-mini": (0.15, 0.60),
    "gpt-5.4": (1.25, 10.00),
}

_SKIP_FRAME_TOKENS = (
    "llm_usage_logger", "ai_models.py", "litellm", "asyncio", "concurrent",
    "threading.py", "logging_utils", "site-packages",
)


def _guess_use_case() -> str:
    """First app-owned frame below us on the stack, as ``module:function``."""
    try:
        for frame in reversed(traceback.extract_stack(limit=40)):
            fn = frame.filename or ""
            if "/app/" not in fn:
                continue
            if any(tok in fn for tok in _SKIP_FRAME_TOKENS):
                continue
            mod = fn.rsplit("/app/", 1)[-1].removesuffix(".py").replace("/", ".")
            return f"{mod}:{frame.name}"[:200]
    except Exception:
        pass
    return "unknown"


def _use_case_from(kwargs: dict) -> str:
    """The caller recorded at call time, else the (usually futile) stack walk.

    litellm copies whatever was passed as ``metadata`` into
    ``kwargs["litellm_params"]["metadata"]`` before invoking callbacks, so the
    tag survives the hop onto litellm's logging thread.
    """
    try:
        lp = kwargs.get("litellm_params") or {}
        for source in (lp.get("metadata"), kwargs.get("metadata")):
            if isinstance(source, dict):
                tagged = source.get(_USE_CASE_KEY)
                if tagged:
                    return str(tagged)[:200]
    except Exception:  # noqa: BLE001
        pass
    return _guess_use_case()


# --------------------------------------------------------------------------
# Call-site tagging
# --------------------------------------------------------------------------

def _tagged_kwargs(kwargs: dict) -> dict:
    """Add the calling site to litellm's metadata without disturbing what's there."""
    metadata = kwargs.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if _USE_CASE_KEY not in metadata:
        metadata = {**metadata, _USE_CASE_KEY: _guess_use_case()}
        kwargs = {**kwargs, "metadata": metadata}
    return kwargs


def _wrap_sync(fn):
    @functools.wraps(fn)
    def _tagging_completion(*args, **kwargs):
        try:
            kwargs = _tagged_kwargs(kwargs)
        except Exception:  # noqa: BLE001 — never break an LLM call over logging
            logger.debug("use-case tagging failed", exc_info=True)
        return fn(*args, **kwargs)
    _tagging_completion._aunoo_tagged = True
    return _tagging_completion


def _wrap_async(fn):
    @functools.wraps(fn)
    async def _tagging_acompletion(*args, **kwargs):
        try:
            kwargs = _tagged_kwargs(kwargs)
        except Exception:  # noqa: BLE001
            logger.debug("use-case tagging failed", exc_info=True)
        return await fn(*args, **kwargs)
    _tagging_acompletion._aunoo_tagged = True
    return _tagging_acompletion


def _install_call_site_tagging() -> None:
    """Wrap litellm's two entry points so every call carries its caller.

    Twelve modules do ``from litellm import completion`` at import time, and
    those bindings are already made by the time this runs, so setting the
    attribute on the litellm module alone would miss them. Any already-imported
    app module still holding the original function is rebound to the wrapper.
    """
    import sys

    import litellm

    for name, wrap in (("completion", _wrap_sync), ("acompletion", _wrap_async)):
        original = getattr(litellm, name, None)
        if original is None or getattr(original, "_aunoo_tagged", False):
            continue
        wrapped = wrap(original)
        setattr(litellm, name, wrapped)
        rebound = 0
        for module in list(sys.modules.values()):
            mod_name = getattr(module, "__name__", "") or ""
            if not mod_name.startswith("app."):
                continue
            try:
                if getattr(module, name, None) is original:
                    setattr(module, name, wrapped)
                    rebound += 1
            except Exception:  # noqa: BLE001 — a module that dislikes getattr is not our problem
                continue
        logger.info("llm_usage_log: tagging litellm.%s (%d early import(s) rebound)", name, rebound)

    # Router needs its own wrapper. It does not call litellm.acompletion from the
    # caller's frame — it hands the work to its scheduler, so by the time the
    # module-level wrapper runs the app is no longer on the stack and the tag
    # comes out "unknown". Wrapping the Router methods captures the caller at the
    # boundary where it is still there. This is the path AIModelFactory uses,
    # which on wileytest is the highest-volume LLM path there is.
    try:
        from litellm.router import Router

        for name, wrap in (("completion", _wrap_sync), ("acompletion", _wrap_async)):
            original = getattr(Router, name, None)
            if original is None or getattr(original, "_aunoo_tagged", False):
                continue
            setattr(Router, name, wrap(original))
            logger.info("llm_usage_log: tagging Router.%s", name)
    except Exception:  # noqa: BLE001 — Router tagging is a bonus, never a blocker
        logger.debug("could not tag litellm Router", exc_info=True)


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    m = (model or "").lower()
    for key, (inp, out) in _PRICE_PER_M.items():
        if key in m:
            return (prompt_tokens * inp + completion_tokens * out) / 1_000_000
    return 0.0


def _extract(kwargs: dict, response, start_time, end_time, status: str, err: str | None):
    alias = str(kwargs.get("model") or "")[:300]
    resolved = alias
    usage = getattr(response, "usage", None) if response is not None else None
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens))
    if response is not None and getattr(response, "model", None):
        resolved = str(response.model)[:300]
    else:
        lp = kwargs.get("litellm_params") or {}
        resolved = str(lp.get("model") or alias)[:300]

    cost = 0.0
    try:
        cost = float(kwargs.get("response_cost") or 0.0)
    except Exception:
        cost = 0.0
    if not cost and status == "success":
        try:
            import litellm as _ll
            cost = float(_ll.completion_cost(completion_response=response) or 0.0)
        except Exception:
            cost = _estimate_cost(resolved, prompt_tokens, completion_tokens)
    provider = resolved.split("/", 1)[0] if "/" in resolved else None

    latency_ms = None
    try:
        latency_ms = int((end_time - start_time).total_seconds() * 1000)
    except Exception:
        pass

    return (
        _use_case_from(kwargs), alias, resolved, provider,
        prompt_tokens, completion_tokens, total_tokens,
        round(cost, 8), latency_ms, status, (err or "")[:2000] or None,
        datetime.now(timezone.utc),
    )


def _enqueue(row: tuple) -> None:
    global _DROPPED
    try:
        _QUEUE.put_nowait(row)
    except queue.Full:
        _DROPPED += 1
        if _DROPPED % 1000 == 1:
            logger.warning("llm_usage_log queue full — dropped %d rows so far", _DROPPED)


def _on_success(kwargs, completion_response, start_time, end_time):  # litellm signature
    try:
        _enqueue(_extract(kwargs, completion_response, start_time, end_time, "success", None))
    except Exception:  # noqa: BLE001 — never break an LLM call over logging
        logger.debug("llm usage logging failed", exc_info=True)


def _on_failure(kwargs, completion_response, start_time, end_time):
    try:
        err = str(kwargs.get("exception") or "")
        _enqueue(_extract(kwargs, None, start_time, end_time, "error", err))
    except Exception:  # noqa: BLE001
        logger.debug("llm usage logging failed", exc_info=True)


_INSERT_SQL = """
    INSERT INTO llm_usage_log
        (use_case, model, resolved_model, provider, prompt_tokens,
         completion_tokens, total_tokens, cost_usd, latency_ms, status,
         error_message, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _connect():
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5,
    )


def _flusher() -> None:
    conn = None
    while True:
        rows: list[tuple] = []
        try:
            rows.append(_QUEUE.get(timeout=_FLUSH_INTERVAL_SEC))
            while len(rows) < _BATCH_MAX:
                rows.append(_QUEUE.get_nowait())
        except queue.Empty:
            pass
        if not rows:
            continue
        try:
            if conn is None or conn.closed:
                conn = _connect()
            with conn.cursor() as cur:
                cur.executemany(_INSERT_SQL, rows)
            conn.commit()
        except Exception:  # noqa: BLE001 — drop the batch, keep the thread alive
            logger.warning("llm_usage_log flush failed (%d rows dropped)", len(rows), exc_info=True)
            try:
                if conn is not None:
                    conn.rollback()
                    conn.close()
            except Exception:  # noqa: BLE001
                pass
            conn = None


def install() -> None:
    """Register callbacks + start the flusher. Idempotent; call at startup."""
    global _INSTALLED
    if _INSTALLED:
        return
    if os.getenv("LLM_USAGE_LOG_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info("llm_usage_log disabled via env")
        return
    import litellm

    if _on_success not in litellm.success_callback:
        litellm.success_callback.append(_on_success)
    if _on_failure not in litellm.failure_callback:
        litellm.failure_callback.append(_on_failure)
    _install_call_site_tagging()
    threading.Thread(target=_flusher, name="llm-usage-flusher", daemon=True).start()
    _INSTALLED = True
    logger.info("llm_usage_log installed (queue=%d, flush=%.0fs)", _QUEUE.maxsize, _FLUSH_INTERVAL_SEC)
