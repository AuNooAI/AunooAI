#!/usr/bin/env python3
"""
Add missing sources to the media bias database.
"""

import sys
import logging
from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('add_missing_sources')

def main():
    """Add missing sources to the media bias database."""
    try:
        # Get database connection
        db = get_database_instance()
        
        # Sources to add with bias data
        sources_to_add = [
            {
                'source': 'biztoc.com',
                'bias': 'center',
                'factual_reporting': 'mostly factual',
                'country': 'USA',
                'media_type': 'News Aggregator',
                'enabled': 1
            },
            {
                'source': 'theatlantic.com',
                'bias': 'left',
                'factual_reporting': 'high',
                'country': 'USA',
                'media_type': 'Magazine',
                'enabled': 1
            },
            {
                'source': 'slate.com',
                'bias': 'left',
                'factual_reporting': 'mostly factual',
                'country': 'USA',
                'media_type': 'News and Opinion',
                'enabled': 1
            }
        ]
        
        # Create media bias instance
        media_bias = MediaBias(db)
        
        added_count = 0
        updated_count = 0
        
        for source_data in sources_to_add:
            source_name = source_data['source']
            
            # Check if source already exists
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM mediabias WHERE source = ?",
                    (source_name,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing source
                    cursor.execute("""
                        UPDATE mediabias SET
                            bias = ?,
                            factual_reporting = ?,
                            country = ?,
                            media_type = ?,
                            enabled = 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE source = ?
                    """, (
                        source_data.get('bias', ''),
                        source_data.get('factual_reporting', ''),
                        source_data.get('country', ''),
                        source_data.get('media_type', ''),
                        source_name
                    ))
                    conn.commit()
                    logger.info(f"Updated existing source: {source_name}")
                    updated_count += 1
                else:
                    # Add new source
                    source_id = media_bias.add_source(source_data)
                    logger.info(f"Added new source: {source_name} (ID: {source_id})")
                    added_count += 1
        
        logger.info(f"Added {added_count} new sources and updated {updated_count} existing sources")
        
        # Get the sources we just added to verify
        for source_name in [s['source'] for s in sources_to_add]:
            bias_data = media_bias.get_bias_for_source(source_name)
            if bias_data:
                logger.info(f"Source {source_name} has bias: {bias_data.get('bias')}, factual: {bias_data.get('factual_reporting')}")
            else:
                logger.warning(f"Source {source_name} not found after adding")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error adding sources: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 