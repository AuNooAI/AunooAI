"""add_hnsw_vector_index

Revision ID: e0aa2eb4fa0a
Revises: b6a5ff4214f5
Create Date: 2025-10-20 18:20:21.915512

Adds HNSW index for pgvector similarity searches on articles.embedding column.

HNSW (Hierarchical Navigable Small World) provides:
- 10-100x faster vector searches than sequential scan
- Approximate nearest neighbor with high accuracy
- Automatic usage by PostgreSQL query planner

Index parameters:
- m=16: Number of connections per layer (good for 1536-dim embeddings)
- ef_construction=64: Quality during index build (higher = better, slower build)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0aa2eb4fa0a'
down_revision: Union[str, None] = 'b6a5ff4214f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add HNSW index on articles.embedding column for fast vector similarity search."""
    # Create HNSW index (IF NOT EXISTS for idempotency)
    # Uses vector_cosine_ops for cosine distance metric
    op.execute("""
        CREATE INDEX IF NOT EXISTS articles_embedding_hnsw_idx
        ON articles
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Add comment to document the index
    op.execute("""
        COMMENT ON INDEX articles_embedding_hnsw_idx IS
        'HNSW index for fast approximate nearest neighbor search on article embeddings.
        Provides 10-100x speedup for vector similarity queries.'
    """)


def downgrade() -> None:
    """Remove HNSW vector index."""
    op.execute('DROP INDEX IF EXISTS articles_embedding_hnsw_idx')
