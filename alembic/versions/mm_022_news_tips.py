""""Submit news" tips from the market front page.

A reader points us at a story we missed: a URL, what it is, and an email to
answer to if they leave one. The row is the record; a mail to the operator
is a convenience, as with vendor and trial requests. Kept apart from those
two tables because a tip is answered by reading the link, not by a reply.

Revision ID: mm_022
Revises: mm_021
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_022'
down_revision = 'mm_021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_news_tips',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('url', sa.String(1000), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('email', sa.String(254), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('status', sa.String(16), nullable=False,
                  server_default='new'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_market_news_tips_market',
                    'market_news_tips', ['market_id', 'created_at'])
    op.create_index('ix_market_news_tips_ip',
                    'market_news_tips', ['ip', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_market_news_tips_ip', table_name='market_news_tips')
    op.drop_index('ix_market_news_tips_market', table_name='market_news_tips')
    op.drop_table('market_news_tips')
