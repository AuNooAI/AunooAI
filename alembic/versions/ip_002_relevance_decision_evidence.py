"""Relevance decision evidence on articles and per-group matches

docs/pipelines/08_INGEST_FIX_SPEC.md, WP4 (M2) and WP5a. Until now a row
said only its score, and readers compared that score with 0.4 whatever
threshold had decided it; the Jev and CE accept tiers raised the score to
the threshold, so a stored score could be invented. Each decision now
records what decided it:

``relevance_threshold_applied``  the threshold the deciding group used
``relevance_accepted_applied``   the decision itself (NULL: a legacy row with
                                 no evidence, or a decision unavailable)
``relevance_decision_engine``    what decided: local, local+llm_fallback,
                                 jev_accept, ce_accept, brand_decision, ...
``relevance_engine_scores``      raw measurements under their own names
                                 (embedding, classifier, llm, ce, jev_on_topic)
``relevance_policy_version``     the decision rules in force
``relevance_decision_group_id``  the keyword group whose decision this is

``keyword_article_matches`` gets the same four decision fields per group,
because one article can be matched by several groups with different
thresholds.

``relevance_attempts`` / ``relevance_next_retry_at`` / ``relevance_last_error``
let a failed relevance check (no engine answered) be retried with a cap.

Additive and safe to re-run; the old code ignores the columns.

Revision ID: ip_002
Revises: ip_001
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = 'ip_002'
down_revision = 'ip_001'
branch_labels = None
depends_on = None

ARTICLE_COLS = [
    ('relevance_threshold_applied', sa.Float()),
    ('relevance_accepted_applied', sa.Boolean()),
    ('relevance_decision_engine', sa.String(48)),
    ('relevance_engine_scores', postgresql.JSONB()),
    ('relevance_policy_version', sa.String(32)),
    ('relevance_decision_group_id', sa.Integer()),
    ('relevance_attempts', sa.Integer()),
    ('relevance_next_retry_at', sa.DateTime(timezone=True)),
    ('relevance_last_error', sa.Text()),
]
MATCH_COLS = [
    ('relevance_threshold_applied', sa.Float()),
    ('relevance_accepted', sa.Boolean()),
    ('relevance_engine', sa.String(48)),
    ('relevance_policy_version', sa.String(32)),
]


def _add(table, cols):
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return
    have = {c['name'] for c in insp.get_columns(table)}
    for name, typ in cols:
        if name not in have:
            op.add_column(table, sa.Column(name, typ))


def upgrade():
    _add('articles', ARTICLE_COLS)
    _add('keyword_article_matches', MATCH_COLS)
    insp = inspect(op.get_bind())
    idx = {i['name'] for i in insp.get_indexes('articles')}
    if 'ix_articles_relevance_retry' not in idx:
        op.create_index('ix_articles_relevance_retry', 'articles', ['relevance_next_retry_at'],
                        postgresql_where=sa.text("ingest_status = 'relevance_check_failed'"))


def downgrade():
    insp = inspect(op.get_bind())
    idx = {i['name'] for i in insp.get_indexes('articles')}
    if 'ix_articles_relevance_retry' in idx:
        op.drop_index('ix_articles_relevance_retry', table_name='articles')
    for table, cols in (('keyword_article_matches', MATCH_COLS), ('articles', ARTICLE_COLS)):
        have = {c['name'] for c in insp.get_columns(table)}
        for name, _ in cols:
            if name in have:
                op.drop_column(table, name)
