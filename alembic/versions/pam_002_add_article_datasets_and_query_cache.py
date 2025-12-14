"""Add PAM article datasets and query cache tables

Revision ID: pam_002
Revises: pam_001
Create Date: 2024-12-13

Adds:
- pam_article_datasets: Track which articles were used for each analysis run
- pam_pillar_queries: Cache LLM-generated semantic queries for each pillar
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers
revision = 'pam_002'
down_revision = 'pam_001'
branch_labels = None
depends_on = None


def upgrade():
    # Table: pam_article_datasets
    # Tracks which articles were used for each PAM analysis run
    op.create_table(
        'pam_article_datasets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.String(36), nullable=False, index=True),
        sa.Column('pillar', sa.String(20), nullable=False),  # 'power', 'attention', 'money'
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('article_title', sa.Text(), nullable=True),
        sa.Column('article_source', sa.String(255), nullable=True),
        sa.Column('relevance_score', sa.Float(), nullable=True),  # cosine distance from vector search
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Index('ix_pam_datasets_run', 'run_id'),
        sa.Index('ix_pam_datasets_pillar', 'pillar'),
        sa.Index('ix_pam_datasets_topic', 'topic'),
    )

    # Table: pam_pillar_queries
    # Caches LLM-generated semantic queries for each pillar
    op.create_table(
        'pam_pillar_queries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('pillar', sa.String(20), nullable=False),  # 'power', 'attention', 'money'
        sa.Column('queries', postgresql.JSONB(), nullable=False),  # List of query strings
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('version', sa.Integer(), default=1),  # For versioning queries
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow),
        sa.UniqueConstraint('pillar', 'version', name='uq_pam_pillar_queries_pillar_version'),
        sa.Index('ix_pam_pillar_queries_pillar', 'pillar'),
        sa.Index('ix_pam_pillar_queries_active', 'is_active'),
    )


def downgrade():
    op.drop_table('pam_pillar_queries')
    op.drop_table('pam_article_datasets')
