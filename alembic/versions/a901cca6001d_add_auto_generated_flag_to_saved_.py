"""add_auto_generated_flag_to_saved_dashboards

Revision ID: a901cca6001d
Revises: ae6ac9286d7a
Create Date: 2025-11-13 14:09:23.579853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a901cca6001d'
down_revision: Union[str, None] = 'ae6ac9286d7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add auto_generated column to saved_dashboards table
    op.add_column('saved_dashboards',
        sa.Column('auto_generated', sa.Boolean(), server_default='false', nullable=False)
    )


def downgrade() -> None:
    # Remove auto_generated column
    op.drop_column('saved_dashboards', 'auto_generated')
