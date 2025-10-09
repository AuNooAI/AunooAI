#!/usr/bin/env python
# flake8: noqa
"""Re-index all existing articles into ChromaDB.

Run with:
$ python scripts/reindex_chromadb.py

Optional arguments:
    --limit N           Only re-index first N rows (for testing).
    --force             Skip confirmation prompt when deleting collection.
    --preserve-collection  Don't delete existing collection (just add/update articles).

The script fetches *articles* joined with *raw_articles* (if present) from the
SQLite database and calls *app.vector_store.upsert_article* for each row.

Note: New collections will use cosine distance metric for 0-1 similarity scores,
which is the standard for text embeddings and works optimally with OpenAI embeddings.
"""

import argparse
import logging
from pathlib import Path
import sys

# Ensure .env variables are loaded *before* any application modules that may
# read from os.environ during import time (e.g. vector_store).
from dotenv import load_dotenv  # type: ignore

load_dotenv()

# Ensure project root (parent of scripts/) is on PYTHONPATH so that 'app'
# package is importable even when this script is executed directly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Now we can import application modules
from app.config.settings import DATABASE_DIR  # type: ignore
from app.vector_store import upsert_article, get_chroma_client
from app.database import Database
from app.database_query_facade import DatabaseQueryFacade

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def check_collection_info(client):
    """Check if collection exists and what distance metric it uses."""
    try:
        collections = client.list_collections()
        if "articles" in collections:
            collection = client.get_collection("articles")
            metadata = collection.metadata or {}
            distance_metric = metadata.get("hnsw:space", "l2")  # l2 is ChromaDB default
            logger.info(f"Existing collection found using '{distance_metric}' distance metric")
            
            # Count existing articles
            count = collection.count()
            logger.info(f"Collection contains {count} articles")
            
            return True, distance_metric, count
        else:
            logger.info("No existing 'articles' collection found")
            return False, None, 0
    except Exception as e:
        logger.warning(f"Could not check collection info: {e}")
        return False, None, 0


def main():
    parser = argparse.ArgumentParser(description="Re-index articles into ChromaDB")
    parser.add_argument("--limit", type=int, help="Re-index only first N articles")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--preserve-collection", action="store_true", 
                        help="Don't delete existing collection (just update articles)")
    args = parser.parse_args()

    # Initialize database connection (works with both SQLite and PostgreSQL)
    try:
        db = Database()
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database: %s", e)
        return 1
    client = get_chroma_client()
    
    # Check existing collection
    exists, current_metric, current_count = check_collection_info(client)
    
    if exists and not args.preserve_collection:
        logger.info("=" * 60)
        logger.info("DISTANCE METRIC INFORMATION:")
        logger.info("  Current: %s", current_metric)
        logger.info("  New:     cosine (recommended for text embeddings)")
        logger.info("=" * 60)
        
        if current_metric == "cosine":
            logger.info("✓ Collection already uses cosine distance - optimal for text!")
        else:
            logger.warning("⚠ Collection uses %s distance - cosine is better for text", current_metric)
            logger.info("  Benefits of switching to cosine:")
            logger.info("  • 0-1 similarity scores (easier to interpret)")
            logger.info("  • Optimized for OpenAI embeddings")
            logger.info("  • Standard for text similarity")
            logger.info("  • Less sensitive to document length")
        
        if not args.force:
            logger.info(f"\nThis will DELETE the existing collection with {current_count} articles")
            response = input("Continue? [y/N]: ")
            if response.lower() != 'y':
                logger.info("Aborted")
                return 0
        
        logger.info("Deleting existing collection...")
        try:
            client.delete_collection("articles")
            logger.info("✓ Collection deleted")
        except Exception as e:
            logger.error("Failed to delete collection: %s", e)
            return 1
    elif args.preserve_collection:
        logger.info("Preserving existing collection (--preserve-collection)")
    
    # Count articles to index
    total_articles = 0
    for _ in (DatabaseQueryFacade(db, logger)).get_iter_articles(args.limit):
        total_articles += 1
    
    logger.info(f"Will index {total_articles} articles from database")
    
    # Re-index articles
    total = 0
    failed = 0

    # TODO: Redundant with above!
    for i, article in enumerate((DatabaseQueryFacade(db, logger)).get_iter_articles(args.limit), 1):
        try:
            upsert_article(article)
            total += 1
            
            # Progress logging
            if i % 100 == 0 or i == total_articles:
                logger.info(f"Progress: {i}/{total_articles} articles ({i/total_articles*100:.1f}%)")
                
        except Exception as exc:  # pragma: no cover – keep going
            failed += 1
            logger.warning(
                "Failed to index %s: %s",
                article.get("uri"),
                exc,
            )
            
            # Stop if too many failures
            if failed > 10:
                logger.error("Too many failures, stopping")
                return 1
    
    logger.info("=" * 60)
    logger.info(f"✓ Successfully indexed {total} articles")
    if failed > 0:
        logger.warning(f"⚠ Failed to index {failed} articles")
    
    # Verify final collection
    try:
        collection = client.get_collection("articles")
        final_count = collection.count()
        final_metric = collection.metadata.get("hnsw:space", "l2")
        logger.info(f"✓ Final collection: {final_count} articles using '{final_metric}' distance")
    except Exception as e:
        logger.warning(f"Could not verify final collection: {e}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 