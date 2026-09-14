"""Paid analyst inquiries booked from the market front page.

A reader pays for a 30 or 60 minute call about a vendor or the market.
The row is written before Stripe is asked for a Checkout session, so the
success page and the webhook both find it whichever arrives first; the
status flips to ``paid`` exactly once (``WHERE status = 'created'``) and the
two notified flags are each claimed atomically, so nobody is mailed twice.
``booked`` and ``refunded`` are set by hand for now.

Revision ID: mm_023
Revises: mcp_001
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_023'
down_revision = 'mcp_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_inquiries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('length_minutes', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False,
                  server_default='usd'),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('stripe_session_id', sa.String(255), nullable=True,
                  unique=True),
        sa.Column('stripe_payment_intent', sa.String(255), nullable=True),
        sa.Column('status', sa.String(16), nullable=False,
                  server_default='created'),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('notified_editors', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('notified_buyer', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_market_inquiries_ip',
                    'market_inquiries', ['ip', 'created_at'])
    op.create_index('ix_market_inquiries_market',
                    'market_inquiries', ['market_id', 'status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_market_inquiries_market', table_name='market_inquiries')
    op.drop_index('ix_market_inquiries_ip', table_name='market_inquiries')
    op.drop_table('market_inquiries')
