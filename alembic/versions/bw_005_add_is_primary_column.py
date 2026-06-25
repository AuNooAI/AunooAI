"""Add is_primary boolean column to bw_brands

Revision ID: bw_005
Revises: bw_004
Create Date: 2026-02-11

Adds an is_primary flag so one brand can be designated as the primary
brand for auto-selection in the Analysis & Insights tabs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bw_005'
down_revision: str = 'bw_004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bw_brands', sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('bw_brands', 'is_primary')
