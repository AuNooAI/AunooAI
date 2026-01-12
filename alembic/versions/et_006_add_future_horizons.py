"""Add future_horizons column to emerging_topics

Revision ID: et_006
Revises: et_005
Create Date: 2026-01-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'et_006'
down_revision = 'et_005'
branch_labels = None
depends_on = None


def upgrade():
    # Add future_horizons JSONB column
    op.add_column(
        'emerging_topics',
        sa.Column('future_horizons', JSONB, nullable=True)
    )


def downgrade():
    op.drop_column('emerging_topics', 'future_horizons')
