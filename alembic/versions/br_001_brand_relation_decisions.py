"""keyword_article_matches: brand relationship, source relationship and decision provenance

The brand-relevance specification (docs/BRAND_RELEVANCE_SPEC.md) stores one
decision per article and target brand on the scoped match row:

``brand_relation``   subject, notable, sector, passing or other (NULL on legacy rows)
``source_relation``  owned, independent or unknown, relative to this brand
``judge_version``    the input key the decision was made under, for reuse
``decision_evidence`` JSON: matched alias, field, extract, evidence quality,
                     provenance (rule or model), reason, route, resolved model,
                     profile and rubric versions, collection query
``last_failure``     JSON: the latest failed attempt, kept apart from the verdict

Every column is nullable, so legacy rows stay readable and nothing is rescored.
The rel_001 verdict columns are added here too when a site lacks them, so this
one migration serves sites with and without rel_001. Every step checks first,
so it is safe to run on a site that already has some of the columns.

Revision ID: br_001
Revises: mf_001
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = 'br_001'
down_revision = 'mf_001'
branch_labels = None
depends_on = None

_TABLE = 'keyword_article_matches'


def _columns():
    return {c['name'] for c in inspect(op.get_bind()).get_columns(_TABLE)}


def _json_type():
    if op.get_bind().dialect.name == 'postgresql':
        return postgresql.JSONB()
    return sa.JSON()


def upgrade():
    cols = _columns()
    # rel_001 columns, for sites that never applied it.
    if 'topic_alignment_score' not in cols:
        op.add_column(_TABLE, sa.Column('topic_alignment_score', sa.Float(), nullable=True))
    if 'relevance_status' not in cols:
        op.add_column(_TABLE, sa.Column('relevance_status', sa.String(32), nullable=True))
    if 'scored_at' not in cols:
        op.add_column(_TABLE, sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True))
    # Brand decision columns.
    if 'brand_relation' not in cols:
        op.add_column(_TABLE, sa.Column('brand_relation', sa.String(16), nullable=True))
    if 'source_relation' not in cols:
        op.add_column(_TABLE, sa.Column('source_relation', sa.String(16), nullable=True))
    if 'judge_version' not in cols:
        op.add_column(_TABLE, sa.Column('judge_version', sa.String(96), nullable=True))
    if 'decision_evidence' not in cols:
        op.add_column(_TABLE, sa.Column('decision_evidence', _json_type(), nullable=True))
    if 'last_failure' not in cols:
        op.add_column(_TABLE, sa.Column('last_failure', _json_type(), nullable=True))
    existing = {i['name'] for i in inspect(op.get_bind()).get_indexes(_TABLE)}
    if 'idx_kam_brand_relation' not in existing:
        op.create_index('idx_kam_brand_relation', _TABLE, ['group_id', 'brand_relation'])


def downgrade():
    existing = {i['name'] for i in inspect(op.get_bind()).get_indexes(_TABLE)}
    if 'idx_kam_brand_relation' in existing:
        op.drop_index('idx_kam_brand_relation', table_name=_TABLE)
    cols = _columns()
    # Only the columns this migration owns; rel_001's stay where they were.
    for c in ('last_failure', 'decision_evidence', 'judge_version', 'source_relation', 'brand_relation'):
        if c in cols:
            op.drop_column(_TABLE, c)
