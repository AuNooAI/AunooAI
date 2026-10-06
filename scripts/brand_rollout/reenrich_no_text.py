#!/usr/bin/env python3
"""Re-enrich articles the no-text guard failed although their page was scraped.

Until 6 Oct 2026 the ingest guard marked an article enrichment_failed when the
collector gave no summary, without looking at the scraped page in
raw_articles. The guard now uses that page (fix_no_text_guard.py). This sends
the earlier victims back through the site's own ingest pipeline with the page
attached, so they are judged and analysed once, normally.

Selects news rows (no social metadata) with ingest_status 'enrichment_failed',
an empty summary and a raw page of at least 200 characters, newest first.
Dry run unless --apply; --limit caps a run (default 100).

    cd /home/orochford/tenants/<site>.aunoo.ai
    .venv/bin/python /home/orochford/tenants/bugfixing.aunoo.ai/scripts/brand_rollout/reenrich_no_text.py --days 14 [--limit 100] [--apply]
"""
import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.getcwd())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(".env")
    import logging
    logging.disable(logging.INFO)
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = db._temp_get_connection()
    rows = conn.execute(text("""
        SELECT a.uri, a.title, a.news_source, a.publication_date, a.topic, r.raw_markdown
          FROM articles a JOIN raw_articles r ON r.uri = a.uri
         WHERE a.ingest_status = 'enrichment_failed'
           AND (a.social_meta IS NULL OR a.social_meta::text = 'null')
           AND COALESCE(a.summary, '') = ''
           AND length(COALESCE(r.raw_markdown, '')) >= 200
           AND left(a.submission_date, 10) >= to_char(now() - make_interval(days => :d), 'YYYY-MM-DD')
         ORDER BY a.submission_date DESC
         LIMIT :lim
    """), {"d": a.days, "lim": a.limit}).mappings().all()
    conn.close()
    by_topic = defaultdict(list)
    for r in rows:
        by_topic[r["topic"]].append({
            "uri": r["uri"], "url": r["uri"], "title": r["title"] or "", "summary": "",
            "news_source": r["news_source"] or "", "source": r["news_source"] or "",
            "publication_date": r["publication_date"], "topic": r["topic"],
            "_scraped_content": r["raw_markdown"], "analyzed": False,
        })
    print(f"{len(rows)} article(s) to re-enrich across {len(by_topic)} topic(s):")
    for t, arts in sorted(by_topic.items(), key=lambda x: -len(x[1])):
        print(f"  {t}: {len(arts)}")
    if not a.apply:
        print("Dry run. Re-run with --apply.")
        return 0

    from app.services.automated_ingest_service import AutomatedIngestService
    svc = AutomatedIngestService(db)
    totals = {"processed": 0, "saved": 0, "errors": 0}

    async def run():
        for topic, arts in by_topic.items():
            keywords = db.facade.get_monitored_keywords_for_topic((topic,))
            res = await svc.process_articles_batch(arts, topic, keywords or [])
            totals["processed"] += int(res.get("processed") or 0)
            totals["saved"] += int(res.get("saved") or 0)
            totals["errors"] += len(res.get("errors") or [])
    asyncio.run(run())
    conn = db._temp_get_connection()
    after = conn.execute(text("SELECT ingest_status, count(*) FROM articles WHERE uri = ANY(:u) GROUP BY 1"),
                         {"u": [r["uri"] for r in rows]}).fetchall()
    conn.close()
    print("result:", json.dumps(totals), "| status now:", {k: v for k, v in after})
    return 0


if __name__ == "__main__":
    sys.exit(main())
