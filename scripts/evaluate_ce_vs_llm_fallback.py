"""Backtest the cross-encoder tier against historical LLM-fallback decisions.

Pulls rows from ``relevance_confidence_readings`` where ``method`` contains
``llm_fallback`` (i.e. borderline cases the old pipeline sent to GPT/Qwen),
reconstructs ``(topic, title, summary)`` triples from the matching articles
table, scores each triple with the cross-encoder, and compares against the
stored LLM score.

Output: agreement rates at configurable CE thresholds so the operator can
pick a (CE_LOW, CE_HIGH) band before enabling ``RELEVANCE_USE_CE_TIER=true``.

Usage:

    python3 scripts/evaluate_ce_vs_llm_fallback.py --days 30 --ce-low 0.15 --ce-high 0.80

The articles join is best-effort — old readings do not carry an article ID,
so we match on ``topic`` + approximate ``recorded_at`` window. Misses are
counted and reported.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ce_eval")

# Ensure app is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class Reading:
    topic: str
    title: str
    summary: str
    llm_score: float
    stored_relevant: bool


def _fetch_readings(days: int, limit: int) -> list[Reading]:
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = db._temp_get_connection()

    # Stored readings do not carry the article body directly, so we join to
    # the articles table on topic + recorded_at proximity. A tighter match
    # would need an article_id FK on readings (future migration).
    sql = text(
        """
        SELECT r.topic, r.score AS llm_score, r.relevant,
               a.title, a.summary
        FROM relevance_confidence_readings r
        JOIN LATERAL (
            SELECT title, summary
            FROM articles
            WHERE topic = r.topic
              AND submission_date::timestamp BETWEEN r.recorded_at - INTERVAL '1 hour'
                                                AND r.recorded_at + INTERVAL '1 hour'
            ORDER BY submission_date DESC
            LIMIT 1
        ) a ON TRUE
        WHERE r.method LIKE '%%llm_fallback%%'
          AND r.recorded_at >= NOW() - INTERVAL ':days days'
          AND r.score IS NOT NULL
        ORDER BY r.recorded_at DESC
        LIMIT :limit
        """.replace(":days days", f"{int(days)} days")
    )

    rows = conn.execute(sql, {"limit": limit}).fetchall()
    return [
        Reading(
            topic=row[0], llm_score=float(row[1]), stored_relevant=bool(row[2]),
            title=row[3] or "", summary=row[4] or "",
        )
        for row in rows
        if row[3] or row[4]
    ]


def evaluate(readings: list[Reading], ce_low: float, ce_high: float) -> dict:
    from app.retrieval.reranker import score_pair

    n_total = len(readings)
    n_ce_missing = 0
    n_ce_decisive = 0
    n_agree = 0
    n_disagree = 0
    ce_scores: list[float] = []

    for r in readings:
        doc = f"{r.title}. {r.summary}".strip(". ")
        ce = score_pair(r.topic, doc)
        if ce is None:
            n_ce_missing += 1
            continue
        ce_scores.append(ce)

        if ce < ce_low or ce > ce_high:
            n_ce_decisive += 1
            ce_verdict = ce > ce_high
            # Compare against stored LLM verdict (score >= 0.5 = relevant).
            llm_verdict = r.llm_score >= 0.5
            if ce_verdict == llm_verdict:
                n_agree += 1
            else:
                n_disagree += 1

    return {
        "total_rows": n_total,
        "ce_missing": n_ce_missing,
        "ce_decisive": n_ce_decisive,
        "ce_borderline": n_total - n_ce_missing - n_ce_decisive,
        "agree_with_llm": n_agree,
        "disagree_with_llm": n_disagree,
        "agreement_rate": (n_agree / n_ce_decisive) if n_ce_decisive else None,
        "ce_score_mean": (sum(ce_scores) / len(ce_scores)) if ce_scores else None,
        "ce_score_min": min(ce_scores) if ce_scores else None,
        "ce_score_max": max(ce_scores) if ce_scores else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=30, help="Lookback window")
    p.add_argument("--limit", type=int, default=1000, help="Max rows to evaluate")
    # Defaults bracket the confident tails of MS-MARCO MiniLM logits; tune
    # with --ce-low / --ce-high when evaluating a different model.
    p.add_argument("--ce-low", type=float, default=-10.0)
    p.add_argument("--ce-high", type=float, default=-3.0)
    args = p.parse_args()

    # Force RERANK_ENABLED on so the singleton will load; the CE model is
    # needed regardless of whether retrieval reranking is enabled in prod.
    os.environ.setdefault("RERANK_ENABLED", "true")

    logger.info("Fetching readings (last %d days, limit %d)...", args.days, args.limit)
    readings = _fetch_readings(args.days, args.limit)
    logger.info("Got %d readings with article bodies", len(readings))

    if not readings:
        logger.warning("No readings found — enable hybrid+llm_fallback logging first")
        return 2

    stats = evaluate(readings, args.ce_low, args.ce_high)

    print("\n===== CE vs LLM-fallback agreement =====")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"  {k:<20} {v:.3f}")
        else:
            print(f"  {k:<20} {v}")
    print("")

    rate = stats["agreement_rate"]
    if rate is None:
        print("No decisive CE predictions at the chosen thresholds — tighten CE_LOW/HIGH.")
        return 3
    if rate >= 0.85:
        print(f"[OK] Agreement {rate:.1%} ≥ 85%; safe to enable RELEVANCE_USE_CE_TIER=true.")
        return 0
    print(f"[WARN] Agreement {rate:.1%} < 85%; tune thresholds or collect more feedback.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
