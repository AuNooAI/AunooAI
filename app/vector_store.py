"""
Vector store implementation using PostgreSQL pgvector.

Community Edition uses PostgreSQL pgvector exclusively for vector operations.
ChromaDB has been removed as it's only needed for SQLite-based deployments.

For all code, use this module which provides pgvector-based vector search.
"""
import logging

logger = logging.getLogger(__name__)

# Import all functions from the pgvector implementation
from app.vector_store_pgvector import (
    # Sync functions
    upsert_article,
    search_articles,
    similar_articles,
    get_vectors_by_metadata,
    get_by_ids,

    # Async functions
    upsert_article_async,
    search_articles_async,
    similar_articles_async,
    get_vectors_by_metadata_async,
    get_by_ids_async,

    # Health check
    check_pgvector_health as check_chromadb_health,  # Renamed for compatibility
)

logger.info("Vector store: Using PostgreSQL pgvector implementation")

# Compatibility stubs for removed ChromaDB functions
# These are kept to prevent import errors in existing routes
def get_chroma_client():
    """Compatibility stub - ChromaDB not available in PostgreSQL-only community edition."""
    raise NotImplementedError(
        "ChromaDB is not available in Community Edition. "
        "This version uses PostgreSQL pgvector exclusively."
    )

def _get_collection(*args, **kwargs):
    """Compatibility stub - ChromaDB not available in PostgreSQL-only community edition."""
    raise NotImplementedError(
        "ChromaDB is not available in Community Edition. "
        "This version uses PostgreSQL pgvector exclusively."
    )

def _embed_texts(*args, **kwargs):
    """Compatibility stub - Use vector_store_pgvector functions instead."""
    raise NotImplementedError(
        "Use upsert_article() or search_articles() instead. "
        "ChromaDB-specific functions are not available in Community Edition."
    )

def embedding_projection(*args, **kwargs):
    """Compatibility stub - ChromaDB not available in PostgreSQL-only community edition."""
    raise NotImplementedError(
        "ChromaDB is not available in Community Edition. "
        "This version uses PostgreSQL pgvector exclusively."
    )

def shutdown_vector_store():
    """Compatibility stub - No cleanup needed for pgvector."""
    logger.info("Vector store shutdown: No cleanup needed for pgvector")
    pass

# Export all public functions
__all__ = [
    # Sync functions
    'upsert_article',
    'search_articles',
    'similar_articles',
    'get_vectors_by_metadata',
    'get_by_ids',

    # Async functions
    'upsert_article_async',
    'search_articles_async',
    'similar_articles_async',
    'get_vectors_by_metadata_async',
    'get_by_ids_async',

    # Health check
    'check_chromadb_health',  # Keep old name for compatibility

    # Compatibility stubs (raise NotImplementedError)
    'get_chroma_client',
    '_get_collection',
    '_embed_texts',
    'embedding_projection',
    'shutdown_vector_store',
]

# Migration note for developers
def _migration_note():
    """
    COMMUNITY EDITION: PostgreSQL pgvector Only

    This module uses PostgreSQL's native pgvector extension for all vector operations.
    ChromaDB support has been removed as it's only needed for SQLite-based deployments.

    Benefits of pgvector:
    - No separate database synchronization needed
    - Native PostgreSQL ACID compliance
    - Simpler architecture and better performance
    - Integrated with existing database connection pool
    - Single source of truth for data and vectors

    All public APIs remain the same, so no changes are needed in calling code.
    """
    pass
