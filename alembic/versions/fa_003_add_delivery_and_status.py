"""add forecast scenario status + topic delivery tables

Revision ID: fa_003
Revises: fa_002
Create Date: 2026-05-22 12:50:00.000000

Backs two features on the Forecast Tracker:

* ``forecast_scenario_status`` — overlay table so users can mark any scenario
  (original or addendum) as "done". Done scenarios are skipped from the
  reranker/LLM stages during assess_run but still get a placeholder verdict
  row at the same scenario_idx, preserving historical comparisons.

* ``forecast_topic_delivery`` — per-topic cadence + recipient configuration
  for the recurring Wiley delivery pipeline (monthly per-topic updates and
  quarterly bundle of the core topics).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fa_003'
down_revision: Union[str, None] = 'fa_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'forecast_scenario_status',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False),
        sa.Column('scenario_idx', sa.Integer(), nullable=True),
        sa.Column('user_scenario_id', sa.String(36), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column('marked_done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.UniqueConstraint('run_id', 'scenario_idx', 'user_scenario_id',
                            name='uq_scenario_status_run_keys'),
    )
    op.create_index('ix_forecast_scenario_status_run', 'forecast_scenario_status', ['run_id'])

    op.create_table(
        'forecast_topic_delivery',
        sa.Column('topic', sa.Text(), primary_key=True),
        sa.Column('cadence', sa.String(16), nullable=False, server_default=sa.text("'none'")),
        sa.Column('recipient_email', sa.Text(), nullable=True),
        sa.Column('last_delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('forecast_topic_delivery')
    op.drop_index('ix_forecast_scenario_status_run', table_name='forecast_scenario_status')
    op.drop_table('forecast_scenario_status')
