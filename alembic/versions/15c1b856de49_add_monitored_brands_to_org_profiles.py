"""add_monitored_brands_to_org_profiles

Revision ID: 15c1b856de49
Revises: pam_002
Create Date: 2025-12-15 09:58:36.053554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15c1b856de49'
down_revision: Union[str, None] = 'pam_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add monitored_brands column to organizational_profiles table
    # Stores JSON array of brand names to track in PAM analysis
    op.add_column(
        'organizational_profiles',
        sa.Column('monitored_brands', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('organizational_profiles', 'monitored_brands')
