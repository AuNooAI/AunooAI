#!/usr/bin/env python3
"""Brand Risk v2 backfill (docs/BRAND_RISK_BENCHMARK_SPEC.md).

Screens every brand-classified article that has no screening verdict yet, then
groups risk-flagged articles into issues. Run from the tenant directory with
its venv:

    cd /home/orochford/tenants/<tenant>.aunoo.ai
    .venv/bin/python scripts/backfill_brand_screening.py [--brand-id N] [--dry-run]

Idempotent: verdicts are keyed on (article_uri, brand_id), so re-running only
touches articles that have none. Screening uses the gate in
app/services/brand_screening.py; gate-skipped articles are counted but get no
verdict row (they were never candidates, which is itself the signal).
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="report counts only, no LLM calls, no writes")
    args = ap.parse_args()

    from app.database import get_database_instance
    from app.services import brand_screening
    from app.services.brand_risk_assessment import build_issues_for_brand

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        brands = conn.execute(text(
            "SELECT id, COALESCE(display_name, name) FROM bw_brands "
            "WHERE enabled = true" + (" AND id = :bid" if args.brand_id else "") +
            " ORDER BY id"),
            ({"bid": args.brand_id} if args.brand_id else {})).fetchall()
        for bid, bname in brands:
            rows = conn.execute(text("""
                SELECT a.uri, a.title, LEFT(COALESCE(a.summary, ''), 2000),
                       COALESCE(a.sentiment, ''),
                       ARRAY_AGG(DISTINCT bac.category)
                FROM articles a
                JOIN bw_article_categories bac ON bac.article_uri = a.uri
                WHERE bac.brand_id = :bid
                  AND COALESCE(bac.relevance_score, a.topic_alignment_score) >= 0.4
                  AND NOT EXISTS (SELECT 1 FROM bw_screening_verdicts v
                                  WHERE v.article_uri = a.uri AND v.brand_id = :bid)
                GROUP BY a.uri, a.title, a.summary, a.sentiment
                ORDER BY MIN(a.publication_date)
            """), {"bid": bid}).fetchall()
            gated = sum(1 for _, t, s, sent, cats in rows
                        if brand_screening.should_screen(sent, f"{t or ''} {s or ''}", cats))
            print(f"[{bname}] {len(rows)} unscreened; {gated} pass the gate")
            if args.dry_run:
                continue
            found = none = 0
            for uri, title, summary, sentiment, cats in rows:
                outcome = await brand_screening.screen_article(
                    conn, uri, bid, bname, title or "", summary or "",
                    sentiment, cats)
                conn.commit()
                if outcome == "risk_found":
                    found += 1
                elif outcome == "no_risk_found":
                    none += 1
            stats = await build_issues_for_brand(conn, bid)
            conn.commit()
            print(f"[{bname}] screened: {found} risk_found, {none} no_risk_found; "
                  f"issues: {stats}")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
