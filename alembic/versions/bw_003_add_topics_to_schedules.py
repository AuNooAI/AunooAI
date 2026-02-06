"""Add topics column to bw_tracker_schedules

Revision ID: bw_003
Revises: bw_002
Create Date: 2026-02-06

Adds JSONB topics column so scheduled runs can target specific topics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bw_003'
down_revision: str = 'bw_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bw_tracker_schedules',
                  sa.Column('topics', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('bw_tracker_schedules', 'topics')
