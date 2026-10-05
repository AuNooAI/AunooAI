"""Each market keeps its own list of followed accounts.

The follow list was the site-wide ``social_accounts.watchlisted`` flag, which
Brand Watcher's account watchlist also sets. So every market showed and read
the same accounts: the AI-in-the-SOC market's analysts appeared under "Accounts
we follow" on the EV battery market, and their posts were read into it.
``market_follows`` holds one row per market and account. Accounts that were
watchlisted when this ran are copied to market 2, the only market they were
followed for; the ``watchlisted`` flag itself is left to Brand Watcher.

Revision ID: mf_001
Revises: cdq_001
"""

from alembic import op
import sqlalchemy as sa

revision = 'mf_001'
down_revision = 'cdq_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_follows',
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(),
                  sa.ForeignKey('social_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('market_id', 'account_id'),
    )
    op.execute("""
        INSERT INTO market_follows (market_id, account_id)
        SELECT 2, id FROM social_accounts
         WHERE watchlisted AND EXISTS (SELECT 1 FROM bw_markets WHERE id = 2)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('market_follows')
