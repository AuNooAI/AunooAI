"""add_dashboard_cache_table

Revision ID: 5d62bf1a46ec
Revises: 19e016650e9f
Create Date: 2025-10-26 11:17:33.663189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d62bf1a46ec'
down_revision: Union[str, None] = '19e016650e9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create dashboard_cache table
    op.create_table(
        'dashboard_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cache_key', sa.Text(), nullable=False),
        sa.Column('dashboard_type', sa.Text(), nullable=False),
        sa.Column('date_range', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('profile_id', sa.Integer(), nullable=True),
        sa.Column('persona', sa.Text(), nullable=True),
        sa.Column('content_json', sa.Text(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('article_count', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('model_used', sa.Text(), nullable=True),
        sa.Column('generation_time_seconds', sa.Float(), nullable=True),
        sa.Column('generated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('accessed_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cache_key', name='uq_dashboard_cache_key'),
        sa.ForeignKeyConstraint(['profile_id'], ['organizational_profiles.id'], ondelete='SET NULL')
    )

    # Create indexes
    op.create_index('idx_dashboard_cache_type', 'dashboard_cache', ['dashboard_type', 'generated_at'], unique=False)
    op.create_index('idx_dashboard_cache_accessed', 'dashboard_cache', ['accessed_at'], unique=False)
    op.create_index('idx_dashboard_cache_key', 'dashboard_cache', ['cache_key'], unique=False)
    op.create_index('idx_dashboard_cache_topic', 'dashboard_cache', ['topic'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_dashboard_cache_topic', table_name='dashboard_cache')
    op.drop_index('idx_dashboard_cache_key', table_name='dashboard_cache')
    op.drop_index('idx_dashboard_cache_accessed', table_name='dashboard_cache')
    op.drop_index('idx_dashboard_cache_type', table_name='dashboard_cache')

    # Drop table
    op.drop_table('dashboard_cache')
