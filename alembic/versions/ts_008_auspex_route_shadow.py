"""auspex_route_shadow — Jev's routing judgment next to Auspex's per-turn choices

Revision ID: ts_008
Revises: ts_007
Create Date: 2026-09-19

One row per Auspex chat turn. Records what the pipeline decided about the
turn (intent and depth from the regex classifiers, the model it used, the
retrieval limit) beside the TypeSafe Jev model's reading of the same turn:
intent and depth as Choices with probabilities, whether the turn needs the
article database at all, and a three-level difficulty Score. This is the
"model router" pattern: a cheap calibrated judgment in front of the
expensive model. Nothing on the chat path reads this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_008'
down_revision = 'ts_007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auspex_route_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chat_id', sa.Integer(), nullable=True, index=True),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('history_turns', sa.Integer(), nullable=True),
        sa.Column('pipe_intent', sa.Text(), nullable=True),
        sa.Column('pipe_depth', sa.Text(), nullable=True),
        sa.Column('pipe_model', sa.Text(), nullable=True),
        sa.Column('pipe_limit', sa.Integer(), nullable=True),
        sa.Column('jev_intent', sa.Text(), nullable=True),
        sa.Column('jev_intent_confidence', sa.Float(), nullable=True),
        sa.Column('jev_depth', sa.Text(), nullable=True),
        sa.Column('jev_depth_confidence', sa.Float(), nullable=True),
        sa.Column('jev_needs_retrieval', sa.Float(), nullable=True),
        sa.Column('jev_followup', sa.Float(), nullable=True),      # answerable from the conversation alone
        sa.Column('jev_difficulty', sa.Float(), nullable=True),    # Score 0-1 over three levels
        sa.Column('jev_difficulty_confidence', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('auspex_route_shadow')
