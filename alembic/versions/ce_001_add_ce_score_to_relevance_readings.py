"""Add ce_score column to relevance_confidence_readings

Revision ID: ce_001
Revises: ti_001
Create Date: 2026-04-19

Adds a nullable ``ce_score`` column so the hybrid relevance service can log
the cross-encoder tier score alongside the classifier + embedding scores.
Needed to backtest the CE tier against historical LLM-fallback decisions.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'ce_001'
down_revision = 'ti_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'relevance_confidence_readings',
        sa.Column('ce_score', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('relevance_confidence_readings', 'ce_score')
