"""Backfill articles.social_meta on tenants that never got bw_006.

The alembic graphs diverge per tenant: wileytest gained social_meta via
bw_006_social_meta, but on tenants whose chain skips bw_006/bw_007 (bugfixing:
opoint_001 -> bw_008) the column never landed — while the shared Brand Watcher
code (adverse alert rules, social endpoints) reads it, so the alert evaluator
died on every cycle. ADD COLUMN IF NOT EXISTS makes this a no-op where bw_006
already ran, so the same file applies everywhere and keeps heads aligned.

Revision ID: bw_016_backfill_social_meta
Revises: bw_015_article_signals
Create Date: 2026-07-04
"""
from alembic import op

revision = 'bw_016_backfill_social_meta'
down_revision = 'bw_015_article_signals'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS social_meta JSONB")


def downgrade():
    # No-op: on bw_006 tenants the column belongs to that revision; dropping it
    # here would corrupt their history.
    pass
