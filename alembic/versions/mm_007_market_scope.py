"""Market Monitor — an explicit statement of what a market covers

Revision ID: mm_007
Revises: mm_006
Create Date: 2026-08-23

The investor-facing report described the tracked vendor cohort by inference —
whoever the reader saw in the registry. That invites a wrong conclusion the
moment coverage includes a vendor outside the cohort (an incumbent named in
third-party news, say), because there was nowhere to state the boundary.

Three nullable text columns on ``bw_markets``. All optional: a market with
none set gets a plain "not defined" note in the report rather than a
fabricated scope description, which is the point — better to say the
boundary was never written down than to guess it from the vendor list.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'mm_007'
down_revision = 'mm_006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE bw_markets
        ADD COLUMN IF NOT EXISTS market_scope_description TEXT,
        ADD COLUMN IF NOT EXISTS inclusion_criteria TEXT,
        ADD COLUMN IF NOT EXISTS exclusion_criteria TEXT""")


def downgrade() -> None:
    op.execute("""ALTER TABLE bw_markets
        DROP COLUMN IF EXISTS market_scope_description,
        DROP COLUMN IF EXISTS inclusion_criteria,
        DROP COLUMN IF EXISTS exclusion_criteria""")
