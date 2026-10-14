"""App store review snapshots and call log.

Brand Watcher collects Google Play and App Store reviews per brand
(docs/APP_STORE_REVIEWS_SPEC.md). Two tables:

- bw_app_snapshots: one row per app, country store and day with the app's
  own rating, review count and downloads, for the rating trend and the
  app_rating_drop alert.
- bw_app_review_calls: one row per scraper call with the records it
  returned, for the monthly record cap and for checking the Bright Data bill.

Revision ID: bw_app_001
Revises: mm_034
Create Date: 2026-10-14

On another site, set down_revision to that site's current head before
copying this file in (oviva: ts_011).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'bw_app_001'
down_revision = 'mm_034'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_app_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('store', sa.Text(), nullable=False),
        sa.Column('app_id', sa.Text(), nullable=False),
        sa.Column('country', sa.Text(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('rating', sa.Numeric(3, 2), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('downloads', sa.BigInteger(), nullable=True),
        sa.Column('data', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('brand_id', 'store', 'app_id', 'country', 'snapshot_date',
                            name='uq_bw_app_snap_day'),
    )
    op.create_index('idx_bw_app_snap_brand', 'bw_app_snapshots', ['brand_id', 'snapshot_date'])

    op.create_table(
        'bw_app_review_calls',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('store', sa.Text(), nullable=False),
        sa.Column('app_id', sa.Text(), nullable=False),
        sa.Column('country', sa.Text(), nullable=False),
        sa.Column('called_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('records', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('idx_bw_app_calls_when', 'bw_app_review_calls', ['called_at'])


def downgrade():
    op.drop_table('bw_app_review_calls')
    op.drop_table('bw_app_snapshots')
