#!/usr/bin/env python3
"""
Migration script to add missing columns to keyword_monitor_settings table

This adds the following columns if they don't exist:
- provider
- auto_ingest_enabled
- min_relevance_threshold
- quality_control_enabled
- auto_save_approved_only
- default_llm_model
- llm_temperature
- llm_max_tokens
- max_articles_per_run
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "app" / "data" / "fnaapp.db"


def column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_column_if_missing(cursor, table_name, column_name, column_def):
    """Add a column to a table if it doesn't exist."""
    if not column_exists(cursor, table_name, column_name):
        print(f"  Adding column: {column_name}")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        return True
    else:
        print(f"  Column already exists: {column_name}")
        return False


def main():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print(f"Migrating database: {DB_PATH}\n")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Define columns to add
        columns_to_add = [
            ("provider", "TEXT DEFAULT 'newsapi'"),
            ("auto_ingest_enabled", "BOOLEAN DEFAULT 0"),
            ("min_relevance_threshold", "REAL DEFAULT 0.0"),
            ("quality_control_enabled", "BOOLEAN DEFAULT 1"),
            ("auto_save_approved_only", "BOOLEAN DEFAULT 0"),
            ("default_llm_model", "TEXT DEFAULT 'gpt-4o-mini'"),
            ("llm_temperature", "REAL DEFAULT 0.1"),
            ("llm_max_tokens", "INTEGER DEFAULT 1000"),
            ("max_articles_per_run", "INTEGER DEFAULT 50"),
        ]

        print("Processing keyword_monitor_settings table:")
        changes_made = 0

        for column_name, column_def in columns_to_add:
            if add_column_if_missing(cursor, "keyword_monitor_settings", column_name, column_def):
                changes_made += 1

        if changes_made > 0:
            conn.commit()
            print(f"\n✓ Migration complete! Added {changes_made} column(s).")
        else:
            print("\n✓ No migration needed - all columns already exist.")

        # Show final schema
        print("\nFinal schema:")
        cursor.execute("PRAGMA table_info(keyword_monitor_settings)")
        for row in cursor.fetchall():
            print(f"  {row[1]}: {row[2]}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
