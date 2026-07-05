"""Five Signals article screening results.

One row per (article, brand): the composed five-signal screen (claim
veracity, source credibility, corroboration, propagation, amplification
integrity) built from saas.aunoo.ai's claim-validation and story-reach
engines, plus trimmed copies of both raw payloads for the detail panel.
Status tracks the background run (running/completed/failed) so the UI can
poll the row itself — no separate run table.

Revision ID: bw_015_article_signals
Revises: bw_014_glassdoor_snapshots
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'bw_015_article_signals'
down_revision = 'bw_014_glassdoor_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_article_signals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='running'),
        sa.Column('signals', JSONB(), nullable=True),
        sa.Column('verdict', sa.Text(), nullable=True),
        sa.Column('composite_score', sa.Float(), nullable=True),
        sa.Column('validation', JSONB(), nullable=True),
        sa.Column('reach', JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('article_uri', 'brand_id', name='uq_bw_signals_article_brand'),
    )
    op.create_index('idx_bw_signals_brand', 'bw_article_signals', ['brand_id'])
    op.create_index('idx_bw_signals_uri', 'bw_article_signals', ['article_uri'])


def downgrade():
    op.drop_table('bw_article_signals')
