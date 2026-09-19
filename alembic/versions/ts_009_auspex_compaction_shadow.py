"""auspex_compaction_shadow — Jev's keep-or-drop verdict per prior turn

Revision ID: ts_009
Revises: ts_008
Create Date: 2026-09-19

One row per prior message of an Auspex chat turn. Records what the
compactor did with the message (kept verbatim because it is within the last
six turns, summarised because the conversation crossed the 50k-token
threshold, or untouched because no compaction ran) beside the TypeSafe Jev
model's answer to "is this message needed to answer the current question".
This is the context garbage-collection pattern: selection instead of
summarisation, so what survives is unchanged. Nothing on the chat path reads
this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_009'
down_revision = 'ts_008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auspex_compaction_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.Integer(), nullable=True, index=True),
        sa.Column('turn_key', sa.String(64), nullable=False, index=True),   # one per chat turn
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('history_messages', sa.Integer(), nullable=False),
        sa.Column('history_tokens_est', sa.Integer(), nullable=True),
        sa.Column('compaction_applied', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('msg_index', sa.Integer(), nullable=False),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('chars', sa.Integer(), nullable=True),
        sa.Column('pipe_fate', sa.Text(), nullable=False),              # kept | summarised | untouched
        sa.Column('jev_needed', sa.Float(), nullable=True),
        sa.Column('jev_carries_specifics', sa.Float(), nullable=True),   # dates, figures, names, URLs a summary would lose
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('auspex_compaction_shadow')
