"""add background_tasks table for persisting task history

Revision ID: background_tasks_001
Revises: a901cca6001d
Create Date: 2025-01-17 15:45:00.000000

Adds database persistence for BackgroundTaskManager, enabling task history
to survive server restarts and providing audit trail for all background operations.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'background_tasks_001'
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
        'background_tasks',
        sa.Column('id', sa.String(36), primary_key=True, comment='UUID for task tracking'),
        sa.Column('name', sa.Text, nullable=False, comment='Human-readable task name'),
        sa.Column('status', sa.String(20), nullable=False, comment='Task status: pending/running/completed/failed/cancelled'),

        # Timestamps
        sa.Column('created_at', sa.DateTime, nullable=False, comment='When task was created'),
        sa.Column('started_at', sa.DateTime, nullable=True, comment='When task started execution'),
        sa.Column('completed_at', sa.DateTime, nullable=True, comment='When task completed or failed'),

        # Progress tracking
        sa.Column('progress', sa.Float, default=0.0, comment='Progress percentage (0-100)'),
        sa.Column('total_items', sa.Integer, default=0, comment='Total items to process'),
        sa.Column('processed_items', sa.Integer, default=0, comment='Items processed so far'),
        sa.Column('current_item', sa.Text, nullable=True, comment='Description of current item being processed'),

        # Results and errors
        sa.Column('result', json_type, nullable=True, comment='Final result data (JSON)'),
        sa.Column('error', sa.Text, nullable=True, comment='Error message if failed'),

        # Metadata
        sa.Column('metadata', json_type, nullable=True, comment='Task-specific metadata (topic, username, etc.)'),
    )

    # Indexes for common queries
    op.create_index('idx_background_tasks_status', 'background_tasks', ['status'])
    op.create_index('idx_background_tasks_created', 'background_tasks', ['created_at'])

    # Index for finding user's tasks (metadata contains username)
    if is_postgresql:
        # PostgreSQL supports GIN index on JSONB for efficient JSON queries
        op.create_index(
            'idx_background_tasks_metadata_gin',
            'background_tasks',
            ['metadata'],
            postgresql_using='gin'
        )


def downgrade():
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == 'postgresql'

    if is_postgresql:
        op.drop_index('idx_background_tasks_metadata_gin', table_name='background_tasks')

    op.drop_index('idx_background_tasks_created', table_name='background_tasks')
    op.drop_index('idx_background_tasks_status', table_name='background_tasks')
    op.drop_table('background_tasks')
