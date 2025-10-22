#!/usr/bin/env python3
"""
Script to consolidate duplicate 'Patent Cliffs' topics.
Fixes 'Patent Cliffs ' (with trailing space) to 'Patent Cliffs'.
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_database_instance
from sqlalchemy import text

def fix_patent_cliffs_topics():
    """Update all articles with 'Patent Cliffs ' (trailing space) to 'Patent Cliffs'."""
    db = get_database_instance()

    print("Checking current state...")

    # Get SQLAlchemy connection
    conn = db._temp_get_connection()

    # Check current state
    result = conn.execute(text("""
        SELECT topic, LENGTH(topic) as len, COUNT(*) as count
        FROM articles
        WHERE topic LIKE 'Patent Cliffs%'
        GROUP BY topic, LENGTH(topic)
        ORDER BY LENGTH(topic), topic
    """))
    rows = result.fetchall()

    print("\nBefore fix:")
    for row in rows:
        print(f"  Topic: '{row.topic}' (len={row.len}) - {row.count} articles")

    # Update articles with trailing space
    print("\nUpdating articles...")
    result = conn.execute(text("""
        UPDATE articles
        SET topic = 'Patent Cliffs'
        WHERE LENGTH(topic) = 14 AND topic LIKE 'Patent Cliffs%'
    """))
    conn.commit()
    updated = result.rowcount
    print(f"Updated {updated} articles")

    # Verify the fix
    print("\nVerifying fix...")
    result = conn.execute(text("""
        SELECT topic, LENGTH(topic) as len, COUNT(*) as count
        FROM articles
        WHERE topic LIKE 'Patent Cliffs%'
        GROUP BY topic, LENGTH(topic)
        ORDER BY LENGTH(topic), topic
    """))
    rows = result.fetchall()

    print("\nAfter fix:")
    for row in rows:
        print(f"  Topic: '{row.topic}' (len={row.len}) - {row.count} articles")

    print("\n✓ Patent Cliffs topics consolidated successfully!")

if __name__ == "__main__":
    fix_patent_cliffs_topics()
