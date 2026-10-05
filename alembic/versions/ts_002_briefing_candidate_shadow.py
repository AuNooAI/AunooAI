"""briefing_candidate_shadow — what the TypeSafe Jev model would have kept

Revision ID: ts_002
Revises: ts_001
Create Date: 2026-09-19

One row per (desk briefing, candidate article) for every article in the
ranked candidate pool of a desk-briefing compose run. It records what the
pipeline did with the candidate (shortlisted? selected? by the curator or by
backfill?) next to Jev's answers to the briefing-worthiness questions. Nothing
reads this table on the compose path; it exists so the two selections can be
compared, and the disagreements hand-labelled, before Jev is allowed to
influence what the curator sees.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_002'
down_revision = 'ts_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'briefing_candidate_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('briefing_id', sa.Integer(), nullable=False, index=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        # what the pipeline did
        sa.Column('pool_rank', sa.Integer(), nullable=True),        # 1 = top of the ranked pool
        sa.Column('prerank_score', sa.Float(), nullable=True),
        sa.Column('topic_alignment', sa.Float(), nullable=True),
        sa.Column('in_shortlist', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('selected', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('selected_via', sa.Text(), nullable=True),        # curator | backfill | NULL
        # what Jev said
        sa.Column('jev_on_topic', sa.Float(), nullable=True),
        sa.Column('jev_material', sa.Float(), nullable=True),
        sa.Column('jev_new_development', sa.Float(), nullable=True),
        sa.Column('jev_noise', sa.Float(), nullable=True),
        sa.Column('jev_injection', sa.Float(), nullable=True),
        sa.Column('jev_worthiness', sa.Float(), nullable=True),     # Score 0-1 over four levels
        sa.Column('jev_confidence', sa.Float(), nullable=True),     # of the worthiness Score
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('briefing_id', 'article_uri', name='uq_briefing_candidate_shadow'),
    )


def downgrade() -> None:
    op.drop_table('briefing_candidate_shadow')
