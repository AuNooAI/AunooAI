import sqlite3
import os
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Update the analyzed status of articles in the database.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default database from config.json
  python update_analyzed_status_standalone.py

  # Specify a database file directly
  python update_analyzed_status_standalone.py --db path/to/database.db

  # List available databases
  python update_analyzed_status_standalone.py --list

  # Show database info without making changes
  python update_analyzed_status_standalone.py --info

  # Force update without confirmation
  python update_analyzed_status_standalone.py --force
        """
    )
    
    parser.add_argument(
        '--db', 
        help='Path to the database file. If not specified, uses the active database from config.json'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available databases in the app/data directory'
    )
    
    parser.add_argument(
        '--info',
        action='store_true',
        help='Show database information without making changes'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    return parser.parse_args()

def get_database_path(custom_db=None):
    """Get the path to the database"""
    try:
        script_dir = Path(__file__).parent
        data_dir = script_dir.parent / 'app' / 'data'
        
        # If custom database specified, use it
        if custom_db:
            db_path = Path(custom_db)
            # If relative path, make it relative to script location
            if not db_path.is_absolute():
                db_path = data_dir / db_path
            
            if not db_path.exists():
                raise FileNotFoundError(f"Database not found at {db_path}")
            return str(db_path)
        
        # Otherwise use config.json
        config_path = data_dir / 'config.json'
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                db_name = config.get('active_database', 'fnaapp.db')
        else:
            logger.warning("config.json not found, using default database name 'fnaapp.db'")
            db_name = 'fnaapp.db'
        
        db_path = data_dir / db_name
        
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found at {db_path}")
            
        return str(db_path)
        
    except Exception as e:
        logger.error(f"Error getting database path: {e}")
        raise

def list_available_databases():
    """List all available databases in the app/data directory"""
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / 'app' / 'data'
    
    print("\nAvailable Databases:")
    print("-" * 60)
    print(f"{'Database Name':<30} {'Size':<15} {'Last Modified'}")
    print("-" * 60)
    
    for file in data_dir.glob('*.db'):
        size_mb = file.stat().st_size / (1024 * 1024)
        mod_time = datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{file.name:<30} {f'{size_mb:.2f} MB':<15} {mod_time}")

def show_database_info(db_path):
    """Show information about the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print("\nDatabase Information:")
        print(f"Path: {db_path}")
        print(f"Size: {Path(db_path).stat().st_size / (1024 * 1024):.2f} MB")
        print(f"Last Modified: {datetime.fromtimestamp(Path(db_path).stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\nTables:")
        print("-" * 40)
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"{table[0]:<30} {count:>8} rows")
            
        # Get article statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN analyzed = TRUE THEN 1 END) as analyzed,
                COUNT(DISTINCT topic) as topics
            FROM articles
        """)
        stats = cursor.fetchone()
        
        print("\nArticle Statistics:")
        print(f"Total Articles: {stats[0]}")
        print(f"Already Analyzed: {stats[1]}")
        print(f"Distinct Topics: {stats[2]}")
        
    except Exception as e:
        logger.error(f"Error getting database info: {e}")
        raise
    finally:
        conn.close()

def update_analyzed_status(db_path):
    """Update the analyzed status of articles based on their content"""
    logger.info(f"Starting update for database: {db_path}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Begin transaction
        cursor.execute("BEGIN IMMEDIATE")
        
        try:
            # Get initial counts
            cursor.execute("SELECT COUNT(*) FROM articles")
            total_before = cursor.fetchone()[0]
            logger.info(f"Total articles before update: {total_before}")
            
            # First, mark all articles as not analyzed
            cursor.execute("""
                UPDATE articles 
                SET analyzed = FALSE
            """)
            logger.info("Reset all articles to unanalyzed state")
            
            # Then, mark articles as analyzed if they have all required fields
            update_query = """
                UPDATE articles 
                SET analyzed = TRUE 
                WHERE sentiment IS NOT NULL 
                AND sentiment != ''
                AND category IS NOT NULL 
                AND category != ''
                AND future_signal IS NOT NULL 
                AND future_signal != ''
                AND time_to_impact IS NOT NULL 
                AND time_to_impact != ''
                AND driver_type IS NOT NULL 
                AND driver_type != ''
            """
            cursor.execute(update_query)
            
            # Get final counts
            cursor.execute("SELECT COUNT(*) FROM articles WHERE analyzed = TRUE")
            analyzed_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM articles WHERE analyzed = FALSE")
            unanalyzed_count = cursor.fetchone()[0]
            
            # Get some sample data for verification
            cursor.execute("""
                SELECT uri, title, analyzed 
                FROM articles 
                WHERE analyzed = TRUE 
                LIMIT 5
            """)
            analyzed_samples = cursor.fetchall()
            
            cursor.execute("""
                SELECT uri, title, analyzed 
                FROM articles 
                WHERE analyzed = FALSE 
                LIMIT 5
            """)
            unanalyzed_samples = cursor.fetchall()
            
            # Commit the transaction
            conn.commit()
            
            # Print detailed report
            print("\n=== Update Complete ===")
            print(f"Database: {db_path}")
            print(f"Total articles: {total_before}")
            print(f"Analyzed articles: {analyzed_count}")
            print(f"Unanalyzed articles: {unanalyzed_count}")
            
            print("\nSample Analyzed Articles:")
            for uri, title, _ in analyzed_samples:
                print(f"- {title[:50]}... ({uri[:50]}...)")
                
            print("\nSample Unanalyzed Articles:")
            for uri, title, _ in unanalyzed_samples:
                print(f"- {title[:50]}... ({uri[:50]}...)")
            
            # Create backup of update results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = Path(db_path).parent / f"analyzed_status_update_{timestamp}.log"
            
            with open(report_path, 'w') as f:
                f.write("=== Article Analysis Status Update ===\n")
                f.write(f"Update Time: {datetime.now().isoformat()}\n")
                f.write(f"Database: {db_path}\n")
                f.write(f"Total Articles: {total_before}\n")
                f.write(f"Analyzed Articles: {analyzed_count}\n")
                f.write(f"Unanalyzed Articles: {unanalyzed_count}\n")
                
                f.write("\nSample Analyzed Articles:\n")
                for uri, title, _ in analyzed_samples:
                    f.write(f"- {title[:50]}... ({uri[:50]}...)\n")
                    
                f.write("\nSample Unanalyzed Articles:\n")
                for uri, title, _ in unanalyzed_samples:
                    f.write(f"- {title[:50]}... ({uri[:50]}...)\n")
            
            logger.info(f"Detailed report saved to: {report_path}")
            
            return {
                "success": True,
                "analyzed_count": analyzed_count,
                "unanalyzed_count": unanalyzed_count,
                "total_count": total_before,
                "report_path": str(report_path)
            }
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error during update: {e}")
            raise
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise

if __name__ == "__main__":
    args = parse_arguments()
    
    try:
        if args.list:
            list_available_databases()
            exit(0)
        
        # Get database path
        db_path = get_database_path(args.db)
        
        if args.info:
            show_database_info(db_path)
            exit(0)
        
        # Show database info and confirm
        show_database_info(db_path)
        
        if not args.force:
            confirm = input("\nDo you want to proceed with the update? (y/N): ")
            if confirm.lower() != 'y':
                print("Update cancelled.")
                exit(0)
        
        result = update_analyzed_status(db_path)
        
        print("\nUpdate successful!")
        print(f"Report saved to: {result['report_path']}")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        print("Update failed!")
        exit(1)