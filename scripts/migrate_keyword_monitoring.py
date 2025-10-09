#!/usr/bin/env python3
"""
Migrate keyword monitoring data from SQLite to PostgreSQL
"""
import sqlite3
import logging
from sqlalchemy import text
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_keyword_monitoring():
    """Migrate keyword monitoring data from SQLite to PostgreSQL"""

    # Connect to SQLite
    sqlite_path = 'app/data/fnaapp.db'
    logger.info(f"Connecting to SQLite: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Connect to PostgreSQL
    logger.info("Connecting to PostgreSQL")
    db = Database()
    pg_conn = db._temp_get_connection()

    try:
        # Migrate keyword_monitor_settings
        logger.info("Migrating keyword_monitor_settings...")
        sqlite_cursor.execute("SELECT * FROM keyword_monitor_settings")
        settings = sqlite_cursor.fetchall()
        for row in settings:
            row_dict = dict(row)
            # Convert integer booleans to actual booleans for PostgreSQL
            if 'is_enabled' in row_dict:
                row_dict['is_enabled'] = bool(row_dict['is_enabled'])
            if 'auto_ingest_enabled' in row_dict:
                row_dict['auto_ingest_enabled'] = bool(row_dict['auto_ingest_enabled'])
            if 'quality_control_enabled' in row_dict:
                row_dict['quality_control_enabled'] = bool(row_dict['quality_control_enabled'])
            if 'auto_save_approved_only' in row_dict:
                row_dict['auto_save_approved_only'] = bool(row_dict['auto_save_approved_only'])

            pg_conn.execute(text("""
                INSERT INTO keyword_monitor_settings (
                    id, check_interval, interval_unit, search_date_range,
                    daily_request_limit, is_enabled, provider, search_fields,
                    language, sort_by, page_size, auto_ingest_enabled,
                    min_relevance_threshold, quality_control_enabled,
                    auto_save_approved_only, default_llm_model,
                    llm_temperature, llm_max_tokens
                ) VALUES (
                    :id, :check_interval, :interval_unit, :search_date_range,
                    :daily_request_limit, :is_enabled, :provider, :search_fields,
                    :language, :sort_by, :page_size, :auto_ingest_enabled,
                    :min_relevance_threshold, :quality_control_enabled,
                    :auto_save_approved_only, :default_llm_model,
                    :llm_temperature, :llm_max_tokens
                )
                ON CONFLICT (id) DO UPDATE SET
                    check_interval = EXCLUDED.check_interval,
                    interval_unit = EXCLUDED.interval_unit,
                    search_date_range = EXCLUDED.search_date_range,
                    daily_request_limit = EXCLUDED.daily_request_limit,
                    is_enabled = EXCLUDED.is_enabled,
                    provider = EXCLUDED.provider,
                    search_fields = EXCLUDED.search_fields,
                    language = EXCLUDED.language,
                    sort_by = EXCLUDED.sort_by,
                    page_size = EXCLUDED.page_size,
                    auto_ingest_enabled = EXCLUDED.auto_ingest_enabled,
                    min_relevance_threshold = EXCLUDED.min_relevance_threshold,
                    quality_control_enabled = EXCLUDED.quality_control_enabled,
                    auto_save_approved_only = EXCLUDED.auto_save_approved_only,
                    default_llm_model = EXCLUDED.default_llm_model,
                    llm_temperature = EXCLUDED.llm_temperature,
                    llm_max_tokens = EXCLUDED.llm_max_tokens
            """), row_dict)
        pg_conn.commit()
        logger.info(f"Migrated {len(settings)} keyword_monitor_settings rows")

        # Migrate keyword_monitor_status
        logger.info("Migrating keyword_monitor_status...")
        sqlite_cursor.execute("SELECT * FROM keyword_monitor_status")
        statuses = sqlite_cursor.fetchall()
        for row in statuses:
            pg_conn.execute(text("""
                INSERT INTO keyword_monitor_status (
                    id, last_check_time, last_error, requests_today, last_reset_date
                ) VALUES (
                    :id, :last_check_time, :last_error, :requests_today, :last_reset_date
                )
                ON CONFLICT (id) DO UPDATE SET
                    last_check_time = EXCLUDED.last_check_time,
                    last_error = EXCLUDED.last_error,
                    requests_today = EXCLUDED.requests_today,
                    last_reset_date = EXCLUDED.last_reset_date
            """), dict(row))
        pg_conn.commit()
        logger.info(f"Migrated {len(statuses)} keyword_monitor_status rows")

        # Migrate keyword_groups
        logger.info("Migrating keyword_groups...")
        sqlite_cursor.execute("SELECT * FROM keyword_groups")
        groups = sqlite_cursor.fetchall()

        # Get provider from settings to use as default
        sqlite_cursor.execute("SELECT provider FROM keyword_monitor_settings LIMIT 1")
        default_provider = sqlite_cursor.fetchone()
        default_provider = default_provider[0] if default_provider else 'newsdata'

        for row in groups:
            row_dict = dict(row)
            # Add default values for columns that don't exist in SQLite
            row_dict['provider'] = default_provider
            row_dict['source'] = default_provider  # Use same value for both

            pg_conn.execute(text("""
                INSERT INTO keyword_groups (
                    id, name, topic, created_at, provider, source
                ) VALUES (
                    :id, :name, :topic, :created_at, :provider, :source
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    topic = EXCLUDED.topic,
                    created_at = EXCLUDED.created_at,
                    provider = EXCLUDED.provider,
                    source = EXCLUDED.source
            """), row_dict)
        pg_conn.commit()
        logger.info(f"Migrated {len(groups)} keyword_groups rows")

        # Migrate monitored_keywords
        logger.info("Migrating monitored_keywords...")
        sqlite_cursor.execute("SELECT * FROM monitored_keywords")
        keywords = sqlite_cursor.fetchall()
        for row in keywords:
            pg_conn.execute(text("""
                INSERT INTO monitored_keywords (
                    id, group_id, keyword, created_at, last_checked
                ) VALUES (
                    :id, :group_id, :keyword, :created_at, :last_checked
                )
                ON CONFLICT (id) DO UPDATE SET
                    group_id = EXCLUDED.group_id,
                    keyword = EXCLUDED.keyword,
                    created_at = EXCLUDED.created_at,
                    last_checked = EXCLUDED.last_checked
            """), dict(row))
        pg_conn.commit()
        logger.info(f"Migrated {len(keywords)} monitored_keywords rows")

        # Migrate keyword_alerts (old structure)
        logger.info("Migrating keyword_alerts...")
        sqlite_cursor.execute("SELECT * FROM keyword_alerts")
        alerts = sqlite_cursor.fetchall()
        migrated_alerts = 0
        skipped_alerts = 0
        for row in alerts:
            row_dict = dict(row)
            # Check if article exists in PostgreSQL
            article_check = pg_conn.execute(text(
                "SELECT COUNT(*) FROM articles WHERE uri = :uri"
            ), {"uri": row_dict['article_uri']}).scalar()

            if article_check > 0:
                pg_conn.execute(text("""
                    INSERT INTO keyword_alerts (
                        id, keyword_id, article_uri, detected_at, is_read
                    ) VALUES (
                        :id, :keyword_id, :article_uri, :detected_at, :is_read
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        keyword_id = EXCLUDED.keyword_id,
                        article_uri = EXCLUDED.article_uri,
                        detected_at = EXCLUDED.detected_at,
                        is_read = EXCLUDED.is_read
                """), row_dict)
                migrated_alerts += 1
            else:
                skipped_alerts += 1
        pg_conn.commit()
        logger.info(f"Migrated {migrated_alerts} keyword_alerts rows (skipped {skipped_alerts} with missing articles)")

        # Migrate keyword_article_matches (new structure)
        logger.info("Migrating keyword_article_matches...")
        sqlite_cursor.execute("SELECT * FROM keyword_article_matches")
        matches = sqlite_cursor.fetchall()
        migrated_matches = 0
        skipped_matches = 0
        for row in matches:
            row_dict = dict(row)
            # Check if article exists in PostgreSQL
            article_check = pg_conn.execute(text(
                "SELECT COUNT(*) FROM articles WHERE uri = :uri"
            ), {"uri": row_dict['article_uri']}).scalar()

            if article_check > 0:
                pg_conn.execute(text("""
                    INSERT INTO keyword_article_matches (
                        id, article_uri, keyword_ids, group_id, detected_at, is_read
                    ) VALUES (
                        :id, :article_uri, :keyword_ids, :group_id, :detected_at, :is_read
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        article_uri = EXCLUDED.article_uri,
                        keyword_ids = EXCLUDED.keyword_ids,
                        group_id = EXCLUDED.group_id,
                        detected_at = EXCLUDED.detected_at,
                        is_read = EXCLUDED.is_read
                """), row_dict)
                migrated_matches += 1
            else:
                skipped_matches += 1
        pg_conn.commit()
        logger.info(f"Migrated {migrated_matches} keyword_article_matches rows (skipped {skipped_matches} with missing articles)")

        logger.info("✅ Keyword monitoring data migration completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error during migration: {str(e)}")
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    migrate_keyword_monitoring()
