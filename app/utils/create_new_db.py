import sqlite3
import os
import logging
from pathlib import Path
import bcrypt
from typing import Optional
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseCreator:
    def __init__(self, db_path: str):
        """
        Initialize the database creator.
        
        Args:
            db_path (str): Path to the database file
        """
        self.db_path = db_path
        self.db_dir = Path(db_path).parent

    def create_database(self) -> None:
        """
        Create a new database from scratch with all required tables.
        """
        try:
            logger.info("Starting database creation...")

            # Remove existing database if it exists
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

            # Create default admin user
            self._create_admin_user(cursor)

            # Create default keyword monitor settings
            self._create_default_settings(cursor)

            conn.commit()
            conn.close()
            logger.info("Database created successfully")

        except Exception as e:
            logger.error(f"Error creating database: {str(e)}")
            raise

    def _create_admin_user(self, cursor: sqlite3.Cursor) -> None:
        """Create the default admin user with password 'admin'."""
        try:
            # Hash the password 'admin'
            password = "admin"
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            
            # Insert admin user
            cursor.execute("""
                INSERT INTO users (username, password_hash, force_password_change, completed_onboarding)
                VALUES (?, ?, ?, ?)
            """, ("admin", password_hash.decode('utf-8'), 1, 0))
            
            logger.info("Created admin user with password 'admin'")
        except Exception as e:
            logger.error(f"Error creating admin user: {str(e)}")
            raise

    def _create_default_settings(self, cursor: sqlite3.Cursor) -> None:
        """Create default keyword monitor settings and status."""
        try:
            # Insert default settings
            cursor.execute("""
                INSERT INTO keyword_monitor_settings (
                    id, check_interval, interval_unit, search_fields, language,
                    sort_by, page_size, is_enabled, daily_request_limit, search_date_range
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                1, 15, 3600, 'title,description,content', 'en',
                'publishedAt', 10, 1, 100, 7
            ))
            
            # Insert default status
            cursor.execute("""
                INSERT INTO keyword_monitor_status (
                    id, last_check_time, last_error, requests_today, last_reset_date
                ) VALUES (?, ?, ?, ?, ?)
            """, (1, None, None, 0, None))
            
            logger.info("Created default keyword monitor settings and status")
        except Exception as e:
            logger.error(f"Error creating default settings: {str(e)}")
            raise

def main():
    """Main function to create a new database."""
    parser = argparse.ArgumentParser(description='Create a new database with all required tables.')
    parser.add_argument('--db-path', type=str, required=True, help='Path to the database file')
    args = parser.parse_args()
    
    creator = DatabaseCreator(args.db_path)
    creator.create_database()

if __name__ == "__main__":
    main() 