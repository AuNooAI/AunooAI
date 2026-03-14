#!/usr/bin/env python3
"""
Export LLM-classified science funding articles for SLM training.

Queries science_article_categories for LLM-classified articles,
joins with articles table for title/summary, and exports as
train/val/test JSON splits for DeBERTa fine-tuning.

Usage:
    python scripts/export_science_funding_training_data.py
    python scripts/export_science_funding_training_data.py --min-samples 20
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


# The 10 science funding categories (must match SCIENCE_CATEGORIES in routes)
CATEGORIES = [
    "Grant Freezes & Cuts",
    "NIH & Biomedical",
    "NSF & Basic Science",
    "DOE & Energy Research",
    "University Impact",
    "Brain Drain & Workforce",
    "Climate & Environmental",
    "DEI & Ideological Targeting",
    "Public Health & Medical",
    "International Collaboration",
]


def get_connection():
    """Get a database connection."""
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "aunoo_db"),
        user=os.getenv("DB_USER", "aunoo_user"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def export_data(min_samples: int = 10, output_dir: str = "data/training"):
    """Export LLM-classified science articles for training."""
    conn = get_connection()
    cur = conn.cursor()

    # Get all LLM-classified articles with their categories
    cur.execute("""
        SELECT
            a.uri,
            a.title,
            a.summary,
            array_agg(DISTINCT sac.category) as categories
        FROM articles a
        JOIN science_article_categories sac ON a.uri = sac.article_uri
        WHERE sac.classification_method = 'llm_semantic'
        GROUP BY a.uri, a.title, a.summary
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No LLM-classified articles found. Run classification first.")
        sys.exit(1)

    print(f"Found {len(rows)} LLM-classified articles")

    # Build category-to-index mapping
    cat2idx = {cat: i for i, cat in enumerate(CATEGORIES)}
    num_categories = len(CATEGORIES)

    # Convert to training format
    samples = []
    category_counts = Counter()

    for uri, title, summary, categories in rows:
        # Filter to known categories only
        valid_cats = [c for c in categories if c in cat2idx]
        if not valid_cats:
            continue

        # Build multi-hot label vector
        labels = [0] * num_categories
        for cat in valid_cats:
            labels[cat2idx[cat]] = 1
            category_counts[cat] += 1

        # Text input: title + summary
        text = title or ""
        if summary:
            text = f"{title}. {summary}" if title else summary

        if not text.strip():
            continue

        samples.append({
            "uri": uri,
            "text": text,
            "labels": labels,
            "categories": valid_cats,
        })

    print(f"\nValid samples: {len(samples)}")

    # Filter categories with too few samples
    print(f"\nCategory distribution:")
    low_count_cats = []
    for i, cat in enumerate(CATEGORIES):
        count = category_counts[cat]
        pct = count / len(samples) * 100 if samples else 0
        marker = " *LOW*" if count < min_samples else ""
        print(f"  {cat}: {count} ({pct:.1f}%){marker}")
        if count < min_samples:
            low_count_cats.append(cat)

    if low_count_cats:
        print(f"\nWarning: {len(low_count_cats)} categories have < {min_samples} samples")
        print(f"  Low categories: {low_count_cats}")
        print("  These will still be included but may have poor model performance")

    # Split: 80/10/10 stratified
    # For multi-label, we use the most common category per sample for stratification
    strat_labels = []
    for s in samples:
        # Use first category as stratification key
        strat_labels.append(s["categories"][0])

    # Handle edge cases where stratification might fail
    try:
        train_data, temp_data, train_strat, temp_strat = train_test_split(
            samples, strat_labels, test_size=0.2, random_state=42, stratify=strat_labels
        )
        val_data, test_data = train_test_split(
            temp_data, test_size=0.5, random_state=42, stratify=temp_strat
        )
    except ValueError:
        # Fallback to non-stratified if some classes too small
        print("Warning: Stratified split failed, using random split")
        train_data, temp_data = train_test_split(samples, test_size=0.2, random_state=42)
        val_data, test_data = train_test_split(temp_data, test_size=0.5, random_state=42)

    print(f"\nSplit sizes: train={len(train_data)}, val={len(val_data)}, test={len(test_data)}")

    # Save
    out_path = BASE_DIR / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    # Strip URI from training data (not needed for training)
    def strip_uri(data):
        return [{"text": s["text"], "labels": s["labels"]} for s in data]

    with open(out_path / "science_funding_train.json", "w") as f:
        json.dump(strip_uri(train_data), f)

    with open(out_path / "science_funding_val.json", "w") as f:
        json.dump(strip_uri(val_data), f)

    with open(out_path / "science_funding_test.json", "w") as f:
        json.dump(strip_uri(test_data), f)

    # Save category mapping
    mapping = {
        "categories": CATEGORIES,
        "id2label": {i: cat for i, cat in enumerate(CATEGORIES)},
        "label2id": {cat: i for i, cat in enumerate(CATEGORIES)},
        "num_labels": num_categories,
        "total_samples": len(samples),
        "category_counts": dict(category_counts),
    }
    with open(out_path / "science_funding_label_mappings.json", "w") as f:
        json.dump(mapping, f, indent=2)

    # Save export summary
    summary_info = {
        "total_articles": len(rows),
        "valid_samples": len(samples),
        "train_size": len(train_data),
        "val_size": len(val_data),
        "test_size": len(test_data),
        "num_categories": num_categories,
        "categories": CATEGORIES,
        "category_counts": dict(category_counts),
        "min_samples_threshold": min_samples,
        "low_count_categories": low_count_cats,
    }
    with open(out_path / "science_funding_export_summary.json", "w") as f:
        json.dump(summary_info, f, indent=2)

    print(f"\nFiles saved to {out_path}:")
    print(f"  science_funding_train.json ({len(train_data)} samples)")
    print(f"  science_funding_val.json ({len(val_data)} samples)")
    print(f"  science_funding_test.json ({len(test_data)} samples)")
    print(f"  science_funding_label_mappings.json")
    print(f"  science_funding_export_summary.json")

    return len(samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export science funding training data")
    parser.add_argument("--min-samples", type=int, default=10,
                       help="Minimum samples per category to warn (default: 10)")
    parser.add_argument("--output-dir", type=str, default="data/training",
                       help="Output directory (default: data/training)")
    args = parser.parse_args()

    export_data(min_samples=args.min_samples, output_dir=args.output_dir)
