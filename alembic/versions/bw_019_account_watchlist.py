"""Watchlist flag on account profiles.

Revision ID: bw_019_account_watchlist
Revises: bw_018_social_accounts_backfill
"""

from alembic import op

revision = 'bw_019_account_watchlist'
down_revision = 'bw_018_social_accounts_backfill'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE social_accounts "
               "ADD COLUMN IF NOT EXISTS watchlisted BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE social_accounts DROP COLUMN IF EXISTS watchlisted")
