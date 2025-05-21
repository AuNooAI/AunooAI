#!/usr/bin/env python3
"""
Script to enable all media bias sources in the database.
This will update all sources to have enabled=1 so their data will be returned.
"""

import sys
import os
import logging
from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('enable_media_sources')

def main():
    """Enable all media bias sources in the database."""
    try:
        # Get database connection
        db = get_database_instance()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current count of disabled sources
            cursor.execute("SELECT COUNT(*) FROM mediabias WHERE enabled = 0")
            disabled_count = cursor.fetchone()[0]
            
            logger.info(f"Found {disabled_count} disabled media bias sources")
            
            if disabled_count > 0:
                # Update all sources to be enabled
                cursor.execute("UPDATE mediabias SET enabled = 1")
                updated_count = cursor.rowcount
                
                # Commit changes
                conn.commit()
                
                logger.info(f"Successfully enabled {updated_count} media bias sources")
            else:
                logger.info("All media bias sources are already enabled")
            
            # Get total count of sources
            cursor.execute("SELECT COUNT(*) FROM mediabias")
            total_count = cursor.fetchone()[0]
            
            logger.info(f"Total media bias sources in database: {total_count}")
            
            # Sample some sources to verify
            cursor.execute("SELECT source, bias, factual_reporting, enabled FROM mediabias LIMIT 5")
            logger.info("Sample sources after update:")
            for row in cursor.fetchall():
                logger.info(f"Source: {row[0]}, Bias: {row[1]}, Factual: {row[2]}, Enabled: {row[3]}")
                
        logger.info("Media bias source update completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error updating media bias sources: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 