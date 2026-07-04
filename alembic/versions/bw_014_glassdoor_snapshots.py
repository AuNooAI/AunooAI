"""Daily Glassdoor employer-rating snapshots.

The aggregates cache in bw_brands.config is overwritten on every refresh, so
there is no history — a slow slide in rating or business outlook is invisible.
This table keeps one row per brand per day (upserted on each fetch), giving the
Workforce tab a ratings-over-time series and the alert evaluator a basis for
detecting deterioration.

Revision ID: bw_014_glassdoor_snapshots
Revises: bw_013_incidents
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'bw_014_glassdoor_snapshots'
down_revision = 'bw_013_incidents'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_glassdoor_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('data', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('brand_id', 'snapshot_date', name='uq_bw_gd_snap_brand_date'),
    )
    op.create_index('idx_bw_gd_snap_brand', 'bw_glassdoor_snapshots', ['brand_id', 'snapshot_date'])


def downgrade():
    op.drop_table('bw_glassdoor_snapshots')
