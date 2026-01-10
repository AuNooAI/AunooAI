"""Add article preference field for more/less like this

Revision ID: article_preference_001
Revises: et_003
Create Date: 2026-01-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'article_preference_001'
down_revision: Union[str, None] = 'et_003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_preference column to articles table."""
    # Add user_preference column - stores 'more', 'less', or null
    op.add_column('articles', sa.Column('user_preference', sa.Text(), nullable=True))

    # Add preference_date to track when preference was set
    op.add_column('articles', sa.Column('preference_date', sa.DateTime(), nullable=True))

    # Add index for efficient querying by preference
    op.create_index('idx_articles_user_preference', 'articles', ['user_preference'])


def downgrade() -> None:
    """Remove user_preference column from articles table."""
    op.drop_index('idx_articles_user_preference', table_name='articles')
    op.drop_column('articles', 'preference_date')
    op.drop_column('articles', 'user_preference')
