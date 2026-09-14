"""Per-group collection language and country on keyword_groups.

Scheduled collection passed one tenant-wide language to every collector, so a
Japanese or German topic asked TheNewsAPI and NewsData for English articles and
got nothing. NULL keeps the old behaviour (tenant setting, no country filter).

Revision ID: kg_lang_001
Revises: mm_022
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'kg_lang_001'
down_revision = 'mm_022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('keyword_groups', sa.Column('language', sa.Text(), nullable=True))
    op.add_column('keyword_groups', sa.Column('country', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('keyword_groups', 'country')
    op.drop_column('keyword_groups', 'language')
