"""A vendor's mark on the brand row, for the market front page.

``logo_data`` is the mark itself as a small data URI (a 64 px PNG, or an
SVG), so a page that must render without external requests can draw it.
``logo_source`` is where it came from; ``logo_fetched_at`` when.

Revision ID: mm_020
Revises: mm_019
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'mm_020'
down_revision = 'mm_019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bw_brands', sa.Column('logo_data', sa.Text(), nullable=True))
    op.add_column('bw_brands', sa.Column('logo_source', sa.Text(), nullable=True))
    op.add_column('bw_brands', sa.Column('logo_fetched_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('bw_brands', 'logo_fetched_at')
    op.drop_column('bw_brands', 'logo_source')
    op.drop_column('bw_brands', 'logo_data')
