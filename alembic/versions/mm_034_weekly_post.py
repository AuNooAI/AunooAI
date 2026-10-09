"""The weekly LinkedIn post for a market.

One row per (market, week): the post as mailed to the editors, the source
behind each bullet, and the open-role count it quoted, so the next week's
post can say whether hiring went up or down from a recorded figure rather
than a guess.

Revision ID: mm_034
Revises: mm_033
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_034'
down_revision = 'mm_033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_weekly_posts',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('sources', postgresql.JSONB(), nullable=False,
                  server_default='[]'),
        sa.Column('open_roles', sa.Integer(), nullable=True),
        sa.Column('model_used', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('market_id', 'week_start',
                            name='uq_bw_market_weekly_posts'),
    )


def downgrade() -> None:
    op.drop_table('bw_market_weekly_posts')
