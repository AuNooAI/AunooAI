"""Cross-encoder reranker for pgvector retrieval sites.

Bi-encoder (DeBERTa 768d) cosine is what populates the candidate set from
pgvector. A cross-encoder scores (query, candidate_text) jointly and so
recovers precision the bi-encoder loses on asymmetric or low-k top-k
retrieval — exactly the shape most of our user-facing and LLM-facing
retrieval takes.

Usage:

    from app.retrieval.reranker import rerank, overfetch_limit

    # Overfetch cosine-ranked candidates
    rows = await db.execute(text("... ORDER BY distance ASC LIMIT :lim"),
                            {"qv": str(qv), "lim": overfetch_limit(top_k)})
    candidates = [dict(...) for r in rows.all()]

    # Rerank to top_k
    ranked = await rerank(query=user_query, candidates=candidates,
                          text_key="title", top_k=top_k)

Design notes mirror `app/detection/paraphrase.py`:
  * Model is loaded lazily on first call; load failures downgrade to a
    silent no-op (returns the input slice unchanged).
  * Inference runs in a thread via `asyncio.to_thread` — `CrossEncoder.predict`
    is synchronous and CPU-bound.
  * Env-tunable via `RERANK_*` vars so ops can flip the flag or swap
    models without a code change.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────

RERANK_ENABLED: bool = os.getenv("RERANK_ENABLED", "false").lower() in {"1", "true", "yes"}

# Default: English retrieval-tuned MS-MARCO MiniLM. Small (~90MB), fast on
# CPU (~10-30ms per (query, doc) pair), produces 0-1 scores.
# For multilingual queries set
#   RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
# — note that model outputs unbounded logits.
RERANK_MODEL_NAME: str = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# How many cosine-ranked candidates to fetch per top_k requested.
# k=10, factor=5 → pull 50 from pgvector, rerank down to 10.
RERANK_OVERFETCH_FACTOR: int = int(os.getenv("RERANK_OVERFETCH_FACTOR", "5"))

# Hard ceiling on the overfetched candidate pool — guards against a caller
# asking for top_k=100 and triggering a 500-candidate CE pass.
RERANK_MAX_CANDIDATES: int = int(os.getenv("RERANK_MAX_CANDIDATES", "200"))

RERANK_BATCH_SIZE: int = int(os.getenv("RERANK_BATCH_SIZE", "32"))

# Per-candidate text length cap. Matches what we feed to embeddings.
RERANK_MAX_TEXT_LEN: int = int(os.getenv("RERANK_MAX_TEXT_LEN", "1000"))


def overfetch_limit(top_k: int) -> int:
    """How many rows to ask pgvector for given a desired top_k.

    Callers should use this to size their ``LIMIT`` so the candidate pool
    matches the reranker's budget. Returns ``top_k`` unchanged when
    reranking is disabled so no-op mode doesn't pay the extra fetch.
    """
    if not RERANK_ENABLED:
        return top_k
    return min(max(top_k * RERANK_OVERFETCH_FACTOR, top_k), RERANK_MAX_CANDIDATES)


# ── Model singleton ────────────────────────────────────────────────────────

_model: Any = None
_load_failed: bool = False


def _get_model():
    """Lazy-load the cross-encoder. Returns None if import or load fails
    so callers degrade to plain cosine ordering."""
    global _model, _load_failed
    if _model is not None:
        return _model
    if _load_failed:
        return None
    try:
        from sentence_transformers import CrossEncoder
        logger.info("Loading retrieval reranker: %s", RERANK_MODEL_NAME)
        _model = CrossEncoder(RERANK_MODEL_NAME, max_length=512)
        return _model
    except Exception:
        logger.exception(
            "Failed to load retrieval reranker — retrieval will continue "
            "in cosine-only mode. Install sentence-transformers or set "
            "RERANK_MODEL to a known-good model id, or unset RERANK_ENABLED."
        )
        _load_failed = True
        return None


def _default_text(candidate: dict, text_key: str) -> str:
    """Build the text the cross-encoder scores against the query.

    Prefers the value at ``text_key`` but falls back to composing
    title/summary/content when available, since callers often have partial
    projections.
    """
    primary = candidate.get(text_key)
    if isinstance(primary, str) and primary.strip():
        return primary[:RERANK_MAX_TEXT_LEN]

    parts: list[str] = []
    for k in ("title", "summary", "content"):
        v = candidate.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return (". ".join(parts))[:RERANK_MAX_TEXT_LEN]


def _predict_scores(model: Any, pairs: list[tuple[str, str]]) -> list[float]:
    """Synchronous CE inference. Runs in a thread from ``rerank``."""
    scores = model.predict(
        pairs,
        batch_size=RERANK_BATCH_SIZE,
        show_progress_bar=False,
    )
    return [float(s) for s in scores]


# ── Public API ─────────────────────────────────────────────────────────────


async def rerank(
    query: str,
    candidates: list[dict],
    *,
    text_key: str = "title",
    top_k: int,
    text_fn: Optional[Callable[[dict], str]] = None,
) -> list[dict]:
    """Rerank cosine-ordered ``candidates`` against ``query``.

    Returns at most ``top_k`` candidates, each with a ``rerank_score`` key
    added. When reranking is disabled, the model fails to load, or there
    are fewer candidates than ``top_k``, returns the input slice unchanged
    (no ``rerank_score`` added) — callers can treat that as a graceful
    degradation to pure cosine order.

    Parameters:
        query: the user's natural-language query (or seed text).
        candidates: list of dicts already ordered by cosine.
        text_key: dict key holding the candidate's primary text. If
            absent, falls back to title+summary+content composition.
        top_k: how many results to return after reranking.
        text_fn: optional custom extractor. Overrides ``text_key``.
    """
    if top_k <= 0 or not candidates:
        return candidates[:top_k]

    if not RERANK_ENABLED:
        return candidates[:top_k]

    if not query or not query.strip():
        return candidates[:top_k]

    model = _get_model()
    if model is None:
        return candidates[:top_k]

    extractor = text_fn if text_fn is not None else (lambda c: _default_text(c, text_key))

    # Cap the pool actually scored; caller may have fetched more than
    # RERANK_MAX_CANDIDATES inadvertently.
    pool = candidates[:RERANK_MAX_CANDIDATES]
    query_trimmed = query.strip()[:RERANK_MAX_TEXT_LEN]
    pairs = [(query_trimmed, extractor(c)) for c in pool]

    try:
        scores = await asyncio.to_thread(_predict_scores, model, pairs)
    except Exception:
        logger.exception(
            "Reranker inference failed on %d candidates — returning cosine order",
            len(pairs),
        )
        return candidates[:top_k]

    scored: list[tuple[float, dict]] = []
    for c, s in zip(pool, scores):
        out = dict(c)
        out["rerank_score"] = s
        scored.append((s, out))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def is_enabled() -> bool:
    """Callers can cheaply check whether to overfetch before querying."""
    return RERANK_ENABLED


def score_pair(query: str, document: str) -> Optional[float]:
    """Score a single (query, document) pair with the cross-encoder.

    Returns the model's raw score. For the default
    ``cross-encoder/ms-marco-MiniLM-L-6-v2`` this is an unbounded logit
    (higher = more relevant, typical range ~[-12, +5]). Consumers that need
    a bounded probability should apply their own sigmoid; thresholds are
    model-specific and should be calibrated with a backtest (see
    ``scripts/evaluate_ce_vs_llm_fallback.py``) before use.

    Reuses the same lazy singleton as ``rerank`` so there is no duplicate
    model load. Returns ``None`` if the model is not available or inference
    fails so the caller can fall back to whatever it was doing before.
    """
    if not query or not document:
        return None
    model = _get_model()
    if model is None:
        return None
    try:
        scores = _predict_scores(
            model,
            [(query[:RERANK_MAX_TEXT_LEN], document[:RERANK_MAX_TEXT_LEN])],
        )
    except Exception:
        logger.exception("Cross-encoder score_pair inference failed")
        return None
    return scores[0] if scores else None
