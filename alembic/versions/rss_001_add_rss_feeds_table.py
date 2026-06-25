"""Add RSS feeds table for RSS feed collection

Revision ID: rss_001
Revises: et_006
Create Date: 2026-01-12

Adds:
- rss_feeds table for storing RSS feed configurations
- rss_feed_monitor_status table for tracking scheduled runs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rss_001'
down_revision = 'et_006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create rss_feeds table
    op.create_table(
        'rss_feeds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),  # Topic name (string, not FK)
        sa.Column('description', sa.Text(), nullable=True),

        # Schedule settings
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('check_interval', sa.Integer(), server_default='60', nullable=False),  # minutes
        sa.Column('interval_unit', sa.String(20), server_default='minutes', nullable=False),

        # Tracking
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_article_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('articles_fetched', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )

    # Create indexes
    op.create_index('ix_rss_feeds_topic', 'rss_feeds', ['topic'])
    op.create_index('ix_rss_feeds_is_active', 'rss_feeds', ['is_active'])
    op.create_index('ix_rss_feeds_last_checked', 'rss_feeds', ['last_checked_at'])

    # Create rss_feed_monitor_status table for global scheduler status
    op.create_table(
        'rss_feed_monitor_status',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('is_running', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_check_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_check_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('feeds_checked', sa.Integer(), server_default='0'),
        sa.Column('articles_fetched', sa.Integer(), server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_run_duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )

    # Insert default status row
    op.execute("""
        INSERT INTO rss_feed_monitor_status (id) VALUES (1)
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('rss_feed_monitor_status')
    op.drop_index('ix_rss_feeds_last_checked', table_name='rss_feeds')
    op.drop_index('ix_rss_feeds_is_active', table_name='rss_feeds')
    op.drop_index('ix_rss_feeds_topic', table_name='rss_feeds')
    op.drop_table('rss_feeds')
