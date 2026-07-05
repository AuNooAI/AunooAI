"""Cross-network propagation payload on Five Signals rows.

The saas reach engine traces Bluesky only. ``xnet`` holds the other-network
pickup gathered by the monolith itself: a free match over the tenant's own
xpoz-collected corpus plus an optional live xpoz query (Twitter/X, Reddit,
TikTok, Instagram) by article URL + headline. Kept separate from ``reach`` so
a fresh Bluesky run never clobbers cross-network data and vice versa.

Revision ID: bw_017_signals_xnet
Revises: bw_016_backfill_social_meta
Create Date: 2026-07-05
"""
from alembic import op

revision = 'bw_017_signals_xnet'
down_revision = 'bw_016_backfill_social_meta'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE bw_article_signals ADD COLUMN IF NOT EXISTS xnet JSONB")


def downgrade():
    op.execute("ALTER TABLE bw_article_signals DROP COLUMN IF EXISTS xnet")
