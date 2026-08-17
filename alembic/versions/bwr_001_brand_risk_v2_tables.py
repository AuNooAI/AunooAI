"""Brand Risk v2: screening verdicts + issue model

Adds the tables behind event-driven brand risk assessment
(docs/BRAND_RISK_BENCHMARK_SPEC.md):

- bw_screening_verdicts — one row per screened (article, brand), including explicit
  no_risk_found, so screening coverage is distinguishable from silence. Typed findings
  stay in bw_article_risks.
- bw_issues / bw_issue_articles — grouped underlying events with severity and dates.
- bw_issue_overrides — analyst merge/split corrections that survive issue rebuilds.
- bw_article_risks.justification — the screener's one-sentence basis, displayed on issues.

Revision ID: bwr_001
Revises: 1204fb391c21
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'bwr_001'
down_revision: Union[str, None] = '1204fb391c21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bw_screening_verdicts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('article_uri', sa.Text, nullable=False),
        sa.Column('brand_id', sa.Integer, nullable=False),
        sa.Column('outcome', sa.String(20), nullable=False),   # risk_found | no_risk_found
        sa.Column('method', sa.String(20), nullable=False),    # llm | keyword
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('prompt_version', sa.String(20), nullable=False),
        sa.Column('screened_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('article_uri', 'brand_id', name='uq_bwsv_article_brand'),
    )
    op.create_index('ix_bwsv_brand_screened', 'bw_screening_verdicts', ['brand_id', 'screened_at'])

    op.create_table(
        'bw_issues',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('brand_id', sa.Integer, nullable=False),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('primary_type', sa.String(40), nullable=False),
        sa.Column('secondary_types', sa.dialects.postgresql.JSONB, server_default='[]'),
        sa.Column('severity', sa.String(10), nullable=False),  # high | medium | low
        sa.Column('justification', sa.Text, nullable=True),
        # ISO text dates, matching articles.publication_date (TEXT in this schema)
        sa.Column('first_seen', sa.Text, nullable=False),
        sa.Column('last_seen', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_bwi_brand_last_seen', 'bw_issues', ['brand_id', 'last_seen'])

    op.create_table(
        'bw_issue_articles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('issue_id', sa.Integer, sa.ForeignKey('bw_issues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text, nullable=False),
        sa.Column('brand_id', sa.Integer, nullable=False),
        sa.Column('similarity', sa.Float, nullable=True),
        # seed | story_group | embedding | llm_confirm | override
        sa.Column('merge_method', sa.String(20), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('brand_id', 'article_uri', name='uq_bwia_brand_article'),
    )
    op.create_index('ix_bwia_issue', 'bw_issue_articles', ['issue_id'])

    op.create_table(
        'bw_issue_overrides',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('brand_id', sa.Integer, nullable=False),
        sa.Column('article_uri', sa.Text, nullable=False),
        sa.Column('action', sa.String(10), nullable=False),    # detach | attach
        sa.Column('target_issue_id', sa.Integer, nullable=True),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('brand_id', 'article_uri', name='uq_bwio_brand_article'),
    )

    op.add_column('bw_article_risks', sa.Column('justification', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column('bw_article_risks', 'justification')
    op.drop_table('bw_issue_overrides')
    op.drop_table('bw_issue_articles')
    op.drop_table('bw_issues')
    op.drop_table('bw_screening_verdicts')
