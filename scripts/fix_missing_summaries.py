#!/usr/bin/env python3
"""
Script to re-analyze articles that have NewsAPI descriptions instead of AI-generated summaries.
This fixes articles that were analyzed before the bug fix was applied.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database
from app.bulk_research import BulkResearch
from app.research import Research
from sqlalchemy import select, text
from app.database_models import t_articles

async def fix_missing_summaries(days_back=7, limit=100, dry_run=True, auto_yes=False):
    """
    Find and fix articles with NewsAPI summaries instead of AI summaries.

    Args:
        days_back: How many days back to check (default: 7)
        limit: Maximum number of articles to fix (default: 100)
        dry_run: If True, only show what would be fixed without actually fixing (default: True)
        auto_yes: If True, skip confirmation prompt (default: False)
    """

    print(f"\n{'='*80}")
    print(f"Fixing Articles with Missing AI Summaries")
    print(f"Days back: {days_back} | Limit: {limit} | Dry run: {dry_run}")
    print(f"{'='*80}\n")

    # Initialize database
    db = Database()
    conn = db._temp_get_connection()

    # Find articles with short summaries (likely NewsAPI descriptions)
    # NewsAPI descriptions are usually truncated and end with "..."
    cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()

    print("🔍 Searching for articles with short/truncated summaries...")

    query = text("""
        SELECT uri, title, summary, topic, publication_date, analyzed
        FROM articles
        WHERE analyzed = true
          AND publication_date >= :cutoff_date
          AND (
              LENGTH(summary) < 300
              OR summary LIKE '%...'
              OR summary LIKE 'Ten philanthropic foundations are committing%'
              OR summary LIKE 'TORONTO--(BUSINESS WIRE)%'
          )
        ORDER BY publication_date DESC
        LIMIT :limit
    """)

    result = conn.execute(query, {"cutoff_date": cutoff_date, "limit": limit}).mappings()
    articles = [dict(row) for row in result]

    print(f"Found {len(articles)} articles that may need re-analysis\n")

    if len(articles) == 0:
        print("✅ No articles need fixing!")
        return

    # Show preview
    print("Preview of articles to be fixed:")
    print(f"{'='*80}")
    for i, article in enumerate(articles[:5], 1):
        print(f"\n{i}. {article['title'][:60]}...")
        print(f"   URL: {article['uri'][:70]}...")
        print(f"   Current summary: {article['summary'][:100]}...")
        print(f"   Topic: {article['topic']}")
        print(f"   Date: {article['publication_date']}")

    if len(articles) > 5:
        print(f"\n... and {len(articles) - 5} more articles")

    print(f"\n{'='*80}\n")

    if dry_run:
        print("🚫 DRY RUN MODE - No changes will be made")
        print("Run with --fix to actually re-analyze these articles")
        return

    # Confirm before proceeding
    if not auto_yes:
        response = input(f"Do you want to re-analyze these {len(articles)} articles? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return
    else:
        print("Auto-confirmed (--yes flag)")

    # Group articles by topic
    articles_by_topic = {}
    for article in articles:
        topic = article['topic'] or 'Unknown'
        if topic not in articles_by_topic:
            articles_by_topic[topic] = []
        articles_by_topic[topic].append(article['uri'])

    print(f"\n📊 Articles grouped by topic:")
    for topic, urls in articles_by_topic.items():
        print(f"  - {topic}: {len(urls)} articles")

    # Re-analyze articles by topic
    research = Research(db)
    bulk_research = BulkResearch(db, research)

    total_fixed = 0
    total_errors = 0

    for topic, urls in articles_by_topic.items():
        print(f"\n{'='*80}")
        print(f"Processing topic: {topic} ({len(urls)} articles)")
        print(f"{'='*80}\n")

        try:
            # Disable cache to force fresh analysis
            if hasattr(bulk_research, 'article_analyzer') and bulk_research.article_analyzer:
                bulk_research.article_analyzer.use_cache = False
                print(f"🔄 Cache disabled - forcing fresh analysis")

            # Analyze articles
            print(f"🔍 Analyzing {len(urls)} articles...")
            results = await bulk_research.analyze_bulk_urls(
                urls=urls,
                summary_type="curious_ai",
                model_name="gpt-4.1-mini",
                summary_length=50,
                summary_voice="neutral",
                topic=topic
            )

            print(f"✅ Analysis completed for {len(results)} articles")

            # Save results
            print(f"💾 Saving analysis results...")
            save_results = await bulk_research.save_bulk_articles(results)

            if save_results['success']:
                fixed_count = len(save_results['success'])
                total_fixed += fixed_count
                print(f"✅ Successfully updated {fixed_count} articles")

            if save_results['errors']:
                error_count = len(save_results['errors'])
                total_errors += error_count
                print(f"❌ Errors for {error_count} articles:")
                for error in save_results['errors'][:3]:
                    print(f"   - {error['uri'][:60]}...: {error['error']}")
                if len(save_results['errors']) > 3:
                    print(f"   ... and {len(save_results['errors']) - 3} more errors")

        except Exception as e:
            print(f"❌ Error processing topic {topic}: {str(e)}")
            total_errors += len(urls)

    print(f"\n{'='*80}")
    print(f"Summary:")
    print(f"  ✅ Fixed: {total_fixed} articles")
    print(f"  ❌ Errors: {total_errors} articles")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Fix articles with missing AI summaries')
    parser.add_argument('--days', type=int, default=7, help='Number of days back to check (default: 7)')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of articles to fix (default: 100)')
    parser.add_argument('--fix', action='store_true', help='Actually fix the articles (default is dry-run)')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')

    args = parser.parse_args()

    asyncio.run(fix_missing_summaries(
        days_back=args.days,
        limit=args.limit,
        dry_run=not args.fix,
        auto_yes=args.yes
    ))
