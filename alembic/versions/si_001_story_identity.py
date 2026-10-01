"""Record whether an article is a copy of one we hold, and whether it is a press release.

Until now the only duplicate check at insert was an exact URL match, so the
same story reached a topic feed several times (tracking parameters, a second
slug, a syndicated copy), and press-release wires counted as news. Ingest now
records three facts and the readable-articles rule acts on them. Nothing is
deleted: the number of outlets carrying a story is information in its own
right. Spec: docs/INGEST_DUPLICATES_AND_PRESS_RELEASES_SPEC.md

Revision ID: si_001
Revises: mm_032
"""

from alembic import op
import sqlalchemy as sa

revision = 'si_001'
down_revision = 'mm_032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('url_key', sa.Text(), nullable=True))
    op.add_column('articles', sa.Column('duplicate_of', sa.Text(), nullable=True))
    op.add_column('articles', sa.Column('source_type', sa.Text(), nullable=True))
    op.create_index('ix_articles_topic_url_key', 'articles', ['topic', 'url_key'])
    op.create_index('ix_articles_topic_pubdate', 'articles', ['topic', 'publication_date'])
    op.create_index('ix_articles_duplicate_of', 'articles', ['duplicate_of'],
                    postgresql_where=sa.text('duplicate_of IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('ix_articles_duplicate_of', table_name='articles')
    op.drop_index('ix_articles_topic_pubdate', table_name='articles')
    op.drop_index('ix_articles_topic_url_key', table_name='articles')
    op.drop_column('articles', 'source_type')
    op.drop_column('articles', 'duplicate_of')
    op.drop_column('articles', 'url_key')
