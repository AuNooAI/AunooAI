#!/usr/bin/env python3
"""
Migrate embeddings from ChromaDB to PostgreSQL pgvector.

This script:
1. Reads all embeddings from ChromaDB collection
2. Updates corresponding articles in PostgreSQL with embeddings
3. Creates IVFFlat index for efficient similarity search
4. Validates the migration

Usage:
    python scripts/migrate_chromadb_to_pgvector.py [--batch-size 100] [--skip-index]
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import get_database_instance
from app.vector_store import get_chroma_client, _get_collection
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_embeddings(batch_size: int = 100, skip_index: bool = False):
    """Migrate embeddings from ChromaDB to pgvector.

    Args:
        batch_size: Number of embeddings to process per batch
        skip_index: Skip index creation (useful for testing)
    """
    logger.info("Starting migration from ChromaDB to pgvector...")

    try:
        # Connect to ChromaDB
        logger.info("Connecting to ChromaDB...")
        collection = _get_collection()

        # Get all embeddings from ChromaDB
        logger.info("Fetching embeddings from ChromaDB...")
        result = collection.get(include=["embeddings", "metadatas"])

        ids = result.get("ids", [])
        embeddings = result.get("embeddings", [])
        metadatas = result.get("metadatas", [])

        if not ids:
            logger.warning("No embeddings found in ChromaDB collection")
            return

        total_embeddings = len(ids)
        logger.info(f"Found {total_embeddings} embeddings in ChromaDB")

        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL...")
        db = get_database_instance()
        conn = db._temp_get_connection()

        # Migrate embeddings in batches
        logger.info(f"Migrating embeddings in batches of {batch_size}...")
        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for i in tqdm(range(0, total_embeddings, batch_size), desc="Migrating embeddings"):
            batch_ids = ids[i:i + batch_size]
            batch_embeddings = embeddings[i:i + batch_size]

            for uri, embedding in zip(batch_ids, batch_embeddings):
                try:
                    # Convert embedding to PostgreSQL array format
                    embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'

                    # Check if article exists
                    check_stmt = text("SELECT uri FROM articles WHERE uri = :uri")
                    result = conn.execute(check_stmt, {"uri": uri})

                    if not result.first():
                        logger.debug(f"Article {uri} not found in database, skipping")
                        skipped_count += 1
                        continue

                    # Update article with embedding
                    # Use CAST to avoid parameter binding issues with ::vector syntax
                    update_stmt = text("""
                        UPDATE articles
                        SET embedding = CAST(:embedding AS vector)
                        WHERE uri = :uri
                    """)

                    conn.execute(update_stmt, {"embedding": embedding_str, "uri": uri})
                    migrated_count += 1

                except Exception as exc:
                    logger.error(f"Failed to migrate embedding for {uri}: {exc}")
                    error_count += 1

            # Commit batch
            conn.commit()
            logger.debug(f"Committed batch {i // batch_size + 1}")

        logger.info(f"Migration complete:")
        logger.info(f"  - Migrated: {migrated_count}")
        logger.info(f"  - Skipped: {skipped_count}")
        logger.info(f"  - Errors: {error_count}")

        # Create IVFFlat index for efficient similarity search
        if not skip_index:
            logger.info("Creating IVFFlat index for vector similarity search...")

            try:
                # Calculate number of lists for IVFFlat index
                # Rule of thumb: lists = sqrt(total_rows)
                # For 10k articles: ~100 lists, for 100k: ~316 lists
                count_stmt = text("SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL")
                result = conn.execute(count_stmt)
                row_count = result.scalar()

                if row_count < 100:
                    logger.warning(f"Only {row_count} articles with embeddings. "
                                   "IVFFlat index requires at least 100 rows for training.")
                    lists = max(10, int(row_count ** 0.5))
                else:
                    lists = int(row_count ** 0.5)

                logger.info(f"Creating IVFFlat index with {lists} lists for {row_count} articles...")

                # Drop existing index if it exists
                conn.execute(text("DROP INDEX IF EXISTS articles_embedding_idx"))

                # Create IVFFlat index
                # Using cosine distance (<=> operator)
                create_index_stmt = text(f"""
                    CREATE INDEX articles_embedding_idx
                    ON articles
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = {lists})
                """)

                conn.execute(create_index_stmt)
                conn.commit()

                logger.info("IVFFlat index created successfully")

            except Exception as exc:
                logger.error(f"Failed to create index: {exc}")
                logger.info("You can create the index manually later with:")
                logger.info("  CREATE INDEX articles_embedding_idx ON articles "
                            "USING ivfflat (embedding vector_cosine_ops) WITH (lists = <N>);")

        # Validate migration
        logger.info("Validating migration...")
        validate_stmt = text("""
            SELECT
                COUNT(*) as total_articles,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL) as with_embeddings
            FROM articles
        """)
        result = conn.execute(validate_stmt)
        row = result.first()

        logger.info(f"Validation results:")
        logger.info(f"  - Total articles: {row[0]}")
        logger.info(f"  - Articles with embeddings: {row[1]}")
        logger.info(f"  - Coverage: {row[1] / row[0] * 100:.1f}%" if row[0] > 0 else "  - Coverage: N/A")

        logger.info("Migration completed successfully!")

    except Exception as exc:
        logger.error(f"Migration failed: {exc}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate embeddings from ChromaDB to PostgreSQL pgvector"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of embeddings to process per batch (default: 100)"
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip index creation (useful for testing)"
    )

    args = parser.parse_args()

    migrate_embeddings(batch_size=args.batch_size, skip_index=args.skip_index)


if __name__ == "__main__":
    main()
