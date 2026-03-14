"""Add science funding tracker tables

Revision ID: sf_001
Revises: pt_005
Create Date: 2026-02-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'sf_001'
down_revision = 'pt_005'
branch_labels = None
depends_on = None


def upgrade():
    # Create science_article_categories table - stores article categorizations
    op.create_table(
        'science_article_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('classified_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('classification_method', sa.Text(), server_default='keyword', nullable=False),
        sa.UniqueConstraint('article_uri', 'category', name='uq_science_article_category')
    )
    op.create_index('idx_science_article_categories_uri', 'science_article_categories', ['article_uri'])
    op.create_index('idx_science_article_categories_category', 'science_article_categories', ['category'])
    op.create_index('idx_science_article_categories_topic', 'science_article_categories', ['topic'])
    op.create_index('idx_science_article_categories_classified_at', 'science_article_categories', ['classified_at'])

    # Create science_category_daily_stats table
    op.create_table(
        'science_category_daily_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('article_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_articles_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('date', 'topic', 'category', name='uq_science_daily_stats')
    )
    op.create_index('idx_science_daily_stats_date', 'science_category_daily_stats', ['date'])
    op.create_index('idx_science_daily_stats_topic', 'science_category_daily_stats', ['topic'])
    op.create_index('idx_science_daily_stats_category', 'science_category_daily_stats', ['category'])

    # Create science_tracker_narratives table
    op.create_table(
        'science_tracker_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('data_summary', postgresql.JSONB(), nullable=True),
        sa.Column('days_back', sa.Integer(), nullable=True),
        sa.Column('date_range_start', sa.Date(), nullable=True),
        sa.Column('date_range_end', sa.Date(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_science_tracker_narratives_topic', 'science_tracker_narratives', ['topic'])
    op.create_index('idx_science_tracker_narratives_generated_at', 'science_tracker_narratives', ['generated_at'])

    # Create science_tracker_imports table
    op.create_table(
        'science_tracker_imports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('import_type', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('filename', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default='pending', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rows_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('articles_created', sa.Integer(), server_default='0', nullable=False),
        sa.Column('articles_updated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('categories_added', sa.Integer(), server_default='0', nullable=False),
        sa.Column('errors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_llm_classification', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('narrative_id', sa.Integer(), sa.ForeignKey('science_tracker_narratives.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('idx_science_tracker_imports_topic', 'science_tracker_imports', ['topic'])
    op.create_index('idx_science_tracker_imports_status', 'science_tracker_imports', ['status'])
    op.create_index('idx_science_tracker_imports_started_at', 'science_tracker_imports', ['started_at'])

    # Create science_tracker_runs table - tracks classification runs
    op.create_table(
        'science_tracker_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('articles_processed', sa.Integer(), nullable=True),
        sa.Column('articles_categorized', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), server_default='running', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_type', sa.Text(), server_default='incremental', nullable=False),
    )
    op.create_index('idx_science_tracker_runs_topic', 'science_tracker_runs', ['topic'])
    op.create_index('idx_science_tracker_runs_started_at', 'science_tracker_runs', ['started_at'])


def downgrade():
    op.drop_table('science_tracker_runs')
    op.drop_table('science_tracker_imports')
    op.drop_table('science_tracker_narratives')
    op.drop_table('science_category_daily_stats')
    op.drop_table('science_article_categories')
