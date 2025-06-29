#!/usr/bin/env python3
"""Script to run database migrations."""

import os
import sys
import sqlite3
import logging
import argparse
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_database_path():
    """Get the database path from the environment or use default."""
    db_path = os.environ.get('DB_PATH', 'app/data/fnaapp.db')
    return db_path

def run_migration(migration_file, db_path=None):
    """Run a specific migration file on the database."""
    if not db_path:
        db_path = get_database_path()
    
    # Check if migration file exists
    mig_path = Path(migration_file)
    if not mig_path.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False
    
    # Read migration SQL
    with open(mig_path, 'r') as f:
        sql = f.read()
    
    # Connect to database
    conn = None
    try:
        logger.info(f"Connecting to database at {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Execute migration script
        logger.info(f"Executing migration: {migration_file}")
        cursor.executescript(sql)
        conn.commit()
        
        logger.info("Migration completed successfully")
        return True
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        return False
    except Exception as e:
        logger.error(f"Error running migration: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument("migration_file", help="Path to migration SQL file")
    parser.add_argument("--db-path", help="Database path")
    parser.add_argument("--migrations-dir", 
                       default="app/database/migrations",
                       help="Directory containing migration files")
    
    args = parser.parse_args()
    
    # If a full path wasn't provided, look in the migrations directory
    migration_file = args.migration_file
    if not os.path.isabs(migration_file) and not os.path.exists(migration_file):
        migration_path = os.path.join(args.migrations_dir, migration_file)
        if os.path.exists(migration_path):
            migration_file = migration_path
    
    success = run_migration(migration_file, args.db_path)
    sys.exit(0 if success else 1) 