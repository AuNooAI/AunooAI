import sqlite3
import os
import shutil
from pathlib import Path
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str):
        """
        Initialize the database manager.
        
        Args:
            db_path (str): Path to the database file
        """
        self.db_path = db_path
        self.backup_path = f"{db_path}.backup"
        self.db_dir = Path(db_path).parent

    def _create_backup(self) -> None:
        """Create a backup of the existing database."""
        if os.path.exists(self.db_path):
            shutil.copy2(self.db_path, self.backup_path)
            logger.info(f"Created backup at {self.backup_path}")

    def _restore_backup(self) -> None:
        """Restore the database from backup if something goes wrong."""
        if os.path.exists(self.backup_path):
            shutil.copy2(self.backup_path, self.db_path)
            logger.info(f"Restored database from backup {self.backup_path}")

    def _cleanup_backup(self) -> None:
        """Remove the backup file after successful operation."""
        if os.path.exists(self.backup_path):
            os.remove(self.backup_path)
            logger.info("Cleaned up backup file")

    def rebuild_database(self) -> None:
        """
        Rebuild the database from scratch.
        This will delete the existing database and create a new one with all required tables.
        """
        try:
            logger.info("Starting database rebuild...")
            self._create_backup()

            # Remove existing database
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
                logger.info(f"Removed existing database {self.db_path}")

            # Create new database connection
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            # Create tables
            cursor.executescript("""
                -- Articles table
                CREATE TABLE IF NOT EXISTS articles (
                    uri TEXT PRIMARY KEY,
                    title TEXT,
                    news_source TEXT,
                    publication_date TEXT,
                    submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    summary TEXT,
                    category TEXT,
                    future_signal TEXT,
                    future_signal_explanation TEXT,
                    sentiment TEXT,
                    sentiment_explanation TEXT,
                    time_to_impact TEXT,
                    time_to_impact_explanation TEXT,
                    tags TEXT,
                    driver_type TEXT,
                    driver_type_explanation TEXT,
                    topic TEXT,
                    analyzed BOOLEAN DEFAULT FALSE
                );

                -- Raw articles table
                CREATE TABLE IF NOT EXISTS raw_articles (
                    uri TEXT PRIMARY KEY,
                    raw_markdown TEXT,
                    submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_updated TEXT,
                    topic TEXT,
                    FOREIGN KEY (uri) REFERENCES articles(uri) ON DELETE CASCADE
                );

                -- Keyword groups table
                CREATE TABLE IF NOT EXISTS keyword_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    topic TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Monitored keywords table
                CREATE TABLE IF NOT EXISTS monitored_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_checked TEXT,
                    FOREIGN KEY (group_id) REFERENCES keyword_groups(id) ON DELETE CASCADE,
                    UNIQUE(group_id, keyword)
                );

                -- Keyword alerts table
                CREATE TABLE IF NOT EXISTS keyword_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword_id INTEGER NOT NULL,
                    article_uri TEXT NOT NULL,
                    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_read INTEGER DEFAULT 0,
                    FOREIGN KEY (keyword_id) REFERENCES monitored_keywords(id) ON DELETE CASCADE,
                    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                    UNIQUE(keyword_id, article_uri)
                );

                -- Keyword article matches table
                CREATE TABLE IF NOT EXISTS keyword_article_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_uri TEXT NOT NULL,
                    keyword_ids TEXT NOT NULL,
                    group_id INTEGER NOT NULL,
                    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_read INTEGER DEFAULT 0,
                    below_threshold INTEGER DEFAULT 0,
                    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES keyword_groups(id) ON DELETE CASCADE,
                    UNIQUE(article_uri, group_id)
                );

                -- Keyword monitor settings table
                CREATE TABLE IF NOT EXISTS keyword_monitor_settings (
                    id INTEGER PRIMARY KEY,
                    check_interval INTEGER NOT NULL DEFAULT 15,
                    interval_unit INTEGER NOT NULL DEFAULT 60,
                    search_fields TEXT NOT NULL DEFAULT 'title,description,content',
                    language TEXT NOT NULL DEFAULT 'en',
                    sort_by TEXT NOT NULL DEFAULT 'publishedAt',
                    page_size INTEGER NOT NULL DEFAULT 10,
                    is_enabled BOOLEAN NOT NULL DEFAULT 1,
                    daily_request_limit INTEGER NOT NULL DEFAULT 100,
                    search_date_range INTEGER NOT NULL DEFAULT 7,
                    provider TEXT DEFAULT 'newsapi',
                    auto_ingest_enabled BOOLEAN DEFAULT 0,
                    min_relevance_threshold REAL DEFAULT 0.0,
                    quality_control_enabled BOOLEAN DEFAULT 1,
                    auto_save_approved_only BOOLEAN DEFAULT 0,
                    default_llm_model TEXT DEFAULT 'gpt-4o-mini',
                    llm_temperature REAL DEFAULT 0.1,
                    llm_max_tokens INTEGER DEFAULT 1000,
                    max_articles_per_run INTEGER DEFAULT 50
                );

                -- Keyword monitor status table
                CREATE TABLE IF NOT EXISTS keyword_monitor_status (
                    id INTEGER PRIMARY KEY,
                    last_check_time TEXT,
                    last_error TEXT,
                    requests_today INTEGER DEFAULT 0,
                    last_reset_date TEXT
                );

                -- Users table
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    force_password_change BOOLEAN DEFAULT 0,
                    completed_onboarding BOOLEAN DEFAULT 0
                );

                -- Article annotations table
                CREATE TABLE IF NOT EXISTS article_annotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_uri TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    is_private BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE
                );

                -- Migrations table
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.commit()
            conn.close()
            logger.info("Database rebuilt successfully")
            self._cleanup_backup()

        except Exception as e:
            logger.error(f"Error rebuilding database: {str(e)}")
            self._restore_backup()
            raise

    def update_schema(self) -> None:
        """
        Update the existing database schema to the latest version.
        This will preserve existing data while adding new tables and columns.
        """
        try:
            logger.info("Starting schema update...")
            self._create_backup()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            # Get current schema
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = {row[0] for row in cursor.fetchall()}

            # Create migrations table if it doesn't exist
            if 'migrations' not in existing_tables:
                cursor.execute("""
                    CREATE TABLE migrations (
                        id INTEGER PRIMARY KEY,
                        name TEXT UNIQUE,
                        applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()

            # Get applied migrations
            cursor.execute("SELECT name FROM migrations")
            applied_migrations = {row[0] for row in cursor.fetchall()}

            # Define migrations - only keeping those that might be needed for legacy databases
            migrations = [
                ("fix_duplicate_alerts", self._fix_duplicate_alerts),
                ("ensure_completed_onboarding", self._ensure_completed_onboarding),
                ("add_below_threshold_column", self._add_below_threshold_column),
            ]

            # Apply missing migrations
            for name, migrate_func in migrations:
                if name not in applied_migrations:
                    logger.info(f"Applying migration: {name}")
                    migrate_func(cursor)
                    cursor.execute("INSERT INTO migrations (name) VALUES (?)", (name,))
                    conn.commit()

            conn.close()
            logger.info("Schema updated successfully")
            self._cleanup_backup()

        except Exception as e:
            logger.error(f"Error updating schema: {str(e)}")
            self._restore_backup()
            raise

    def _fix_duplicate_alerts(self, cursor):
        """Remove duplicate alerts and ensure the unique constraint exists."""
        try:
            # Check if the unique constraint exists
            cursor.execute("""
                SELECT sql FROM sqlite_master 
                WHERE type='table' AND name='keyword_alerts'
            """)
            table_def = cursor.fetchone()[0]
            
            # If the unique constraint is missing, we need to recreate the table
            if "UNIQUE(keyword_id, article_uri)" not in table_def:
                logger.info("Fixing keyword_alerts table: adding unique constraint")
                
                # Create a temporary table with the correct schema
                cursor.execute("""
                    CREATE TABLE keyword_alerts_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword_id INTEGER NOT NULL,
                        article_uri TEXT NOT NULL,
                        detected_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        is_read INTEGER DEFAULT 0,
                        FOREIGN KEY (keyword_id) REFERENCES monitored_keywords(id) ON DELETE CASCADE,
                        FOREIGN KEY (article_uri) REFERENCES articles(uri) ON DELETE CASCADE,
                        UNIQUE(keyword_id, article_uri)
                    )
                """)
                
                # Copy data to the temporary table, keeping only one row per keyword_id/article_uri pair
                cursor.execute("""
                    INSERT OR IGNORE INTO keyword_alerts_temp (keyword_id, article_uri, detected_at, is_read)
                    SELECT keyword_id, article_uri, MIN(detected_at), MIN(is_read)
                    FROM keyword_alerts
                    GROUP BY keyword_id, article_uri
                """)
                
                # Drop the old table and rename the temporary one
                cursor.execute("DROP TABLE keyword_alerts")
                cursor.execute("ALTER TABLE keyword_alerts_temp RENAME TO keyword_alerts")
                
                logger.info("Fixed duplicate alerts in keyword_alerts table")
        except Exception as e:
            logger.error(f"Error fixing duplicate alerts: {str(e)}")
            raise

    def _ensure_completed_onboarding(self, cursor):
        """Ensure the completed_onboarding column exists in the users table."""
        try:
            # First check if the users table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                logger.info("Creating users table with completed_onboarding column")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        force_password_change BOOLEAN DEFAULT 0,
                        completed_onboarding BOOLEAN DEFAULT 0
                    )
                """)
                return
                
            # Check if the column exists
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'completed_onboarding' not in columns:
                logger.info("Adding completed_onboarding column to users table")
                cursor.execute("ALTER TABLE users ADD COLUMN completed_onboarding BOOLEAN DEFAULT 0")
                
        except Exception as e:
            logger.error(f"Error ensuring completed_onboarding column: {str(e)}")
            raise

    def _add_below_threshold_column(self, cursor):
        """Add below_threshold column to keyword_article_matches table."""
        try:
            # Check if the column exists
            cursor.execute("PRAGMA table_info(keyword_article_matches)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'below_threshold' not in columns:
                logger.info("Adding below_threshold column to keyword_article_matches table")
                cursor.execute("ALTER TABLE keyword_article_matches ADD COLUMN below_threshold INTEGER DEFAULT 0")

        except Exception as e:
            logger.error(f"Error adding below_threshold column: {str(e)}")
            raise

def main():
    """Main function to run database management operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Manage database operations.')
    parser.add_argument('--db-path', type=str, required=True, help='Path to the database file')
    parser.add_argument('--operation', type=str, choices=['rebuild', 'update'], required=True, 
                        help='Operation to perform: rebuild or update')
    args = parser.parse_args()
    
    db_manager = DatabaseManager(args.db_path)
    
    if args.operation == 'rebuild':
        db_manager.rebuild_database()
    elif args.operation == 'update':
        db_manager.update_schema()

if __name__ == "__main__":
    main() 