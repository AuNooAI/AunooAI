#!/usr/bin/env python3
"""Run Brand Watcher's reader endpoints for every enabled brand on this site
and report any that fail. Read-only: no model calls, nothing written.

Brand labels change the SQL these readers build (brand_coverage), so a query
that is valid with the flag off can fail once BRAND_RELATION_DECISIONS is on
(6 Oct 2026: /stats failed with "missing FROM-clause entry for table bac").

    cd /home/orochford/tenants/<site>.aunoo.ai && .venv/bin/python /home/orochford/tenants/bugfixing.aunoo.ai/scripts/brand_rollout/smoke_bw_readers.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(".env")
    import logging
    logging.disable(logging.WARNING)
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.routes import brand_watcher_routes as r
    from app.services.brand_coverage import labels_active

    conn = get_database_instance()._temp_get_connection()
    brands = conn.execute(text("SELECT id, display_name FROM bw_brands WHERE enabled ORDER BY id")).fetchall()
    conn.close()
    print(f"site={os.path.basename(os.getcwd())} labels_active={labels_active()} brands={len(brands)}")
    calls = []
    for bid, name in brands:
        calls += [
            (f"stats {name}", lambda b=bid: r.get_stats(brand_id=b, brand_ids=None, topics=None, days_back=365, session={})),
            (f"categories {name}", lambda b=bid: r.get_category_distribution(brand_id=b, brand_ids=None, topics=None, days_back=365, session={})),
            (f"temporal {name}", lambda b=bid: r.get_temporal_data(brand_id=b, brand_ids=None, topics=None, days_back=365, session={})),
            (f"sentiment-trends {name}", lambda b=bid: r.get_sentiment_trends(brand_id=b, topics=None, days_back=365, session={})),
            (f"alerts {name}", lambda b=bid: r.get_brand_alerts(brand_id=b, days_back=30, session={})),
        ]
    calls += [
        ("stats all", lambda: r.get_stats(brand_id=None, brand_ids=None, topics=None, days_back=365, session={})),
        ("comparison all", lambda: r.get_brand_comparison(topics=None, brand_ids=None, days_back=365, session={})),
    ]
    failed = 0

    async def run():
        nonlocal failed
        for label, fn in calls:
            try:
                await fn()
            except Exception as e:  # noqa: BLE001
                failed += 1
                detail = getattr(e, "detail", None) or str(e)
                print(f"FAIL {label}: {type(e).__name__}: {str(detail)[:200]}")
    asyncio.run(run())

    # Brand risk assessment builds its own queries with the same rule.
    try:
        from app.services import brand_risk_assessment as bra
        conn = get_database_instance()._temp_get_connection()
        from datetime import date
        for bid, name in brands:
            for fn in ("_attention",):
                if hasattr(bra, fn):
                    try:
                        getattr(bra, fn)(conn, bid, date.today().isoformat())
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        conn.rollback()
                        print(f"FAIL risk.{fn} {name}: {type(e).__name__}: {str(e)[:200]}")
        conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"risk module not checked: {e}")
    print(f"{len(calls)} endpoint calls, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
