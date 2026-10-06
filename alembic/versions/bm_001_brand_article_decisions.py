"""brand_article_decisions: brand decisions for Market Monitor vendor links

docs/BRAND_RELEVANCE_MARKET_VENDORS.md: when a Market Monitor's name match
finds a vendor in an article, the brand decision runs and only an earned
decision writes the vendor link. Every decision, kept or not, is stored here,
one row per article and vendor. Brand-topic decisions stay on
keyword_article_matches, which is scoped per keyword group; a market group
covers many vendors, so it cannot hold one label per vendor.

``outcome``           decided, unavailable or deferred
``brand_relation``    subject, notable, sector, passing or other (NULL unless decided)
``source_relation``   owned, independent or unknown, relative to this vendor
``judge_version``     the input key the decision was made under, for reuse
``decision_evidence`` JSON: the same evidence brand-topic decisions carry
``last_failure``      JSON: the latest failed attempt and the attempt count
``linked``            whether the vendor link was written for this decision

Every step checks first, so the migration is safe to run again.

Revision ID: bm_001
Revises: br_001
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = 'bm_001'
down_revision = 'br_001'
branch_labels = None
depends_on = None

TABLE = 'brand_article_decisions'


def upgrade():
    insp = inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text, nullable=False),
        sa.Column('brand_id', sa.Integer, nullable=False),
        sa.Column('market_id', sa.Integer, nullable=True),
        sa.Column('outcome', sa.Text, nullable=False),
        sa.Column('brand_relation', sa.Text, nullable=True),
        sa.Column('source_relation', sa.Text, nullable=True),
        sa.Column('judge_version', sa.Text, nullable=True),
        sa.Column('decision_evidence', postgresql.JSONB, nullable=True),
        sa.Column('last_failure', postgresql.JSONB, nullable=True),
        sa.Column('linked', sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('article_uri', 'brand_id', name='uq_brand_article_decisions_pair'),
    )
    op.create_index('idx_bad_brand_outcome', TABLE, ['brand_id', 'outcome'])
    op.create_index('idx_bad_judge_version', TABLE, ['article_uri', 'judge_version'])


def downgrade():
    insp = inspect(op.get_bind())
    if TABLE in insp.get_table_names():
        op.drop_table(TABLE)
