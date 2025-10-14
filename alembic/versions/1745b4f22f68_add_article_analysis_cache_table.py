"""add_article_analysis_cache_table

Revision ID: 1745b4f22f68
Revises: d8d9cdcec340
Create Date: 2025-10-13 20:34:57.662837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1745b4f22f68'
down_revision: Union[str, None] = 'd8d9cdcec340'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create article_analysis_cache table
    op.create_table(
        'article_analysis_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('analysis_type', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('model_used', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_uri', 'analysis_type', 'model_used', name='uq_article_analysis_cache')
    )

    # Create indexes
    op.create_index('idx_article_analysis_cache_uri', 'article_analysis_cache', ['article_uri'], unique=False)
    op.create_index('idx_article_analysis_cache_type', 'article_analysis_cache', ['analysis_type'], unique=False)
    op.create_index('idx_article_analysis_cache_expires', 'article_analysis_cache', ['expires_at'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_article_analysis_cache_expires', table_name='article_analysis_cache')
    op.drop_index('idx_article_analysis_cache_type', table_name='article_analysis_cache')
    op.drop_index('idx_article_analysis_cache_uri', table_name='article_analysis_cache')

    # Drop table
    op.drop_table('article_analysis_cache')
