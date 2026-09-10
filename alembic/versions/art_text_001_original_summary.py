"""articles.original_summary: the collected text when `summary` is its English translation

Companion to art_title_001. Social posts carry the post itself in `summary`,
and news the relevance gate rejected keeps the collector's description there;
neither goes through the analysis step, so on a Japanese customer site most of
the feed stayed Japanese under an English headline. The first insert now
translates the summary too and keeps the original here.

Branches off art_title_001, which every customer site has applied; the
canonical tree merges it with its own head in mm_027.

Revision ID: art_text_001
Revises: art_title_001
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'art_text_001'
down_revision = 'art_title_001'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('articles', 'original_summary'):
        op.add_column('articles', sa.Column('original_summary', sa.Text(), nullable=True))


def downgrade():
    if _has_column('articles', 'original_summary'):
        op.drop_column('articles', 'original_summary')
