"""add_analysis_run_logs_tables

Revision ID: 8f65d368bbd0
Revises: 5d62bf1a46ec
Create Date: 2025-11-05 14:02:19.593395

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f65d368bbd0'
down_revision: Union[str, None] = '5d62bf1a46ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create analysis_run_logs table
    op.create_table(
        'analysis_run_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('analysis_type', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('articles_analyzed', sa.Integer(), nullable=True),
        sa.Column('timeframe_days', sa.Integer(), nullable=True),
        sa.Column('consistency_mode', sa.Text(), nullable=True),
        sa.Column('profile_id', sa.Integer(), nullable=True),
        sa.Column('persona', sa.Text(), nullable=True),
        sa.Column('customer_type', sa.Text(), nullable=True),
        sa.Column('cache_key', sa.Text(), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('started_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True, server_default=sa.text("'running'")),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id')
    )

    # Create indexes for analysis_run_logs
    op.create_index('idx_analysis_run_logs_type', 'analysis_run_logs', ['analysis_type'])
    op.create_index('idx_analysis_run_logs_topic', 'analysis_run_logs', ['topic'])
    op.create_index('idx_analysis_run_logs_started', 'analysis_run_logs', ['started_at'])
    op.create_index('idx_analysis_run_logs_run_id', 'analysis_run_logs', ['run_id'])

    # Create analysis_run_articles table
    op.create_table(
        'analysis_run_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('article_title', sa.Text(), nullable=True),
        sa.Column('article_source', sa.Text(), nullable=True),
        sa.Column('published_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('sentiment', sa.Text(), nullable=True),
        sa.Column('relevance_score', sa.REAL(), nullable=True),
        sa.Column('included_in_prompt', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('article_position', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_run_logs.run_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['article_uri'], ['articles.uri'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for analysis_run_articles
    op.create_index('idx_analysis_run_articles_run_id', 'analysis_run_articles', ['run_id'])
    op.create_index('idx_analysis_run_articles_uri', 'analysis_run_articles', ['article_uri'])
    op.create_index('idx_analysis_run_articles_created', 'analysis_run_articles', ['created_at'])


def downgrade() -> None:
    # Drop tables and indexes
    op.drop_index('idx_analysis_run_articles_created', table_name='analysis_run_articles')
    op.drop_index('idx_analysis_run_articles_uri', table_name='analysis_run_articles')
    op.drop_index('idx_analysis_run_articles_run_id', table_name='analysis_run_articles')
    op.drop_table('analysis_run_articles')

    op.drop_index('idx_analysis_run_logs_run_id', table_name='analysis_run_logs')
    op.drop_index('idx_analysis_run_logs_started', table_name='analysis_run_logs')
    op.drop_index('idx_analysis_run_logs_topic', table_name='analysis_run_logs')
    op.drop_index('idx_analysis_run_logs_type', table_name='analysis_run_logs')
    op.drop_table('analysis_run_logs')
