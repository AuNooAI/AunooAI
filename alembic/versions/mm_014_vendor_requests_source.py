"""Vendor requests can come from inside the product, not only from the form.

Top voices reads which accounts posting about a market are vendors' own. A
vendor we do not track has no profile to attach the account to, so it goes
into the same queue a reader uses through "Is your company missing?". That
row has no contact address, so ``email`` becomes nullable, and ``source``
says which path filed it.

Revision ID: mm_014
Revises: mm_013
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_014'
down_revision = 'mm_013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('market_vendor_requests',
                  sa.Column('source', sa.String(40), nullable=False,
                            server_default='form'))
    op.alter_column('market_vendor_requests', 'email',
                    existing_type=sa.String(254), nullable=True)
    # One queue entry per company per market from the product side; the
    # form may repeat (a second person can ask).
    op.create_index('uq_market_vendor_requests_auto', 'market_vendor_requests',
                    ['market_id', sa.text('lower(company)')], unique=True,
                    postgresql_where=sa.text("source <> 'form'"))


def downgrade() -> None:
    op.drop_index('uq_market_vendor_requests_auto', table_name='market_vendor_requests')
    op.execute("DELETE FROM market_vendor_requests WHERE email IS NULL")
    op.alter_column('market_vendor_requests', 'email',
                    existing_type=sa.String(254), nullable=False)
    op.drop_column('market_vendor_requests', 'source')
