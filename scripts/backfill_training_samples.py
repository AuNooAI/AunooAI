#!/usr/bin/env python3
"""
Backfill Training Samples

Populates the enrichment_training_samples and training_sample_counts tables
from existing analyzed articles in the database.

Usage:
    python scripts/backfill_training_samples.py [--limit N] [--topic "Topic Name"]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ENRICHMENT_FIELDS = ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']


def backfill_training_samples(limit: int = None, topic: str = None, batch_size: int = 1000):
    """Backfill training samples from existing analyzed articles."""
    db = Database()

    # Build query
    query = """
        SELECT uri, topic, sentiment, time_to_impact, driver_type, future_signal
        FROM articles
        WHERE topic IS NOT NULL
          AND topic != ''
          AND analyzed = true
    """
    params = {}

    if topic:
        query += " AND topic = :topic_filter"
        params['topic_filter'] = topic

    query += " ORDER BY submission_date DESC"

    if limit:
        query += f" LIMIT {limit}"

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get total count
        count_query = """
            SELECT COUNT(*) FROM articles
            WHERE topic IS NOT NULL AND topic != '' AND analyzed = true
        """
        if topic:
            count_query += " AND topic = :topic_filter"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        logger.info(f"Found {total} analyzed articles to process")

        # Fetch articles
        cursor.execute(query, params if params else {})
        articles = cursor.fetchall()

        inserted = 0
        updated_counts = {}

        for i, article in enumerate(articles):
            uri, art_topic, sentiment, time_to_impact, driver_type, future_signal = article

            values = {
                'sentiment': sentiment,
                'time_to_impact': time_to_impact,
                'driver_type': driver_type,
                'future_signal': future_signal,
            }

            for field, value in values.items():
                if value and value.strip():
                    try:
                        # Insert training sample
                        cursor.execute("""
                            INSERT INTO enrichment_training_samples
                            (article_uri, topic, field_name, field_value, source, confidence)
                            VALUES (:uri, :topic, :field, :value, :source, :confidence)
                            ON CONFLICT (article_uri, field_name) DO NOTHING
                        """, {
                            'uri': uri,
                            'topic': art_topic,
                            'field': field,
                            'value': value.strip(),
                            'source': 'backfill',
                            'confidence': 0.9
                        })

                        if cursor.rowcount > 0:
                            inserted += 1
                            # Track counts for aggregation
                            key = (art_topic, field, value.strip())
                            updated_counts[key] = updated_counts.get(key, 0) + 1

                    except Exception as e:
                        logger.warning(f"Error inserting sample for {uri}/{field}: {e}")

            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.info(f"Processed {i + 1}/{len(articles)} articles, {inserted} samples inserted")

        conn.commit()
        logger.info(f"Inserted {inserted} training samples")

        # Update aggregated counts
        logger.info("Updating aggregated counts...")
        for (topic_name, field, value), count in updated_counts.items():
            cursor.execute("""
                INSERT INTO training_sample_counts (topic, field_name, field_value, sample_count, last_updated)
                VALUES (:topic, :field, :value, :count, NOW())
                ON CONFLICT (topic, field_name, field_value)
                DO UPDATE SET
                    sample_count = training_sample_counts.sample_count + EXCLUDED.sample_count,
                    last_updated = NOW()
            """, {'topic': topic_name, 'field': field, 'value': value, 'count': count})

        conn.commit()
        logger.info(f"Updated {len(updated_counts)} count aggregations")

        # Show summary
        cursor.execute("""
            SELECT topic, field_name, SUM(sample_count) as total
            FROM training_sample_counts
            GROUP BY topic, field_name
            ORDER BY topic, field_name
        """)

        print("\n" + "="*60)
        print("TRAINING SAMPLE COUNTS BY TOPIC AND FIELD")
        print("="*60)

        current_topic = None
        for row in cursor.fetchall():
            topic_name, field, total = row
            if topic_name != current_topic:
                if current_topic:
                    print()
                print(f"\n{topic_name}:")
                current_topic = topic_name
            print(f"  {field}: {total}")

        print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(description='Backfill training samples from existing articles')
    parser.add_argument('--limit', type=int, help='Limit number of articles to process')
    parser.add_argument('--topic', type=str, help='Only process specific topic')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for commits')

    args = parser.parse_args()

    backfill_training_samples(
        limit=args.limit,
        topic=args.topic,
        batch_size=args.batch_size,
    )


if __name__ == '__main__':
    main()
