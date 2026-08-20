#!/usr/bin/env python3
"""
Re-enrich articles that were filtered by a broken classifier.

Context: `HybridRelevanceService`'s classifier returned ~0 for topics it was
never trained on (e.g. "Quantum Computing"), vetoing semantically-relevant
articles. Those articles were saved with `ingest_status='filtered_relevance'`
and NULL category/sentiment, making them invisible to /explore.

The LLM-fallback fix in hybrid_relevance_service.py now arbitrates such
classifier/embedding disagreements. This script re-runs the pipeline against
already-filtered articles so the backlog can be recovered.

Selection criteria:
  - ingest_status = 'filtered_relevance'
  - topic matches the given --topic
  - keyword_relevance_score >= --min-embed  (embedding was confident; classifier
    was the veto source)

Each candidate is pushed through AutomatedIngestService.process_articles_batch,
which runs the fixed relevance scorer, the LLM analyzer, quality check, and
writes enrichment fields (category, sentiment, future_signal, etc.) back to
the same row — flipping it to 'approved' if it now passes.

Usage:
    python scripts/reenrich_filtered_articles.py \
        --topic "Quantum Computing" \
        --min-embed 0.5 \
        --batch-size 50 \
        [--limit N]   # cap total re-enrichments
        [--dry-run]   # list candidates only; do not process
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database
from app.services.automated_ingest_service import AutomatedIngestService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)
logger = logging.getLogger("reenrich")


def fetch_candidates(db: Database, topic: str, min_embed: float, limit: int | None,
                     min_alignment: float | None = None) -> List[Dict[str, Any]]:
    """Pull filtered-but-embedding-confident articles for re-enrichment.

    ``--min-alignment`` exists because the embedding score alone cannot tell a
    topic-relevant article from a topic-adjacent one. Measured on the SOC
    automation market: "Build vs Buy AI for the SOC" and "How to Choose a Smart
    Intercom System Manufacturer in China" both score ~0.70 on the embedding.
    ``topic_alignment_score`` separates them — 0.40 against 0.10 — so filtering
    on it means the re-enrichment pass pays for the articles worth recovering
    instead of re-rejecting the rest at LLM prices.
    """
    sql = """
        SELECT uri, title, summary, news_source, publication_date,
               keyword_relevance_score, topic_alignment_score
        FROM articles
        WHERE ingest_status = 'filtered_relevance'
          AND topic = :topic
          AND keyword_relevance_score >= :min_embed
    """
    params: Dict[str, Any] = {"topic": topic, "min_embed": min_embed}
    if min_alignment is not None:
        sql += " AND topic_alignment_score >= :min_align"
        params["min_align"] = min_alignment
    sql += " ORDER BY keyword_relevance_score DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    columns = [
        'uri', 'title', 'summary', 'news_source', 'publication_date',
        'keyword_relevance_score', 'topic_alignment_score',
    ]
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [dict(zip(columns, r)) for r in rows]


def fetch_topic_keywords(db: Database, topic: str) -> List[str]:
    """Keywords for this topic (used for relevance scoring context)."""
    try:
        return db.facade.get_monitored_keywords_for_topic((topic,)) or []
    except Exception as e:
        logger.warning(f"Could not fetch keywords for topic '{topic}': {e}")
        return []


async def reenrich(topic: str, min_embed: float, limit: int | None,
                   batch_size: int, dry_run: bool,
                   min_alignment: float | None = None) -> None:
    db = Database()
    candidates = fetch_candidates(db, topic, min_embed, limit, min_alignment)

    logger.info(f"Topic '{topic}': {len(candidates)} candidates for re-enrichment "
                f"(ingest_status='filtered_relevance', keyword_relevance_score >= {min_embed}"
                + (f", topic_alignment_score >= {min_alignment}" if min_alignment is not None else "")
                + ")")

    if not candidates:
        logger.info("Nothing to do.")
        return

    if dry_run:
        logger.info("DRY RUN — sample candidates:")
        for c in candidates[:10]:
            logger.info(f"  {c['keyword_relevance_score']:.2f}  {c['uri']}  {c['title'][:80]}")
        logger.info(f"(total {len(candidates)} candidates; re-run without --dry-run to process)")
        return

    keywords = fetch_topic_keywords(db, topic)
    logger.info(f"Using {len(keywords)} keywords from topic '{topic}' for relevance context")

    ingest = AutomatedIngestService(db)

    total_saved = 0
    total_still_filtered = 0
    total_errors = 0

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(candidates) + batch_size - 1) // batch_size
        logger.info(f"Batch {batch_num}/{total_batches} — {len(batch)} articles")

        # Shape each row into the dict process_articles_batch expects.
        formatted = []
        for c in batch:
            formatted.append({
                'uri': c['uri'],
                'title': c['title'] or '',
                'summary': c['summary'] or '',
                'news_source': c['news_source'] or '',
                'publication_date': c['publication_date'] or '',
                'content': '',      # triggers Firecrawl scrape in the pipeline
                'topic': topic,
                'analyzed': False,
            })

        try:
            results = await ingest.process_articles_batch(formatted, topic=topic, keywords=keywords)
        except Exception as e:
            logger.error(f"Batch {batch_num} failed: {e}", exc_info=True)
            total_errors += len(batch)
            continue

        saved = results.get('saved', 0)
        processed = results.get('processed', 0)
        total_saved += saved
        total_still_filtered += max(0, processed - saved)
        total_errors += len(results.get('errors', []))

        logger.info(f"Batch {batch_num} done: saved={saved}, processed={processed}, "
                    f"errors={len(results.get('errors', []))}")

    logger.info("=" * 60)
    logger.info(f"Re-enrichment complete for topic '{topic}':")
    logger.info(f"  Recovered (ingest_status -> approved): {total_saved}")
    logger.info(f"  Still filtered (below threshold even after LLM): {total_still_filtered}")
    logger.info(f"  Errors: {total_errors}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", required=True, help='Topic name, e.g. "Quantum Computing"')
    parser.add_argument("--min-embed", type=float, default=0.5,
                        help="Minimum keyword_relevance_score (embedding) for re-enrichment candidate (default 0.5)")
    parser.add_argument("--min-alignment", type=float, default=None,
                        help="Also require topic_alignment_score >= this. The "
                             "embedding cannot separate topic-relevant from "
                             "topic-adjacent; the alignment verdict can.")
    parser.add_argument("--limit", type=int, default=None, help="Cap total candidates (default: no cap)")
    parser.add_argument("--batch-size", type=int, default=50, help="Articles per LLM batch (default 50)")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without processing")
    args = parser.parse_args()

    asyncio.run(reenrich(
        topic=args.topic,
        min_embed=args.min_embed,
        min_alignment=args.min_alignment,
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
