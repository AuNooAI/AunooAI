"""articles.author_role: who wrote the post, so a brand can hear its audiences apart

A social post about a health provider might come from a patient on the
programme, the GP who referred them, a dietitian, a journalist, or the
company itself. Sentiment alone flattens those into one number. The social
evaluation step now also names the author's role (patient, clinician,
customer, employee, journalist ...) and keeps a one-line reason, so the
Voices view can show what clinicians say next to what patients say.

The role is a property of the post, not of the (post, brand) pair, so it
lives on the article row and serves both the per-mention read path and the
legacy topic read path.

Branches off art_text_001, which every customer site has applied; the
canonical tree merges it with its own head in mm_028.

Revision ID: voice_001
Revises: art_text_001
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'voice_001'
down_revision = 'art_text_001'
branch_labels = None
depends_on = None


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in inspect(bind).get_columns(table)}


def upgrade():
    if not _has_column('articles', 'author_role'):
        op.add_column('articles', sa.Column('author_role', sa.String(32), nullable=True))
    if not _has_column('articles', 'author_role_reason'):
        op.add_column('articles', sa.Column('author_role_reason', sa.Text(), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS idx_articles_author_role "
               "ON articles (author_role) WHERE author_role IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_articles_author_role")
    if _has_column('articles', 'author_role_reason'):
        op.drop_column('articles', 'author_role_reason')
    if _has_column('articles', 'author_role'):
        op.drop_column('articles', 'author_role')
