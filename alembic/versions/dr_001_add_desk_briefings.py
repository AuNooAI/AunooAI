"""Add desk_briefings table for Briefing Desk feature

Revision ID: dr_001
Revises: kwg_001
Create Date: 2026-01-28

Adds desk_briefings table to store curated briefings that can include
articles and incidents from any topic. Users can add items, finalize
to generate AI synthesis, and export/share briefings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dr_001'
down_revision: Union[str, None] = 'kwg_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'desk_briefings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('topic', sa.String(255), nullable=True),  # Optional - briefings can be cross-topic
        sa.Column('username', sa.Text(), nullable=True),

        # Content (JSONB arrays)
        sa.Column('articles', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('incidents', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),

        # AI-generated synthesis (populated on finalize)
        sa.Column('synthesis', sa.Text(), nullable=True),
        sa.Column('themes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('priority_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Status tracking
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),  # draft, finalized
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('articles_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('incidents_count', sa.Integer(), server_default='0', nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'username', name='uq_desk_briefings_name_user')
    )

    # Indexes for efficient queries
    op.create_index('idx_desk_briefings_username', 'desk_briefings', ['username'], unique=False)
    op.create_index('idx_desk_briefings_status', 'desk_briefings', ['status'], unique=False)
    op.create_index('idx_desk_briefings_created_at', 'desk_briefings', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_desk_briefings_created_at', table_name='desk_briefings')
    op.drop_index('idx_desk_briefings_status', table_name='desk_briefings')
    op.drop_index('idx_desk_briefings_username', table_name='desk_briefings')
    op.drop_table('desk_briefings')
