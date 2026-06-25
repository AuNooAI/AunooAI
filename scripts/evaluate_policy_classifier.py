#!/usr/bin/env python3
"""
Evaluate the trained policy classifier against the original dataset.

Usage:
    python scripts/evaluate_policy_classifier.py
    python scripts/evaluate_policy_classifier.py --show-errors 20
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.metrics import classification_report, f1_score, accuracy_score
from policy_classifier_inference import PolicyClassifier

BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"

# Category mapping from CSV columns to model labels
CATEGORY_COLUMNS = {
    "Violating Democratic Norms, Undermining Rule of Law": "undermining_democracy",
    "Hollowing State / Weakening Federal Institutions": "hollowing_state",
    "Suppressing Dissent / Weaponising State Against 'Enemies'": "suppressing_dissent",
    "Controlling Information Including Spreading Misinformation and Propaganda": "controlling_information",
    "Control of Science & Health to Align with State Ideology": "attacking_science",
    "Attacking Universities, Schools, Museums, Culture": "attacking_education",
    "Weakening Civil Rights": "weakening_civil_rights",
    "Corruption & Enrichment": "corruption",
    "Aggressive Foreign Policy & Global Destabilisation": "foreign_policy",
    "Anti-immigrant or Militarised Nationalism": "nationalism_immigration",
}


def load_ground_truth():
    """Load the CSV and extract ground truth labels."""
    df = pd.read_csv(DATA_PATH, skiprows=1)

    category_cols = list(CATEGORY_COLUMNS.keys())
    category_names = list(CATEGORY_COLUMNS.values())

    records = []
    for _, row in df.iterrows():
        text = row.get("Title", "")
        if not text or pd.isna(text):
            continue

        # Get ground truth labels
        true_labels = set()
        for col, name in CATEGORY_COLUMNS.items():
            if row.get(col, "No") == "Yes":
                true_labels.add(name)

        records.append({
            "text": text,
            "true_labels": true_labels,
        })

    return records, category_names


def evaluate(show_errors: int = 10, threshold: float = 0.5):
    """Run evaluation."""
    print("Loading model...")
    classifier = PolicyClassifier()

    print("Loading ground truth data...")
    records, category_names = load_ground_truth()
    print(f"Loaded {len(records)} records\n")

    # Run predictions
    print("Running predictions...")
    all_true = []
    all_pred = []
    errors = []

    batch_size = 32
    texts = [r["text"] for r in records]

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_records = records[i:i + batch_size]

        results = classifier.classify_batch(batch_texts, threshold)

        for record, result in zip(batch_records, results):
            true_labels = record["true_labels"]
            pred_labels = set(result["categories"])

            # Convert to binary vectors
            true_vec = [1 if cat in true_labels else 0 for cat in category_names]
            pred_vec = [1 if cat in pred_labels else 0 for cat in category_names]

            all_true.append(true_vec)
            all_pred.append(pred_vec)

            # Track errors
            if true_labels != pred_labels:
                errors.append({
                    "text": record["text"],
                    "true": true_labels,
                    "pred": pred_labels,
                    "missed": true_labels - pred_labels,
                    "extra": pred_labels - true_labels,
                    "scores": result["scores"],
                })

        if (i + batch_size) % 500 == 0 or i + batch_size >= len(texts):
            print(f"  Processed {min(i + batch_size, len(texts))}/{len(texts)}")

    all_true = np.array(all_true)
    all_pred = np.array(all_pred)

    # Overall metrics
    print("\n" + "=" * 60)
    print("OVERALL METRICS")
    print("=" * 60)

    f1_micro = f1_score(all_true, all_pred, average="micro")
    f1_macro = f1_score(all_true, all_pred, average="macro")
    f1_weighted = f1_score(all_true, all_pred, average="weighted")

    # Exact match accuracy (all labels correct)
    exact_match = np.all(all_true == all_pred, axis=1).mean()

    print(f"F1 Micro:      {f1_micro:.4f}")
    print(f"F1 Macro:      {f1_macro:.4f}")
    print(f"F1 Weighted:   {f1_weighted:.4f}")
    print(f"Exact Match:   {exact_match:.4f} ({int(exact_match * len(records))}/{len(records)} perfect)")
    print(f"Error Rate:    {len(errors)}/{len(records)} ({len(errors)/len(records)*100:.1f}%)")

    # Per-category metrics
    print("\n" + "=" * 60)
    print("PER-CATEGORY METRICS")
    print("=" * 60)
    print(classification_report(all_true, all_pred, target_names=category_names, zero_division=0))

    # Show error examples
    if show_errors > 0 and errors:
        print("\n" + "=" * 60)
        print(f"ERROR EXAMPLES (showing {min(show_errors, len(errors))} of {len(errors)})")
        print("=" * 60)

        # Sort by most egregious errors (most missed + extra)
        errors.sort(key=lambda e: len(e["missed"]) + len(e["extra"]), reverse=True)

        for i, err in enumerate(errors[:show_errors]):
            print(f"\n[{i+1}] {err['text'][:100]}...")
            print(f"    TRUE:   {', '.join(sorted(err['true'])) or '(none)'}")
            print(f"    PRED:   {', '.join(sorted(err['pred'])) or '(none)'}")
            if err["missed"]:
                print(f"    MISSED: {', '.join(sorted(err['missed']))}")
            if err["extra"]:
                print(f"    EXTRA:  {', '.join(sorted(err['extra']))}")

            # Show borderline scores for missed categories
            if err["missed"]:
                print(f"    Scores for missed:")
                for cat in sorted(err["missed"]):
                    print(f"      {cat}: {err['scores'][cat]:.3f}")

    return f1_micro, f1_macro, exact_match


def main():
    parser = argparse.ArgumentParser(description="Evaluate policy classifier")
    parser.add_argument("--show-errors", type=int, default=10, help="Number of error examples to show")
    parser.add_argument("--threshold", type=float, default=0.55, help="Classification threshold")

    args = parser.parse_args()
    evaluate(show_errors=args.show_errors, threshold=args.threshold)


if __name__ == "__main__":
    main()
