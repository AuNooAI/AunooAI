"""add forecast user scenarios table

Revision ID: fa_002
Revises: fa_001
Create Date: 2026-05-22 12:00:00.000000

Backs the "promote unanticipated developments to tracked scenarios" feature:
users can promote a surprise cluster on a Forecast Tracker assessment into a
first-class scenario. These addendum scenarios live in a separate table so the
original Three Horizons forecast (future_horizons_runs.raw_output.scenarios)
remains untouched as an audit trail. The assessment service loads original +
addendum scenarios and concatenates them at run time.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_002'
down_revision: Union[str, None] = 'fa_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'forecast_user_scenarios',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('horizon_type', sa.String(4), nullable=False),
        sa.Column('timeframe', sa.String(32), nullable=True),
        sa.Column('source_assessment_id', sa.String(36), nullable=True),
        sa.Column('source_surprise_label', sa.Text(), nullable=True),
        sa.Column('source_article_uris', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('ix_forecast_user_scenarios_run', 'forecast_user_scenarios', ['run_id'])


def downgrade() -> None:
    op.drop_index('ix_forecast_user_scenarios_run', table_name='forecast_user_scenarios')
    op.drop_table('forecast_user_scenarios')
