#!/usr/bin/env python3

import sys
import sqlite3
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.append('.')

from app.database import Database
from app.config.settings import DATABASE_DIR

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def add_auto_ingest_columns():
    """Add missing auto-ingest columns to the database"""
    try:
        # Get the database instance
        db = Database()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            logger.info("Checking and adding missing auto-ingest columns...")
            
            # Check and add columns to keyword_monitor_settings table
            settings_columns = [
                ('auto_ingest_enabled', 'BOOLEAN NOT NULL DEFAULT FALSE'),
                ('min_relevance_threshold', 'REAL NOT NULL DEFAULT 0.0'),
                ('quality_control_enabled', 'BOOLEAN NOT NULL DEFAULT TRUE'),
                ('auto_save_approved_only', 'BOOLEAN NOT NULL DEFAULT FALSE'),
                ('default_llm_model', 'TEXT NOT NULL DEFAULT "gpt-4o-mini"'),
                ('llm_temperature', 'REAL NOT NULL DEFAULT 0.1'),
                ('llm_max_tokens', 'INTEGER NOT NULL DEFAULT 1000')
            ]
            
            for column_name, column_def in settings_columns:
                if not check_column_exists(cursor, 'keyword_monitor_settings', column_name):
                    sql = f"ALTER TABLE keyword_monitor_settings ADD COLUMN {column_name} {column_def}"
                    logger.info(f"Adding column: {column_name} to keyword_monitor_settings")
                    cursor.execute(sql)
                else:
                    logger.info(f"Column {column_name} already exists in keyword_monitor_settings")
            
            # Check and add columns to articles table
            articles_columns = [
                ('ingest_status', 'TEXT DEFAULT "manual"'),
                ('quality_score', 'REAL'),
                ('quality_issues', 'TEXT'),
                ('auto_ingested', 'BOOLEAN DEFAULT FALSE')
            ]
            
            for column_name, column_def in articles_columns:
                if not check_column_exists(cursor, 'articles', column_name):
                    sql = f"ALTER TABLE articles ADD COLUMN {column_name} {column_def}"
                    logger.info(f"Adding column: {column_name} to articles")
                    cursor.execute(sql)
                else:
                    logger.info(f"Column {column_name} already exists in articles")
            
            # Create indexes for new fields
            indexes = [
                ("idx_articles_ingest_status", "articles", "ingest_status"),
                ("idx_articles_auto_ingested", "articles", "auto_ingested"),
                ("idx_articles_quality_score", "articles", "quality_score")
            ]
            
            for index_name, table_name, column_name in indexes:
                try:
                    sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"
                    cursor.execute(sql)
                    logger.info(f"Created index: {index_name}")
                except Exception as e:
                    logger.warning(f"Could not create index {index_name}: {e}")
            
            # Commit all changes
            conn.commit()
            logger.info("✅ Auto-ingest migration completed successfully!")
            
            # Verify the columns were added
            logger.info("\nVerifying columns were added:")
            cursor.execute("PRAGMA table_info(articles)")
            articles_columns = [row[1] for row in cursor.fetchall()]
            
            required_columns = ['ingest_status', 'quality_score', 'quality_issues', 'auto_ingested']
            for col in required_columns:
                if col in articles_columns:
                    logger.info(f"✅ articles.{col} - EXISTS")
                else:
                    logger.error(f"❌ articles.{col} - MISSING")
            
            cursor.execute("PRAGMA table_info(keyword_monitor_settings)")
            settings_columns = [row[1] for row in cursor.fetchall()]
            
            required_settings = ['auto_ingest_enabled', 'min_relevance_threshold', 'quality_control_enabled']
            for col in required_settings:
                if col in settings_columns:
                    logger.info(f"✅ keyword_monitor_settings.{col} - EXISTS")
                else:
                    logger.error(f"❌ keyword_monitor_settings.{col} - MISSING")
                    
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    add_auto_ingest_columns() 