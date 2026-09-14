"""Our own pieces beside the weekly briefing.

A briefing row can now be an ``analysis`` or a ``note`` a person wrote, with
an author and the moment it was published. ``generation = 'written'`` says
no model drafted it.

Revision ID: mm_021
Revises: mm_020
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'mm_021'
down_revision = 'mm_020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bw_market_briefings',
                  sa.Column('kind', sa.String(20), nullable=False, server_default='briefing'))
    op.add_column('bw_market_briefings', sa.Column('author', sa.String(120), nullable=True))
    op.add_column('bw_market_briefings',
                  sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_bw_market_briefings_kind', 'bw_market_briefings',
                               "kind IN ('briefing', 'analysis', 'note')")
    op.drop_constraint('ck_bw_market_briefings_generation', 'bw_market_briefings',
                       type_='check')
    op.create_check_constraint(
        'ck_bw_market_briefings_generation', 'bw_market_briefings',
        "generation IN ('generated', 'fallback', 'edited', 'written')")
    # The briefings approved so far were published when last updated.
    op.execute("UPDATE bw_market_briefings SET published_at = updated_at "
               "WHERE status = 'approved' AND published_at IS NULL")


def downgrade() -> None:
    op.drop_constraint('ck_bw_market_briefings_generation', 'bw_market_briefings',
                       type_='check')
    op.execute("UPDATE bw_market_briefings SET generation = 'edited' WHERE generation = 'written'")
    op.create_check_constraint(
        'ck_bw_market_briefings_generation', 'bw_market_briefings',
        "generation IN ('generated', 'fallback', 'edited')")
    op.drop_constraint('ck_bw_market_briefings_kind', 'bw_market_briefings', type_='check')
    op.drop_column('bw_market_briefings', 'published_at')
    op.drop_column('bw_market_briefings', 'author')
    op.drop_column('bw_market_briefings', 'kind')
