"""add ingest_job_status table for tracking auto-ingest progress

Revision ID: ingest_job_tracking_001
Revises: a901cca6001d
Create Date: 2025-01-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ingest_job_tracking_001'
down_revision = 'a901cca6001d'
branch_labels = None
depends_on = None


def upgrade():
    # Determine if we're using PostgreSQL or SQLite
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'

    # Create appropriate JSON column type
    json_type = postgresql.JSONB if is_postgresql else sa.Text

    op.create_table(
        'ingest_job_status',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('topic', sa.String(100), nullable=True),

        # Progress tracking
        sa.Column('total_articles', sa.Integer, default=0),
        sa.Column('processed_articles', sa.Integer, default=0),
        sa.Column('saved_articles', sa.Integer, default=0),
        sa.Column('filtered_articles', sa.Integer, default=0),
        sa.Column('failed_articles', sa.Integer, default=0),
        sa.Column('progress_percent', sa.Float, default=0.0),

        # Current activity
        sa.Column('current_stage', sa.String(100), nullable=True),
        sa.Column('current_article_title', sa.Text, nullable=True),

        # Timestamps - use CURRENT_TIMESTAMP for SQLite compatibility
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),

        # Results and errors - use Text for SQLite, JSONB for PostgreSQL
        sa.Column('result_summary', json_type, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_details', json_type, nullable=True),

        # Configuration used
        sa.Column('config_snapshot', json_type, nullable=True),
    )

    # Indexes for common queries
    if is_postgresql:
        # PostgreSQL supports partial indexes
        op.create_index('idx_ingest_job_status_lookup', 'ingest_job_status', ['status'],
                       postgresql_where=sa.text("status IN ('queued', 'running')"))
    else:
        # SQLite doesn't support partial indexes in all versions
        op.create_index('idx_ingest_job_status_lookup', 'ingest_job_status', ['status'])

    op.create_index('idx_ingest_job_username_lookup', 'ingest_job_status', ['username', 'created_at'])
    op.create_index('idx_ingest_job_created_lookup', 'ingest_job_status', ['created_at'])


def downgrade():
    op.drop_index('idx_ingest_job_created_lookup', table_name='ingest_job_status')
    op.drop_index('idx_ingest_job_username_lookup', table_name='ingest_job_status')
    op.drop_index('idx_ingest_job_status_lookup', table_name='ingest_job_status')
    op.drop_table('ingest_job_status')
