"""Add module_config table for per-module enable/disable

Revision ID: mc_001
Revises: sf_002
Create Date: 2026-02-06

Stores per-module enabled state. When empty, the app falls back to
the ENABLED_MODULES env var. First toggle from the UI seeds all rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "mc_001"
down_revision: Union[str, None] = "sf_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "module_config",
        sa.Column("module_id", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("module_config")
