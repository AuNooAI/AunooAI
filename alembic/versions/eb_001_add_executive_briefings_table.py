"""add saved_executive_briefings table

Revision ID: eb_001
Revises: sfg_001
Create Date: 2025-11-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'eb_001'
down_revision: Union[str, None] = 'sfg_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_executive_briefings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('persona', sa.String(50), nullable=False),  # CEO/CMO/CTO/CISO/Custom
        sa.Column('article_count', sa.Integer(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Generation config
        sa.Column('articles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),  # Analyzed articles
        sa.Column('briefing_summary', sa.Text(), nullable=True),  # Synthesis narrative
        sa.Column('themes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Cross-article themes
        sa.Column('priority_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Recommended actions
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Generation stats
        sa.Column('articles_used', sa.Integer(), nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_exec_briefings_topic_user_name')
    )
    op.create_index('idx_saved_exec_briefings_topic', 'saved_executive_briefings', ['topic'], unique=False)
    op.create_index('idx_saved_exec_briefings_user', 'saved_executive_briefings', ['username'], unique=False)
    op.create_index('idx_saved_exec_briefings_persona', 'saved_executive_briefings', ['persona'], unique=False)
    op.create_index('idx_saved_exec_briefings_created', 'saved_executive_briefings', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_saved_exec_briefings_created', table_name='saved_executive_briefings')
    op.drop_index('idx_saved_exec_briefings_persona', table_name='saved_executive_briefings')
    op.drop_index('idx_saved_exec_briefings_user', table_name='saved_executive_briefings')
    op.drop_index('idx_saved_exec_briefings_topic', table_name='saved_executive_briefings')
    op.drop_table('saved_executive_briefings')
