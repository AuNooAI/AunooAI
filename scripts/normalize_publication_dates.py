#!/usr/bin/env python3
"""
Normalize all publication_date values to ISO format
Date: 2025-10-21
Issue: Multiple date formats in database causing inconsistent filtering
"""

import sys
import os
from datetime import datetime
from dateutil import parser as date_parser
import psycopg2
from psycopg2.extras import execute_batch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(
        host='localhost',
        database='test',
        user='test_user',
        password='ccPUs8wn/LvubZD4jLW7iK0S4kfYrdUc'
    )

def parse_date_safe(date_str):
    """
    Safely parse various date formats to ISO format string

    Handles:
    - "2025-10-21 04:06:04" -> "2025-10-21T04:06:04"
    - "2025-10-16T15:04:54Z" -> "2025-10-16T15:04:54Z"
    - "2025-10-20 06:50:44" -> "2025-10-20T06:50:44"
    - None/empty -> None
    """
    if not date_str or date_str.strip() == '':
        return None

    try:
        # Try to parse with dateutil (handles most formats)
        parsed = date_parser.parse(date_str)

        # Convert to ISO format
        # If it has timezone info, keep it; otherwise add Z for UTC assumption
        if parsed.tzinfo is not None:
            return parsed.isoformat()
        else:
            # Assume UTC for dates without timezone
            return parsed.isoformat() + 'Z'

    except Exception as e:
        print(f"ERROR: Could not parse date '{date_str}': {e}")
        return None

def analyze_current_formats(conn):
    """Analyze the current date formats in the database"""
    cursor = conn.cursor()

    print("\n=== Current Date Format Analysis ===")

    # Sample various date formats
    cursor.execute("""
        SELECT publication_date, COUNT(*) as count
        FROM articles
        WHERE publication_date IS NOT NULL AND publication_date != ''
        GROUP BY publication_date
        ORDER BY count DESC
        LIMIT 20
    """)

    print("\nMost common publication_date values:")
    for row in cursor.fetchall():
        print(f"  {row[0][:50]:50} (count: {row[1]})")

    # Count nulls/empties
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN publication_date IS NULL OR publication_date = '' THEN 1 END) as null_or_empty,
            COUNT(CASE WHEN publication_date IS NOT NULL AND publication_date != '' THEN 1 END) as has_value
        FROM articles
    """)

    stats = cursor.fetchone()
    print(f"\nOverall statistics:")
    print(f"  Total articles: {stats[0]}")
    print(f"  Null/Empty dates: {stats[1]}")
    print(f"  Has date value: {stats[2]}")

    cursor.close()

def normalize_dates(conn, batch_size=1000, dry_run=False):
    """Normalize all publication dates to ISO format"""
    cursor = conn.cursor()

    # Get all articles with publication_date
    cursor.execute("""
        SELECT uri, publication_date
        FROM articles
        WHERE publication_date IS NOT NULL AND publication_date != ''
        ORDER BY uri
    """)

    articles = cursor.fetchall()
    total = len(articles)

    print(f"\n=== {'DRY RUN: ' if dry_run else ''}Normalizing {total} publication dates ===")

    updates = []
    skipped = 0
    errors = 0

    for i, (uri, pub_date) in enumerate(articles, 1):
        # Parse and normalize
        normalized = parse_date_safe(pub_date)

        if normalized is None:
            skipped += 1
            continue

        # Only update if format changed
        if normalized != pub_date:
            updates.append((normalized, uri))

        # Progress indicator
        if i % 1000 == 0:
            print(f"  Processed {i}/{total} articles...")

    print(f"\nProcessing complete:")
    print(f"  Total articles: {total}")
    print(f"  Need updating: {len(updates)}")
    print(f"  Skipped (parsing failed): {skipped}")

    if updates and not dry_run:
        print(f"\nUpdating {len(updates)} articles in batches of {batch_size}...")

        update_cursor = conn.cursor()
        execute_batch(
            update_cursor,
            "UPDATE articles SET publication_date = %s WHERE uri = %s",
            updates,
            page_size=batch_size
        )

        conn.commit()
        update_cursor.close()

        print(f"✓ Updated {len(updates)} articles successfully")

    elif updates and dry_run:
        print(f"\nDRY RUN: Would update {len(updates)} articles")
        print("\nSample updates (first 10):")
        for normalized, uri in updates[:10]:
            cursor.execute("SELECT publication_date FROM articles WHERE uri = %s", (uri,))
            old_date = cursor.fetchone()[0]
            print(f"  {old_date} -> {normalized}")

    cursor.close()
    return len(updates), skipped

def verify_normalization(conn):
    """Verify all dates are in consistent format"""
    cursor = conn.cursor()

    print("\n=== Verification ===")

    # Check for non-ISO formats (heuristic: space between date and time)
    cursor.execute("""
        SELECT COUNT(*)
        FROM articles
        WHERE publication_date IS NOT NULL
        AND publication_date != ''
        AND publication_date LIKE '% %'
        AND publication_date NOT LIKE '%T%'
    """)

    non_iso = cursor.fetchone()[0]

    print(f"Articles with space-separated dates (non-ISO): {non_iso}")

    if non_iso == 0:
        print("✓ All dates appear to be in ISO format!")
    else:
        print("⚠ Some dates may still need normalization")

        # Sample problematic dates
        cursor.execute("""
            SELECT publication_date
            FROM articles
            WHERE publication_date IS NOT NULL
            AND publication_date != ''
            AND publication_date LIKE '% %'
            AND publication_date NOT LIKE '%T%'
            LIMIT 5
        """)

        print("\nSample non-ISO dates:")
        for row in cursor.fetchall():
            print(f"  {row[0]}")

    cursor.close()

def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Normalize publication dates to ISO format')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for updates (default: 1000)')
    args = parser.parse_args()

    try:
        print("Connecting to database...")
        conn = get_db_connection()

        # Analyze current state
        analyze_current_formats(conn)

        # Normalize dates
        updated, skipped = normalize_dates(conn, batch_size=args.batch_size, dry_run=args.dry_run)

        # Verify results
        if not args.dry_run and updated > 0:
            verify_normalization(conn)

        conn.close()

        print("\n✓ Migration complete!")

        if args.dry_run:
            print("\nThis was a DRY RUN. Run without --dry-run to apply changes.")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
