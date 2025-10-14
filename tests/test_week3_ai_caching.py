"""
PostgreSQL Migration - Week 3 AI Caching Test Suite

Tests for AI analysis caching methods migrated in Week 3.
Date: 2025-10-13
"""

import os
import logging
import json
from app.database import Database
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database type
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()


class TestAICaching:
    """Test suite for AI analysis caching methods migrated in Week 3"""

    def test_save_and_get_article_analysis_cache(self, db):
        """Test saving and retrieving article analysis cache"""
        logger.info("Testing save_article_analysis_cache() and get_article_analysis_cache()...")

        # First, create a test article in the articles table
        from sqlalchemy import insert, delete
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_test_{datetime.now().timestamp()}"
        test_content = "This is test analysis content for Week 3 migration"
        test_model = "gpt-4"
        test_analysis_type = "summary"
        test_metadata = {
            "temperature": 0.7,
            "max_tokens": 500,
            "prompt_version": "v1.2"
        }

        conn = db._temp_get_connection()

        try:
            # Create parent article first
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Test save cache
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content=test_content,
                model_used=test_model,
                metadata=test_metadata
            )
            assert result is True, "Should successfully save cache"

            # Test retrieve cache
            cached = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=test_model
            )

            assert cached is not None, "Should retrieve cached analysis"
            assert cached['content'] == test_content, "Should match saved content"
            assert cached['model_used'] == test_model, "Should match model used"
            assert 'generated_at' in cached, "Should have generated_at timestamp"
            assert cached['metadata'] == test_metadata, "Should match metadata"

            logger.info("✅ save_article_analysis_cache() and get_article_analysis_cache() - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_cache_update_existing_entry(self, db):
        """Test updating an existing cache entry"""
        logger.info("Testing cache update for existing entry...")

        from sqlalchemy import insert, delete
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_update_{datetime.now().timestamp()}"
        test_model = "gpt-4"
        test_analysis_type = "analysis"

        conn = db._temp_get_connection()

        try:
            # Create parent article
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article Update",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Save initial cache
            initial_content = "Initial analysis content"
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content=initial_content,
                model_used=test_model
            )
            assert result is True, "Should save initial cache"

            # Update with new content
            updated_content = "Updated analysis content"
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content=updated_content,
                model_used=test_model
            )
            assert result is True, "Should update existing cache"

            # Verify update
            cached = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=test_model
            )
            assert cached is not None, "Should retrieve updated cache"
            assert cached['content'] == updated_content, "Should have updated content"

            logger.info("✅ Cache update - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_cache_expiration(self, db):
        """Test cache expiration handling"""
        logger.info("Testing cache expiration...")

        from sqlalchemy import insert, delete, update
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_expire_{datetime.now().timestamp()}"
        test_model = "gpt-4"
        test_analysis_type = "summary"

        conn = db._temp_get_connection()

        try:
            # Create parent article
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article Expiration",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Save cache entry
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content="Expiring content",
                model_used=test_model
            )
            assert result is True, "Should save cache"

            # Manually set expiration to past date
            past_date = datetime.utcnow() - timedelta(days=1)
            conn.execute(
                update(t_article_analysis_cache)
                .where(t_article_analysis_cache.c.article_uri == test_uri)
                .values(expires_at=past_date)
            )
            conn.commit()

            # Try to retrieve expired cache
            cached = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=test_model
            )

            # Should return None for expired cache
            assert cached is None, "Should not return expired cache"

            logger.info("✅ Cache expiration - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_cache_different_models(self, db):
        """Test cache with different models"""
        logger.info("Testing cache with different models...")

        from sqlalchemy import insert, delete
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_models_{datetime.now().timestamp()}"
        test_analysis_type = "analysis"

        conn = db._temp_get_connection()

        try:
            # Create parent article
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article Models",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Save cache for model 1
            model1 = "gpt-4"
            content1 = "Analysis from GPT-4"
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content=content1,
                model_used=model1
            )
            assert result is True, "Should save cache for model 1"

            # Save cache for model 2
            model2 = "claude-3"
            content2 = "Analysis from Claude-3"
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content=content2,
                model_used=model2
            )
            assert result is True, "Should save cache for model 2"

            # Retrieve each cache
            cached1 = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=model1
            )
            assert cached1 is not None, "Should retrieve cache for model 1"
            assert cached1['content'] == content1, "Should have correct content for model 1"

            cached2 = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=model2
            )
            assert cached2 is not None, "Should retrieve cache for model 2"
            assert cached2['content'] == content2, "Should have correct content for model 2"

            logger.info("✅ Cache with different models - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_clean_expired_analysis_cache(self, db):
        """Test cleaning expired cache entries"""
        logger.info("Testing clean_expired_analysis_cache()...")

        from sqlalchemy import insert, delete
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_clean_{datetime.now().timestamp()}"
        test_model = "gpt-4"
        test_analysis_type = "summary"

        conn = db._temp_get_connection()

        try:
            # Create parent article
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article Clean",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Save cache entry with past expiration
            past_date = datetime.utcnow() - timedelta(days=1)
            cache_stmt = insert(t_article_analysis_cache).values(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content="Expired content",
                model_used=test_model,
                expires_at=past_date
            )
            conn.execute(cache_stmt)
            conn.commit()

            # Clean expired entries
            deleted_count = db.clean_expired_analysis_cache()
            assert deleted_count >= 1, "Should delete at least one expired entry"

            logger.info(f"✅ clean_expired_analysis_cache() - Cleaned {deleted_count} entries")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_cache_without_metadata(self, db):
        """Test cache operations without metadata"""
        logger.info("Testing cache without metadata...")

        from sqlalchemy import insert, delete
        from app.database_models import t_articles, t_article_analysis_cache

        test_uri = f"http://test.com/week3_cache_no_metadata_{datetime.now().timestamp()}"
        test_model = "gpt-4"
        test_analysis_type = "quick_summary"

        conn = db._temp_get_connection()

        try:
            # Create parent article
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article No Metadata",
                news_source="Test Source",
                topic="technology",
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Save cache without metadata
            result = db.save_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                content="Content without metadata",
                model_used=test_model,
                metadata=None
            )
            assert result is True, "Should save cache without metadata"

            # Retrieve cache
            cached = db.get_article_analysis_cache(
                article_uri=test_uri,
                analysis_type=test_analysis_type,
                model_used=test_model
            )
            assert cached is not None, "Should retrieve cache"
            assert cached['metadata'] == {}, "Should have empty metadata dict"

            logger.info("✅ Cache without metadata - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_article_analysis_cache).where(t_article_analysis_cache.c.article_uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")


def run_all_tests():
    """Run all Week 3 AI caching tests"""
    db = Database()

    logger.info("=" * 80)
    logger.info(f"PostgreSQL Migration - Week 3 AI Caching Test Suite")
    logger.info(f"Database Type: {DB_TYPE}")
    logger.info("=" * 80)

    # Test AI Caching Operations
    logger.info("\n🧠 Testing AI Analysis Caching:")
    cache_tests = TestAICaching()
    cache_tests.test_save_and_get_article_analysis_cache(db)
    cache_tests.test_cache_update_existing_entry(db)
    cache_tests.test_cache_expiration(db)
    cache_tests.test_cache_different_models(db)
    cache_tests.test_clean_expired_analysis_cache(db)
    cache_tests.test_cache_without_metadata(db)

    logger.info("\n" + "=" * 80)
    logger.info("✅ All Week 3 AI caching tests completed successfully!")
    logger.info("=" * 80)


if __name__ == "__main__":
    run_all_tests()
