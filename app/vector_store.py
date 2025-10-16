"""
Vector store implementation using PostgreSQL pgvector.

This module has been migrated from ChromaDB to native PostgreSQL pgvector for better
performance and simpler architecture. The old ChromaDB implementation is preserved
in vector_store_chromadb_backup.py.

For all new code, use this module which provides the same interface but uses pgvector.
"""
import logging

logger = logging.getLogger(__name__)

# Import all functions from the new pgvector implementation
from app.vector_store_pgvector import (
    # Sync functions
    upsert_article,
    search_articles,
    similar_articles,
    get_vectors_by_metadata,

    # Async functions
    upsert_article_async,
    search_articles_async,
    similar_articles_async,
    get_vectors_by_metadata_async,

    # Health check
    check_pgvector_health as check_chromadb_health,  # Renamed for compatibility
)

# Import legacy ChromaDB functions for backward compatibility with old routes
from app.vector_store_chromadb_backup import (
    _get_collection,
    get_chroma_client,
    _embed_texts,
    embedding_projection,
    shutdown_vector_store,
)

logger.info("Vector store: Using PostgreSQL pgvector implementation")

# Export all public functions
__all__ = [
    # Sync functions
    'upsert_article',
    'search_articles',
    'similar_articles',
    'get_vectors_by_metadata',

    # Async functions
    'upsert_article_async',
    'search_articles_async',
    'similar_articles_async',
    'get_vectors_by_metadata_async',

    # Health check
    'check_chromadb_health',  # Keep old name for compatibility

    # Legacy ChromaDB functions (for backward compatibility)
    '_get_collection',
    'get_chroma_client',
    '_embed_texts',
    'embedding_projection',
    'shutdown_vector_store',
]

# Compatibility note for developers
def _migration_note():
    """
    MIGRATION COMPLETE: ChromaDB → pgvector

    This module now uses PostgreSQL's native pgvector extension instead of ChromaDB.

    Benefits:
    - No separate database synchronization needed
    - Native PostgreSQL ACID compliance
    - Simpler architecture and better performance
    - Integrated with existing database connection pool

    The old ChromaDB implementation is available in vector_store_chromadb_backup.py
    if you need to reference it.

    All public APIs remain the same, so no changes are needed in calling code.
    """
    pass
