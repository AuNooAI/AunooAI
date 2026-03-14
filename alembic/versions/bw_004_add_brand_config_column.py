"""Add config JSONB column to bw_brands

Revision ID: bw_004
Revises: bw_003
Create Date: 2026-02-06

Adds a config JSONB column for per-brand settings like SLM confidence threshold.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'bw_004'
down_revision: str = 'bw_003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bw_brands', sa.Column('config', postgresql.JSONB(), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('bw_brands', 'config')
