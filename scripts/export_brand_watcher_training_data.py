#!/usr/bin/env python3
"""
Export LLM-classified brand watcher articles for SLM training.

Queries bw_article_categories for LLM-classified articles,
joins with articles table for title/summary, and exports as
train/val/test JSON splits for DeBERTa fine-tuning.

Usage:
    python scripts/export_brand_watcher_training_data.py
    python scripts/export_brand_watcher_training_data.py --min-samples 20
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

CATEGORIES = [
    "Product & Innovation",
    "Financial Performance",
    "Leadership & Governance",
    "Brand Sentiment & Perception",
    "Competitive Landscape",
    "Legal & Regulatory",
    "Partnerships & Alliances",
    "ESG & Social Responsibility",
    "Customer & Product Issues",
    "Market Strategy & Expansion",
    "Media & Advertising",
]


def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "aunoo_db"),
        user=os.getenv("DB_USER", "aunoo_user"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def export_data(min_samples: int = 10, output_dir: str = "data/training"):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            a.uri,
            a.title,
            a.summary,
            array_agg(DISTINCT bac.category) as categories
        FROM articles a
        JOIN bw_article_categories bac ON a.uri = bac.article_uri
        WHERE bac.classification_method = 'llm_semantic'
        GROUP BY a.uri, a.title, a.summary
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No LLM-classified articles found. Run classification first.")
        sys.exit(1)

    print(f"Found {len(rows)} LLM-classified articles")

    cat2idx = {cat: i for i, cat in enumerate(CATEGORIES)}
    num_categories = len(CATEGORIES)

    samples = []
    category_counts = Counter()

    for uri, title, summary, categories in rows:
        valid_cats = [c for c in categories if c in cat2idx]
        if not valid_cats:
            continue

        labels = [0] * num_categories
        for cat in valid_cats:
            labels[cat2idx[cat]] = 1
            category_counts[cat] += 1

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

    # Split 80/10/10
    strat_labels = [s["categories"][0] for s in samples]
    try:
        train_data, temp_data, train_strat, temp_strat = train_test_split(
            samples, strat_labels, test_size=0.2, random_state=42, stratify=strat_labels
        )
        val_data, test_data = train_test_split(
            temp_data, test_size=0.5, random_state=42, stratify=temp_strat
        )
    except ValueError:
        print("Warning: Stratified split failed, using random split")
        train_data, temp_data = train_test_split(samples, test_size=0.2, random_state=42)
        val_data, test_data = train_test_split(temp_data, test_size=0.5, random_state=42)

    print(f"\nSplit sizes: train={len(train_data)}, val={len(val_data)}, test={len(test_data)}")

    out_path = BASE_DIR / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    def strip_uri(data):
        return [{"text": s["text"], "labels": s["labels"]} for s in data]

    with open(out_path / "brand_watcher_train.json", "w") as f:
        json.dump(strip_uri(train_data), f)
    with open(out_path / "brand_watcher_val.json", "w") as f:
        json.dump(strip_uri(val_data), f)
    with open(out_path / "brand_watcher_test.json", "w") as f:
        json.dump(strip_uri(test_data), f)

    mapping = {
        "categories": CATEGORIES,
        "id2label": {i: cat for i, cat in enumerate(CATEGORIES)},
        "label2id": {cat: i for i, cat in enumerate(CATEGORIES)},
        "num_labels": num_categories,
        "total_samples": len(samples),
        "category_counts": dict(category_counts),
    }
    with open(out_path / "brand_watcher_label_mappings.json", "w") as f:
        json.dump(mapping, f, indent=2)

    print(f"\nFiles saved to {out_path}:")
    print(f"  brand_watcher_train.json ({len(train_data)} samples)")
    print(f"  brand_watcher_val.json ({len(val_data)} samples)")
    print(f"  brand_watcher_test.json ({len(test_data)} samples)")
    print(f"  brand_watcher_label_mappings.json")

    return len(samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export brand watcher training data")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--output-dir", type=str, default="data/training")
    args = parser.parse_args()
    export_data(min_samples=args.min_samples, output_dir=args.output_dir)
