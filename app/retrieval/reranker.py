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

# Default: BAAI/bge-reranker-base. Multilingual (XLM-RoBERTa base, which the
# German and Japanese posts on the brand tenants need), ~278M params, Apache
# 2.0, and like the rest of the BGE family it outputs bounded [0, 1]
# probabilities after sigmoid — so ``score_pair`` thresholds stay
# interpretable without per-model calibration. Measured here on a relevant
# and an irrelevant document for the same query: 0.888 against 0.0001.
#
# It replaced BAAI/bge-reranker-v2-m3 (~568M) on 23 September 2026, when the
# reranker moved to CPU: v2-m3 costs 0.72s per pair on this host under load
# against this model's 0.14s, which is the difference between reordering 32
# candidates in 4s and 16 in 12s. The context window is not the trade-off it
# looks like — ``_get_model`` pins ``max_length=512`` for every model, so
# v2-m3's 8K window was never reachable either.
#
# Legacy option: ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (~90MB, English
# only, unbounded logits) if a site needs a tiny footprint and has no
# non-English corpus.
RERANK_MODEL_NAME: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-base")

# How many cosine-ranked candidates to fetch per top_k requested.
# k=10, factor=5 → pull 50 from pgvector, rerank down to 10.
RERANK_OVERFETCH_FACTOR: int = int(os.getenv("RERANK_OVERFETCH_FACTOR", "5"))

# Hard ceiling on the overfetched candidate pool — guards against a caller
# asking for top_k=100 and triggering a 500-candidate CE pass.
RERANK_MAX_CANDIDATES: int = int(os.getenv("RERANK_MAX_CANDIDATES", "200"))

RERANK_BATCH_SIZE: int = int(os.getenv("RERANK_BATCH_SIZE", "32"))

# Where the cross-encoder runs. This host's GPU is fully committed - vLLM
# holds 17 of its 20 GB, alongside the e5 and DeBERTa encoder services - so a
# CUDA load raises "CUDA error: out of memory", and because the failure path
# is a silent no-op every tenant had been reranking nothing since the GPU
# filled up. CPU is the default: a slower rerank beats no rerank. Set
# RERANK_DEVICE=cuda on a host with room.
RERANK_DEVICE: str = os.getenv("RERANK_DEVICE", "cpu")
_ON_CPU: bool = RERANK_DEVICE.split(":")[0].lower() == "cpu"

# Torch threads for CE inference. Measured here (20 cores, under normal
# load): eight threads score as fast as twenty, because the pass is bound by
# memory bandwidth rather than cores, and eight leaves the other tenants and
# the pipeline worker their share.
RERANK_THREADS: int = int(os.getenv("RERANK_THREADS", "8"))

# Per-candidate text length cap, in characters. The tokenizer truncates at
# 512 tokens (~2000 chars) whatever this says, so the GPU default is really a
# "don't bother trimming" value. On CPU the sequence length is most of the
# cost — 32 candidates take 4.3s at 700 chars against 15s at 1500 — so CPU
# keeps the title and lede and drops the body.
RERANK_MAX_TEXT_LEN: int = int(os.getenv("RERANK_MAX_TEXT_LEN", "700" if _ON_CPU else "4000"))

# How many candidates the cross-encoder actually scores, as opposed to how
# many are fetched. This is the latency dial. A pair costs about
# 0.14s here with bge-reranker-base, so thirty-two candidates is 4.3s even
# with this host at its usual load average of 27 on 20 cores. Candidates
# past the cap keep
# their cosine order behind the scored ones instead of being dropped, so a
# caller asking for top_k=100 still gets 100 rows - only the head of the list
# is reordered. Keep it a clear multiple of a typical top_k: at ten, with
# callers asking for top_k=10 or 20, the cross-encoder has nothing left to
# rescue and the pass buys nothing for its seconds — measured on oviva, where
# a ten-candidate budget dropped the best answer to a question before the
# caller ever saw it.
RERANK_MAX_SCORED: int = int(os.getenv("RERANK_MAX_SCORED", "32" if _ON_CPU else "200"))

# assign_exclusive scores every article against every scenario, so its pair
# count is a product and grows fast. Past this ceiling it returns unassigned
# and Forecast Assessment falls back to topic-only attribution, rather than
# occupying a worker for the best part of an hour.
RERANK_MAX_PAIRS: int = int(os.getenv("RERANK_MAX_PAIRS", "1500" if _ON_CPU else "20000"))


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
        logger.info("Loading retrieval reranker: %s on %s", RERANK_MODEL_NAME, RERANK_DEVICE)
        if _ON_CPU and RERANK_THREADS > 0:
            try:
                import torch
                torch.set_num_threads(RERANK_THREADS)
            except Exception:  # noqa: BLE001
                logger.debug("Could not cap torch threads", exc_info=True)
        _model = CrossEncoder(RERANK_MODEL_NAME, max_length=512, device=RERANK_DEVICE)
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
    topic: Optional[str] = None,
) -> list[dict]:
    """Rerank cosine-ordered ``candidates`` against ``query``.

    ``topic`` is optional and only feeds the TypeSafe Jev shadow
    (``app.retrieval.rerank_shadow``), which records what Jev would have
    ranked for brand and market topics; it never changes the order returned.

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

    # Cap the pool actually scored. Everything past the cap keeps its cosine
    # order behind the scored rows, so a caller asking for top_k=100 still
    # gets 100 - it is the reordering that is bounded, not the result set.
    pool = candidates[:RERANK_MAX_SCORED]
    unscored = candidates[RERANK_MAX_SCORED:]
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
    ranked = [c for _, c in scored] + unscored

    # Shadow (brand and market topics only): record Jev's per-candidate
    # relevance next to this order. Own thread, never changes `ranked`.
    if topic:
        try:
            from app.retrieval import rerank_shadow
            rerank_shadow.schedule(query_trimmed, topic, pool, ranked, top_k, caller="reranker.rerank")
        except Exception as shadow_err:  # noqa: BLE001
            logger.debug(f"rerank shadow not scheduled: {shadow_err}")
        # Decision (TYPESAFE_DECIDE_RERANK, brand and market topics): drop the
        # top-k candidates Jev says do not answer the query. Off by default;
        # off or failing, the list below is exactly ranked[:top_k].
        try:
            from app.retrieval import rerank_shadow as _rs
            return await asyncio.to_thread(_rs.decide, query_trimmed, topic, ranked, top_k, "reranker.rerank")
        except Exception as decide_err:  # noqa: BLE001
            logger.warning(f"rerank decide failed, cosine-reranked order kept: {decide_err}")

    return ranked[:top_k]


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

    if len(pairs) > RERANK_MAX_PAIRS:
        logger.warning(
            "assign_exclusive asked for %d pairs (%d articles x %d scenarios), "
            "over the %d ceiling — returning unassigned so the caller falls "
            "back to topic-only attribution",
            len(pairs), len(articles), len(scenarios), RERANK_MAX_PAIRS,
        )
        return [
            {"scenario_idx": None, "score": None, "margin": None,
             "best_alt_scenario_idx": None, "all_scores": []}
            for _ in articles
        ]

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
