"""Backfill articles.embedding_model + forecast_topic_metadata.source_topics.

Cross-tenant parity in the bw_016 style: these columns landed on most tenants
via other branch lineages (source_topics via fa_011; embedding_model outside
the tracked chain), but wiley's alembic history only walks the
opoint_001 -> bw_0xx branch, so it never received them — while shared code
(keyword_monitor source_topics, embedding bookkeeping) reads both. ADD COLUMN
IF NOT EXISTS makes this a no-op everywhere the columns already exist, so the
same file applies on all tenants and keeps heads aligned.

Revision ID: bw_021_backfill_embedding_meta
Revises: bw_020_incident_attachments
Create Date: 2026-07-14
"""
from alembic import op

revision = 'bw_021_backfill_embedding_meta'
down_revision = 'bw_020_incident_attachments'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(64)")
    op.execute("ALTER TABLE forecast_topic_metadata ADD COLUMN IF NOT EXISTS source_topics JSONB")


def downgrade():
    # No-op: on tenants where these columns belong to fa_011 / their original
    # revisions, dropping them here would corrupt that history.
    pass
