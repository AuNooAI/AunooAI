#!/usr/bin/env python3
"""
Script to clean up invalid future_signal values from the articles table.

This script:
1. Loads topic configurations to get valid future_signals for each topic
2. Finds articles with invalid future_signal values
3. Sets invalid future_signal values to empty string
4. Reports on the cleanup process
"""

import sys
import os
import logging
from collections import defaultdict

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.database import get_database_instance
from app.config.settings import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_topic_valid_signals():
    """Load valid future signals for each topic from config."""
    config = load_config()
    topic_signals = {}

    for topic in config.get('topics', []):
        topic_name = topic.get('name')
        future_signals = topic.get('future_signals', [])
        if topic_name and future_signals:
            topic_signals[topic_name] = set(future_signals)
            logger.info(f"Topic '{topic_name}' has {len(future_signals)} valid signals: {future_signals}")

    return topic_signals


def find_invalid_signals(db):
    """Find all articles with invalid future_signal values."""
    topic_signals = get_topic_valid_signals()

    if not topic_signals:
        logger.error("No topic configurations found!")
        return []

    invalid_articles = []
    stats = defaultdict(lambda: defaultdict(int))

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get all articles with future_signal values
        cursor.execute("""
            SELECT uri, topic, future_signal, title
            FROM articles
            WHERE future_signal IS NOT NULL
              AND future_signal != ''
              AND analyzed = 1
        """)

        articles = cursor.fetchall()
        logger.info(f"Checking {len(articles)} articles with future_signal values...")

        for article in articles:
            uri, topic, future_signal, title = article

            # Check if topic has valid signals defined
            if topic not in topic_signals:
                logger.warning(f"Topic '{topic}' not found in config, skipping article {uri}")
                stats[topic]['unknown_topic'] += 1
                continue

            # Check if the signal is valid for this topic
            if future_signal not in topic_signals[topic]:
                invalid_articles.append({
                    'uri': uri,
                    'topic': topic,
                    'invalid_signal': future_signal,
                    'title': title
                })
                stats[topic][future_signal] += 1

    return invalid_articles, stats


def cleanup_invalid_signals(db, dry_run=True):
    """Clean up invalid future_signal values."""
    invalid_articles, stats = find_invalid_signals(db)

    if not invalid_articles:
        logger.info("No invalid future_signal values found. Database is clean!")
        return

    logger.info(f"\nFound {len(invalid_articles)} articles with invalid future_signal values")

    # Print statistics by topic
    logger.info("\nInvalid signals by topic:")
    for topic, signals in sorted(stats.items()):
        logger.info(f"\n  Topic: {topic}")
        for signal, count in sorted(signals.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"    '{signal}': {count} articles")

    # Show some examples
    logger.info("\nExample invalid articles (first 10):")
    for article in invalid_articles[:10]:
        logger.info(f"  '{article['invalid_signal']}' in topic '{article['topic']}'")
        logger.info(f"    Title: {article['title'][:80] if article['title'] else 'No title'}...")

    if dry_run:
        logger.info(f"\n[DRY RUN] Would clean up {len(invalid_articles)} articles")
        logger.info("Run with --execute flag to perform actual cleanup")
        return

    # Perform cleanup
    logger.info(f"\nCleaning up {len(invalid_articles)} articles...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        article_uris = [article['uri'] for article in invalid_articles]

        # Update in batches of 100
        batch_size = 100
        for i in range(0, len(article_uris), batch_size):
            batch = article_uris[i:i + batch_size]
            placeholders = ','.join('?' * len(batch))

            cursor.execute(f"""
                UPDATE articles
                SET future_signal = '',
                    future_signal_explanation = '[CLEANED: Invalid signal value removed]'
                WHERE uri IN ({placeholders})
            """, batch)

            conn.commit()
            logger.info(f"  Cleaned up batch {i//batch_size + 1} ({len(batch)} articles)")

    logger.info(f"\nCleanup complete! Cleaned {len(invalid_articles)} articles")


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(description='Clean up invalid future_signal values')
    parser.add_argument('--execute', action='store_true',
                       help='Actually perform the cleanup (default is dry-run)')
    args = parser.parse_args()

    try:
        logger.info("Starting future_signal cleanup script...")
        logger.info(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

        db = get_database_instance()
        cleanup_invalid_signals(db, dry_run=not args.execute)

        logger.info("\nScript completed successfully!")

    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()