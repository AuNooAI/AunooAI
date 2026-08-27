"""Stored Market Horizon computations.

One row per computation of a market's scale-against-momentum map, so the
next computation can show which vendors moved tier. The result is JSON: the
rated vendors with axes, tier and every input behind them, and the vendors
not rated with the reading each is missing.

Revision ID: mm_015
Revises: mm_014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_015'
down_revision = 'mm_014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_horizon',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=False),
    )
    op.create_index('ix_bw_market_horizon_market', 'bw_market_horizon',
                    ['market_id', 'computed_at'])


def downgrade() -> None:
    op.drop_index('ix_bw_market_horizon_market', table_name='bw_market_horizon')
    op.drop_table('bw_market_horizon')
