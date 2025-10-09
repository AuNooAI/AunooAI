#!/usr/bin/env python3
"""
Delete all articles that don't have any relevance scores.
This removes articles where all three score fields are NULL:
- topic_alignment_score
- keyword_relevance_score
- confidence_score
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import Database
from sqlalchemy import select, and_
from app.database_models import t_articles
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Delete articles without relevance scores')
    parser.add_argument('--confirm', action='store_true', help='Confirm deletion without prompting')
    args = parser.parse_args()

    logger.info("Starting deletion of articles without relevance scores")

    # Initialize database
    db = Database()

    # Get connection
    conn = db._temp_get_connection()

    # Query for articles without any relevance scores
    stmt = select(t_articles.c.uri).where(
        and_(
            t_articles.c.topic_alignment_score.is_(None),
            t_articles.c.keyword_relevance_score.is_(None),
            t_articles.c.confidence_score.is_(None)
        )
    )

    result = conn.execute(stmt)
    uris_to_delete = [row[0] for row in result.fetchall()]

    logger.info(f"Found {len(uris_to_delete)} articles without relevance scores")

    if not uris_to_delete:
        logger.info("No articles to delete")
        return

    # Show first few URIs as confirmation
    logger.info(f"First 5 URIs to delete: {uris_to_delete[:5]}")

    # Confirm deletion
    if not args.confirm:
        try:
            response = input(f"\nAbout to delete {len(uris_to_delete)} articles. Continue? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("Deletion cancelled by user")
                return
        except EOFError:
            logger.error("Cannot prompt for confirmation in non-interactive mode. Use --confirm flag.")
            return

    # Delete articles in batches
    BATCH_SIZE = 50
    total_deleted = 0

    # Get connection for manual commit
    conn = db._temp_get_connection()

    for i in range(0, len(uris_to_delete), BATCH_SIZE):
        batch = uris_to_delete[i:i + BATCH_SIZE]
        logger.info(f"Deleting batch {i // BATCH_SIZE + 1} ({len(batch)} articles)")

        try:
            deleted_count = db.bulk_delete_articles(batch)
            total_deleted += deleted_count
            logger.info(f"Batch deleted: {deleted_count} articles")
        except Exception as e:
            logger.error(f"Error deleting batch: {e}")
            # Continue with next batch

    # Explicitly commit the connection's transaction
    try:
        conn.commit()
        logger.info("Main transaction committed")
    except Exception as e:
        logger.error(f"Error committing main transaction: {e}")

    logger.info(f"✅ Deletion complete. Total articles deleted: {total_deleted}")

    # Verify deletion
    verify_stmt = select(t_articles.c.uri).where(
        and_(
            t_articles.c.topic_alignment_score.is_(None),
            t_articles.c.keyword_relevance_score.is_(None),
            t_articles.c.confidence_score.is_(None)
        )
    )

    verify_result = conn.execute(verify_stmt)
    remaining = len(verify_result.fetchall())

    if remaining == 0:
        logger.info("✅ All articles without relevance scores have been deleted")
    else:
        logger.warning(f"⚠️ {remaining} articles without relevance scores still remain")


if __name__ == "__main__":
    main()
