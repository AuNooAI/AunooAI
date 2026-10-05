"""rerank_shadow — Jev's per-candidate relevance next to the cross-encoder order

Revision ID: ts_004
Revises: ts_003
Create Date: 2026-09-19

One row per (rerank call, candidate) for Auspex retrievals on brand and
market topics, where the shared cross-encoder scores at chance (AUC 0.478
on hand-labelled brand articles, see hybrid_relevance_service.py). Records
the cosine rank, the cross-encoder rank and score, whether the candidate
made the top_k the caller received, and the TypeSafe Jev model's answers
to "does this candidate answer the query" and "is it about the monitored
entity or market". Nothing reads this table on the retrieval path.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_004'
down_revision = 'ts_003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rerank_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('call_id', sa.String(36), nullable=False, index=True),   # one per rerank() call
        sa.Column('caller', sa.Text(), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('topic_kind', sa.Text(), nullable=False),               # brand | market
        sa.Column('top_k', sa.Integer(), nullable=False),
        sa.Column('pool_size', sa.Integer(), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('cosine_rank', sa.Integer(), nullable=True),
        sa.Column('cosine_score', sa.Float(), nullable=True),
        sa.Column('ce_rank', sa.Integer(), nullable=True),
        sa.Column('ce_score', sa.Float(), nullable=True),
        sa.Column('in_top_k', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('jev_answers_query', sa.Float(), nullable=True),
        sa.Column('jev_about_entity', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('rerank_shadow')
