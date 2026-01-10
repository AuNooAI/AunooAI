"""Add scheduling and notification settings for emerging topics

Revision ID: et_004
Revises: et_003
Create Date: 2026-01-10

Adds:
- emerging_topics_settings table for schedule and notification configuration
- emerging_topics_monitor_status table for tracking scheduled runs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'et_004'
down_revision = 'et_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create emerging_topics_settings table
    op.create_table(
        'emerging_topics_settings',
        sa.Column('id', sa.Integer(), primary_key=True),

        # Schedule settings
        sa.Column('schedule_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('check_interval', sa.Integer(), server_default='24', nullable=False),
        sa.Column('interval_unit', sa.String(20), server_default='hours', nullable=False),
        sa.Column('min_articles', sa.Integer(), server_default='50', nullable=False),

        # Detection settings (mirror what's in config modal)
        sa.Column('sample_size', sa.Integer(), server_default='200'),
        sa.Column('days_back', sa.Integer(), server_default='7'),
        sa.Column('model', sa.String(100), server_default='gpt-4o-mini'),
        sa.Column('topic_filter', sa.String(255), nullable=True),

        # Notification settings
        sa.Column('notifications_enabled', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('notification_channels', postgresql.JSONB(),
                  server_default='{"email": false, "in_app": true, "bluesky": false}'),
        sa.Column('min_confidence', sa.Float(), server_default='0.7'),
        sa.Column('cooldown_minutes', sa.Integer(), server_default='360'),
        sa.Column('email_recipients', postgresql.JSONB(), server_default='[]'),
        sa.Column('bluesky_handle', sa.String(255), nullable=True),
        sa.Column('detection_type_filters', postgresql.JSONB(),
                  server_default='["accelerating", "new_cluster"]'),

        # Last notification tracking (for cooldown)
        sa.Column('last_notification_time', sa.DateTime(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )

    # Create emerging_topics_monitor_status table
    op.create_table(
        'emerging_topics_monitor_status',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('last_check_time', sa.DateTime(), nullable=True),
        sa.Column('next_check_time', sa.DateTime(), nullable=True),
        sa.Column('topics_detected', sa.Integer(), server_default='0'),
        sa.Column('articles_analyzed', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('is_running', sa.Boolean(), server_default='false'),
        sa.Column('last_run_duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()')),
    )

    # Insert default settings row
    op.execute("""
        INSERT INTO emerging_topics_settings (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)

    # Insert default status row
    op.execute("""
        INSERT INTO emerging_topics_monitor_status (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('emerging_topics_monitor_status')
    op.drop_table('emerging_topics_settings')
