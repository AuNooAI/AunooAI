#!/usr/bin/env python3
"""
Check if specific sources exist in the media bias database.
This will help diagnose why only Vanity Fair is showing bias data.
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

logger = logging.getLogger('check_specific_sources')

def main():
    """Check if specific sources exist in the media bias database."""
    try:
        # Get database connection
        db = get_database_instance()
        media_bias = MediaBias(db)
        
        # Sources to check - add those from your screenshot
        sources_to_check = [
            'biztoc.com',
            'theverge.com',
            'vanity fair',
            'vanityfair.com',
            'cnn.com',
            'foxnews.com',
            'forbes.com',
            'yahoo.com'
        ]
        
        print(f"Checking {len(sources_to_check)} sources for media bias data:")
        print("-" * 80)
        
        for source in sources_to_check:
            # Normalize source name
            normalized = normalize_domain(source)
            
            # Check if source exists in database
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT source, bias, factual_reporting, enabled FROM mediabias WHERE source LIKE ?",
                    (f"%{normalized}%",)
                )
                db_results = cursor.fetchall()
                
                if db_results:
                    print(f"Source: {source} (normalized: {normalized})")
                    print(f"Found {len(db_results)} matches in database:")
                    for result in db_results:
                        print(f"  - {result[0]}: Bias={result[1]}, Factual={result[2]}, Enabled={result[3]}")
                else:
                    print(f"Source: {source} (normalized: {normalized})")
                    print(f"  No matches found in database")
                
                # Also try using the get_bias_for_source function
                bias_result = media_bias.get_bias_for_source(source)
                if bias_result:
                    print(f"  get_bias_for_source returned: {bias_result.get('source')}")
                    print(f"    Bias: {bias_result.get('bias')}")
                    print(f"    Factual: {bias_result.get('factual_reporting')}")
                    print(f"    Enabled: {bias_result.get('enabled')}")
                else:
                    print(f"  get_bias_for_source returned no results")
                    
                print("-" * 80)
                
        return 0
        
    except Exception as e:
        logger.error(f"Error checking sources: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 