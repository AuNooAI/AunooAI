"""
Import policy tracker CSV data into the database.

This script imports pre-categorized Trump administration actions from the CSV file
into the policy_article_categories table.

Usage:
    python scripts/import_policy_tracker_csv.py [--dry-run] [--import-articles]

Options:
    --dry-run         Preview what would be imported without making changes
    --import-articles Import CSV rows as new articles if they don't exist
"""

import csv
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import get_database_instance

# CSV file path
CSV_FILE = "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"

# Topic for the policy tracker
TOPIC = "Trump Administration Tracker"

# Map CSV column names to our policy category names
CSV_TO_CATEGORY_MAP = {
    "Violating Democratic Norms, Undermining Rule of Law": ["Democratic Norms", "Rule of Law"],
    "Hollowing State / Weakening Federal Institutions": ["Hollowing State"],
    "Suppressing Dissent / Weaponising State Against 'Enemies'": ["Suppressing Dissent"],
    "Controlling Information Including Spreading Misinformation and Propaganda": ["Controlling Information"],
    "Control of Science & Health to Align with State Ideology": ["Science & Health Control"],
    "Attacking Universities, Schools, Museums, Culture": ["Attacking Education"],
    "Weakening Civil Rights": ["Weakening Civil Rights"],
    "Corruption & Enrichment": ["Corruption & Enrichment"],
    "Aggressive Foreign Policy & Global Destabilisation": ["Foreign Policy / Nationalism"],
    "Anti-immigrant or Militarised Nationalism": ["Foreign Policy / Nationalism"],
}


def parse_date(date_str):
    """Parse date string from CSV."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError:
            return None


def import_csv(dry_run=False, import_articles=False):
    """Import CSV data into the database."""
    db = get_database_instance()
    conn = db._temp_get_connection()

    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), CSV_FILE)

    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    print(f"Reading CSV from: {csv_path}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE IMPORT'}")
    print(f"Import articles: {import_articles}")
    print("-" * 60)

    stats = {
        "rows_processed": 0,
        "articles_found": 0,
        "articles_created": 0,
        "categories_added": 0,
        "categories_skipped": 0,
        "errors": 0
    }

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            # Skip metadata lines at the top (citation + empty line)
            lines = f.readlines()

            # Find the header row (starts with "Index,")
            header_idx = 0
            for i, line in enumerate(lines):
                if line.strip().startswith("Index,"):
                    header_idx = i
                    break

            print(f"Found header at line {header_idx + 1}")

            # Parse from header onwards
            from io import StringIO
            csv_content = ''.join(lines[header_idx:])
            reader = csv.DictReader(StringIO(csv_content))

            for row in reader:
                stats["rows_processed"] += 1

                url = row.get("URL", "").strip()
                title = row.get("Title", "").strip()
                date_str = row.get("Date", "").strip()

                if not url or not title:
                    print(f"Skipping row {stats['rows_processed']}: missing URL or title")
                    continue

                # Use URL as the article URI
                article_uri = url
                pub_date = parse_date(date_str)

                # Check if article exists
                result = conn.execute(text("""
                    SELECT uri FROM articles WHERE uri = :uri
                """), {"uri": article_uri})
                article_exists = result.fetchone() is not None

                if article_exists:
                    stats["articles_found"] += 1
                elif import_articles:
                    # Create article
                    if not dry_run:
                        try:
                            conn.execute(text("""
                                INSERT INTO articles (uri, title, summary, topic, publication_date, news_source)
                                VALUES (:uri, :title, :summary, :topic, :pub_date, :source)
                                ON CONFLICT (uri) DO NOTHING
                            """), {
                                "uri": article_uri,
                                "title": title,
                                "summary": title,  # Use title as summary
                                "topic": TOPIC,
                                "pub_date": pub_date,
                                "source": "Trump Action Tracker"
                            })
                            conn.commit()
                            stats["articles_created"] += 1
                            print(f"Created article: {title[:50]}...")
                        except Exception as e:
                            print(f"Error creating article: {e}")
                            stats["errors"] += 1
                            continue
                    else:
                        stats["articles_created"] += 1
                        print(f"Would create article: {title[:50]}...")
                else:
                    # Skip - article doesn't exist and we're not importing
                    continue

                # Extract categories from Yes/No columns
                categories = []
                for csv_col, category_names in CSV_TO_CATEGORY_MAP.items():
                    value = row.get(csv_col, "").strip().lower()
                    if value == "yes":
                        categories.extend(category_names)

                # Remove duplicates (e.g., Foreign Policy might appear twice)
                categories = list(set(categories))

                if not categories:
                    continue

                # Store categories
                for category in categories:
                    if not dry_run:
                        try:
                            conn.execute(text("""
                                INSERT INTO policy_article_categories
                                (article_uri, category, topic, classification_method)
                                VALUES (:uri, :category, :topic, 'csv_import')
                                ON CONFLICT (article_uri, category) DO NOTHING
                            """), {
                                "uri": article_uri,
                                "category": category,
                                "topic": TOPIC
                            })
                            stats["categories_added"] += 1
                        except Exception as e:
                            print(f"Error storing category: {e}")
                            stats["categories_skipped"] += 1
                    else:
                        stats["categories_added"] += 1

                if stats["rows_processed"] % 100 == 0:
                    print(f"Processed {stats['rows_processed']} rows...")
                    if not dry_run:
                        conn.commit()

        if not dry_run:
            conn.commit()

        print("-" * 60)
        print("Import Summary:")
        print(f"  Rows processed: {stats['rows_processed']}")
        print(f"  Existing articles found: {stats['articles_found']}")
        print(f"  Articles created: {stats['articles_created']}")
        print(f"  Categories added: {stats['categories_added']}")
        print(f"  Categories skipped: {stats['categories_skipped']}")
        print(f"  Errors: {stats['errors']}")

    except Exception as e:
        print(f"Error during import: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    import_articles = "--import-articles" in sys.argv

    import_csv(dry_run=dry_run, import_articles=import_articles)
