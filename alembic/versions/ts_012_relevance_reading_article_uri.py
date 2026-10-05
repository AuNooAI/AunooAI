"""relevance_confidence_readings.article_uri — trace a reading back to its article

Revision ID: ts_012
Revises: ts_011
Create Date: 2026-09-20

The readings table had no article reference, so only 28 of 165 Jev
disagreements could be joined back to an article for labelling (by matching
embedding_score to keyword_relevance_score). The ingest path knows the uri
when it records the reading; this column stores it. Nullable, because other
callers (the DeBERTa-only paths) record without an article.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_012'
down_revision = 'ts_011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('relevance_confidence_readings', sa.Column('article_uri', sa.Text(), nullable=True))
    op.create_index('ix_relevance_readings_article_uri', 'relevance_confidence_readings', ['article_uri'])


def downgrade() -> None:
    op.drop_index('ix_relevance_readings_article_uri', table_name='relevance_confidence_readings')
    op.drop_column('relevance_confidence_readings', 'article_uri')
