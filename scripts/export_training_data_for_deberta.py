#!/usr/bin/env python3
"""
Export Training Data for DeBERTa

Exports samples from enrichment_training_samples table to JSON files
for train_enrichment_model.py to consume.

Usage:
    python scripts/export_training_data_for_deberta.py
    python scripts/export_training_data_for_deberta.py --min-samples 100

Output:
    data/training/enrichment_train.json
    data/training/enrichment_val.json
    data/training/enrichment_test.json
    data/training/label_mappings.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Database

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "training"

ENRICHMENT_FIELDS = ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']


def parse_args():
    parser = argparse.ArgumentParser(description='Export training data for DeBERTa')
    parser.add_argument('--min-samples', type=int, default=50,
                        help='Minimum samples per label value (default: 50)')
    parser.add_argument('--test-size', type=float, default=0.1,
                        help='Test split ratio (default: 0.1)')
    parser.add_argument('--val-size', type=float, default=0.1,
                        help='Validation split ratio (default: 0.1)')
    parser.add_argument('--topics', type=str, nargs='*',
                        help='Specific topics to include (default: all)')
    return parser.parse_args()


def export_training_data(
    min_samples: int = 50,
    test_size: float = 0.1,
    val_size: float = 0.1,
    topics: list = None,
):
    """Export training samples from database to JSON files."""
    db = Database()

    logger.info("Fetching training samples from database...")

    # Build query
    query = """
        SELECT
            e.article_uri,
            a.title,
            a.summary,
            e.topic,
            e.field_name,
            e.field_value,
            e.confidence
        FROM enrichment_training_samples e
        JOIN articles a ON e.article_uri = a.uri
        WHERE e.field_value IS NOT NULL
          AND e.field_value != ''
          AND a.title IS NOT NULL
    """
    params = {}

    if topics:
        placeholders = ', '.join(f':topic_{i}' for i in range(len(topics)))
        query += f" AND e.topic IN ({placeholders})"
        for i, topic in enumerate(topics):
            params[f'topic_{i}'] = topic

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    logger.info(f"Fetched {len(rows)} field-level samples")

    # Pivot data: one row per article with all fields
    articles = defaultdict(lambda: {
        'uri': None, 'title': None, 'summary': None, 'topic': None,
        'sentiment': None, 'time_to_impact': None,
        'driver_type': None, 'future_signal': None
    })

    for row in rows:
        uri, title, summary, topic, field_name, field_value, confidence = row
        articles[uri]['uri'] = uri
        articles[uri]['title'] = title
        articles[uri]['summary'] = summary or ''
        articles[uri]['topic'] = topic
        if field_name in ENRICHMENT_FIELDS:
            articles[uri][field_name] = field_value

    # Convert to DataFrame
    df = pd.DataFrame(list(articles.values()))
    logger.info(f"Converted to {len(df)} article records")

    # Filter out articles missing any field
    for field in ENRICHMENT_FIELDS:
        df = df[df[field].notna() & (df[field] != '')]

    logger.info(f"After filtering incomplete records: {len(df)} articles")

    # Build label mappings and filter rare labels
    label_mappings = {}

    for field in ENRICHMENT_FIELDS:
        value_counts = df[field].value_counts()
        valid_values = value_counts[value_counts >= min_samples].index.tolist()

        if len(valid_values) < len(value_counts):
            removed = set(value_counts.index) - set(valid_values)
            logger.warning(f"Field '{field}': removing rare values (<{min_samples}): {removed}")
            df = df[df[field].isin(valid_values)]

        # Create mapping
        values = sorted(df[field].unique())
        label2id = {v: i for i, v in enumerate(values)}
        id2label = {i: v for v, i in label2id.items()}

        label_mappings[field] = {
            'num_labels': len(values),
            'values': values,
            'label2id': label2id,
            'id2label': id2label,
        }

        logger.info(f"Field '{field}': {len(values)} labels, {df[field].value_counts().sum()} samples")

    logger.info(f"Final dataset: {len(df)} articles")

    # Split data
    train_df, temp_df = train_test_split(df, test_size=(test_size + val_size), random_state=42)
    val_df, test_df = train_test_split(temp_df, test_size=test_size/(test_size + val_size), random_state=42)

    logger.info(f"Split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # Save files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    train_df.to_json(OUTPUT_DIR / "enrichment_train.json", orient='records', indent=2)
    val_df.to_json(OUTPUT_DIR / "enrichment_val.json", orient='records', indent=2)
    test_df.to_json(OUTPUT_DIR / "enrichment_test.json", orient='records', indent=2)

    with open(OUTPUT_DIR / "label_mappings.json", 'w') as f:
        json.dump(label_mappings, f, indent=2)

    logger.info(f"\nExported to {OUTPUT_DIR}:")
    logger.info(f"  - enrichment_train.json ({len(train_df)} samples)")
    logger.info(f"  - enrichment_val.json ({len(val_df)} samples)")
    logger.info(f"  - enrichment_test.json ({len(test_df)} samples)")
    logger.info(f"  - label_mappings.json")

    # Print label distribution summary
    print("\n" + "="*60)
    print("LABEL DISTRIBUTION SUMMARY")
    print("="*60)

    for field in ENRICHMENT_FIELDS:
        print(f"\n{field}:")
        for value, count in train_df[field].value_counts().items():
            print(f"  {value}: {count}")

    return train_df, val_df, test_df, label_mappings


def main():
    args = parse_args()

    export_training_data(
        min_samples=args.min_samples,
        test_size=args.test_size,
        val_size=args.val_size,
        topics=args.topics,
    )


if __name__ == "__main__":
    main()
