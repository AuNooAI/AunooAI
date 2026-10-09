"""Weekly vendor chart for the market front page.

One row per (market, week, vendor) for the vendors that made that week's
Top 40, ranked by momentum on the Market Maturity Map run that closed the
week (``horizon_id``). Each week is frozen when it closes, so "weeks at #1"
keeps its meaning when the map's weights or inputs change later. Movement,
peak and weeks on the chart are derived from these rows when the page reads
them.

Revision ID: mm_033
Revises: subd_001
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_033'
down_revision = 'subd_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_vendor_chart',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('bw_brands.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('momentum', sa.Float(), nullable=False),
        sa.Column('scale', sa.Float(), nullable=True),
        sa.Column('band', sa.String(24), nullable=True),
        sa.Column('horizon_id', sa.Integer(),
                  sa.ForeignKey('bw_market_horizon.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint('market_id', 'week_start', 'brand_id',
                            name='uq_bw_market_vendor_chart'),
    )
    op.create_index('ix_bw_market_vendor_chart_market',
                    'bw_market_vendor_chart', ['market_id', 'week_start'])


def downgrade() -> None:
    op.drop_index('ix_bw_market_vendor_chart_market',
                  table_name='bw_market_vendor_chart')
    op.drop_table('bw_market_vendor_chart')
