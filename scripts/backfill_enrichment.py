#!/usr/bin/env python3
"""
Backfill Enrichment Script

Enriches articles that are missing sentiment, driver_type, time_to_impact, and future_signal
using the SLM enrichment service (DeBERTa classifier).

Can also regenerate summaries using vLLM Phi-3 for articles where summary = title.

Usage:
    python scripts/backfill_enrichment.py --source "Trump Action Tracker" --limit 100
    python scripts/backfill_enrichment.py --all-unenriched --limit 500
    python scripts/backfill_enrichment.py --source "Trump Action Tracker" --fix-summaries
"""

import sys
import os
import argparse
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database
from app.services.enrichment_service import get_enrichment_service
from app.services.summarization_service import get_summarization_service


def get_unenriched_articles(db, source=None, limit=100, fix_summaries=False):
    """Fetch articles missing enrichment fields."""

    if fix_summaries:
        # Get articles where summary equals title (fake summaries from CSV import)
        query = """
            SELECT uri, title, summary, topic, news_source
            FROM articles
            WHERE sentiment IS NULL
              AND summary IS NOT NULL
              AND TRIM(summary) = TRIM(title)
        """
    else:
        query = """
            SELECT uri, title, summary, topic, news_source
            FROM articles
            WHERE sentiment IS NULL
        """

    if source:
        query += " AND news_source = :source"

    query += " ORDER BY uri DESC LIMIT :limit"

    params = {"limit": limit}
    if source:
        params["source"] = source

    return db.fetch_all(query, params)


def update_article_enrichment(db, uri, enrichment_data):
    """Update article with enrichment data."""
    query = """
        UPDATE articles
        SET sentiment = :sentiment,
            time_to_impact = :time_to_impact,
            driver_type = :driver_type,
            future_signal = :future_signal
        WHERE uri = :uri
    """

    db.execute_query(query, {
        "uri": uri,
        "sentiment": enrichment_data.get("sentiment"),
        "time_to_impact": enrichment_data.get("time_to_impact"),
        "driver_type": enrichment_data.get("driver_type"),
        "future_signal": enrichment_data.get("future_signal"),
    })


def update_article_summary(db, uri, summary):
    """Update article summary."""
    query = """
        UPDATE articles
        SET summary = :summary
        WHERE uri = :uri
    """
    db.execute_query(query, {"uri": uri, "summary": summary})


def main():
    parser = argparse.ArgumentParser(description="Backfill enrichment for articles")
    parser.add_argument("--source", type=str, help="News source to filter (e.g., 'Trump Action Tracker')")
    parser.add_argument("--all-unenriched", action="store_true", help="Process all unenriched articles")
    parser.add_argument("--limit", type=int, default=100, help="Maximum articles to process")
    parser.add_argument("--fix-summaries", action="store_true", help="Also regenerate summaries where summary=title")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--batch-size", type=int, default=10, help="Commit after N articles")

    args = parser.parse_args()

    if not args.source and not args.all_unenriched:
        print("Error: Must specify --source or --all-unenriched")
        sys.exit(1)

    print("=" * 70)
    print("ENRICHMENT BACKFILL")
    print("=" * 70)
    print(f"Source filter: {args.source or 'ALL'}")
    print(f"Limit: {args.limit}")
    print(f"Fix summaries: {args.fix_summaries}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 70)

    # Initialize services
    db = Database()
    enrichment_service = get_enrichment_service()
    summarization_service = get_summarization_service() if args.fix_summaries else None

    # Check service availability
    print(f"\nEnrichment service available: {enrichment_service.is_available()}")
    if args.fix_summaries:
        print(f"Summarization service available: {summarization_service.is_available()}")
        print(f"Summarization status: {summarization_service.get_status()}")

    if not enrichment_service.is_available():
        print("ERROR: Enrichment service not available!")
        sys.exit(1)

    # Get articles to process
    print("\nFetching unenriched articles...")
    articles = get_unenriched_articles(
        db,
        source=args.source if not args.all_unenriched else None,
        limit=args.limit,
        fix_summaries=args.fix_summaries
    )

    print(f"Found {len(articles)} articles to process")

    if not articles:
        print("No articles to process!")
        return

    # Process articles
    stats = {
        "processed": 0,
        "enriched": 0,
        "summaries_fixed": 0,
        "errors": 0,
        "total_time": 0,
    }

    start_time = time.time()

    for i, article in enumerate(articles, 1):
        uri = article["uri"]
        title = article["title"]
        summary = article["summary"] or title
        source = article["news_source"]

        print(f"\n[{i}/{len(articles)}] {title[:60]}...")
        print(f"  Source: {source}")

        try:
            # Step 1: Fix summary if needed
            if args.fix_summaries and summary.strip() == title.strip():
                print("  Summary = Title, regenerating...")
                if summarization_service and summarization_service.is_available():
                    # For articles without content, use title as content
                    # In production, you might want to fetch raw_articles.raw_markdown
                    sum_start = time.time()
                    result = summarization_service.summarize(title=title, content=title)
                    sum_time = time.time() - sum_start

                    new_summary = result.get("summary", "")
                    sum_source = result.get("source", "unknown")

                    if new_summary and len(new_summary) > len(title):
                        summary = new_summary
                        if not args.dry_run:
                            update_article_summary(db, uri, summary)
                        stats["summaries_fixed"] += 1
                        print(f"  ✅ Summary regenerated via {sum_source} ({sum_time:.1f}s): {summary[:60]}...")
                    else:
                        print(f"  ⚠️  Summary generation returned short result, keeping original")
                else:
                    print("  ⚠️  Summarization service not available")

            # Step 2: Enrich with SLM
            enrich_start = time.time()
            enrichment = enrichment_service.enrich(title=title, summary=summary)
            enrich_time = time.time() - enrich_start

            print(f"  Sentiment: {enrichment.get('sentiment')} ({enrichment.get('sentiment_confidence', 0):.2f})")
            print(f"  Driver: {enrichment.get('driver_type')} ({enrichment.get('driver_type_confidence', 0):.2f})")
            print(f"  TTI: {enrichment.get('time_to_impact')} ({enrichment.get('time_to_impact_confidence', 0):.2f})")
            print(f"  Signal: {enrichment.get('future_signal')} ({enrichment.get('future_signal_confidence', 0):.2f})")
            print(f"  ⏱️  Enrichment took {enrich_time:.2f}s")

            # Step 3: Update database
            if not args.dry_run:
                update_article_enrichment(db, uri, enrichment)

            stats["enriched"] += 1
            stats["processed"] += 1

            # Commit in batches
            if not args.dry_run and i % args.batch_size == 0:
                print(f"  💾 Committed batch ({i} articles)")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            stats["errors"] += 1
            stats["processed"] += 1

    stats["total_time"] = time.time() - start_time

    # Print summary
    print("\n" + "=" * 70)
    print("BACKFILL COMPLETE")
    print("=" * 70)
    print(f"Processed: {stats['processed']}")
    print(f"Enriched: {stats['enriched']}")
    print(f"Summaries fixed: {stats['summaries_fixed']}")
    print(f"Errors: {stats['errors']}")
    print(f"Total time: {stats['total_time']:.1f}s")
    print(f"Avg per article: {stats['total_time'] / max(stats['processed'], 1):.2f}s")

    if args.dry_run:
        print("\n⚠️  DRY RUN - No changes were made to the database")


if __name__ == "__main__":
    main()
