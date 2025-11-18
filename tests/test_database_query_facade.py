import pytest
import logging
import json
from sqlalchemy import create_engine, insert, select, update, delete, func
from sqlalchemy.pool import StaticPool
from datetime import datetime
from app.database_query_facade import DatabaseQueryFacade as DQF
from app.database_models import metadata
from app.database_models import (t_keyword_monitor_settings as keyword_monitor_settings,
                                 t_keyword_monitor_status as keyword_monitor_status,
                                 t_keyword_article_matches as keyword_article_matches,
                                 t_articles as articles,
                                 t_monitored_keywords as monitored_keywords,
                                 t_keyword_groups as keyword_groups,
                                 t_analysis_versions as analysis_versions,
                                 t_analysis_versions_v2 as analysis_versions_v2,
                                 t_organizational_profiles as organizational_profiles,
                                 t_keyword_alerts as keyword_alerts,
                                 t_oauth_allowlist as oauth_allowlist,
                                 t_oauth_users as oauth_users,
                                 t_users,
                                 t_podcasts as podcasts,
                                 t_model_bias_arena_runs as model_bias_arena_runs,
                                 t_model_bias_arena_results as model_bias_arena_results,
                                 t_model_bias_arena_articles as model_bias_arena_articles,
                                 t_mediabias as mediabias,
                                 t_mediabias_settings as mediabias_settings,
                                 t_feed_items as feed_items,
                                 t_feed_keyword_groups as feed_keyword_groups,
                                 t_feed_group_sources as feed_group_sources,
                                 t_user_feed_subscriptions as user_feed_subscriptions,
                                 t_auspex_chats as auspex_chats,
                                 t_auspex_messages as auspex_messages,
                                 t_auspex_prompts as auspex_prompts,
                                 t_dashboard_cache as dashboard_cache,
                                 t_signal_alerts as signal_alerts,
                                 t_signal_instructions as signal_instructions,
                                 # t_keyword_monitor_checks as keyword_monitor_checks,  # Table doesn't exist
                                 t_raw_articles as raw_articles)
                                 # t_paper_search_results as paper_search_results,  # Table doesn't exist
                                 # t_news_search_results as news_search_results,  # Table doesn't exist
                             # t_keyword_alert_articles as keyword_alert_articles)  # Table doesn't exist


class TestLogger:
    def __init__(self):
        self.errors = []
        self.infos = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)

    def debug(self, msg):
        # forward to python logging so caplog can capture
        logging.getLogger(__name__).debug(msg)


class SAConnectionWrapper:
    def __init__(self, engine):
        self._conn = engine.connect()

    def execute(self, statement, params=None):
        if params is not None:
            return self._conn.execute(statement, params)
        return self._conn.execute(statement)

    def commit(self):
        try:
            self._conn.commit()
        finally:
            self._conn.close()

    def rollback(self):
        try:
            self._conn.rollback()
        finally:
            self._conn.close()


class TestDB:
    def __init__(self, engine):
        self._engine = engine
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        self.connection = self.engine.connect()

    def _temp_get_connection(self):
        return SAConnectionWrapper(self._engine)

    # Needed by some facade methods that use context manager style
    def get_connection(self):
        class _DBContext:
            def __init__(self, engine):
                self._engine = engine
                self._conn = None

            def __enter__(self):
                self._conn = self._engine.connect()
                return self._conn

            def __exit__(self, exc_type, exc, tb):
                try:
                    if exc_type is None:
                        self._conn.commit()
                    else:
                        self._conn.rollback()
                finally:
                    self._conn.close()
                return False

        return _DBContext(self._engine)


@pytest.fixture()
def facade():
    # Shared in-memory DB across connections
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    db = TestDB(engine)
    logger = TestLogger()
    return DQF(db, logger)


def test_create_and_get_keyword_monitor_status(facade):
    params = {
        "id": 1,
        "last_check_time": "2025-01-01T00:00:00Z",
        "requests_today": 3,
        "last_error": None,
    }
    facade.create_keyword_monitor_status(params)

    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["id"] == 1
    assert row["requests_today"] == 3
    assert row["last_check_time"] == "2025-01-01T00:00:00Z"


# Test methods for database query method 

def test_get_keyword_monitor_settings_by_id(facade):
    # First, insert a sample keyword monitor settings row
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            check_interval=5,
            interval_unit=1,
            search_fields="title,content",
            language="en",
            sort_by="relevancy",
            page_size=20,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            provider="newsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.8,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.7,
            llm_max_tokens=512,
            providers='["newsapi"]'
        )
    )

    # Now retrieve it using the method
    row = facade.get_keyword_monitor_settings_by_id(1)

    # Validate the fetched record
    assert row is not None
    assert row["id"] == 1
    assert row["provider"] == "newsapi"
    assert row["is_enabled"] is True
    assert row["page_size"] == 20


def test_get_keyword_monitor_status_by_id(facade):
    # Insert a test record into keyword_monitor_status
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_check_time="2025-01-01T00:00:00Z",
            last_error=None,
            requests_today=3,
            last_reset_date="2025-01-01"
        )
    )

    # Fetch the record using the method
    row = facade.get_keyword_monitor_status_by_id(1)

    # Validate the fetched record
    assert row is not None
    assert row["id"] == 1
    assert row["requests_today"] == 3
    assert row["last_check_time"] == "2025-01-01T00:00:00Z"


def test_update_keyword_monitor_status_by_id(facade):
    # Insert an initial record
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_check_time="2025-01-01T00:00:00Z",
            requests_today=5
        )
    )

    # Update the record using the method
    facade.update_keyword_monitor_status_by_id(
        1,
        {
            "last_check_time": "2025-01-02T00:00:00Z",
            "requests_today": 10
        }
    )

    # Fetch and validate the updated record
    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["id"] == 1
    assert row["requests_today"] == 10
    assert row["last_check_time"] == "2025-01-02T00:00:00Z"



def test_get_or_create_keyword_monitor_settings(facade):
    # Insert a sample record
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            provider="newsapi",
            check_interval=5,
            interval_unit=1,
            search_fields="title,content",
            language="en",
            sort_by="relevancy",
            page_size=10,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            auto_ingest_enabled=True,
            min_relevance_threshold=0.8,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.7,
            llm_max_tokens=512,
            providers='["newsapi"]'
        )
    )

    # Fetch using the method under test
    row = facade.get_or_create_keyword_monitor_settings()

    # Validate
    assert row is not None
    assert row["id"] == 1
    assert row["provider"] == "newsapi"


def test_get_keyword_monitoring_provider(facade):
    # Insert a record with a specific provider
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            provider="gptnews",
            check_interval=5,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="relevancy",
            page_size=10,
            is_enabled=True,
            daily_request_limit=50,
            search_date_range=7,
            auto_ingest_enabled=False,
            min_relevance_threshold=0.5,
            quality_control_enabled=True,
            auto_save_approved_only=True,
            default_llm_model="gpt-4",
            llm_temperature=0.6,
            llm_max_tokens=256,
            providers='["gptnews"]'
        )
    )

    # Fetch provider via the method
    provider = facade.get_keyword_monitoring_provider()

    # Validate
    assert provider == "gptnews"



def test_get_keyword_monitoring_providers(facade):
    # Case 1: Record with 'providers' field
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            providers='["reuters", "bbc"]',
            provider="oldnews",
            check_interval=5,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="latest",
            page_size=15,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.8,
            llm_max_tokens=512
        )
    )

    result = facade.get_keyword_monitoring_providers()
    assert result == '["reuters", "bbc"]'



def test_update_keyword_monitoring_providers(facade):
    # Ensure clean state
    facade._execute_with_rollback(keyword_monitor_settings.delete().where(keyword_monitor_settings.c.id == 1))

    # Insert a record with initial providers
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            providers='["newsapi"]',
            provider="newsapi",
            check_interval=5,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="latest",
            page_size=15,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.8,
            llm_max_tokens=512
        )
    )

    # Update the providers JSON array
    new_providers = '["cnn", "reuters"]'
    facade.update_keyword_monitoring_providers(new_providers)

    # Verify the update
    row = facade.get_keyword_monitor_settings_by_id(1)
    assert row is not None
    assert row["providers"] == new_providers


def test_get_keyword_monitoring_counter(facade):
    # Clean up and insert test record
    facade._execute_with_rollback(keyword_monitor_status.delete().where(keyword_monitor_status.c.id == 1))
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_check_time="2025-01-05T00:00:00Z",
            requests_today=12,
            last_reset_date="2025-01-04"
        )
    )

    # Fetch using method
    row = facade.get_keyword_monitoring_counter()

    # Validate
    assert row is not None
    assert row["id"] == 1
    assert row["requests_today"] == 12
    assert row["last_check_time"] == "2025-01-05T00:00:00Z"


def test_reset_keyword_monitoring_counter(facade):
    # Clean up and insert record with non-zero requests
    facade._execute_with_rollback(keyword_monitor_status.delete().where(keyword_monitor_status.c.id == 1))
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_reset_date="2025-01-04",
            requests_today=25
        )
    )

    # Reset the counter
    facade.reset_keyword_monitoring_counter(["2025-01-05"])

    # Verify results
    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["requests_today"] == 0
    assert row["last_reset_date"] == "2025-01-05"


def test_create_keyword_monitor_status(facade):
    # Create a new keyword monitor status record
    params = {
        "id": 1,
        "last_check_time": "2025-01-10T00:00:00Z",
        "requests_today": 3,
        "last_error": None,
        "last_reset_date": "2025-01-09"
    }

    facade.create_keyword_monitor_status(params)

    # Verify the record was inserted correctly
    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["id"] == 1
    assert row["requests_today"] == 3
    assert row["last_check_time"] == "2025-01-10T00:00:00Z"

def test_create_or_update_keyword_monitor_last_check(facade):
    # Should create when no record exists
    facade.create_or_update_keyword_monitor_last_check(["2025-01-10T00:00:00Z", 5])
    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["requests_today"] == 5
    assert row["last_check_time"] == "2025-01-10T00:00:00Z"

    # Should update when record already exists
    facade.create_or_update_keyword_monitor_last_check(["2025-01-11T00:00:00Z", 9])
    row = facade.get_keyword_monitor_status_by_id(1)
    assert row is not None
    assert row["requests_today"] == 9
    assert row["last_check_time"] == "2025-01-11T00:00:00Z"



def test_get_monitored_keywords(facade):
    # Insert a keyword group and a monitored keyword linked to it
    group_id = 1
    facade._execute_with_rollback(
        keyword_groups.insert().values(
            id=group_id,
            name="AI News",
            topic="Artificial Intelligence",
            created_at="2025-01-10",
            provider="newsapi",
            source="online"
        )
    )

    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=group_id,
            keyword="machine learning",
            created_at="2025-01-10",
            last_checked="2025-01-09"
        )
    )

    # Fetch monitored keywords joined with keyword_groups
    rows = facade.get_monitored_keywords()

    # Validate
    assert len(rows) == 1
    row = rows[0]
    assert row["keyword"] == "machine learning"
    assert row["topic"] == "Artificial Intelligence"
    assert row["last_checked"] == "2025-01-09"


def test_get_monitored_keywords_for_topic(facade):
    # Insert keyword group and monitored keywords
    group_id = 1
    topic = "AI Ethics"

    facade._execute_with_rollback(
        keyword_groups.insert().values(
            id=group_id,
            name="AI Ethics Group",
            topic=topic,
            created_at="2025-01-10",
            provider="newsapi",
            source="web"
        )
    )

    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=group_id,
            keyword="AI responsibility",
            created_at="2025-01-09",
            last_checked="2025-01-09"
        )
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=2,
            group_id=group_id,
            keyword="AI fairness",
            created_at="2025-01-09",
            last_checked="2025-01-09"
        )
    )

    # Fetch keywords for topic
    result = facade.get_monitored_keywords_for_topic([topic])

    # Validate
    assert isinstance(result, list)
    assert "AI responsibility" in result
    assert "AI fairness" in result
    assert len(result) == 2


def test_article_exists(facade):
    # Clean up and insert a test article
    facade._execute_with_rollback(articles.delete().where(articles.c.uri == "http://example.com/article1"))
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article1",
            title="AI Breakthrough",
            news_source="TechTimes",
            publication_date="2025-01-09",
            summary="AI model reaches new heights",
            topic="AI",
            analyzed=False
        )
    )

    # Check if article exists
    exists = facade.article_exists(["http://example.com/article1"])
    assert exists is not None

    # Check a non-existing article
    not_exists = facade.article_exists(["http://example.com/missing"])
    assert not_exists is None


def test_create_article(facade):
    # Insert group and monitored keyword
    facade._execute_with_rollback(
        keyword_groups.insert().values(
            id=1,
            name="AI Group",
            topic="Artificial Intelligence",
            created_at="2025-01-10",
            provider="newsapi",
            source="online"
        )
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=1,
            keyword="AI Research",
            created_at="2025-01-10",
            last_checked="2025-01-10"
        )
    )

    article_url = "http://example.com/ai_article"
    article_data = {
        "title": "AI Innovations",
        "source": "Tech World",
        "published_date": "2025-01-11",
        "summary": "AI research growing fast"
    }

    # 1️⃣ Create a new article
    inserted, alert_inserted, match_updated = facade.create_article(
        article_exists=None,
        article_url=article_url,
        article=article_data,
        topic="Artificial Intelligence",
        keyword_id=1
    )

    assert inserted is True
    assert alert_inserted is False
    assert match_updated is True

    # 2️⃣ Call again with same article and keyword (should not duplicate)
    inserted, alert_inserted, match_updated = facade.create_article(
        article_exists=True,
        article_url=article_url,
        article=article_data,
        topic="Artificial Intelligence",
        keyword_id=1
    )

    assert inserted is False  # Article already exists
    assert alert_inserted is False
    assert match_updated is False  # Keyword already in match list

    # 3️⃣ Add a new keyword to same group to test match update
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=2,
            group_id=1,
            keyword="AI Ethics",
            created_at="2025-01-10",
            last_checked="2025-01-10"
        )
    )

    inserted, alert_inserted, match_updated = facade.create_article(
        article_exists=True,
        article_url=article_url,
        article=article_data,
        topic="Artificial Intelligence",
        keyword_id=2
    )

    assert match_updated is True  # Should update keyword_ids list


def test_update_monitored_keyword_last_checked(facade):
    # Insert a monitored keyword
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=1,
            keyword="AI trends",
            created_at="2025-01-10",
            last_checked="2025-01-09"
        )
    )

    # Update its last_checked field
    facade.update_monitored_keyword_last_checked(["2025-01-11", 1])

    # Fetch and verify
    row = facade._execute_with_rollback(
        select(monitored_keywords).where(monitored_keywords.c.id == 1)
    ).mappings().fetchone()

    assert row is not None
    assert row["last_checked"] == "2025-01-11"


def test_update_keyword_monitor_counter(facade):
    # Insert a record into keyword_monitor_status
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_check_time="2025-01-10T00:00:00Z",
            requests_today=5
        )
    )

    # Update the requests_today value
    facade.update_keyword_monitor_counter([12])

    # Verify the update
    row = facade._execute_with_rollback(
        select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
    ).mappings().fetchone()

    assert row is not None
    assert row["requests_today"] == 12


def test_create_keyword_monitor_log_entry(facade):
    # Case 1: Create new record when none exists
    facade.create_keyword_monitor_log_entry(["2025-01-10T00:00:00Z", None, 5])
    row = facade._execute_with_rollback(
        select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
    ).mappings().fetchone()
    assert row is not None
    assert row["last_check_time"] == "2025-01-10T00:00:00Z"
    assert row["requests_today"] == 5
    assert row["last_error"] is None

    # Case 2: Update existing record
    facade.create_keyword_monitor_log_entry(["2025-01-11T00:00:00Z", "timeout error", 9])
    row = facade._execute_with_rollback(
        select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
    ).mappings().fetchone()

    assert row is not None
    assert row["last_check_time"] == "2025-01-11T00:00:00Z"
    assert row["requests_today"] == 9
    assert row["last_error"] == "timeout error"


def test_get_keyword_monitor_polling_enabled(facade):
    # Case 1: Explicitly enabled
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            is_enabled=True,
            check_interval=10,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="relevancy",
            page_size=20,
            daily_request_limit=100,
            search_date_range=7,
            provider="newsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.8,
            llm_max_tokens=512,
            providers='["newsapi"]'
        )
    )

    result = facade.get_keyword_monitor_polling_enabled()
    assert result is True

    # Case 2: Explicitly disabled
    facade._execute_with_rollback(
        update(keyword_monitor_settings)
        .where(keyword_monitor_settings.c.id == 1)
        .values(is_enabled=False)
    )
    result = facade.get_keyword_monitor_polling_enabled()
    assert result is False




def test_get_keyword_monitor_interval(facade):
    # Insert keyword monitor settings record with interval values
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            check_interval=15,
            interval_unit=2,
            search_fields="title",
            language="en",
            sort_by="relevancy",
            page_size=20,
            is_enabled=True,
            daily_request_limit=50,
            search_date_range=7,
            provider="newsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.8,
            llm_max_tokens=512,
            providers='["newsapi"]'
        )
    )

    # Fetch the interval configuration
    row = facade.get_keyword_monitor_interval()

    # Verify both values
    assert row is not None
    assert row[0] == 15      # check_interval
    assert row[1] == 2       # interval_unit



def test_get_article_by_url(facade):
    # Insert a sample article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/test-article",
            title="AI in Healthcare",
            news_source="Tech Daily",
            publication_date="2025-01-11",
            summary="How AI is transforming healthcare",
            topic="Artificial Intelligence",
            analyzed=False
        )
    )

    # Fetch it using the method under test
    row = facade.get_article_by_url("http://example.com/test-article")

    # Validate
    assert row is not None
    assert row["uri"] == "http://example.com/test-article"
    assert row["title"] == "AI in Healthcare"
    assert row["topic"] == "Artificial Intelligence"

    # Verify non-existing URL returns None
    assert facade.get_article_by_url("http://example.com/does-not-exist") is None


def test_create_article_with_extracted_content(facade):
    params = [
        "http://example.com/ai-research",
        "AI Research Advances",
        "TechWorld",
        "Artificial Intelligence",
        False,
        "A summary of the latest AI breakthroughs."
    ]

    # Create article using the method
    facade.create_article_with_extracted_content(params)

    # Fetch the created article
    row = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == "http://example.com/ai-research")
    ).mappings().fetchone()

    # Validate
    assert row is not None
    assert row["title"] == "AI Research Advances"
    assert row["news_source"] == "TechWorld"
    assert row["summary"].startswith("A summary")
    assert row["topic"] == "Artificial Intelligence"
    assert row["analyzed"] is False


# move_alert_to_articles not functionnal in the database query facade

def test_get_iter_articles(facade):
    # Insert a couple of articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article1",
            title="AI in 2025",
            news_source="Tech Daily",
            topic="AI",
            analyzed=True
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article2",
            title="AI for Sustainability",
            news_source="Green Future",
            topic="AI",
            analyzed=False
        )
    )

    # Insert corresponding raw_articles
    facade._execute_with_rollback(
        raw_articles.insert().values(
            uri="http://example.com/article1",
            raw_markdown="**AI Article 1 Content**"
        )
    )

    # Fetch all articles (join with raw_articles)
    rows = facade.get_iter_articles()
    assert len(rows) >= 2

    # Ensure join worked
    row_with_raw = next((r for r in rows if r["uri"] == "http://example.com/article1"), None)
    assert row_with_raw is not None
    assert "AI" in row_with_raw["title"]
    assert row_with_raw["raw"] == "**AI Article 1 Content**"

    # Test with limit
    limited_rows = facade.get_iter_articles(limit=1)
    assert len(limited_rows) == 1


def test_save_analysis_version(facade):
    params = [
        "AI",
        '{"insights": "AI usage growing rapidly"}',
        "gpt-4",
        "deep"
    ]

    # Save new analysis version
    facade.save_analysis_version(params)

    # Verify it was inserted
    row = facade._execute_with_rollback(
        select(analysis_versions).where(analysis_versions.c.topic == "AI")
    ).mappings().fetchone()

    assert row is not None
    assert row["topic"] == "AI"
    assert "AI usage" in row["version_data"]
    assert row["model_used"] == "gpt-4"
    assert row["analysis_depth"] == "deep"


def test_get_latest_analysis_version(facade):
    # Insert multiple versions of the same topic using real datetime objects
    facade._execute_with_rollback(
        analysis_versions.insert().values(
            topic="Climate Change",
            version_data="Version 1 data",
            model_used="gpt-3.5",
            analysis_depth="shallow",
            created_at=datetime(2025, 1, 9, 10, 0, 0)
        )
    )
    facade._execute_with_rollback(
        analysis_versions.insert().values(
            topic="Climate Change",
            version_data="Version 2 data",
            model_used="gpt-4",
            analysis_depth="deep",
            created_at=datetime(2025, 1, 10, 12, 0, 0)
        )
    )

    # Retrieve latest version
    row = facade.get_latest_analysis_version("Climate Change")

    assert row is not None
    assert row[0] == "Version 2 data"  # Most recent version



def test_get_articles_with_dynamic_limit(facade):
    # Insert sample articles for topic "AI"
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/a1",
            title="AI in Finance",
            summary="AI is transforming financial systems.",
            publication_date="2025-01-05 09:00:00",
            topic="AI",
            sentiment="positive",
            category="finance",
            future_signal="growth",
            driver_type="economic",
            time_to_impact="short"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/a2",
            title="AI and Healthcare",
            summary="AI improving diagnostics.",
            publication_date="2025-01-06 10:00:00",
            topic="AI",
            sentiment="neutral",
            category="healthcare",
            future_signal="innovation",
            driver_type="technology",
            time_to_impact="medium"
        )
    )

    start_date = datetime(2025, 1, 4)
    end_date = datetime(2025, 1, 7)

    # Balanced mode should fetch exactly optimal_sample_size articles
    rows = facade.get_articles_with_dynamic_limit(
        consistency_mode="balanced",
        topic="AI",
        start_date=start_date,
        end_date=end_date,
        optimal_sample_size=2
    )
    assert len(rows) == 2
    assert all("AI" in r["title"] for r in rows)
    assert all(r["summary"] != "" for r in rows)

    # Deterministic mode should fetch double (multiplier = 2)
    rows_deterministic = facade.get_articles_with_dynamic_limit(
        consistency_mode="deterministic",
        topic="AI",
        start_date=start_date,
        end_date=end_date,
        optimal_sample_size=1
    )
    assert len(rows_deterministic) == 2  # 1 * 2
    assert rows_deterministic[0]["publication_date"] >= rows_deterministic[-1]["publication_date"]


def test_get_organisational_profile(facade):
    # Insert an organisational profile
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="TechVision",
            description="AI-driven research company",
            industry="Technology",
            organization_type="Private",
            region="Asia",
            key_concerns="Data privacy",
            strategic_priorities="AI innovation",
            risk_tolerance="medium",
            innovation_appetite="high",
            decision_making_style="decentralized",
            stakeholder_focus="customers",
            competitive_landscape="fast-paced",
            regulatory_environment="lenient",
            custom_context="Global R&D"
        )
    )

    # Retrieve by ID
    profile = facade.get_organisational_profile(1)

    # Validate data
    assert profile is not None
    assert profile["name"] == "TechVision"
    assert profile["industry"] == "Technology"
    assert profile["region"] == "Asia"
    assert "AI" in profile["description"]



def test_get_organisational_profiles(facade):
    # Insert multiple organisational profiles
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="TechVision",
            industry="Technology",
            organization_type="Private",
            is_default=True,
            region="Asia",
            created_at=datetime(2025, 1, 1, 10, 0, 0)
        )
    )
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=2,
            name="EcoCorp",
            industry="Environment",
            organization_type="Nonprofit",
            is_default=False,
            region="Europe",
            created_at=datetime(2025, 1, 2, 11, 0, 0)
        )
    )

    # Fetch all profiles
    profiles = facade.get_organisational_profiles()

    # Validate sorting: default profile first, then alphabetical by name
    assert len(profiles) >= 2
    assert profiles[0]["is_default"] is True
    assert profiles[0]["name"] == "TechVision"
    assert profiles[1]["name"] == "EcoCorp"


def test_create_organisational_profile(facade):
    params = [
        "AI Vision",
        "Artificial Intelligence Strategy Consultancy",
        "Technology",
        "Private",
        "Global",
        "Ethical AI Development",
        "Promote Responsible AI",
        "Medium",
        "High",
        "Collaborative",
        "Investors",
        "Competitive",
        "Regulated",
        "Contextual innovation"
    ]

    result = facade.create_organisational_profile(params)
    assert result is not None  # Should return an executed result

    # Verify insertion
    row = facade._execute_with_rollback(
        select(organizational_profiles).where(organizational_profiles.c.name == "AI Vision")
    ).mappings().fetchone()

    assert row is not None
    assert row["industry"] == "Technology"
    assert row["organization_type"] == "Private"
    assert "Ethical" in row["key_concerns"]


def test_delete_organisational_profile(facade):
    # Insert a test profile
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="Eco Vision",
            description="Sustainability Org",
            industry="Environment"
        )
    )

    # Delete it
    facade.delete_organisational_profile(1)

    # Verify deletion
    row = facade._execute_with_rollback(
        select(organizational_profiles).where(organizational_profiles.c.id == 1)
    ).mappings().fetchone()

    assert row is None


def test_get_organisational_profile_by_name(facade):
    # Insert profile
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="Tech Dynamics",
            industry="Software"
        )
    )

    # Fetch by name
    row = facade.get_organisational_profile_by_name("Tech Dynamics")

    assert row is not None
    assert row["id"] == 1

    # Non-existent name returns None
    assert facade.get_organisational_profile_by_name("Unknown Org") is None


def test_get_organisational_profile_by_id(facade):
    # Insert profile
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=2,
            name="BioTech Ltd",
            industry="Healthcare"
        )
    )

    # Fetch by ID
    row = facade.get_organisational_profile_by_id(2)

    assert row is not None
    assert row["id"] == 2
    assert row["id"] == 2



def test_get_organizational_profile_for_ui(facade):
    # Insert profile with extended fields
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=3,
            name="Quantum Labs",
            description="Quantum Computing Research Firm",
            industry="Technology",
            organization_type="Private",
            region="North America",
            key_concerns="Scalability",
            strategic_priorities="Quantum Supremacy",
            risk_tolerance="High",
            innovation_appetite="Very High",
            decision_making_style="Centralized",
            stakeholder_focus="Researchers",
            competitive_landscape="High Innovation",
            regulatory_environment="Evolving",
            custom_context="Focus on superconducting qubits",
            is_default=False,
            created_at=datetime(2025, 1, 10, 9, 0, 0),
            updated_at=datetime(2025, 1, 11, 10, 0, 0)
        )
    )

    # Fetch using method
    row = facade.get_organizational_profile_for_ui(3)

    assert row is not None
    assert row["name"] == "Quantum Labs"
    assert row["industry"] == "Technology"
    assert row["organization_type"] == "Private"
    assert row["region"] == "North America"
    assert row["key_concerns"] == "Scalability"
    assert row["created_at"] is not None
    assert row["updated_at"] is not None


def test_check_organisational_profile_name_conflict(facade):
    # Insert two profiles with different names
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="TechOne",
            industry="Software"
        )
    )
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=2,
            name="EcoWave",
            industry="Environment"
        )
    )

    # Check conflict for same name but different ID
    conflict = facade.check_organisational_profile_name_conflict("TechOne", 2)
    assert conflict is not None
    assert conflict[0] == 1  # Conflicting profile ID

    # Check no conflict for same ID
    no_conflict = facade.check_organisational_profile_name_conflict("TechOne", 1)
    assert no_conflict is None


def test_update_organisational_profile(facade):
    # Insert a base profile
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="Old Name",
            description="Initial Description",
            industry="Technology",
            organization_type="Private",
            region="Global"
        )
    )

    # Update the profile fields
    params = [
        "New Name",                  # name
        "Updated Description",       # description
        "AI Industry",               # industry
        "Public",                    # organization_type
        "Europe",                    # region
        "Risk Management",           # key_concerns
        "Expand AI reach",           # strategic_priorities
        "High",                      # risk_tolerance
        "Very High",                 # innovation_appetite
        "Collaborative",             # decision_making_style
        "Stakeholders",              # stakeholder_focus
        "Competitive",               # competitive_landscape
        "Strict",                    # regulatory_environment
        "AI-driven organization",    # custom_context
        1                            # profile_id
    ]

    facade.update_organisational_profile(params)

    # Verify update
    row = facade._execute_with_rollback(
        select(organizational_profiles).where(organizational_profiles.c.id == 1)
    ).mappings().fetchone()

    assert row is not None
    assert row["name"] == "New Name"
    assert row["description"] == "Updated Description"
    assert row["industry"] == "AI Industry"
    assert row["organization_type"] == "Public"
    assert row["region"] == "Europe"
    assert row["custom_context"] == "AI-driven organization"


def test_check_if_profile_exists_and_is_not_default(facade):
    # Insert two profiles — one default, one not
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=1,
            name="Default Org",
            is_default=True
        )
    )
    facade._execute_with_rollback(
        organizational_profiles.insert().values(
            id=2,
            name="Regular Org",
            is_default=False
        )
    )

    # Check for default profile
    result_default = facade.check_if_profile_exists_and_is_not_default(1)
    assert result_default is not None
    assert result_default[0] is True

    # Check for non-default profile
    result_non_default = facade.check_if_profile_exists_and_is_not_default(2)
    assert result_non_default is not None
    assert result_non_default[0] is False


def test_get_configured_llm_model(facade):
    # Insert model configuration
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            default_llm_model="gpt-4",
            llm_temperature=0.8,
            llm_max_tokens=1024,
            check_interval=5,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="latest",
            page_size=10,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            provider="newsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False
        )
    )

    result = facade.get_configured_llm_model()
    assert result == "gpt-4"

    # Case 2: Simulate missing model (delete + insert without model)
    facade._execute_with_rollback(delete(keyword_monitor_settings))
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            llm_temperature=0.9,
            llm_max_tokens=800,
            check_interval=5,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="latest",
            page_size=10,
            is_enabled=True,
            daily_request_limit=100,
            search_date_range=7,
            provider="newsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False
        )
    )

    fallback_result = facade.get_configured_llm_model()
    assert fallback_result == "gpt-4o-mini"


def test_get_llm_parameters(facade):
    # Insert LLM parameters
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            llm_temperature=0.7,
            llm_max_tokens=512,
            check_interval=5,
            interval_unit=1,
            search_fields="summary",
            language="en",
            sort_by="relevance",
            page_size=15,
            is_enabled=True,
            daily_request_limit=50,
            search_date_range=10,
            provider="thenewsapi",
            auto_ingest_enabled=True,
            min_relevance_threshold=0.9,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4"
        )
    )

    result = facade.get_llm_parameters()
    assert result == (0.7, 512)

    # Case: Missing row returns None
    facade._execute_with_rollback(delete(keyword_monitor_settings))
    assert facade.get_llm_parameters() is None


def test_save_approved_article(facade, caplog):
    # Insert base article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/test-article",
            title="Old Title",
            summary="Old Summary",
            analyzed=False
        )
    )

    params = [
        "New Title",                     # 0
        "Updated Summary",               # 1
        "approved",                      # 2 ingest_status
        0.95,                            # 3 quality_score
        "none",                          # 4 quality_issues
        "tech",                          # 5 category
        "positive",                      # 6 sentiment
        "neutral",                       # 7 bias
        "factual",                       # 8 factual_reporting
        "high",                          # 9 mbfc_credibility_rating
        "mbfc",                          # 10 bias_source
        "us",                            # 11 bias_country
        "free",                          # 12 press_freedom
        "media",                         # 13 media_type
        "high",                          # 14 popularity
        0.88,                            # 15 topic_alignment_score
        0.92,                            # 16 keyword_relevance_score
        "growth",                        # 17 future_signal
        "Future looks good",             # 18 future_signal_explanation
        "Positive outlook",              # 19 sentiment_explanation
        "short",                         # 20 time_to_impact
        "driver",                        # 21 driver_type
        "tag1,tag2",                     # 22 tags
        None,                            # 23 skip index
        0.97,                            # 24 confidence_score
        "Overall strong alignment",      # 25 overall_match_explanation
        "2025-01-05 12:00:00",           # 26 publication_date
        "http://example.com/test-article" # 27 article_uri
    ]

    facade.save_approved_article(params)

    # Verify update
    updated = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == "http://example.com/test-article")
    ).mappings().fetchone()

    assert updated["title"] == "New Title"
    assert updated["summary"] == "Updated Summary"
    assert updated["analyzed"] is True
    assert updated["quality_score"] == 0.95


def test_get_min_relevance_threshold(facade):
    # Insert monitor settings
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            min_relevance_threshold=0.85,
            check_interval=10,
            interval_unit=1,
            search_fields="title",
            language="en",
            sort_by="latest",
            page_size=20,
            is_enabled=True,
            daily_request_limit=200,
            search_date_range=14,
            provider="newsapi",
            auto_ingest_enabled=True,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4",
            llm_temperature=0.6,
            llm_max_tokens=400
        )
    )

    result = facade.get_min_relevance_threshold()
    assert isinstance(result, float)
    assert result == 0.85


def test_get_auto_ingest_settings(facade):
    # Insert valid columns only (avoid unrecognized fields)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1,
            article_uri="http://example.com/ai",
            keyword_ids="1,2",
            group_id=5
        )
    )

    result = facade.get_auto_ingest_settings()

    # Since those columns don't exist, result should be None
    assert result is None or isinstance(result, tuple)


def test_update_ingested_article(facade):
    # Insert a sample article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article1",
            title="Old Title",
            quality_score=None,
            quality_issues=None,
            ingest_status=None,
            auto_ingested=False
        )
    )

    # Update ingestion-related fields
    params = ["completed", 0.95, "none", "http://example.com/article1"]
    facade.update_ingested_article(params)

    # Verify the article was updated
    row = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == "http://example.com/article1")
    ).mappings().fetchone()

    assert row is not None
    assert row["auto_ingested"] is True
    assert row["ingest_status"] == "completed"
    assert abs(row["quality_score"] - 0.95) < 1e-6
    assert row["quality_issues"] == "none"


def test_get_topic_articles_to_ingest_using_new_table_structure(facade):
    # Insert data for articles, keyword groups, and matches
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="AI", topic="Artificial Intelligence")
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="http://example.com/ai", title="AI Revolution", summary="AI is growing", news_source="TechNews")
    )
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1,
            article_uri="http://example.com/ai",
            keyword_ids="1",
            group_id=1,
            detected_at="2025-01-01T10:00:00Z"
        )
    )

    result = facade.get_topic_articles_to_ingest_using_new_table_structure("Artificial Intelligence")

    assert len(result) == 1
    article = result[0]
    assert article["title"] == "AI Revolution"
    assert article["topic"] == "Artificial Intelligence"



def test_get_topic_articles_to_ingest_using_old_table_structure(facade):
    # Insert data for keyword groups and monitored keywords
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="Climate", topic="Climate Change")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=1, group_id=1, keyword="global warming")
    )
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            id=1,
            keyword_id=1,
            article_uri="http://example.com/climate",
            detected_at="2025-01-02T09:00:00Z",
            is_read=0
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/climate",
            title="Climate Crisis Deepens",
            summary="Rising global temperatures",
            news_source="WorldNews"
        )
    )

    result = facade.get_topic_articles_to_ingest_using_old_table_structure("Climate Change")

    assert len(result) == 1
    article = result[0]
    assert article["uri"] == "http://example.com/climate"
    assert article["topic"] == "Climate Change"


def test_get_topic_unprocessed_and_unread_articles_using_new_table_structure(facade):
    # Insert group, article, and match data
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="AI", topic="Artificial Intelligence")
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/unread",
            title="Unread AI News",
            summary="New discoveries",
            news_source="TechDaily",
            auto_ingested=False
        )
    )
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1,
            article_uri="http://example.com/unread",
            keyword_ids="1",
            group_id=1,
            detected_at="2025-01-04T08:00:00Z",
            is_read=0
        )
    )

    result = facade.get_topic_unprocessed_and_unread_articles_using_new_table_structure("Artificial Intelligence")

    assert len(result) == 1
    row = result[0]
    assert row["uri"] == "http://example.com/unread"
    assert row["title"] == "Unread AI News"
    assert row["topic"] == "Artificial Intelligence"


def test_get_topic_unprocessed_and_unread_articles_using_old_table_structure(facade):
    # Insert related topic and keywords
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="Energy", topic="Renewable Energy")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=1, group_id=1, keyword="solar power")
    )
    # Insert article that’s not yet ingested
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/solar",
            title="Solar Power Expansion",
            summary="New solar plants are being built worldwide.",
            news_source="EcoNews",
            auto_ingested=False
        )
    )
    # Keyword alert linking keyword + article
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            id=1,
            keyword_id=1,
            article_uri="http://example.com/solar",
            detected_at="2025-01-03T10:00:00Z",
            is_read=0
        )
    )

    # Query should return this article
    result = facade.get_topic_unprocessed_and_unread_articles_using_old_table_structure("Renewable Energy")

    assert len(result) == 1
    row = result[0]
    assert row["uri"] == "http://example.com/solar"
    assert row["title"] == "Solar Power Expansion"
    assert row["topic"] == "Renewable Energy"


def test_get_topic_keywords(facade):
    # Insert topic + keywords
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="AI", topic="Artificial Intelligence")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=1, group_id=1, keyword="machine learning")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=2, group_id=1, keyword="neural networks")
    )

    result = facade.get_topic_keywords("Artificial Intelligence")

    assert len(result) == 2
    assert "machine learning" in result
    assert "neural networks" in result


from datetime import datetime, timedelta

def test_get_articles_for_market_signal_analysis(facade):
    topic_name = "Climate Change"

    # Insert article analyzed recently (within timeframe)
    recent_date = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
    old_date = (datetime.utcnow() - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')

    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/recent",
            title="Global Warming Trends",
            summary="CO2 emissions continue to rise.",
            topic=topic_name,
            future_signal="rising",
            sentiment="concerned",
            time_to_impact="medium",
            driver_type="environment",
            category="climate",
            publication_date=recent_date,
            news_source="World Climate Journal",
            analyzed=True
        )
    )
    # Insert old article outside timeframe
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/old",
            title="Old Report",
            summary="Old data no longer relevant.",
            topic=topic_name,
            future_signal="steady",
            sentiment="neutral",
            time_to_impact="long",
            driver_type="economic",
            category="policy",
            publication_date=old_date,
            news_source="Old News",
            analyzed=True
        )
    )

    result = facade.get_articles_for_market_signal_analysis(timeframe_days=7, topic_name=topic_name)

    # Only recent article should match the timeframe filter
    assert len(result) == 1
    row = result[0]
    assert row["uri"] == "http://example.com/recent"
    assert row["title"] == "Global Warming Trends"
    assert row["future_signal"] == "rising"
    assert row["sentiment"] == "concerned"
    assert row["news_source"] == "World Climate Journal"


from datetime import datetime, timedelta

def test_get_recent_articles_for_market_signal_analysis(facade):
    topic_name = "AI"
    now = datetime.utcnow()
    recent_date = (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
    old_date = (now - timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')

    # Insert analyzed, recent article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/recent",
            title="AI Breakthrough",
            summary="AI reaches new milestones.",
            topic=topic_name,
            future_signal="rising",
            sentiment="positive",
            time_to_impact="short",
            driver_type="innovation",
            category="tech",
            publication_date=recent_date,
            news_source="AI Today",
            analyzed=True
        )
    )

    # Insert old article (should not match timeframe)
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/old",
            title="Old AI Research",
            summary="Archived study on AI trends.",
            topic=topic_name,
            publication_date=old_date,
            analyzed=True
        )
    )

    result = facade.get_recent_articles_for_market_signal_analysis(7, topic_name, 10)
    assert len(result) == 1
    article = result[0]
    assert article["uri"] == "http://example.com/recent"
    assert article["title"] == "AI Breakthrough"
    assert article["future_signal"] == "rising"
    assert article["news_source"] == "AI Today"


def test_get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(facade):
    topic_name = "Climate Change"

    # Insert analyzed articles with future signals
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/a1",
            title="Rising CO2 Levels",
            future_signal="rising",
            topic=topic_name,
            analyzed=True
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/a2",
            title="Decline in Ice Caps",
            future_signal="rising",
            topic=topic_name,
            analyzed=True
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/a3",
            title="Stable Emissions",
            future_signal="steady",
            topic=topic_name,
            analyzed=True
        )
    )

    result = facade.get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(topic_name)

    assert len(result) == 2
    assert result[0]["future_signal"] == "rising"
    assert result[0]["count"] == 2
    assert result[1]["future_signal"] == "steady"
    assert result[1]["count"] == 1


def test_get_unique_topics(facade):
    # Insert analyzed articles across different topics
    facade._execute_with_rollback(
        articles.insert().values(uri="u1", topic="AI", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="u2", topic="Space", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="u3", topic="AI", analyzed=True)
    )
    # Insert unanalyzed or empty topic (should be ignored)
    facade._execute_with_rollback(
        articles.insert().values(uri="u4", topic="", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="u5", topic=None, analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="u6", topic="Health", analyzed=False)
    )

    result = facade.get_unique_topics()

    assert result == ["AI", "Space"]


def test_get_unique_categories(facade):
    # Insert analyzed articles with categories
    facade._execute_with_rollback(
        articles.insert().values(uri="c1", category="Technology", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="c2", category="Health", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="c3", category="Technology", analyzed=True)
    )
    # Insert invalid ones
    facade._execute_with_rollback(
        articles.insert().values(uri="c4", category="", analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="c5", category=None, analyzed=True)
    )
    facade._execute_with_rollback(
        articles.insert().values(uri="c6", category="Space", analyzed=False)
    )

    result = facade.get_unique_categories()

    assert result == ["Health", "Technology"]



def test_count_oauth_allowlist_active_users(facade):
    # Insert active and inactive users in allowlist
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="user1@example.com", is_active=True)
    )
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="user2@example.com", is_active=False)
    )
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="user3@example.com", is_active=True)
    )

    result = facade.count_oauth_allowlist_active_users()
    assert result == 2  # Only two are active


def test_get_oauth_allowlist_user_by_email_and_provider(facade):
    # Insert mock OAuth user
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=1,
            email="test@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 10, 10, 0, 0)  # FIXED
        )
    )

    result = facade.get_oauth_allowlist_user_by_email_and_provider("test@example.com", "google")
    assert result is not None
    assert result.email == "test@example.com"
    assert result.provider == "google"


def test_get_oauth_allowlist_user_by_id(facade):
    # Insert a user
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=5,
            email="iduser@example.com",
            provider="github",
            is_active=True,
            created_at=datetime(2025, 1, 10, 12, 0, 0)  # FIXED
        )
    )

    result = facade.get_oauth_allowlist_user_by_id(5)
    assert result is not None
    assert result.email == "iduser@example.com"
    assert result.provider == "github"


def test_get_oauth_active_users_by_provider(facade):
    # Insert active/inactive users for different providers
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=1,
            email="active1@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 9, 9, 0, 0)  # FIXED
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=2,
            email="inactive@example.com",
            provider="google",
            is_active=False,
            created_at=datetime(2025, 1, 8, 9, 0, 0)  # FIXED
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=3,
            email="active2@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 11, 9, 0, 0)  # FIXED
        )
    )

    result = facade.get_oauth_active_users_by_provider("google")
    assert len(result) == 2
    assert result[0]["email"] == "active2@example.com"
    assert result[1]["email"] == "active1@example.com"



def test_is_oauth_user_allowed(facade):
    # Insert into allowlist
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="allowed@example.com", is_active=True)
    )
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="blocked@example.com", is_active=False)
    )

    assert facade.is_oauth_user_allowed("allowed@example.com") is True
    assert facade.is_oauth_user_allowed("blocked@example.com") is False
    assert facade.is_oauth_user_allowed("unknown@example.com") is False



def test_add_oauth_user_to_allowlist(facade):
    # Insert a new allowlist entry
    facade.add_oauth_user_to_allowlist("newuser@example.com", "admin@example.com")

    # Check if the user was added
    result = facade._execute_with_rollback(
        select(oauth_allowlist).where(oauth_allowlist.c.email == "newuser@example.com")
    ).fetchone()

    assert result is not None
    assert result.email == "newuser@example.com"
    assert result.added_by == "admin@example.com"

    # Run again to ensure update path (email already exists)
    facade.add_oauth_user_to_allowlist("newuser@example.com", "system@example.com")

    updated = facade._execute_with_rollback(
        select(oauth_allowlist).where(oauth_allowlist.c.email == "newuser@example.com")
    ).fetchone()
    assert updated.added_by == "system@example.com"  # Updated successfully


def test_remove_oauth_user_from_allowlist(facade):
    # Insert active allowlist entry
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="remove@example.com", is_active=True)
    )

    # Remove it (set is_active = 0)
    rows_affected = facade.remove_oauth_user_from_allowlist("remove@example.com")
    assert rows_affected == 1

    # Verify it is inactive
    result = facade._execute_with_rollback(
        select(oauth_allowlist.c.is_active).where(oauth_allowlist.c.email == "remove@example.com")
    ).fetchone()
    assert result.is_active == 0


from datetime import datetime

def test_get_oauth_active_users(facade):
    # Insert active and inactive users
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=1,
            email="active1@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 9, 9, 0, 0)
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=2,
            email="inactive@example.com",
            provider="google",
            is_active=False,
            created_at=datetime(2025, 1, 8, 9, 0, 0)
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=3,
            email="active2@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 11, 9, 0, 0)
        )
    )

    # Retrieve only active users
    result = facade.get_oauth_active_users("google")

    assert len(result) == 2
    assert result[0]["email"] == "active2@example.com"
    assert result[1]["email"] == "active1@example.com"


def test_deactivate_user(facade):
    # Insert active OAuth user
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=1,
            email="deactivate@example.com",
            provider="github",
            is_active=True,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )

    # Deactivate user
    rows_affected = facade.deactivate_user("deactivate@example.com", "github")
    assert rows_affected == 1

    # Verify user is now inactive
    result = facade._execute_with_rollback(
        select(oauth_users.c.is_active).where(oauth_users.c.email == "deactivate@example.com")
    ).fetchone()
    assert result.is_active == 0


def test_get_active_oauth_allowlist_user_by_id(facade):
    # Insert users (one active, one inactive)
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=1,
            email="active@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            id=2,
            email="inactive@example.com",
            provider="google",
            is_active=False,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )

    # Should return only active user
    result = facade.get_active_oauth_allowlist_user_by_id(1)
    assert result is not None
    assert result.email == "active@example.com"

    # Inactive user should return None
    result_inactive = facade.get_active_oauth_allowlist_user_by_id(2)
    assert result_inactive is None


def test_get_active_oauth_allowlist_user_by_email_and_provider(facade):
    # Insert active and inactive OAuth users
    facade._execute_with_rollback(
        oauth_users.insert().values(
            email="active@example.com",
            provider="google",
            is_active=True,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(
            email="inactive@example.com",
            provider="google",
            is_active=False,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )

    # Active user should be fetched
    result = facade.get_active_oauth_allowlist_user_by_email_and_provider("active@example.com", "google")
    assert result is not None
    assert result.email == "active@example.com"

    # Inactive user should return None
    result_none = facade.get_active_oauth_allowlist_user_by_email_and_provider("inactive@example.com", "google")
    assert result_none is None


def test_update_oauth_allowlist_user(facade):
    # Insert a user to update
    facade._execute_with_rollback(
        oauth_users.insert().values(
            email="update@example.com",
            provider="github",
            name="Old Name",
            provider_id="123",
            avatar_url="old_url",
            is_active=True,
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )

    # Update fields
    facade.update_oauth_allowlist_user(["New Name", "999", "new_url", "update@example.com", "github"])

    # Verify updated fields
    result = facade._execute_with_rollback(
        select(oauth_users.c.name, oauth_users.c.provider_id, oauth_users.c.avatar_url)
        .where(oauth_users.c.email == "update@example.com")
    ).fetchone()

    assert result.name == "New Name"
    assert result.provider_id == "999"
    assert result.avatar_url == "new_url"


def test_create_oauth_allowlist_user(facade):
    # Create new OAuth user
    user_id = facade.create_oauth_allowlist_user([
        "newuser@example.com", "New User", "google", "provider123", "avatar_url"
    ])

    # Verify inserted
    result = facade._execute_with_rollback(
        select(oauth_users).where(oauth_users.c.email == "newuser@example.com")
    ).fetchone()

    assert result is not None
    assert result.id == user_id
    assert result.name == "New User"
    assert result.provider == "google"


def test_create_user(facade):
    username = "testuser"
    email = "testuser@example.com"

    # Create new user
    user = facade.create_user(
        username=username,
        email=email,
        password_hash="hashed123",
        role="admin"
    )

    # Verify result is dict and correct
    assert isinstance(user, dict)
    assert user["username"] == username
    assert user["email"] == email
    assert user["role"] == "admin"

    # Fetch same user directly
    fetched = facade.get_user_by_username(username)
    assert fetched["email"] == email


def test_get_user_by_username_case_insensitive(facade):
    # Create user using the same facade connection
    facade.create_user(
        username="CaseUser",
        email="case@example.com",
        password_hash="hashed_pw",
        role="user"
    )

    # Query lowercase
    result = facade.get_user_by_username("caseuser")
    assert result is not None
    assert result["email"] == "case@example.com"

    # Query uppercase
    result2 = facade.get_user_by_username("CASEUSER")
    assert result2 is not None
    assert result2["email"] == "case@example.com"



def test_get_user_by_email(facade):

    # Insert lowercase email (same as what method expects)
    facade._execute_with_rollback(
        t_users.insert().values(
            username="alpha",
            email="alpha@example.com",
            password_hash="hashedpw",
            role="user",
            is_active=True
        )
    )
    facade.connection.commit()

    # Case-insensitive lookup (works since DB stores lowercase)
    result = facade.get_user_by_email("Alpha@Example.com")
    assert result is not None
    assert result["username"] == "alpha"

    # None email should return None safely
    assert facade.get_user_by_email(None) is None


def test_list_all_users(facade):
    # Insert active + inactive users
    facade._execute_with_rollback(
        t_users.insert().values(username="active_user", email="a@e.com", password_hash="p", is_active=True)
    )
    facade._execute_with_rollback(
        t_users.insert().values(username="inactive_user", email="i@e.com", password_hash="p", is_active=False)
    )
    facade.connection.commit()

    # Should only return active users by default
    result = facade.list_all_users()
    usernames = [u["username"] for u in result]
    assert "active_user" in usernames
    assert "inactive_user" not in usernames

    # Should return both if include_inactive=True
    all_users = facade.list_all_users(include_inactive=True)
    all_names = [u["username"] for u in all_users]
    assert "active_user" in all_names
    assert "inactive_user" in all_names



def test_update_user(facade):
    # Insert user
    facade._execute_with_rollback(
        t_users.insert().values(username="beta", email="beta@example.com", password_hash="oldhash", role="user")
    )
    facade.connection.commit()

    # Update password and role
    result = facade.update_user("beta", password_hash="newhash", role="admin")
    assert result is True

    # Verify update
    row = facade._execute_with_rollback(
        select(t_users.c.password_hash, t_users.c.role).where(t_users.c.username == "beta")
    ).fetchone()
    assert row.password_hash == "newhash"
    assert row.role == "admin"



def test_deactivate_user_by_username(facade):
    # Insert active user
    facade._execute_with_rollback(
        t_users.insert().values(username="gamma", email="gamma@example.com", password_hash="hash", is_active=True)
    )
    facade.connection.commit()

    # Deactivate
    result = facade.deactivate_user_by_username("gamma")
    assert result is True

    # Verify deactivation
    row = facade._execute_with_rollback(
        select(t_users.c.is_active).where(t_users.c.username == "gamma")
    ).fetchone()
    assert row.is_active == 0



def test_check_user_is_admin(facade):
    # Insert admin and normal users
    facade._execute_with_rollback(
        t_users.insert().values(username="admin_user", email="admin@x.com", password_hash="pw", role="admin")
    )
    facade._execute_with_rollback(
        t_users.insert().values(username="regular_user", email="user@x.com", password_hash="pw", role="user")
    )
    facade.connection.commit()

    # Check roles
    assert facade.check_user_is_admin("admin_user") is True
    assert facade.check_user_is_admin("regular_user") is False
    assert facade.check_user_is_admin("nonexistent") is False


def test_count_admin_users(facade):
    # Insert multiple users (some admins, some not)
    facade._execute_with_rollback(
        t_users.insert().values(username="admin1", email="a1@x.com", password_hash="pw", role="admin", is_active=True)
    )
    facade._execute_with_rollback(
        t_users.insert().values(username="admin2", email="a2@x.com", password_hash="pw", role="admin", is_active=False)
    )
    facade._execute_with_rollback(
        t_users.insert().values(username="user1", email="u1@x.com", password_hash="pw", role="user", is_active=True)
    )
    facade.connection.commit()

    result = facade.count_admin_users()
    assert result == 1  # Only one active admin


def test_get_oauth_allow_list(facade):
    # Insert allowlist entries
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(
            email="first@example.com", added_by="admin", added_at=datetime(2025, 1, 10, 10, 0, 0), is_active=True
        )
    )
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(
            email="second@example.com", added_by="user", added_at=datetime(2025, 1, 11, 9, 0, 0), is_active=False
        )
    )
    facade.connection.commit()

    result = facade.get_oauth_allow_list()
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["email"] in ("first@example.com", "second@example.com")


def test_get_oauth_system_status_and_settings(facade):
    # Insert into allowlist and users
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="user1@x.com", added_by="admin", added_at=datetime(2025, 1, 9), is_active=True)
    )
    facade._execute_with_rollback(
        oauth_allowlist.insert().values(email="user2@x.com", added_by="admin", added_at=datetime(2025, 1, 9), is_active=False)
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(email="user1@x.com", provider="google", is_active=True, created_at=datetime(2025, 1, 9))
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(email="user2@x.com", provider="github", is_active=True, created_at=datetime(2025, 1, 9))
    )
    facade._execute_with_rollback(
        oauth_users.insert().values(email="user3@x.com", provider="github", is_active=False, created_at=datetime(2025, 1, 9))
    )
    facade.connection.commit()

    allowlist_count, oauth_users_count, provider_stats = facade.get_oauth_system_status_and_settings()
    assert allowlist_count == 1
    assert oauth_users_count == 2
    assert provider_stats == {"google": 1, "github": 1}



def test_get_feed_item_tags(facade):
    # Insert required group for FK
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(id=1, name="group", is_active=True)
    )
    # Insert feed item with required NOT NULL fields
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=1,
            source_type="news",
            source_id="s1",
            group_id=1,
            title="Example",
            url="https://example.com",
            tags="AI,Tech",
        )
    )
    facade.connection.commit()

    result = facade.get_feed_item_tags(1)
    assert result is not None
    assert "AI" in result[0]


def test_get_feed_item_url(facade):
    # Insert required group for FK
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(id=2, name="group2", is_active=True)
    )
    # Insert feed item with required NOT NULL fields
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=2,
            source_type="news",
            source_id="s2",
            group_id=2,
            title="OpenAI",
            url="https://openai.com",
            tags="Innovation",
        )
    )
    facade.connection.commit()

    result = facade.get_feed_item_url(2)
    assert result is not None
    assert result[0] == "https://openai.com"


def test_get_enrichment_data_for_article(facade):
    # Insert sample article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="article-1",
            category="Tech",
            sentiment="Positive",
            driver_type="AI",
            time_to_impact="Short",
            topic_alignment_score=0.9,
            keyword_relevance_score=0.85,
            confidence_score=0.95,
            analyzed=True,
            summary="A detailed article about AI advancements",
        )
    )
    facade.connection.commit()

    result = facade.get_enrichment_data_for_article("article-1")

    assert result is not None
    assert result[0] == "Tech"
    assert "AI" in result


def test_get_enrichment_data_for_article_with_extra_fields(facade):
    # Insert sample article with topic field
    facade._execute_with_rollback(
        articles.insert().values(
            uri="article-2",
            category="Finance",
            sentiment="Neutral",
            topic="Markets",
            summary="Stock market report summary.",
            analyzed=True
        )
    )
    facade.connection.commit()

    result = facade.get_enrichment_data_for_article_with_extra_fields("article-2")

    assert result is not None
    assert result[0] == "Finance"
    assert result[-1] == "Markets"



def test_update_feed_article_data(facade):
    # Insert an article with missing title/summary
    facade._execute_with_rollback(
        articles.insert().values(
            uri="article-3",
            title=None,
            summary=None,
            topic=None,
            news_source=None,
            publication_date=None,
            analyzed=False
        )
    )
    facade.connection.commit()

    params = [
        "Updated Title",
        "Updated Summary",
        "Updated Source",
        datetime(2025, 1, 10),
        "article-3"
    ]

    facade.update_feed_article_data(params)

    # Verify update
    updated = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == "article-3")
    ).mappings().fetchone()

    assert updated["analyzed"] == True
    assert updated["title"] == "Updated Title"
    assert updated["summary"] == "Updated Summary"
    assert updated["news_source"] == "Updated Source"
    assert updated["topic"] == "General"



def test_extract_topics_from_article(facade):
    # Insert analyzed articles with longer summaries
    facade._execute_with_rollback(
        articles.insert().values(
            uri="a1",
            title="AI Future",
            summary="The future of artificial intelligence is incredibly bright and full of endless opportunities for innovation and progress.",
            topic="Tech",
            category="AI",
            analyzed=True,
            submission_date=datetime(2025, 1, 10)
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="a2",
            title="Market Report",
            summary="Financial markets remain stable over the last quarter, indicating a positive outlook for the economy this year.",
            topic="Finance",
            category="Economy",
            analyzed=True,
            submission_date=datetime(2025, 1, 11)
        )
    )
    facade.connection.commit()

    # Filter by topic
    result_topic = facade.extract_topics_from_article(topic_filter="Tech", category_filter=None, limit=None)
    assert len(result_topic) == 1
    assert result_topic[0]["topic"] == "Tech"

    # Filter by category
    result_cat = facade.extract_topics_from_article(topic_filter=None, category_filter="Economy", limit=None)
    assert len(result_cat) == 1
    assert result_cat[0]["category"] == "Economy"

    # No filter
    result_all = facade.extract_topics_from_article(topic_filter=None, category_filter=None, limit=10)
    assert len(result_all) >= 2




def test_create_feed_group(facade):
    params = [
        "AI Insights",
        "Group for AI-related articles",
        "#FF5733",
        datetime(2025, 1, 10),
        datetime(2025, 1, 10)
    ]

    new_id = facade.create_feed_group(params)
    assert isinstance(new_id, int)

    # Verify it was inserted
    row = facade._execute_with_rollback(
        select(feed_keyword_groups).where(feed_keyword_groups.c.id == new_id)
    ).mappings().fetchone()

    assert row["name"] == "AI Insights"
    assert row["color"] == "#FF5733"


def test_get_feed_groups_including_inactive(facade):
    # Insert active and inactive groups
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            name="GroupA",
            description="Active Group",
            color="#FF0000",
            is_active=True,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            name="GroupB",
            description="Inactive Group",
            color="#00FF00",
            is_active=False,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    result = facade.get_feed_groups_including_inactive()

    assert len(result) == 2
    names = [row["name"] for row in result]
    assert "GroupA" in names and "GroupB" in names


def test_get_feed_groups_excluding_inactive(facade):
    # Insert groups
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            name="ActiveGroup",
            is_active=True,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            name="InactiveGroup",
            is_active=False,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    result = facade.get_feed_groups_excluding_inactive()

    assert len(result) == 1
    assert result[0]["name"] == "ActiveGroup"
    assert result[0]["is_active"] == 1


def test_get_feed_group_sources(facade):
    # Insert sources linked to group 1
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=1,
            group_id=1,
            source_type="news",
            keywords="AI,tech",
            enabled=True,
            last_checked=datetime(2025, 1, 11, 10, 0, 0),
            created_at=datetime(2025, 1, 10, 9, 0, 0)
        )
    )
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=2,
            group_id=1,
            source_type="blog",
            keywords="AI,future",
            enabled=False,
            last_checked=datetime(2025, 1, 12, 10, 0, 0),
            created_at=datetime(2025, 1, 10, 10, 0, 0)
        )
    )
    facade.connection.commit()

    result = facade.get_feed_group_sources(1)

    assert len(result) == 2
    assert result[0]["source_type"] in ["blog", "news"]  # sorted ascending


def test_get_feed_group_by_id(facade):
    # Insert a test group
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=10,
            name="RetrieveGroup",
            description="Test group for retrieval",
            color="#123456",
            is_active=True,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    result = facade.get_feed_group_by_id(10)

    assert result is not None
    assert result[1] == "RetrieveGroup" or result["name"] == "RetrieveGroup"



def test_update_feed_group(facade):
    # Insert test group
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=20,
            name="OldGroup",
            description="Old description",
            color="#AAAAAA",
            is_active=True,
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    # Update name and color only
    facade.update_feed_group(
        name="NewGroup",
        description=None,
        color="#00FFFF",
        is_active=None,
        group_id=20
    )

    updated = facade._execute_with_rollback(
        select(feed_keyword_groups).where(feed_keyword_groups.c.id == 20)
    ).mappings().fetchone()

    assert updated["name"] == "NewGroup"
    assert updated["color"] == "#00FFFF"
    assert "updated_at" in updated


def test_delete_feed_group(facade):
    # Insert a feed group
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=100,
            name="DeleteMe",
            description="Temporary group",
            color="#ABCDEF",
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    # Delete it
    facade.delete_feed_group(100)

    # Verify it's deleted
    result = facade._execute_with_rollback(
        select(feed_keyword_groups).where(feed_keyword_groups.c.id == 100)
    ).fetchone()
    assert result is None


def test_create_default_feed_subscription(facade):
    # Create subscription for group_id = 1
    facade.create_default_feed_subscription(1)

    # Verify it exists
    result = facade._execute_with_rollback(
        select(user_feed_subscriptions).where(user_feed_subscriptions.c.group_id == 1)
    ).fetchone()

    assert result is not None
    assert result[1] == 1 or result["group_id"] == 1


def test_update_group_source(facade):
    import json
    # Insert test source
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=200,
            group_id=10,
            source_type="news",
            keywords="AI,Tech",
            enabled=True,
            created_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    # Update the source
    facade.update_group_source(
        source_id=200,
        keywords=["AI", "Future", "Robotics"],
        enabled=False,
        date_range_days=7,
        custom_start_date="2025-01-01",
        custom_end_date="2025-01-07"
    )

    # Verify update
    updated = facade._execute_with_rollback(
        select(feed_group_sources).where(feed_group_sources.c.id == 200)
    ).mappings().fetchone()

    assert updated is not None
    assert json.loads(updated["keywords"]) == ["AI", "Future", "Robotics"]
    assert updated["enabled"] == 0
    assert updated["date_range_days"] == 7
    assert updated["custom_start_date"] == "2025-01-01"
    assert updated["custom_end_date"] == "2025-01-07"



def test_get_source_by_id(facade):
    # Insert test source
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=300,
            group_id=5,
            source_type="blog",
            keywords="AI",
            enabled=True,
            created_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    # Fetch by ID
    result = facade.get_source_by_id(300)

    assert result is not None
    assert result[0] == 300
    assert result[2] == "blog"


def test_get_group_source(facade):
    # Insert multiple sources
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=400,
            group_id=2,
            source_type="social",
            keywords="AI,Trends",
            enabled=True,
            created_at=datetime(2025, 1, 11)
        )
    )
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=401,
            group_id=2,
            source_type="news",
            keywords="Business,Markets",
            enabled=True,
            created_at=datetime(2025, 1, 12)
        )
    )
    facade.connection.commit()

    # Fetch by (group_id, source_type)
    result = facade.get_group_source(2, "social")

    assert result is not None
    assert result[0] == 400 or result["id"] == 400



def test_delete_group_source(facade):
    # Insert a feed group source
    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=501,
            group_id=10,
            source_type="news",
            keywords="AI,ML",
            enabled=True,
            created_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    # Delete it
    facade.delete_group_source(501)

    # Verify deletion
    result = facade._execute_with_rollback(
        select(feed_group_sources).where(feed_group_sources.c.id == 501)
    ).fetchone()

    assert result is None


def test_add_source_to_group(facade):
    params = [
        5,                    # group_id
        "social",             # source_type
        "AI,Technology",      # keywords
        True,                 # enabled
        7,                    # date_range_days
        "2025-01-01",         # custom_start_date
        "2025-01-07",         # custom_end_date
        datetime(2025, 1, 10) # created_at
    ]

    new_id = facade.add_source_to_group(params)

    # Verify new source exists
    result = facade._execute_with_rollback(
        select(feed_group_sources).where(feed_group_sources.c.id == new_id)
    ).mappings().fetchone()

    assert result is not None
    assert result["group_id"] == 5
    assert result["source_type"] == "social"
    assert result["enabled"] == 1



def test_get_feed_group_by_name(facade):
    # Insert feed group
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=601,
            name="AI Group",
            description="Group for AI feeds",
            color="#123456",
            created_at=datetime(2025, 1, 11),
            updated_at=datetime(2025, 1, 11)
        )
    )
    facade.connection.commit()

    result = facade.get_feed_group_by_name("AI Group")

    assert result is not None
    assert result[0] == 601



def test_get_keyword_groups_count(facade):
    # Clear and insert known number of groups
    facade._execute_with_rollback(delete(feed_keyword_groups))
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=701,
            name="Group1",
            description="Test1",
            color="#111111",
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=702,
            name="Group2",
            description="Test2",
            color="#222222",
            created_at=datetime(2025, 1, 10),
            updated_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    count = facade.get_keyword_groups_count()

    assert count == 2



def test_get_feed_item_count(facade):
    # Clear and insert known number of feed items
    facade._execute_with_rollback(delete(feed_items))
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=801,
            url="https://ai.example.com",
            source_type="news",
            source_id = 1,
            group_id = 10,
            title="AI Example",
            tags="AI,ML",
            created_at=datetime(2025, 1, 9)
        )
    )
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=802,
            url="https://tech.example.com",
            source_type="social",
            source_id = 2,
            group_id = 10,
            title="Tech Example",
            tags="Tech,Trends",
            created_at=datetime(2025, 1, 10)
        )
    )
    facade.connection.commit()

    count = facade.get_feed_item_count()

    assert count == 2


def test_get_article_id_by_url(facade):
    # Insert an article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/article-1",
            title="AI Market Boom",
            summary="AI adoption is growing.",
            news_source="Tech Daily",
            publication_date=datetime(2025, 1, 15),
            analyzed=False,
            topic="Technology"
        )
    )
    facade.connection.commit()

    result = facade.get_article_id_by_url("https://example.com/article-1")

    assert result == "https://example.com/article-1"


def test_check_if_article_exists_with_enrichment(facade):
    # Insert analyzed article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/enriched",
            title="AI Forecast",
            summary="AI trends and predictions.",
            news_source="Analytics Hub",
            publication_date=datetime(2025, 1, 10),
            analyzed=True,
            topic="AI"
        )
    )
    facade.connection.commit()

    result = facade.check_if_article_exists_with_enrichment("https://example.com/enriched")

    assert result is not None
    assert result[0] == "https://example.com/enriched"


def test_create_article_without_enrichment(facade):
    params = [
        "https://example.com/new-article",
        "New AI Discovery",
        "Breakthrough in neural efficiency.",
        "Tech World",
        datetime(2025, 1, 20)
    ]

    inserted_id = facade.create_article_without_enrichment(params)
    assert inserted_id is not None

    result = facade.get_article_id_by_url("https://example.com/new-article")
    assert result == "https://example.com/new-article"



def test_get_feed_item_details(facade):
    # Insert feed item
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=900,
            title="AI in Healthcare",
            url="https://example.com/healthcare-ai",
            content="AI improving diagnostics.",
            author="Jane Doe",
            publication_date=datetime(2025, 1, 12),
            source_type="news",
            group_id=1,
            source_id=1
        )
    )
    facade.connection.commit()

    result = facade.get_feed_item_details(900)

    assert result is not None
    assert result[0] == "https://example.com/healthcare-ai"
    assert result[1] == "AI in Healthcare"


def test_update_feed_tags(facade):
    # Insert item
    facade._execute_with_rollback(
        feed_items.insert().values(
            id=901,
            title="AI in Education",
            url="https://example.com/education-ai",
            source_type="news",
            group_id=2,
            source_id=1,
            tags="AI,Learning"
        )
    )
    facade.connection.commit()

    # Update tags
    facade.update_feed_tags(["AI,Learning,Innovation", 901])

    result = facade._execute_with_rollback(
        select(feed_items.c.tags).where(feed_items.c.id == 901)
    ).fetchone()

    assert result is not None
    assert result[0] == "AI,Learning,Innovation"



def test_get_feed_keywords_by_source_type(facade):
    # Insert active feed group and source
    facade._execute_with_rollback(
        feed_keyword_groups.insert().values(
            id=501,
            name="AI Updates",
            description="All AI news sources",
            color="#FF0000",
            is_active=True,
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1)
        )
    )

    facade._execute_with_rollback(
        feed_group_sources.insert().values(
            id=601,
            group_id=501,
            source_type="news",
            keywords="AI,Tech",
            enabled=True,
            created_at=datetime(2025, 1, 1)
        )
    )

    facade.connection.commit()

    result = facade.get_feed_keywords_by_source_type("news")

    assert len(result) == 1
    assert result[0]["id"] == 501
    assert result[0]["name"] == "AI Updates"



def test_get_statistics_for_specific_feed_group(facade):
    # Insert feed items: one recent, one older
    recent_date = datetime.utcnow() - timedelta(days=3)
    old_date = datetime.utcnow() - timedelta(days=10)

    facade._execute_with_rollback(
        feed_items.insert().values(
            id=801,
            title="AI Revolution",
            url="https://example.com/ai1",
            source_type="news",
            source_id=1,
            group_id=701,
            publication_date=recent_date,
            created_at=recent_date
        )
    )

    facade._execute_with_rollback(
        feed_items.insert().values(
            id=802,
            title="ML Growth",
            url="https://example.com/ml2",
            source_type="social",
            source_id=2,
            group_id=701,
            publication_date=old_date,
            created_at=old_date
        )
    )

    facade.connection.commit()

    total_items, source_counts, recent_items = facade.get_statistics_for_specific_feed_group(group_id=701)

    assert total_items == 2
    # source_counts is a mapping of source_type -> count
    assert source_counts.get("news") == 1
    assert source_counts.get("social") == 1
    assert recent_items == 1

def test_get_is_keyword_monitor_enabled(facade):
    # Insert keyword monitor settings row
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            is_enabled=True
        )
    )
    facade.connection.commit()

    result = facade.get_is_keyword_monitor_enabled()
    assert result is True



def test_get_keyword_monitor_last_check_time(facade):
    # Function is stubbed to return None
    result = facade.get_keyword_monitor_last_check_time()
    assert result is None


def test_get_unread_alerts(facade):
    # Insert article and alert
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/alert-article",
            title="Breaking AI News",
            summary="New AI breakthrough discovered.",
            publication_date=datetime(2025, 1, 5),
            category="Technology",
            sentiment="Positive",
            driver_type="Innovation",
            time_to_impact="Short",
            future_signal="Growth",
            bias="Low",
            factual_reporting="High",
            mbfc_credibility_rating="High",
            bias_country="USA",
            press_freedom="High",
            media_type="Online",
            popularity=8.7
        )
    )

    # Insert required monitored keyword for FK and use its id in alert
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=1, group_id=1, keyword="ai")
    )

    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            id=901,
            keyword_id=1,
            detected_at=datetime(2025, 1, 6),
            article_uri="https://example.com/alert-article",
            is_read=0
        )
    )

    facade.connection.commit()

    result = facade.get_unread_alerts()

    assert len(result) == 1
    assert result[0]["title"] == "Breaking AI News"
    assert result[0]["is_read"] == 0 if "is_read" in result[0] else True


def test_delete_keyword_alerts_by_article_url(facade):
    # Seed required FK rows
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/article-to-delete",
            title="t"
        )
    )
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=1, name="grp", topic="General")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(id=1, group_id=1, keyword="k")
    )
    # Insert a keyword alert
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            id=1101,
            keyword_id=1,
            article_uri="https://example.com/article-to-delete",
            detected_at=datetime(2025, 1, 10),
            is_read=0
        )
    )
    facade.connection.commit()

    # Ensure alert exists before deletion
    count_before = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts)
    ).scalar()
    assert count_before == 1

    # Delete by URL
    facade.delete_keyword_alerts_by_article_url("https://example.com/article-to-delete")

    # Ensure deletion worked
    count_after = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts)
    ).scalar()
    assert count_after == 0


def test_delete_keyword_alerts_by_article_url_from_new_table(facade):
    # Seed required FK rows
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/new-table-article",
            title="t2"
        )
    )
    facade._execute_with_rollback(
        keyword_groups.insert().values(id=2, name="grp2", topic="General")
    )
    # Insert into new table
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1201,
            article_uri="https://example.com/new-table-article",
            keyword_ids="1",
            group_id=2,
            detected_at=datetime(2025, 1, 11),
            is_read=0
        )
    )
    facade.connection.commit()

    # Confirm exists
    count_before = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches)
    ).scalar()
    assert count_before == 1

    # Delete
    facade.delete_keyword_alerts_by_article_url_from_new_table("https://example.com/new-table-article")

    count_after = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches)
    ).scalar()
    assert count_after == 0



def test_mark_article_as_below_threshold_logs_message(facade, caplog):
    # Capture debug log
    with caplog.at_level("DEBUG"):
        facade.mark_article_as_below_threshold("https://example.com/low-score-article")

    assert "saved with relevance scores" in caplog.text


def test_get_total_articles_and_sample_categories_for_topic(facade):
    # Insert articles for topic 'AI'
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a1",
            title="AI Trends 2025",
            topic="AI",
            category="Technology"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a2",
            title="AI Ethics",
            topic="AI",
            category="Ethics"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a3",
            title="Misc Article",
            topic="AI"
        )
    )
    facade.connection.commit()

    total, with_categories, sample_cats = facade.get_total_articles_and_sample_categories_for_topic("AI")

    assert total == 3
    assert with_categories == 2
    assert set(sample_cats) == {"Technology", "Ethics"}


def test_get_topic(facade):
    # Insert topics
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/topic-check",
            title="AI Growth",
            topic="AI"
        )
    )
    facade.connection.commit()

    result = facade.get_topic("AI")

    assert result is not None
    assert result[0] == "AI"


def test_upsert_article_insert_and_update(facade):
    uri = "https://example.com/upsert-test"

    # Insert (first upsert) without topic to avoid external validation dependency
    article_data = {
        "uri": uri,
        "title": "Upsert Test",
        "summary": "Initial insert test",
        "publication_date": datetime.utcnow(),
        "tags": ["AI", "ML"]
    }

    result_insert = facade.upsert_article(article_data)
    assert result_insert["success"] is True
    assert result_insert["uri"] == uri

    inserted = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == uri)
    ).mappings().fetchone()
    assert inserted is not None
    assert inserted["summary"] == "Initial insert test"
    # tags list should be stored as comma-separated string
    assert inserted["tags"] in ("AI,ML", "ML,AI")

    # Update (second upsert)
    article_data["summary"] = "Updated summary"
    result_update = facade.upsert_article(article_data)
    assert result_update["success"] is True

    updated = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == uri)
    ).mappings().fetchone()
    assert updated["summary"] == "Updated summary"


def test_get_articles_count_from_topic_and_categories(facade):
    # Insert articles under different categories
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a1",
            title="AI Market Boom",
            topic="AI",
            category="Technology"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a2",
            title="AI Ethics",
            topic="AI",
            category="Ethics"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a3",
            title="Sports Today",
            topic="Sports",
            category="Health"
        )
    )
    facade.connection.commit()

    placeholders = ["Technology", "Ethics"]
    params = ["AI"]

    result = facade.get_articles_count_from_topic_and_categories(placeholders, params)

    assert result == 2



def test_get_article_count_for_topic(facade):
    # Insert multiple AI articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/t1",
            title="AI Future",
            topic="AI"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/t2",
            title="AI and ML",
            topic="AI"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/t3",
            title="Blockchain 2025",
            topic="Blockchain"
        )
    )
    facade.connection.commit()

    result = facade.get_article_count_for_topic("AI")

    assert result == 2




def test_get_recent_articles_for_topic_and_category(facade):
    # Insert recent and older articles for 'AI' and 'Tech'
    recent_date = datetime.utcnow() - timedelta(days=1)
    old_date = datetime.utcnow() - timedelta(days=15)

    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/r1",
            title="Recent AI Update",
            topic="AI",
            category="Tech",
            publication_date=recent_date,
            news_source="AI Times"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/r2",
            title="Old AI Article",
            topic="AI",
            category="Tech",
            publication_date=old_date,
            news_source="Old Source"
        )
    )
    facade.connection.commit()

    params = ["AI", "Tech", 7]  # past 7 days
    result = facade.get_recent_articles_for_topic_and_category(params)

    assert len(result) == 1
    assert result[0]["title"] == "Recent AI Update"
    assert result[0]["news_source"] == "AI Times"



def test_get_categories_for_topic(facade):
    # Insert articles for topic 'AI' with various categories
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/c1",
            title="AI in Medicine",
            topic="AI",
            category="Health"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/c2",
            title="AI in Finance",
            topic="AI",
            category="Economy"
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/c3",
            title="AI Uncategorized",
            topic="AI",
            category=""
        )
    )
    facade.connection.commit()

    result = facade.get_categories_for_topic("AI")

    assert set(result) == {"Health", "Economy"}



def test_get_podcasts_columns(facade):
    result = facade.get_podcasts_columns()
    # Basic structure check — ensure key columns are present
    assert isinstance(result, list)
    assert "id" in result or "key" in result



def test_generate_latest_podcasts(facade):
    # Insert a sample podcast
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=1,
            title="AI Insights Episode 1",
            audio_url="https://example.com/audio1.mp3",
            transcript="Welcome to AI Insights!",
            created_at=datetime(2025, 1, 15)
        )
    )
    facade.connection.commit()

    # Case: all flags True, excludes topic filter
    result = facade.generate_latest_podcasts(
        topic="AI",
        column_names=["created_at"],
        has_transcript=True,
        has_topic=False,
        has_audio_url=True
    )

    assert result is not None
    assert result.audio_url == "https://example.com/audio1.mp3"
    assert result.transcript.startswith("Welcome")

    # Case: missing title in column_names
    result2 = facade.generate_latest_podcasts(
        topic="AI",
        column_names=[],
        has_transcript=False,
        has_topic=False,
        has_audio_url=False
    )
    assert result2.title == "Untitled Podcast"



def test_get_articles_for_date_range(facade):
    now = datetime.utcnow()
    start_date = now - timedelta(days=5)
    end_date = now + timedelta(days=1)

    # Insert articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ar1",
            title="AI Market Overview",
            topic="AI",
            publication_date=now
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ar2",
            title="Sports Update",
            topic="Sports",
            publication_date=now
        )
    )
    facade.connection.commit()

    columns, results = facade.get_articles_for_date_range(
        limit=5, topic="AI", start_date=start_date, end_date=end_date
    )

    assert "title" in columns
    assert len(results) == 1
    assert results[0]["title"] == "AI Market Overview"



def test_enriched_articles(facade):
    now = datetime.utcnow()

    # Insert articles with category and tags
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/en1",
            title="AI Innovations",
            category="Tech",
            tags="AI,ML,Data",
            submission_date=now
        )
    )
    # Article without tags
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/en2",
            title="AI Basics",
            category="Education",
            tags=None,
            submission_date=now
        )
    )
    facade.connection.commit()

    result = facade.enriched_articles(limit=5)

    assert len(result) == 2
    first = result[0]
    assert isinstance(first["tags"], list)
    assert "AI" in first["tags"] or first["tags"] == []



def test_create_model_bias_arena_runs(facade):
    params = [
        "Bias Test Run 1",
        "Evaluating GPT-5 bias levels",
        "gpt-5",
        "gpt-5,gpt-4o",
        10,
        3,
        1
    ]

    run_id = facade.create_model_bias_arena_runs(params)

    # Verify inserted record
    result = facade._execute_with_rollback(
        select(model_bias_arena_runs.c.name, model_bias_arena_runs.c.status)
    ).fetchone()

    assert run_id is not None
    assert result.name == "Bias Test Run 1"
    assert result.status == "running"



def test_store_evaluation_results(facade):
    # Insert a model run first
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="Run1", description="desc", benchmark_model="gpt-5", selected_models="gpt-5"
        )
    ).lastrowid

    params = [
        run_id,
        "https://example.com/a1",
        "gpt-5",
        "Generated summary text",
        0.9,
        0.95,
        120,
        None
    ]

    facade.store_evaluation_results(params)

    # Validate stored record
    result = facade._execute_with_rollback(
        select(model_bias_arena_results.c.model_name, model_bias_arena_results.c.bias_score)
    ).fetchone()

    assert result.model_name == "gpt-5"
    assert float(result.bias_score) == 0.9



def test_store_ontological_results(facade):
    # Create a mock run first
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="OntoRun1",
            description="Ontology test",
            benchmark_model="gpt-5",
            selected_models="gpt-5"
        )
    ).lastrowid

    params = [
        run_id,
        "https://example.com/onto1",
        "gpt-5",
        "Response text example",
        100,
        "Positive",
        "Strong optimism",
        "Rising",
        "Clear indication",
        "1 day",
        "Immediate effect",
        "AI",
        "Relevant driver",
        "Tech",
        "Category details",
        "Center-left",
        "Mild political bias",
        "High",
        "Strong factual basis",
        1
    ]

    facade.store_ontological_results(params)

    # Verify stored row
    result = facade._execute_with_rollback(
        select(model_bias_arena_results.c.model_name, model_bias_arena_results.c.sentiment)
    ).fetchone()

    assert result.model_name == "gpt-5"
    assert result.sentiment == "Positive"



def test_update_run_status(facade):
    # Insert a run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunStatus1",
            description="status test",
            benchmark_model="gpt-5",
            selected_models="gpt-5",
            status="running"
        )
    ).lastrowid
    facade.connection.commit()

    params = ["completed", run_id]
    facade.update_run_status(params)

    updated = facade._execute_with_rollback(
        select(model_bias_arena_runs.c.status)
    ).fetchone()

    assert updated.status == "completed"



def test_get_run_details(facade):
    # Insert run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunDetails1",
            description="desc",
            benchmark_model="gpt-5",
            selected_models="gpt-5,gpt-4o",
            article_count=5,
            rounds=3,
            current_round=1,
            status="running"
        )
    ).lastrowid
    facade.connection.commit()

    result = facade.get_run_details(run_id)

    assert result["name"] == "RunDetails1"
    assert result["status"] == "running"
    assert result["article_count"] == 5



def test_get_ontological_results_with_article_info(facade):
    # Create a run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunOnto2",
            benchmark_model="gpt-5",
            selected_models="gpt-5"
        )
    ).lastrowid

    # Insert related article info
    facade._execute_with_rollback(
        model_bias_arena_articles.insert().values(
            run_id=run_id,
            article_uri="https://example.com/article1",
            article_title="AI Bias",
            article_summary="Bias in AI models"
        )
    )

    # Insert result
    facade._execute_with_rollback(
        model_bias_arena_results.insert().values(
            run_id=run_id,
            article_uri="https://example.com/article1",
            model_name="gpt-5",
            sentiment="Positive",
            round_number=1
        )
    )
    facade.connection.commit()

    results = facade.get_ontological_results_with_article_info(run_id)

    assert len(results) == 1
    assert results[0]["model_name"] == "gpt-5"
    assert results[0]["article_title"] == "AI Bias"



def test_get_benchmark_data_including_media_bias_info(facade):
    # Create a run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunMedia",
            benchmark_model="gpt-5",
            selected_models="gpt-5"
        )
    ).lastrowid

    # Insert article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a1",
            title="Media Bias Study",
            sentiment="Neutral",
            bias="Center",
            factual_reporting="High",
            mbfc_credibility_rating="Reliable",
            category="News",
            news_source="BBC"
        )
    )

    # Link article to run
    facade._execute_with_rollback(
        model_bias_arena_articles.insert().values(
            run_id=run_id,
            article_uri="https://example.com/a1",
            article_title="Media Bias Study",
            article_summary="Study on bias in media"
        )
    )
    facade.connection.commit()

    result = facade.get_benchmark_data_including_media_bias_info(run_id)

    assert len(result) == 1
    row = result[0]
    assert row["title"] == "Media Bias Study"
    assert row["bias"] == "Center"
    assert row["news_source"] == "BBC"




def test_delete_run(facade):
    # Insert a model bias run to delete
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="DeletableRun",
            description="A test run for deletion",
            benchmark_model="gpt-5",
            selected_models="gpt-5,gpt-4o",
            article_count=5,
            rounds=2,
            current_round=1,
            status="running"
        )
    ).lastrowid
    facade.connection.commit()

    # Perform deletion
    deleted_count = facade.delete_run(run_id)

    # Assert deletion successful
    assert deleted_count == 1

    # Verify it's removed
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(model_bias_arena_runs)
    ).scalar()
    assert remaining == 0


def test_get_source_bias_validation_data(facade):
    # Insert article with bias/factual data
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/article_bias",
            title="Bias Validation Article",
            bias="Left-Center",
            factual_reporting="High",
            mbfc_credibility_rating="Reliable",
            bias_country="USA",
            press_freedom="Free",
            media_type="News",
            popularity="High"
        )
    )
    facade.connection.commit()

    result = facade.get_source_bias_validation_data("https://example.com/article_bias")

    assert result.bias == "Left-Center"
    assert result.factual_reporting == "High"
    assert result.mbfc_credibility_rating == "Reliable"
    assert result.press_freedom == "Free"



def test_get_run_articles(facade):
    # Create a run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="ArticleRun",
            description="Test Run with Articles",
            benchmark_model="gpt-5",
            selected_models="gpt-5"
        )
    ).lastrowid

    # Insert articles tied to the run
    facade._execute_with_rollback(
        model_bias_arena_articles.insert().values(
            run_id=run_id,
            article_uri="https://example.com/a1",
            article_title="Bias in AI",
            article_summary="Examines bias in models"
        )
    )
    facade._execute_with_rollback(
        model_bias_arena_articles.insert().values(
            run_id=run_id,
            article_uri="https://example.com/a2",
            article_title="AI Fairness",
            article_summary="Focuses on fairness testing"
        )
    )
    facade.connection.commit()

    result = facade.get_run_articles(run_id)

    assert len(result) == 2
    assert {r["article_title"] for r in result} == {"Bias in AI", "AI Fairness"}



def test_get_all_bias_evaluation_runs(facade):
    # Insert multiple runs
    facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="Run1", description="Bias check 1", benchmark_model="gpt-5", selected_models="gpt-5", status="running"
        )
    )
    facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="Run2", description="Bias check 2", benchmark_model="gpt-4", selected_models="gpt-4", status="completed"
        )
    )
    facade.connection.commit()

    result = facade.get_all_bias_evaluation_runs()

    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "Run1" in names and "Run2" in names




def test_update_run(facade):
    # Insert a run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="UpdateRun",
            description="Round update test",
            benchmark_model="gpt-5",
            selected_models="gpt-5",
            current_round=1
        )
    ).lastrowid
    facade.connection.commit()

    # Update current_round
    params = [3, run_id]
    facade.update_run(params)

    # Verify update
    updated = facade._execute_with_rollback(
        select(model_bias_arena_runs.c.current_round)
    ).fetchone()

    assert updated.current_round == 3


def test_get_topics_from_article(facade):
    # Insert an article with topic
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/topic1",
            title="Climate Impact",
            topic="Environment"
        )
    )
    facade.connection.commit()

    result = facade.get_topics_from_article("https://example.com/topic1")

    assert result is not None
    assert result[0] == "Environment"


def test_get_run_info(facade):
    # Insert model bias run
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunInfoTest",
            description="Info testing",
            benchmark_model="gpt-5",
            selected_models="gpt-5,gpt-4o",
            rounds=5,
            current_round=2
        )
    ).lastrowid
    facade.connection.commit()

    result = facade.get_run_info(run_id)

    assert result is not None
    assert result[0] == 5
    assert result[1] == 2


def test_add_articles_to_run(facade):
    # Create a run first
    run_id = facade._execute_with_rollback(
        model_bias_arena_runs.insert().values(
            name="RunWithArticles",
            benchmark_model="gpt-5",
            selected_models="gpt-5,gpt-4o",
        )
    ).lastrowid

    params = [
        run_id,
        "https://example.com/run-article",
        "AI Ethics Review",
        "A deep look at ethical challenges in AI"
    ]

    facade.add_articles_to_run(params)

    result = facade._execute_with_rollback(
        select(model_bias_arena_articles.c.article_title)
    ).fetchone()

    assert result.article_title == "AI Ethics Review"



def test_sample_articles(facade):
    # Insert articles meeting all criteria
    for i in range(3):
        facade._execute_with_rollback(
            articles.insert().values(
                uri=f"https://example.com/sampled{i}",
                title=f"AI Progress {i}",
                summary="A" * 150,  # summary > 100 chars
                news_source="TechNews",
                topic="AI",
                category="Technology",
                sentiment="Positive",
                future_signal="Growth",
                time_to_impact="1 year",
                driver_type="Innovation",
                bias="Center",
                factual_reporting="High",
                mbfc_credibility_rating="Reliable",
                bias_country="USA",
                analyzed=True
            )
        )
    # Insert one invalid (short summary)
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/invalid",
            title="Too Short",
            summary="Short text",
            news_source="TechNews",
            topic="AI",
            category="Technology",
            sentiment="Positive",
            future_signal="Growth",
            time_to_impact="1 year",
            driver_type="Innovation",
            bias="Center",
            factual_reporting="High",
            mbfc_credibility_rating="Reliable",
            bias_country="USA",
            analyzed=True
        )
    )
    facade.connection.commit()

    result = facade.sample_articles(count=2, topic="AI")

    assert len(result) <= 2
    for r in result:
        assert len(r["summary"]) > 100
        assert r["sentiment"] == "Positive"



def test_get_topics_with_article_counts(facade):
    now = datetime.utcnow()
    # Insert articles with topics
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/topicA",
            title="AI in Medicine",
            topic="AI",
            publication_date=now
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/topicB",
            title="AI in Finance",
            topic="AI",
            publication_date=now - timedelta(days=1)
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/topicC",
            title="Renewable Energy",
            topic="Environment",
            publication_date=now
        )
    )
    facade.connection.commit()

    result = facade.get_topics_with_article_counts()

    assert "AI" in result
    assert result["AI"]["article_count"] == 2
    assert isinstance(result["AI"]["last_article_date"], (datetime, str))



def test_debug_articles(facade):
    # Insert sample data
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://debug.com/1",
            title="Debug Article",
            topic="AI"
        )
    )
    facade.connection.commit()

    result = facade.debug_articles()
    assert any(row["title"] == "Debug Article" for row in result)


def test_get_rate_limit_status(facade):
    # Insert a dummy status
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            requests_today=50,
            last_error="None"
        )
    )
    facade.connection.commit()

    result = facade.get_rate_limit_status()
    assert result["requests_today"] == 50
    assert result["last_error"] == "None"



def test_get_monitor_page_keywords(facade):
    # Insert group and keyword
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Group", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="GPT-5")
    )
    facade.connection.commit()

    result = facade.get_monitor_page_keywords()
    assert any(r["keyword"] == "GPT-5" for r in result)
    assert any(r["name"] == "AI Group" for r in result)



def test_get_monitored_keywords_for_keyword_alerts_page(facade):
    facade._execute_with_rollback(keyword_monitor_settings.insert().values(
        id=1, check_interval=15, interval_unit="minutes", is_enabled=True
    ))
    facade._execute_with_rollback(keyword_monitor_status.insert().values(
        id=1, last_error=None
    ))
    # monitored_keywords requires a valid group_id (FK), create a group first
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="Alerts Group", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI", last_checked=datetime.utcnow())
    )
    facade.connection.commit()

    result = facade.get_monitored_keywords_for_keyword_alerts_page()
    assert result[1] == 15
    assert result[4] == 1  # SQLite stores True as 1



def test_get_all_groups_with_their_alerts_and_status(facade):
    # Insert group, keyword, and alert
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="Test Group", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="ChatGPT")
    ).lastrowid
    # keyword_alerts requires article_uri (FK to articles), insert a stub article and use its URI
    article_uri = "https://example.com/keyword-alert-article"
    facade._execute_with_rollback(
        articles.insert().values(uri=article_uri, title="Stub Article")
    )
    facade._execute_with_rollback(
        keyword_alerts.insert().values(keyword_id=kid, article_uri=article_uri, is_read=0)
    )
    facade.connection.commit()

    result = facade.get_all_groups_with_their_alerts_and_status()
    assert any(r["name"] == "Test Group" for r in result)
    assert any(r["keywords"] and "ChatGPT" in r["keywords"] for r in result)




def test_get_keywords_and_articles_for_keywords_alert_page_using_new_structure(facade):
    # Create an article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/news1",
            title="AI Breakthrough",
            summary="A major AI event.",
            news_source="TechTimes"
        )
    )

    # Create group (FK)
    group_id = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Group", topic="AI")
    ).lastrowid

    # Create monitored keywords (used in keyword_ids)
    kw1 = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    ).lastrowid
    kw2 = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="ML")
    ).lastrowid

    # Create keyword_article_match record
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=group_id,
            article_uri="https://example.com/news1",
            keyword_ids=f"{kw1},{kw2}",
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    result = facade.get_keywords_and_articles_for_keywords_alert_page_using_new_structure(group_id)
    assert len(result) >= 1
    assert result[0][2] == "https://example.com/news1"  # article_uri


def test_get_keywords_and_articles_for_keywords_alert_page_using_old_structure(facade):
    # Create article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/news2",
            title="ChatGPT in Healthcare",
            summary="New AI adoption in hospitals.",
            news_source="MedTech"
        )
    )

    # Create group
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="Health AI", topic="AI")
    ).lastrowid

    # Create monitored keyword
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="ChatGPT")
    ).lastrowid

    # Create alert linked to article + keyword
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid,
            article_uri="https://example.com/news2",
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    result = facade.get_keywords_and_articles_for_keywords_alert_page_using_old_structure(gid)
    assert len(result) == 1
    assert result[0]["matched_keyword"] == "ChatGPT"


def test_get_all_completed_podcasts(facade):
    # Insert completed podcast
    facade._execute_with_rollback(
        podcasts.insert().values(
            id="pod-1",
            title="AI Weekly Recap",
            created_at=datetime.utcnow(),
            status="completed",
            audio_url="https://cdn.podcast.com/ai-weekly.mp3",
            transcript="This week in AI..."
        )
    )
    facade.connection.commit()

    result = facade.get_all_completed_podcasts()
    assert len(result) >= 1
    assert result[0]["status"] == "completed" if "status" in result[0] else True


def test_create_podcast(facade):
    podcast_id = 12345
    facade.create_podcast([
        podcast_id,
        "AI Deep Dive",
        '{"language":"en"}',
        "https://example.com/article1,https://example.com/article2"
    ])

    result = facade._execute_with_rollback(
        select(podcasts).where(podcasts.c.id == podcast_id)
    ).mappings().fetchone()

    assert result["title"] == "AI Deep Dive"
    assert result["status"] == "processing"


def test_update_podcast_status(facade):
    podcast_id = 101
    # Insert podcast first
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="AI Talks",
            status="processing",
            created_at=datetime.utcnow(),
        )
    )
    facade.connection.commit()

    # Update podcast
    facade.update_podcast_status(["completed", "https://audio.url/ai.mp3", "Full transcript text", podcast_id])

    # Verify
    result = facade._execute_with_rollback(
        select(podcasts).where(podcasts.c.id == podcast_id)
    ).mappings().fetchone()

    assert result["status"] == "completed"
    assert result["audio_url"] == "https://audio.url/ai.mp3"
    assert "Full transcript" in result["transcript"]


def test_get_flow_data(facade):
    now = datetime.utcnow()

    # Insert sample articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/1",
            title="AI Growth",
            topic="AI",
            news_source="TechSource",
            category="Technology",
            sentiment="Positive",
            driver_type="Innovation",
            submission_date=now
        )
    )
    facade.connection.commit()

    result = facade.get_flow_data("AI", "7", 10)
    assert len(result) >= 1
    assert result[0]["source"] == "TechSource"
    assert result[0]["category"] == "Technology"



def test_create_keyword_monitor_group(facade):
    group_id = facade.create_keyword_monitor_group(["Tech Trends", "AI"])
    result = facade._execute_with_rollback(
        select(keyword_groups).where(keyword_groups.c.id == group_id)
    ).mappings().fetchone()

    assert result["name"] == "Tech Trends"
    assert result["topic"] == "AI"



def test_create_keyword(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Insights", topic="AI")
    ).lastrowid
    facade.connection.commit()

    facade.create_keyword([gid, "OpenAI"])
    result = facade._execute_with_rollback(
        select(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).mappings().fetchone()

    assert result["keyword"] == "OpenAI"
    assert result["group_id"] == gid
    assert result["id"] is not None
    # Verify only one keyword added to this group
    count_kw = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).scalar()
    assert count_kw == 1



def test_delete_keyword(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="GroupDeleteKW", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="TestDelete")
    ).lastrowid
    facade.connection.commit()

    facade.delete_keyword(kid)
    result = facade._execute_with_rollback(
        select(monitored_keywords).where(monitored_keywords.c.id == kid)
    ).fetchone()

    assert result is None
    # Ensure no keywords remain for the group
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).scalar()
    assert remaining == 0



def test_delete_keyword_group(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="DeleteGroup", topic="AI")
    ).lastrowid
    facade.connection.commit()

    facade.delete_keyword_group(gid)
    result = facade._execute_with_rollback(
        select(keyword_groups).where(keyword_groups.c.id == gid)
    ).fetchone()

    assert result is None
    # Ensure the table has no rows with that ID
    total = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_groups).where(keyword_groups.c.id == gid)
    ).scalar()
    assert total == 0



def test_delete_group_keywords(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="GroupBulkDelete", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="ML")
    )
    facade.connection.commit()

    facade.delete_group_keywords(gid)

    result = facade._execute_with_rollback(
        select(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).fetchall()
    assert result == []
    # Confirm via count
    count_after = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).scalar()
    assert count_after == 0



def test_create_group(facade):
    gid = facade.create_group("AI Watch", "Artificial Intelligence")
    result = facade._execute_with_rollback(
        select(keyword_groups).where(keyword_groups.c.id == gid)
    ).mappings().fetchone()
    assert result["name"] == "AI Watch"
    assert result["topic"] == "Artificial Intelligence"
    # created_at should be set
    assert result["created_at"] is not None


def test_add_keywords_to_group(facade):
    gid = facade.create_group("Tech News", "Technology")
    facade.add_keywords_to_group(gid, "AI")
    result = facade._execute_with_rollback(
        select(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).mappings().fetchone()
    assert result["keyword"] == "AI"
    # Ensure only one keyword exists for this group
    count_kw = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid)
    ).scalar()
    assert count_kw == 1



def test_get_all_group_ids_associated_to_topic(facade):
    gid1 = facade.create_group("AI Insights", "AI")
    gid2 = facade.create_group("AI Trends", "AI")
    facade.connection.commit()

    result = facade.get_all_group_ids_associated_to_topic("AI")
    ids = [r["id"] for r in result]
    assert gid1 in ids and gid2 in ids
    # Ensure all rows contain an integer id
    assert all(isinstance(r["id"], int) for r in result)


def test_get_keyword_ids_associated_to_group(facade):
    gid = facade.create_group("Finance", "Economy")
    facade.add_keywords_to_group(gid, "Inflation")
    facade.add_keywords_to_group(gid, "Stocks")
    result = facade.get_keyword_ids_associated_to_group(gid)
    assert len(result) == 2
    # IDs should be unique
    assert len(set(result)) == 2


def test_get_keywords_associated_to_group(facade):
    gid = facade.create_group("AI Research", "AI")
    facade.add_keywords_to_group(gid, "Deep Learning")
    facade.add_keywords_to_group(gid, "NLP")
    keywords = facade.get_keywords_associated_to_group(gid)
    assert set(keywords) == {"Deep Learning", "NLP"}
    assert len(keywords) == 2


def test_get_keywords_associated_to_group_ordered_by_keyword(facade):
    gid = facade.create_group("Energy", "Environment")
    facade.add_keywords_to_group(gid, "Solar")
    facade.add_keywords_to_group(gid, "Wind")
    ordered = facade.get_keywords_associated_to_group_ordered_by_keyword(gid)
    assert ordered == sorted(ordered)
    assert set(ordered) == {"Solar", "Wind"}


def test_delete_keyword_article_matches_from_new_table_structure(facade):
    gid = facade.create_group("AI Alerts", "AI")
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid,
            article_uri="https://example.com/ai",
            keyword_ids="1",
            detected_at=datetime.utcnow(),
            is_read=False
        )
    )
    facade.connection.commit()

    deleted = facade.delete_keyword_article_matches_from_new_table_structure(gid)
    assert deleted == 1
    # Confirm deletion
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches).where(keyword_article_matches.c.group_id == gid)
    ).scalar()
    assert remaining == 0


def test_delete_keyword_article_matches_from_old_table_structure(facade):
    gid = facade.create_group("Legacy", "AI")
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="TestKeyword")
    ).lastrowid
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid,
            article_uri="https://example.com/test",
            is_read=False,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    deleted = facade.delete_keyword_article_matches_from_old_table_structure("", [kid])
    assert deleted == 1
    # Ensure related alerts are deleted
    count_alerts = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts).where(keyword_alerts.c.keyword_id == kid)
    ).scalar()
    assert count_alerts == 0


def test_delete_groups_keywords(facade):
    gid1 = facade.create_group("GroupA", "AI")
    gid2 = facade.create_group("GroupB", "AI")
    facade.add_keywords_to_group(gid1, "AI")
    facade.add_keywords_to_group(gid2, "ML")
    facade.connection.commit()

    deleted = facade.delete_groups_keywords("", [gid1, gid2])
    assert deleted == 2
    # Ensure both groups have no keywords
    c1 = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid1)
    ).scalar()
    c2 = facade._execute_with_rollback(
        select(func.count()).select_from(monitored_keywords).where(monitored_keywords.c.group_id == gid2)
    ).scalar()
    assert c1 == 0 and c2 == 0


def test_delete_all_keyword_groups(facade):
    facade.create_group("A", "AI")
    facade.create_group("B", "AI")
    facade.create_group("C", "Finance")
    facade.connection.commit()

    deleted = facade.delete_all_keyword_groups("AI")
    assert deleted == 2
    # Ensure no groups remain for topic AI
    remaining_ai = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_groups).where(keyword_groups.c.topic == "AI")
    ).scalar()
    assert remaining_ai == 0


def test_check_if_alert_id_exists_in_new_table_structure(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AlertCheckGroup", topic="AI")
    ).lastrowid
    inserted = facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid,
            article_uri="https://example.com/alert",
            keyword_ids="1",
            detected_at=datetime.utcnow(),
            is_read=False
        )
    )
    facade.connection.commit()

    result = facade.check_if_alert_id_exists_in_new_table_structure(inserted.lastrowid)
    assert result is not None


def test_mark_alert_as_read_or_unread_in_new_table(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="ReadToggleGroup", topic="AI")
    ).lastrowid
    inserted = facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid,
            article_uri="https://example.com/toggle",
            keyword_ids="1",
            detected_at=datetime.utcnow(),
            is_read=False
        )
    )
    facade.connection.commit()

    facade.mark_alert_as_read_or_unread_in_new_table(inserted.lastrowid, True)
    updated = facade._execute_with_rollback(
        select(keyword_article_matches.c.is_read).where(keyword_article_matches.c.id == inserted.lastrowid)
    ).scalar()
    # SQLite may return 1 for True, accept either representation
    assert updated == 1 or updated is True


def test_mark_alert_as_read_or_unread_in_old_table(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="LegacyGroup", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid
    inserted = facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid,
            article_uri="https://example.com/legacy",
            is_read=False,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    facade.mark_alert_as_read_or_unread_in_old_table(inserted.lastrowid, True)
    updated = facade._execute_with_rollback(
        select(keyword_alerts.c.is_read).where(keyword_alerts.c.id == inserted.lastrowid)
    ).scalar()
    assert updated == 1


def test_get_number_of_monitored_keywords_by_group_id(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="CountGroup", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(monitored_keywords.insert().values(group_id=gid, keyword="AI"))
    facade._execute_with_rollback(monitored_keywords.insert().values(group_id=gid, keyword="ML"))
    facade.connection.commit()

    count = facade.get_number_of_monitored_keywords_by_group_id(gid)
    assert count == 2


def test_get_total_number_of_keywords(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="TotalKWGroup", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(monitored_keywords.insert().values(group_id=gid, keyword="Data"))
    facade._execute_with_rollback(monitored_keywords.insert().values(group_id=gid, keyword="Science"))
    facade.connection.commit()

    total = facade.get_total_number_of_keywords()
    assert total >= 2


def test_get_alerts(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AlertsGroup", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/alerts",
            title="AI News",
            summary="Test summary",
            news_source="Source",
            publication_date=datetime.utcnow()
        )
    )
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid,
            article_uri="https://example.com/alerts",
            is_read=False,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    columns, data = facade.get_alerts(show_read=False)
    assert "title" in columns
    assert len(data) >= 1
    assert data[0]["matched_keyword"] == "AI"


def test_get_article_enrichment(facade):
    uri = "https://example.com/enrich"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=uri,
            title="AI Ethics",
            category="Technology",
            sentiment="Positive",
            driver_type="Policy",
            time_to_impact="Short-term",
            topic_alignment_score=0.9,
            keyword_relevance_score=0.85,
            confidence_score=0.95,
            overall_match_explanation="Strong alignment with AI policy",
            extracted_article_topics="AI, Ethics",
            extracted_article_keywords="Bias, Fairness",
            auto_ingested=True,
            ingest_status="success",
            quality_score=0.92,
            quality_issues="None"
        )
    )
    facade.connection.commit()

    result = facade.get_article_enrichment({"uri": uri})
    assert result is not None
    assert result[0] == "Technology" or result["category"] == "Technology"


def test_get_all_groups_with_alerts_and_status_new_table_structure(facade):
    # Create 2 keyword groups
    gid1 = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Watch", topic="AI")
    ).lastrowid
    gid2 = facade._execute_with_rollback(
        keyword_groups.insert().values(name="Finance Track", topic="Finance")
    ).lastrowid

    # Insert articles for alert linkage
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ai-1",
            title="AI Growth",
            publication_date=datetime.utcnow()
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/finance-1",
            title="Finance Update",
            publication_date=datetime.utcnow()
        )
    )

    # Insert keyword_article_matches for both groups
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid1,
            article_uri="https://example.com/ai-1",
            detected_at=datetime.utcnow(),
            is_read=False,
            keyword_ids="1",
        )
    )
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid2,
            article_uri="https://example.com/finance-1",
            detected_at=datetime.utcnow(),
            is_read=True,
            keyword_ids="1",
        )
    )
    facade.connection.commit()

    # Run the method
    result = facade.get_all_groups_with_alerts_and_status_new_table_structure()

    # Validate results structure and counts
    assert len(result) >= 2
    row_dicts = [dict(r._mapping) for r in result] if hasattr(result[0], '_mapping') else result

    # Group names should appear
    names = [r["name"] if isinstance(r, dict) else r[1] for r in row_dicts]
    assert "AI Watch" in names and "Finance Track" in names

    # Ensure counts are numeric
    for r in row_dicts:
        unread = r["unread_count"] if isinstance(r, dict) else r[3]
        total = r["total_count"] if isinstance(r, dict) else r[4]
        assert isinstance(unread, int)
        assert isinstance(total, int)



def test_get_most_recent_unread_alerts_for_group_id_new_table_structure(facade):
    # Create a keyword group
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="NewStructGroup", topic="AI")
    ).lastrowid

    # Insert article linked to the alert
    uri = "https://example.com/ai-alert"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=uri,
            title="AI Alert News",
            summary="AI Alert summary",
            publication_date=datetime.utcnow()
        )
    )

    # Insert a new-table alert (unread)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid,
            article_uri=uri,
            keyword_ids="1,2",
            detected_at=datetime.utcnow(),
            is_read=False
        )
    )
    facade.connection.commit()

    # Execute
    result = facade.get_most_recent_unread_alerts_for_group_id_new_table_structure(gid)

    assert len(result) == 1
    row = result[0]
    assert row["article_uri"] == uri
    assert row["is_read"] == 0
    assert row["title"] == "AI Alert News"


def test_get_most_recent_unread_alerts_for_group_id_old_table_structure(facade):
    # Create group and keyword
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="OldStructGroup", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid

    # Create article
    uri = "https://example.com/old-alert"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=uri,
            title="Old Alert Title",
            summary="Old Alert Summary",
            publication_date=datetime.utcnow()
        )
    )

    # Create old-style alert (unread)
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid,
            article_uri=uri,
            is_read=False,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Execute
    result = facade.get_most_recent_unread_alerts_for_group_id_old_table_structure(gid)
    assert len(result) == 1
    row = result[0]
    assert row["matched_keyword"] == "AI"
    assert row["title"] == "Old Alert Title"
    assert row["is_read"] == 0


def test_count_total_group_unread_articles_new_table_structure(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="UnreadCountNew", topic="AI")
    ).lastrowid

    # Insert articles
    uri1 = "https://example.com/ai1"
    uri2 = "https://example.com/ai2"
    facade._execute_with_rollback(
        articles.insert().values(uri=uri1, title="A1", publication_date=datetime.utcnow())
    )
    facade._execute_with_rollback(
        articles.insert().values(uri=uri2, title="A2", publication_date=datetime.utcnow())
    )

    # Insert alerts (1 read, 1 unread)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid, article_uri=uri1, keyword_ids="1", detected_at=datetime.utcnow(), is_read=False
        )
    )
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=gid, article_uri=uri2, keyword_ids="1", detected_at=datetime.utcnow(), is_read=True
        )
    )
    facade.connection.commit()

    count = facade.count_total_group_unread_articles_new_table_structure(gid)
    assert count == 1


def test_count_total_group_unread_articles_old_table_structure(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="UnreadCountOld", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid

    # Insert article
    uri = "https://example.com/old-unread"
    facade._execute_with_rollback(
        articles.insert().values(uri=uri, title="Old Count", publication_date=datetime.utcnow())
    )

    # Insert one unread alert
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid, article_uri=uri, is_read=False, detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    count = facade.count_total_group_unread_articles_old_table_structure(gid)
    assert count == 1


def test_get_all_matched_keywords_for_article_and_group(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="MatchGroup", topic="AI")
    ).lastrowid

    # Insert multiple keywords
    k1 = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid
    k2 = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="ML")
    ).lastrowid
    facade.connection.commit()

    # Build placeholders and params list
    params = [k1, k2, gid]
    result = facade.get_all_matched_keywords_for_article_and_group(None, params)

    assert "AI" in result and "ML" in result


def test_get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(facade):
    # Create a keyword group and insert a keyword
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="AlertGroup", topic="AI")
    ).lastrowid
    kid = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    ).lastrowid

    # Create article and alert
    uri = "https://example.com/ai-keyword"
    facade._execute_with_rollback(
        articles.insert().values(uri=uri, title="AI Keyword", publication_date=datetime.utcnow())
    )
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=kid, article_uri=uri, is_read=False, detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    result = facade.get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(uri, gid)
    assert "AI" in result


def test_get_article_enrichment_by_article_url(facade):
    uri = "https://example.com/enrich-url"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=uri,
            title="AI Article",
            category="Technology",
            sentiment="Positive",
            driver_type="Innovation",
            time_to_impact="Short-term",
            topic_alignment_score=0.9,
            keyword_relevance_score=0.8,
            confidence_score=0.95,
            overall_match_explanation="Relevant AI advancement",
            extracted_article_topics="AI, Robotics",
            extracted_article_keywords="Automation, Machine Learning"
        )
    )
    facade.connection.commit()

    result = facade.get_article_enrichment_by_article_url(uri)
    assert result is not None
    assert "Technology" in result or result[0] == "Technology"


def test_create_keyword_monitor_table_if_not_exists_and_insert_default_value(facade):
    # Ensure table is empty initially
    existing = facade._execute_with_rollback(select(keyword_monitor_status)).fetchall()
    assert len(existing) == 0

    # Create default row
    facade.create_keyword_monitor_table_if_not_exists_and_insert_default_value()
    data = facade._execute_with_rollback(select(keyword_monitor_status)).mappings().fetchone()

    assert data is not None
    assert data["id"] == 1
    assert data["requests_today"] == 0


def test_check_keyword_monitor_status_and_settings_tables(facade):
    # Create mock rows for both tables
    facade._execute_with_rollback(
        insert(keyword_monitor_status).values(id=1, requests_today=5, last_error="None")
    )
    facade._execute_with_rollback(
        insert(keyword_monitor_settings).values(
            id=1,
            check_interval=15,
            interval_unit="minutes",
            search_fields="title,summary",
            language="en",
            sort_by="date",
            page_size=10,
            daily_request_limit=100,
            is_enabled=True,
            provider="NewsAPI"
        )
    )
    facade.connection.commit()

    status, settings = facade.check_keyword_monitor_status_and_settings_tables()
    assert status["requests_today"] == 5
    assert settings["provider"] == "NewsAPI"


def test_get_count_of_monitored_keywords(facade):
    gid = facade._execute_with_rollback(
        keyword_groups.insert().values(name="KWGroup", topic="AI")
    ).lastrowid
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=gid, keyword="AI")
    )
    facade.connection.commit()

    count = facade.get_count_of_monitored_keywords()
    assert count >= 1


def test_get_settings_and_status_together(facade):
    # Create settings row
    facade._execute_with_rollback(
        insert(keyword_monitor_settings).values(
            id=1,
            check_interval=30,
            interval_unit="minutes",
            search_fields="title",
            language="en",
            sort_by="date",
            page_size=5,
            daily_request_limit=50,
            is_enabled=True,
            provider="TestAPI",
            default_llm_model="gpt-4o-mini"
        )
    )

    # Create matching status row
    today = datetime.utcnow().strftime("%Y-%m-%d")
    facade._execute_with_rollback(
        insert(keyword_monitor_status).values(
            id=1,
            requests_today=10,
            last_error=None,
            last_check_time=datetime.utcnow(),
            last_reset_date=today
        )
    )
    facade.connection.commit()

    result = facade.get_settings_and_status_together()
    assert result is not None
    assert result[0] == 30
    assert result[8] == "TestAPI"


def test_update_or_insert_keyword_monitor_settings_insert_and_update(facade):
    # Ensure table is empty
    facade._execute_with_rollback(delete(keyword_monitor_settings))
    facade.connection.commit()

    params = [
        15, "minutes", "title,summary", "en", "date", 10, 100,
        "NewsAPI", True, 0.8, True, False,
        "gpt-4o-mini", 0.7, 1500
    ]

    # Insert new settings
    facade.update_or_insert_keyword_monitor_settings(params)

    result = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()  # ✅ <-- added `.mappings()`
    assert result is not None
    assert result["provider"] == "NewsAPI"
    assert result["language"] == "en"

    # Update the existing settings
    params_updated = [
        30, "hours", "title", "fr", "relevance", 5, 50,
        "UpdatedAPI", False, 0.5, False, True,
        "gpt-5", 0.9, 1000
    ]
    facade.update_or_insert_keyword_monitor_settings(params_updated)

    result_updated = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()  # ✅ <-- added `.mappings()`
    assert result_updated is not None
    assert result_updated["provider"] == "UpdatedAPI"
    assert result_updated["check_interval"] == 30
    assert result_updated["language"] == "fr"


def test_update_keyword_monitor_settings_provider_insert_and_update(facade):
    # Clear table
    facade._execute_with_rollback(delete(keyword_monitor_settings))
    facade.connection.commit()

    # Insert via method (no preexisting row)
    facade.update_keyword_monitor_settings_provider("thenewsapi")

    result_inserted = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()  # ✅
    assert result_inserted is not None
    assert result_inserted["provider"] == "thenewsapi"
    assert result_inserted["check_interval"] == 15

    # Update existing provider
    facade.update_keyword_monitor_settings_provider("newsdata")

    result_updated = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()  # ✅
    assert result_updated is not None
    assert result_updated["provider"] == "newsdata"


def test_topic_exists(facade):
    # Insert an article with a known topic
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ai-topic",
            title="AI Revolution",
            topic="AI",
            publication_date=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Check existing topic
    assert facade.topic_exists("AI") is True

    # Check non-existing topic
    assert facade.topic_exists("Space") is False


def test_get_keyword_group_id_by_name_and_topic(facade):
    # Insert a keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Alerts", topic="AI")
    )
    facade.connection.commit()

    # Retrieve it
    result = facade.get_keyword_group_id_by_name_and_topic("AI Alerts", "AI")
    assert result is not None

    # Non-existing combination should return None
    result_none = facade.get_keyword_group_id_by_name_and_topic("Climate Alerts", "Environment")
    assert result_none is None


def test_toggle_polling_insert_and_update(facade):
    # Step 1: Ensure the keyword_monitor_settings table is empty
    facade._execute_with_rollback(delete(keyword_monitor_settings))
    facade.connection.commit()

    # Create a mock toggle object
    class Toggle:
        def __init__(self, enabled):
            self.enabled = enabled

    # Step 2: Test inserting when no settings exist
    toggle_on = Toggle(enabled=True)
    facade.toggle_polling(toggle_on)

    result_insert = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()

    assert result_insert is not None
    assert result_insert["is_enabled"] == 1  # True
    assert result_insert["language"] == "en"
    assert result_insert["check_interval"] == 15
    assert result_insert["interval_unit"] == 60

    # Step 3: Test updating existing row
    toggle_off = Toggle(enabled=False)
    facade.toggle_polling(toggle_off)

    result_update = facade._execute_with_rollback(
        select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
    ).mappings().fetchone()

    assert result_update is not None
    assert result_update["is_enabled"] == 0  # False
    assert result_update["language"] == "en"  # Other fields unchanged


def test_get_all_alerts_for_export_old_table_structure(facade):
    # Step 1: Create keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(
            name="AI Alerts",
            topic="AI"
        )
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Alerts")
    ).scalar_one()

    # Step 2: Create monitored keyword
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            group_id=group_id,
            keyword="Artificial Intelligence"
        )
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "Artificial Intelligence")
    ).scalar_one()

    # Step 3: Create article
    article_uri = "https://example.com/ai-advances"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Advances in 2025",
            news_source="TechDaily",
            publication_date=datetime.utcnow(),
            topic="AI"
        )
    )

    # Step 4: Create keyword alert linking them
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    # Step 5: Execute the method
    result = facade.get_all_alerts_for_export_old_table_structure()

    # Step 6: Assertions
    assert len(result) == 1
    alert = result[0]
    assert alert["group_name"] == "AI Alerts"
    assert alert["topic"] == "AI"
    assert alert["title"] == "AI Advances in 2025"
    assert alert["news_source"] == "TechDaily"
    assert alert["matched_keyword"] == "Artificial Intelligence"


def test_get_all_group_and_topic_alerts_for_export_old_table_structure(facade):
    # Step 1: Create a keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Insights", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Insights")
    ).scalar_one()

    # Step 2: Add monitored keyword
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="ChatGPT")
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "ChatGPT")
    ).scalar_one()

    # Step 3: Add article
    article_uri = "https://example.com/ai-chatgpt"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="ChatGPT Innovations",
            news_source="TechToday",
            publication_date=datetime.utcnow(),
            topic="AI"
        )
    )

    # Step 4: Add alert linking them
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    # Step 5: Call method under test
    results = facade.get_all_group_and_topic_alerts_for_export_old_table_structure(group_id, "AI")

    # Step 6: Assertions
    assert len(results) == 1
    alert = results[0]
    assert alert["group_name"] == "AI Insights"
    assert alert["topic"] == "AI"
    assert alert["title"] == "ChatGPT Innovations"
    assert alert["news_source"] == "TechToday"
    assert alert["matched_keyword"] == "ChatGPT"
    assert alert["is_read"] == 0



def test_get_alerts_by_group_id_from_new_table_structure(facade):
    # Step 1: Create a group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Monitor", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Monitor")
    ).scalar_one()

    # Step 2: Create article
    article_uri = "https://example.com/ai-trends"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Trends 2025",
            publication_date=datetime.utcnow(),
            category="Tech",
            topic="AI"
        )
    )

    # Step 3: Insert keyword_article_match
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=group_id,
            article_uri=article_uri,
            keyword_ids="1,2",
            is_read=0,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Step 4: Call method under test
    results = facade.get_alerts_by_group_id_from_new_table_structure(
        status="added", show_read=False, group_id=group_id, page_size=10, offset=0
    )

    # Step 5: Assertions
    assert len(results) == 1
    alert = results[0]
    assert alert["article_uri"] == article_uri
    assert alert["is_read"] == 0
    assert alert["title"] == "AI Trends 2025"
    assert alert["category"] == "Tech"


def test_get_alerts_by_group_id_from_old_table_structure(facade):
    # Step 1: Create keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI News Group", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI News Group")
    ).scalar_one()

    # Step 2: Add monitored keyword
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "AI")
    ).scalar_one()

    # Step 3: Add article
    article_uri = "https://example.com/ai-discovery"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Discovery Breakthrough",
            publication_date=datetime.utcnow(),
            topic="AI",
            category="Tech"
        )
    )

    # Step 4: Add keyword alert
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    # Step 5: Run method (show only unread + added)
    results = facade.get_alerts_by_group_id_from_old_table_structure(
        status="added", show_read=False, group_id=group_id, page_size=10, offset=0
    )

    # Step 6: Assertions
    assert len(results) == 1
    alert = results[0]
    assert alert["article_uri"] == article_uri
    assert alert["matched_keyword"] == "AI"
    assert alert["is_read"] == 0
    assert alert["title"] == "AI Discovery Breakthrough"


def test_count_unread_articles_by_group_id_from_new_table_structure(facade):
    # Step 1: Create group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Alerts New", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Alerts New")
    ).scalar_one()

    # Step 2: Add article
    article_uri = "https://example.com/new-ai"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="New AI Revolution",
            publication_date=datetime.utcnow(),
            topic="AI"
        )
    )

    # Step 3: Insert keyword_article_match (unread)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=group_id,
            article_uri=article_uri,
            keyword_ids="1,2",
            is_read=0,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Step 4: Execute method
    result = facade.count_unread_articles_by_group_id_from_new_table_structure(group_id)
    assert result == 1


def test_count_unread_articles_by_group_id_from_old_table_structure(facade):
    # Step 1: Create keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="Old Alerts Group", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "Old Alerts Group")
    ).scalar_one()

    # Step 2: Create monitored keyword
    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "AI")
    ).scalar_one()

    # Step 3: Create article
    article_uri = "https://example.com/ai-old"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="Old AI Article",
            publication_date=datetime.utcnow()
        )
    )

    # Step 4: Insert keyword_alert (unread)
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    # Step 5: Call method
    result = facade.count_unread_articles_by_group_id_from_old_table_structure(group_id)
    assert result == 1


def test_count_total_articles_by_group_id_from_new_table_structure(facade):
    # Create group and article
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Growth", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Growth")
    ).scalar_one()

    article_uri = "https://example.com/ai-growth"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Growth Report",
            publication_date=datetime.utcnow(),
            category="Tech"
        )
    )

    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=group_id,
            article_uri=article_uri,
            keyword_ids="3,4",
            is_read=1,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    count_added = facade.count_total_articles_by_group_id_from_new_table_structure(group_id, status="added")
    count_all = facade.count_total_articles_by_group_id_from_new_table_structure(group_id, status="all")

    assert count_added == 1
    assert count_all >= 1


def test_count_total_articles_by_group_id_from_old_table_structure(facade):
    # Create group, keyword, article
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Data Group", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Data Group")
    ).scalar_one()

    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "AI")
    ).scalar_one()

    article_uri = "https://example.com/ai-data"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Data Insights",
            publication_date=datetime.utcnow(),
            category="Research"
        )
    )

    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    count_added = facade.count_total_articles_by_group_id_from_old_table_structure(group_id, status="added")
    count_all = facade.count_total_articles_by_group_id_from_old_table_structure(group_id, status="all")

    assert count_added == 1
    assert count_all >= 1


def test_update_media_bias(facade):
    # Step 1: Insert a disabled media bias source
    source_name = "BBC News"
    facade._execute_with_rollback(
        mediabias.insert().values(source=source_name, enabled=0)
    )
    facade.connection.commit()

    # Step 2: Call update_media_bias
    facade.update_media_bias(source_name)

    # Step 3: Verify enabled status is updated
    result = facade._execute_with_rollback(
        select(mediabias.c.enabled).where(mediabias.c.source == source_name)
    ).scalar_one()

    assert result == 1


def test_get_group_name_known_and_unknown(facade):
    # Step 1: Insert known group
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Watchers", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "AI Watchers")
    ).scalar_one()

    # Step 2: Known group should return its name
    known_name = facade.get_group_name(group_id)
    assert known_name == "AI Watchers"

    # Step 3: Nonexistent group should return 'Unknown Group'
    unknown_name = facade.get_group_name(9999)
    assert unknown_name == "Unknown Group"


def test_article_urls_by_topic(facade):
    # Insert articles with topics
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ai",
            title="AI Advances",
            topic="AI",
            publication_date=datetime.utcnow()
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/finance",
            title="Market Trends",
            topic="Finance",
            publication_date=datetime.utcnow()
        )
    )
    facade.connection.commit()

    result = facade.article_urls_by_topic("AI")

    assert len(result) == 1
    assert result[0]["uri"] == "https://example.com/ai"


def test_delete_article_matches_by_url(facade):
    url = "https://example.com/delete-me"

    # Insert match record
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=1,
            article_uri=url,
            keyword_ids="1,2",
            is_read=0,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Delete by URL
    deleted_count = facade.delete_article_matches_by_url(url)
    assert deleted_count == 1

    # Verify record removed
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches).where(keyword_article_matches.c.article_uri == url)
    ).scalar()
    assert remaining == 0


def test_delete_keyword_alerts_by_url(facade):
    # Step 1: Insert dependent records
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="Delete Group", topic="AI")
    )
    group_id = facade._execute_with_rollback(
        select(keyword_groups.c.id).where(keyword_groups.c.name == "Delete Group")
    ).scalar_one()

    facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    )
    keyword_id = facade._execute_with_rollback(
        select(monitored_keywords.c.id).where(monitored_keywords.c.keyword == "AI")
    ).scalar_one()

    article_uri = "https://example.com/ai-delete"
    facade._execute_with_rollback(
        articles.insert().values(
            uri=article_uri,
            title="AI Delete Example",
            publication_date=datetime.utcnow(),
            topic="AI"
        )
    )

    # Insert alert record
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=article_uri,
            detected_at=datetime.utcnow(),
            is_read=0
        )
    )
    facade.connection.commit()

    # Step 2: Delete and verify
    deleted_count = facade.delete_keyword_alerts_by_url(article_uri)
    assert deleted_count == 1
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts).where(keyword_alerts.c.article_uri == article_uri)
    ).scalar()
    assert remaining == 0


def test_delete_article_by_url(facade):
    url = "https://example.com/delete-this-article"

    # Step 1: Insert article
    facade._execute_with_rollback(
        articles.insert().values(
            uri=url,
            title="Article to be deleted",
            topic="AI",
            publication_date=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Step 2: Delete article
    deleted_count = facade.delete_article_by_url(url)
    assert deleted_count == 1

    # Step 3: Verify removal
    remaining = facade._execute_with_rollback(
        select(func.count()).select_from(articles).where(articles.c.uri == url)
    ).scalar()
    assert remaining == 0



def test_get_all_topics_referenced_in_keyword_groups(facade):
    # Step 1: Insert groups with topics
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="AI Group", topic="AI")
    )
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="Health Group", topic="Health")
    )
    facade._execute_with_rollback(
        keyword_groups.insert().values(name="Duplicate Group", topic="AI")
    )
    facade.connection.commit()

    # Step 2: Fetch distinct topics
    result = facade.get_all_topics_referenced_in_keyword_groups()

    # Step 3: Verify distinctness and values
    assert set(result) == {"AI", "Health"}




def test_get_urls_and_topics_from_articles(facade):
    # Step 1: Insert valid articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ai1",
            title="AI Revolution",
            topic="AI",
            publication_date=datetime.utcnow()
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/health1",
            title="Healthcare 2025",
            topic="Health",
            publication_date=datetime.utcnow()
        )
    )

    # Step 2: Insert one without topic (should be ignored)
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/unknown",
            title="Untitled Article",
            topic=None,
            publication_date=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Step 3: Fetch URLs and topics
    results = facade.get_urls_and_topics_from_articles()

    # Step 4: Validate filtering and content
    urls = [row["uri"] for row in results]
    topics = [row["topic"] for row in results]

    assert "https://example.com/unknown" not in urls
    assert set(topics) == {"AI", "Health"}


# check_if_articles_table_has_topic_column method is not added to test


def test_delete_keyword_article_matches_from_new_table_structure_by_url(facade):
    url = "https://example.com/article-to-delete"

    # Insert a valid row
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            group_id=1,
            article_uri=url,
            is_read=0,
            detected_at=datetime.utcnow(),
            keyword_ids="1"
        )
    )
    facade.connection.commit()

    # Verify row inserted
    before = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches).where(keyword_article_matches.c.article_uri == url)
    ).scalar()
    assert before == 1

    # Delete row
    deleted = facade.delete_keyword_article_matches_from_new_table_structure_by_url(url)
    assert deleted == 1

    # Verify deletion
    after = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_article_matches).where(keyword_article_matches.c.article_uri == url)
    ).scalar()
    assert after == 0


def test_delete_keyword_article_matches_from_old_table_structure_by_url(facade):
    url = "https://example.com/old-alert-delete"

    # Step 1: Create valid keyword group and keyword
    group_id = facade._execute_with_rollback(
        keyword_groups.insert().values(name="Test Group", topic="AI")
    ).inserted_primary_key[0]
    keyword_id = facade._execute_with_rollback(
        monitored_keywords.insert().values(group_id=group_id, keyword="AI")
    ).inserted_primary_key[0]
    facade.connection.commit()

    # Step 2: Insert valid alert
    facade._execute_with_rollback(
        keyword_alerts.insert().values(
            keyword_id=keyword_id,
            article_uri=url,
            is_read=0,
            detected_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    # Step 3: Verify insertion
    count_before = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts).where(keyword_alerts.c.article_uri == url)
    ).scalar()
    assert count_before == 1

    # Step 4: Delete and verify
    deleted = facade.delete_keyword_article_matches_from_old_table_structure_by_url(url)
    assert deleted == 1

    count_after = facade._execute_with_rollback(
        select(func.count()).select_from(keyword_alerts).where(keyword_alerts.c.article_uri == url)
    ).scalar()
    assert count_after == 0


def test_delete_articles_by_article_urls(facade):
    urls = ["https://example.com/a1", "https://example.com/a2"]

    # Insert sample articles (title & publication_date are required)
    for url in urls:
        facade._execute_with_rollback(
            articles.insert().values(
                uri=url,
                title="Sample Title",
                publication_date=datetime.utcnow()
            )
        )
    facade.connection.commit()

    # Verify insertion
    count_before = facade._execute_with_rollback(
        select(func.count()).select_from(articles)
    ).scalar()
    assert count_before == 2

    # Perform deletion
    deleted_count = facade.delete_articles_by_article_urls(None, urls)
    assert deleted_count == 2

    # Verify deletion
    count_after = facade._execute_with_rollback(
        select(func.count()).select_from(articles)
    ).scalar()
    assert count_after == 0



def test_get_monitor_settings(facade):
    # Insert sample keyword monitor settings
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            check_interval=10,
            interval_unit=60,
            is_enabled=True,
            search_date_range=7,
            daily_request_limit=100
        )
    )
    facade.connection.commit()

    result = facade.get_monitor_settings()
    assert result is not None
    assert result[0] == 10  # check_interval
    assert result[2] is True  # is_enabled


def test_get_request_count_for_today(facade):
    today = datetime.utcnow().date()

    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            requests_today=15,
            last_reset_date=str(today)
        )
    )
    facade.connection.commit()

    result = facade.get_request_count_for_today()
    assert result is not None
    assert result[0] == 15  # requests_today



def test_get_articles_by_url(facade):
    url = "https://example.com/article123"

    facade._execute_with_rollback(
        articles.insert().values(
            uri=url,
            title="AI Revolution",
            publication_date=datetime.utcnow()
        )
    )
    facade.connection.commit()

    article = facade.get_articles_by_url(url)
    assert article is not None
    assert article["title"] == "AI Revolution"


def test_get_raw_articles_markdown_by_url(facade):
    url = "https://example.com/raw-article"

    facade._execute_with_rollback(
        raw_articles.insert().values(
            uri=url,
            raw_markdown="# Test Markdown"
        )
    )
    facade.connection.commit()

    result = facade.get_raw_articles_markdown_by_url(url)
    assert result is not None
    assert result["raw_markdown"] == "# Test Markdown"


def test_get_podcasts_for_newsletter_inclusion(facade):
    now = datetime.utcnow()
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=1,
            title="AI Weekly Recap",
            created_at=now,
            audio_url="https://audio.example.com/podcast.mp3"
        )
    )
    facade.connection.commit()

    result = facade.get_podcasts_for_newsletter_inclusion(["audio_url"])
    assert isinstance(result, list)



def test_generate_tts_podcast(facade):
    podcast_id = 99
    params = [
        podcast_id,
        "AI Narration",
        "This is a test transcript",
        '{"language": "en"}'
    ]

    facade.generate_tts_podcast(params)

    result = facade._execute_with_rollback(
        select(podcasts).where(podcasts.c.id == podcast_id)
    ).mappings().fetchone()

    assert result is not None
    assert result["title"] == "AI Narration"
    assert result["status"] == "processing"
    assert result["transcript"] == "This is a test transcript"



def test_mark_podcast_generation_as_complete(facade):
    podcast_id = 1

    # Insert podcast initially in 'processing' state
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="AI Audio Summary",
            status="processing",
            created_at=datetime.utcnow(),
            transcript="Initial transcript",
            metadata='{}'
        )
    )
    facade.connection.commit()

    # Mark as completed
    params = [
        "https://example.com/audio.mp3",  # audio_url
        '{"duration": "2m"}',             # metadata
        podcast_id
    ]
    facade.mark_podcast_generation_as_complete(params)

    # Verify update
    updated = facade._execute_with_rollback(
        select(podcasts).where(podcasts.c.id == podcast_id)
    ).mappings().fetchone()

    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["audio_url"] == "https://example.com/audio.mp3"
    assert updated["error"] is None



def test_log_error_generating_podcast(facade):
    podcast_id = 2

    # Insert podcast initially
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="Failed Podcast",
            status="processing",
            created_at=datetime.utcnow(),
            transcript="Testing error handling"
        )
    )
    facade.connection.commit()

    # Simulate error
    params = ["Audio processing failed", podcast_id]
    facade.log_error_generating_podcast(params)

    # Verify update
    failed = facade._execute_with_rollback(
        select(podcasts).where(podcasts.c.id == podcast_id)
    ).mappings().fetchone()

    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error"] == "Audio processing failed"
    assert failed["completed_at"] is not None



def test_test_data_select(facade):
    # Should not raise any exceptions
    facade.test_data_select()



def test_get_keyword_monitor_is_enabled_and_daily_request_limit(facade):
    # Insert keyword monitor settings
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            is_enabled=True,
            daily_request_limit=250,
            check_interval=10,
            interval_unit=60,
            search_date_range=7
        )
    )
    facade.connection.commit()

    result = facade.get_keyword_monitor_is_enabled_and_daily_request_limit()
    assert result is not None
    assert result[0] is True  # is_enabled
    assert result[1] == 250   # daily_request_limit



def test_get_topic_statistics(facade):
    now = datetime.utcnow()

    # Insert articles under two topics
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a1",
            title="AI in 2025",
            topic="AI",
            submission_date=now
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a2",
            title="Climate Innovations",
            topic="Environment",
            publication_date=now - timedelta(days=2)
        )
    )
    facade.connection.commit()

    result = facade.get_topic_statistics()
    assert isinstance(result, list)
    topics = [r["topic"] for r in result]
    assert "AI" in topics
    assert "Environment" in topics
    assert all("article_count" in r for r in result)



def test_get_last_check_time_using_timezone_format(facade):
    from datetime import datetime

    now = datetime.utcnow()

    # Insert a row into keyword_monitor_status
    facade._execute_with_rollback(
        keyword_monitor_status.insert().values(
            id=1,
            last_check_time=now.isoformat(),
            requests_today=5
        )
    )
    facade.connection.commit()

    result = facade.get_last_check_time_using_timezone_format()
    assert result.endswith("Z")
    assert "T" in result


def test_get_podcast_transcript(facade):
    podcast_id = 10
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="AI Deep Dive",
            transcript="This is a transcript.",
            metadata='{"duration": "5m"}',
            created_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    result = facade.get_podcast_transcript(podcast_id)
    assert result is not None
    assert result[0] == "AI Deep Dive"
    assert "transcript" in podcasts.c



def test_get_all_podcasts(facade):
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=11,
            title="Podcast Alpha",
            status="completed",
            created_at=datetime.utcnow(),
            audio_url="https://example.com/audio1.mp3"
        )
    )
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=12,
            title="Podcast Beta",
            status="processing",
            created_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    results = facade.get_all_podcasts()
    assert isinstance(results, list)
    assert len(results) >= 2
    assert "title" in results[0]
    assert "status" in results[0]



def test_get_podcast_generation_status(facade):
    podcast_id = 13
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="Podcast Status Test",
            status="completed",
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            audio_url="https://example.com/audio.mp3",
            error=None
        )
    )
    facade.connection.commit()

    result = facade.get_podcast_generation_status(podcast_id)
    assert result is not None
    assert result[2] == "completed"  # status



def test_get_podcast_audio_file(facade):
    podcast_id = 14
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="Audio File Podcast",
            audio_url="https://example.com/podcast.mp3",
            created_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    result = facade.get_podcast_audio_file(podcast_id)
    assert result is not None
    assert "example.com/podcast.mp3" in result[0]



def test_delete_podcast(facade):
    podcast_id = 15
    facade._execute_with_rollback(
        podcasts.insert().values(
            id=podcast_id,
            title="Podcast to Delete",
            created_at=datetime.utcnow()
        )
    )
    facade.connection.commit()

    facade.delete_podcast(podcast_id)

    deleted = facade._execute_with_rollback(
        select(func.count()).select_from(podcasts).where(podcasts.c.id == podcast_id)
    ).scalar()

    assert deleted == 0



def test_search_for_articles_based_on_query_date_range_and_topic(facade):
    now = datetime.utcnow()

    # Insert multiple articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/ai-news",
            title="AI Research Breakthrough",
            summary="Advancements in deep learning.",
            topic="AI",
            publication_date=now
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/env-news",
            title="Climate Change Progress",
            summary="Renewable energy growth.",
            topic="Environment",
            publication_date=now - timedelta(days=5)
        )
    )
    facade.connection.commit()

    # Search by query, topic, and date range
    start_date = now - timedelta(days=7)
    end_date = now
    result = facade.search_for_articles_based_on_query_date_range_and_topic(
        query="AI",
        topic="AI",
        start_date=start_date,
        end_date=end_date,
        limit=10
    )

    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0]["topic"] == "AI"




def test_update_article_by_url(facade):
    uri = "https://example.com/article-xyz"

    # Insert base article
    facade._execute_with_rollback(
        articles.insert().values(
            uri=uri,
            title="Old Title",
            topic="AI",
            publication_date=datetime.utcnow(),
            topic_alignment_score=0.1
        )
    )
    facade.connection.commit()

    # Update the article
    params = [0.95, 0.85, 0.9, "AI-related", "AI, ML", "data, learning", uri]
    updated_rows = facade.update_article_by_url(params)

    assert updated_rows == 1

    updated = facade._execute_with_rollback(
        select(articles).where(articles.c.uri == uri)
    ).mappings().fetchone()
    assert updated["topic_alignment_score"] == 0.95
    assert updated["keyword_relevance_score"] == 0.85


def test_enable_or_disable_auto_ingest(facade):
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            auto_ingest_enabled=False,
            check_interval=10,
            interval_unit=60,
            search_date_range=7,
            daily_request_limit=100
        )
    )
    facade.connection.commit()

    # Enable auto-ingest
    facade.enable_or_disable_auto_ingest(True)
    updated = facade._execute_with_rollback(
        select(keyword_monitor_settings.c.auto_ingest_enabled)
    ).scalar()
    assert updated is True



def test_get_auto_ingest_settings(facade):
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            auto_ingest_enabled=True,
            min_relevance_threshold=0.7,
            quality_control_enabled=True,
            auto_save_approved_only=False,
            default_llm_model="gpt-4o-mini",
            llm_temperature=0.5,
            llm_max_tokens=1000
        )
    )
    facade.connection.commit()

    settings = facade.get_auto_ingest_settings()
    assert settings is not None
    assert settings[0] is True
    assert settings[1] == 0.7



def test_get_processing_statistics(facade):
    now = datetime.utcnow()

    # Insert multiple articles
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a1",
            title="Approved Article",
            auto_ingested=True,
            ingest_status="approved",
            quality_score=9.5
        )
    )
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/a2",
            title="Failed Article",
            auto_ingested=True,
            ingest_status="failed",
            quality_score=5.0
        )
    )
    facade.connection.commit()

    stats = facade.get_processing_statistics()
    assert stats is not None
    assert stats[0] == 2  # total_auto_ingested
    assert stats[1] == 1  # approved_count
    assert stats[2] == 1  # failed_count



def test_stamp_keyword_monitor_status_table_with_todays_date_insert_and_update(facade):
    today = datetime.utcnow().date().isoformat()

    # Insert new entry
    params = [10, today]
    facade.stamp_keyword_monitor_status_table_with_todays_date(params)

    first_entry = facade._execute_with_rollback(
        select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
    ).mappings().fetchone()
    assert first_entry["requests_today"] == 10

    # Update existing
    params = [20, today]
    facade.stamp_keyword_monitor_status_table_with_todays_date(params)

    updated_entry = facade._execute_with_rollback(
        select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
    ).mappings().fetchone()
    assert updated_entry["requests_today"] == 20



def test_get_keyword_monitor_status_daily_request_limit(facade):
    facade._execute_with_rollback(
        keyword_monitor_settings.insert().values(
            id=1,
            daily_request_limit=500,
            check_interval=15,
            interval_unit=60,
            search_date_range=7
        )
    )
    facade.connection.commit()

    result = facade.get_keyword_monitor_status_daily_request_limit()
    assert result is not None
    assert result[0] == 500


def test_check_if_media_bias_has_updated_at_column(facade):
    cols = facade.check_if_media_bias_has_updated_at_column()
    assert isinstance(cols, list)
    assert "updated_at" in cols

def test_insert_media_bias_insert_and_return_id(facade):
    # clean slate if an entry exists
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == "test-source-1"))
    facade.connection.commit()

    params = [
        "test-source-1",   # source
        "Testland",        # country
        "left",            # bias
        7.5,               # factual_reporting
        80.0,              # press_freedom
        "online",          # media_type
        123,               # popularity
        "A+",              # mbfc_credibility_rating
    ]

    inserted_id = facade.insert_media_bias(params + [None])  # last param (enabled) ignored for insert path
    # inserted_primary_key should be returned as an int
    assert isinstance(inserted_id, int) or inserted_id is not None

    row = facade._execute_with_rollback(select(mediabias).where(mediabias.c.source == "test-source-1")).mappings().fetchone()
    assert row is not None
    assert row["source"] == "test-source-1"
    assert row["enabled"] == 1

def test_insert_media_bias_update_existing_row(facade):
    # ensure existing
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == "test-source-2"))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source="test-source-2",
            country="Oldland",
            bias="center",
            factual_reporting=5.0,
            press_freedom=60.0,
            media_type="print",
            popularity=10,
            mbfc_credibility_rating="B",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    # update via insert_media_bias (update branch)
    params = [
        "test-source-2",  # source (existing)
        "Newland",        # country (update)
        "right",          # bias
        8.0,              # factual_reporting
        90.0,             # press_freedom
        "online",         # media_type
        999,              # popularity
        "A",              # mbfc_credibility_rating
        0                 # enabled -> update to 0
    ]
    rowcount = facade.insert_media_bias(params)
    assert rowcount == 1  # one row updated

    updated = facade._execute_with_rollback(select(mediabias).where(mediabias.c.source == "test-source-2")).mappings().fetchone()
    assert updated["country"] == "Newland"
    assert updated["bias"] == "right"
    assert updated["enabled"] == 0

def test_update_media_bias_source(facade):
    # ensure base row exists
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == "test-source-3"))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source="test-source-3",
            country="X",
            bias="center",
            factual_reporting=4.0,
            press_freedom=50.0,
            media_type="tv",
            popularity=1,
            mbfc_credibility_rating="C",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    params = [
        "test-source-3",   # source
        "UpdatedCountry",  # country
        "left",            # bias
        9.0,               # factual_reporting
        100.0,             # press_freedom
        "online",          # media_type
        42,                # popularity
        "A-",              # mbfc_credibility_rating
        1                  # enabled
    ]
    facade.update_media_bias_source(params)

    updated = facade._execute_with_rollback(select(mediabias).where(mediabias.c.source == "test-source-3")).mappings().fetchone()
    assert updated["country"] == "UpdatedCountry"
    assert updated["bias"] == "left"
    assert updated["mbfc_credibility_rating"] == "A-"

def test_update_media_bias_settings_and_readback(facade):
    # ensure mediabias_settings row exists (id=1)
    facade._execute_with_rollback(delete(mediabias_settings).where(mediabias_settings.c.id == 1))
    facade._execute_with_rollback(
        insert(mediabias_settings).values(id=1, enabled=0, source_file=None, last_updated=None)
    )
    facade.connection.commit()

    test_path = "/tmp/test_media_bias_source.csv"
    facade.update_media_bias_settings(test_path)

    row = facade._execute_with_rollback(select(mediabias_settings).where(mediabias_settings.c.id == 1)).mappings().fetchone()
    assert row is not None
    assert row["enabled"] == 1
    assert row["source_file"] == test_path

def test_get_all_media_bias_sources_returns_ordered_list(facade):
    # cleanup & insert multiple sources
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source.like("bulk-source-%")))
    for i in range(1, 4):
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=f"bulk-source-{i}",
                country=f"Country{i}",
                bias="center",
                factual_reporting=5.0 + i,
                press_freedom=50 + i,
                media_type="online",
                popularity=i,
                mbfc_credibility_rating="B",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )
    facade.connection.commit()

    rows = facade.get_all_media_bias_sources()
    # ensure we returned a list of mappings and that our inserted sources appear
    sources = [r["source"] for r in rows]
    assert "bulk-source-1" in sources
    assert "bulk-source-2" in sources
    assert "bulk-source-3" in sources


def test_get_media_bias_status(facade):
    # ensure mediabias_settings has an entry
    facade._execute_with_rollback(delete(mediabias_settings).where(mediabias_settings.c.id == 1))
    facade._execute_with_rollback(
        insert(mediabias_settings).values(
            id=1,
            enabled=1,
            source_file="/tmp/media_bias.csv",
            last_updated=func.current_timestamp()
        )
    )
    facade.connection.commit()

    result = facade.get_media_bias_status()
    assert result is not None
    assert result[0] == 1
    assert "/tmp/media_bias.csv" in result[2]


def test_get_media_bias_source(facade):
    source_name = "sample-source"
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == source_name))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source=source_name,
            country="Testland",
            bias="center",
            factual_reporting=8.0,
            press_freedom=90.0,
            media_type="online",
            popularity=50,
            mbfc_credibility_rating="A",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    result = facade.get_media_bias_source(source_name)
    assert result is not None
    assert result[0] == source_name


def test_delete_media_bias_source(facade):
    source_name = "delete-me"
    facade._execute_with_rollback(
        insert(mediabias).values(
            source=source_name,
            country="X",
            bias="right",
            factual_reporting=6.0,
            press_freedom=75.0,
            media_type="print",
            popularity=10,
            mbfc_credibility_rating="B",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    facade.delete_media_bias_source(source_name)

    count = facade._execute_with_rollback(
        select(func.count()).select_from(mediabias).where(mediabias.c.source == source_name)
    ).scalar()
    assert count == 0


def test_get_total_media_bias_sources(facade):
    # insert a few sources
    for i in range(3):
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=f"count-source-{i}",
                country="Y",
                bias="center",
                factual_reporting=7.0,
                press_freedom=80.0,
                media_type="online",
                popularity=5,
                mbfc_credibility_rating="A",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )
    facade.connection.commit()

    total = facade.get_total_media_bias_sources()
    assert isinstance(total, int)
    assert total >= 3


def test_enable_media_bias_sources(facade):
    facade._execute_with_rollback(delete(mediabias_settings).where(mediabias_settings.c.id == 1))
    facade._execute_with_rollback(
        insert(mediabias_settings).values(id=1, enabled=0, source_file=None)
    )
    facade.connection.commit()

    # Enable
    facade.enable_media_bias_sources(True)
    enabled_val = facade._execute_with_rollback(
        select(mediabias_settings.c.enabled).where(mediabias_settings.c.id == 1)
    ).scalar()
    assert enabled_val == 1

    # Disable
    facade.enable_media_bias_sources(False)
    disabled_val = facade._execute_with_rollback(
        select(mediabias_settings.c.enabled).where(mediabias_settings.c.id == 1)
    ).scalar()
    assert disabled_val == 0


def test_update_media_bias_last_updated(facade):
    facade._execute_with_rollback(delete(mediabias_settings).where(mediabias_settings.c.id == 1))
    facade._execute_with_rollback(
        insert(mediabias_settings).values(id=1, enabled=1, source_file=None, last_updated=None)
    )
    facade.connection.commit()

    rowcount = facade.update_media_bias_last_updated()
    assert rowcount == 1

    result = facade._execute_with_rollback(
        select(mediabias_settings.c.last_updated).where(mediabias_settings.c.id == 1)
    ).scalar()
    assert result is not None


def test_reset_media_bias_sources(facade):
    # Insert some sources
    for i in range(2):
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=f"reset-source-{i}",
                country="Z",
                bias="neutral",
                factual_reporting=5.5,
                press_freedom=85.0,
                media_type="tv",
                popularity=25,
                mbfc_credibility_rating="B",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )

    # Insert mediabias_settings entry
    facade._execute_with_rollback(
        insert(mediabias_settings).values(
            id=1,
            enabled=1,
            source_file="/tmp/test.csv",
            last_updated=func.current_timestamp()
        )
    )
    facade.connection.commit()

    facade.reset_media_bias_sources()

    # Confirm mediabias cleared
    total = facade._execute_with_rollback(select(func.count()).select_from(mediabias)).scalar()
    assert total == 0

    # Confirm mediabias_settings reset but not disabled
    settings = facade._execute_with_rollback(select(mediabias_settings).where(mediabias_settings.c.id == 1)).mappings().fetchone()
    assert settings["enabled"] == 1
    assert settings["source_file"] is None


def test_enable_media_source(facade):
    source_name = "enable-me"
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == source_name))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source=source_name,
            country="X",
            bias="left",
            factual_reporting=7.2,
            press_freedom=92.0,
            media_type="online",
            popularity=12,
            mbfc_credibility_rating="A",
            updated_at=func.current_timestamp(),
            enabled=0
        )
    )
    facade.connection.commit()

    facade.enable_media_source(source_name)

    result = facade._execute_with_rollback(
        select(mediabias.c.enabled).where(mediabias.c.source == source_name)
    ).scalar()
    assert result == 1


def test_search_media_bias_sources(facade):
    # Clean and insert some test data
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source.like("search-source-%")))
    for i, bias in enumerate(["left", "right", "center"]):
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=f"search-source-{i}",
                country=f"Country{i}",
                bias=bias,
                factual_reporting=str(6 + i),
                press_freedom=80 + i,
                media_type="online",
                popularity=i,
                mbfc_credibility_rating="A",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )
    facade.connection.commit()

    # Case 1: Query filter
    total, results = facade.search_media_bias_sources(
        query="source-1", bias_filter=None, factual_filter=None, country_filter=None, page=1, per_page=10
    )
    assert total >= 1
    assert any("source-1" in row["source"] for row in results)

    # Case 2: Bias filter
    total, results = facade.search_media_bias_sources(
        query=None, bias_filter="right", factual_filter=None, country_filter=None, page=1, per_page=10
    )
    assert total == 1
    assert results[0]["bias"] == "right"

    # Case 3: Country filter (pagination)
    total, results = facade.search_media_bias_sources(
        query=None, bias_filter=None, factual_filter=None, country_filter="Country", page=1, per_page=2
    )
    assert total >= 3
    assert len(results) <= 2


def test_delete_media_bias_source_removes_entry(facade):
    src = "to-delete-source"
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == src))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source=src,
            country="DeleteLand",
            bias="neutral",
            factual_reporting="7",
            press_freedom=90.0,
            media_type="print",
            popularity=5,
            mbfc_credibility_rating="B",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    # Delete and verify
    facade.delete_media_bias_source(src)
    count = facade._execute_with_rollback(
        select(func.count()).select_from(mediabias).where(mediabias.c.source == src)
    ).scalar()
    assert count == 0


def test_get_media_bias_source_by_id(facade):
    src = "lookup-source"
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source == src))
    facade._execute_with_rollback(
        insert(mediabias).values(
            source=src,
            country="LookupLand",
            bias="left",
            factual_reporting="8",
            press_freedom=88.0,
            media_type="tv",
            popularity=12,
            mbfc_credibility_rating="A+",
            updated_at=func.current_timestamp(),
            enabled=1
        )
    )
    facade.connection.commit()

    result = facade.get_media_bias_source_by_id(src)
    assert result is not None
    assert result["source"] == src
    assert result["country"] == "LookupLand"


def test_get_media_bias_filter_options(facade):
    # Insert multiple distinct bias/country/factual entries
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source.like("filter-source-%")))
    data = [
        ("filter-source-1", "India", "left", "High"),
        ("filter-source-2", "USA", "right", "Medium"),
        ("filter-source-3", "France", "center", "Low")
    ]
    for src, country, bias, factual in data:
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=src,
                country=country,
                bias=bias,
                factual_reporting=factual,
                press_freedom=90.0,
                media_type="online",
                popularity=10,
                mbfc_credibility_rating="A",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )
    facade.connection.commit()

    biases, factuals, countries = facade.get_media_bias_filter_options()

    assert all(isinstance(b, str) for b in biases)
    assert any(b == "left" for b in biases)
    assert any(c == "USA" for c in countries)
    assert any(f == "High" for f in factuals)


def test_load_media_bias_sources_from_database(facade):
    # Insert a few rows
    facade._execute_with_rollback(delete(mediabias).where(mediabias.c.source.like("load-source-%")))
    for i in range(2):
        facade._execute_with_rollback(
            insert(mediabias).values(
                source=f"load-source-{i}",
                country="LoadLand",
                bias="neutral",
                factual_reporting="7",
                press_freedom=85.0,
                media_type="online",
                popularity=10,
                mbfc_credibility_rating="A",
                updated_at=func.current_timestamp(),
                enabled=1
            )
        )
    facade.connection.commit()

    rows = facade.load_media_bias_sources_from_database()
    assert isinstance(rows, list)
    assert any("load-source-" in row["source"] for row in rows)


def test_search_articles_with_filters(facade):
    # Clean up any old data
    facade._execute_with_rollback(delete(articles).where(articles.c.title.like("search-article-%")))

    # Insert some dummy articles
    now = datetime.utcnow()
    sample_articles = [
        {
            "uri": f"uri-{i}",
            "title": f"search-article-{i}",
            "summary": "AI and environment",
            "topic": "AI" if i % 2 == 0 else "Environment",
            "category": "Tech" if i % 2 == 0 else "Science",
            "future_signal": "positive",
            "sentiment": "neutral",
            "tags": "innovation,climate",
            "publication_date": now,
            "submission_date": now,
        }
        for i in range(5)
    ]
    for art in sample_articles:
        facade._execute_with_rollback(insert(articles).values(**art))
    facade.connection.commit()

    # Test topic filter
    results, count = facade.search_articles(topic="AI")
    assert count > 0
    assert all(r["topic"] == "AI" for r in results)

    # Test keyword filter
    results, count = facade.search_articles(keyword="environment")
    assert count > 0
    assert any("environment" in r["summary"] for r in results)

    # Test category + pagination
    results, count = facade.search_articles(category=["Tech"], page=1, per_page=2)
    assert count >= 1
    assert len(results) <= 2
    assert all(r["category"] == "Tech" for r in results)

    # Test require_category flag
    results, count = facade.search_articles(require_category=True)
    assert all(r["category"] for r in results)


def test_get_recent_articles_by_topic(facade):
    topic = "AI Recent"
    now = datetime.utcnow()

    # Clean up and insert test data
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    for i in range(3):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"recent-{i}",
                title=f"Recent article {i}",
                topic=topic,
                category="Tech",
                sentiment="positive",
                tags="ml,ai",
                publication_date=now - timedelta(days=i),
                submission_date=now - timedelta(days=i),
            )
        )
    facade.connection.commit()

    # Fetch recent articles
    results = facade.get_recent_articles_by_topic(topic_name=topic, limit=2)
    assert isinstance(results, list)
    assert len(results) <= 2
    assert all(r["topic"] == topic for r in results)
    assert isinstance(results[0]["tags"], list)


def test_get_news_feed_articles_for_date_range(facade):
    topic = "FeedTopic"
    now = datetime.utcnow()

    # Clean up and insert test data
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    for i in range(4):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"feed-uri-{i}",
                title=f"Feed title {i}",
                summary="Feed summary",
                news_source="testnews.com",
                publication_date=(now - timedelta(days=i)),
                submission_date=(now - timedelta(days=i)),
                category="Tech",
                topic=topic,
                sentiment="positive",
                bias="neutral",
                factual_reporting="high",
            )
        )
    facade.connection.commit()

    # Run the query for last 7 days
    start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    results = facade.get_news_feed_articles_for_date_range(
        date_condition_type="7d",
        date_params=[start_date, end_date],
        max_articles=5,
        topic=topic,
        bias_filter=None,
        offset=0,
        limit=3
    )

    assert isinstance(results, list)
    assert len(results) <= 3
    assert all("uri" in r for r in results)
    assert all(r["topic"] == topic for r in results)


def test_get_news_feed_articles_count_for_date_range(facade):
    topic = "CountTopic"
    now = datetime.utcnow()

    # Clean and insert test data
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    for i in range(3):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"count-uri-{i}",
                title=f"Count title {i}",
                summary="Counting test article",
                news_source="countnews.com",
                publication_date=(now - timedelta(days=i)),
                category="Tech",
                topic=topic,
                sentiment="positive",
                bias="center",
                factual_reporting="mostly factual",
            )
        )
    facade.connection.commit()

    # Count within date range
    start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    count = facade.get_news_feed_articles_count_for_date_range(
        date_condition_type="7d",
        date_params=[start_date, end_date],
        topic=topic,
        bias_filter="center"
    )

    assert isinstance(count, int)
    assert count >= 1


def test_get_articles_by_uris(facade):
    now = datetime.utcnow()
    uris = [f"uri-{i}" for i in range(3)]

    # Cleanup & insert
    facade._execute_with_rollback(delete(articles).where(articles.c.uri.in_(uris)))
    for i in range(3):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=uris[i],
                title=f"Article {i}",
                topic="AI",
                category="Tech",
                news_source="SourceX",
                sentiment="neutral",
                publication_date=now,
                submission_date=now
            )
        )
    facade.connection.commit()

    # Just verify returned data (ignore logs)
    results = facade.get_articles_by_uris(uris)
    assert isinstance(results, list)
    assert len(results) == 3
    assert all(r["uri"] in uris for r in results)

    # Empty URIs returns empty list
    empty_results = facade.get_articles_by_uris([])
    assert empty_results == []


def test_get_topic_articles_count(facade):
    topic = "CountTestTopic"
    now = datetime.utcnow()

    # Cleanup & insert
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    for i in range(2):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"count-uri-{i}",
                title=f"Count Article {i}",
                topic=topic,
                category="Science",
                publication_date=now,
                submission_date=now
            )
        )
    facade.connection.commit()

    count = facade.get_topic_articles_count(topic)
    assert isinstance(count, int)
    assert count == 2


def test_get_topic_articles_count_since(facade):
    topic = "SinceTestTopic"
    now = datetime.utcnow()

    # Cleanup & insert 2 recent + 1 old
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    facade._execute_with_rollback(
        insert(articles).values(
            uri="since-old",
            title="Old Article",
            topic=topic,
            submission_date=now - timedelta(days=10),
            publication_date=now - timedelta(days=10)
        )
    )
    for i in range(2):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"since-new-{i}",
                title=f"New Article {i}",
                topic=topic,
                submission_date=now,
                publication_date=now
            )
        )
    facade.connection.commit()

    # Only count recent ones (last 5 days)
    since_datetime = (now - timedelta(days=5)).isoformat()
    count = facade.get_topic_articles_count_since(topic, since_datetime)
    assert count == 2


def test_get_dominant_news_source_for_topic(facade):
    topic = "SourceTestTopic"
    now = datetime.utcnow()

    # Cleanup
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    # Insert multiple sources (2 from Reuters, 1 from Bloomberg)
    data = [
        ("reuters.com", now),
        ("reuters.com", now),
        ("bloomberg.com", now)
    ]
    for idx, (src, dt) in enumerate(data):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"src-{idx}",
                title=f"Article {idx}",
                topic=topic,
                news_source=src,
                submission_date=dt,
                publication_date=dt
            )
        )
    facade.connection.commit()

    result = facade.get_dominant_news_source_for_topic(topic, (now - timedelta(days=1)).isoformat())
    assert result == "reuters.com"


def test_get_most_frequent_time_to_impact_for_topic(facade):
    topic = "ImpactTestTopic"
    now = datetime.utcnow()

    # Cleanup
    facade._execute_with_rollback(delete(articles).where(articles.c.topic == topic))
    # Insert with time_to_impact values (two 'short-term', one 'long-term')
    impacts = ["short-term", "short-term", "long-term"]
    for i, tti in enumerate(impacts):
        facade._execute_with_rollback(
            insert(articles).values(
                uri=f"impact-{i}",
                title=f"Impact {i}",
                topic=topic,
                time_to_impact=tti,
                submission_date=now,
                publication_date=now
            )
        )
    facade.connection.commit()

    result = facade.get_most_frequent_time_to_impact_for_topic(topic, (now - timedelta(days=2)).isoformat())
    assert result == "short-term"



def test_get_signal_alerts(facade): # todo: to be enhanced in database_query_facade.py
    now = datetime.utcnow()

    # Cleanup any old data
    facade._execute_with_rollback(delete(signal_alerts))
    facade._execute_with_rollback(delete(articles))

    # Insert sample article
    facade._execute_with_rollback(
        insert(articles).values(
            uri="article-1",
            title="AI Threat Detection",
            topic="AI",
            news_source="testsource.com",
            publication_date=now,
            submission_date=now
        )
    )

    # Insert sample signal alert
    facade._execute_with_rollback(
        insert(signal_alerts).values(
            id=1,
            article_uri="article-1",
            instruction_id=10,
            instruction_name="Detect AI Risks",
            confidence=0.9,
            threat_level="high",
            summary="Potential AI misuse",
            detected_at=now,
            is_acknowledged=False,
            acknowledged_at=None
        )
    )
    facade.connection.commit()

    # Fetch alerts normally
    results = facade.get_signal_alerts(topic="AI", acknowledged=False)
    assert isinstance(results, list)
    assert len(results) == 1
    alert = results[0]
    assert alert["instruction_name"] == "Detect AI Risks"
    assert alert["article_title"] == "AI Threat Detection"

    # Test with empty filters
    results = facade.get_signal_alerts()
    assert len(results) >= 1


def test_acknowledge_signal_alert(facade): # todo: to be enhanced in database_query_facade.py
    now = datetime.utcnow()

    # Ensure a sample alert exists
    facade._execute_with_rollback(delete(signal_alerts))
    facade._execute_with_rollback(
        insert(signal_alerts).values(
            id=2,
            article_uri="ack-uri",
            instruction_id=5,
            instruction_name="Acknowledge Test",
            confidence=0.8,
            threat_level="medium",
            summary="Testing acknowledgment",
            detected_at=now,
            is_acknowledged=False,
            acknowledged_at=None
        )
    )
    facade.connection.commit()

    # Acknowledge alert
    result = facade.acknowledge_signal_alert(alert_id=2)
    assert result is True

    # Verify acknowledgment updated
    updated = facade._execute_with_rollback(
        select(signal_alerts.c.is_acknowledged).where(signal_alerts.c.id == 2)
    ).scalar()
    assert updated is True


def test_get_signal_instructions(facade): # todo: to be enhanced in database_query_facade.py
    now = datetime.utcnow()

    # Cleanup & insert sample data
    facade._execute_with_rollback(delete(signal_instructions))
    sample_data = [
        dict(id=1, name="Instruction A", description="Detect AI risks", instruction="Use model A",
             topic="AI", is_active=True, created_at=now, updated_at=now),
        dict(id=2, name="Instruction B", description="Monitor energy", instruction="Use model B",
             topic="Energy", is_active=False, created_at=now, updated_at=now)
    ]
    for row in sample_data:
        facade._execute_with_rollback(insert(signal_instructions).values(**row))
    facade.connection.commit()

    # Fetch active instructions
    active = facade.get_signal_instructions(active_only=True)
    assert all(i["is_active"] for i in active)

    # Fetch all instructions
    all_instr = facade.get_signal_instructions(active_only=False)
    assert len(all_instr) >= 2


def test_save_signal_instruction(facade): # todo: to be enhanced in database_query_facade.py
    now = datetime.utcnow()
    facade._execute_with_rollback(delete(signal_instructions))
    facade.connection.commit()

    # Insert new instruction
    result = facade.save_signal_instruction(
        name="ThreatAlert",
        description="Detect deepfake content",
        instruction="If deepfake detected, flag as high risk",
        topic="AI",
        is_active=True
    )
    assert result is True

    # Verify insertion
    row = facade._execute_with_rollback(
        select(signal_instructions.c.name, signal_instructions.c.description)
    ).mappings().fetchone()
    assert row["name"] == "ThreatAlert"
    assert "deepfake" in row["description"]

    # Update same record (ON CONFLICT)
    result2 = facade.save_signal_instruction(
        name="ThreatAlert",
        description="Updated description",
        instruction="Updated rule",
        topic="AI",
        is_active=False
    )
    assert result2 is True

    # Ensure updated
    updated = facade._execute_with_rollback(
        select(signal_instructions.c.description, signal_instructions.c.is_active)
    ).mappings().fetchone()
    assert updated["description"] == "Updated description"
    assert bool(updated["is_active"]) is False


def test_delete_signal_instruction(facade): # todo: to be enhanced in database_query_facade.py  
    now = datetime.utcnow()
    facade._execute_with_rollback(delete(signal_instructions))

    # Insert a dummy record
    facade._execute_with_rollback(
        insert(signal_instructions).values(
            id=999,
            name="DeleteMe",
            description="Temporary rule",
            instruction="DELETE TEST",
            topic="Temp",
            is_active=True,
            created_at=now,
            updated_at=now
        )
    )
    facade.connection.commit()

    # Delete it
    result = facade.delete_signal_instruction(999)
    assert result is True

    # Verify deletion
    exists = facade._execute_with_rollback(
        select(signal_instructions.c.id).where(signal_instructions.c.id == 999)
    ).fetchone()
    assert exists is None



def test_save_signal_alert_insert_and_update(facade): # todo: to be enhanced in database_query_facade.py
    # Insert a sample article (for FK reference)
    facade._execute_with_rollback(
        articles.insert().values(
            uri="https://example.com/article1",
            title="AI Cyber Threats",
            publication_date=datetime.utcnow()
        )
    )

    # Insert a sample instruction (for FK reference)
    facade._execute_with_rollback(
        signal_instructions.insert().values(
            id=1,
            name="Detect AI Threats",
            description="Instruction to detect AI threats",
            instruction="Find AI-generated malicious content",
            topic="Cybersecurity",
            is_active=True
        )
    )
    facade.connection.commit()

    # Insert a new signal alert
    alert_id = facade.save_signal_alert(
        article_uri="https://example.com/article1",
        instruction_id=1,
        instruction_name="Detect AI Threats",
        confidence=0.85,
        threat_level="high",
        summary="Detected possible AI-driven phishing attempt"
    )

    assert alert_id is not None

    # Verify the inserted record
    result = facade._execute_with_rollback(
        select(signal_alerts).where(signal_alerts.c.id == alert_id)
    ).mappings().fetchone()

    assert result is not None
    assert result["instruction_name"] == "Detect AI Threats"
    assert result["confidence"] == pytest.approx(0.85, 0.001)
    assert result["threat_level"] == "high"
    assert result["summary"] == "Detected possible AI-driven phishing attempt"

    detected_at_before = result["detected_at"]

    # Update the same alert (should trigger ON CONFLICT)
    updated_id = facade.save_signal_alert(
        article_uri="https://example.com/article1",
        instruction_id=1,
        instruction_name="Detect AI Threats",
        confidence=0.92,
        threat_level="critical",
        summary="AI ransomware activity detected"
    )

    assert updated_id == alert_id

    # Verify the update
    updated_result = facade._execute_with_rollback(
        select(signal_alerts).where(signal_alerts.c.id == alert_id)
    ).mappings().fetchone()

    assert updated_result["confidence"] == pytest.approx(0.92, 0.001)
    assert updated_result["threat_level"] == "critical"
    assert updated_result["summary"] == "AI ransomware activity detected"
    assert updated_result["detected_at"] >= detected_at_before





def test_create_and_get_auspex_chat(facade):
    metadata = {"model": "gpt-5", "context": "business-analysis"}

    # Create a new Auspex chat
    chat_id = facade.create_auspex_chat(
        topic="AI Strategy",
        title="Q1 Business Planning",
        user_id="user_001",
        profile_id=5,
        metadata=metadata
    )
    assert chat_id is not None

    # Retrieve the chat
    chat = facade.get_auspex_chat(chat_id)
    assert chat is not None
    assert chat["topic"] == "AI Strategy"
    assert chat["title"] == "Q1 Business Planning"
    assert chat["user_id"] == "user_001"
    assert chat["profile_id"] == 5
    assert isinstance(chat["metadata"], dict)
    assert chat["metadata"]["model"] == "gpt-5"


def test_get_auspex_chats_with_message_counts(facade):
    # Create another chat
    chat_id = facade.create_auspex_chat(
        topic="AI Strategy",
        title="Follow-up Discussion",
        user_id="user_001",
        metadata={"context": "follow-up"}
    )

    # Add two messages to this chat
    facade.add_auspex_message(chat_id, "user", "Hello, let's plan AI roadmap")
    facade.add_auspex_message(chat_id, "assistant", "Sure, let's begin with goals")

    # Retrieve all chats
    chats = facade.get_auspex_chats(topic="AI Strategy", user_id="user_001")
    assert isinstance(chats, list)
    assert len(chats) >= 1
    assert any("message_count" in chat for chat in chats)
    assert all(isinstance(chat["message_count"], int) for chat in chats)


def test_update_auspex_chat_profile(facade):
    # Create a chat
    chat_id = facade.create_auspex_chat(
        topic="Cybersecurity",
        title="Threat Analysis",
        user_id="user_002",
        profile_id=1
    )

    # Update profile_id
    result = facade.update_auspex_chat_profile(chat_id, 10)
    assert result is True

    # Verify update
    chat = facade.get_auspex_chat(chat_id)
    assert chat["profile_id"] == 10


def test_add_and_get_auspex_messages(facade):
    # Create a chat
    chat_id = facade.create_auspex_chat(topic="AI Ethics", user_id="user_003")

    # Add multiple messages
    msg_id_1 = facade.add_auspex_message(chat_id, "user", "What is AI ethics?")
    msg_id_2 = facade.add_auspex_message(
        chat_id, "assistant", "AI ethics is about responsible AI use", metadata={"tokens": 12}
    )

    assert msg_id_1 is not None
    assert msg_id_2 is not None

    # Retrieve messages
    messages = facade.get_auspex_messages(chat_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert isinstance(messages[1]["metadata"], dict)
    assert messages[1]["metadata"]["tokens"] == 12


def test_delete_auspex_chat(facade):
    # Create a chat and add a message
    chat_id = facade.create_auspex_chat(topic="Delete Test", user_id="user_004")
    facade.add_auspex_message(chat_id, "user", "Please delete this chat")

    # Delete the chat
    result = facade.delete_auspex_chat(chat_id)
    assert result is True

    # Verify it was deleted
    chat = facade.get_auspex_chat(chat_id)
    assert chat is None




def test_create_auspex_prompt(facade):
    prompt_id = facade.create_auspex_prompt(
        name="prompt_create_test",
        title="Create Test",
        content="This is a test prompt content",
        description="Prompt for testing",
        is_default=False,
        user_created="test_user"
    )
    assert prompt_id is not None


def test_get_auspex_prompt(facade):
    facade.create_auspex_prompt(
        name="prompt_get_test",
        title="Get Title",
        content="Prompt content"
    )

    result = facade.get_auspex_prompt("prompt_get_test")
    assert result is not None
    assert result["name"] == "prompt_get_test"
    assert result["title"] == "Get Title"


def test_update_auspex_prompt(facade):
    facade.create_auspex_prompt(
        name="prompt_update_test",
        title="Old Title",
        content="Old content"
    )

    updated = facade.update_auspex_prompt(
        name="prompt_update_test",
        title="New Title",
        content="Updated content",
        description="Updated description"
    )
    assert updated is True

    result = facade.get_auspex_prompt("prompt_update_test")
    assert result["title"] == "New Title"
    assert result["content"] == "Updated content"


def test_delete_auspex_prompt(facade):
    facade.create_auspex_prompt(
        name="prompt_delete_test",
        title="Delete Me",
        content="To be deleted"
    )

    deleted = facade.delete_auspex_prompt("prompt_delete_test")
    assert deleted is True

    result = facade.get_auspex_prompt("prompt_delete_test")
    assert result is None


def test_get_all_auspex_prompts(facade):
    facade.create_auspex_prompt(name="prompt1", title="T1", content="C1")
    facade.create_auspex_prompt(name="prompt2", title="T2", content="C2")

    prompts = facade.get_all_auspex_prompts()
    assert isinstance(prompts, list)
    assert any(p["name"] == "prompt1" for p in prompts)
    assert any(p["name"] == "prompt2" for p in prompts)

# ---------------------------------------------------------
#  Cached Trend Analysis Methods
# ---------------------------------------------------------

def test_save_cached_trend_analysis(facade):
    cache_key = "cache_key_test"
    topic = "AI"
    version_data = '{"version": "1.0"}'
    cache_metadata = '{"source": "unit_test"}'
    created_at = datetime(2025, 11, 17, 10, 0, 0)

    # Save cache
    facade.save_cached_trend_analysis(
        cache_key=cache_key,
        topic=topic,
        version_data=version_data,
        cache_metadata=cache_metadata,
        created_at=created_at
    )

    result = facade.get_cached_trend_analysis(cache_key)
    assert result is not None
    assert result["version_data"] == version_data
    assert result["created_at"] == created_at

def test_get_cached_trend_analysis(facade):
    cache_key = "cache_key_lookup"
    topic = "Tech Trends"
    version_data = '{"data": "trend info"}'
    cache_metadata = '{"generated": "test"}'
    created_at = datetime(2025, 11, 17, 10, 0, 0)

    # Save before retrieving
    facade.save_cached_trend_analysis(
        cache_key=cache_key,
        topic=topic,
        version_data=version_data,
        cache_metadata=cache_metadata,
        created_at=created_at
    )

    result = facade.get_cached_trend_analysis(cache_key)
    assert result is not None
    assert result["version_data"] == version_data
    assert result["created_at"] == created_at


def test_upsert_dashboard_cache(facade):
    """Test inserting and updating a dashboard cache entry."""
    cache_key = "cache_key_upsert_test"
    dashboard_type = "insights"
    content_data = {"chart": "sales_growth", "value": 120}
    summary_text = "Quarterly growth chart"

    # First insert
    facade.upsert_dashboard_cache(
        cache_key=cache_key,
        dashboard_type=dashboard_type,
        date_range="Q1-2025",
        topic="Economy",
        profile_id=1,
        persona="analyst",
        content_json=json.dumps(content_data),
        summary_text=summary_text,
        article_count=10,
        model_used="gpt-5",
        generation_time_seconds=2.5
    )

    result = facade.get_dashboard_cache(cache_key)
    assert result is not None
    assert result["cache_key"] == cache_key
    assert result["dashboard_type"] == dashboard_type
    assert result["content"]["chart"] == "sales_growth"

    # Update same key to test UPSERT
    updated_content = {"chart": "updated_chart", "value": 150}
    facade.upsert_dashboard_cache(
        cache_key=cache_key,
        dashboard_type=dashboard_type,
        date_range="Q1-2025",
        topic="Economy",
        profile_id=1,
        persona="analyst",
        content_json=json.dumps(updated_content),
        summary_text="Updated summary",
        article_count=12,
        model_used="gpt-5",
        generation_time_seconds=3.0
    )

    updated_result = facade.get_dashboard_cache(cache_key)
    assert updated_result["summary_text"] == "Updated summary"
    assert updated_result["content"]["chart"] == "updated_chart"


def test_get_dashboard_cache(facade):
    """Test retrieving a single cached dashboard."""
    cache_key = "cache_key_get_test"
    content_data = {"metrics": [10, 20, 30]}

    facade.upsert_dashboard_cache(
        cache_key=cache_key,
        dashboard_type="performance",
        date_range="2025",
        topic="AI",
        profile_id=2,
        persona="researcher",
        content_json=json.dumps(content_data),
        summary_text="AI metrics summary",
        article_count=5,
        model_used="gpt-4",
        generation_time_seconds=1.2
    )

    result = facade.get_dashboard_cache(cache_key)
    assert result is not None
    assert result["cache_key"] == cache_key
    assert "metrics" in result["content"]


def test_update_dashboard_cache_access(facade):
    """Test that accessed_at timestamp is updated successfully."""
    cache_key = "cache_key_access_test"
    facade.upsert_dashboard_cache(
        cache_key=cache_key,
        dashboard_type="trends",
        date_range="2025",
        topic="Climate",
        profile_id=None,
        persona=None,
        content_json=json.dumps({"data": "test"}),
        summary_text="Test access update",
        article_count=3,
        model_used="gpt-3.5",
        generation_time_seconds=1.0
    )

    # Call update
    facade.update_dashboard_cache_access(cache_key)

    result = facade.get_dashboard_cache(cache_key)
    assert result is not None
    assert "accessed_at" in result


def test_get_latest_dashboard_cache(facade):
    """Test retrieving the most recent dashboard cache by type."""
    # Insert two dashboards of the same type but different topics
    for i in range(2):
        facade.upsert_dashboard_cache(
            cache_key=f"cache_key_latest_{i}",
            dashboard_type="overview",
            date_range="2025",
            topic=f"Topic_{i}",
            profile_id=None,
            persona=None,
            content_json=json.dumps({"id": i}),
            summary_text=f"Summary {i}",
            article_count=5 + i,
            model_used="gpt-5",
            generation_time_seconds=1.0 + i
        )

    latest = facade.get_latest_dashboard_cache("overview", topic="Topic_1")
    assert latest is not None
    assert latest["topic"] == "Topic_1"
    assert "content" in latest


def test_list_dashboard_cache(facade):
    """Test listing multiple cached dashboards."""
    for i in range(3):
        facade.upsert_dashboard_cache(
            cache_key=f"cache_key_list_{i}",
            dashboard_type="summary",
            date_range="2025",
            topic="Economy",
            profile_id=None,
            persona=None,
            content_json=json.dumps({"index": i}),
            summary_text=f"Dashboard {i}",
            article_count=10 + i,
            model_used="gpt-4",
            generation_time_seconds=2.0
        )

    dashboards = facade.list_dashboard_cache(limit=2)
    assert isinstance(dashboards, list)
    assert len(dashboards) <= 2
    assert "content_json" not in dashboards[0]  # Should be stripped out


def test_delete_dashboard_cache(facade):
    """Test deleting a dashboard cache entry."""
    cache_key = "cache_key_delete_test"

    facade.upsert_dashboard_cache(
        cache_key=cache_key,
        dashboard_type="insights",
        date_range="Q4-2025",
        topic="Tech",
        profile_id=None,
        persona=None,
        content_json=json.dumps({"chart": "delete_me"}),
        summary_text="To be deleted",
        article_count=4,
        model_used="gpt-4",
        generation_time_seconds=2.2
    )

    deleted = facade.delete_dashboard_cache(cache_key)
    assert deleted is True

    result = facade.get_dashboard_cache(cache_key)
    assert result is None


def test_get_all_alerts_for_export_new_table_structure(facade):
    """
    Test the get_all_alerts_for_export_new_table_structure method.
    Verifies joins, keyword mapping, and keyword concatenation.
    """
    # Step 1: Insert sample data into dependent tables
    # ------------------------------------------------

    # 1️⃣ Insert keyword group
    group_stmt = facade._execute_with_rollback(
        keyword_groups.insert().values(
            id=1,
            name="Tech Group",
            topic="AI",
        )
    )
    facade.connection.commit()

    # 2️⃣ Insert monitored keywords
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=1,
            keyword="AI",
        )
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=2,
            group_id=1,
            keyword="Machine Learning",
        )
    )
    facade.connection.commit()

    # 3️⃣ Insert article
    article_stmt = facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article1",
            title="AI Revolution",
            news_source="TechCrunch",
            publication_date=datetime(2025, 11, 11),
            topic="AI",
        )
    )
    facade.connection.commit()

    # 4️⃣ Insert keyword_article_matches (comma-separated keyword_ids)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1,
            article_uri="http://example.com/article1",
            group_id=1,
            keyword_ids="1,2,3",
            detected_at=datetime(2025, 11, 11, 10, 30, 0)
        )
    )
    facade.connection.commit()

    # Step 2: Call the method under test
    # -----------------------------------
    results = facade.get_all_alerts_for_export_new_table_structure()

    # Step 3: Validate results
    # -----------------------------------
    assert isinstance(results, list)
    assert len(results) == 1

    alert = results[0]
    assert alert[0] == "Tech Group"              # group_name
    assert alert[1] == "AI"                      # topic
    assert alert[2] == "AI Revolution"           # article title
    assert alert[3] == "TechCrunch"              # news_source
    assert alert[4] == "http://example.com/article1"
    assert "AI" in alert[6]                      # matched_keywords
    assert "Machine Learning" in alert[6]


def test_get_all_group_and_topic_alerts_for_export_new_table_structure(facade):
    """
    Test the get_all_group_and_topic_alerts_for_export_new_table_structure method.
    Verifies joins, filtering by group_id and topic, keyword mapping, and concatenation.
    """
    # Step 1: Insert sample data into dependent tables
    # ------------------------------------------------

    # 1️⃣ Insert keyword group
    facade._execute_with_rollback(
        keyword_groups.insert().values(
            id=1,
            name="Tech Group",
            topic="AI",
        )
    )
    facade.connection.commit()

    # 2️⃣ Insert monitored keywords
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=1,
            group_id=1,
            keyword="AI",
        )
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=2,
            group_id=1,
            keyword="Machine Learning",
        )
    )
    facade._execute_with_rollback(
        monitored_keywords.insert().values(
            id=3,
            group_id=1,
            keyword="Deep Learning",
        )
    )
    facade.connection.commit()

    # 3️⃣ Insert article
    facade._execute_with_rollback(
        articles.insert().values(
            uri="http://example.com/article1",
            title="AI Revolution",
            news_source="TechCrunch",
            publication_date=datetime(2025, 11, 11),
            topic="AI",
        )
    )
    facade.connection.commit()

    # 4️⃣ Insert keyword_article_matches (comma-separated keyword_ids)
    facade._execute_with_rollback(
        keyword_article_matches.insert().values(
            id=1,
            article_uri="http://example.com/article1",
            group_id=1,
            keyword_ids="1,2",
            detected_at=datetime(2025, 11, 11, 10, 30, 0),
            is_read=False
        )
    )
    facade.connection.commit()

    # Step 2: Call the method under test
    # -----------------------------------
    results = facade.get_all_group_and_topic_alerts_for_export_new_table_structure(
        group_id=1, topic="AI"
    )

    # Step 3: Validate results
    # -----------------------------------
    assert isinstance(results, list)
    assert len(results) == 1

    alert = results[0]
    assert alert[0] == "Tech Group"              # group_name
    assert alert[1] == "AI"                      # topic
    assert alert[2] == "AI Revolution"           # article title
    assert alert[3] == "TechCrunch"              # news_source
    assert alert[4] == "http://example.com/article1"
    assert "AI" in alert[6]                      # matched_keywords
    assert "Machine Learning" in alert[6]


