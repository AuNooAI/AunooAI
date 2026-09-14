"""Monthly subscriptions sold from the market front page.

Two plans: the full dataset ($179/month) and the full dataset with MCP
access for the buyer's AI tools ($279/month). The row is written before
Stripe is asked for a Checkout session, so the success page and the
webhook both find it whichever arrives first; ``created`` flips to
``active`` exactly once (``WHERE status = 'created'``), and that winner is
the only path that mints the access token — and, on the MCP plan, the
bearer key — so a credential is never minted twice. Stripe's subscription
lifecycle events move ``active`` to ``past_due`` and ``cancelled``.

Revision ID: mm_025
Revises: mm_024
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_025'
down_revision = 'mm_024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('plan', sa.String(16), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False,
                  server_default='usd'),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('site', sa.String(200), nullable=True),
        sa.Column('stripe_session_id', sa.String(255), nullable=True,
                  unique=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True,
                  unique=True),
        sa.Column('status', sa.String(16), nullable=False,
                  server_default='created'),
        sa.Column('access_token_hash', sa.String(64), nullable=True,
                  unique=True),
        sa.Column('access_token_prefix', sa.String(12), nullable=True),
        sa.Column('mcp_key_id', sa.Integer(),
                  sa.ForeignKey('mcp_api_keys.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('notified_editors', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('notified_buyer', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_market_subscriptions_ip',
                    'market_subscriptions', ['ip', 'created_at'])
    op.create_index('ix_market_subscriptions_market',
                    'market_subscriptions', ['market_id', 'status', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_market_subscriptions_market', table_name='market_subscriptions')
    op.drop_index('ix_market_subscriptions_ip', table_name='market_subscriptions')
    op.drop_table('market_subscriptions')
