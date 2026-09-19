"""issue_merge_shadow — Jev's same-event judgment next to the merge decision

Revision ID: ts_006
Revises: ts_004
Create Date: 2026-09-19

One row per (article, candidate issue) pair the brand-risk issue builder
considered. Records the cosine similarity and what the pipeline did (auto
merge above 0.99, LLM-confirmed merge or refusal in the 0.85 to 0.99 band,
new issue below), next to the TypeSafe Jev model's three-level Score from the
entity-alignment recipe (different event / related, possibly the same /
same event) and three per-aspect Nouls a curator can read. Replayed pairs
from existing issues carry decision 'replay'. Nothing on the merge path
reads this table.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_006'
down_revision = 'ts_004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'issue_merge_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand_id', sa.Integer(), nullable=False, index=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('article_title', sa.Text(), nullable=True),
        sa.Column('issue_id', sa.Integer(), nullable=True),
        sa.Column('issue_title', sa.Text(), nullable=True),
        sa.Column('issue_members', sa.Integer(), nullable=True),
        sa.Column('cosine_sim', sa.Float(), nullable=True),
        sa.Column('pipe_decision', sa.Text(), nullable=False),   # auto_merge | llm_confirm_yes | llm_confirm_no | new_issue | replay_same | replay_different
        sa.Column('jev_score', sa.Float(), nullable=True),        # 0 different .. 1 same (Score / 2)
        sa.Column('jev_level', sa.Text(), nullable=True),         # different | related | same (nearest level)
        sa.Column('jev_p_different', sa.Float(), nullable=True),
        sa.Column('jev_p_related', sa.Float(), nullable=True),
        sa.Column('jev_p_same', sa.Float(), nullable=True),
        sa.Column('jev_confidence', sa.Float(), nullable=True),
        sa.Column('jev_same_action', sa.Float(), nullable=True),  # same concrete event or action
        sa.Column('jev_same_actors', sa.Float(), nullable=True),  # same named people or organisations acting
        sa.Column('jev_same_period', sa.Float(), nullable=True),  # same time period or a continuation
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('issue_merge_shadow')
