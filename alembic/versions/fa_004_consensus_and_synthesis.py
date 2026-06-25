"""add current consensus + scenario synthesis + bundle synthesis cache

Revision ID: fa_004
Revises: fa_003
Create Date: 2026-05-23 09:00:00.000000

Three additions to support the analytically-faithful quarterly Wiley deck:

* ``forecast_scenario_verdicts.current_consensus_pct`` — share of confident
  verdicts that are ``supports_trajectory`` for this scenario. Recomputed
  each assessment so the deck can show original deck consensus next to the
  freshly-measured current consensus.

* ``forecast_scenario_verdicts.synthesis`` — JSONB cache for per-scenario
  LLM-synthesised artefacts (key_signals + strategic_imperative). Lazily
  populated by ensure_narratives_for_assessment.

* ``forecast_bundle_synthesis`` — cache for cross-topic LLM artefacts that
  span a whole bundle (strategic_overview, cross_cutting_themes,
  executive_decision_framework). Keyed by (cadence, period_label) so a
  re-export of the same quarter is instant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_004'
down_revision: Union[str, None] = 'fa_003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'forecast_scenario_verdicts',
        sa.Column('current_consensus_pct', sa.Float(), nullable=True),
    )
    op.add_column(
        'forecast_scenario_verdicts',
        sa.Column('synthesis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        'forecast_bundle_synthesis',
        sa.Column('cadence', sa.String(16), primary_key=True),
        sa.Column('period_label', sa.String(64), primary_key=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('topics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('forecast_bundle_synthesis')
    op.drop_column('forecast_scenario_verdicts', 'synthesis')
    op.drop_column('forecast_scenario_verdicts', 'current_consensus_pct')
