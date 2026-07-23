"""Finding-level case states: reviewed/escalated/dismissed with audit trail

bw_finding_reviews: current state per (article, brand). bw_finding_review_log:
append-only audit of every transition (actor from session).

Revision ID: bw_012_finding_reviews
Revises: bw_011_article_risks
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'bw_012_finding_reviews'
down_revision = 'bw_011_article_risks'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_finding_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'new'")),
        sa.Column('actor', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('article_uri', 'brand_id', name='uq_bw_finding_review'),
    )
    op.create_table(
        'bw_finding_review_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.Column('old_status', sa.Text(), nullable=True),
        sa.Column('new_status', sa.Text(), nullable=False),
        sa.Column('actor', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_bw_review_log_uri', 'bw_finding_review_log', ['article_uri'])


def downgrade():
    op.drop_table('bw_finding_review_log')
    op.drop_table('bw_finding_reviews')
