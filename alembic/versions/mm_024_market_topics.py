"""Stored "Being discussed" and "Emerging" topics for a market.

One row per daily run: the market's matched corpus over the last 30 days,
grouped by embedding, each group named by a model, with counts for the
whole window and for the last 7 days. Each run is self-contained. The
emerging signal is the date distribution inside one clustering, so nothing
matches groups across runs and nothing should: a group's id is only stable
inside the row it is stored in. The front page reads the newest row.

Revision ID: mm_024
Revises: mm_023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'mm_024'
down_revision = 'mm_023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_topics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_days', sa.Integer(), nullable=False),
        sa.Column('recent_days', sa.Integer(), nullable=False),
        sa.Column('n_articles', sa.Integer(), nullable=False),
        sa.Column('k', sa.Integer(), nullable=False),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=False),
    )
    op.create_index('ix_bw_market_topics_market', 'bw_market_topics',
                    ['market_id', 'computed_at'])


def downgrade() -> None:
    op.drop_index('ix_bw_market_topics_market', table_name='bw_market_topics')
    op.drop_table('bw_market_topics')
