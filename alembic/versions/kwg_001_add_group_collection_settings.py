"""Add per-group collection settings to keyword_groups table

Revision ID: kwg_001
Revises: gh_003
Create Date: 2026-01-26

Adds per-group auto-collection configuration columns to keyword_groups table.
Each group can have its own collectors and schedule, falling back to global defaults
when values are NULL.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'kwg_001'
down_revision = 'gh_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add collection schedule columns
    op.add_column('keyword_groups',
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False)
    )
    op.add_column('keyword_groups',
        sa.Column('check_interval', sa.Integer(), nullable=True)  # NULL = use global
    )
    op.add_column('keyword_groups',
        sa.Column('interval_unit', sa.Integer(), nullable=True)  # 60=minutes, 3600=hours, 86400=days
    )
    op.add_column('keyword_groups',
        sa.Column('search_date_range', sa.Integer(), nullable=True)
    )

    # Providers (JSON array)
    op.add_column('keyword_groups',
        sa.Column('providers', sa.Text(), nullable=True)  # e.g., '["thenewsapi", "arxiv"]'
    )

    # Processing settings (NULL = use global)
    op.add_column('keyword_groups',
        sa.Column('auto_ingest_enabled', sa.Boolean(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('min_relevance_threshold', sa.Float(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('quality_control_enabled', sa.Boolean(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('auto_save_approved_only', sa.Boolean(), nullable=True)
    )

    # AI settings (NULL = use global)
    op.add_column('keyword_groups',
        sa.Column('default_llm_model', sa.Text(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('llm_temperature', sa.Float(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('llm_max_tokens', sa.Integer(), nullable=True)
    )

    # Scheduling state
    op.add_column('keyword_groups',
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('last_error', sa.Text(), nullable=True)
    )
    op.add_column('keyword_groups',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True)
    )

    # Create index for efficient due-group queries
    op.create_index(
        'idx_keyword_groups_next_check',
        'keyword_groups',
        ['is_active', 'next_check_at']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_keyword_groups_next_check', table_name='keyword_groups')

    # Drop columns in reverse order
    op.drop_column('keyword_groups', 'updated_at')
    op.drop_column('keyword_groups', 'last_error')
    op.drop_column('keyword_groups', 'next_check_at')
    op.drop_column('keyword_groups', 'last_checked_at')
    op.drop_column('keyword_groups', 'llm_max_tokens')
    op.drop_column('keyword_groups', 'llm_temperature')
    op.drop_column('keyword_groups', 'default_llm_model')
    op.drop_column('keyword_groups', 'auto_save_approved_only')
    op.drop_column('keyword_groups', 'quality_control_enabled')
    op.drop_column('keyword_groups', 'min_relevance_threshold')
    op.drop_column('keyword_groups', 'auto_ingest_enabled')
    op.drop_column('keyword_groups', 'providers')
    op.drop_column('keyword_groups', 'search_date_range')
    op.drop_column('keyword_groups', 'interval_unit')
    op.drop_column('keyword_groups', 'check_interval')
    op.drop_column('keyword_groups', 'is_active')
