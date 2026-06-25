#!/usr/bin/env python3
"""
Ensemble classifier combining RoBERTa and LLM for policy classification.

Usage:
    python scripts/policy_ensemble_classifier.py "Trump fires inspector general"
    python scripts/policy_ensemble_classifier.py --interactive
    python scripts/policy_ensemble_classifier.py --evaluate
"""

import argparse
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import classification_report, f1_score

# Import both classifiers
from policy_classifier_inference import PolicyClassifier as RobertaClassifier
from policy_llm_inference import PolicyLLMClassifier

BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"

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

CATEGORY_NAMES = list(CATEGORY_COLUMNS.values())

# Default weights and thresholds (can be optimized)
DEFAULT_ROBERTA_WEIGHT = 0.7
DEFAULT_LLM_WEIGHT = 0.3

# Per-category thresholds (optimized for best F1)
DEFAULT_THRESHOLDS = {
    "undermining_democracy": 0.45,
    "hollowing_state": 0.50,
    "suppressing_dissent": 0.45,
    "controlling_information": 0.40,  # Lower - often missed
    "attacking_science": 0.55,
    "attacking_education": 0.50,
    "weakening_civil_rights": 0.45,
    "corruption": 0.50,
    "foreign_policy": 0.55,
    "nationalism_immigration": 0.50,
}


class PolicyEnsembleClassifier:
    """
    Ensemble classifier combining RoBERTa (fast, calibrated scores)
    with LLM (reasoning, context-aware).
    """

    def __init__(
        self,
        roberta_weight: float = DEFAULT_ROBERTA_WEIGHT,
        llm_weight: float = DEFAULT_LLM_WEIGHT,
        thresholds: dict = None,
        load_llm: bool = True,
    ):
        self.roberta_weight = roberta_weight
        self.llm_weight = llm_weight
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.categories = CATEGORY_NAMES

        print("Loading RoBERTa classifier...")
        self.roberta = RobertaClassifier()

        self.llm = None
        if load_llm:
            print("Loading LLM classifier...")
            try:
                self.llm = PolicyLLMClassifier()
            except Exception as e:
                print(f"Warning: Could not load LLM: {e}")
                print("Running in RoBERTa-only mode")
                self.roberta_weight = 1.0
                self.llm_weight = 0.0

    def classify(
        self,
        title: str,
        summary: str = None,
        full_text: str = None,
        return_details: bool = False,
    ) -> dict:
        """
        Classify using ensemble of both models.

        Args:
            title: Article title
            summary: Optional summary (used by LLM)
            full_text: Optional full text (used by LLM)
            return_details: Include per-model scores in output

        Returns:
            dict with 'categories' and optionally detailed scores
        """
        # Get RoBERTa scores (always available, fast)
        roberta_result = self.roberta.classify(title, threshold=0.0)  # Get all scores
        roberta_scores = roberta_result["scores"]

        # Get LLM predictions (slower, but context-aware)
        llm_scores = {cat: 0.0 for cat in self.categories}
        llm_raw = ""

        if self.llm is not None and self.llm_weight > 0:
            llm_result = self.llm.classify(title, summary, full_text)
            llm_raw = llm_result.get("raw_response", "")

            # Convert LLM binary predictions to scores
            for cat in llm_result["categories"]:
                if cat in llm_scores:
                    llm_scores[cat] = 1.0

        # Combine scores with weights
        combined_scores = {}
        for cat in self.categories:
            r_score = roberta_scores.get(cat, 0.0)
            l_score = llm_scores.get(cat, 0.0)
            combined_scores[cat] = (
                self.roberta_weight * r_score + self.llm_weight * l_score
            )

        # Apply per-category thresholds
        predicted = []
        for cat in self.categories:
            threshold = self.thresholds.get(cat, 0.5)
            if combined_scores[cat] >= threshold:
                predicted.append(cat)

        result = {
            "title": title[:100] + "..." if len(title) > 100 else title,
            "categories": predicted,
            "scores": combined_scores,
        }

        if return_details:
            result["roberta_scores"] = roberta_scores
            result["llm_scores"] = llm_scores
            result["llm_raw"] = llm_raw

        return result

    def classify_roberta_only(self, title: str, threshold: float = 0.55) -> dict:
        """Fast classification using only RoBERTa."""
        return self.roberta.classify(title, threshold)


def load_ground_truth():
    """Load CSV ground truth."""
    df = pd.read_csv(DATA_PATH, skiprows=1)

    records = []
    for _, row in df.iterrows():
        title = row.get("Title", "")
        if not title or pd.isna(title):
            continue

        true_labels = set()
        for col, name in CATEGORY_COLUMNS.items():
            if row.get(col, "No") == "Yes":
                true_labels.add(name)

        records.append({"title": title, "true_labels": true_labels})

    return records


def optimize_thresholds(classifier, records, roberta_weight=0.7, llm_weight=0.3):
    """Find optimal per-category thresholds using grid search."""
    print("\nOptimizing per-category thresholds...")

    # First, get all scores
    all_scores = []
    all_true = []

    for i, record in enumerate(records):
        roberta_result = classifier.roberta.classify(record["title"], threshold=0.0)
        roberta_scores = roberta_result["scores"]

        llm_scores = {cat: 0.0 for cat in CATEGORY_NAMES}
        if classifier.llm is not None:
            llm_result = classifier.llm.classify(record["title"])
            for cat in llm_result["categories"]:
                if cat in llm_scores:
                    llm_scores[cat] = 1.0

        combined = {}
        for cat in CATEGORY_NAMES:
            combined[cat] = roberta_weight * roberta_scores.get(cat, 0) + llm_weight * llm_scores.get(cat, 0)

        all_scores.append(combined)
        all_true.append(record["true_labels"])

        if (i + 1) % 200 == 0:
            print(f"  Scored {i + 1}/{len(records)}")

    # Optimize threshold for each category
    best_thresholds = {}
    for cat in CATEGORY_NAMES:
        best_f1 = 0
        best_thresh = 0.5

        for thresh in np.arange(0.2, 0.8, 0.05):
            y_true = [1 if cat in t else 0 for t in all_true]
            y_pred = [1 if s[cat] >= thresh else 0 for s in all_scores]

            if sum(y_pred) == 0:
                continue

            tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
            fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
            fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            if f1 > best_f1:
                best_f1 = f1
                best_thresh = thresh

        best_thresholds[cat] = round(best_thresh, 2)
        print(f"  {cat}: threshold={best_thresh:.2f}, F1={best_f1:.3f}")

    return best_thresholds


def evaluate(classifier, records, show_errors: int = 10):
    """Evaluate ensemble on ground truth."""
    print(f"\nEvaluating on {len(records)} records...")

    all_true = []
    all_pred = []
    errors = []

    for i, record in enumerate(records):
        result = classifier.classify(record["title"])

        true_labels = record["true_labels"]
        pred_labels = set(result["categories"])

        true_vec = [1 if cat in true_labels else 0 for cat in CATEGORY_NAMES]
        pred_vec = [1 if cat in pred_labels else 0 for cat in CATEGORY_NAMES]

        all_true.append(true_vec)
        all_pred.append(pred_vec)

        if true_labels != pred_labels:
            errors.append({
                "title": record["title"],
                "true": true_labels,
                "pred": pred_labels,
                "scores": result["scores"],
            })

        if (i + 1) % 200 == 0 or i + 1 == len(records):
            print(f"  Processed {i + 1}/{len(records)}")

    all_true = np.array(all_true)
    all_pred = np.array(all_pred)

    # Metrics
    f1_micro = f1_score(all_true, all_pred, average="micro")
    f1_macro = f1_score(all_true, all_pred, average="macro")
    exact_match = np.all(all_true == all_pred, axis=1).mean()

    print("\n" + "=" * 60)
    print("ENSEMBLE METRICS")
    print("=" * 60)
    print(f"F1 Micro:      {f1_micro:.4f}")
    print(f"F1 Macro:      {f1_macro:.4f}")
    print(f"Exact Match:   {exact_match:.4f} ({int(exact_match * len(records))}/{len(records)} perfect)")
    print(f"Error Rate:    {len(errors)}/{len(records)} ({len(errors)/len(records)*100:.1f}%)")

    print("\n" + "=" * 60)
    print("PER-CATEGORY METRICS")
    print("=" * 60)
    print(classification_report(all_true, all_pred, target_names=CATEGORY_NAMES, zero_division=0))

    if show_errors > 0 and errors:
        print("\n" + "=" * 60)
        print(f"ERROR EXAMPLES (showing {min(show_errors, len(errors))})")
        print("=" * 60)

        for i, err in enumerate(errors[:show_errors]):
            print(f"\n[{i+1}] {err['title'][:80]}...")
            print(f"    TRUE: {', '.join(sorted(err['true'])) or '(none)'}")
            print(f"    PRED: {', '.join(sorted(err['pred'])) or '(none)'}")

    return f1_micro, exact_match


def interactive_mode(classifier):
    """Interactive classification."""
    print("\nEnsemble Policy Classifier")
    print("Enter article titles (Ctrl+C to exit)\n")

    while True:
        try:
            title = input("Article: ").strip()
            if not title:
                continue

            result = classifier.classify(title, return_details=True)

            print(f"\nCategories: {', '.join(result['categories']) or '(none)'}")
            print("\nCombined scores:")
            for cat, score in sorted(result["scores"].items(), key=lambda x: -x[1]):
                thresh = classifier.thresholds.get(cat, 0.5)
                marker = " ✓" if score >= thresh else ""
                print(f"  {cat:25s} {score:.3f} (thresh={thresh}){marker}")

            if result.get("llm_raw"):
                print(f"\nLLM response: {result['llm_raw']}")
            print()

        except KeyboardInterrupt:
            print("\nExiting")
            break


def main():
    parser = argparse.ArgumentParser(description="Ensemble Policy Classifier")
    parser.add_argument("title", nargs="?", help="Article title to classify")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--evaluate", action="store_true", help="Run evaluation")
    parser.add_argument("--optimize", action="store_true", help="Optimize thresholds")
    parser.add_argument("--roberta-only", action="store_true", help="Use only RoBERTa (fast)")
    parser.add_argument("--roberta-weight", type=float, default=0.7, help="Weight for RoBERTa")
    parser.add_argument("--llm-weight", type=float, default=0.3, help="Weight for LLM")

    args = parser.parse_args()

    # Load classifier
    load_llm = not args.roberta_only
    classifier = PolicyEnsembleClassifier(
        roberta_weight=args.roberta_weight,
        llm_weight=args.llm_weight,
        load_llm=load_llm,
    )

    if args.optimize:
        records = load_ground_truth()
        thresholds = optimize_thresholds(
            classifier, records, args.roberta_weight, args.llm_weight
        )
        print("\nOptimized thresholds:")
        print(json.dumps(thresholds, indent=2))

        # Save thresholds
        save_path = BASE_DIR / "models/ensemble_thresholds.json"
        with open(save_path, "w") as f:
            json.dump(thresholds, f, indent=2)
        print(f"\nSaved to {save_path}")

    elif args.evaluate:
        records = load_ground_truth()
        evaluate(classifier, records)

    elif args.interactive:
        interactive_mode(classifier)

    elif args.title:
        result = classifier.classify(args.title, return_details=True)
        print(f"\nTitle: {result['title']}")
        print(f"Categories: {', '.join(result['categories']) or '(none)'}")
        print("\nScores:")
        for cat, score in sorted(result["scores"].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {score:.3f}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
