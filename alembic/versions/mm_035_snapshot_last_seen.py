"""When a vendor snapshot was last seen, not only when it was first stored.

``store_snapshot`` keeps one row per distinct content, so re-reading an
unchanged LinkedIn profile wrote nothing and the row kept the date we first
saw it. The headcount freshness check then read a stable vendor as stale after
two collection cycles and dropped it from the Maturity Map (HTCD and Intezer on
14 Oct 2026). ``last_seen_at`` is bumped on every re-read, so freshness can
mean "we checked it recently" and the series still only grows on a change.

NULL on existing rows: readers fall back to ``observed_at``.

Revision ID: mm_035
Revises: bw_app_001
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_035'
down_revision = 'bw_app_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bw_vendor_snapshots',
                  sa.Column('last_seen_at', sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column('bw_vendor_snapshots', 'last_seen_at')
