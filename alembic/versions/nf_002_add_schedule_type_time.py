"""Add schedule_type and schedule_time columns for daily scheduling

Revision ID: nf_002
Revises: nf_001
Create Date: 2026-01-10

Adds schedule_type and schedule_time for daily scheduling support.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'nf_002'
down_revision = 'nf_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add schedule_type column
    op.add_column('newsfeed_dashboard_settings',
        sa.Column('schedule_type', sa.String(20), server_default='interval', nullable=False))

    # Add schedule_time column for daily schedules
    op.add_column('newsfeed_dashboard_settings',
        sa.Column('schedule_time', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('newsfeed_dashboard_settings', 'schedule_time')
    op.drop_column('newsfeed_dashboard_settings', 'schedule_type')
