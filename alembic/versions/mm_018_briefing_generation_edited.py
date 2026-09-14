"""Let a briefing's generation be 'edited'.

mm_004 allowed only 'generated' and 'fallback'. A briefing a person has
rewritten is neither, and a reader should be able to tell a model's
sentence from a person's, so the check gains 'edited'.

Revision ID: mm_018
Revises: mm_017
"""

from alembic import op

revision = 'mm_018'
down_revision = 'mm_017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint('ck_bw_market_briefings_generation', 'bw_market_briefings',
                       type_='check')
    op.create_check_constraint(
        'ck_bw_market_briefings_generation', 'bw_market_briefings',
        "generation IN ('generated', 'fallback', 'edited')")


def downgrade() -> None:
    op.execute("UPDATE bw_market_briefings SET generation = 'generated' "
               "WHERE generation = 'edited'")
    op.drop_constraint('ck_bw_market_briefings_generation', 'bw_market_briefings',
                       type_='check')
    op.create_check_constraint(
        'ck_bw_market_briefings_generation', 'bw_market_briefings',
        "generation IN ('generated', 'fallback')")
