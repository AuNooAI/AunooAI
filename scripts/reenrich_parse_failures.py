#!/usr/bin/env python3
"""
Re-enrich articles that entered enrichment but never came out of it.

Context: `ArticleAnalyzer.parse_analysis` validated the model's response by
exact heading match. When a model relabelled a heading ("Driver Signal
Explanation" for "Driver Type Explanation"), numbered them ("1. Category"),
wrapped them in markdown ("**Sentiment:** Positive"), collapsed the four
rationales into one "Explanation" block, or omitted "Title", the whole
analysis was discarded and the row was left with NULL category/sentiment.

Every observer agent retrieves on "sentiment IS NOT NULL AND category IS NOT
NULL", so those articles were invisible to signal alerts, /explore and reports
— permanently, because nothing retries them.

The parser now aliases heading variants, strips list/markdown decoration from
keys and values, reuses a merged "Explanation" block, falls back to the
caller's title, and only hard-fails when Title/Summary/Category/Sentiment are
genuinely absent. This script re-runs the pipeline over the backlog those
failures left behind.

Selection criteria (the signature of a mid-pipeline drop):
  - category IS NULL          -- enrichment never wrote its fields
  - ingest_status IS NULL     -- NOT 'filtered_relevance'; those were dropped
                                 deliberately by the relevance gate and are
                                 the business of reenrich_filtered_articles.py
  - news_source <> 'bluesky'  -- social posts are enriched on another path

Articles are grouped by their stored `topic` because the analysis ontology
(categories, future signals, sentiments...) is resolved per topic.

By default the stored summary is reused as article content, which avoids
re-scraping the whole backlog. That is what the observer agents read anyway
(they format title + summary). Pass --rescrape to fetch full text instead.

Usage:
    python scripts/reenrich_parse_failures.py --dry-run
    python scripts/reenrich_parse_failures.py --since 2026-07-01
    python scripts/reenrich_parse_failures.py --topic "Brand Monitoring Wiley"
    python scripts/reenrich_parse_failures.py --limit 500 --rescrape
"""

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database
from app.services.automated_ingest_service import AutomatedIngestService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger("reenrich-parse-failures")

COLUMNS = ['uri', 'title', 'summary', 'news_source', 'publication_date',
           'submission_date', 'topic']


def fetch_candidates(db: Database, since: str | None, topic: str | None,
                     limit: int | None) -> List[Dict[str, Any]]:
    """Pull rows that entered enrichment and never had fields written back."""
    sql = """
        SELECT uri, title, summary, news_source, publication_date,
               submission_date, topic
        FROM articles
        WHERE category IS NULL
          AND ingest_status IS NULL
          AND news_source <> 'bluesky'
          AND topic IS NOT NULL AND topic <> ''
          AND title IS NOT NULL AND title <> ''
    """
    params: Dict[str, Any] = {}
    if since:
        sql += " AND submission_date >= :since"
        params["since"] = since
    if topic:
        sql += " AND topic = :topic"
        params["topic"] = topic
    sql += " ORDER BY submission_date DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [dict(zip(COLUMNS, r)) for r in rows]


def fetch_topic_keywords(db: Database, topic: str) -> List[str]:
    try:
        return db.facade.get_monitored_keywords_for_topic((topic,)) or []
    except Exception as e:
        logger.warning(f"Could not fetch keywords for topic '{topic}': {e}")
        return []


async def missing_ontology(ingest: AutomatedIngestService, topic: str) -> List[str]:
    """Name the ontology lists this topic is missing, if any.

    analyze_content() rejects an empty list for any of these before it calls
    the model, so a topic with a gap here can never enrich — re-running it
    just burns a scrape and a batch to rediscover that. Checked up front so
    those topics are reported and skipped instead.
    """
    research = ingest._get_research()
    checks = {
        'categories': research.get_categories,
        'future_signals': research.get_future_signals,
        'sentiment': research.get_sentiments,
        'time_to_impact': research.get_time_to_impact,
        'driver_types': research.get_driver_types,
    }
    missing = []
    for name, getter in checks.items():
        try:
            if not await getter(topic):
                missing.append(name)
        except Exception as e:
            logger.warning(f"Could not read '{name}' for topic '{topic}': {e}")
            missing.append(name)
    return missing


async def reenrich(since: str | None, topic: str | None, limit: int | None,
                   batch_size: int, rescrape: bool, dry_run: bool) -> None:
    db = Database()
    candidates = fetch_candidates(db, since, topic, limit)

    if not candidates:
        logger.info("No articles match the stuck-enrichment signature. Nothing to do.")
        return

    by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        by_topic[c['topic']].append(c)

    logger.info(f"{len(candidates)} article(s) stuck without enrichment, "
                f"across {len(by_topic)} topic(s)")
    for t, rows in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        logger.info(f"  {len(rows):>6}  {t}")

    if dry_run:
        logger.info("DRY RUN — sample candidates:")
        for c in candidates[:10]:
            logger.info(f"  [{c['topic']}] {c['submission_date']}  {c['uri']}")
        logger.info(f"(total {len(candidates)}; re-run without --dry-run to process)")
        return

    ingest = AutomatedIngestService(db)
    total_saved = total_processed = total_errors = total_skipped = 0

    for topic_name, rows in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        gaps = await missing_ontology(ingest, topic_name)
        if gaps:
            logger.error(
                f"SKIPPING topic '{topic_name}' ({len(rows)} article(s)): ontology is "
                f"missing {', '.join(gaps)}. These articles cannot enrich until the "
                f"topic config is completed — this is a config gap, not a parse failure.")
            total_skipped += len(rows)
            continue

        keywords = fetch_topic_keywords(db, topic_name)
        logger.info(f"=== Topic '{topic_name}': {len(rows)} article(s), "
                    f"{len(keywords)} keyword(s) for relevance context ===")

        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(rows) + batch_size - 1) // batch_size

            formatted = []
            for c in batch:
                summary = (c['summary'] or '').strip()
                # process_articles_batch scrapes anything under 200 chars, so a
                # short/absent summary still gets full text fetched for it.
                content = '' if rescrape else summary
                formatted.append({
                    'uri': c['uri'],
                    'title': c['title'] or '',
                    'summary': summary,
                    'news_source': c['news_source'] or '',
                    'publication_date': c['publication_date'] or '',
                    'content': content,
                    'topic': topic_name,
                    'analyzed': False,
                })

            logger.info(f"Batch {batch_num}/{total_batches} — {len(batch)} articles")
            try:
                results = await ingest.process_articles_batch(
                    formatted, topic=topic_name, keywords=keywords)
            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}", exc_info=True)
                total_errors += len(batch)
                continue

            saved = results.get('saved', 0)
            processed = results.get('processed', 0)
            errors = len(results.get('errors', []))
            total_saved += saved
            total_processed += processed
            total_errors += errors
            logger.info(f"Batch {batch_num} done: saved={saved}, "
                        f"processed={processed}, errors={errors}")

    logger.info("=" * 60)
    logger.info("Re-enrichment complete:")
    logger.info(f"  Candidates:        {len(candidates)}")
    logger.info(f"  Processed:         {total_processed}")
    logger.info(f"  Saved (enriched):  {total_saved}")
    logger.info(f"  Errors:            {total_errors}")
    logger.info(f"  Skipped (topic ontology incomplete): {total_skipped}")
    logger.info("Verify with: SELECT COUNT(*) FROM articles "
                "WHERE category IS NULL AND ingest_status IS NULL "
                "AND news_source <> 'bluesky';")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None,
                        help="Only articles with submission_date >= this (YYYY-MM-DD)")
    parser.add_argument("--topic", default=None, help="Restrict to a single topic")
    parser.add_argument("--limit", type=int, default=None, help="Cap total candidates")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Articles per pipeline batch (default 50)")
    parser.add_argument("--rescrape", action="store_true",
                        help="Fetch full article text instead of reusing the stored summary")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the backlog without processing it")
    args = parser.parse_args()

    asyncio.run(reenrich(args.since, args.topic, args.limit,
                         args.batch_size, args.rescrape, args.dry_run))


if __name__ == "__main__":
    main()
