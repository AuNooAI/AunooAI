"""Add confidence metrics persistence tables

Revision ID: act_003
Revises: act_002
Create Date: 2025-01-30

Stores DeBERTa confidence readings and relevance scoring stats
so they persist across service restarts.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = 'act_003'
down_revision = 'act_002'
branch_labels = None
depends_on = None


def upgrade():
    # Table for DeBERTa enrichment confidence readings
    op.create_table(
        'enrichment_confidence_readings',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('field_name', sa.Text, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # Index for querying by topic and time window
    op.create_index(
        'ix_enrichment_confidence_topic_time',
        'enrichment_confidence_readings',
        ['topic', 'recorded_at']
    )

    # Index for efficient pruning of old records
    op.create_index(
        'ix_enrichment_confidence_time',
        'enrichment_confidence_readings',
        ['recorded_at']
    )

    # Table for relevance scoring confidence readings
    op.create_table(
        'relevance_confidence_readings',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('score', sa.Float, nullable=False),
        sa.Column('classifier_score', sa.Float, nullable=True),
        sa.Column('embedding_score', sa.Float, nullable=True),
        sa.Column('method', sa.Text, nullable=False, server_default='hybrid'),
        sa.Column('relevant', sa.Boolean, nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # Index for querying by topic and time window
    op.create_index(
        'ix_relevance_confidence_topic_time',
        'relevance_confidence_readings',
        ['topic', 'recorded_at']
    )

    # Index for efficient pruning of old records
    op.create_index(
        'ix_relevance_confidence_time',
        'relevance_confidence_readings',
        ['recorded_at']
    )


def downgrade():
    op.drop_index('ix_relevance_confidence_time', table_name='relevance_confidence_readings')
    op.drop_index('ix_relevance_confidence_topic_time', table_name='relevance_confidence_readings')
    op.drop_table('relevance_confidence_readings')

    op.drop_index('ix_enrichment_confidence_time', table_name='enrichment_confidence_readings')
    op.drop_index('ix_enrichment_confidence_topic_time', table_name='enrichment_confidence_readings')
    op.drop_table('enrichment_confidence_readings')
