"""Add relevance_threshold and articles_enriched to rss_feeds

Revision ID: rss_002
Revises: rss_001
Create Date: 2026-01-12

Adds:
- relevance_threshold column for per-feed relevance filtering
- articles_enriched column for tracking enrichment count
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'rss_002'
down_revision = 'rss_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add relevance_threshold column if it doesn't exist (0 = skip filtering, 1-100 = threshold percentage)
    op.execute("""
        ALTER TABLE rss_feeds
        ADD COLUMN IF NOT EXISTS relevance_threshold INTEGER DEFAULT 0 NOT NULL
    """)

    # Add articles_enriched counter if it doesn't exist
    op.execute("""
        ALTER TABLE rss_feeds
        ADD COLUMN IF NOT EXISTS articles_enriched INTEGER DEFAULT 0 NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('rss_feeds', 'articles_enriched')
    op.drop_column('rss_feeds', 'relevance_threshold')
