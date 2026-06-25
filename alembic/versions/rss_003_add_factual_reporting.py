"""Add default_factual_reporting to rss_feeds

Revision ID: rss_003
Revises: rss_002
Create Date: 2026-01-13

Adds:
- default_factual_reporting column for setting source credibility on RSS articles
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'rss_003'
down_revision = 'rss_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add default_factual_reporting column if it doesn't exist
    # Valid values: NULL (don't set), 'very high', 'high', 'mostly factual', 'mixed', 'low', 'very low'
    op.execute("""
        ALTER TABLE rss_feeds
        ADD COLUMN IF NOT EXISTS default_factual_reporting VARCHAR(50) DEFAULT NULL
    """)


def downgrade() -> None:
    op.drop_column('rss_feeds', 'default_factual_reporting')
