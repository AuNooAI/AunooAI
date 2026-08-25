"""Market Monitor — a per-vendor brand-monitoring switch

Revision ID: mm_005
Revises: mm_004
Create Date: 2026-08-20

Market monitoring and brand monitoring are different jobs at different prices,
and until now a vendor in a market was implicitly a Brand Watcher brand as
well. That is wrong in both directions: 83 vendors flood a brand dashboard
built for a handful, and the ones worth following closely get no more attention
than the ones nobody writes about.

``brand_monitoring_enabled`` is the third independent switch on a market
vendor, alongside ``collection_enabled`` (do we spend on watching it) and
``is_public`` (does it reach a public page). It is off by default: a market
import should not silently add 83 brands to somebody's brand dashboard.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_005'
down_revision = 'mm_004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE bw_market_brands
        ADD COLUMN IF NOT EXISTS brand_monitoring_enabled BOOLEAN
        NOT NULL DEFAULT FALSE""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_bw_market_brands_brandmon
        ON bw_market_brands (market_id)
        WHERE brand_monitoring_enabled""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bw_market_brands_brandmon")
    op.execute("""ALTER TABLE bw_market_brands
        DROP COLUMN IF EXISTS brand_monitoring_enabled""")
