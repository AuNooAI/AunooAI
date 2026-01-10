"""Add trend tracking tables for emerging topics

Revision ID: et_003
Revises: et_002
Create Date: 2026-01-09

Adds:
- detection_runs table to track each scan execution
- topic_history table to store snapshots of topic metrics per run
- Temporal tracking columns on emerging_topics table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'et_003'
down_revision = 'et_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create detection_runs table
    op.create_table(
        'detection_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_date', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('topic_filter', sa.String(255), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=True),
        sa.Column('topics_detected', sa.Integer(), server_default='0'),
        sa.Column('articles_sampled', sa.Integer(), server_default='0'),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), server_default='completed'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )

    op.create_index('idx_detection_runs_date', 'detection_runs', ['run_date'])
    op.create_index('idx_detection_runs_topic_filter', 'detection_runs', ['topic_filter'])

    # Create topic_history table
    op.create_table(
        'topic_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('emerging_topics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('detection_run_id', sa.Integer(), sa.ForeignKey('detection_runs.id', ondelete='CASCADE'), nullable=False),

        # Snapshot of metrics
        sa.Column('article_count', sa.Integer()),
        sa.Column('growth_rate', sa.Float()),
        sa.Column('velocity', sa.String(20)),
        sa.Column('confidence_score', sa.Float()),

        # Trend scores
        sa.Column('volume_score', sa.Float()),
        sa.Column('velocity_score', sa.Float()),
        sa.Column('diversity_score', sa.Float()),
        sa.Column('novelty_score', sa.Float()),
        sa.Column('composite_score', sa.Float()),
        sa.Column('source_count', sa.Integer()),

        # Full analysis snapshot (optional)
        sa.Column('actors', postgresql.JSONB()),
        sa.Column('events', postgresql.JSONB()),
        sa.Column('synthesis', postgresql.JSONB()),

        sa.Column('captured_at', sa.DateTime(), server_default=sa.text('NOW()')),

        sa.UniqueConstraint('topic_id', 'detection_run_id', name='uq_topic_history_topic_run'),
    )

    op.create_index('idx_topic_history_topic', 'topic_history', ['topic_id'])
    op.create_index('idx_topic_history_run', 'topic_history', ['detection_run_id'])

    # Add temporal tracking columns to emerging_topics
    op.add_column('emerging_topics', sa.Column('first_detection_date', sa.Date(), nullable=True))
    op.add_column('emerging_topics', sa.Column('last_detection_date', sa.Date(), nullable=True))
    op.add_column('emerging_topics', sa.Column('detection_count', sa.Integer(), server_default='1'))
    op.add_column('emerging_topics', sa.Column('consecutive_detections', sa.Integer(), server_default='1'))
    op.add_column('emerging_topics', sa.Column('missed_runs', sa.Integer(), server_default='0'))

    # Populate temporal fields for existing topics
    op.execute("""
        UPDATE emerging_topics
        SET first_detection_date = COALESCE(detection_date::date, created_at::date),
            last_detection_date = COALESCE(detection_date::date, created_at::date),
            detection_count = 1,
            consecutive_detections = 1,
            missed_runs = 0
        WHERE first_detection_date IS NULL
    """)


def downgrade() -> None:
    # Remove temporal tracking columns
    op.drop_column('emerging_topics', 'missed_runs')
    op.drop_column('emerging_topics', 'consecutive_detections')
    op.drop_column('emerging_topics', 'detection_count')
    op.drop_column('emerging_topics', 'last_detection_date')
    op.drop_column('emerging_topics', 'first_detection_date')

    # Drop tables
    op.drop_table('topic_history')
    op.drop_table('detection_runs')
