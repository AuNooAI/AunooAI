"""Add policy tracker scheduling table

Revision ID: pt_004
Revises: add_inference_mode
Create Date: 2026-02-03

Adds a table for scheduling automatic policy tracker classification.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'pt_004'
down_revision: str = 'add_inference_mode'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create policy_tracker_schedules table
    op.create_table(
        'policy_tracker_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('topic', sa.String(255), nullable=True),  # Topic to classify

        # Processing configuration
        sa.Column('run_type', sa.String(20), server_default='incremental', nullable=False),  # 'full' or 'incremental'
        sa.Column('days_back', sa.Integer(), server_default='30', nullable=False),

        # Scheduling configuration
        sa.Column('schedule_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('schedule_type', sa.String(20), server_default='interval', nullable=True),  # 'interval' or 'daily'
        sa.Column('schedule_interval', sa.Integer(), nullable=True),  # Interval value
        sa.Column('schedule_unit', sa.String(20), server_default='hours', nullable=True),  # 'minutes', 'hours', 'days'
        sa.Column('schedule_time', sa.Time(), nullable=True),  # For daily schedules (HH:MM)

        # Notification settings
        sa.Column('notify_on_complete', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('notify_threshold', sa.Integer(), server_default='10', nullable=False),  # Min articles to notify

        # Run tracking
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.String(20), nullable=True),  # 'success', 'error', 'running'
        sa.Column('last_run_error', sa.Text(), nullable=True),
        sa.Column('last_run_articles_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_run_articles_categorized', sa.Integer(), server_default='0', nullable=False),
        sa.Column('run_count', sa.Integer(), server_default=sa.text('0'), nullable=False),

        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Add indexes for efficient querying
    op.create_index('ix_policy_tracker_schedules_next_run', 'policy_tracker_schedules', ['next_run_at'])
    op.create_index('ix_policy_tracker_schedules_schedule_enabled', 'policy_tracker_schedules', ['schedule_enabled'])
    op.create_index('ix_policy_tracker_schedules_topic', 'policy_tracker_schedules', ['topic'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_policy_tracker_schedules_topic', table_name='policy_tracker_schedules')
    op.drop_index('ix_policy_tracker_schedules_schedule_enabled', table_name='policy_tracker_schedules')
    op.drop_index('ix_policy_tracker_schedules_next_run', table_name='policy_tracker_schedules')

    # Drop table
    op.drop_table('policy_tracker_schedules')
