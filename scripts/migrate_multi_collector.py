#!/usr/bin/env python
"""
Migration script to add multi-collector support to keyword monitoring.
Adds 'providers' JSON array column and migrates existing 'provider' values.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_multi_collector():
    """Add providers column and migrate existing data"""
    db = get_database_instance()

    try:
        logger.info("Starting multi-collector migration...")

        # Check if column already exists
        conn = db._temp_get_connection()

        # For SQLite
        if db.db_type == 'sqlite':
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE name='keyword_monitor_settings'"
            )
            schema = cursor.fetchone()
            if schema and 'providers' in schema[0]:
                logger.info("Column 'providers' already exists. Migration not needed.")
                return True

            logger.info("Adding 'providers' column to keyword_monitor_settings...")
            cursor.execute("""
                ALTER TABLE keyword_monitor_settings
                ADD COLUMN providers TEXT DEFAULT '["newsapi"]'
            """)
            conn.commit()
            logger.info("Column added successfully")

            # Migrate existing data
            logger.info("Migrating existing provider data...")
            cursor.execute("""
                UPDATE keyword_monitor_settings
                SET providers = json_array(provider)
                WHERE provider IS NOT NULL
            """)
            conn.commit()
            logger.info(f"Migrated {cursor.rowcount} row(s)")

        # For PostgreSQL
        elif db.db_type == 'postgresql':
            cursor = conn.cursor()
            # Check if column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='keyword_monitor_settings'
                AND column_name='providers'
            """)
            if cursor.fetchone():
                logger.info("Column 'providers' already exists. Migration not needed.")
                return True

            logger.info("Adding 'providers' column to keyword_monitor_settings...")
            cursor.execute("""
                ALTER TABLE keyword_monitor_settings
                ADD COLUMN providers TEXT DEFAULT '["newsapi"]'
            """)
            conn.commit()
            logger.info("Column added successfully")

            # Migrate existing data (PostgreSQL JSON syntax)
            logger.info("Migrating existing provider data...")
            cursor.execute("""
                UPDATE keyword_monitor_settings
                SET providers = json_build_array(provider)::text
                WHERE provider IS NOT NULL
            """)
            conn.commit()
            logger.info(f"Migrated {cursor.rowcount} row(s)")

        else:
            logger.error(f"Unsupported database type: {db.db_type}")
            return False

        cursor.close()
        conn.close()

        logger.info("Multi-collector migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate_multi_collector()
    sys.exit(0 if success else 1)
