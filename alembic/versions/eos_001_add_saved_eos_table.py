"""add saved_eos table

Revision ID: eos_001
Revises: newsletter_001
Create Date: 2025-11-30 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eos_001'
down_revision: Union[str, None] = 'newsletter_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_eos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('scenarios', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('articles_used', sa.Integer(), nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('time_horizon', sa.String(50), nullable=True),
        sa.Column('scenario_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_eos_topic_user_name')
    )
    op.create_index('idx_saved_eos_topic', 'saved_eos', ['topic'], unique=False)
    op.create_index('idx_saved_eos_user', 'saved_eos', ['username'], unique=False)
    op.create_index('idx_saved_eos_created', 'saved_eos', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_saved_eos_created', table_name='saved_eos')
    op.drop_index('idx_saved_eos_user', table_name='saved_eos')
    op.drop_index('idx_saved_eos_topic', table_name='saved_eos')
    op.drop_table('saved_eos')
