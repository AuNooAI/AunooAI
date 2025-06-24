#!/usr/bin/env python3
"""
Clean asterisk artifacts and "Unknown" values from database fields.
This script removes asterisk formatting and filters out "Unknown" values from various fields.
"""

import sqlite3
import re
from pathlib import Path

def clean_asterisk_artifacts(db_path: str):
    """Clean asterisk artifacts and Unknown values from database fields."""
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Cleaning asterisk artifacts and Unknown values in {db_path}")
    
    # Fields to clean
    fields_to_clean = [
        'future_signal',
        'time_to_impact', 
        'sentiment',
        'driver_type',
        'category',
        'title',
        'summary',
        'future_signal_explanation',
        'sentiment_explanation',
        'time_to_impact_explanation',
        'driver_type_explanation'
    ]
    
    total_cleaned = 0
    
    for field in fields_to_clean:
        print(f"\nCleaning field: {field}")
        
        # Find articles with asterisk artifacts or "Unknown" values
        cursor.execute(f"""
            SELECT uri, {field} 
            FROM articles 
            WHERE {field} IS NOT NULL 
            AND ({field} LIKE '**%' 
                 OR {field} LIKE '* %' 
                 OR {field} = 'Unknown'
                 OR {field} LIKE '%** %'
                 OR {field} LIKE '%**%**%')
        """)
        
        rows = cursor.fetchall()
        field_cleaned = 0
        
        for uri, original_value in rows:
            if not original_value:
                continue
                
            # Clean the value
            cleaned_value = clean_text_value(original_value)
            
            # Skip if value becomes "Unknown" after cleaning
            if cleaned_value == "Unknown" or cleaned_value.strip() == "":
                # Set to NULL instead of keeping "Unknown"
                cleaned_value = None
                
            if cleaned_value != original_value:
                cursor.execute(f"""
                    UPDATE articles 
                    SET {field} = ? 
                    WHERE uri = ?
                """, (cleaned_value, uri))
                
                field_cleaned += 1
                print(f"  Cleaned: '{original_value}' -> '{cleaned_value}'")
        
        total_cleaned += field_cleaned
        print(f"  {field_cleaned} records cleaned in {field}")
    
    # Commit changes
    conn.commit()
    
    # Show summary
    print(f"\n=== SUMMARY ===")
    print(f"Total records cleaned: {total_cleaned}")
    
    # Show remaining asterisk artifacts
    cursor.execute("""
        SELECT COUNT(*) 
        FROM articles 
        WHERE future_signal LIKE '**%' 
           OR future_signal LIKE '* %'
           OR time_to_impact LIKE '**%'
           OR time_to_impact LIKE '* %'
           OR sentiment LIKE '**%'
           OR sentiment LIKE '* %'
           OR driver_type LIKE '**%'
           OR driver_type LIKE '* %'
    """)
    
    remaining = cursor.fetchone()[0]
    print(f"Remaining asterisk artifacts: {remaining}")
    
    # Show "Unknown" values count
    cursor.execute("""
        SELECT COUNT(*) 
        FROM articles 
        WHERE future_signal = 'Unknown'
           OR time_to_impact = 'Unknown'
           OR sentiment = 'Unknown'
           OR driver_type = 'Unknown'
           OR category = 'Unknown'
    """)
    
    unknown_count = cursor.fetchone()[0]
    print(f"Remaining 'Unknown' values: {unknown_count}")
    
    # Show current future signal distribution after cleaning
    cursor.execute("""
        SELECT future_signal, COUNT(*) as count
        FROM articles 
        WHERE future_signal IS NOT NULL 
        AND future_signal != ''
        GROUP BY future_signal
        ORDER BY count DESC
        LIMIT 10
    """)
    
    print(f"\nTop 10 future signals after cleaning:")
    for signal, count in cursor.fetchall():
        print(f"  {signal}: {count}")
    
    conn.close()
    print(f"\nCleaning completed!")

def clean_text_value(text):
    """Clean a single text value of asterisk artifacts."""
    if not text:
        return text
    
    # Remove leading asterisks and spaces
    cleaned = re.sub(r'^[\*\s]+', '', text)
    
    # Remove trailing asterisks and spaces
    cleaned = re.sub(r'[\*\s]+$', '', cleaned)
    
    # Remove double asterisks (markdown bold)
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
    
    # Remove single asterisks at word boundaries
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    
    # Remove standalone asterisks
    cleaned = re.sub(r'\s\*\s', ' ', cleaned)
    
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Remove leading "The article" if it appears after cleaning
    cleaned = re.sub(r'^The article\s*', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()

if __name__ == "__main__":
    # Default database path
    db_path = "app/data/fnaapp.db"
    
    # Check if database exists
    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        print("Please check the path and try again.")
        exit(1)
    
    # Run the cleaning
    clean_asterisk_artifacts(db_path) 