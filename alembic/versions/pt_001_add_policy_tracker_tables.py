"""Add policy tracker tables for persistent category tracking

Revision ID: pt_001
Revises: rss_003
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'pt_001'
down_revision = ('nf_004', 'article_preference_001', 'auspex_snippets_001')  # Merge multiple heads
branch_labels = None
depends_on = None


def upgrade():
    # Create policy_article_categories table - stores article categorizations
    op.create_table(
        'policy_article_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),  # For future AI-based classification
        sa.Column('classified_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('classification_method', sa.Text(), server_default='keyword', nullable=False),  # keyword, ai, manual
        sa.UniqueConstraint('article_uri', 'category', name='uq_policy_article_category')
    )
    op.create_index('idx_policy_article_categories_uri', 'policy_article_categories', ['article_uri'])
    op.create_index('idx_policy_article_categories_category', 'policy_article_categories', ['category'])
    op.create_index('idx_policy_article_categories_topic', 'policy_article_categories', ['topic'])
    op.create_index('idx_policy_article_categories_classified_at', 'policy_article_categories', ['classified_at'])

    # Create policy_category_daily_stats table - tracks daily category counts for trend analysis
    op.create_table(
        'policy_category_daily_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_articles_count', sa.Integer(), nullable=False, server_default='0'),  # Articles added that day
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('date', 'topic', 'category', name='uq_policy_daily_stats')
    )
    op.create_index('idx_policy_daily_stats_date', 'policy_category_daily_stats', ['date'])
    op.create_index('idx_policy_daily_stats_topic', 'policy_category_daily_stats', ['topic'])
    op.create_index('idx_policy_daily_stats_category', 'policy_category_daily_stats', ['category'])

    # Create policy_tracker_runs table - tracks classification runs
    op.create_table(
        'policy_tracker_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('articles_processed', sa.Integer(), nullable=True),
        sa.Column('articles_categorized', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), server_default='running', nullable=False),  # running, completed, failed
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_type', sa.Text(), server_default='incremental', nullable=False),  # full, incremental
    )
    op.create_index('idx_policy_tracker_runs_topic', 'policy_tracker_runs', ['topic'])
    op.create_index('idx_policy_tracker_runs_started_at', 'policy_tracker_runs', ['started_at'])


def downgrade():
    op.drop_table('policy_tracker_runs')
    op.drop_table('policy_category_daily_stats')
    op.drop_table('policy_article_categories')
