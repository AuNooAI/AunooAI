"""Add article_origin column to articles table

Revision ID: pt_003
Revises: pt_002
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'pt_003'
down_revision = 'pt_002'
branch_labels = None
depends_on = None


def upgrade():
    # Add article_origin column to articles table
    op.add_column(
        'articles',
        sa.Column('article_origin', sa.Text(), server_default='unknown', nullable=True)
    )

    # Create index for efficient filtering
    op.create_index('idx_articles_article_origin', 'articles', ['article_origin'])

    # Update existing articles based on auto_ingested flag
    # Articles from automated ingest -> 'aunoo'
    # Other articles -> 'external'
    op.execute("""
        UPDATE articles
        SET article_origin = 'aunoo'
        WHERE auto_ingested = TRUE
    """)

    op.execute("""
        UPDATE articles
        SET article_origin = 'external'
        WHERE auto_ingested = FALSE OR auto_ingested IS NULL
    """)


def downgrade():
    op.drop_index('idx_articles_article_origin', table_name='articles')
    op.drop_column('articles', 'article_origin')
