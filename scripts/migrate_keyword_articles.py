#!/usr/bin/env python3
"""
Migrate articles referenced by keyword monitoring from SQLite to PostgreSQL
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

def migrate_keyword_articles():
    """Migrate articles referenced by keyword monitoring from SQLite to PostgreSQL"""

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
        # Get unique article URIs from keyword_article_matches
        logger.info("Getting article URIs from keyword_article_matches...")
        sqlite_cursor.execute("""
            SELECT DISTINCT article_uri FROM keyword_article_matches
        """)
        article_uris = [row[0] for row in sqlite_cursor.fetchall()]
        logger.info(f"Found {len(article_uris)} unique article URIs in keyword_article_matches")

        # Get unique article URIs from keyword_alerts (old structure)
        logger.info("Getting article URIs from keyword_alerts...")
        sqlite_cursor.execute("""
            SELECT DISTINCT article_uri FROM keyword_alerts
        """)
        alert_uris = [row[0] for row in sqlite_cursor.fetchall()]
        logger.info(f"Found {len(alert_uris)} unique article URIs in keyword_alerts")

        # Combine and deduplicate
        all_uris = list(set(article_uris + alert_uris))
        logger.info(f"Total unique article URIs to migrate: {len(all_uris)}")

        # Migrate articles
        migrated_count = 0
        skipped_count = 0

        for uri in all_uris:
            # Get article from SQLite
            sqlite_cursor.execute("SELECT * FROM articles WHERE uri = ?", (uri,))
            article = sqlite_cursor.fetchone()

            if not article:
                logger.warning(f"Article not found in SQLite: {uri}")
                skipped_count += 1
                continue

            article_dict = dict(article)

            # Convert boolean columns from integer (SQLite) to boolean (PostgreSQL)
            boolean_columns = ['analyzed', 'auto_ingested']
            for col in boolean_columns:
                if col in article_dict and article_dict[col] is not None:
                    article_dict[col] = bool(article_dict[col])

            # Check if article already exists in PostgreSQL
            existing = pg_conn.execute(text(
                "SELECT COUNT(*) FROM articles WHERE uri = :uri"
            ), {"uri": uri}).scalar()

            if existing > 0:
                logger.debug(f"Article already exists in PostgreSQL: {uri}")
                continue

            # Build column list dynamically from article_dict keys
            columns = ', '.join(article_dict.keys())
            placeholders = ', '.join(f':{key}' for key in article_dict.keys())

            # Insert into PostgreSQL
            pg_conn.execute(text(f"""
                INSERT INTO articles ({columns})
                VALUES ({placeholders})
            """), article_dict)
            migrated_count += 1

            if migrated_count % 10 == 0:
                logger.info(f"Progress: {migrated_count} articles migrated...")

        pg_conn.commit()
        logger.info(f"✅ Migrated {migrated_count} articles (skipped {skipped_count})")

        # Now re-run keyword_alerts migration with existing articles
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
                # Check if alert already exists
                existing_alert = pg_conn.execute(text(
                    "SELECT COUNT(*) FROM keyword_alerts WHERE id = :id"
                ), {"id": row_dict['id']}).scalar()

                if existing_alert == 0:
                    pg_conn.execute(text("""
                        INSERT INTO keyword_alerts (
                            id, keyword_id, article_uri, detected_at, is_read
                        ) VALUES (
                            :id, :keyword_id, :article_uri, :detected_at, :is_read
                        )
                    """), row_dict)
                    migrated_alerts += 1
            else:
                skipped_alerts += 1

        pg_conn.commit()
        logger.info(f"✅ Migrated {migrated_alerts} keyword_alerts (skipped {skipped_alerts})")

        # Migrate keyword_article_matches
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
                # Check if match already exists
                existing_match = pg_conn.execute(text(
                    "SELECT COUNT(*) FROM keyword_article_matches WHERE id = :id"
                ), {"id": row_dict['id']}).scalar()

                if existing_match == 0:
                    pg_conn.execute(text("""
                        INSERT INTO keyword_article_matches (
                            id, article_uri, keyword_ids, group_id, detected_at, is_read
                        ) VALUES (
                            :id, :article_uri, :keyword_ids, :group_id, :detected_at, :is_read
                        )
                    """), row_dict)
                    migrated_matches += 1
            else:
                skipped_matches += 1

        pg_conn.commit()
        logger.info(f"✅ Migrated {migrated_matches} keyword_article_matches (skipped {skipped_matches})")

        logger.info("✅ Article migration completed successfully!")

    except Exception as e:
        logger.error(f"❌ Error during migration: {str(e)}")
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()

if __name__ == "__main__":
    migrate_keyword_articles()
