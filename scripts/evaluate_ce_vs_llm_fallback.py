"""Backtest the cross-encoder tier against labeled user feedback.

Loads rows from ``user_relevance_feedback`` (which has ``article_uri`` + a
``more_like_this`` / ``less_like_this`` label), joins to the ``articles``
table for title + summary, scores each ``(topic, article)`` pair with the
cross-encoder, and reports:

  * per-label mean / range (so you can see whether CE scores separate
    relevant from irrelevant articles at all),
  * best single-threshold accuracy and the F1 score at that threshold,
  * the implied ``(CE_LOW, CE_HIGH)`` band for the high-confidence tails.

NOTE: only the CE_HIGH half of that band is still wired up. The CE tier in
hybrid_relevance_service is accept-only — measurement showed no reject
threshold exists with any real margin (the widest cut that loses no relevant
article was exactly the lowest-scoring relevant article), and a wrong
"confident reject" drops an article permanently with no LLM review. Read the
CE_LOW reported below as diagnostic only; it is not a knob any more.

If the label pool is too small (<20 per class) treat results as indicative;
the script reports what's usable for now and flags sparsity.

Usage:

    python3 scripts/evaluate_ce_vs_llm_fallback.py
    # Try a different model
    RERANK_MODEL=cross-encoder/stsb-roberta-base \
        python3 scripts/evaluate_ce_vs_llm_fallback.py

The earlier version of this script joined against
``relevance_confidence_readings`` — that table has no article FK, so the
lateral join collapsed to a single article per topic and every row was
scored identically. Fixed here.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ce_eval")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class LabeledPair:
    topic: str
    title: str
    summary: str
    is_relevant: bool  # more_like_this = True, less_like_this = False


def _fetch_pairs() -> list[LabeledPair]:
    from sqlalchemy import text
    from app.database import get_database_instance

    conn = get_database_instance()._temp_get_connection()
    rows = conn.execute(
        text(
            """
            SELECT f.topic, f.feedback_type, a.title, a.summary
            FROM user_relevance_feedback f
            JOIN articles a ON a.uri = f.article_uri
            WHERE f.feedback_type IN ('more_like_this', 'less_like_this')
            """
        )
    ).fetchall()
    return [
        LabeledPair(
            topic=r[0],
            title=r[2] or "",
            summary=r[3] or "",
            is_relevant=(r[1] == "more_like_this"),
        )
        for r in rows
        if r[2] or r[3]
    ]


def _score(pairs: list[LabeledPair]) -> list[tuple[LabeledPair, float]]:
    from app.retrieval.reranker import score_pair

    scored: list[tuple[LabeledPair, float]] = []
    for p in pairs:
        doc = f"{p.title}. {p.summary}".strip(". ")
        s = score_pair(p.topic, doc)
        if s is None:
            continue
        scored.append((p, s))
    return scored


def _best_threshold(scored: list[tuple[LabeledPair, float]]) -> tuple[float, float, float]:
    """Scan candidate thresholds (each observed score) and return the one
    with highest F1. Returns (threshold, accuracy, f1)."""
    if not scored:
        return 0.0, 0.0, 0.0
    best = (0.0, 0.0, -1.0)
    scores = sorted({s for _, s in scored})
    for t in scores:
        tp = sum(1 for p, s in scored if s >= t and p.is_relevant)
        fp = sum(1 for p, s in scored if s >= t and not p.is_relevant)
        fn = sum(1 for p, s in scored if s < t and p.is_relevant)
        tn = sum(1 for p, s in scored if s < t and not p.is_relevant)
        total = tp + fp + fn + tn
        if total == 0:
            continue
        acc = (tp + tn) / total
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best[2]:
            best = (t, acc, f1)
    return best


def _confident_tails(scored: list[tuple[LabeledPair, float]]) -> tuple[float, float, int, int]:
    """Find tightest (CE_LOW, CE_HIGH) that keep ≥85% accuracy on each tail.

    CE_LOW: highest threshold such that everything below is non-relevant
        with ≥85% accuracy. CE_HIGH: lowest threshold such that everything
        above is relevant with ≥85% accuracy. Returns (low, high,
        #decisive_below, #decisive_above).
    """
    scores = sorted({s for _, s in scored})
    low = min(scores) - 1.0
    high = max(scores) + 1.0
    n_low = 0
    n_high = 0

    # Sweep low threshold upward while below-threshold class stays ≥85% non-relevant.
    for t in scores:
        below = [p.is_relevant for p, s in scored if s < t]
        if not below:
            continue
        nr_frac = 1 - (sum(below) / len(below))
        if nr_frac >= 0.85:
            low = t
            n_low = len(below)

    # Sweep high threshold downward while above-threshold class stays ≥85% relevant.
    for t in reversed(scores):
        above = [p.is_relevant for p, s in scored if s >= t]
        if not above:
            continue
        rel_frac = sum(above) / len(above)
        if rel_frac >= 0.85:
            high = t
            n_high = len(above)

    return low, high, n_low, n_high


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=str, default=None,
                   help="Override RERANK_MODEL env var for this run")
    args = p.parse_args()

    os.environ.setdefault("RERANK_ENABLED", "true")
    if args.model:
        os.environ["RERANK_MODEL"] = args.model

    model_name = os.environ.get("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    logger.info("Evaluating model: %s", model_name)

    pairs = _fetch_pairs()
    logger.info("Fetched %d labeled pairs (%d relevant, %d not)",
                len(pairs), sum(1 for p in pairs if p.is_relevant),
                sum(1 for p in pairs if not p.is_relevant))
    if len(pairs) < 10:
        logger.warning("Sparse ground truth — results are indicative only")

    scored = _score(pairs)
    if not scored:
        logger.error("No CE scores produced — check model availability")
        return 2

    rel = [s for p, s in scored if p.is_relevant]
    nr = [s for p, s in scored if not p.is_relevant]

    print(f"\n===== {model_name} =====")
    if rel:
        print(f"  relevant     n={len(rel):2d}  mean={sum(rel)/len(rel):+7.3f}  range=[{min(rel):+7.3f}, {max(rel):+7.3f}]")
    if nr:
        print(f"  not-relevant n={len(nr):2d}  mean={sum(nr)/len(nr):+7.3f}  range=[{min(nr):+7.3f}, {max(nr):+7.3f}]")

    t, acc, f1 = _best_threshold(scored)
    print(f"  best single threshold: {t:+.3f}  accuracy={acc:.1%}  f1={f1:.2f}")

    low, high, n_low, n_high = _confident_tails(scored)
    print(f"  85%-confident tails: CE_LOW={low:+.3f} (covers {n_low}/{len(scored)})  "
          f"CE_HIGH={high:+.3f} (covers {n_high}/{len(scored)})")

    decisive = n_low + n_high
    print(f"  CE would bypass LLM for ~{decisive / len(scored):.0%} of borderline cases at these thresholds")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
