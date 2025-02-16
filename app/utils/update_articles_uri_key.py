import sqlite3
import os
import json
import logging
from datetime import datetime
from config.settings import DATABASE_DIR

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_active_database():
    config_path = os.path.join('data', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config.get('active_database', 'fnaapp.db')

def update_articles_uri_key():
    """Update articles table to have URI as primary key and remove duplicates"""
    db_path = os.path.join(DATABASE_DIR, get_active_database())
    logger.info(f"Updating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Begin transaction
        cursor.execute("BEGIN IMMEDIATE")
        
        # Get current row count
        cursor.execute("SELECT COUNT(*) FROM articles")
        old_count = cursor.fetchone()[0]
        logger.info(f"Current number of articles: {old_count}")

        # Create new table with correct schema
        cursor.execute("""
            CREATE TABLE articles_new (
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
            )
        """)
        
        # Copy data, keeping only the most recent entry for each URI
        cursor.execute("""
            INSERT INTO articles_new 
            SELECT 
                uri,
                title,
                news_source,
                publication_date,
                MAX(submission_date),
                summary,
                category,
                future_signal,
                future_signal_explanation,
                sentiment,
                sentiment_explanation,
                time_to_impact,
                time_to_impact_explanation,
                tags,
                driver_type,
                driver_type_explanation,
                topic,
                analyzed
            FROM articles
            GROUP BY uri
        """)
        
        # Get new count
        cursor.execute("SELECT COUNT(*) FROM articles_new")
        new_count = cursor.fetchone()[0]
        duplicates_removed = old_count - new_count
        logger.info(f"Removed {duplicates_removed} duplicate articles")
        
        # Backup old table just in case
        backup_name = f"articles_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute(f"ALTER TABLE articles RENAME TO {backup_name}")
        logger.info(f"Backed up old table as {backup_name}")
        
        # Rename new table
        cursor.execute("ALTER TABLE articles_new RENAME TO articles")
        
        # Create index on uri
        cursor.execute("CREATE UNIQUE INDEX idx_articles_uri ON articles(uri)")
        
        # Update any related foreign keys
        cursor.execute("PRAGMA foreign_key_list('keyword_alerts')")
        fk_info = cursor.fetchall()
        logger.info("Checking foreign key constraints...")
        
        # Check for any orphaned keyword alerts
        cursor.execute("""
            DELETE FROM keyword_alerts 
            WHERE article_uri NOT IN (SELECT uri FROM articles)
        """)
        orphans_removed = cursor.rowcount
        logger.info(f"Removed {orphans_removed} orphaned keyword alerts")
        
        # Commit changes
        conn.commit()
        logger.info("Database update completed successfully")
        logger.info(f"Summary:")
        logger.info(f"- Original articles: {old_count}")
        logger.info(f"- Articles after deduplication: {new_count}")
        logger.info(f"- Duplicate entries removed: {duplicates_removed}")
        logger.info(f"- Orphaned alerts removed: {orphans_removed}")
        
    except sqlite3.Error as e:
        logger.error(f"An error occurred: {e}")
        conn.rollback()
        raise
        
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        update_articles_uri_key()
    except Exception as e:
        logger.error(f"Script failed: {e}")
        exit(1) 