"""add consensus-topic lifecycle columns to forecast_topic_metadata

Revision ID: fa_010
Revises: fa_009
Create Date: 2026-05-26 13:00:00.000000

A tracked topic is a CLAIM whose source consensus is the forecast basis.
The consensus-topic lifecycle loop (detect → formalize → analyze each cycle
→ retire on decay → cycle in) needs a little state per topic:

  claim_statement     — the documented claim being tracked
  basis_consensus_pct — source-consensus % measured at formalization
  formalized_at       — when the candidate became a tracked consensus topic
  last_evidence_cycle — period_label of the last cycle that produced new events
  dormant_since       — period_label when the topic first went evidence-quiet

The scheduled loop itself (auto-detect / decay sweep / cycle-in) is a later
layer; this migration just lands the state columns + the per-cycle READ is
cached on the assessment summary (no schema needed for that).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fa_010'
down_revision: Union[str, None] = 'fa_009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('forecast_topic_metadata',
                  sa.Column('claim_statement', sa.Text(), nullable=True))
    op.add_column('forecast_topic_metadata',
                  sa.Column('basis_consensus_pct', sa.Float(), nullable=True))
    op.add_column('forecast_topic_metadata',
                  sa.Column('formalized_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('forecast_topic_metadata',
                  sa.Column('last_evidence_cycle', sa.String(64), nullable=True))
    op.add_column('forecast_topic_metadata',
                  sa.Column('dormant_since', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('forecast_topic_metadata', 'dormant_since')
    op.drop_column('forecast_topic_metadata', 'last_evidence_cycle')
    op.drop_column('forecast_topic_metadata', 'formalized_at')
    op.drop_column('forecast_topic_metadata', 'basis_consensus_pct')
    op.drop_column('forecast_topic_metadata', 'claim_statement')
