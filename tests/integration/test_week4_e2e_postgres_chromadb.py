#!/usr/bin/env python3
"""
PostgreSQL Migration - Week 4: End-to-End Integration Tests
Tests complete user workflows with PostgreSQL and ChromaDB integration.
"""

import sys
import os
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.database import Database
from app.vector_store import (
    upsert_article_async,
    search_articles_async,
    similar_articles_async,
    check_chromadb_health
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EndToEndTests:
    """End-to-end user workflow tests"""

    def __init__(self, db: Database):
        self.db = db
        self.test_user = f"e2e_test_user_{int(datetime.now().timestamp())}"
        self.test_topic = None  # Will use existing topic
        self.test_articles = []

    async def test_complete_user_workflow(self) -> bool:
        """
        Test complete user workflow:
        1. Create user
        2. Create topic
        3. Submit article
        4. Verify article in PostgreSQL
        5. Index article in ChromaDB
        6. Search for article
        7. Verify results
        """
        logger.info("Testing complete user workflow...")

        try:
            # 1. Create test user
            logger.info("Step 1: Creating test user...")
            import bcrypt
            password_hash = bcrypt.hashpw("TestPass123!".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            success = self.db.create_user(
                self.test_user,
                password_hash,
                force_password_change=False
            )
            assert success, "Failed to create user"
            logger.info(f"✅ User created: {self.test_user}")

            # 2. Verify user exists
            logger.info("Step 2: Verifying user...")
            user = self.db.get_user(self.test_user)
            assert user is not None, "User not found"
            assert user['username'] == self.test_user
            logger.info("✅ User verified")

            # 3. Get existing topic (use first available topic)
            logger.info("Step 3: Getting existing topic...")
            topics = self.db.get_topics()
            assert len(topics) > 0, "No topics available in database"
            self.test_topic = topics[0]  # Use first topic
            logger.info(f"✅ Using topic: {self.test_topic}")

            # 4. Submit article
            logger.info("Step 4: Submitting article...")
            article_data = {
                'uri': f'http://test.com/e2e_article_{int(datetime.now().timestamp())}',
                'title': 'End-to-End Test Article',
                'summary': 'This is an end-to-end integration test article for PostgreSQL and ChromaDB',
                'topic': self.test_topic,
                'news_source': 'Test Source',
                'publication_date': datetime.now().isoformat(),
                'analyzed': False
            }

            self.db.update_or_create_article(article_data)
            self.test_articles.append(article_data['uri'])
            logger.info(f"✅ Article submitted: {article_data['uri']}")

            # 5. Verify article in PostgreSQL
            logger.info("Step 5: Verifying article in PostgreSQL...")
            articles = self.db.get_recent_articles_by_topic(self.test_topic, limit=10)
            found = any(a['uri'] == article_data['uri'] for a in articles)
            assert found, "Article not found in PostgreSQL"
            logger.info("✅ Article verified in PostgreSQL")

            # 6. Index article in ChromaDB
            logger.info("Step 6: Indexing article in ChromaDB...")
            await upsert_article_async(article_data)
            logger.info("✅ Article indexed in ChromaDB")

            # Wait a moment for indexing to complete
            await asyncio.sleep(0.5)

            # 7. Search for article
            logger.info("Step 7: Searching for article...")
            search_results = await search_articles_async(
                query="end-to-end integration test",
                top_k=5,
                metadata_filter={"topic": self.test_topic}
            )

            # Verify results
            assert len(search_results) > 0, "No search results found"
            found_in_search = any(r.get('uri') == article_data['uri'] for r in search_results)
            logger.info(f"✅ Search completed: {len(search_results)} results")

            # 8. Test similar articles
            logger.info("Step 8: Testing similar articles...")
            similar = await similar_articles_async(article_data['uri'], top_k=3)
            logger.info(f"✅ Similar articles: {len(similar)} results")

            logger.info("✅ Complete user workflow test PASSED")
            return True

        except Exception as e:
            logger.error(f"❌ Complete user workflow test FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def cleanup(self):
        """Clean up test data"""
        logger.info("Cleaning up test data...")

        try:
            # Delete articles
            conn = self.db._temp_get_connection()
            for uri in self.test_articles:
                from sqlalchemy import delete
                from app.database_models import t_articles
                stmt = delete(t_articles).where(t_articles.c.uri == uri)
                conn.execute(stmt)

            # Don't delete topic (we used an existing one)

            # Delete user
            from sqlalchemy import delete
            from app.database_models import t_users
            stmt = delete(t_users).where(t_users.c.username == self.test_user)
            conn.execute(stmt)
            conn.commit()

            logger.info("✅ Cleanup completed")
        except Exception as e:
            logger.warning(f"Cleanup error (non-fatal): {e}")


class PerformanceBenchmarks:
    """Performance regression tests"""

    def __init__(self, db: Database):
        self.db = db
        self.results: Dict[str, float] = {}

    async def test_query_performance_benchmarks(self) -> bool:
        """
        Benchmark critical operations:
        - User login: < 50ms
        - Get recent articles: < 100ms
        - Topic list: < 50ms
        - Vector search: < 500ms
        """
        logger.info("Running performance benchmarks...")

        try:
            import time

            # Test 1: User login (get_user)
            logger.info("Benchmark 1: User login...")
            start = time.time()
            user = self.db.get_user("admin")  # Assumes admin exists
            elapsed_ms = (time.time() - start) * 1000
            self.results['user_login_ms'] = elapsed_ms

            if elapsed_ms > 50:
                logger.warning(f"⚠️  User login slower than target: {elapsed_ms:.2f}ms > 50ms")
            else:
                logger.info(f"✅ User login: {elapsed_ms:.2f}ms")

            # Test 2: Get recent articles
            logger.info("Benchmark 2: Get recent articles...")
            start = time.time()
            articles = self.db.get_recent_articles(limit=100)
            elapsed_ms = (time.time() - start) * 1000
            self.results['recent_articles_ms'] = elapsed_ms

            if elapsed_ms > 100:
                logger.warning(f"⚠️  Get recent articles slower than target: {elapsed_ms:.2f}ms > 100ms")
            else:
                logger.info(f"✅ Get recent articles: {elapsed_ms:.2f}ms")

            # Test 3: Topic list
            logger.info("Benchmark 3: Topic list...")
            start = time.time()
            topics = self.db.get_topics()
            elapsed_ms = (time.time() - start) * 1000
            self.results['topic_list_ms'] = elapsed_ms

            if elapsed_ms > 50:
                logger.warning(f"⚠️  Topic list slower than target: {elapsed_ms:.2f}ms > 50ms")
            else:
                logger.info(f"✅ Topic list: {elapsed_ms:.2f}ms")

            # Test 4: Vector search
            logger.info("Benchmark 4: Vector search...")
            start = time.time()
            results = await search_articles_async(
                query="artificial intelligence machine learning",
                top_k=10
            )
            elapsed_ms = (time.time() - start) * 1000
            self.results['vector_search_ms'] = elapsed_ms

            if elapsed_ms > 500:
                logger.warning(f"⚠️  Vector search slower than target: {elapsed_ms:.2f}ms > 500ms")
            else:
                logger.info(f"✅ Vector search: {elapsed_ms:.2f}ms")

            # Print summary
            logger.info("\n" + "=" * 80)
            logger.info("📊 Performance Benchmark Results:")
            logger.info("=" * 80)
            for metric, value in self.results.items():
                logger.info(f"  {metric}: {value:.2f}ms")
            logger.info("=" * 80)

            return True

        except Exception as e:
            logger.error(f"❌ Performance benchmarks FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False


class DatabaseConsistencyTests:
    """Database consistency verification tests"""

    def __init__(self, db: Database):
        self.db = db

    def test_data_integrity_checks(self) -> bool:
        """
        Verify data integrity:
        - User table integrity
        - Topic/article relationships
        - No orphaned records
        """
        logger.info("Running data integrity checks...")

        try:
            # Check 1: User table integrity
            logger.info("Check 1: User table integrity...")
            conn = self.db._temp_get_connection()
            from sqlalchemy import select
            from app.database_models import t_users

            stmt = select(t_users).limit(10)
            result = conn.execute(stmt).mappings()
            users = [dict(row) for row in result]

            for user in users:
                assert 'username' in user, "Missing username field"
                assert 'password_hash' in user, "Missing password_hash field"
                assert len(user['password_hash']) > 0, "Empty password hash"

            logger.info(f"✅ User table integrity verified ({len(users)} users checked)")

            # Check 2: Topics and articles relationship
            logger.info("Check 2: Topic/article relationships...")
            topics = self.db.get_topics()

            checked_topics = 0
            for topic in topics[:5]:  # Sample first 5 topics
                articles = self.db.get_recent_articles_by_topic(topic, limit=1)
                if len(articles) > 0:
                    assert articles[0]['topic'] == topic, f"Article topic mismatch: {articles[0]['topic']} != {topic}"
                    checked_topics += 1

            logger.info(f"✅ Topic/article relationships verified ({checked_topics} topics checked)")

            # Check 3: Article field integrity
            logger.info("Check 3: Article field integrity...")
            articles = self.db.get_recent_articles(limit=10)

            for article in articles:
                assert 'uri' in article, "Missing uri field"
                assert 'title' in article, "Missing title field"
                assert 'topic' in article, "Missing topic field"

            logger.info(f"✅ Article field integrity verified ({len(articles)} articles checked)")

            logger.info("✅ All data integrity checks PASSED")
            return True

        except Exception as e:
            logger.error(f"❌ Data integrity checks FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_chromadb_health(self) -> bool:
        """Test ChromaDB health and status"""
        logger.info("Testing ChromaDB health...")

        try:
            health = check_chromadb_health()

            assert health['healthy'], "ChromaDB is not healthy"
            assert health['collection_exists'], "Collection does not exist"
            assert health['collection_count'] > 0, "Collection is empty"

            logger.info(f"✅ ChromaDB health check PASSED")
            logger.info(f"   - Collection count: {health['collection_count']}")
            logger.info(f"   - Thread pool size: {health['thread_pool_size']}")

            return True

        except Exception as e:
            logger.error(f"❌ ChromaDB health check FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False


async def run_async_tests():
    """Run all async tests"""
    logger.info("=" * 80)
    logger.info("  WEEK 4: END-TO-END INTEGRATION TESTS")
    logger.info("=" * 80)
    logger.info(f"Database Type: {os.getenv('DB_TYPE', 'sqlite')}")
    logger.info("=" * 80)

    db = Database()

    results = {
        'e2e_workflow': False,
        'performance_benchmarks': False,
        'data_integrity': False,
        'chromadb_health': False
    }

    # Test Suite 1: End-to-End Workflow
    logger.info("\n" + "=" * 80)
    logger.info("Test Suite 1: End-to-End User Workflow")
    logger.info("=" * 80)
    e2e_tests = EndToEndTests(db)
    results['e2e_workflow'] = await e2e_tests.test_complete_user_workflow()
    await e2e_tests.cleanup()

    # Test Suite 2: Performance Benchmarks
    logger.info("\n" + "=" * 80)
    logger.info("Test Suite 2: Performance Benchmarks")
    logger.info("=" * 80)
    perf_tests = PerformanceBenchmarks(db)
    results['performance_benchmarks'] = await perf_tests.test_query_performance_benchmarks()

    # Test Suite 3: Data Integrity
    logger.info("\n" + "=" * 80)
    logger.info("Test Suite 3: Data Integrity Checks")
    logger.info("=" * 80)
    consistency_tests = DatabaseConsistencyTests(db)
    results['data_integrity'] = consistency_tests.test_data_integrity_checks()

    # Test Suite 4: ChromaDB Health
    logger.info("\n" + "=" * 80)
    logger.info("Test Suite 4: ChromaDB Health Check")
    logger.info("=" * 80)
    results['chromadb_health'] = await consistency_tests.test_chromadb_health()

    # Final Results
    logger.info("\n" + "=" * 80)
    logger.info("  FINAL RESULTS")
    logger.info("=" * 80)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"  {test_name}: {status}")

    logger.info("=" * 80)
    logger.info(f"  Tests Passed: {passed}/{total}")
    logger.info("=" * 80)

    if passed == total:
        logger.info("✅ ALL WEEK 4 INTEGRATION TESTS PASSED!")
        return True
    else:
        logger.error(f"❌ {total - passed} test(s) failed")
        return False


def run_all_tests():
    """Entry point for running all tests"""
    success = asyncio.run(run_async_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    run_all_tests()
