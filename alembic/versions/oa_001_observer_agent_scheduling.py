"""Add observer agent scheduling columns

Revision ID: oa_001
Revises: sr_001
Create Date: 2026-01-10

Adds scheduling configuration and run tracking columns to signal_instructions table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'oa_001'
down_revision: Union[str, None] = 'sr_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scheduling configuration columns
    op.add_column('signal_instructions',
        sa.Column('schedule_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('signal_instructions',
        sa.Column('schedule_type', sa.String(20), server_default='interval', nullable=True))
    op.add_column('signal_instructions',
        sa.Column('schedule_interval', sa.Integer(), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('schedule_unit', sa.String(20), server_default='hours', nullable=True))
    op.add_column('signal_instructions',
        sa.Column('schedule_time', sa.Time(), nullable=True))

    # Add run tracking columns
    op.add_column('signal_instructions',
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('last_run_status', sa.String(20), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('last_run_error', sa.Text(), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('run_count', sa.Integer(), server_default=sa.text('0'), nullable=False))

    # Add index for efficient querying of due agents
    op.create_index('ix_signal_instructions_next_run', 'signal_instructions', ['next_run_at'])
    op.create_index('ix_signal_instructions_schedule_enabled', 'signal_instructions', ['schedule_enabled'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_signal_instructions_schedule_enabled', table_name='signal_instructions')
    op.drop_index('ix_signal_instructions_next_run', table_name='signal_instructions')

    # Drop run tracking columns
    op.drop_column('signal_instructions', 'run_count')
    op.drop_column('signal_instructions', 'last_run_error')
    op.drop_column('signal_instructions', 'last_run_status')
    op.drop_column('signal_instructions', 'next_run_at')
    op.drop_column('signal_instructions', 'last_run_at')

    # Drop scheduling configuration columns
    op.drop_column('signal_instructions', 'schedule_time')
    op.drop_column('signal_instructions', 'schedule_unit')
    op.drop_column('signal_instructions', 'schedule_interval')
    op.drop_column('signal_instructions', 'schedule_type')
    op.drop_column('signal_instructions', 'schedule_enabled')
