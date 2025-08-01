#!/usr/bin/env python3
"""
Migration script to add consistency features to existing database.

This script creates the enhanced cache table for the trend convergence analysis
consistency improvements and migrates existing data if needed.

Usage:
    python scripts/migrate_consistency_features.py [database_path]
    
If no database path is provided, it will use 'app/data/fnaapp.db'
"""

import sqlite3
import logging
import sys
import os
from datetime import datetime
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_database(db_path: str):
    """Run all necessary migrations for consistency features."""
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
    
    logger.info(f"Starting migration for database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create new analysis versions table with cache support
        logger.info("Creating analysis_versions_v2 table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_versions_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT UNIQUE NOT NULL,
            topic TEXT NOT NULL,
            version_data TEXT NOT NULL,
            cache_metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create indexes for performance
        logger.info("Creating indexes...")
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cache_key_created 
        ON analysis_versions_v2(cache_key, created_at DESC)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_topic_created 
        ON analysis_versions_v2(topic, created_at DESC)
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_accessed_at 
        ON analysis_versions_v2(accessed_at DESC)
        """)
        
        # Create consistency metrics table
        logger.info("Creating trend_consistency_metrics table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trend_consistency_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            consistency_score REAL NOT NULL,
            comparison_count INTEGER,
            detailed_metrics TEXT,
            analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create index for consistency metrics
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_consistency_topic_date 
        ON trend_consistency_metrics(topic, analysis_date DESC)
        """)
        
        # Check if old analysis_versions table exists and migrate data
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='analysis_versions'")
        old_table_exists = cursor.fetchone()[0] > 0
        
        if old_table_exists:
            logger.info("Found existing analysis_versions table, checking for data to migrate...")
            
            # Check how much data exists
            cursor.execute("SELECT COUNT(*) FROM analysis_versions")
            total_count = cursor.fetchone()[0]
            
            if total_count > 0:
                logger.info(f"Found {total_count} existing analysis versions")
                
                # Migrate recent data (last 30 days)
                logger.info("Migrating recent analysis versions (last 30 days)...")
                cursor.execute("""
                INSERT OR IGNORE INTO analysis_versions_v2 (cache_key, topic, version_data, created_at)
                SELECT 
                    'legacy_' || substr(hex(randomblob(8)), 1, 16) as cache_key,
                    topic,
                    version_data,
                    created_at
                FROM analysis_versions
                WHERE created_at >= date('now', '-30 days')
                ORDER BY created_at DESC
                """)
                
                migrated = cursor.rowcount
                logger.info(f"Migrated {migrated} recent analysis versions")
                
                if migrated < total_count:
                    logger.info(f"Note: Only migrated recent entries. {total_count - migrated} older entries were not migrated to keep database size manageable.")
            else:
                logger.info("No existing analysis versions found to migrate")
        
        # Create a sample consistency test entry
        logger.info("Creating sample consistency metrics entry...")
        cursor.execute("""
        INSERT OR IGNORE INTO trend_consistency_metrics 
        (topic, consistency_score, comparison_count, detailed_metrics)
        VALUES (?, ?, ?, ?)
        """, (
            'system_test',
            0.85,
            1,
            json.dumps({
                'test_entry': True,
                'created_by': 'migration_script',
                'note': 'This is a test entry created during migration'
            })
        ))
        
        conn.commit()
        logger.info("Database migration completed successfully!")
        
        # Verify tables were created
        cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN ('analysis_versions_v2', 'trend_consistency_metrics')
        ORDER BY name
        """)
        created_tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Created tables: {', '.join(created_tables)}")
        
        # Show table sizes
        for table in created_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            logger.info(f"Table {table}: {count} rows")
        
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        logger.error(f"Error details: {type(e).__name__}: {str(e)}")
        return False
    finally:
        conn.close()

def verify_migration(db_path: str):
    """Verify that the migration was successful."""
    
    logger.info("Verifying migration...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if required tables exist
        required_tables = ['analysis_versions_v2', 'trend_consistency_metrics']
        
        for table in required_tables:
            cursor.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                logger.info(f"✓ Table {table} exists with {count} rows")
            else:
                logger.error(f"✗ Table {table} does not exist")
                return False
        
        # Check if indexes exist
        required_indexes = [
            'idx_cache_key_created',
            'idx_topic_created', 
            'idx_consistency_topic_date'
        ]
        
        for index in required_indexes:
            cursor.execute(f"SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='{index}'")
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                logger.info(f"✓ Index {index} exists")
            else:
                logger.warning(f"⚠ Index {index} does not exist")
        
        # Test basic functionality
        cursor.execute("SELECT cache_key, topic FROM analysis_versions_v2 LIMIT 1")
        result = cursor.fetchone()
        if result:
            logger.info(f"✓ Sample data accessible: cache_key={result[0][:8]}..., topic={result[1]}")
        
        logger.info("Migration verification completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False
    finally:
        conn.close()

def main():
    """Main migration function."""
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default database path
        db_path = os.path.join('app', 'data', 'fnaapp.db')
    
    logger.info("=" * 60)
    logger.info("TREND CONVERGENCE CONSISTENCY FEATURES MIGRATION")
    logger.info("=" * 60)
    logger.info(f"Target database: {db_path}")
    logger.info(f"Migration started at: {datetime.now().isoformat()}")
    logger.info("")
    
    # Run migration
    success = migrate_database(db_path)
    
    if success:
        # Verify migration
        verify_success = verify_migration(db_path)
        
        if verify_success:
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            logger.info("The following consistency features are now available:")
            logger.info("• Enhanced caching system with comprehensive cache keys")
            logger.info("• Deterministic article selection for consistent results")
            logger.info("• Consistency scoring and monitoring")
            logger.info("• Four consistency modes: deterministic, low_variance, balanced, creative")
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Restart your application to use the new features")
            logger.info("2. Test the consistency controls in the trend convergence interface")
            logger.info("3. Monitor consistency scores in the analysis results")
            logger.info("")
            return 0
        else:
            logger.error("Migration verification failed!")
            return 1
    else:
        logger.error("")
        logger.error("=" * 60)
        logger.error("❌ MIGRATION FAILED!")
        logger.error("=" * 60)
        logger.error("Please check the error messages above and try again.")
        logger.error("If the problem persists, please backup your database and contact support.")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)