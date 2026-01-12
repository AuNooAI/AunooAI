"""Add organization_implications column to emerging_topics table

Revision ID: et_005
Revises: et_004
Create Date: 2026-01-11

Adds organization_implications JSONB column for storing org-specific impact analysis.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'et_005'
down_revision = 'et_004'
branch_labels = None
depends_on = None


def upgrade():
    """Add organization_implications JSONB column to emerging_topics table."""
    op.add_column(
        'emerging_topics',
        sa.Column('organization_implications', JSONB, nullable=True)
    )


def downgrade():
    """Remove organization_implications column."""
    op.drop_column('emerging_topics', 'organization_implications')
