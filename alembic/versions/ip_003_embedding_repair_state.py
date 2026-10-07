"""Embedding repair state on articles

docs/pipelines/08_INGEST_FIX_SPEC.md, WP5b (M5), and the social-post
embedding path. An encoder error used to leave an approved article without
an embedding for good, and nothing said so.

``embedding_due_at``         when the row became due for an embedding: its
                             latest approval, or a social post's evaluation
                             at relevance >= 0.4. NULL on legacy rows, which
                             are counted as a separate backlog, never as
                             overdue since some invented time.
``embedding_attempts``       failed encode attempts for this row
``embedding_last_error``     the latest failure
``embedding_next_retry_at``  backoff: not retried before this

Additive and safe to re-run.

Revision ID: ip_003
Revises: ip_002
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'ip_003'
down_revision = 'ip_002'
branch_labels = None
depends_on = None

COLS = [
    ('embedding_due_at', sa.DateTime(timezone=True)),
    ('embedding_attempts', sa.Integer()),
    ('embedding_last_error', sa.Text()),
    ('embedding_next_retry_at', sa.DateTime(timezone=True)),
]


def upgrade():
    insp = inspect(op.get_bind())
    have = {c['name'] for c in insp.get_columns('articles')}
    for name, typ in COLS:
        if name not in have:
            op.add_column('articles', sa.Column(name, typ))
    idx = {i['name'] for i in insp.get_indexes('articles')}
    if 'ix_articles_embedding_due' not in idx:
        op.create_index('ix_articles_embedding_due', 'articles', ['embedding_due_at'],
                        postgresql_where=sa.text('embedding IS NULL'))


def downgrade():
    insp = inspect(op.get_bind())
    idx = {i['name'] for i in insp.get_indexes('articles')}
    if 'ix_articles_embedding_due' in idx:
        op.drop_index('ix_articles_embedding_due', table_name='articles')
    have = {c['name'] for c in insp.get_columns('articles')}
    for name, _ in COLS:
        if name in have:
            op.drop_column('articles', name)
