"""add_consensus_analysis_runs_table

Revision ID: 7166c8140b17
Revises: 8f65d368bbd0
Create Date: 2025-11-05 15:58:11.389563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7166c8140b17'
down_revision: Union[str, None] = '8f65d368bbd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consensus_analysis_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('timeframe', sa.String(100), nullable=True),
        sa.Column('selected_categories', sa.JSON, nullable=True),
        sa.Column('raw_output', sa.JSON, nullable=False),
        sa.Column('total_articles_analyzed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
    )

    # Create index on user_id and created_at for efficient queries
    op.create_index('idx_consensus_analysis_user_created', 'consensus_analysis_runs', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('idx_consensus_analysis_user_created', table_name='consensus_analysis_runs')
    op.drop_table('consensus_analysis_runs')
