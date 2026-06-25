"""add forecast bundle review table

Revision ID: fa_005
Revises: fa_004
Create Date: 2026-05-23 11:30:00.000000

Backs the human-in-the-loop review gate added to the WileyBundleSupervisor
pipeline. The LLM-as-judge reviewer agent inspects every artefact produced
by the upstream synthesis agents and persists its findings (per-artefact
severity + suggested fix) into this table. A human approver clears the
gate via the Wiley Deliverables panel before the deck ships.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_005'
down_revision: Union[str, None] = 'fa_004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'forecast_bundle_review',
        sa.Column('cadence', sa.String(16), primary_key=True),
        sa.Column('period_label', sa.String(64), primary_key=True),
        sa.Column('status', sa.String(32), nullable=False, server_default=sa.text("'awaiting_synth'")),
        sa.Column('reviewer_findings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reviewer_model', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.Text(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('forecast_bundle_review')
