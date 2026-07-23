"""bw_article_categories.relevance_score — per-brand relevance

The global articles.topic_alignment_score is computed against the article's
OWNING topic, so brand-relevant articles collected under other topics (e.g. the
Courant/Wiley story owned by "Scientific Publishers - General Monitoring") were
hidden by Brand Watcher's >=0.4 display filter. This column stores relevance
judged against the BRAND itself, written at classification time.

NOTE: down_revision differs per tenant (alembic graphs diverge) — this file is
anchored to bugfixing's head (opoint_001); wileytest's copy revises
bw_007_social_accounts.

Revision ID: bw_008_brand_relevance
Revises: opoint_001
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'bw_008_brand_relevance'
down_revision = 'opoint_001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bw_article_categories', sa.Column('relevance_score', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('bw_article_categories', 'relevance_score')
