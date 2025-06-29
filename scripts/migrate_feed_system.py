#!/usr/bin/env python3
"""
Migration script for creating feed system tables.
This creates the new unified feed system for social media and academic journals.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Add the project root to Python path
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)

from app.database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('feed_system_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_migration():
    """Execute the feed system migration."""
    try:
        logger.info("Starting feed system migration...")
        
        # Initialize database connection
        db = Database()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if migration was already applied
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='feed_keyword_groups'
            """)
            
            if cursor.fetchone():
                logger.warning("Feed system tables already exist. Skipping migration.")
                return True
            
            # Read the migration SQL file
            migration_file = os.path.join(
                os.path.dirname(__file__), 
                '..', 
                'app', 
                'database', 
                'migrations', 
                'create_feed_system_tables.sql'
            )
            
            if not os.path.exists(migration_file):
                logger.error(f"Migration file not found: {migration_file}")
                return False
            
            with open(migration_file, 'r') as f:
                migration_sql = f.read()
            
            logger.info("Executing migration SQL...")
            cursor.executescript(migration_sql)
            
            # Record the migration in migrations table
            migration_name = "create_feed_system_tables"
            cursor.execute("""
                INSERT OR IGNORE INTO migrations (name, applied_at) 
                VALUES (?, ?)
            """, (migration_name, datetime.now().isoformat()))
            
            conn.commit()
            
            # Verify tables were created
            tables_to_check = [
                'feed_keyword_groups',
                'feed_group_sources', 
                'feed_items',
                'user_feed_subscriptions'
            ]
            
            for table in tables_to_check:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table,))
                
                if not cursor.fetchone():
                    logger.error(f"Table {table} was not created successfully")
                    return False
                
                logger.info(f"✓ Table {table} created successfully")
            
            # Verify indexes were created
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name LIKE 'idx_feed_%'
            """)
            indexes = cursor.fetchall()
            logger.info(f"✓ Created {len(indexes)} indexes for performance")
            
            logger.info("Feed system migration completed successfully!")
            return True
            
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        logger.exception("Full error details:")
        return False

def create_sample_data():
    """Create some sample feed groups for testing."""
    try:
        logger.info("Creating sample feed data...")
        
        db = Database()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create sample feed groups
            sample_groups = [
                {
                    'name': 'AI Research',
                    'description': 'Latest AI and machine learning research',
                    'color': '#FF69B4'
                },
                {
                    'name': 'Tech News',
                    'description': 'Technology industry updates and discussions',
                    'color': '#32CD32'
                },
                {
                    'name': 'Climate Science',
                    'description': 'Climate change research and environmental news',
                    'color': '#4169E1'
                }
            ]
            
            for group in sample_groups:
                cursor.execute("""
                    INSERT OR IGNORE INTO feed_keyword_groups 
                    (name, description, color) VALUES (?, ?, ?)
                """, (group['name'], group['description'], group['color']))
                
                group_id = cursor.lastrowid
                if group_id:
                    logger.info(f"✓ Created sample group: {group['name']} (ID: {group_id})")
                    
                    # Add sample sources for each group
                    if group['name'] == 'AI Research':
                        keywords = '["artificial intelligence", "machine learning", "neural networks", "deep learning"]'
                    elif group['name'] == 'Tech News':
                        keywords = '["technology", "startup", "software", "programming"]'
                    else:  # Climate Science
                        keywords = '["climate change", "global warming", "carbon emissions", "renewable energy"]'
                    
                    # Add social media source
                    cursor.execute("""
                        INSERT OR IGNORE INTO feed_group_sources 
                        (group_id, source_type, keywords) VALUES (?, ?, ?)
                    """, (group_id, 'social_media', keywords))
                    
                    # Add academic journals source
                    cursor.execute("""
                        INSERT OR IGNORE INTO feed_group_sources 
                        (group_id, source_type, keywords) VALUES (?, ?, ?)
                    """, (group_id, 'academic_journals', keywords))
                    
                    # Add user subscription
                    cursor.execute("""
                        INSERT OR IGNORE INTO user_feed_subscriptions 
                        (group_id) VALUES (?)
                    """, (group_id,))
            
            conn.commit()
            logger.info("Sample feed data created successfully!")
            
    except Exception as e:
        logger.error(f"Failed to create sample data: {str(e)}")
        logger.exception("Full error details:")

def main():
    """Main migration execution."""
    logger.info("=" * 50)
    logger.info("FEED SYSTEM MIGRATION")
    logger.info("=" * 50)
    
    # Run the migration
    success = run_migration()
    
    if success:
        # Create sample data
        create_sample_data()
        
        logger.info("Migration completed successfully!")
        logger.info("You can now start implementing the feed services and API endpoints.")
        return 0
    else:
        logger.error("Migration failed!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 