"""add_article_list_to_consensus_analysis_runs

Revision ID: 47bbb2e52c81
Revises: 0bb0b7cee976
Create Date: 2025-11-06 15:34:34.573573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47bbb2e52c81'
down_revision: Union[str, None] = '0bb0b7cee976'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add article_list JSON column to consensus_analysis_runs table
    op.add_column('consensus_analysis_runs',
                  sa.Column('article_list', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove article_list column
    op.drop_column('consensus_analysis_runs', 'article_list')
