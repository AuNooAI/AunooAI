"""Add Brand Watcher tables

Revision ID: bw_001
Revises: mc_001
Create Date: 2026-02-06

Multi-brand intelligence tracking: brands, article categories,
narratives, tracker runs, daily stats.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'bw_001'
down_revision = 'mc_001'
branch_labels = None
depends_on = None


def upgrade():
    # bw_brands — user-configured brand entities
    op.create_table(
        'bw_brands',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('brand_keywords', postgresql.JSONB(), nullable=False),
        sa.Column('product_keywords', postgresql.JSONB(), nullable=True),
        sa.Column('people_keywords', postgresql.JSONB(), nullable=True),
        sa.Column('competitor_keywords', postgresql.JSONB(), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # bw_article_categories — multi-label classifications per brand
    op.create_table(
        'bw_article_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('classification_method', sa.Text(), server_default='keyword', nullable=False),
        sa.Column('classified_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('article_uri', 'brand_id', 'category', name='uq_bw_article_brand_category'),
    )
    op.create_index('idx_bw_article_categories_uri', 'bw_article_categories', ['article_uri'])
    op.create_index('idx_bw_article_categories_brand', 'bw_article_categories', ['brand_id'])
    op.create_index('idx_bw_article_categories_category', 'bw_article_categories', ['category'])
    op.create_index('idx_bw_article_categories_method', 'bw_article_categories', ['classification_method'])
    op.create_index('idx_bw_article_categories_at', 'bw_article_categories', ['classified_at'])

    # bw_tracker_narratives — per-brand AI insight reports
    op.create_table(
        'bw_tracker_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('data_summary', postgresql.JSONB(), nullable=True),
        sa.Column('days_back', sa.Integer(), nullable=True),
        sa.Column('date_range_start', sa.Date(), nullable=True),
        sa.Column('date_range_end', sa.Date(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_bw_narratives_brand', 'bw_tracker_narratives', ['brand_id'])
    op.create_index('idx_bw_narratives_at', 'bw_tracker_narratives', ['generated_at'])

    # bw_tracker_runs — classification run tracking
    op.create_table(
        'bw_tracker_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='SET NULL'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('articles_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('articles_categorized', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.Text(), server_default='running', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_type', sa.Text(), server_default='incremental', nullable=False),
    )
    op.create_index('idx_bw_runs_brand', 'bw_tracker_runs', ['brand_id'])
    op.create_index('idx_bw_runs_started', 'bw_tracker_runs', ['started_at'])

    # bw_daily_stats — daily aggregated stats per brand + category
    op.create_table(
        'bw_daily_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('article_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('date', 'brand_id', 'category', name='uq_bw_daily_stats'),
    )
    op.create_index('idx_bw_daily_stats_date', 'bw_daily_stats', ['date'])
    op.create_index('idx_bw_daily_stats_brand', 'bw_daily_stats', ['brand_id'])


def downgrade():
    op.drop_table('bw_daily_stats')
    op.drop_table('bw_tracker_runs')
    op.drop_table('bw_tracker_narratives')
    op.drop_table('bw_article_categories')
    op.drop_table('bw_brands')
