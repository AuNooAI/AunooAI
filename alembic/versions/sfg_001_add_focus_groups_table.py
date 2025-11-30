"""add saved_focus_groups table

Revision ID: sfg_001
Revises: eos_001
Create Date: 2025-11-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'sfg_001'
down_revision: Union[str, None] = 'eos_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_focus_groups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('personas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('focus_group_summary', sa.Text(), nullable=True),
        sa.Column('interaction_dynamics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('articles_used', sa.Integer(), nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('persona_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_focus_groups_topic_user_name')
    )
    op.create_index('idx_saved_focus_groups_topic', 'saved_focus_groups', ['topic'], unique=False)
    op.create_index('idx_saved_focus_groups_user', 'saved_focus_groups', ['username'], unique=False)
    op.create_index('idx_saved_focus_groups_created', 'saved_focus_groups', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_saved_focus_groups_created', table_name='saved_focus_groups')
    op.drop_index('idx_saved_focus_groups_user', table_name='saved_focus_groups')
    op.drop_index('idx_saved_focus_groups_topic', table_name='saved_focus_groups')
    op.drop_table('saved_focus_groups')
