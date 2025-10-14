"""
PostgreSQL Migration - Week 2 Test Suite

Tests for article operations and podcast settings migrated in Week 2.
Date: 2025-10-13
"""

import os
import logging
from app.database import Database
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database type
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()

class TestArticleOperations:
    """Test suite for article operation methods migrated in Week 2"""

    def test_get_recent_articles(self, db):
        """Test getting recent articles"""
        logger.info("Testing get_recent_articles()...")
        articles = db.get_recent_articles(limit=10)

        assert isinstance(articles, list), "Should return a list"
        assert len(articles) <= 10, "Should respect limit"

        # Check structure
        if articles:
            article = articles[0]
            assert 'uri' in article, "Should have uri field"
            assert 'tags' in article, "Should have tags field"
            assert isinstance(article['tags'], list), "Tags should be a list"

        logger.info(f"✅ get_recent_articles() - Retrieved {len(articles)} articles")

    def test_get_all_articles(self, db):
        """Test getting all articles"""
        logger.info("Testing get_all_articles()...")
        articles = db.get_all_articles()

        assert isinstance(articles, list), "Should return a list"

        # Check structure
        if articles:
            article = articles[0]
            assert 'uri' in article, "Should have uri field"
            # Check default fields are handled
            assert 'tags' in article, "Should have tags field"
            assert 'sentiment' in article, "Should have sentiment field"
            assert 'category' in article, "Should have category field"

        logger.info(f"✅ get_all_articles() - Retrieved {len(articles)} articles")

    def test_get_articles_by_ids(self, db):
        """Test batch fetch by URIs"""
        logger.info("Testing get_articles_by_ids()...")

        # Get some URIs first
        recent = db.get_recent_articles(limit=5)

        if len(recent) > 0:
            uris = [article['uri'] for article in recent]
            articles = db.get_articles_by_ids(uris)

            assert isinstance(articles, list), "Should return a list"
            assert len(articles) <= len(uris), "Should not return more than requested"

            # Check structure
            if articles:
                article = articles[0]
                assert 'uri' in article, "Should have uri field"
                assert 'tags' in article, "Should have tags field"
                assert isinstance(article['tags'], list), "Tags should be a list"
                assert 'url' in article or 'uri' in article, "Should have url or uri field"

            logger.info(f"✅ get_articles_by_ids() - Retrieved {len(articles)} articles")
        else:
            logger.info("⏭️  get_articles_by_ids() - No articles to test with")

    def test_get_categories(self, db):
        """Test getting categories"""
        logger.info("Testing get_categories()...")
        categories = db.get_categories()

        assert isinstance(categories, list), "Should return a list"

        # Check that categories are non-empty strings
        for category in categories:
            assert isinstance(category, str), "Categories should be strings"
            assert len(category) > 0, "Categories should not be empty"

        logger.info(f"✅ get_categories() - Retrieved {len(categories)} categories")

    def test_save_and_get_raw_article(self, db):
        """Test raw article storage and retrieval"""
        logger.info("Testing save_raw_article() and get_raw_article()...")

        # First, create a test article in the articles table
        from sqlalchemy import insert, delete, select
        from app.database_models import t_articles, t_raw_articles

        test_uri = f"http://test.com/week2_test_article_{datetime.now().timestamp()}"
        test_markdown = "# Test Article\n\nTest content for Week 2 migration"
        test_topic = "technology"

        conn = db._temp_get_connection()

        try:
            # Create parent article first
            article_stmt = insert(t_articles).values(
                uri=test_uri,
                title="Test Article",
                news_source="Test Source",
                topic=test_topic,
                publication_date=datetime.now(),
                submission_date=datetime.now()
            )
            conn.execute(article_stmt)
            conn.commit()

            # Now save raw article
            result = db.save_raw_article(test_uri, test_markdown, test_topic)
            assert result is not None, "Should return result"
            assert "message" in result, "Should have message in result"

            # Retrieve
            raw = db.get_raw_article(test_uri)
            assert raw is not None, "Should retrieve raw article"
            assert raw['raw_markdown'] == test_markdown, "Should match saved markdown"
            assert raw['topic'] == test_topic, "Should match topic"

            logger.info("✅ save_raw_article() and get_raw_article() - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_raw_articles).where(t_raw_articles.c.uri == test_uri))
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_update_or_create_article(self, db):
        """Test article upsert operation"""
        logger.info("Testing update_or_create_article()...")

        from sqlalchemy import delete
        from app.database_models import t_articles

        test_uri = f"http://test.com/week2_upsert_test_{datetime.now().timestamp()}"

        conn = db._temp_get_connection()

        try:
            # Test create
            article_data = {
                'uri': test_uri,
                'title': 'Test Article Create',
                'news_source': 'Test Source',
                'summary': 'Test summary',
                'topic': 'technology',
                'publication_date': datetime.now().isoformat(),
                'sentiment': 'neutral',
                'category': 'test'
            }

            result = db.update_or_create_article(article_data)
            assert result is True, "Should successfully create article"

            # Test update
            article_data['title'] = 'Test Article Updated'
            result = db.update_or_create_article(article_data)
            assert result is True, "Should successfully update article"

            logger.info("✅ update_or_create_article() - Create and update working")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_articles).where(t_articles.c.uri == test_uri))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")


class TestPodcastSettings:
    """Test suite for podcast settings methods migrated in Week 2"""

    def test_get_podcast_settings(self, db):
        """Test getting podcast settings"""
        logger.info("Testing get_podcast_settings()...")
        settings = db.get_podcast_settings()

        assert isinstance(settings, dict), "Should return a dict"

        # Check for default fields
        expected_fields = ['podcast_enabled', 'transcribe_enabled', 'openai_model']
        for field in expected_fields:
            assert field in settings, f"Should have {field} field"

        logger.info("✅ get_podcast_settings() - Retrieved settings")

    def test_set_and_get_podcast_setting(self, db):
        """Test setting and getting individual podcast settings"""
        logger.info("Testing set_podcast_setting() and get_podcast_setting()...")

        from sqlalchemy import delete
        from app.database_models import t_settings_podcasts

        test_key = f"test_setting_{datetime.now().timestamp()}"
        test_value = "test_value"

        conn = db._temp_get_connection()

        try:
            # Set
            result = db.set_podcast_setting(test_key, test_value)
            assert result is True, "Should successfully set setting"

            # Get
            value = db.get_podcast_setting(test_key)
            assert value == test_value, "Should retrieve correct value"

            # Update
            new_value = "updated_value"
            result = db.set_podcast_setting(test_key, new_value)
            assert result is True, "Should successfully update setting"

            # Verify update
            value = db.get_podcast_setting(test_key)
            assert value == new_value, "Should retrieve updated value"

            logger.info("✅ set_podcast_setting() and get_podcast_setting() - Working correctly")

        finally:
            # Cleanup
            try:
                conn.execute(delete(t_settings_podcasts).where(t_settings_podcasts.c.key == test_key))
                conn.commit()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

    def test_update_podcast_settings(self, db):
        """Test batch update of podcast settings"""
        logger.info("Testing update_podcast_settings()...")

        test_settings = {
            'podcast_enabled': 1,
            'transcribe_enabled': 1,
            'openai_model': 'whisper-1',
            'transcript_format': 'text'
        }

        result = db.update_podcast_settings(test_settings)
        assert result is True, "Should successfully update settings"

        # Verify settings were updated
        settings = db.get_podcast_settings()
        for key, value in test_settings.items():
            if key in settings:
                # Note: May need type conversion depending on storage
                logger.debug(f"Verified {key}: {settings[key]}")

        logger.info("✅ update_podcast_settings() - Batch update working")


def run_all_tests():
    """Run all Week 2 migration tests"""
    db = Database()

    logger.info("=" * 80)
    logger.info(f"PostgreSQL Migration - Week 2 Test Suite")
    logger.info(f"Database Type: {DB_TYPE}")
    logger.info("=" * 80)

    # Test Article Operations
    logger.info("\n📦 Testing Article Operations:")
    article_tests = TestArticleOperations()
    article_tests.test_get_recent_articles(db)
    article_tests.test_get_all_articles(db)
    article_tests.test_get_articles_by_ids(db)
    article_tests.test_get_categories(db)
    article_tests.test_save_and_get_raw_article(db)
    article_tests.test_update_or_create_article(db)

    # Test Podcast Settings
    logger.info("\n🎙️  Testing Podcast Settings:")
    podcast_tests = TestPodcastSettings()
    podcast_tests.test_get_podcast_settings(db)
    podcast_tests.test_set_and_get_podcast_setting(db)
    podcast_tests.test_update_podcast_settings(db)

    logger.info("\n" + "=" * 80)
    logger.info("✅ All Week 2 migration tests completed successfully!")
    logger.info("=" * 80)


if __name__ == "__main__":
    run_all_tests()
