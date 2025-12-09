"""add_embedding_model_column

Revision ID: df6502715388
Revises: eb_001
Create Date: 2025-12-08 15:12:03.150532

Adds embedding_model column to track which model generated each embedding.
This enables user-configurable embedding models (OpenAI vs Ollama Nomic).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df6502715388'
down_revision: Union[str, None] = 'eb_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add embedding_model column to track which model generated each embedding
    op.execute("""
        ALTER TABLE articles
        ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(64)
    """)

    # Set existing embeddings to OpenAI model (since that was the previous default)
    op.execute("""
        UPDATE articles SET embedding_model = 'openai/text-embedding-3-small'
        WHERE embedding IS NOT NULL AND embedding_model IS NULL
    """)

    # Add comment for documentation
    op.execute("""
        COMMENT ON COLUMN articles.embedding_model IS
        'Model used to generate embedding (e.g., openai/text-embedding-3-small, ollama/nomic-embed-text)'
    """)


def downgrade() -> None:
    op.drop_column('articles', 'embedding_model')
