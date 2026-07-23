"""Adverse risk taxonomy: per-article-per-brand risk findings

Cross-cutting risk dimension (orthogonal to the 11 'what is it about' categories,
so the DeBERTa classifier needs no retrain): legal_regulatory, financial_distress,
fraud_integrity, esg, executive_misconduct, data_breach.

Revision ID: bw_011_article_risks
Revises: bw_010_alerting
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'bw_011_article_risks'
down_revision = 'bw_010_alerting'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_article_risks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('risk_type', sa.Text(), nullable=False),
        sa.Column('severity', sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('method', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('article_uri', 'brand_id', 'risk_type', name='uq_bw_risk_article_brand_type'),
    )
    op.create_index('idx_bw_risks_brand', 'bw_article_risks', ['brand_id'])
    op.create_index('idx_bw_risks_uri', 'bw_article_risks', ['article_uri'])


def downgrade():
    op.drop_table('bw_article_risks')
