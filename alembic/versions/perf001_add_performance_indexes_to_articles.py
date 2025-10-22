"""add_performance_indexes_to_articles

Revision ID: perf001
Revises: e0aa2eb4fa0a
Create Date: 2025-10-22 10:00:00.000000

Adds critical performance indexes on frequently queried columns in the articles table.

Missing indexes were causing full table scans on every date range and topic query.
These indexes will dramatically improve query performance, especially for:
- Date range queries (publication_date)
- Topic filtering (topic)
- Category filtering (category)
- Sentiment filtering (sentiment)
- Combined date + category queries (composite index)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'perf001'
down_revision: Union[str, None] = 'e0aa2eb4fa0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes on articles table."""

    # Add index on publication_date - heavily queried for date ranges
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_publication_date
        ON articles (publication_date)
    """)

    # Add index on topic - heavily queried for topic filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_topic
        ON articles (topic)
    """)

    # Add index on category - queried for category filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_category
        ON articles (category)
    """)

    # Add index on sentiment - queried for sentiment filtering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_sentiment
        ON articles (sentiment)
    """)

    # Add composite index on (publication_date, category) for common combined queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_articles_pubdate_category
        ON articles (publication_date, category)
    """)

    # Add comments to document the indexes
    op.execute("""
        COMMENT ON INDEX idx_articles_publication_date IS
        'Index for fast date range queries on articles'
    """)

    op.execute("""
        COMMENT ON INDEX idx_articles_topic IS
        'Index for fast topic filtering on articles'
    """)

    op.execute("""
        COMMENT ON INDEX idx_articles_category IS
        'Index for fast category filtering on articles'
    """)

    op.execute("""
        COMMENT ON INDEX idx_articles_sentiment IS
        'Index for fast sentiment filtering on articles'
    """)

    op.execute("""
        COMMENT ON INDEX idx_articles_pubdate_category IS
        'Composite index for date range + category queries (common in news feed)'
    """)


def downgrade() -> None:
    """Remove performance indexes."""
    op.execute('DROP INDEX IF EXISTS idx_articles_publication_date')
    op.execute('DROP INDEX IF EXISTS idx_articles_topic')
    op.execute('DROP INDEX IF EXISTS idx_articles_category')
    op.execute('DROP INDEX IF EXISTS idx_articles_sentiment')
    op.execute('DROP INDEX IF EXISTS idx_articles_pubdate_category')
