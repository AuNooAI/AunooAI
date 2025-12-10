#!/usr/bin/env python3
"""
Import script to load Geopolitical Hotspots topic data from CSV exports.

Usage:
    # First, extract the tarball:
    tar -xzvf /tmp/geopolitics_export.tar.gz -C /tmp/

    # Then run this script:
    python scripts/import_geopolitics_topic.py --target-db test --export-dir /tmp/geopolitics_export
"""

import argparse
import csv
import psycopg2
from psycopg2.extras import execute_values
import sys
import os

# Database configurations
DB_CONFIGS = {
    "test": {
        "host": "localhost",
        "port": 5432,
        "dbname": "test",
        "user": "test_user",
        "password": "ccPUs8wn/LvubZD4jLW7iK0S4kfYrdUc"
    },
    "wileytest": {
        "host": "localhost",
        "port": 5432,
        "dbname": "wileytest",
        "user": "wileytest_user",
        "password": "ZtG/Z0GfKeRhH3nfbnMWdXsRvOKtDm9b"
    }
}


def get_connection(db_name):
    """Get a database connection."""
    config = DB_CONFIGS[db_name]
    return psycopg2.connect(**config)


def get_next_keyword_group_id(conn):
    """Get the next available keyword_group ID."""
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM keyword_groups")
        return cur.fetchone()[0]


def import_keyword_group(conn, export_dir, dry_run=False):
    """Import the keyword_group and return the new ID and original ID."""
    csv_path = os.path.join(export_dir, "keyword_groups.csv")

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        row = next(reader)

    original_id = int(row['id'])
    print(f"Found keyword group: {row['name']} (topic: {row['topic']}, original id: {original_id})")

    # Check if topic already exists
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM keyword_groups WHERE name = %s OR topic = %s",
            (row['name'], row['topic'])
        )
        existing = cur.fetchone()

        if existing:
            print(f"WARNING: Topic '{row['topic']}' already exists with id {existing[0]}")
            response = input("Use existing group? (y/n): ")
            if response.lower() == 'y':
                return existing[0], original_id
            else:
                print("Aborting")
                sys.exit(1)

        new_id = get_next_keyword_group_id(conn)
        print(f"Will create keyword group with new id: {new_id}")

        if not dry_run:
            cur.execute(
                """INSERT INTO keyword_groups (id, name, topic, created_at, provider, source)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (new_id, row['name'], row['topic'], row.get('created_at'),
                 row.get('provider'), row.get('source'))
            )
            cur.execute(
                "SELECT setval('keyword_groups_id_seq', GREATEST(nextval('keyword_groups_id_seq'), %s))",
                (new_id,)
            )

        return new_id, original_id


def import_monitored_keywords(conn, export_dir, new_group_id, dry_run=False):
    """Import monitored keywords."""
    csv_path = os.path.join(export_dir, "monitored_keywords.csv")

    if not os.path.exists(csv_path):
        print("No monitored_keywords.csv found, skipping")
        return 0

    keywords = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        keywords = list(reader)

    print(f"Found {len(keywords)} monitored keywords to import")

    if not dry_run and keywords:
        with conn.cursor() as cur:
            for kw in keywords:
                cur.execute(
                    """INSERT INTO monitored_keywords (group_id, keyword, created_at, last_checked)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (group_id, keyword) DO NOTHING""",
                    (new_group_id, kw['keyword'], kw.get('created_at'), kw.get('last_checked'))
                )
        print(f"Inserted {len(keywords)} monitored keywords")

    return len(keywords)


def import_articles(conn, export_dir, dry_run=False):
    """Import articles, skipping duplicates."""
    csv_path = os.path.join(export_dir, "articles.csv")

    if not os.path.exists(csv_path):
        print("No articles.csv found, skipping")
        return 0, 0

    # Read all articles
    articles = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        articles = list(reader)

    if not articles:
        print("No articles to import")
        return 0, 0

    # Get existing URIs
    uris = [a['uri'] for a in articles]
    with conn.cursor() as cur:
        cur.execute("SELECT uri FROM articles WHERE uri = ANY(%s)", (uris,))
        existing_uris = set(row[0] for row in cur.fetchall())

    new_articles = [a for a in articles if a['uri'] not in existing_uris]
    print(f"Articles: {len(articles)} total, {len(existing_uris)} already exist, {len(new_articles)} to insert")

    if not dry_run and new_articles:
        with conn.cursor() as cur:
            # Get column names from first article, excluding empty values
            for art in new_articles:
                # Filter out empty/None values and handle special fields
                cols = []
                vals = []
                for k, v in art.items():
                    if v is not None and v != '':
                        cols.append(k)
                        # Handle boolean fields
                        if k in ('analyzed', 'auto_ingested'):
                            vals.append(v.lower() in ('true', 't', '1', 'yes') if v else None)
                        # Handle numeric fields
                        elif k in ('topic_alignment_score', 'keyword_relevance_score',
                                   'confidence_score', 'quality_score'):
                            vals.append(float(v) if v else None)
                        else:
                            vals.append(v)

                if cols:
                    placeholders = ', '.join(['%s'] * len(cols))
                    col_names = ', '.join(cols)
                    cur.execute(
                        f"INSERT INTO articles ({col_names}) VALUES ({placeholders}) ON CONFLICT (uri) DO NOTHING",
                        vals
                    )
        print(f"Inserted {len(new_articles)} new articles")

    return len(existing_uris), len(new_articles)


def import_raw_articles(conn, export_dir, dry_run=False):
    """Import raw_articles."""
    csv_path = os.path.join(export_dir, "raw_articles.csv")

    if not os.path.exists(csv_path):
        print("No raw_articles.csv found, skipping")
        return 0, 0

    raw_articles = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        raw_articles = list(reader)

    if not raw_articles:
        print("No raw articles to import")
        return 0, 0

    # Get existing URIs
    uris = [r['uri'] for r in raw_articles]
    with conn.cursor() as cur:
        cur.execute("SELECT uri FROM raw_articles WHERE uri = ANY(%s)", (uris,))
        existing_uris = set(row[0] for row in cur.fetchall())

    new_raw = [r for r in raw_articles if r['uri'] not in existing_uris]
    print(f"Raw articles: {len(raw_articles)} total, {len(existing_uris)} already exist, {len(new_raw)} to insert")

    if not dry_run and new_raw:
        with conn.cursor() as cur:
            for ra in new_raw:
                cur.execute(
                    """INSERT INTO raw_articles (uri, raw_markdown, submission_date, last_updated, topic)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (uri) DO NOTHING""",
                    (ra['uri'], ra.get('raw_markdown'), ra.get('submission_date'),
                     ra.get('last_updated'), ra.get('topic'))
                )
        print(f"Inserted {len(new_raw)} new raw articles")

    return len(existing_uris), len(new_raw)


def import_keyword_article_matches(conn, export_dir, new_group_id, dry_run=False):
    """Import keyword_article_matches."""
    csv_path = os.path.join(export_dir, "keyword_article_matches.csv")

    if not os.path.exists(csv_path):
        print("No keyword_article_matches.csv found, skipping")
        return 0

    matches = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        matches = list(reader)

    print(f"Found {len(matches)} keyword_article_matches to import")

    if not dry_run and matches:
        with conn.cursor() as cur:
            for m in matches:
                # Handle boolean/integer fields
                is_read = int(m.get('is_read', 0) or 0) if m.get('is_read') else None
                below_threshold = int(m.get('below_threshold', 0) or 0) if m.get('below_threshold') else None

                cur.execute(
                    """INSERT INTO keyword_article_matches
                       (article_uri, keyword_ids, group_id, detected_at, is_read, below_threshold)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (article_uri, group_id) DO NOTHING""",
                    (m['article_uri'], m.get('keyword_ids'), new_group_id,
                     m.get('detected_at'), is_read, below_threshold)
                )
        print(f"Inserted keyword_article_matches")

    return len(matches)


def main():
    parser = argparse.ArgumentParser(description='Import topic data from CSV exports')
    parser.add_argument('--target-db', required=True, help='Target database name')
    parser.add_argument('--export-dir', required=True, help='Directory containing CSV exports')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')

    args = parser.parse_args()

    if args.target_db not in DB_CONFIGS:
        print(f"ERROR: Unknown database '{args.target_db}'")
        print(f"Available: {list(DB_CONFIGS.keys())}")
        sys.exit(1)

    if not os.path.exists(args.export_dir):
        print(f"ERROR: Export directory '{args.export_dir}' does not exist")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN MODE ===\n")

    print(f"Importing from {args.export_dir} to {args.target_db}\n")

    conn = get_connection(args.target_db)

    try:
        # Step 1: Import keyword_group
        print("=" * 60)
        print("Step 1: Importing keyword_group")
        print("=" * 60)
        new_group_id, original_id = import_keyword_group(conn, args.export_dir, args.dry_run)

        # Step 2: Import monitored_keywords
        print("\n" + "=" * 60)
        print("Step 2: Importing monitored_keywords")
        print("=" * 60)
        import_monitored_keywords(conn, args.export_dir, new_group_id, args.dry_run)

        # Step 3: Import articles
        print("\n" + "=" * 60)
        print("Step 3: Importing articles")
        print("=" * 60)
        existing_articles, new_articles = import_articles(conn, args.export_dir, args.dry_run)

        # Step 4: Import raw_articles
        print("\n" + "=" * 60)
        print("Step 4: Importing raw_articles")
        print("=" * 60)
        existing_raw, new_raw = import_raw_articles(conn, args.export_dir, args.dry_run)

        # Step 5: Import keyword_article_matches
        print("\n" + "=" * 60)
        print("Step 5: Importing keyword_article_matches")
        print("=" * 60)
        matches_count = import_keyword_article_matches(conn, args.export_dir, new_group_id, args.dry_run)

        if not args.dry_run:
            conn.commit()
            print("\n" + "=" * 60)
            print("IMPORT COMPLETE!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("DRY RUN COMPLETE")
            print("=" * 60)

        print(f"""
Summary:
  - New group ID: {new_group_id}
  - Articles: {existing_articles} existing + {new_articles} new
  - Raw articles: {existing_raw} existing + {new_raw} new
  - Keyword matches: {matches_count}
""")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
