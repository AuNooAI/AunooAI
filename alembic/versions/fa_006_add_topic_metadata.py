"""add forecast topic metadata sidecar

Revision ID: fa_006
Revises: fa_005
Create Date: 2026-05-23 22:40:00.000000

Sidecar table for first-class topic lifecycle data. The existing pattern
keys every forecast artefact by the topic string (future_horizons_runs,
forecast_assessments, forecast_topic_delivery, the deck overlay JSON
files). This adds owner / description / status / overlay_status metadata
on top, keyed by the same topic string so existing rows remain untouched.

A backfill script seeds one row per topic already present in
forecast_topic_delivery so the Topics dashboard has full visibility from
day one without manual data entry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_006'
down_revision: Union[str, None] = 'fa_005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'forecast_topic_metadata',
        sa.Column('topic', sa.Text(), primary_key=True),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner', sa.Text(), nullable=True),
        # 'draft' / 'active' / 'archived' — controls whether the topic
        # surfaces in bundle generation and the Topics dashboard default view.
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # 'missing' / 'auto_generated' / 'human_reviewed' — flagged in the
        # bundle reviewer findings when 'missing' or 'auto_generated' so the
        # deck never silently ships with low-confidence deck framing.
        sa.Column('overlay_status', sa.String(16), nullable=False,
                  server_default=sa.text("'missing'")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_topic_metadata_status', 'forecast_topic_metadata', ['status'])
    op.create_index('idx_topic_metadata_owner', 'forecast_topic_metadata', ['owner'])


def downgrade() -> None:
    op.drop_index('idx_topic_metadata_owner', table_name='forecast_topic_metadata')
    op.drop_index('idx_topic_metadata_status', table_name='forecast_topic_metadata')
    op.drop_table('forecast_topic_metadata')
