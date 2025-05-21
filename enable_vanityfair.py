#!/usr/bin/env python3
"""Script to enable Vanity Fair in the media bias database."""

from app.database import get_database_instance
from app.models.media_bias import MediaBias
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Update the Vanity Fair entry in the database."""
    # Get database instance
    db = get_database_instance()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if Vanity Fair exists in the database
        cursor.execute(
            "SELECT source, enabled FROM mediabias WHERE source LIKE '%vanityfair%'"
        )
        rows = cursor.fetchall()
        
        if not rows:
            logger.error("No Vanity Fair entry found in the database")
            return
        
        for source, enabled in rows:
            logger.info(f"Found source: {source}, enabled: {enabled}")
            
            # Update the enabled field to 1
            cursor.execute(
                "UPDATE mediabias SET enabled = 1 WHERE source = ?",
                (source,)
            )
            logger.info(f"Updated {source} enabled status to 1")
            
        # Commit the changes
        conn.commit()
        
        # Verify the update
        cursor.execute(
            "SELECT source, enabled FROM mediabias WHERE source LIKE '%vanityfair%'"
        )
        rows = cursor.fetchall()
        
        for source, enabled in rows:
            logger.info(f"After update - source: {source}, enabled: {enabled}")
    
    # Reload media bias data
    media_bias = MediaBias(db)
    logger.info("Reloaded media bias data")
    
    # Test if Vanity Fair can be found now
    test_result = media_bias.get_bias_for_source("vanityfair.com")
    if test_result:
        logger.info(f"Successfully found Vanity Fair bias data: {test_result}")
    else:
        logger.error("Still can't find Vanity Fair bias data after update")

if __name__ == "__main__":
    main() 