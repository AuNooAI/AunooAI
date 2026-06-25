"""Add adaptive classification training tables

Revision ID: act_001
Revises: dr_002
Create Date: 2026-02-01

Tables:
- enrichment_training_samples: Stores training samples from LLM bootstrap
- training_sample_counts: Aggregated counts for fast queries
- training_runs: Tracks finetuning runs and model deployments
- Adds enrichment_sources JSONB column to articles table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'act_001'
down_revision = 'dr_002'
branch_labels = None
depends_on = None


def upgrade():
    # Create enrichment_training_samples table
    op.create_table(
        'enrichment_training_samples',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('article_uri', sa.Text, sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('field_name', sa.Text, nullable=False),  # 'sentiment', 'time_to_impact', etc.
        sa.Column('field_value', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=False),  # 'llm_bootstrap', 'human_verified'
        sa.Column('model_used', sa.Text),  # 'gpt-4o-mini'
        sa.Column('confidence', sa.Float),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('article_uri', 'field_name', name='uq_training_sample_article_field')
    )
    op.create_index('idx_training_samples_topic', 'enrichment_training_samples', ['topic'])
    op.create_index('idx_training_samples_field', 'enrichment_training_samples', ['field_name'])
    op.create_index('idx_training_samples_source', 'enrichment_training_samples', ['source'])
    op.create_index('idx_training_samples_topic_field', 'enrichment_training_samples', ['topic', 'field_name'])

    # Create training_sample_counts table (aggregated for fast queries)
    op.create_table(
        'training_sample_counts',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('field_name', sa.Text, nullable=False),
        sa.Column('field_value', sa.Text, nullable=False),
        sa.Column('sample_count', sa.Integer, nullable=False, server_default=sa.text('0')),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('topic', 'field_name', 'field_value', name='uq_sample_counts_topic_field_value')
    )
    op.create_index('idx_sample_counts_topic', 'training_sample_counts', ['topic'])
    op.create_index('idx_sample_counts_field', 'training_sample_counts', ['field_name'])
    op.create_index('idx_sample_counts_topic_field', 'training_sample_counts', ['topic', 'field_name'])

    # Create training_runs table
    op.create_table(
        'training_runs',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Text, nullable=False, unique=True),
        sa.Column('status', sa.Text, nullable=False, server_default=sa.text("'pending'")),  # pending, running, completed, failed
        sa.Column('topics_included', JSONB),
        sa.Column('fields_included', JSONB),
        sa.Column('sample_count', sa.Integer),
        sa.Column('metrics', JSONB),  # accuracy, f1, etc.
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('model_path', sa.Text),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False)
    )
    op.create_index('idx_training_runs_status', 'training_runs', ['status'])
    op.create_index('idx_training_runs_created', 'training_runs', ['created_at'])

    # Add enrichment_sources column to articles table
    op.add_column(
        'articles',
        sa.Column('enrichment_sources', JSONB, server_default=sa.text("'{}'"), nullable=True)
    )


def downgrade():
    # Remove enrichment_sources column from articles
    op.drop_column('articles', 'enrichment_sources')

    # Drop training_runs table
    op.drop_index('idx_training_runs_created', table_name='training_runs')
    op.drop_index('idx_training_runs_status', table_name='training_runs')
    op.drop_table('training_runs')

    # Drop training_sample_counts table
    op.drop_index('idx_sample_counts_topic_field', table_name='training_sample_counts')
    op.drop_index('idx_sample_counts_field', table_name='training_sample_counts')
    op.drop_index('idx_sample_counts_topic', table_name='training_sample_counts')
    op.drop_table('training_sample_counts')

    # Drop enrichment_training_samples table
    op.drop_index('idx_training_samples_topic_field', table_name='enrichment_training_samples')
    op.drop_index('idx_training_samples_source', table_name='enrichment_training_samples')
    op.drop_index('idx_training_samples_field', table_name='enrichment_training_samples')
    op.drop_index('idx_training_samples_topic', table_name='enrichment_training_samples')
    op.drop_table('enrichment_training_samples')
