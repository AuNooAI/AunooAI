#!/usr/bin/env python3
"""
Test pgvector migration and functionality.

This script tests:
1. Health check
2. Search functionality
3. Similar articles functionality
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from app.vector_store import (
    check_chromadb_health,
    search_articles,
    similar_articles,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_health():
    """Test pgvector health check."""
    logger.info("Testing pgvector health...")
    health = check_chromadb_health()

    logger.info(f"Health status: {health}")

    assert health['healthy'], "pgvector is not healthy"
    assert health['extension_installed'], "pgvector extension not installed"
    assert health['articles_with_embeddings'] > 0, "No articles with embeddings"

    logger.info(f"✓ Health check passed: {health['articles_with_embeddings']} articles with embeddings")


def test_search():
    """Test semantic search."""
    logger.info("Testing semantic search...")

    query = "Gaza conflict peace negotiations"
    results = search_articles(query, top_k=5)

    logger.info(f"Search returned {len(results)} results")

    if results:
        logger.info("Top result:")
        logger.info(f"  - Title: {results[0]['metadata'].get('title', 'N/A')}")
        logger.info(f"  - Score: {results[0]['score']:.4f}")
        logger.info(f"  - URI: {results[0]['id']}")

    assert len(results) > 0, "Search returned no results"
    logger.info("✓ Search test passed")


def test_similar_articles():
    """Test similar articles functionality."""
    logger.info("Testing similar articles...")

    # Use the first article URI from the previous search
    test_uri = "https://www.yahoo.com/news/articles/idf-must-ensure-lessons-october-212955053.html"

    results = similar_articles(test_uri, top_k=3)

    logger.info(f"Similar articles returned {len(results)} results")

    if results:
        logger.info("Top similar article:")
        logger.info(f"  - Title: {results[0]['metadata'].get('title', 'N/A')}")
        logger.info(f"  - Score: {results[0]['score']:.4f}")

    assert len(results) > 0, "Similar articles returned no results"
    logger.info("✓ Similar articles test passed")


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Testing pgvector migration")
    logger.info("=" * 60)

    try:
        test_health()
        logger.info("")

        test_search()
        logger.info("")

        test_similar_articles()
        logger.info("")

        logger.info("=" * 60)
        logger.info("✓ All tests passed!")
        logger.info("=" * 60)

    except Exception as exc:
        logger.error(f"✗ Test failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
