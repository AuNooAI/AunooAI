"""keyword_article_matches: the relevance verdict per (article, topic)

One article row carries one topic and one topic_alignment_score, but the
ingest scores an article once for every group whose keywords matched it.
Until now the last pipeline to approve the article overwrote the row's
score without moving the topic, so a row filed under "U.S. Federal R&D
Pullback" could carry the 0.9 that "AI and Machine Learning" earned.

The match row is the (article, group) pair, so the verdict for that topic
lives there: score, status and when it was scored. The row-level score is
now moved together with the topic (see async_db.update_article_with_enrichment).

Branches off voice_001, which every customer site has applied.

Revision ID: rel_001
Revises: voice_001
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'rel_001'
down_revision = 'voice_001'
branch_labels = None
depends_on = None


def _columns():
    return {c['name'] for c in inspect(op.get_bind()).get_columns('keyword_article_matches')}


def upgrade():
    cols = _columns()
    if 'topic_alignment_score' not in cols:
        op.add_column('keyword_article_matches', sa.Column('topic_alignment_score', sa.Float(), nullable=True))
    if 'relevance_status' not in cols:
        op.add_column('keyword_article_matches', sa.Column('relevance_status', sa.String(32), nullable=True))
    if 'scored_at' not in cols:
        op.add_column('keyword_article_matches', sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    cols = _columns()
    for c in ('scored_at', 'relevance_status', 'topic_alignment_score'):
        if c in cols:
            op.drop_column('keyword_article_matches', c)
