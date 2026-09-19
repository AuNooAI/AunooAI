"""briefing_claim_shadow — Jev's citation check next to the reviewer's findings

Revision ID: ts_003
Revises: ts_002
Create Date: 2026-09-19

One row per sentence of a desk-briefing draft at its first review. Records
which source items the sentence rests on, what the TypeSafe Jev model said
about whether those sources support it (the "double-checking citations"
recipe: supports / contradicts / says nothing, with a confidence), and
whether the deterministic preflight or the LLM judge flagged the same
sentence. Nothing on the finalize path reads this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_003'
down_revision = 'ts_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'briefing_claim_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('briefing_id', sa.Integer(), nullable=True, index=True),
        sa.Column('briefing_name', sa.Text(), nullable=True),
        sa.Column('review_round', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('target', sa.Text(), nullable=False),          # summary | theme:<name> | action:<n>
        sa.Column('sentence_no', sa.Integer(), nullable=False),
        sa.Column('sentence', sa.Text(), nullable=False),
        sa.Column('source_refs', sa.Text(), nullable=True),      # "Article 2, Article 5" — what the sentence was checked against
        sa.Column('scope', sa.Text(), nullable=True),            # cited | all
        # Jev
        sa.Column('jev_relation', sa.Text(), nullable=True),     # supports | contradicts | says_nothing
        sa.Column('jev_p_supports', sa.Float(), nullable=True),
        sa.Column('jev_p_contradicts', sa.Float(), nullable=True),
        sa.Column('jev_p_says_nothing', sa.Float(), nullable=True),
        sa.Column('jev_confidence', sa.Float(), nullable=True),
        sa.Column('jev_best_source', sa.Text(), nullable=True),  # source ref with the highest per-source support
        sa.Column('jev_best_source_p', sa.Float(), nullable=True),
        sa.Column('jev_has_specific', sa.Float(), nullable=True),  # does the sentence carry a checkable specific (date, figure, name, event)?
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        # the incumbent
        sa.Column('judge_flagged', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('judge_severity', sa.Text(), nullable=True),   # error | warning | info
        sa.Column('judge_check', sa.Text(), nullable=True),      # date | figure | ... | preflight source
        sa.Column('judge_finding', sa.Text(), nullable=True),
        sa.Column('review_status', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('briefing_claim_shadow')
