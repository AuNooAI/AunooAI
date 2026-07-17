"""Add per-group social platform selection to keyword_groups.

NULL means "use the XPOZ_PLATFORMS env default"; otherwise a JSON array of
platform names, e.g. '["twitter", "reddit"]'.

Revision ID: kg_social_01
Revises: llm_usage_01
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'kg_social_01'
down_revision = 'llm_usage_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('keyword_groups',
                  sa.Column('social_platforms', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('keyword_groups', 'social_platforms')
