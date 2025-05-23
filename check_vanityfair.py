#!/usr/bin/env python3
"""Script to check Vanity Fair media bias data."""

from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain, domains_match
import json

def main():
    """Main function to check Vanity Fair media bias data."""
    # Get database instance
    db = get_database_instance()
    
    # Check direct DB access
    print("Checking direct database access:")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Get column names
        cursor.execute("PRAGMA table_info(mediabias)")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Table columns: {columns}")
        
        # Get Vanity Fair entry
        cursor.execute("SELECT * FROM mediabias WHERE source LIKE '%vanityfair%'")
        rows = cursor.fetchall()
        
        if rows:
            for row in rows:
                # Convert to dict for easier reading
                result = dict(zip(columns, row))
                print(json.dumps(result, indent=2))
                print(f"enabled value: {result.get('enabled')}")
        else:
            print("No Vanity Fair entry found in database")
    
    # Check via MediaBias class
    print("\nChecking via MediaBias class:")
    media_bias = MediaBias(db)
    
    # Try different variations of the name
    test_sources = [
        "vanityfair.com",
        "www.vanityfair.com", 
        "Vanity Fair",
        "vanity fair",
        "https://www.vanityfair.com/some-article"
    ]
    
    for source in test_sources:
        print(f"\nTesting source: {source}")
        normalized = normalize_domain(source)
        print(f"Normalized: {normalized}")
        
        result = media_bias.get_bias_for_source(source)
        if result:
            print(f"FOUND: {json.dumps(result, indent=2)}")
        else:
            print("No match found")

if __name__ == "__main__":
    main() 