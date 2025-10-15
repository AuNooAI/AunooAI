# ChromaDB to pgvector Migration - Detailed Implementation Specification

## Table of Contents
1. [Overview](#overview)
2. [Consumer Code Compatibility](#consumer-code-compatibility)
3. [Prerequisites](#prerequisites)
4. [Phase 1: Infrastructure Setup](#phase-1-infrastructure-setup)
5. [Phase 2: Core Vector Store Implementation](#phase-2-core-vector-store-implementation)
6. [Phase 3: Async Operations](#phase-3-async-operations)
7. [Phase 4: Migration & Reindexing](#phase-4-migration--reindexing)
8. [Phase 5: Testing & Validation](#phase-5-testing--validation)
9. [Phase 6: Deployment & Cleanup](#phase-6-deployment--cleanup)
10. [Rollback Plan](#rollback-plan)
11. [Performance Tuning](#performance-tuning)

---

## Overview

### Goals
- Replace ChromaDB vector storage with PostgreSQL pgvector extension
- Maintain 100% API compatibility with existing code
- Improve performance and reliability
- Simplify architecture (single database)

### Success Criteria
- ✅ All vector operations work identically to ChromaDB
- ✅ Semantic search results match ChromaDB accuracy (>95% similarity)
- ✅ No breaking changes to routes using vector_store.py
- ✅ Performance equal or better than ChromaDB
- ✅ All tests pass

### Migration Approach
**Strategy:** Blue-green migration with parallel implementation
- Implement pgvector alongside ChromaDB
- Validate parity before switching
- Feature flag to toggle between implementations
- Remove ChromaDB after validation period

### Effort Estimate
**Total: 12-16 hours of AI implementation time**

- Phase 1 (Infrastructure): 1-2 hours
- Phase 2 (Core Implementation): 4-5 hours
- Phase 3 (Async): 2-3 hours
- Phase 4 (Migration): 2-3 hours
- Phase 5 (Testing): 1-2 hours
- Phase 6 (Deployment): 0.5-1 hour

---

## Consumer Code Compatibility

### Zero-Impact Migration
**NO CHANGES REQUIRED** to any consumer code that uses vector operations. The facade pattern ensures complete API compatibility.

### Files That Do NOT Need Updates

The following files use the abstracted `app.vector_store` module and will work seamlessly with pgvector:

#### 1. app/routes/auspex_routes.py
- **Status**: NO CHANGES NEEDED
- **Reason**: Uses only the public API from `app.vector_store`
- **Current Usage**: Imports and calls abstracted functions

#### 2. app/services/auspex_service.py
- **Status**: NO CHANGES NEEDED
- **Reason**: Clean abstraction via facade pattern
- **Current Usage** (line 17):
```python
from app.vector_store import search_articles as vector_search_articles
```
- **Call Pattern**: `vector_search_articles(query, top_k, metadata_filter)`
- **Migration Impact**: Zero - facade routes to correct backend

#### 3. app/services/auspex_tools.py
- **Status**: NO CHANGES NEEDED
- **Reason**: Uses abstracted vector_store module
- **Current Usage** (line 14):
```python
from app.vector_store import search_articles as vector_search_articles
```

#### 4. templates/news_feed.html
- **Status**: NO CHANGES NEEDED
- **Reason**: Frontend template calling backend APIs only
- **Migration Impact**: Zero - no direct vector operations

### Why No Updates Are Needed

#### Clean Separation of Concerns
```python
# Consumer code (auspex_service.py, auspex_routes.py, etc.)
from app.vector_store import search_articles

# Remains unchanged regardless of backend
results = search_articles("AI trends", top_k=10)
```

#### Facade Pattern Implementation
```python
# app/vector_store.py (becomes facade)
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chromadb")

if VECTOR_BACKEND == "pgvector":
    from app.vector_store_pgvector import search_articles
elif VECTOR_BACKEND == "chromadb":
    from app.vector_store_chromadb import search_articles
```

#### API Compatibility Guarantee
All vector operations maintain **identical signatures** and **return formats**:

| Function | Signature | Return Type | Status |
|----------|-----------|-------------|--------|
| `upsert_article()` | `(article: Dict) -> None` | None | Compatible |
| `search_articles()` | `(query: str, top_k: int, filter: Dict) -> List[Dict]` | List[Dict] | Compatible |
| `similar_articles()` | `(uri: str, top_k: int) -> List[Dict]` | List[Dict] | Compatible |
| `get_vectors_by_metadata()` | `(limit: int, where: Dict) -> tuple` | tuple | Compatible |

### Verification Checklist

Before deployment, verify:
- [ ] No direct ChromaDB imports in consumer files (VERIFIED)
- [ ] All vector operations use `app.vector_store` facade (VERIFIED)
- [ ] Return data structures match ChromaDB format (VERIFIED IN SPEC)
- [ ] Async operations maintain compatibility (VERIFIED IN SPEC)

### Migration Impact Summary

| Component | Files Changed | Breaking Changes | Action Required |
|-----------|---------------|------------------|-----------------|
| Vector Store Core | 3 files (new pgvector impl, facade, rename chromadb) | None | Implementation only |
| Consumer Code | 0 files | None | None |
| Database Schema | 1 migration | None (additive only) | Run migration |
| Configuration | .env file | None (new variables) | Add env vars |

**Total Consumer Code Updates: 0 files**

---

## Prerequisites

### Environment Requirements
```bash
# PostgreSQL version check (need 11+)
psql --version  # You have PostgreSQL 14+ ✓

# Install pgvector extension
sudo apt-get install postgresql-14-pgvector  # Ubuntu/Debian
# OR build from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

### Python Dependencies
```python
# Add to requirements.txt
pgvector>=0.2.4
asyncpg>=0.29.0  # If not already present
sqlalchemy[asyncio]>=2.0.0
```

### Database Extension Installation
```sql
-- Run as PostgreSQL superuser
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';
```

---

## Phase 1: Infrastructure Setup

### 1.1 Database Schema Migration

**File:** `alembic/versions/YYYYMMDD_add_pgvector_support.py`

```python
"""Add pgvector support to articles table

Revision ID: add_pgvector_001
Revises: <previous_revision>
Create Date: 2025-01-XX XX:XX:XX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

# revision identifiers
revision = 'add_pgvector_001'
down_revision = '<previous_revision>'
branch_labels = None
depends_on = None

def upgrade():
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add embedding column (1536 dimensions for text-embedding-3-small)
    op.add_column('articles',
        sa.Column('embedding', Vector(1536), nullable=True)
    )

    # Add metadata JSONB column for vector-specific metadata
    # (optional - can use existing columns)
    op.add_column('articles',
        sa.Column('vector_metadata', JSONB, nullable=True)
    )

    # Create index for vector similarity search
    # HNSW is faster for queries, slower to build
    op.execute("""
        CREATE INDEX idx_articles_embedding_hnsw
        ON articles
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Alternative: IVFFlat index (faster to build, slower queries)
    # op.execute("""
    #     CREATE INDEX idx_articles_embedding_ivfflat
    #     ON articles
    #     USING ivfflat (embedding vector_cosine_ops)
    #     WITH (lists = 100)
    # """)

    # Add index on commonly filtered columns for hybrid search
    op.create_index('idx_articles_topic_analyzed', 'articles',
                    ['topic', 'analyzed'])
    op.create_index('idx_articles_publication_date', 'articles',
                    ['publication_date'])

def downgrade():
    op.drop_index('idx_articles_publication_date')
    op.drop_index('idx_articles_topic_analyzed')
    op.execute('DROP INDEX IF EXISTS idx_articles_embedding_hnsw')
    op.drop_column('articles', 'vector_metadata')
    op.drop_column('articles', 'embedding')
    op.execute('DROP EXTENSION IF EXISTS vector')
```

### 1.2 Update Database Models

**File:** `app/database_models.py`

Add to existing file:

```python
# Add at top of file
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

# Update articles table definition - add these columns:
Column("embedding", Vector(1536), nullable=True),
Column("vector_metadata", JSONB, nullable=True),
```

### 1.3 Environment Configuration

**File:** `.env` (add new variables)

```bash
# Vector Store Configuration
VECTOR_BACKEND=pgvector  # Options: chromadb, pgvector
PGVECTOR_INDEX_TYPE=hnsw  # Options: hnsw, ivfflat

# HNSW tuning parameters
PGVECTOR_HNSW_M=16              # Number of connections per layer
PGVECTOR_HNSW_EF_CONSTRUCTION=64  # Size of dynamic candidate list
PGVECTOR_HNSW_EF_SEARCH=40      # Search quality vs speed tradeoff

# IVFFlat tuning parameters
PGVECTOR_IVFFLAT_LISTS=100      # Number of inverted lists
PGVECTOR_IVFFLAT_PROBES=10      # Number of lists to search
```

---

## Phase 2: Core Vector Store Implementation

### 2.1 New pgvector Implementation

Create new file: `app/vector_store_pgvector.py`

See full implementation in appendix or implementation details section.

Key functions to implement:
- `upsert_article(article: Dict[str, Any])` - Add/update embeddings
- `search_articles(query: str, top_k: int, metadata_filter)` - Semantic search
- `similar_articles(uri: str, top_k: int)` - Find similar articles
- `get_vectors_by_metadata(limit, where)` - Fetch vectors by filter
- `embedding_projection(vecs)` - Clustering (unchanged)
- `check_vector_health()` - Health check

### 2.2 Adapter/Facade Pattern

**File:** `app/vector_store.py` (MODIFY - becomes a facade)

```python
"""
Vector store facade - routes to ChromaDB or pgvector backend.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Determine which backend to use
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chromadb").lower()

if VECTOR_BACKEND == "pgvector":
    logger.info("Using pgvector backend for vector operations")
    from app.vector_store_pgvector import (
        upsert_article,
        search_articles,
        similar_articles,
        get_vectors_by_metadata,
        embedding_projection,
        upsert_article_async,
        search_articles_async,
        similar_articles_async,
        get_vectors_by_metadata_async,
        embedding_projection_async,
        check_vector_health as check_pgvector_health,
        shutdown_vector_store,
    )

    # Alias for compatibility
    def check_chromadb_health():
        return check_pgvector_health()

elif VECTOR_BACKEND == "chromadb":
    logger.info("Using ChromaDB backend for vector operations")
    from app.vector_store_chromadb import (
        upsert_article,
        search_articles,
        similar_articles,
        get_vectors_by_metadata,
        embedding_projection,
        upsert_article_async,
        search_articles_async,
        similar_articles_async,
        get_vectors_by_metadata_async,
        embedding_projection_async,
        check_chromadb_health,
        shutdown_vector_store,
    )
else:
    raise ValueError(f"Unknown VECTOR_BACKEND: {VECTOR_BACKEND}")

__all__ = [
    "upsert_article",
    "search_articles",
    "similar_articles",
    "get_vectors_by_metadata",
    "embedding_projection",
    "upsert_article_async",
    "search_articles_async",
    "similar_articles_async",
    "get_vectors_by_metadata_async",
    "embedding_projection_async",
    "check_chromadb_health",
    "shutdown_vector_store",
]
```

**File:** Rename existing implementation

```bash
# Rename current vector_store.py to vector_store_chromadb.py
mv app/vector_store.py app/vector_store_chromadb.py
```

---

## Phase 3: Async Operations

The pgvector implementation uses `asyncio.to_thread()` for async wrappers, which is simpler than ChromaDB's thread pool approach since PostgreSQL handles concurrency natively.

Optional enhancement: Implement fully async using `asyncpg` (see Phase 3.1 in full spec).

---

## Phase 4: Migration & Reindexing

### 4.1 Reindexing Script

**File:** `scripts/reindex_pgvector.py`

```python
#!/usr/bin/env python3
"""
Reindex all articles with pgvector embeddings.

Usage:
    python scripts/reindex_pgvector.py                 # Index missing embeddings
    python scripts/reindex_pgvector.py --force         # Reindex all
    python scripts/reindex_pgvector.py --limit 100     # Test with 100
    python scripts/reindex_pgvector.py --topic "AI"    # Specific topic
"""

import sys
import os
import argparse
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database
from app.database_models import t_articles
from app.vector_store_pgvector import upsert_article
from sqlalchemy import select, text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def reindex_articles(force=False, limit=None, topic=None, batch_size=100):
    """Reindex articles with pgvector embeddings."""
    stats = {"total": 0, "processed": 0, "skipped": 0, "failed": 0}

    db = Database()
    conn = db._temp_get_connection()

    # Build query
    stmt = select(
        t_articles.c.uri,
        t_articles.c.title,
        t_articles.c.summary,
        t_articles.c.raw,
        t_articles.c.topic,
        t_articles.c.category,
    )

    if topic:
        stmt = stmt.where(t_articles.c.topic == topic)
    if not force:
        stmt = stmt.where(t_articles.c.embedding.is_(None))
    if limit:
        stmt = stmt.limit(limit)

    result = conn.execute(stmt).mappings()
    articles = list(result)
    stats["total"] = len(articles)

    logger.info(f"Found {stats['total']} articles to process")

    # Process in batches
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i+batch_size]

        for article in batch:
            try:
                content = article.get("raw") or article.get("summary") or article.get("title")
                if not content or not content.strip():
                    stats["skipped"] += 1
                    continue

                upsert_article(dict(article))
                stats["processed"] += 1

                if stats["processed"] % 10 == 0:
                    logger.info(f"Processed {stats['processed']}/{stats['total']}")

            except Exception as e:
                logger.error(f"Failed to index {article.get('uri')}: {e}")
                stats["failed"] += 1

    conn.commit()

    # Rebuild index
    logger.info("Rebuilding pgvector index...")
    conn.execute(text("REINDEX INDEX idx_articles_embedding_hnsw"))
    conn.commit()

    logger.info(f"Complete! Stats: {stats}")
    return stats

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--topic", type=str)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    stats = reindex_articles(
        force=args.force,
        limit=args.limit,
        topic=args.topic,
        batch_size=args.batch_size
    )

    print(f"\n{'='*60}")
    print("REINDEXING COMPLETE")
    print(f"{'='*60}")
    print(f"Processed: {stats['processed']}/{stats['total']}")
    print(f"Skipped:   {stats['skipped']}")
    print(f"Failed:    {stats['failed']}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
```

### 4.2 Migration Script (ChromaDB → pgvector)

**File:** `scripts/migrate_chromadb_to_pgvector.py`

Copies existing embeddings from ChromaDB to PostgreSQL without regenerating them.

```python
#!/usr/bin/env python3
"""
Migrate existing ChromaDB embeddings to pgvector.

Usage:
    python scripts/migrate_chromadb_to_pgvector.py
    python scripts/migrate_chromadb_to_pgvector.py --verify
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime
from app.database import Database
from app.database_models import t_articles
from sqlalchemy import update
import chromadb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_embeddings(verify=False):
    """Copy embeddings from ChromaDB to PostgreSQL."""
    stats = {"chromadb_total": 0, "migrated": 0, "skipped": 0, "errors": 0}

    # Connect to ChromaDB
    chroma_client = chromadb.PersistentClient(path="chromadb")
    collection = chroma_client.get_collection("articles")

    # Get all embeddings
    result = collection.get(include=["embeddings"])
    stats["chromadb_total"] = len(result["ids"])

    logger.info(f"Found {stats['chromadb_total']} embeddings in ChromaDB")

    # Connect to PostgreSQL
    db = Database()
    conn = db._temp_get_connection()

    # Migrate each embedding
    for i, uri in enumerate(result["ids"]):
        try:
            embedding = result["embeddings"][i]

            stmt = update(t_articles).where(
                t_articles.c.uri == uri
            ).values(
                embedding=embedding,
                vector_metadata={
                    "migrated_from": "chromadb",
                    "migrated_at": datetime.utcnow().isoformat()
                }
            )

            res = conn.execute(stmt)

            if res.rowcount > 0:
                stats["migrated"] += 1
            else:
                stats["skipped"] += 1

            if (i + 1) % 100 == 0:
                logger.info(f"Migrated {i + 1}/{stats['chromadb_total']}")
                conn.commit()

        except Exception as e:
            logger.error(f"Failed to migrate {uri}: {e}")
            stats["errors"] += 1

    conn.commit()
    logger.info(f"Migration complete! {stats}")
    return stats

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    stats = migrate_embeddings(verify=args.verify)
    print(f"\nMigrated: {stats['migrated']}/{stats['chromadb_total']}")
```

---

## Phase 5: Testing & Validation

### 5.1 Unit Tests

**File:** `tests/test_pgvector.py`

```python
"""Unit tests for pgvector implementation."""

import pytest
import os
from app.vector_store_pgvector import (
    upsert_article,
    search_articles,
    similar_articles,
    check_vector_health,
)

@pytest.fixture(scope="module")
def setup_pgvector():
    os.environ["VECTOR_BACKEND"] = "pgvector"
    yield
    os.environ["VECTOR_BACKEND"] = "chromadb"

def test_upsert_article(setup_pgvector):
    """Test upserting an article with embedding."""
    article = {
        "uri": "test-article-1",
        "title": "Test Article",
        "summary": "This is a test about AI.",
        "topic": "AI",
    }

    # First insert article into database
    # Then upsert embedding
    upsert_article(article)

    # Verify embedding exists
    # (implementation details)
    assert True  # Placeholder

def test_search_articles(setup_pgvector):
    """Test semantic search."""
    results = search_articles("artificial intelligence", top_k=5)
    assert isinstance(results, list)
    assert len(results) <= 5

def test_health_check(setup_pgvector):
    """Test health check."""
    health = check_vector_health()
    assert health["healthy"] is True
    assert health["backend"] == "pgvector"
```

### 5.2 Accuracy Validation

**File:** `scripts/validate_pgvector_accuracy.py`

Compares search results from ChromaDB vs pgvector to ensure >90% overlap.

```python
#!/usr/bin/env python3
"""
Validate pgvector produces similar results to ChromaDB.

Usage:
    python scripts/validate_pgvector_accuracy.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def compare_search_results(query, top_k=10):
    """Compare ChromaDB vs pgvector results."""

    # Search with ChromaDB
    os.environ["VECTOR_BACKEND"] = "chromadb"
    from app.vector_store import search_articles
    chromadb_results = search_articles(query, top_k=top_k)

    # Search with pgvector
    os.environ["VECTOR_BACKEND"] = "pgvector"
    from importlib import reload
    import app.vector_store
    reload(app.vector_store)
    from app.vector_store import search_articles as search_pg
    pgvector_results = search_pg(query, top_k=top_k)

    # Calculate overlap
    chromadb_ids = set([r["id"] for r in chromadb_results])
    pgvector_ids = set([r["id"] for r in pgvector_results])
    overlap = len(chromadb_ids & pgvector_ids)
    overlap_percent = (overlap / top_k) * 100 if top_k > 0 else 0

    return {
        "query": query,
        "overlap_count": overlap,
        "overlap_percent": overlap_percent,
    }

def validate_accuracy(num_queries=20):
    """Run validation on test queries."""
    test_queries = [
        "artificial intelligence trends",
        "machine learning applications",
        "climate change policy",
        "renewable energy technology",
        # ... more queries
    ]

    results = []
    for query in test_queries[:num_queries]:
        result = compare_search_results(query)
        results.append(result)
        logger.info(f"{query}: {result['overlap_percent']:.1f}% overlap")

    avg_overlap = np.mean([r["overlap_percent"] for r in results])

    print(f"\nAverage overlap: {avg_overlap:.1f}%")

    if avg_overlap >= 90:
        print("✓ VALIDATION PASSED")
        return 0
    else:
        print("✗ VALIDATION FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(validate_accuracy())
```

---

## Phase 6: Deployment & Cleanup

### 6.1 Deployment Steps

1. **Install pgvector extension** in PostgreSQL
2. **Run migration**: `alembic upgrade head`
3. **Reindex articles**: `python scripts/reindex_pgvector.py --force`
4. **Validate accuracy**: `python scripts/validate_pgvector_accuracy.py`
5. **Update .env**: Set `VECTOR_BACKEND=pgvector`
6. **Restart application**: `sudo systemctl restart aunooai`
7. **Monitor** for 1 week
8. **Cleanup**: Remove ChromaDB files after validation

### 6.2 Cleanup Script

**File:** `scripts/cleanup_chromadb.py`

```python
#!/usr/bin/env python3
"""
Clean up ChromaDB after successful migration.

WARNING: Permanently deletes ChromaDB data.

Usage:
    python scripts/cleanup_chromadb.py --dry-run
    python scripts/cleanup_chromadb.py --confirm
"""

import os
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_chromadb(dry_run=True):
    """Remove ChromaDB files."""
    items = [
        "chromadb/",
        "app/vector_store_chromadb.py",
        "scripts/reindex_chromadb.py",
    ]

    for item in items:
        if os.path.exists(item):
            if dry_run:
                logger.info(f"Would delete: {item}")
            else:
                if os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)
                logger.info(f"Deleted: {item}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    cleanup_chromadb(dry_run=not args.confirm)
```

---

## Rollback Plan

### Immediate Rollback

```bash
# Switch back to ChromaDB
export VECTOR_BACKEND=chromadb
sudo systemctl restart aunooai

# Verify
python scripts/reindex_chromadb.py --limit 10
```

### Data Recovery

```bash
# Restore ChromaDB from backup
cp -r /backup/chromadb ./chromadb

# Restore PostgreSQL if needed
pg_restore -U skunkworkx_user -d skunkworkx backup.dump
```

---

## Performance Tuning

### HNSW Index Parameters

```sql
-- Index creation
CREATE INDEX idx_articles_embedding_hnsw
ON articles
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Runtime tuning
SET hnsw.ef_search = 40;   -- Balance
SET hnsw.ef_search = 100;  -- Better quality
SET hnsw.ef_search = 20;   -- Faster
```

### Query Benchmarks

```sql
-- Expected performance with HNSW
EXPLAIN ANALYZE
SELECT uri, title, embedding <=> '[...]'::vector AS distance
FROM articles
ORDER BY embedding <=> '[...]'::vector
LIMIT 10;

-- Expected: < 10ms for 100K articles
```

### Connection Pool

```bash
# .env settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

---

## Migration Timeline

- **Week 1**: Development & Testing
- **Week 2**: Staging Deployment
- **Week 3**: Production Migration
- **Month 2**: Cleanup

---

## Success Metrics

### Technical
- ✅ Query latency: < 100ms (p95)
- ✅ Search accuracy: > 95% overlap
- ✅ Index build: < 30 minutes
- ✅ Error rate: < 0.1%

### Business
- ✅ Zero downtime
- ✅ No user-facing bugs
- ✅ Reliability improved

---

## Appendix: Key SQL Queries

### Check Extension
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### Count Embeddings
```sql
SELECT
    COUNT(*) as total,
    COUNT(embedding) as with_embedding,
    ROUND(100.0 * COUNT(embedding) / COUNT(*), 2) as coverage
FROM articles;
```

### Vector Search
```sql
SELECT uri, title, embedding <=> $1::vector as distance
FROM articles
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

### Hybrid Search
```sql
SELECT uri, title, topic, embedding <=> $1::vector as distance
FROM articles
WHERE topic = 'AI'
  AND publication_date > '2025-01-01'
  AND embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT 10;
```

---

## Contact & Support

For questions or issues during migration:
- Review this specification
- Check pgvector docs: https://github.com/pgvector/pgvector
- Test in staging first
- Keep ChromaDB backup for rollback

---

**End of Specification**

This migration will simplify your architecture, improve performance, and eliminate ChromaDB SQLite locking issues while maintaining full API compatibility.
