"""add_analysis_storage_tables

Revision ID: 0bb0b7cee976
Revises: 7166c8140b17
Create Date: 2025-11-06 12:56:54.131628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bb0b7cee976'
down_revision: Union[str, None] = '7166c8140b17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create market_signals_runs table
    op.create_table(
        'market_signals_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('raw_output', sa.JSON, nullable=False),
        sa.Column('total_articles_analyzed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
    )
    op.create_index('idx_market_signals_user_created', 'market_signals_runs', ['user_id', 'created_at'])

    # Create impact_timeline_runs table
    op.create_table(
        'impact_timeline_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('raw_output', sa.JSON, nullable=False),
        sa.Column('total_articles_analyzed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
    )
    op.create_index('idx_impact_timeline_user_created', 'impact_timeline_runs', ['user_id', 'created_at'])

    # Create strategic_recommendations_runs table
    op.create_table(
        'strategic_recommendations_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('raw_output', sa.JSON, nullable=False),
        sa.Column('total_articles_analyzed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
    )
    op.create_index('idx_strategic_recs_user_created', 'strategic_recommendations_runs', ['user_id', 'created_at'])

    # Create future_horizons_runs table
    op.create_table(
        'future_horizons_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=True),
        sa.Column('topic', sa.Text, nullable=False),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('raw_output', sa.JSON, nullable=False),
        sa.Column('total_articles_analyzed', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('analysis_duration_seconds', sa.Float, nullable=True),
    )
    op.create_index('idx_future_horizons_user_created', 'future_horizons_runs', ['user_id', 'created_at'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('idx_future_horizons_user_created', table_name='future_horizons_runs')
    op.drop_table('future_horizons_runs')

    op.drop_index('idx_strategic_recs_user_created', table_name='strategic_recommendations_runs')
    op.drop_table('strategic_recommendations_runs')

    op.drop_index('idx_impact_timeline_user_created', table_name='impact_timeline_runs')
    op.drop_table('impact_timeline_runs')

    op.drop_index('idx_market_signals_user_created', table_name='market_signals_runs')
    op.drop_table('market_signals_runs')
