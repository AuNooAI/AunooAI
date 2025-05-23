#!/usr/bin/env python3
"""Script to update existing articles with media bias data."""

import os
import sys
import logging
import asyncio
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

# Import necessary modules
from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain
from run_migration import run_migration


async def update_articles_with_bias():
    """Update all existing articles with media bias data."""
    print("=== Updating Articles with Media Bias Data ===")
    
    # Run the migration first
    migration_file = os.path.join("migrations", "add_media_bias_fields.sql")
    if run_migration(migration_file):
        print("✓ Database schema updated with media bias fields")
    else:
        print("✗ Error updating database schema")
        return False
    
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance for lookups
    media_bias = MediaBias(db)
    
    # Connect to the database
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Get all articles
        cursor.execute("SELECT uri, news_source FROM articles")
        articles = cursor.fetchall()
        
        print(f"Found {len(articles)} articles to update")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for uri, source in articles:
            try:
                if not source:
                    domain = None
                    if uri:
                        # Try to extract domain from URI
                        from urllib.parse import urlparse
                        parsed_uri = urlparse(uri)
                        domain = parsed_uri.netloc
                else:
                    domain = source
                
                if not domain:
                    print(f"✗ Skipping article with no domain: {uri}")
                    skipped_count += 1
                    continue
                
                # Normalize domain
                normalized_domain = normalize_domain(domain)
                
                # Get bias data
                bias_data = media_bias.get_bias_for_source(normalized_domain)
                
                if bias_data:
                    # Update the article with bias data
                    cursor.execute("""
                        UPDATE articles SET 
                            bias = ?,
                            factual_reporting = ?,
                            mbfc_credibility_rating = ?,
                            bias_source = ?,
                            bias_country = ?,
                            press_freedom = ?,
                            media_type = ?,
                            popularity = ?
                        WHERE uri = ?
                    """, (
                        bias_data.get('bias'),
                        bias_data.get('factual_reporting'),
                        bias_data.get('mbfc_credibility_rating'),
                        bias_data.get('source'),
                        bias_data.get('country'),
                        bias_data.get('press_freedom'),
                        bias_data.get('media_type'),
                        bias_data.get('popularity'),
                        uri
                    ))
                    
                    updated_count += 1
                    
                    # Print progress every 100 articles
                    if updated_count % 100 == 0:
                        print(f"Updated {updated_count} articles so far...")
                else:
                    # No bias data found
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                print(f"✗ Error updating article {uri}: {str(e)}")
        
        # Commit the changes
        conn.commit()
        
        print("\n=== Update Complete ===")
        print(f"Total articles: {len(articles)}")
        print(f"Updated: {updated_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Errors: {error_count}")
        
        return True
    
    except Exception as e:
        conn.rollback()
        print(f"✗ Error updating articles: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # Run the update
    asyncio.run(update_articles_with_bias()) 