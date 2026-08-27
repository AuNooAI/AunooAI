"""Revisions of a market briefing's text.

A briefing can be edited by hand after the model wrote it. Every previous
text is kept here — the model's original and each edit — with who saved it
and why (edit, restore), so an approved report can always be traced back to
what the model actually said and what a person changed.

Revision ID: mm_017
Revises: mm_016
"""

from alembic import op
import sqlalchemy as sa

revision = 'mm_017'
down_revision = 'mm_016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bw_market_briefing_revisions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('briefing_id', sa.BigInteger(),
                  sa.ForeignKey('bw_market_briefings.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('report_content', sa.Text(), nullable=False),
        sa.Column('generation', sa.String(40), nullable=True),
        sa.Column('reason', sa.String(40), nullable=False, server_default='edit'),
        sa.Column('saved_by', sa.String(120), nullable=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_bw_market_briefing_revisions_briefing',
                    'bw_market_briefing_revisions', ['briefing_id', 'saved_at'])


def downgrade() -> None:
    op.drop_index('ix_bw_market_briefing_revisions_briefing',
                  table_name='bw_market_briefing_revisions')
    op.drop_table('bw_market_briefing_revisions')
