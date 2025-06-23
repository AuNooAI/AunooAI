#!/usr/bin/env python3
"""
Script to fix SQLite database corruption issues.
Attempts to recover data from corrupted databases and provides fallback options.
"""

import os
import sys
import sqlite3
import shutil
import logging
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_database_paths():
    """Get database directory and file paths."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    data_dir = os.path.join(project_root, 'app', 'data')
    
    # Ensure data directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    config_path = os.path.join(data_dir, 'config.json')
    
    # Read active database from config
    active_db = 'fnaapp.db'  # Default
    if os.path.exists(config_path):
        try:
            import json
            with open(config_path, 'r') as f:
                config = json.load(f)
                active_db = config.get('active_database', 'fnaapp.db')
        except Exception as e:
            logger.warning(f"Could not read database config: {e}")
    
    db_path = os.path.join(data_dir, active_db)
    
    return data_dir, db_path, active_db

def check_database_corruption(db_path):
    """Check if a database is corrupted."""
    if not os.path.exists(db_path):
        logger.info(f"Database file does not exist: {db_path}")
        return False, "not_exists"
    
    try:
        # Try to connect and perform basic operations
        conn = sqlite3.connect(db_path)
        
        # Test basic operations
        cursor = conn.cursor()
        
        # Check integrity
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        if result[0] != 'ok':
            logger.error(f"Database integrity check failed: {result[0]}")
            conn.close()
            return True, "integrity_fail"
        
        # Try to enable WAL mode (this is where the error occurred)
        cursor.execute("PRAGMA journal_mode = WAL")
        wal_result = cursor.fetchone()
        logger.info(f"WAL mode test result: {wal_result}")
        
        # Test a simple query
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        cursor.fetchall()
        
        conn.close()
        logger.info(f"Database {db_path} appears to be healthy")
        return False, "healthy"
        
    except sqlite3.DatabaseError as e:
        logger.error(f"Database corruption detected: {e}")
        return True, str(e)
    except Exception as e:
        logger.error(f"Error checking database: {e}")
        return True, str(e)

def backup_corrupted_database(db_path):
    """Create a backup of the corrupted database."""
    if not os.path.exists(db_path):
        return None
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.corrupted_backup_{timestamp}"
    
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"Corrupted database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to backup corrupted database: {e}")
        return None

def attempt_database_recovery(db_path):
    """Attempt to recover data from a corrupted database."""
    logger.info("Attempting database recovery...")
    
    # Create recovery database path
    recovery_path = f"{db_path}.recovery"
    
    try:
        # Try to dump and recreate the database
        with sqlite3.connect(db_path) as corrupted_conn:
            # Try to export data
            with sqlite3.connect(recovery_path) as recovery_conn:
                # Attempt to copy data
                corrupted_conn.backup(recovery_conn)
                
        logger.info(f"Recovery database created: {recovery_path}")
        return recovery_path
        
    except Exception as e:
        logger.error(f"Database recovery failed: {e}")
        
        # Try alternative recovery method
        try:
            logger.info("Trying alternative recovery method...")
            recovery_conn = sqlite3.connect(recovery_path)
            corrupted_conn = sqlite3.connect(db_path)
            
            # Get list of tables
            cursor = corrupted_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            for table_name, in tables:
                try:
                    # Try to copy table data
                    cursor.execute(f"SELECT sql FROM sqlite_master WHERE name='{table_name}'")
                    create_sql = cursor.fetchone()
                    if create_sql:
                        recovery_conn.execute(create_sql[0])
                        
                    # Copy data
                    cursor.execute(f"SELECT * FROM {table_name}")
                    rows = cursor.fetchall()
                    
                    if rows:
                        placeholders = ','.join(['?' for _ in range(len(rows[0]))])
                        recovery_conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
                        logger.info(f"Recovered {len(rows)} rows from table {table_name}")
                        
                except Exception as table_error:
                    logger.warning(f"Could not recover table {table_name}: {table_error}")
                    
            recovery_conn.commit()
            recovery_conn.close()
            corrupted_conn.close()
            
            logger.info("Alternative recovery completed")
            return recovery_path
            
        except Exception as alt_error:
            logger.error(f"Alternative recovery also failed: {alt_error}")
            
    return None

def get_password_hash(password):
    """Simple password hashing function to avoid import issues."""
    import hashlib
    import secrets
    
    # Generate a salt
    salt = secrets.token_hex(16)
    
    # Hash the password with salt
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    
    # Return salt + hash
    return salt + pwd_hash.hex()

def create_fresh_database(db_path):
    """Create a fresh database with basic structure."""
    logger.info("Creating fresh database...")
    
    try:
        # Remove the corrupted file
        if os.path.exists(db_path):
            os.remove(db_path)
            
        # Create new database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create basic tables (minimal structure)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                force_password_change BOOLEAN DEFAULT 0,
                completed_onboarding BOOLEAN DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
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
        
        # Create admin user with default password
        admin_hash = get_password_hash("admin")
        cursor.execute("""
            INSERT OR IGNORE INTO users (username, password_hash, force_password_change)
            VALUES (?, ?, ?)
        """, ("admin", admin_hash, True))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Fresh database created: {db_path}")
        logger.info("Default admin user created (username: admin, password: admin)")
        logger.info("You will be prompted to change the password on first login")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create fresh database: {e}")
        return False

def main():
    """Main function to fix database corruption."""
    logger.info("Database Corruption Fix Tool")
    logger.info("=" * 50)
    
    try:
        # Get database paths
        data_dir, db_path, active_db = get_database_paths()
        logger.info(f"Data directory: {data_dir}")
        logger.info(f"Active database: {active_db}")
        logger.info(f"Database path: {db_path}")
        
        # Check if database is corrupted
        is_corrupted, error_type = check_database_corruption(db_path)
        
        if not is_corrupted:
            if error_type == "not_exists":
                logger.info("Database does not exist, creating fresh database...")
                if create_fresh_database(db_path):
                    logger.info("Fresh database created successfully")
                    return 0
                else:
                    logger.error("Failed to create fresh database")
                    return 1
            else:
                logger.info("Database appears to be healthy")
                return 0
        
        logger.warning(f"Database corruption detected: {error_type}")
        
        # Backup corrupted database
        backup_path = backup_corrupted_database(db_path)
        
        # Try to recover data
        recovery_path = attempt_database_recovery(db_path)
        
        if recovery_path and os.path.exists(recovery_path):
            # Test recovered database
            is_recovered_corrupted, _ = check_database_corruption(recovery_path)
            
            if not is_recovered_corrupted:
                # Replace corrupted database with recovered one
                shutil.move(recovery_path, db_path)
                logger.info("Database successfully recovered!")
                return 0
            else:
                logger.warning("Recovered database is still corrupted")
                os.remove(recovery_path)
        
        # If recovery failed, create fresh database
        logger.info("Recovery failed, creating fresh database...")
        if create_fresh_database(db_path):
            logger.info("Fresh database created successfully")
            logger.warning("All previous data has been lost")
            if backup_path:
                logger.info(f"Corrupted database backed up to: {backup_path}")
            return 0
        else:
            logger.error("Failed to create fresh database")
            return 1
            
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 