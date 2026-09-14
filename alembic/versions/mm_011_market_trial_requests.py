"""Trial requests from the shared market report.

The shared (no-session) view of a market report blurs most of the evidence
and asks the reader to request a trial. This is where those requests land.
It is deliberately a plain table with no workflow state: a person reads it
and replies, and the row is the record that they asked.

Revision ID: mm_011
Revises: mm_010
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_011'
down_revision = 'mm_010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_trial_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(),
                  sa.ForeignKey('bw_markets.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('surface', sa.String(40), nullable=False,
                  server_default='report.html'),
        sa.Column('viewer_reason', sa.String(60), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(400), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('ix_market_trial_requests_created',
                    'market_trial_requests', ['created_at'])
    op.create_index('ix_market_trial_requests_ip_created',
                    'market_trial_requests', ['ip', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_market_trial_requests_ip_created',
                  table_name='market_trial_requests')
    op.drop_index('ix_market_trial_requests_created',
                  table_name='market_trial_requests')
    op.drop_table('market_trial_requests')
