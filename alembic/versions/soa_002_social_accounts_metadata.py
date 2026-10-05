"""Give social_accounts the metadata column the account-role lookup reads.

``audience_voices.account_audiences`` reads ``social_accounts.metadata`` for a
profiled account's market role. The column arrived with ei_002, which the
Wiley trees never took, so on wiley and wileytest that query failed on every
Social tab and Voices request. The failure was caught, but it left the
transaction aborted, so any query after it in the same request failed too.

Same definition as ei_002, idempotent, so a no-op wherever ei_002 ran. These
trees have diverged, so it is copied between them with only
``down_revision`` changed.

Revision ID: soa_002
Revises: soa_001
Create Date: 2026-09-24
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'soa_002'
down_revision = 'soa_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE social_accounts
        ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb""")


def downgrade() -> None:
    # Nothing to drop: on an entity tenant the column belongs to ei_002.
    pass
