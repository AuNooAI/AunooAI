"""Featured items on the market front page.

A hand-picked link the front page promotes: a whitepaper we wrote, a talk,
a report. The row carries what the card prints (kind, title, blurb, link,
publisher, byline) and where it goes (``placement``: the main column, the
desktop sidebar, or both). ``starts_at``/``ends_at`` bound the run;
``active`` retires a row without deleting it. First use: the Anvilogic
whitepaper "The Decoupled SIEM" (Oliver Rochford, September 2026).

Revision ID: mm_029
Revises: sd_002
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_029'
down_revision = 'sd_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_featured',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('kind', sa.String(32), nullable=False,
                  server_default='whitepaper'),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('blurb', sa.Text(), nullable=True),
        sa.Column('url', sa.String(1000), nullable=False),
        sa.Column('publisher', sa.String(120), nullable=True),
        sa.Column('byline', sa.String(200), nullable=True),
        sa.Column('vendor', sa.String(120), nullable=True),
        sa.Column('placement', sa.String(8), nullable=False,
                  server_default='both'),
        sa.Column('sort_order', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_market_featured_market',
                    'market_featured', ['market_id', 'active', 'sort_order'])


def downgrade() -> None:
    op.drop_index('ix_market_featured_market', table_name='market_featured')
    op.drop_table('market_featured')
