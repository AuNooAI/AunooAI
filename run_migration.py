#!/usr/bin/env python3
"""Script to run database migrations with version tracking and rollback support."""

import os
import sys
import sqlite3
import logging
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

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

def calculate_checksum(file_path):
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def ensure_migration_table(conn):
    """Ensure the migration_history table exists."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            checksum TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_migration_name ON migration_history(migration_name)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_applied_at ON migration_history(applied_at DESC)
    """)
    conn.commit()

def is_migration_applied(conn, migration_name):
    """Check if a migration has already been applied."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT success FROM migration_history WHERE migration_name = ?",
        (migration_name,)
    )
    result = cursor.fetchone()
    return result is not None and result[0]

def record_migration(conn, migration_name, checksum, success=True, error_message=None):
    """Record a migration in the history table."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO migration_history
        (migration_name, applied_at, success, error_message, checksum)
        VALUES (?, ?, ?, ?, ?)
    """, (migration_name, datetime.now(), success, error_message, checksum))
    conn.commit()

def get_migration_history(conn):
    """Get all applied migrations."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT migration_name, applied_at, success, error_message
        FROM migration_history
        ORDER BY applied_at DESC
    """)
    return cursor.fetchall()

def rollback_migration(conn, migration_name):
    """Remove a migration from history (for rollback)."""
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM migration_history WHERE migration_name = ?",
        (migration_name,)
    )
    conn.commit()
    logger.info(f"Rolled back migration: {migration_name}")

def run_migration(migration_file, db_path=None, force=False, rollback=False):
    """Run a specific migration file on the database."""
    if not db_path:
        db_path = get_database_path()

    # Check if migration file exists
    mig_path = Path(migration_file)
    if not mig_path.exists():
        logger.error(f"Migration file not found: {migration_file}")
        return False

    migration_name = mig_path.name

    # Calculate checksum
    checksum = calculate_checksum(mig_path)

    # Read migration SQL
    with open(mig_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    # Connect to database
    conn = None
    try:
        logger.info(f"Connecting to database at {db_path}")
        conn = sqlite3.connect(db_path)

        # Ensure migration tracking table exists
        ensure_migration_table(conn)

        # Handle rollback
        if rollback:
            rollback_migration(conn, migration_name)
            return True

        # Check if already applied
        if not force and is_migration_applied(conn, migration_name):
            logger.info(f"Migration '{migration_name}' already applied. Skipping.")
            return True

        cursor = conn.cursor()

        # Execute migration script
        logger.info(f"Executing migration: {migration_name}")
        cursor.executescript(sql)
        conn.commit()

        # Record successful migration
        record_migration(conn, migration_name, checksum, success=True)

        logger.info(f"✓ Migration completed successfully: {migration_name}")
        return True

    except sqlite3.Error as e:
        error_msg = f"SQLite error: {e}"
        logger.error(error_msg)
        if conn:
            record_migration(conn, migration_name, checksum, success=False, error_message=str(e))
        return False
    except Exception as e:
        error_msg = f"Error running migration: {e}"
        logger.error(error_msg)
        if conn:
            record_migration(conn, migration_name, checksum, success=False, error_message=str(e))
        return False
    finally:
        if conn:
            conn.close()

def run_all_migrations(migrations_dir, db_path=None):
    """Run all pending migrations in order."""
    migrations_path = Path(migrations_dir)
    if not migrations_path.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        return False

    # Get all SQL files sorted by name
    migration_files = sorted(migrations_path.glob("*.sql"))

    if not migration_files:
        logger.warning(f"No migration files found in {migrations_dir}")
        return True

    logger.info(f"Found {len(migration_files)} migration files")

    success_count = 0
    skip_count = 0
    fail_count = 0

    for migration_file in migration_files:
        result = run_migration(str(migration_file), db_path)
        if result:
            success_count += 1
        else:
            fail_count += 1

    logger.info(f"\nMigration Summary:")
    logger.info(f"  ✓ Successful: {success_count}")
    logger.info(f"  ✗ Failed: {fail_count}")
    logger.info(f"  Total: {len(migration_files)}")

    return fail_count == 0

def show_migration_history(db_path=None):
    """Display migration history."""
    if not db_path:
        db_path = get_database_path()

    try:
        conn = sqlite3.connect(db_path)
        ensure_migration_table(conn)

        history = get_migration_history(conn)

        if not history:
            logger.info("No migrations have been applied yet.")
            return

        logger.info("\nMigration History:")
        logger.info("-" * 80)
        logger.info(f"{'Migration Name':<50} {'Applied At':<20} {'Status'}")
        logger.info("-" * 80)

        for name, applied_at, success, error in history:
            status = "✓ Success" if success else f"✗ Failed: {error}"
            logger.info(f"{name:<50} {applied_at:<20} {status}")

        conn.close()

    except Exception as e:
        logger.error(f"Error reading migration history: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run database migrations with version tracking")
    parser.add_argument("migration_file", nargs='?', help="Path to migration SQL file")
    parser.add_argument("--db-path", help="Database path")
    parser.add_argument("--migrations-dir",
                       default="app/database/migrations",
                       help="Directory containing migration files")
    parser.add_argument("--all", action="store_true",
                       help="Run all pending migrations")
    parser.add_argument("--force", action="store_true",
                       help="Force re-run migration even if already applied")
    parser.add_argument("--rollback", action="store_true",
                       help="Rollback (remove from history) the specified migration")
    parser.add_argument("--history", action="store_true",
                       help="Show migration history")

    args = parser.parse_args()

    # Show history
    if args.history:
        show_migration_history(args.db_path)
        sys.exit(0)

    # Run all migrations
    if args.all:
        success = run_all_migrations(args.migrations_dir, args.db_path)
        sys.exit(0 if success else 1)

    # Run single migration
    if not args.migration_file:
        parser.print_help()
        sys.exit(1)

    # If a full path wasn't provided, look in the migrations directory
    migration_file = args.migration_file
    if not os.path.isabs(migration_file) and not os.path.exists(migration_file):
        migration_path = os.path.join(args.migrations_dir, migration_file)
        if os.path.exists(migration_path):
            migration_file = migration_path

    success = run_migration(migration_file, args.db_path, args.force, args.rollback)
    sys.exit(0 if success else 1)
