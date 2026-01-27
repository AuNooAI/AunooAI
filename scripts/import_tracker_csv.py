#!/usr/bin/env python3
"""
Import Trump Action Tracker CSV data into policy_article_categories.
Maps articles by URL and imports hand-curated category classifications.
"""

import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.database import get_database_instance

# Map CSV column names to our category names
CSV_TO_CATEGORY_MAP = {
    "Violating Democratic Norms, Undermining Rule of Law": ["Undermining Democracy"],
    "Hollowing State / Weakening Federal Institutions": ["Hollowing State"],
    "Suppressing Dissent / Weaponising State Against 'Enemies'": ["Suppressing Dissent"],
    "Controlling Information Including Spreading Misinformation and Propaganda": ["Controlling Information"],
    "Control of Science & Health to Align with State Ideology": ["Attacking Science"],
    "Attacking Universities, Schools, Museums, Culture": ["Attacking Education"],
    "Weakening Civil Rights": ["Weakening Civil Rights"],
    "Corruption & Enrichment": ["Corruption"],
    "Aggressive Foreign Policy & Global Destabilisation": ["Foreign Policy"],
    "Nationalism & Immigration": ["Nationalism & Immigration"],
}

TOPIC = "Trump Administration Tracker"
CSV_PATH = "/home/orochford/tenants/bugfixing.aunoo.ai/spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"


def main():
    db = get_database_instance()
    conn = db._temp_get_connection()

    # Read CSV
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        # Skip the copyright header line and empty line
        next(f)  # copyright
        next(f)  # empty line
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Read {len(rows)} rows from CSV")

    # Get all article URIs for this topic
    result = conn.execute(text("""
        SELECT uri FROM articles WHERE topic = :topic
    """), {"topic": TOPIC})
    existing_uris = {row[0] for row in result.fetchall()}
    print(f"Found {len(existing_uris)} articles in database for topic '{TOPIC}'")

    matched = 0
    categories_added = 0
    not_found = 0

    for row in rows:
        url = row.get('URL', '').strip()
        if not url:
            continue

        # Check if article exists
        if url not in existing_uris:
            not_found += 1
            continue

        matched += 1

        # Process each category column
        for csv_col, our_categories in CSV_TO_CATEGORY_MAP.items():
            value = row.get(csv_col, '').strip().lower()
            if value == 'yes':
                for category in our_categories:
                    try:
                        conn.execute(text("""
                            INSERT INTO policy_article_categories (article_uri, category, topic, confidence, classification_method)
                            VALUES (:uri, :category, :topic, 1.0, 'csv_import')
                            ON CONFLICT (article_uri, category) DO NOTHING
                        """), {"uri": url, "category": category, "topic": TOPIC})
                        categories_added += 1
                    except Exception as e:
                        print(f"Error inserting {category} for {url}: {e}")

    conn.commit()
    conn.close()

    print(f"""
Import complete:
  CSV rows: {len(rows)}
  Matched articles: {matched}
  Not found in DB: {not_found}
  Categories added: {categories_added}
""")


if __name__ == "__main__":
    main()
