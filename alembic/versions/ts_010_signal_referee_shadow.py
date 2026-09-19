"""signal_referee_shadow — Jev as referee on observer-agent matches

Revision ID: ts_010
Revises: ts_009
Create Date: 2026-09-19

One row per (signal instruction, article) the observer matcher looked at, in
both the inline and the scheduled path. Records whether the LLM matcher
flagged the article, with its confidence, threat level and summary, beside
the TypeSafe Jev model's own reading: does the article match the plain-English
signal, how serious is it on the same three levels, and does the matcher's
summary claim anything the article does not support. That is the "completion
referee" pattern: a cheap judge of whether the agent's claim is backed by the
evidence it cites. Nothing on the alert path reads this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_010'
down_revision = 'ts_009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'signal_referee_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('instruction_id', sa.Integer(), nullable=True, index=True),
        sa.Column('instruction_name', sa.Text(), nullable=True),
        sa.Column('run_kind', sa.Text(), nullable=False),            # inline | scheduled
        sa.Column('batch_key', sa.String(32), nullable=False, index=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('matcher_flagged', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('matcher_confidence', sa.Float(), nullable=True),
        sa.Column('matcher_threat', sa.Text(), nullable=True),
        sa.Column('matcher_summary', sa.Text(), nullable=True),
        sa.Column('jev_matches', sa.Float(), nullable=True),
        sa.Column('jev_threat', sa.Float(), nullable=True),          # Score 0-1 over low / medium / high
        sa.Column('jev_threat_level', sa.Text(), nullable=True),
        sa.Column('jev_threat_confidence', sa.Float(), nullable=True),
        sa.Column('jev_summary_relation', sa.Text(), nullable=True), # supports | contradicts | says_nothing (flagged only)
        sa.Column('jev_summary_confidence', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('signal_referee_shadow')
