"""Widen forecast_scenario_verdicts.horizon_type varchar(4) -> varchar(16).

The column was sized for the Three Horizons vocabulary ("h1"/"h2"/"h3").
The newer deck-overlay generator emits likelihood classes ("probable",
"plausible", "possible") as the deck scenario horizon, and the first
assessment run against such an overlay (Attacks on Expertise, 2026-08-03)
computed five correct verdicts and then lost all of them to
``StringDataRightTruncation`` at the INSERT. 16 chars covers both
vocabularies with room.

Revision ID: fsv_horizon_16
Revises: emb_768_01
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'fsv_horizon_16'
down_revision = 'emb_768_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'forecast_scenario_verdicts', 'horizon_type',
        existing_type=sa.String(4), type_=sa.String(16),
        existing_nullable=True,
    )
    # Same vocabulary can reach user-promoted scenarios.
    op.alter_column(
        'forecast_user_scenarios', 'horizon_type',
        existing_type=sa.String(4), type_=sa.String(16),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Values longer than 4 chars ("probable"…) would truncate — refuse
    # silently lossy downgrades by leaving the wider type in place is not
    # an option for alembic symmetry, so trim first.
    op.execute("UPDATE forecast_scenario_verdicts "
               "SET horizon_type = left(horizon_type, 4) "
               "WHERE length(horizon_type) > 4")
    op.execute("UPDATE forecast_user_scenarios "
               "SET horizon_type = left(horizon_type, 4) "
               "WHERE length(horizon_type) > 4")
    op.alter_column(
        'forecast_scenario_verdicts', 'horizon_type',
        existing_type=sa.String(16), type_=sa.String(4),
        existing_nullable=True,
    )
    op.alter_column(
        'forecast_user_scenarios', 'horizon_type',
        existing_type=sa.String(16), type_=sa.String(4),
        existing_nullable=True,
    )
