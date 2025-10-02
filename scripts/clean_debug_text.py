#!/usr/bin/env python3
"""
Clean DEBUG text from article fields in the database.
This removes the 'DEBUG: ||||' text that was accidentally written to articles.
"""

import sqlite3
import re
import os

def clean_debug_text():
    """Remove DEBUG text from article fields"""

    # Get database path - try both common names
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, 'app', 'data', 'fnaapp.db')

    if not os.path.exists(db_path):
        db_path = os.path.join(base_dir, 'app', 'data', 'articles.db')

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    # Pattern to match DEBUG text like "DEBUG: value1|value2|value3|value4|value5"
    debug_pattern = re.compile(r'DEBUG:\s*[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^\s]*\s*')

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Searching for articles with DEBUG text...")

    # Get all articles
    cursor.execute("SELECT COUNT(*) FROM articles")
    total_count = cursor.fetchone()[0]
    print(f"Found {total_count} total articles")

    # Find articles with DEBUG text in any field
    # Note: Only checking fields that exist in the articles table schema
    fields_to_check = ['title', 'summary', 'category', 'sentiment', 'driver_type', 'time_to_impact']
    cleaned_count = 0

    for field in fields_to_check:
        cursor.execute(f"SELECT uri, {field} FROM articles WHERE {field} LIKE '%DEBUG:%'")
        articles = cursor.fetchall()

        if articles:
            print(f"\nFound {len(articles)} articles with DEBUG text in {field}")

            for article_uri, value in articles:
                if value and 'DEBUG:' in value:
                    # Remove the DEBUG text
                    cleaned_value = debug_pattern.sub('', value).strip()

                    if cleaned_value != value:
                        # Update the article
                        cursor.execute(f"UPDATE articles SET {field} = ? WHERE uri = ?",
                                     (cleaned_value, article_uri))
                        print(f"  ✓ Cleaned {field} in article {article_uri}")
                        cleaned_count += 1

    # Commit changes
    conn.commit()
    conn.close()

    print(f"\nCleaning complete!")
    print(f"Total field updates: {cleaned_count}")
    print(f"Total articles checked: {total_count}")

if __name__ == "__main__":
    print("=" * 60)
    print("Article DEBUG Text Cleanup Script")
    print("=" * 60)
    print()

    clean_debug_text()

    print()
    print("=" * 60)
    print("Cleanup finished!")
    print("=" * 60)
