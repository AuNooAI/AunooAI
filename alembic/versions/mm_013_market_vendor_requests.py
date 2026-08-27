""""Is your company missing?" requests from the market report.

A reader of a market report who works at a vendor we do not track can say
so. The row is the record; a mail to the operator is a convenience. Kept apart
from ``market_trial_requests`` because the two are answered by different
people with different questions: one wants a trial, the other wants to be on
the list.

Revision ID: mm_013
Revises: mm_012
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_013'
down_revision = 'mm_012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_vendor_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('company', sa.String(200), nullable=False),
        sa.Column('website', sa.String(300), nullable=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_market_vendor_requests_market',
                    'market_vendor_requests', ['market_id', 'created_at'])
    op.create_index('ix_market_vendor_requests_ip',
                    'market_vendor_requests', ['ip', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_market_vendor_requests_ip', table_name='market_vendor_requests')
    op.drop_index('ix_market_vendor_requests_market', table_name='market_vendor_requests')
    op.drop_table('market_vendor_requests')
