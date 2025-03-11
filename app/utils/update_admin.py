import sqlite3
import os
import logging
from pathlib import Path
from passlib.context import CryptContext

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Create password context - matches the one used in the application
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def update_admin_password(db_path: str, new_password: str):
    """
    Update the admin user's password in the database.
    
    Args:
        db_path: Path to the SQLite database file
        new_password: New password for the admin user
    """
    # Hash the password
    hashed_password = pwd_context.hash(new_password)
    
    # Expand tilde in path if present
    expanded_path = os.path.abspath(os.path.expanduser(db_path))
    
    # Ensure the directory exists
    db_dir = os.path.dirname(expanded_path)
    if not os.path.exists(db_dir):
        logger.info(f"Creating directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)
    
    logger.info(f"Connecting to database at: {expanded_path}")
    
    # Connect to database
    conn = sqlite3.connect(expanded_path)
    cursor = conn.cursor()
    
    try:
        # Ensure the users table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                force_password_change INTEGER DEFAULT 0
            )
        """)
        
        # Update the admin user's password and set force_password_change
        cursor.execute(
            "UPDATE users SET password = ?, force_password_change = 1 WHERE username = 'admin'",
            (hashed_password,)
        )
        
        # If no rows were updated, create the admin user
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO users (username, password, force_password_change) VALUES ('admin', ?, 1)",
                (hashed_password,)
            )
            
        conn.commit()
        logger.info("Admin password updated successfully and force_password_change set to true")
    except Exception as e:
        logger.error(f"Error updating password: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Get database path from environment or use relative path
    default_db_path = os.environ.get("DB_PATH", "data/fnaapp.db")
    default_password = os.environ.get("ADMIN_PASSWORD", "admin")
    
    import argparse
    parser = argparse.ArgumentParser(description='Update admin password in SQLite database')
    parser.add_argument('--db-path', default=default_db_path, help='Path to the SQLite database file')
    parser.add_argument('--password', default=default_password, help='New password for the admin user')
    args = parser.parse_args()
    
    update_admin_password(args.db_path, args.password) 
