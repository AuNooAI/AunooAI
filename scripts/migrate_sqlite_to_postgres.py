#!/usr/bin/env python3
"""
Comprehensive SQLite to PostgreSQL migration script.

This script migrates all data from an existing SQLite database (fnaapp.db)
to PostgreSQL. It handles:
- All core tables (articles, users, settings, etc.)
- Keyword monitoring data
- Organizational profiles
- Media bias data
- Feed groups and sources
- Analysis data and caches
- OAuth data
- And all other application tables

Usage:
    python scripts/migrate_sqlite_to_postgres.py [--sqlite-path PATH]

Options:
    --sqlite-path PATH    Path to SQLite database (default: app/data/fnaapp.db)
    --skip-existing      Skip records that already exist in PostgreSQL
    --dry-run            Show what would be migrated without actually migrating
"""

import sys
import os
import sqlite3
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from sqlalchemy import text, inspect

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Tables to migrate in order (respecting foreign key dependencies)
MIGRATION_ORDER = [
    # Core user and auth tables
    'users',
    'oauth_users',
    'oauth_sessions',
    'oauth_allowlist',

    # Settings tables
    'keyword_monitor_settings',
    'keyword_monitor_status',
    'mediabias_settings',
    'settings_podcasts',

    # Organizational data
    'organizational_profiles',

    # Media bias data
    'mediabias',

    # Keyword monitoring
    'keyword_groups',
    'monitored_keywords',

    # Articles and related data
    'articles',
    'raw_articles',
    'articles_scenario_1',
    'article_analysis_cache',
    'article_annotations',

    # Keyword alerts (depends on articles and keywords)
    'keyword_alerts',
    'keyword_article_matches',

    # Feed management
    'shared_news_feeds',
    'feed_keyword_groups',
    'feed_group_sources',
    'feed_items',
    'user_feed_subscriptions',

    # Analysis and scenarios
    'scenarios',
    'scenario_blocks',
    'building_blocks',
    'analysis_versions',
    'analysis_versions_v2',

    # Auspex chat data
    'auspex_prompts',
    'auspex_chats',
    'auspex_messages',

    # Model bias arena
    'model_bias_arena_runs',
    'model_bias_arena_articles',
    'model_bias_arena_results',

    # Newsletters and podcasts
    'newsletter_prompts',
    'podcasts',

    # Signals and incidents
    'signal_instructions',
    'signal_alerts',
    'incident_status',

    # Trends and filters
    'trend_consistency_metrics',
    'vantage_desk_filters',

    # Migration tracking
    'migrations',
]


# Boolean columns that need conversion from SQLite INTEGER to PostgreSQL BOOLEAN
BOOLEAN_COLUMNS = {
    'articles': ['analyzed', 'auto_ingested'],
    'keyword_monitor_settings': ['is_enabled', 'auto_ingest_enabled', 'quality_control_enabled', 'auto_save_approved_only'],
    'keyword_alerts': ['is_read'],
    'keyword_article_matches': ['is_read'],
    'organizational_profiles': ['is_default'],
    'mediabias': ['enabled'],
    'users': ['is_admin', 'is_active'],
    'oauth_users': ['is_active'],
    'shared_news_feeds': ['is_public', 'is_default'],
    'user_feed_subscriptions': ['is_active'],
    'auspex_chats': ['is_archived'],
    'signal_alerts': ['is_acknowledged', 'is_resolved'],
}


class SQLiteToPostgresMigrator:
    """Handles migration from SQLite to PostgreSQL."""

    def __init__(self, sqlite_path: str, skip_existing: bool = True, dry_run: bool = False):
        """Initialize migrator.

        Args:
            sqlite_path: Path to SQLite database file
            skip_existing: Skip records that already exist in PostgreSQL
            dry_run: Show what would be migrated without actually migrating
        """
        self.sqlite_path = Path(sqlite_path)
        self.skip_existing = skip_existing
        self.dry_run = dry_run
        self.stats = {}

        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")

        # Connect to databases
        logger.info(f"Connecting to SQLite: {self.sqlite_path}")
        self.sqlite_conn = sqlite3.connect(str(self.sqlite_path))
        self.sqlite_conn.row_factory = sqlite3.Row

        logger.info("Connecting to PostgreSQL")
        self.db = Database()
        self.pg_conn = self.db._temp_get_connection()

        # Get list of tables that exist in both databases
        self.common_tables = self._get_common_tables()
        logger.info(f"Found {len(self.common_tables)} common tables to migrate")

    def _get_common_tables(self) -> List[str]:
        """Get list of tables that exist in both SQLite and PostgreSQL."""
        # Get SQLite tables
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        sqlite_tables = {row[0] for row in cursor.fetchall()}

        # Get PostgreSQL tables
        inspector = inspect(self.pg_conn)
        pg_tables = set(inspector.get_table_names())

        # Find common tables in migration order
        common = []
        for table in MIGRATION_ORDER:
            if table in sqlite_tables and table in pg_tables:
                common.append(table)

        # Add any remaining tables not in MIGRATION_ORDER
        for table in sorted(sqlite_tables & pg_tables):
            if table not in common:
                common.append(table)

        return common

    def _convert_booleans(self, table: str, row_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert boolean columns from SQLite INTEGER to PostgreSQL BOOLEAN.

        Args:
            table: Table name
            row_dict: Row data dictionary

        Returns:
            Modified row dictionary with converted booleans
        """
        if table in BOOLEAN_COLUMNS:
            for col in BOOLEAN_COLUMNS[table]:
                if col in row_dict and row_dict[col] is not None:
                    row_dict[col] = bool(row_dict[col])
        return row_dict

    def _get_primary_key(self, table: str) -> str:
        """Get primary key column name for a table.

        Args:
            table: Table name

        Returns:
            Primary key column name (usually 'id')
        """
        inspector = inspect(self.pg_conn)
        pk = inspector.get_pk_constraint(table)
        if pk and pk['constrained_columns']:
            return pk['constrained_columns'][0]
        return 'id'  # Default assumption

    def _record_exists(self, table: str, row_dict: Dict[str, Any]) -> bool:
        """Check if a record already exists in PostgreSQL.

        Args:
            table: Table name
            row_dict: Row data dictionary

        Returns:
            True if record exists, False otherwise
        """
        try:
            pk_col = self._get_primary_key(table)
            if pk_col not in row_dict:
                return False

            result = self.pg_conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {pk_col} = :pk_value"),
                {"pk_value": row_dict[pk_col]}
            ).scalar()

            return result > 0
        except Exception as e:
            logger.debug(f"Error checking if record exists in {table}: {e}")
            return False

    def migrate_table(self, table: str) -> Tuple[int, int]:
        """Migrate a single table from SQLite to PostgreSQL.

        Args:
            table: Table name

        Returns:
            Tuple of (migrated_count, skipped_count)
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Migrating table: {table}")
        logger.info(f"{'='*60}")

        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()

        if not rows:
            logger.info(f"  No data in {table}, skipping")
            return 0, 0

        logger.info(f"  Found {len(rows)} rows")

        migrated = 0
        skipped = 0
        errors = 0

        for row in rows:
            row_dict = dict(row)

            # Convert booleans
            row_dict = self._convert_booleans(table, row_dict)

            # Check if record exists
            if self.skip_existing and self._record_exists(table, row_dict):
                skipped += 1
                continue

            if self.dry_run:
                logger.debug(f"  [DRY RUN] Would migrate: {row_dict}")
                migrated += 1
                continue

            try:
                # Build INSERT query
                columns = ', '.join(row_dict.keys())
                placeholders = ', '.join(f':{key}' for key in row_dict.keys())

                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

                # Add ON CONFLICT clause for tables with primary keys
                pk_col = self._get_primary_key(table)
                if pk_col in row_dict:
                    # Build UPDATE clause for all columns except primary key
                    update_cols = [f"{col} = EXCLUDED.{col}" for col in row_dict.keys() if col != pk_col]
                    if update_cols:
                        query += f" ON CONFLICT ({pk_col}) DO UPDATE SET {', '.join(update_cols)}"
                    else:
                        query += f" ON CONFLICT ({pk_col}) DO NOTHING"

                self.pg_conn.execute(text(query), row_dict)
                migrated += 1

                # Commit every 100 rows
                if migrated % 100 == 0:
                    if not self.dry_run:
                        self.pg_conn.commit()
                    logger.info(f"  Progress: {migrated} rows migrated...")

            except Exception as e:
                errors += 1
                logger.error(f"  Error migrating row: {e}")
                logger.debug(f"  Row data: {row_dict}")
                if errors > 10:
                    logger.error(f"  Too many errors, skipping rest of {table}")
                    break

        # Final commit
        if not self.dry_run:
            self.pg_conn.commit()

        logger.info(f"  ✅ Migrated: {migrated}, Skipped: {skipped}, Errors: {errors}")

        return migrated, skipped

    def migrate_all(self):
        """Migrate all tables from SQLite to PostgreSQL."""
        logger.info("\n" + "="*70)
        logger.info("Starting comprehensive SQLite to PostgreSQL migration")
        logger.info("="*70)

        if self.dry_run:
            logger.info("⚠️  DRY RUN MODE - No data will actually be migrated")

        total_migrated = 0
        total_skipped = 0

        for table in self.common_tables:
            try:
                migrated, skipped = self.migrate_table(table)
                self.stats[table] = {'migrated': migrated, 'skipped': skipped}
                total_migrated += migrated
                total_skipped += skipped
            except Exception as e:
                logger.error(f"Failed to migrate table {table}: {e}")
                self.stats[table] = {'migrated': 0, 'skipped': 0, 'error': str(e)}

        # Print summary
        self._print_summary(total_migrated, total_skipped)

    def _print_summary(self, total_migrated: int, total_skipped: int):
        """Print migration summary."""
        logger.info("\n" + "="*70)
        logger.info("Migration Summary")
        logger.info("="*70)

        logger.info(f"\nTotal records migrated: {total_migrated}")
        logger.info(f"Total records skipped: {total_skipped}")

        logger.info("\nPer-table breakdown:")
        logger.info(f"{'Table':<35} {'Migrated':<12} {'Skipped':<12}")
        logger.info("-" * 70)

        for table in sorted(self.stats.keys()):
            stats = self.stats[table]
            if 'error' in stats:
                logger.info(f"{table:<35} {'ERROR':<12} {stats['error']}")
            else:
                logger.info(f"{table:<35} {stats['migrated']:<12} {stats['skipped']:<12}")

        if self.dry_run:
            logger.info("\n⚠️  This was a DRY RUN - no data was actually migrated")
            logger.info("Run without --dry-run to perform the actual migration")
        else:
            logger.info("\n🎉 Migration completed successfully!")
            logger.info("\nNext steps:")
            logger.info("1. Restart your application to use the PostgreSQL database")
            logger.info("2. Verify data integrity in the PostgreSQL database")
            logger.info("3. Keep a backup of your SQLite database (fnaapp.db)")

    def close(self):
        """Close database connections."""
        self.sqlite_conn.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Migrate SQLite database to PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate with default settings
  python scripts/migrate_sqlite_to_postgres.py

  # Dry run to see what would be migrated
  python scripts/migrate_sqlite_to_postgres.py --dry-run

  # Migrate from custom SQLite path
  python scripts/migrate_sqlite_to_postgres.py --sqlite-path /path/to/custom.db

  # Force re-migration of existing records
  python scripts/migrate_sqlite_to_postgres.py --no-skip-existing
        """
    )

    parser.add_argument(
        '--sqlite-path',
        default='app/data/fnaapp.db',
        help='Path to SQLite database (default: app/data/fnaapp.db)'
    )

    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=True,
        help='Skip records that already exist in PostgreSQL (default: True)'
    )

    parser.add_argument(
        '--no-skip-existing',
        action='store_false',
        dest='skip_existing',
        help='Re-migrate existing records (overwrite)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually migrating'
    )

    args = parser.parse_args()

    try:
        migrator = SQLiteToPostgresMigrator(
            sqlite_path=args.sqlite_path,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run
        )

        migrator.migrate_all()
        migrator.close()

        return 0

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Migration cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
