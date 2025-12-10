#!/usr/bin/env python3
"""
Migration script to copy topic data (keyword groups, keywords, articles, raw_articles,
and keyword_article_matches) from one tenant database to another.

Usage:
    python scripts/migrate_topic_data.py --source-db skunkworkx --target-db test --topic-id 74
"""

import argparse
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
import sys

# Database configurations
DB_CONFIGS = {
    "skunkworkx": {
        "host": "localhost",
        "port": 6432,
        "dbname": "skunkworkx",
        "user": "skunkworkx_user",
        "password": "d2HhLW8JLFUGDDg/4GhznpKKGQd4lXb2reioB+Bhreo="
    },
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


def get_next_keyword_group_id(target_conn):
    """Get the next available keyword_group ID in target database."""
    with target_conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM keyword_groups")
        return cur.fetchone()[0]


def migrate_keyword_group(source_conn, target_conn, source_topic_id, dry_run=False):
    """Migrate the keyword_group and return the new ID."""
    with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
        src_cur.execute(
            "SELECT name, topic, created_at, provider, source FROM keyword_groups WHERE id = %s",
            (source_topic_id,)
        )
        group = src_cur.fetchone()

        if not group:
            print(f"ERROR: Keyword group with id {source_topic_id} not found in source database")
            sys.exit(1)

        print(f"Found keyword group: {group['name']} (topic: {group['topic']})")

    # Check if this topic already exists in target
    with target_conn.cursor() as tgt_cur:
        tgt_cur.execute(
            "SELECT id FROM keyword_groups WHERE name = %s OR topic = %s",
            (group['name'], group['topic'])
        )
        existing = tgt_cur.fetchone()

        if existing:
            print(f"WARNING: Topic '{group['topic']}' already exists in target with id {existing[0]}")
            response = input("Do you want to use the existing group? (y/n): ")
            if response.lower() == 'y':
                return existing[0], group
            else:
                print("Aborting migration")
                sys.exit(1)

        new_id = get_next_keyword_group_id(target_conn)
        print(f"Will create keyword group with new id: {new_id}")

        if not dry_run:
            tgt_cur.execute(
                """INSERT INTO keyword_groups (id, name, topic, created_at, provider, source)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (new_id, group['name'], group['topic'], group['created_at'],
                 group['provider'], group['source'])
            )
            # Update the sequence
            tgt_cur.execute(
                "SELECT setval('keyword_groups_id_seq', GREATEST(nextval('keyword_groups_id_seq'), %s))",
                (new_id,)
            )

        return new_id, group


def migrate_monitored_keywords(source_conn, target_conn, source_group_id, target_group_id, dry_run=False):
    """Migrate monitored keywords for the group."""
    with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
        src_cur.execute(
            "SELECT keyword, created_at, last_checked FROM monitored_keywords WHERE group_id = %s",
            (source_group_id,)
        )
        keywords = src_cur.fetchall()

        print(f"Found {len(keywords)} monitored keywords to migrate")

    if not dry_run and keywords:
        with target_conn.cursor() as tgt_cur:
            for kw in keywords:
                tgt_cur.execute(
                    """INSERT INTO monitored_keywords (group_id, keyword, created_at, last_checked)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (group_id, keyword) DO NOTHING""",
                    (target_group_id, kw['keyword'], kw['created_at'], kw['last_checked'])
                )
            print(f"Inserted {len(keywords)} monitored keywords")

    return len(keywords)


def get_article_uris_for_group(source_conn, source_group_id):
    """Get all article URIs associated with the keyword group."""
    with source_conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT article_uri FROM keyword_article_matches WHERE group_id = %s",
            (source_group_id,)
        )
        return [row[0] for row in cur.fetchall()]


def migrate_articles(source_conn, target_conn, article_uris, dry_run=False):
    """Migrate articles, skipping duplicates."""
    if not article_uris:
        print("No articles to migrate")
        return 0, 0

    # Get existing URIs in target
    with target_conn.cursor() as tgt_cur:
        tgt_cur.execute("SELECT uri FROM articles WHERE uri = ANY(%s)", (article_uris,))
        existing_uris = set(row[0] for row in tgt_cur.fetchall())

    new_uris = [uri for uri in article_uris if uri not in existing_uris]
    print(f"Articles: {len(article_uris)} total, {len(existing_uris)} already exist, {len(new_uris)} to insert")

    if not new_uris:
        return len(existing_uris), 0

    # Fetch articles from source in batches
    batch_size = 500
    inserted = 0

    for i in range(0, len(new_uris), batch_size):
        batch_uris = new_uris[i:i+batch_size]

        with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
            src_cur.execute(
                """SELECT uri, title, news_source, publication_date, submission_date, summary,
                          category, future_signal, future_signal_explanation, sentiment,
                          sentiment_explanation, time_to_impact, time_to_impact_explanation,
                          tags, driver_type, driver_type_explanation, topic, analyzed,
                          bias, factual_reporting, mbfc_credibility_rating, bias_source,
                          bias_country, press_freedom, media_type, popularity,
                          topic_alignment_score, keyword_relevance_score, confidence_score,
                          overall_match_explanation, extracted_article_topics,
                          extracted_article_keywords, ingest_status, quality_score,
                          quality_issues, auto_ingested, created_by, embedding, url,
                          llm_status, llm_status_updated_at, llm_error_type, llm_error_message,
                          llm_processing_metadata
                   FROM articles WHERE uri = ANY(%s)""",
                (batch_uris,)
            )
            articles = src_cur.fetchall()

        if not dry_run and articles:
            with target_conn.cursor() as tgt_cur:
                for art in articles:
                    columns = list(art.keys())
                    values = [art[col] for col in columns]
                    placeholders = ', '.join(['%s'] * len(columns))
                    col_names = ', '.join(columns)

                    tgt_cur.execute(
                        f"INSERT INTO articles ({col_names}) VALUES ({placeholders}) ON CONFLICT (uri) DO NOTHING",
                        values
                    )
                inserted += len(articles)

        print(f"  Processed batch {i//batch_size + 1}: {len(articles)} articles")

    print(f"Inserted {inserted} new articles")
    return len(existing_uris), inserted


def migrate_raw_articles(source_conn, target_conn, article_uris, dry_run=False):
    """Migrate raw_articles for the given article URIs."""
    if not article_uris:
        print("No raw articles to migrate")
        return 0, 0

    # Get raw articles that exist in source
    with source_conn.cursor() as src_cur:
        src_cur.execute(
            "SELECT uri FROM raw_articles WHERE uri = ANY(%s)",
            (article_uris,)
        )
        source_raw_uris = [row[0] for row in src_cur.fetchall()]

    if not source_raw_uris:
        print("No raw articles found in source for these URIs")
        return 0, 0

    # Get existing raw articles in target
    with target_conn.cursor() as tgt_cur:
        tgt_cur.execute("SELECT uri FROM raw_articles WHERE uri = ANY(%s)", (source_raw_uris,))
        existing_uris = set(row[0] for row in tgt_cur.fetchall())

    new_uris = [uri for uri in source_raw_uris if uri not in existing_uris]
    print(f"Raw articles: {len(source_raw_uris)} in source, {len(existing_uris)} already exist, {len(new_uris)} to insert")

    if not new_uris:
        return len(existing_uris), 0

    # Fetch and insert in batches
    batch_size = 500
    inserted = 0

    for i in range(0, len(new_uris), batch_size):
        batch_uris = new_uris[i:i+batch_size]

        with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
            src_cur.execute(
                """SELECT uri, raw_markdown, submission_date, last_updated, topic
                   FROM raw_articles WHERE uri = ANY(%s)""",
                (batch_uris,)
            )
            raw_articles = src_cur.fetchall()

        if not dry_run and raw_articles:
            with target_conn.cursor() as tgt_cur:
                for ra in raw_articles:
                    tgt_cur.execute(
                        """INSERT INTO raw_articles (uri, raw_markdown, submission_date, last_updated, topic)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT (uri) DO NOTHING""",
                        (ra['uri'], ra['raw_markdown'], ra['submission_date'],
                         ra['last_updated'], ra['topic'])
                    )
                inserted += len(raw_articles)

        print(f"  Processed batch {i//batch_size + 1}: {len(raw_articles)} raw articles")

    print(f"Inserted {inserted} new raw articles")
    return len(existing_uris), inserted


def migrate_keyword_article_matches(source_conn, target_conn, source_group_id, target_group_id,
                                     article_uris, dry_run=False):
    """Migrate keyword_article_matches for the group."""
    if not article_uris:
        print("No keyword_article_matches to migrate")
        return 0

    with source_conn.cursor(cursor_factory=RealDictCursor) as src_cur:
        src_cur.execute(
            """SELECT article_uri, keyword_ids, detected_at, is_read, below_threshold
               FROM keyword_article_matches
               WHERE group_id = %s AND article_uri = ANY(%s)""",
            (source_group_id, article_uris)
        )
        matches = src_cur.fetchall()

    print(f"Found {len(matches)} keyword_article_matches to migrate")

    if not dry_run and matches:
        with target_conn.cursor() as tgt_cur:
            for m in matches:
                tgt_cur.execute(
                    """INSERT INTO keyword_article_matches
                       (article_uri, keyword_ids, group_id, detected_at, is_read, below_threshold)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (article_uri, group_id) DO NOTHING""",
                    (m['article_uri'], m['keyword_ids'], target_group_id,
                     m['detected_at'], m['is_read'], m['below_threshold'])
                )
        print(f"Inserted keyword_article_matches")

    return len(matches)


def main():
    parser = argparse.ArgumentParser(description='Migrate topic data between tenant databases')
    parser.add_argument('--source-db', required=True, help='Source database name')
    parser.add_argument('--target-db', required=True, help='Target database name')
    parser.add_argument('--topic-id', type=int, required=True, help='Source topic/keyword_group ID')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    args = parser.parse_args()

    if args.source_db not in DB_CONFIGS:
        print(f"ERROR: Unknown source database '{args.source_db}'")
        print(f"Available: {list(DB_CONFIGS.keys())}")
        sys.exit(1)

    if args.target_db not in DB_CONFIGS:
        print(f"ERROR: Unknown target database '{args.target_db}'")
        print(f"Available: {list(DB_CONFIGS.keys())}")
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN MODE - No changes will be made ===\n")

    print(f"Migrating topic ID {args.topic_id} from {args.source_db} to {args.target_db}\n")

    source_conn = get_connection(args.source_db)
    target_conn = get_connection(args.target_db)

    try:
        # Step 1: Migrate keyword_group
        print("=" * 60)
        print("Step 1: Migrating keyword_group")
        print("=" * 60)
        new_group_id, group_info = migrate_keyword_group(
            source_conn, target_conn, args.topic_id, args.dry_run
        )

        # Step 2: Migrate monitored_keywords
        print("\n" + "=" * 60)
        print("Step 2: Migrating monitored_keywords")
        print("=" * 60)
        migrate_monitored_keywords(
            source_conn, target_conn, args.topic_id, new_group_id, args.dry_run
        )

        # Step 3: Get article URIs
        print("\n" + "=" * 60)
        print("Step 3: Getting article URIs")
        print("=" * 60)
        article_uris = get_article_uris_for_group(source_conn, args.topic_id)
        print(f"Found {len(article_uris)} articles associated with this topic")

        # Step 4: Migrate articles
        print("\n" + "=" * 60)
        print("Step 4: Migrating articles")
        print("=" * 60)
        existing_articles, new_articles = migrate_articles(
            source_conn, target_conn, article_uris, args.dry_run
        )

        # Step 5: Migrate raw_articles
        print("\n" + "=" * 60)
        print("Step 5: Migrating raw_articles")
        print("=" * 60)
        existing_raw, new_raw = migrate_raw_articles(
            source_conn, target_conn, article_uris, args.dry_run
        )

        # Step 6: Migrate keyword_article_matches
        print("\n" + "=" * 60)
        print("Step 6: Migrating keyword_article_matches")
        print("=" * 60)
        matches_count = migrate_keyword_article_matches(
            source_conn, target_conn, args.topic_id, new_group_id, article_uris, args.dry_run
        )

        if not args.dry_run:
            target_conn.commit()
            print("\n" + "=" * 60)
            print("MIGRATION COMPLETE!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("DRY RUN COMPLETE - No changes were made")
            print("=" * 60)

        print(f"""
Summary:
  - Topic: {group_info['topic']}
  - New group ID in target: {new_group_id}
  - Articles: {existing_articles} existing + {new_articles} new = {existing_articles + new_articles} total
  - Raw articles: {existing_raw} existing + {new_raw} new
  - Keyword matches: {matches_count}
""")

    except Exception as e:
        target_conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    main()
