import sqlite3
import logging
import argparse
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def inspect_database(db_path: str) -> None:
    """
    Inspect the database structure and print detailed information.
    
    Args:
        db_path (str): Path to the database file
    """
    try:
        logger.info(f"Inspecting database at {db_path}")
        
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            logger.info("Database is empty (no tables found)")
            return
        
        logger.info(f"Found {len(tables)} tables:")
        
        # Inspect each table
        for table in tables:
            table_name = table[0]
            logger.info(f"\nTable: {table_name}")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            logger.info("Columns:")
            for col in columns:
                logger.info(f"  {col[1]} ({col[2]})")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            row_count = cursor.fetchone()[0]
            logger.info(f"Row count: {row_count}")
            
            # Get sample data (up to 2 rows)
            if row_count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 2;")
                sample_rows = cursor.fetchall()
                logger.info("Sample data:")
                for row in sample_rows:
                    logger.info(f"  {row}")
        
        conn.close()
        logger.info("\nDatabase inspection completed")
        
    except Exception as e:
        logger.error(f"Error inspecting database: {str(e)}")
        raise

def main():
    """Main function to run the database inspection."""
    parser = argparse.ArgumentParser(description='Inspect a SQLite database structure and contents.')
    parser.add_argument('--db-path', type=str, required=True, help='Path to the database file')
    args = parser.parse_args()
    
    inspect_database(args.db_path)

if __name__ == "__main__":
    main() 