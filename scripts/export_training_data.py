#!/usr/bin/env python3
"""
Export enriched articles from database for SLM training.

This script exports training data for three types of models:
1. Relevance Classifier - Binary classification (approved vs filtered)
2. Summarizer - Article text to summary mapping
3. Multi-task Enrichment - Sentiment, time_to_impact, driver_type, category, future_signal

The first ~2000 articles from the AI topic are human-curated (gold labels).

Usage:
    python scripts/export_training_data.py

    # Export from specific database
    python scripts/export_training_data.py --database wileytest

    # Export only specific datasets
    python scripts/export_training_data.py --relevance --summarization

Outputs:
    data/training/relevance_train.json
    data/training/relevance_val.json
    data/training/relevance_test.json
    data/training/summarization_train.json
    data/training/summarization_val.json
    data/training/summarization_test.json
    data/training/enrichment_train.json
    data/training/enrichment_val.json
    data/training/enrichment_test.json
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sklearn.model_selection import train_test_split
from sqlalchemy import create_engine, text

# Configuration
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "training"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Export training data from database')
    parser.add_argument('--database', type=str, default=None,
                        help='Database name to connect to (overrides DB_NAME env var)')
    parser.add_argument('--relevance', action='store_true',
                        help='Export only relevance data')
    parser.add_argument('--summarization', action='store_true',
                        help='Export only summarization data')
    parser.add_argument('--enrichment', action='store_true',
                        help='Export only enrichment data')
    parser.add_argument('--append', action='store_true',
                        help='Append to existing data instead of overwriting')
    return parser.parse_args()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_connection(database_name: Optional[str] = None):
    """
    Get database connection using environment settings.

    Args:
        database_name: Optional database name to override DB_NAME env var
                      Special handling for 'wileytest' which uses different port/credentials
    """
    from app.config.settings import db_settings
    from urllib.parse import quote_plus

    # Special handling for wileytest (different port and credentials)
    if database_name == 'wileytest':
        user = quote_plus('wileytest_user')
        password = quote_plus('ZtG/Z0GfKeRhH3nfbnMWdXsRvOKtDm9b')
        host = '127.0.0.1'
        port = '6432'
        database_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/wileytest"
        logger.info(f"Connecting to wileytest database (port 6432)")
    elif database_name:
        # Build custom URL with specified database using current credentials
        user = quote_plus(db_settings.DB_USER)
        password = quote_plus(db_settings.DB_PASSWORD)
        host = db_settings.DB_HOST
        port = db_settings.DB_PORT
        database_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database_name}"
        logger.info(f"Connecting to database: {database_name}")
    else:
        database_url = db_settings.get_sync_database_url()
        logger.info(f"Connecting to database: {db_settings.DB_NAME}")

    engine = create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )
    return engine


def export_relevance_data(engine, output_dir: Path) -> Dict[str, int]:
    """
    Export data for relevance classification training.

    Labels are determined by topic_alignment_score (LLM-generated):
    - topic_alignment_score >= 0.5 = relevant (positive class)
    - topic_alignment_score < 0.5 = irrelevant (negative class)

    This approach:
    - Works for ALL topics without per-topic human labels
    - Uses LLM relevance judgment as training signal (knowledge distillation)
    - Score is available BEFORE enrichment in the pipeline

    Features:
    - topic: The target topic for relevance
    - title: Article title
    - summary: Article summary
    - topic_alignment_score: LLM-generated score (0-1)
    - keyword_relevance_score: LLM-generated score (0-1)
    - confidence_score: LLM-generated confidence (0-1)
    """
    logger.info("Exporting relevance training data...")

    # Threshold for relevance classification
    RELEVANCE_THRESHOLD = 0.5

    # Query all articles with topic_alignment_score
    query = """
    SELECT
        a.uri,
        a.title,
        a.summary,
        a.topic,
        a.topic_alignment_score,
        a.keyword_relevance_score,
        a.confidence_score,
        a.ingest_status,
        a.submission_date,
        a.user_preference
    FROM articles a
    WHERE a.title IS NOT NULL
      AND a.summary IS NOT NULL
      AND a.topic IS NOT NULL
      AND a.topic_alignment_score IS NOT NULL
    ORDER BY a.submission_date ASC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    logger.info(f"Retrieved {len(rows)} articles with topic_alignment_score")

    # Process into training format
    data = []
    for row in rows:
        (uri, title, summary, topic, topic_alignment, keyword_relevance,
         confidence, ingest_status, submission_date, user_preference) = row

        # Use topic_alignment_score as the label
        # This is the LLM's relevance judgment - we're distilling it into the SLM
        if topic_alignment is not None and topic_alignment >= RELEVANCE_THRESHOLD:
            label = 1  # Relevant
            label_source = 'alignment_score_high'
        else:
            label = 0  # Irrelevant
            label_source = 'alignment_score_low'

        # User preference can still override
        if user_preference == 'less':
            label = 0
            label_source = 'user_feedback'
        elif user_preference == 'more':
            label = 1
            label_source = 'user_feedback'

        record = {
            'uri': uri,
            'title': title,
            'summary': summary,
            'topic': topic,
            'topic_alignment_score': topic_alignment,
            'keyword_relevance_score': keyword_relevance,
            'confidence_score': confidence,
            'label': label,
            'label_source': label_source,
            'submission_date': submission_date,
        }
        data.append(record)

    logger.info(f"Labeled {sum(1 for d in data if d['label'] == 1)} as relevant (score >= {RELEVANCE_THRESHOLD})")
    logger.info(f"Labeled {sum(1 for d in data if d['label'] == 0)} as irrelevant (score < {RELEVANCE_THRESHOLD})")

    # Convert to DataFrame for analysis
    df = pd.DataFrame(data)

    # Show statistics
    logger.info(f"\nRelevance Data Statistics:")
    logger.info(f"Total records: {len(df)}")
    logger.info(f"Label distribution:")
    logger.info(f"  Relevant (1): {(df['label'] == 1).sum()}")
    logger.info(f"  Irrelevant (0): {(df['label'] == 0).sum()}")
    logger.info(f"\nLabel source distribution:")
    logger.info(df['label_source'].value_counts().to_string())
    logger.info(f"\nTopic distribution:")
    logger.info(df['topic'].value_counts().head(10).to_string())

    # Prioritize human-labeled data (first entries for each topic)
    # AI topic has ~2000 human-curated entries at the start
    df_sorted = df.sort_values('submission_date')

    # Split with stratification by label and topic
    train_df, temp_df = train_test_split(
        df_sorted,
        test_size=0.2,
        random_state=42,
        stratify=df_sorted['label']
    )
    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.5,
        random_state=42,
        stratify=temp_df['label']
    )

    # Save to JSON files
    output_dir.mkdir(parents=True, exist_ok=True)

    train_df.to_json(output_dir / "relevance_train.json", orient='records', indent=2)
    val_df.to_json(output_dir / "relevance_val.json", orient='records', indent=2)
    test_df.to_json(output_dir / "relevance_test.json", orient='records', indent=2)

    logger.info(f"\nSaved relevance data:")
    logger.info(f"  Train: {len(train_df)} records -> {output_dir / 'relevance_train.json'}")
    logger.info(f"  Val: {len(val_df)} records -> {output_dir / 'relevance_val.json'}")
    logger.info(f"  Test: {len(test_df)} records -> {output_dir / 'relevance_test.json'}")

    return {
        'train': len(train_df),
        'val': len(val_df),
        'test': len(test_df),
        'total': len(df)
    }


def export_summarization_data(engine, output_dir: Path) -> Dict[str, int]:
    """
    Export data for summarization model training.

    Uses articles that have both raw content and LLM-generated summaries.
    The LLM summary serves as the distillation target.
    """
    logger.info("Exporting summarization training data...")

    query = """
    SELECT
        a.uri,
        a.title,
        a.summary,
        a.topic,
        r.raw_markdown,
        a.submission_date
    FROM articles a
    JOIN raw_articles r ON a.uri = r.uri
    WHERE a.summary IS NOT NULL
      AND LENGTH(a.summary) > 50
      AND r.raw_markdown IS NOT NULL
      AND LENGTH(r.raw_markdown) > 200
    ORDER BY a.submission_date ASC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    logger.info(f"Retrieved {len(rows)} articles with content and summaries")

    # Process into training format
    data = []
    for row in rows:
        uri, title, summary, topic, raw_markdown, submission_date = row

        # Clean up raw markdown (remove excessive whitespace)
        content = ' '.join(raw_markdown.split())

        # Truncate content to reasonable size (will be further truncated during training)
        max_content_chars = 10000  # ~2500 tokens
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "..."

        record = {
            'uri': uri,
            'title': title,
            'content': content,
            'summary': summary,
            'topic': topic,
            'submission_date': submission_date,
            'content_length': len(content),
            'summary_length': len(summary),
        }
        data.append(record)

    df = pd.DataFrame(data)

    # Show statistics
    logger.info(f"\nSummarization Data Statistics:")
    logger.info(f"Total records: {len(df)}")
    logger.info(f"Content length: mean={df['content_length'].mean():.0f}, median={df['content_length'].median():.0f}")
    logger.info(f"Summary length: mean={df['summary_length'].mean():.0f}, median={df['summary_length'].median():.0f}")
    logger.info(f"\nTopic distribution:")
    logger.info(df['topic'].value_counts().head(10).to_string())

    # Split data
    train_df, temp_df = train_test_split(df, test_size=0.2, random_state=42)
    val_df, test_df = train_test_split(temp_df, test_size=0.5, random_state=42)

    # Save to JSON files
    train_df.to_json(output_dir / "summarization_train.json", orient='records', indent=2)
    val_df.to_json(output_dir / "summarization_val.json", orient='records', indent=2)
    test_df.to_json(output_dir / "summarization_test.json", orient='records', indent=2)

    logger.info(f"\nSaved summarization data:")
    logger.info(f"  Train: {len(train_df)} records -> {output_dir / 'summarization_train.json'}")
    logger.info(f"  Val: {len(val_df)} records -> {output_dir / 'summarization_val.json'}")
    logger.info(f"  Test: {len(test_df)} records -> {output_dir / 'summarization_test.json'}")

    return {
        'train': len(train_df),
        'val': len(val_df),
        'test': len(test_df),
        'total': len(df)
    }


def export_enrichment_data(engine, output_dir: Path) -> Dict[str, int]:
    """
    Export data for multi-task enrichment model training.

    Fields to predict:
    - sentiment: Positive/Negative/Neutral
    - time_to_impact: Immediate/6 months/1 year/2+ years
    - driver_type: accelerating/delaying/blocking/initiating/terminating/catalyzing
    - category: Topic-specific categories
    - future_signal: Emerging/Declining/Stable/etc

    Each field includes the LLM-generated explanation for potential use in training.
    """
    logger.info("Exporting enrichment training data...")

    query = """
    SELECT
        a.uri,
        a.title,
        a.summary,
        a.topic,
        a.sentiment,
        a.sentiment_explanation,
        a.time_to_impact,
        a.time_to_impact_explanation,
        a.driver_type,
        a.driver_type_explanation,
        a.category,
        a.future_signal,
        a.future_signal_explanation,
        a.submission_date
    FROM articles a
    WHERE a.title IS NOT NULL
      AND a.summary IS NOT NULL
      AND a.sentiment IS NOT NULL
      AND a.time_to_impact IS NOT NULL
      AND a.driver_type IS NOT NULL
    ORDER BY a.submission_date ASC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query))
        rows = result.fetchall()

    logger.info(f"Retrieved {len(rows)} fully enriched articles")

    # Process into training format
    data = []
    for row in rows:
        (uri, title, summary, topic, sentiment, sentiment_expl,
         time_to_impact, tti_expl, driver_type, dt_expl,
         category, future_signal, fs_expl, submission_date) = row

        record = {
            'uri': uri,
            'title': title,
            'summary': summary,
            'topic': topic,
            # Labels
            'sentiment': sentiment,
            'sentiment_explanation': sentiment_expl,
            'time_to_impact': time_to_impact,
            'time_to_impact_explanation': tti_expl,
            'driver_type': driver_type,
            'driver_type_explanation': dt_expl,
            'category': category,
            'future_signal': future_signal,
            'future_signal_explanation': fs_expl,
            'submission_date': submission_date,
        }
        data.append(record)

    df = pd.DataFrame(data)

    # Show statistics
    logger.info(f"\nEnrichment Data Statistics:")
    logger.info(f"Total records: {len(df)}")

    logger.info(f"\nSentiment distribution:")
    logger.info(df['sentiment'].value_counts().to_string())

    logger.info(f"\nTime to Impact distribution:")
    logger.info(df['time_to_impact'].value_counts().to_string())

    logger.info(f"\nDriver Type distribution:")
    logger.info(df['driver_type'].value_counts().to_string())

    logger.info(f"\nFuture Signal distribution:")
    logger.info(df['future_signal'].value_counts().head(10).to_string())

    logger.info(f"\nCategory distribution:")
    logger.info(df['category'].value_counts().head(15).to_string())

    logger.info(f"\nTopic distribution:")
    logger.info(df['topic'].value_counts().head(10).to_string())

    # Split data
    train_df, temp_df = train_test_split(df, test_size=0.2, random_state=42)
    val_df, test_df = train_test_split(temp_df, test_size=0.5, random_state=42)

    # Save to JSON files
    train_df.to_json(output_dir / "enrichment_train.json", orient='records', indent=2)
    val_df.to_json(output_dir / "enrichment_val.json", orient='records', indent=2)
    test_df.to_json(output_dir / "enrichment_test.json", orient='records', indent=2)

    logger.info(f"\nSaved enrichment data:")
    logger.info(f"  Train: {len(train_df)} records -> {output_dir / 'enrichment_train.json'}")
    logger.info(f"  Val: {len(val_df)} records -> {output_dir / 'enrichment_val.json'}")
    logger.info(f"  Test: {len(test_df)} records -> {output_dir / 'enrichment_test.json'}")

    return {
        'train': len(train_df),
        'val': len(val_df),
        'test': len(test_df),
        'total': len(df)
    }


def export_label_mappings(engine, output_dir: Path):
    """
    Export unique values for each enrichment field to create label mappings.
    These mappings are needed for model configuration.
    """
    logger.info("Exporting label mappings...")

    mappings = {}

    # Query unique values for each field
    fields = [
        ('sentiment', 'sentiment'),
        ('time_to_impact', 'time_to_impact'),
        ('driver_type', 'driver_type'),
        ('future_signal', 'future_signal'),
        ('category', 'category'),
    ]

    with engine.connect() as conn:
        for field_name, column in fields:
            query = f"""
            SELECT DISTINCT {column}
            FROM articles
            WHERE {column} IS NOT NULL
            ORDER BY {column}
            """
            result = conn.execute(text(query))
            values = [row[0] for row in result.fetchall()]
            mappings[field_name] = {
                'values': values,
                'label2id': {v: i for i, v in enumerate(values)},
                'id2label': {i: v for i, v in enumerate(values)},
                'num_labels': len(values)
            }
            logger.info(f"  {field_name}: {len(values)} unique values")

    # Save mappings
    with open(output_dir / "label_mappings.json", 'w') as f:
        json.dump(mappings, f, indent=2)

    logger.info(f"Saved label mappings to {output_dir / 'label_mappings.json'}")

    return mappings


def main():
    """Main export function."""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("SLM Training Data Export")
    logger.info("=" * 60)

    # Determine which datasets to export
    export_all = not (args.relevance or args.summarization or args.enrichment)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get database connection
    engine = get_database_connection(args.database)

    # Export datasets
    stats = {}

    try:
        # 1. Relevance data
        if export_all or args.relevance:
            stats['relevance'] = export_relevance_data(engine, OUTPUT_DIR)

        # 2. Summarization data
        if export_all or args.summarization:
            stats['summarization'] = export_summarization_data(engine, OUTPUT_DIR)

        # 3. Enrichment data
        if export_all or args.enrichment:
            stats['enrichment'] = export_enrichment_data(engine, OUTPUT_DIR)

        # 4. Label mappings (always export if enrichment is exported)
        if export_all or args.enrichment:
            label_mappings = export_label_mappings(engine, OUTPUT_DIR)

    finally:
        engine.dispose()

    # Save export summary
    summary = {
        'export_date': datetime.now().isoformat(),
        'output_dir': str(OUTPUT_DIR),
        'datasets': stats,
        'notes': [
            'First ~2000 AI topic articles are human-curated (gold labels)',
            'Relevance: approved/manual=1, filtered_*=0',
            'Summarization: LLM-generated summaries used as distillation targets',
            'Enrichment: All fields from LLM analysis (silver labels)',
        ]
    }

    with open(OUTPUT_DIR / "export_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("Export Complete!")
    logger.info("=" * 60)
    logger.info(f"\nOutput directory: {OUTPUT_DIR}")
    logger.info(f"\nDataset Statistics:")
    for dataset_name, dataset_stats in stats.items():
        logger.info(f"  {dataset_name}:")
        logger.info(f"    Total: {dataset_stats['total']}")
        logger.info(f"    Train: {dataset_stats['train']}")
        logger.info(f"    Val: {dataset_stats['val']}")
        logger.info(f"    Test: {dataset_stats['test']}")

    return stats


if __name__ == "__main__":
    main()
