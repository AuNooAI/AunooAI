#!/usr/bin/env python3
"""Detect the article-collection gap for this tenant and write the artifact.

Finds the longest contiguous span (>= MIN_GAP_DAYS) with zero collected
articles in the recent window, plus a per-source before/after breakdown so
we can tell a pipeline outage (all sources silent) from a single-source
lapse. Writes ``data/wiley_horizons/collection_gap.json`` — the single
source of truth for both ``backfill_collection_gap.py`` and the deck's
collection-gap disclosure footnote (§5 / §91 of the plan).

Run from a tenant directory so it uses that tenant's DB:
    python scripts/detect_collection_gap.py [--since 2026-01-01] [--min-days 5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_PATH = "data/wiley_horizons/collection_gap.json"
MIN_GAP_DAYS = 5


def _iso_day(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def detect(since: str = "2026-01-01", min_days: int = MIN_GAP_DAYS) -> dict:
    from app.database import get_database_instance
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(text(
            "SELECT substring(publication_date,1,10) d, count(*) n "
            "FROM articles WHERE publication_date >= :since GROUP BY 1 ORDER BY 1"
        ), {"since": since}).fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    days: dict[date, int] = {}
    for d, n in rows:
        dd = _iso_day(d)
        if dd:
            days[dd] = days.get(dd, 0) + int(n)
    if not days:
        return {"detected": False, "reason": "no dated articles in window"}

    lo, hi = min(days), max(days)
    # Longest contiguous zero-run between populated days.
    best = None
    run: list[date] = []
    dd = lo
    while dd <= hi:
        if days.get(dd, 0) == 0:
            run.append(dd)
        else:
            if len(run) >= min_days and (best is None or len(run) > best[2]):
                best = (run[0], run[-1], len(run))
            run = []
        dd += timedelta(days=1)
    if len(run) >= min_days and (best is None or len(run) > best[2]):
        best = (run[0], run[-1], len(run))

    if not best:
        return {"detected": False, "reason": f"no contiguous gap >= {min_days} days",
                "window": [lo.isoformat(), hi.isoformat()]}

    start, end, ndays = best
    # Per-source breakdown: which sources were active just before/after the
    # gap (i.e. should have produced articles during it).
    from app.database import get_database_instance as _g
    conn = _g()._temp_get_connection()
    try:
        from sqlalchemy import text as _t
        before = conn.execute(_t(
            "SELECT DISTINCT news_source FROM articles "
            "WHERE publication_date >= :a AND publication_date < :b AND news_source IS NOT NULL"
        ), {"a": (start - timedelta(days=14)).isoformat(), "b": start.isoformat()}).fetchall()
        after = conn.execute(_t(
            "SELECT DISTINCT news_source FROM articles "
            "WHERE publication_date > :b AND publication_date <= :c AND news_source IS NOT NULL"
        ), {"b": end.isoformat(), "c": (end + timedelta(days=14)).isoformat()}).fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    sources_affected = sorted({r[0] for r in before} & {r[0] for r in after})
    # When essentially every source goes silent at once it's a collection
    # pipeline outage, not per-source rate limits — store a count, not the
    # (hundreds-long) source list.
    likely_outage = len(sources_affected) >= 20
    return {
        "detected": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": ndays,
        "likely_pipeline_outage": likely_outage,
        "n_sources_active_around_gap": len(sources_affected),
        "sample_sources": sources_affected[:10],
        "n_recovered": None,  # filled by backfill_collection_gap.py
        "window_examined": [lo.isoformat(), hi.isoformat()],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--min-days", type=int, default=MIN_GAP_DAYS)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    result = detect(since=args.since, min_days=args.min_days)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
