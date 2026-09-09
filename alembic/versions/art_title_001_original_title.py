"""English headline for non-English articles: keep the original alongside.

The analysis step writes the summary in English whatever the article's
language, but the headline stayed as collected. ``title`` now holds the
English headline when the collected one was not English, and the collected
one moves to ``original_title``. NULL means the title was already English.

This branches off mcp_001, the last revision every customer site has applied,
so it can run on them without the market-monitor chain (mm_023..mm_025) that
only the canonical site carries. ``merge_art_title_mm`` joins the two heads.

Revision ID: art_title_001
Revises: mcp_001
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'art_title_001'
down_revision = 'mcp_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('original_title', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('articles', 'original_title')
