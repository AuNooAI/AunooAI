"""Add scheduling settings for newsfeed dashboard generation

Revision ID: nf_001
Revises: oa_001
Create Date: 2026-01-10

Adds:
- newsfeed_dashboard_settings table for schedule configuration
- newsfeed_dashboard_monitor_status table for tracking scheduled runs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'nf_001'
down_revision = 'oa_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create newsfeed_dashboard_settings table
    op.create_table(
        'newsfeed_dashboard_settings',
        sa.Column('id', sa.Integer(), primary_key=True),

        # Schedule settings
        sa.Column('schedule_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('check_interval', sa.Integer(), server_default='24', nullable=False),
        sa.Column('interval_unit', sa.String(20), server_default='hours', nullable=False),

        # What to generate
        sa.Column('generate_briefing', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('generate_highlights', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('generate_narratives', sa.Boolean(), server_default='false', nullable=False),

        # Briefing settings
        sa.Column('persona', sa.String(50), server_default='CEO', nullable=False),
        sa.Column('model', sa.String(100), server_default='gpt-4o-mini'),
        sa.Column('topic_filter', sa.String(255), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )

    # Create newsfeed_dashboard_monitor_status table
    op.create_table(
        'newsfeed_dashboard_monitor_status',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('last_run_time', sa.DateTime(), nullable=True),
        sa.Column('next_run_time', sa.DateTime(), nullable=True),
        sa.Column('last_run_status', sa.String(20), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('is_running', sa.Boolean(), server_default='false'),
        sa.Column('run_count', sa.Integer(), server_default='0'),
        sa.Column('last_run_duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )

    # Insert default settings row
    op.execute("""
        INSERT INTO newsfeed_dashboard_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)

    # Insert default status row
    op.execute("""
        INSERT INTO newsfeed_dashboard_monitor_status (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('newsfeed_dashboard_monitor_status')
    op.drop_table('newsfeed_dashboard_settings')
