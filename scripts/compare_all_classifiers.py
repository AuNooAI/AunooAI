#!/usr/bin/env python3
"""
Comprehensive evaluation comparing 6 policy classifier configurations.

Configurations:
1. RoBERTa-Large alone
2. DeBERTa-base alone
3. RoBERTa + DeBERTa ensemble (50/50)
4. DeBERTa + LLM (70/30)
5. RoBERTa + LLM (70/30)
6. LLM (Mistral-7B) alone

Usage:
    CUDA_VISIBLE_DEVICES=0 python scripts/compare_all_classifiers.py

    # Skip LLM (faster, just compare SLMs)
    python scripts/compare_all_classifiers.py --skip-llm

    # Custom output
    python scripts/compare_all_classifiers.py --output results.md
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, precision_score, recall_score
from tqdm import tqdm

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

# Import classifier classes
from policy_classifier_inference import PolicyClassifier
from policy_llm_inference import PolicyLLMClassifier

# Paths
ROBERTA_PATH = BASE_DIR / "models/policy_classifier/final_roberta_large"
DEBERTA_PATH = BASE_DIR / "models/policy_classifier/final"
LLM_PATH = BASE_DIR / "models/policy_llm/final"
DATASET_PATH = BASE_DIR / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"

# Column mappings (CSV column names to category names)
COLUMN_TO_CATEGORY = {
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

CATEGORIES = list(COLUMN_TO_CATEGORY.values())


class MultiModelEvaluator:
    """Evaluator that loads all models and runs comprehensive comparison."""

    def __init__(self, skip_llm: bool = False, verbose: bool = True):
        self.skip_llm = skip_llm
        self.verbose = verbose
        self.roberta = None
        self.deberta = None
        self.llm = None

        # Results storage
        self.predictions = {}
        self.raw_scores = {}

    def load_models(self):
        """Load all classifier models."""
        print("=" * 60)
        print("Loading Models")
        print("=" * 60)

        # Load DeBERTa
        print("\n[1/3] Loading DeBERTa-base...")
        self.deberta = PolicyClassifier(model_path=str(DEBERTA_PATH))

        # Load RoBERTa
        print("\n[2/3] Loading RoBERTa-Large...")
        self.roberta = PolicyClassifier(model_path=str(ROBERTA_PATH))

        # Load LLM (optional)
        if not self.skip_llm:
            print("\n[3/3] Loading Mistral-7B LLM...")
            self.llm = PolicyLLMClassifier(model_path=str(LLM_PATH))
        else:
            print("\n[3/3] Skipping LLM (--skip-llm flag)")

        print("\nAll models loaded successfully!")

    def load_dataset(self) -> pd.DataFrame:
        """Load and prepare the evaluation dataset."""
        print("\n" + "=" * 60)
        print("Loading Dataset")
        print("=" * 60)

        # Read CSV, skip the attribution row
        df = pd.read_csv(DATASET_PATH, skiprows=1)

        # Remove rows with missing titles
        df = df.dropna(subset=["Title"])

        print(f"Loaded {len(df)} records from dataset")

        # Convert label columns to binary
        for col, cat in COLUMN_TO_CATEGORY.items():
            if col in df.columns:
                df[cat] = (df[col].str.lower() == "yes").astype(int)
            else:
                print(f"WARNING: Column '{col}' not found in dataset")
                df[cat] = 0

        return df

    def get_ground_truth(self, df: pd.DataFrame) -> np.ndarray:
        """Extract ground truth labels as numpy array."""
        return df[CATEGORIES].values

    def run_slm_predictions(self, df: pd.DataFrame, model, model_name: str) -> tuple:
        """
        Run predictions with an SLM classifier.

        Returns:
            (predictions, raw_scores) - binary predictions and sigmoid scores
        """
        print(f"\nRunning {model_name} predictions...")

        titles = df["Title"].tolist()
        all_scores = []

        # Process in batches
        batch_size = 32
        for i in tqdm(range(0, len(titles), batch_size), desc=model_name):
            batch = titles[i:i + batch_size]
            results = model.classify_batch(batch, threshold=0.0)  # Get all scores

            for result in results:
                scores = [result["scores"].get(cat, 0.0) for cat in CATEGORIES]
                all_scores.append(scores)

        raw_scores = np.array(all_scores)
        return raw_scores

    def run_llm_predictions(self, df: pd.DataFrame) -> np.ndarray:
        """
        Run predictions with the LLM classifier.

        Returns:
            binary predictions array (LLM outputs binary, not scores)
        """
        print("\nRunning LLM predictions...")

        titles = df["Title"].tolist()
        all_preds = []

        for title in tqdm(titles, desc="Mistral-7B"):
            result = self.llm.classify(title)

            # Convert categories to binary vector
            pred = [1 if cat in result["categories"] else 0 for cat in CATEGORIES]
            all_preds.append(pred)

        return np.array(all_preds)

    def compute_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        """Compute evaluation metrics."""
        # Ensure predictions are binary
        y_pred_binary = (y_pred > 0.5).astype(int) if y_pred.dtype == float else y_pred

        # F1 scores
        f1_micro = f1_score(y_true, y_pred_binary, average="micro", zero_division=0)
        f1_macro = f1_score(y_true, y_pred_binary, average="macro", zero_division=0)

        # Per-category F1
        f1_per_cat = f1_score(y_true, y_pred_binary, average=None, zero_division=0)

        # Precision and Recall
        precision_micro = precision_score(y_true, y_pred_binary, average="micro", zero_division=0)
        recall_micro = recall_score(y_true, y_pred_binary, average="micro", zero_division=0)

        precision_macro = precision_score(y_true, y_pred_binary, average="macro", zero_division=0)
        recall_macro = recall_score(y_true, y_pred_binary, average="macro", zero_division=0)

        # Exact match (all categories correct for a sample)
        exact_match = np.mean(np.all(y_true == y_pred_binary, axis=1))

        # Subset accuracy (at least one correct prediction per sample)
        any_correct = np.mean(np.any((y_true == 1) & (y_pred_binary == 1), axis=1))

        return {
            "f1_micro": f1_micro,
            "f1_macro": f1_macro,
            "precision_micro": precision_micro,
            "recall_micro": recall_micro,
            "precision_macro": precision_macro,
            "recall_macro": recall_macro,
            "exact_match": exact_match,
            "any_correct": any_correct,
            "f1_per_category": dict(zip(CATEGORIES, f1_per_cat.tolist())),
        }

    def ensemble_scores(self, scores1: np.ndarray, scores2: np.ndarray,
                        w1: float, w2: float, threshold: float = 0.5) -> np.ndarray:
        """
        Combine scores from two models with weights.

        For SLM + SLM: Both have sigmoid scores (0-1)
        For SLM + LLM: LLM has binary (0/1), treat as scores
        """
        combined = w1 * scores1 + w2 * scores2
        return (combined >= threshold).astype(int)

    def run_evaluation(self):
        """Run full evaluation pipeline."""
        # Load dataset
        df = self.load_dataset()
        y_true = self.get_ground_truth(df)

        print(f"\nDataset shape: {df.shape}")
        print(f"Ground truth shape: {y_true.shape}")
        print(f"Label distribution: {y_true.sum(axis=0)}")

        # Get predictions from base models
        print("\n" + "=" * 60)
        print("Running Base Model Predictions")
        print("=" * 60)

        # DeBERTa
        deberta_scores = self.run_slm_predictions(df, self.deberta, "DeBERTa")
        self.raw_scores["deberta"] = deberta_scores

        # RoBERTa
        roberta_scores = self.run_slm_predictions(df, self.roberta, "RoBERTa")
        self.raw_scores["roberta"] = roberta_scores

        # LLM
        if not self.skip_llm:
            llm_preds = self.run_llm_predictions(df)
            self.raw_scores["llm"] = llm_preds.astype(float)  # Convert to float for ensemble

        # Compute metrics for all 6 configurations
        print("\n" + "=" * 60)
        print("Computing Metrics for All Configurations")
        print("=" * 60)

        results = {}

        # 1. RoBERTa alone
        print("\n[1/6] RoBERTa-Large alone...")
        roberta_preds = (roberta_scores >= 0.5).astype(int)
        results["RoBERTa-Large"] = self.compute_metrics(y_true, roberta_preds)

        # 2. DeBERTa alone
        print("[2/6] DeBERTa-base alone...")
        deberta_preds = (deberta_scores >= 0.5).astype(int)
        results["DeBERTa-base"] = self.compute_metrics(y_true, deberta_preds)

        # 3. RoBERTa + DeBERTa (50/50)
        print("[3/6] RoBERTa + DeBERTa ensemble (50/50)...")
        slm_ensemble_preds = self.ensemble_scores(roberta_scores, deberta_scores, 0.5, 0.5)
        results["RoBERTa + DeBERTa (50/50)"] = self.compute_metrics(y_true, slm_ensemble_preds)

        if not self.skip_llm:
            # 4. DeBERTa + LLM (70/30)
            print("[4/6] DeBERTa + LLM ensemble (70/30)...")
            deberta_llm_preds = self.ensemble_scores(deberta_scores, self.raw_scores["llm"], 0.7, 0.3)
            results["DeBERTa + LLM (70/30)"] = self.compute_metrics(y_true, deberta_llm_preds)

            # 5. RoBERTa + LLM (70/30)
            print("[5/6] RoBERTa + LLM ensemble (70/30)...")
            roberta_llm_preds = self.ensemble_scores(roberta_scores, self.raw_scores["llm"], 0.7, 0.3)
            results["RoBERTa + LLM (70/30)"] = self.compute_metrics(y_true, roberta_llm_preds)

            # 6. LLM alone
            print("[6/6] Mistral-7B LLM alone...")
            llm_preds_binary = self.raw_scores["llm"].astype(int)
            results["Mistral-7B LLM"] = self.compute_metrics(y_true, llm_preds_binary)
        else:
            print("[4-6] Skipped (LLM not loaded)")

        return results, y_true

    def generate_report(self, results: dict, output_path: str = None):
        """Generate markdown comparison report."""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "# Policy Classifier Comparison Results",
            f"\n**Generated:** {timestamp}",
            f"\n**Dataset:** {DATASET_PATH.name}",
            "",
            "## Summary Table",
            "",
            "| Model | F1 Micro | F1 Macro | Exact Match | Precision | Recall |",
            "|-------|----------|----------|-------------|-----------|--------|",
        ]

        # Sort by F1 Micro descending
        sorted_models = sorted(results.items(), key=lambda x: x[1]["f1_micro"], reverse=True)

        for model_name, metrics in sorted_models:
            lines.append(
                f"| {model_name} | "
                f"{metrics['f1_micro']:.4f} | "
                f"{metrics['f1_macro']:.4f} | "
                f"{metrics['exact_match']:.4f} | "
                f"{metrics['precision_micro']:.4f} | "
                f"{metrics['recall_micro']:.4f} |"
            )

        # Per-category breakdown
        lines.extend([
            "",
            "## Per-Category F1 Scores",
            "",
        ])

        # Build per-category table
        header = "| Category |"
        separator = "|----------|"
        for model_name in sorted_models:
            short_name = model_name[0][:15]
            header += f" {short_name} |"
            separator += "--------|"

        lines.append(header)
        lines.append(separator)

        for cat in CATEGORIES:
            row = f"| {cat} |"
            for model_name, metrics in sorted_models:
                f1 = metrics["f1_per_category"].get(cat, 0)
                row += f" {f1:.3f} |"
            lines.append(row)

        # Analysis section
        lines.extend([
            "",
            "## Analysis",
            "",
        ])

        best_model = sorted_models[0]
        lines.append(f"**Best Overall:** {best_model[0]} (F1 Micro: {best_model[1]['f1_micro']:.4f})")

        # Find best per category
        lines.append("\n**Best Per Category:**")
        for cat in CATEGORIES:
            best_for_cat = max(sorted_models, key=lambda x: x[1]["f1_per_category"].get(cat, 0))
            f1 = best_for_cat[1]["f1_per_category"].get(cat, 0)
            lines.append(f"- {cat}: {best_for_cat[0]} ({f1:.3f})")

        # Configuration details
        lines.extend([
            "",
            "## Configuration Details",
            "",
            "| # | Configuration | Description |",
            "|---|---------------|-------------|",
            "| 1 | RoBERTa-Large | RoBERTa-Large fine-tuned classifier |",
            "| 2 | DeBERTa-base | DeBERTa-base fine-tuned classifier |",
            "| 3 | RoBERTa + DeBERTa | SLM ensemble (50/50 weighted average) |",
            "| 4 | DeBERTa + LLM | DeBERTa + Mistral-7B (70/30 weighted) |",
            "| 5 | RoBERTa + LLM | RoBERTa + Mistral-7B (70/30 weighted) |",
            "| 6 | Mistral-7B LLM | Mistral-7B with LoRA fine-tuning |",
            "",
            "**Ensemble Strategy:**",
            "- SLM + SLM: Average sigmoid scores, threshold at 0.5",
            "- SLM + LLM: Weight SLM 70%, LLM 30% (LLM binary → 1.0/0.0)",
        ])

        report = "\n".join(lines)

        # Save or print
        if output_path:
            with open(output_path, "w") as f:
                f.write(report)
            print(f"\nReport saved to: {output_path}")

        return report


def main():
    parser = argparse.ArgumentParser(description="Compare all policy classifier configurations")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM evaluation (faster)")
    parser.add_argument("--output", "-o", type=str, default="/tmp/classifier_comparison_results.md",
                        help="Output path for results markdown")
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce output verbosity")

    args = parser.parse_args()

    print("=" * 60)
    print("Policy Classifier Comparison")
    print("=" * 60)
    print(f"\nOutput: {args.output}")
    print(f"Skip LLM: {args.skip_llm}")

    # Initialize evaluator
    evaluator = MultiModelEvaluator(skip_llm=args.skip_llm, verbose=not args.quiet)

    # Load models
    evaluator.load_models()

    # Run evaluation
    results, y_true = evaluator.run_evaluation()

    # Generate report
    print("\n" + "=" * 60)
    print("Generating Report")
    print("=" * 60)

    report = evaluator.generate_report(results, args.output)

    # Print summary to console
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    print(report)

    # Also save raw results as JSON
    json_output = args.output.replace(".md", ".json")
    with open(json_output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved to: {json_output}")

    print("\n✓ Evaluation complete!")


if __name__ == "__main__":
    main()
