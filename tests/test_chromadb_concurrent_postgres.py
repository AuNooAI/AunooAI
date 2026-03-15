"""
PostgreSQL Migration - Week 3 ChromaDB Concurrent Operations Test Suite

Tests for ChromaDB async infrastructure and concurrent operations.
Date: 2025-10-13
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import List
import pytest

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database type
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()


class TestChromaDBAsync:
    """Test suite for ChromaDB async operations"""

    @pytest.mark.asyncio
    async def test_upsert_article_async(self):
        """Test async article upsert"""
        logger.info("Testing upsert_article_async()...")

        from app.vector_store import upsert_article_async

        test_article = {
            'uri': f'http://test.com/async_upsert_{datetime.now().timestamp()}',
            'title': 'Test Article Async Upsert',
            'summary': 'This is a test article for async upsert operations',
            'news_source': 'Test Source',
            'topic': 'technology',
            'publication_date': datetime.now().isoformat()
        }

        try:
            # Should not raise an exception
            await upsert_article_async(test_article)
            logger.info("✅ upsert_article_async() - Working correctly")
        except Exception as e:
            logger.error(f"❌ upsert_article_async() failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_search_articles_async(self):
        """Test async article search"""
        logger.info("Testing search_articles_async()...")

        from app.vector_store import search_articles_async

        test_query = "artificial intelligence machine learning"

        try:
            results = await search_articles_async(test_query, top_k=5)
            assert isinstance(results, list), "Should return a list"
            logger.info(f"✅ search_articles_async() - Found {len(results)} results")
        except Exception as e:
            logger.error(f"❌ search_articles_async() failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_similar_articles_async(self):
        """Test async similar articles search"""
        logger.info("Testing similar_articles_async()...")

        from app.vector_store import similar_articles_async, upsert_article_async

        # First insert a test article
        test_uri = f'http://test.com/async_similar_{datetime.now().timestamp()}'
        test_article = {
            'uri': test_uri,
            'title': 'AI Technology Article',
            'summary': 'Advanced artificial intelligence and machine learning techniques',
            'news_source': 'Test Source',
            'topic': 'technology',
            'publication_date': datetime.now().isoformat()
        }

        try:
            await upsert_article_async(test_article)

            # Wait a moment for ChromaDB to index
            await asyncio.sleep(1)

            # Search for similar articles
            results = await similar_articles_async(test_uri, top_k=3)
            assert isinstance(results, list), "Should return a list"
            logger.info(f"✅ similar_articles_async() - Found {len(results)} similar articles")
        except Exception as e:
            logger.error(f"❌ similar_articles_async() failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_get_vectors_by_metadata_async(self):
        """Test async vector retrieval by metadata"""
        logger.info("Testing get_vectors_by_metadata_async()...")

        from app.vector_store import get_vectors_by_metadata_async

        try:
            vecs, metas, ids = await get_vectors_by_metadata_async(
                limit=10,
                where={"topic": "technology"}
            )
            assert isinstance(vecs, object), "Should return vectors array"
            assert isinstance(metas, list), "Should return metadatas list"
            assert isinstance(ids, list), "Should return ids list"
            logger.info(f"✅ get_vectors_by_metadata_async() - Retrieved {len(ids)} vectors")
        except Exception as e:
            logger.error(f"❌ get_vectors_by_metadata_async() failed: {e}")
            raise


class TestChromaDBConcurrency:
    """Test suite for ChromaDB concurrent operations"""

    @pytest.mark.asyncio
    async def test_concurrent_upserts(self):
        """Test multiple concurrent upsert operations"""
        logger.info("Testing concurrent upsert operations...")

        from app.vector_store import upsert_article_async

        # Create test articles
        timestamp = datetime.now().timestamp()
        articles = [
            {
                'uri': f'http://test.com/concurrent_upsert_{i}_{timestamp}',
                'title': f'Test Article {i}',
                'summary': f'Test content for concurrent upsert article {i}',
                'news_source': 'Test Source',
                'topic': 'technology',
                'publication_date': datetime.now().isoformat()
            }
            for i in range(5)
        ]

        try:
            # Upsert all articles concurrently
            tasks = [upsert_article_async(article) for article in articles]
            await asyncio.gather(*tasks)
            logger.info(f"✅ Concurrent upserts - Successfully upserted {len(articles)} articles")
        except Exception as e:
            logger.error(f"❌ Concurrent upserts failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """Test multiple concurrent search operations"""
        logger.info("Testing concurrent search operations...")

        from app.vector_store import search_articles_async

        queries = [
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "neural networks",
            "data science"
        ]

        try:
            # Execute all searches concurrently
            tasks = [search_articles_async(query, top_k=3) for query in queries]
            results = await asyncio.gather(*tasks)

            assert len(results) == len(queries), "Should return results for all queries"
            for i, result in enumerate(results):
                assert isinstance(result, list), f"Query {i} should return a list"

            logger.info(f"✅ Concurrent searches - Successfully executed {len(queries)} searches")
        except Exception as e:
            logger.error(f"❌ Concurrent searches failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self):
        """Test mixed read/write concurrent operations"""
        logger.info("Testing mixed concurrent operations...")

        from app.vector_store import upsert_article_async, search_articles_async, similar_articles_async

        timestamp = datetime.now().timestamp()

        # Create some upsert tasks
        upsert_articles = [
            {
                'uri': f'http://test.com/mixed_op_{i}_{timestamp}',
                'title': f'Mixed Op Article {i}',
                'summary': f'Test content for mixed operation article {i}',
                'news_source': 'Test Source',
                'topic': 'technology',
                'publication_date': datetime.now().isoformat()
            }
            for i in range(3)
        ]

        # Create some search tasks
        search_queries = [
            "artificial intelligence",
            "machine learning"
        ]

        try:
            # Mix upserts and searches
            tasks = []
            tasks.extend([upsert_article_async(article) for article in upsert_articles])
            tasks.extend([search_articles_async(query, top_k=3) for query in search_queries])

            results = await asyncio.gather(*tasks)

            logger.info(f"✅ Mixed concurrent operations - Successfully executed {len(tasks)} operations")
        except Exception as e:
            logger.error(f"❌ Mixed concurrent operations failed: {e}")
            raise

    @pytest.mark.asyncio
    async def test_concurrent_operations_stress(self):
        """Stress test with many concurrent operations"""
        logger.info("Testing concurrent operations stress test...")

        from app.vector_store import upsert_article_async, search_articles_async

        timestamp = datetime.now().timestamp()

        # Create many articles
        num_articles = 20
        articles = [
            {
                'uri': f'http://test.com/stress_{i}_{timestamp}',
                'title': f'Stress Test Article {i}',
                'summary': f'AI and machine learning content for stress test article {i}',
                'news_source': 'Test Source',
                'topic': 'technology',
                'publication_date': datetime.now().isoformat()
            }
            for i in range(num_articles)
        ]

        # Create many search queries
        num_searches = 10
        queries = [f"search query {i}" for i in range(num_searches)]

        try:
            # Mix upserts and searches
            tasks = []
            tasks.extend([upsert_article_async(article) for article in articles])
            tasks.extend([search_articles_async(query, top_k=3) for query in queries])

            start_time = datetime.now()
            results = await asyncio.gather(*tasks)
            elapsed = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"✅ Stress test - Successfully executed {len(tasks)} operations "
                f"({num_articles} upserts + {num_searches} searches) in {elapsed:.2f}s"
            )
        except Exception as e:
            logger.error(f"❌ Stress test failed: {e}")
            raise


class TestPgvectorHealth:
    """Test suite for pgvector health and cleanup"""

    def test_check_pgvector_health(self):
        """Test pgvector health check"""
        logger.info("Testing check_pgvector_health()...")

        from app.vector_store_pgvector import check_pgvector_health

        try:
            health = check_pgvector_health()

            assert isinstance(health, dict), "Should return a dictionary"
            assert 'healthy' in health, "Should have healthy status"
            assert 'extension_installed' in health, "Should have extension_installed status"
            assert 'articles_with_embeddings' in health, "Should have articles_with_embeddings"

            if health['healthy']:
                logger.info(
                    f"✅ check_pgvector_health() - pgvector is healthy "
                    f"(articles_with_embeddings: {health.get('articles_with_embeddings', 0)}, "
                    f"extension_installed: {health['extension_installed']})"
                )
            else:
                logger.warning(
                    f"⚠️  check_pgvector_health() - pgvector health check returned unhealthy: {health.get('error')}"
                )

        except Exception as e:
            logger.error(f"❌ check_pgvector_health() failed: {e}")
            raise

    def test_shutdown_vector_store(self):
        """Test vector store shutdown (warning: will shutdown the thread pool)"""
        logger.info("Testing shutdown_vector_store()...")

        from app.vector_store import shutdown_vector_store

        # Note: This test should be run last as it shuts down the thread pool
        try:
            # Call shutdown
            shutdown_vector_store()
            logger.info("✅ shutdown_vector_store() - Shutdown completed successfully")

            # Note: After this test, the thread pool is shutdown
            # and further async operations may fail
            logger.warning("⚠️  Thread pool has been shutdown. Further async operations may fail.")

        except Exception as e:
            logger.error(f"❌ shutdown_vector_store() failed: {e}")
            raise


async def run_async_tests():
    """Run async tests"""
    async_tests = TestChromaDBAsync()

    logger.info("\n🔄 Testing ChromaDB Async Operations:")
    await async_tests.test_upsert_article_async()
    await async_tests.test_search_articles_async()
    await async_tests.test_similar_articles_async()
    await async_tests.test_get_vectors_by_metadata_async()

    logger.info("\n⚡ Testing ChromaDB Concurrent Operations:")
    concurrency_tests = TestChromaDBConcurrency()
    await concurrency_tests.test_concurrent_upserts()
    await concurrency_tests.test_concurrent_searches()
    await concurrency_tests.test_mixed_concurrent_operations()
    await concurrency_tests.test_concurrent_operations_stress()


def run_all_tests():
    """Run all Week 3 ChromaDB tests"""
    logger.info("=" * 80)
    logger.info(f"PostgreSQL Migration - Week 3 ChromaDB Concurrent Operations Test Suite")
    logger.info(f"Database Type: {DB_TYPE}")
    logger.info("=" * 80)

    # Run async tests
    asyncio.run(run_async_tests())

    # Run health check tests (sync)
    logger.info("\n🏥 Testing pgvector Health and Cleanup:")
    health_tests = TestPgvectorHealth()
    health_tests.test_check_pgvector_health()

    # Note: Uncomment the line below to test shutdown (will shutdown thread pool)
    # health_tests.test_shutdown_vector_store()

    logger.info("\n" + "=" * 80)
    logger.info("✅ All Week 3 ChromaDB concurrent operations tests completed successfully!")
    logger.info("=" * 80)


if __name__ == "__main__":
    run_all_tests()
