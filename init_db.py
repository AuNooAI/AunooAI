#!/usr/bin/env python3
"""Script to initialize the database."""

import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

# Import database
from app.database import get_database_instance, initialize_db

def init_database():
    """Initialize the database with required tables."""
    logger.info("Initializing database...")
    
    # Get database instance
    db = get_database_instance()
    
    # Initialize database (create tables)
    initialize_db()
    
    # Create a connection to ensure tables are created
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if articles table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
        if cursor.fetchone():
            logger.info("Articles table exists")
        else:
            logger.error("Articles table does not exist after initialization!")
            return False
    
    logger.info("Database initialization completed successfully")
    return True

if __name__ == "__main__":
    if init_database():
        print("Database initialized successfully!")
    else:
        print("Error initializing database!")
        sys.exit(1) 