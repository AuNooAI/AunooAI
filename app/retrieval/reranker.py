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

# Default: BAAI/bge-reranker-v2-m3. Multilingual, 8K context (matters for
# paragraph-level topical relevance rather than just titles+ledes), ~568M
# params, Apache 2.0. Top of MTEB reranking benchmarks and outputs bounded
# [0, 1] probabilities after sigmoid — so ``score_pair`` thresholds are
# interpretable without per-model calibration.
# Legacy option: ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (~90MB, English,
# 512 ctx, unbounded logits) if you need a tiny CPU footprint.
RERANK_MODEL_NAME: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# How many cosine-ranked candidates to fetch per top_k requested.
# k=10, factor=5 → pull 50 from pgvector, rerank down to 10.
RERANK_OVERFETCH_FACTOR: int = int(os.getenv("RERANK_OVERFETCH_FACTOR", "5"))

# Hard ceiling on the overfetched candidate pool — guards against a caller
# asking for top_k=100 and triggering a 500-candidate CE pass.
RERANK_MAX_CANDIDATES: int = int(os.getenv("RERANK_MAX_CANDIDATES", "200"))

RERANK_BATCH_SIZE: int = int(os.getenv("RERANK_BATCH_SIZE", "32"))

# Per-candidate text length cap. BGE-reranker-v2-m3 has an 8K-token window;
# 4000 chars ≈ 1000 tokens, enough for body paragraphs where topical signal
# actually lives for news articles (not just headline+lede).
RERANK_MAX_TEXT_LEN: int = int(os.getenv("RERANK_MAX_TEXT_LEN", "4000"))


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


async def assign_exclusive(
    scenarios: list[dict],
    articles: list[dict],
    *,
    scenario_text_fn: Callable[[dict], str] | None = None,
    article_text_fn: Callable[[dict], str] | None = None,
    margin: float = 0.1,
) -> list[dict]:
    """Score every article against every scenario, assign each article to the
    scenario it best matches if the margin to the runner-up is large enough.

    Used by Forecast Assessment to prevent overlapping scenarios (e.g., an H1
    decline scenario and an H3 replacement scenario about the same system)
    from both claiming credit for the same article.

    Returns a list parallel to ``articles`` with dicts containing:
        ``scenario_idx``       — winning scenario index (or None if ambiguous)
        ``score``              — sigmoid'd reranker score against the winner
        ``margin``             — score gap to runner-up scenario
        ``best_alt_scenario_idx`` — runner-up scenario index
        ``all_scores``         — full scenarios×score row (sigmoid'd) for inspection

    When reranking is disabled or the model fails to load, returns rows with
    ``scenario_idx=None`` so the caller can degrade gracefully (e.g. fall back
    to topic-only attribution).
    """
    if not scenarios or not articles:
        return []

    if not RERANK_ENABLED:
        return [
            {"scenario_idx": None, "score": None, "margin": None,
             "best_alt_scenario_idx": None, "all_scores": []}
            for _ in articles
        ]

    model = _get_model()
    if model is None:
        return [
            {"scenario_idx": None, "score": None, "margin": None,
             "best_alt_scenario_idx": None, "all_scores": []}
            for _ in articles
        ]

    import math

    s_extractor = scenario_text_fn if scenario_text_fn is not None else (
        lambda s: f"{s.get('title','')}. {s.get('description','')}"[:RERANK_MAX_TEXT_LEN]
    )
    a_extractor = article_text_fn if article_text_fn is not None else (
        lambda a: _default_text(a, "title")
    )

    scenario_texts = [s_extractor(s) for s in scenarios]
    article_texts = [a_extractor(a) for a in articles]

    pairs: list[tuple[str, str]] = []
    for a_text in article_texts:
        for s_text in scenario_texts:
            pairs.append((a_text, s_text))

    try:
        raw_scores = await asyncio.to_thread(_predict_scores, model, pairs)
    except Exception:
        logger.exception(
            "Reranker assign_exclusive failed on %d pairs — returning unassigned",
            len(pairs),
        )
        return [
            {"scenario_idx": None, "score": None, "margin": None,
             "best_alt_scenario_idx": None, "all_scores": []}
            for _ in articles
        ]

    def _sigmoid(x: float) -> float:
        if 0.0 <= x <= 1.0:
            return float(x)
        return 1.0 / (1.0 + math.exp(-x))

    n_scen = len(scenarios)
    out: list[dict] = []
    for i in range(len(articles)):
        row = [_sigmoid(raw_scores[i * n_scen + j]) for j in range(n_scen)]
        # argmax + runner-up
        ranked = sorted(range(n_scen), key=lambda j: row[j], reverse=True)
        top = ranked[0]
        second = ranked[1] if n_scen > 1 else None
        top_score = row[top]
        second_score = row[second] if second is not None else 0.0
        gap = top_score - second_score
        assigned = top if gap >= margin else None
        out.append({
            "scenario_idx": assigned,
            "score": top_score,
            "margin": gap,
            "best_alt_scenario_idx": second,
            "all_scores": row,
        })
    return out


def score_pair(query: str, document: str) -> Optional[float]:
    """Score a single (query, document) pair with the cross-encoder.

    Returns a probability in ``[0, 1]``. The default model
    (``BAAI/bge-reranker-v2-m3``) emits a logit that sigmoid-maps cleanly
    into that range; swapping to a model that returns unbounded or already-
    bounded scores may shift thresholds. Calibrate with
    ``scripts/evaluate_ce_vs_llm_fallback.py`` when changing models.

    ``rerank()`` deliberately does not sigmoid its output — it only needs
    relative ordering, and keeping the raw score avoids the extra exp call
    per candidate on large candidate pools.

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
    if not scores:
        return None
    import math
    logit = scores[0]
    # Guard against models that already return probabilities in [0, 1]
    # (rare but possible). Applying sigmoid to a probability would compress
    # it; detect by range and short-circuit.
    if 0.0 <= logit <= 1.0:
        return float(logit)
    return 1.0 / (1.0 + math.exp(-logit))
