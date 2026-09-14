"""Per-vendor analyst controls for the Market Horizon.

One row per vendor per market: a multiplier per input (0 to 2, default 1) so
an analyst can discount an input that is noise for this vendor or emphasise
one that is real, a free-text note, and a status — active, acquired or
closed — with the acquirer and date. Applied on the next compute and printed
beside the vendor, so an adjustment is never silent.

Revision ID: mm_016
Revises: mm_015
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_016'
down_revision = 'mm_015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_vendor_controls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('multipliers', postgresql.JSONB(), nullable=False,
                  server_default='{}'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('acquired_by', sa.String(200), nullable=True),
        sa.Column('status_date', sa.Date(), nullable=True),
        sa.Column('updated_by', sa.String(120), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.UniqueConstraint('market_id', 'brand_id', name='uq_bw_market_vendor_controls'),
    )


def downgrade() -> None:
    op.drop_table('bw_market_vendor_controls')
