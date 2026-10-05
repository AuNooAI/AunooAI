"""extraction_check_shadow — Jev's source-support verdict for every extracted claim

Revision ID: ts_007
Revises: ts_006
Create Date: 2026-09-19

One row per (extraction site, item, claim). An extraction site is any step
where a model turns source text into a value we store: the per-article
enrichment summary and explanations, timeline event titles and descriptions,
and whatever is attached next. Each claim is checked against the source text
it was extracted from with the "double-checking citations" recipe: supports /
contradicts / says nothing, with a confidence and a "carries a checkable
specific" probability. Nothing on the extraction path reads this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_007'
down_revision = 'ts_006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'extraction_check_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('site', sa.Text(), nullable=False, index=True),      # enrichment | timeline_event | ...
        sa.Column('item_key', sa.Text(), nullable=False, index=True),  # article uri, or scope/day/event title
        sa.Column('field', sa.Text(), nullable=False),                 # summary | sentiment_explanation | event.description | ...
        sa.Column('claim_no', sa.Integer(), nullable=False),
        sa.Column('claim', sa.Text(), nullable=False),
        sa.Column('source_label', sa.Text(), nullable=True),           # what the claim was checked against
        sa.Column('source_chars', sa.Integer(), nullable=True),
        sa.Column('pipe_model', sa.Text(), nullable=True),             # the model that did the extraction
        sa.Column('jev_relation', sa.Text(), nullable=True),
        sa.Column('jev_p_supports', sa.Float(), nullable=True),
        sa.Column('jev_p_contradicts', sa.Float(), nullable=True),
        sa.Column('jev_p_says_nothing', sa.Float(), nullable=True),
        sa.Column('jev_confidence', sa.Float(), nullable=True),
        sa.Column('jev_has_specific', sa.Float(), nullable=True),
        sa.Column('jev_best_source', sa.Text(), nullable=True),
        sa.Column('jev_best_source_p', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('extraction_check_shadow')
