#!/usr/bin/env python3
"""
Evaluate SLM Pipeline vs LLM Quality

This script compares the quality of SLM-based article enrichment
against the original LLM-based enrichment.

Evaluates:
1. Relevance Classifier - Binary classification accuracy
2. Summarization - ROUGE, BERTScore, length analysis
3. Multi-task Enrichment - Per-task accuracy, F1, agreement with LLM

Usage:
    python scripts/evaluate_slm_pipeline.py

    # Evaluate specific components
    python scripts/evaluate_slm_pipeline.py --relevance --summarization
    python scripts/evaluate_slm_pipeline.py --enrichment --sample-size 500

Requirements:
    pip install transformers torch pandas scikit-learn rouge-score bert-score

Output:
    Reports comparison metrics to stdout and optionally saves to JSON
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    cohen_kappa_score,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "training"
OUTPUT_DIR = BASE_DIR / "data" / "evaluation"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Evaluate SLM pipeline')
    parser.add_argument('--relevance', action='store_true',
                        help='Evaluate relevance classifier')
    parser.add_argument('--summarization', action='store_true',
                        help='Evaluate summarization model')
    parser.add_argument('--enrichment', action='store_true',
                        help='Evaluate multi-task enrichment model')
    parser.add_argument('--all', action='store_true',
                        help='Evaluate all components')
    parser.add_argument('--sample-size', type=int, default=None,
                        help='Limit evaluation to N samples')
    parser.add_argument('--output', type=str, default=None,
                        help='Save results to JSON file')
    parser.add_argument('--skip-llm-comparison', action='store_true',
                        help='Skip LLM comparison (faster, local-only)')
    return parser.parse_args()


def evaluate_relevance(sample_size: Optional[int] = None) -> Dict[str, Any]:
    """
    Evaluate relevance classifier on test set.

    Returns:
        Dict with evaluation metrics
    """
    logger.info("=" * 60)
    logger.info("Evaluating Relevance Classifier")
    logger.info("=" * 60)

    try:
        from app.services.relevance_classifier_service import get_relevance_classifier
    except ImportError as e:
        logger.error(f"Failed to import relevance classifier: {e}")
        return {"error": str(e)}

    # Load test data
    test_df = pd.read_json(DATA_DIR / "relevance_test.json")
    if sample_size:
        test_df = test_df.sample(min(sample_size, len(test_df)), random_state=42)

    logger.info(f"Evaluating on {len(test_df)} samples")

    # Get classifier
    classifier = get_relevance_classifier()
    if not classifier.is_available():
        logger.warning("Relevance classifier not available, skipping")
        return {"error": "Model not available", "status": classifier.get_status()}

    # Run predictions
    predictions = []
    labels = []
    latencies = []

    for idx, row in test_df.iterrows():
        start = time.time()

        result = classifier.classify(
            topic=row['topic'],
            title=row['title'],
            summary=row['summary']
        )

        latencies.append(time.time() - start)

        predictions.append(1 if result['relevant'] else 0)
        labels.append(row['label'])

    # Compute metrics
    metrics = {
        "accuracy": accuracy_score(labels, predictions),
        "precision": precision_score(labels, predictions, zero_division=0),
        "recall": recall_score(labels, predictions, zero_division=0),
        "f1": f1_score(labels, predictions, zero_division=0),
        "kappa": cohen_kappa_score(labels, predictions),
        "avg_latency_ms": np.mean(latencies) * 1000,
        "p95_latency_ms": np.percentile(latencies, 95) * 1000,
        "samples": len(test_df),
    }

    # Confusion matrix
    cm = confusion_matrix(labels, predictions)
    metrics["confusion_matrix"] = cm.tolist()

    # Classification report
    logger.info(f"\nRelevance Classifier Results:")
    logger.info(f"  Accuracy: {metrics['accuracy']:.4f}")
    logger.info(f"  Precision: {metrics['precision']:.4f}")
    logger.info(f"  Recall: {metrics['recall']:.4f}")
    logger.info(f"  F1: {metrics['f1']:.4f}")
    logger.info(f"  Cohen's Kappa: {metrics['kappa']:.4f}")
    logger.info(f"  Avg Latency: {metrics['avg_latency_ms']:.2f}ms")
    logger.info(f"\nClassification Report:")
    logger.info(classification_report(labels, predictions, target_names=['Irrelevant', 'Relevant']))

    return metrics


def evaluate_summarization(
    sample_size: Optional[int] = None,
    skip_llm: bool = False
) -> Dict[str, Any]:
    """
    Evaluate summarization model on test set.

    Returns:
        Dict with evaluation metrics (ROUGE, BERTScore, length stats)
    """
    logger.info("=" * 60)
    logger.info("Evaluating Summarization Model")
    logger.info("=" * 60)

    try:
        from app.services.summarization_service import get_summarization_service
    except ImportError as e:
        logger.error(f"Failed to import summarization service: {e}")
        return {"error": str(e)}

    # Load test data
    test_df = pd.read_json(DATA_DIR / "summarization_test.json")
    if sample_size:
        test_df = test_df.sample(min(sample_size, len(test_df)), random_state=42)

    logger.info(f"Evaluating on {len(test_df)} samples")

    # Get summarizer
    summarizer = get_summarization_service()
    if not summarizer.is_available():
        logger.warning("Summarization model not available, using LLM fallback")

    # Generate summaries
    generated = []
    references = []
    latencies = []

    for idx, row in test_df.iterrows():
        start = time.time()

        result = summarizer.summarize(
            title=row['title'],
            content=row['content']
        )

        latencies.append(time.time() - start)

        generated.append(result['summary'])
        references.append(row['summary'])

    # Compute ROUGE scores
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)

        rouge_scores = {'rouge1': [], 'rouge2': [], 'rougeL': []}
        for gen, ref in zip(generated, references):
            scores = scorer.score(ref, gen)
            rouge_scores['rouge1'].append(scores['rouge1'].fmeasure)
            rouge_scores['rouge2'].append(scores['rouge2'].fmeasure)
            rouge_scores['rougeL'].append(scores['rougeL'].fmeasure)

        metrics = {
            "rouge1": np.mean(rouge_scores['rouge1']),
            "rouge2": np.mean(rouge_scores['rouge2']),
            "rougeL": np.mean(rouge_scores['rougeL']),
        }
    except ImportError:
        logger.warning("rouge_score not installed, skipping ROUGE metrics")
        metrics = {}

    # Compute BERTScore
    try:
        from bert_score import score as bert_score
        P, R, F1 = bert_score(generated, references, lang='en', verbose=False)
        metrics['bert_score_f1'] = F1.mean().item()
        metrics['bert_score_p'] = P.mean().item()
        metrics['bert_score_r'] = R.mean().item()
    except ImportError:
        logger.warning("bert_score not installed, skipping BERTScore metrics")

    # Length statistics
    gen_lengths = [len(s.split()) for s in generated]
    ref_lengths = [len(s.split()) for s in references]

    metrics.update({
        "gen_length_mean": np.mean(gen_lengths),
        "gen_length_std": np.std(gen_lengths),
        "ref_length_mean": np.mean(ref_lengths),
        "length_ratio": np.mean(gen_lengths) / max(np.mean(ref_lengths), 1),
        "avg_latency_ms": np.mean(latencies) * 1000,
        "p95_latency_ms": np.percentile(latencies, 95) * 1000,
        "samples": len(test_df),
    })

    # Print results
    logger.info(f"\nSummarization Results:")
    logger.info(f"  ROUGE-1: {metrics.get('rouge1', 'N/A'):.4f}" if 'rouge1' in metrics else "  ROUGE-1: N/A")
    logger.info(f"  ROUGE-2: {metrics.get('rouge2', 'N/A'):.4f}" if 'rouge2' in metrics else "  ROUGE-2: N/A")
    logger.info(f"  ROUGE-L: {metrics.get('rougeL', 'N/A'):.4f}" if 'rougeL' in metrics else "  ROUGE-L: N/A")
    logger.info(f"  BERTScore F1: {metrics.get('bert_score_f1', 'N/A'):.4f}" if 'bert_score_f1' in metrics else "  BERTScore F1: N/A")
    logger.info(f"  Avg Generated Length: {metrics['gen_length_mean']:.1f} words")
    logger.info(f"  Avg Reference Length: {metrics['ref_length_mean']:.1f} words")
    logger.info(f"  Avg Latency: {metrics['avg_latency_ms']:.2f}ms")

    # Sample outputs
    logger.info("\nSample Summaries:")
    for i in range(min(3, len(test_df))):
        logger.info(f"\n--- Sample {i+1} ---")
        logger.info(f"Title: {test_df.iloc[i]['title'][:80]}...")
        logger.info(f"Reference: {references[i][:200]}...")
        logger.info(f"Generated: {generated[i][:200]}...")

    return metrics


def evaluate_enrichment(
    sample_size: Optional[int] = None,
    skip_llm: bool = False
) -> Dict[str, Any]:
    """
    Evaluate multi-task enrichment model on test set.

    Returns:
        Dict with per-task evaluation metrics
    """
    logger.info("=" * 60)
    logger.info("Evaluating Multi-Task Enrichment Model")
    logger.info("=" * 60)

    try:
        from app.services.enrichment_service import get_enrichment_service
    except ImportError as e:
        logger.error(f"Failed to import enrichment service: {e}")
        return {"error": str(e)}

    # Load test data and label mappings
    test_df = pd.read_json(DATA_DIR / "enrichment_test.json")
    with open(DATA_DIR / "label_mappings.json") as f:
        label_mappings = json.load(f)

    if sample_size:
        test_df = test_df.sample(min(sample_size, len(test_df)), random_state=42)

    logger.info(f"Evaluating on {len(test_df)} samples")

    # Get enrichment service
    enricher = get_enrichment_service()
    if not enricher.is_available():
        logger.warning("Enrichment model not available, using LLM fallback")

    # Define tasks to evaluate
    tasks = ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']
    tasks = [t for t in tasks if t in test_df.columns and t in label_mappings]

    # Run predictions
    predictions = {task: [] for task in tasks}
    labels = {task: [] for task in tasks}
    confidences = {task: [] for task in tasks}
    latencies = []

    for idx, row in test_df.iterrows():
        start = time.time()

        result = enricher.enrich(
            title=row['title'],
            summary=row['summary']
        )

        latencies.append(time.time() - start)

        for task in tasks:
            if task in result and pd.notna(row.get(task)):
                predictions[task].append(result[task])
                labels[task].append(row[task])
                confidences[task].append(result.get(f'{task}_confidence', 0))

    # Compute metrics per task
    metrics = {
        "avg_latency_ms": np.mean(latencies) * 1000,
        "p95_latency_ms": np.percentile(latencies, 95) * 1000,
        "samples": len(test_df),
        "tasks": {},
    }

    for task in tasks:
        if not predictions[task]:
            continue

        # Map to numeric for sklearn
        all_labels = list(set(predictions[task]) | set(labels[task]))
        label_to_id = {l: i for i, l in enumerate(all_labels)}

        pred_ids = [label_to_id.get(p, -1) for p in predictions[task]]
        true_ids = [label_to_id.get(l, -1) for l in labels[task]]

        # Filter out invalid mappings
        valid_mask = [(p >= 0 and t >= 0) for p, t in zip(pred_ids, true_ids)]
        pred_ids = [p for p, v in zip(pred_ids, valid_mask) if v]
        true_ids = [t for t, v in zip(true_ids, valid_mask) if v]
        task_confidences = [c for c, v in zip(confidences[task], valid_mask) if v]

        if not pred_ids:
            continue

        task_metrics = {
            "accuracy": accuracy_score(true_ids, pred_ids),
            "f1_macro": f1_score(true_ids, pred_ids, average='macro', zero_division=0),
            "f1_weighted": f1_score(true_ids, pred_ids, average='weighted', zero_division=0),
            "kappa": cohen_kappa_score(true_ids, pred_ids),
            "avg_confidence": np.mean(task_confidences) if task_confidences else 0,
            "samples": len(pred_ids),
            "labels": all_labels,
        }

        metrics["tasks"][task] = task_metrics

        logger.info(f"\n{task.upper()} Results:")
        logger.info(f"  Accuracy: {task_metrics['accuracy']:.4f}")
        logger.info(f"  F1 (macro): {task_metrics['f1_macro']:.4f}")
        logger.info(f"  F1 (weighted): {task_metrics['f1_weighted']:.4f}")
        logger.info(f"  Cohen's Kappa: {task_metrics['kappa']:.4f}")
        logger.info(f"  Avg Confidence: {task_metrics['avg_confidence']:.4f}")

    # Overall metrics
    f1_scores = [m['f1_weighted'] for m in metrics['tasks'].values()]
    if f1_scores:
        metrics['avg_f1_weighted'] = np.mean(f1_scores)
        logger.info(f"\nOverall Average F1 (weighted): {metrics['avg_f1_weighted']:.4f}")

    return metrics


def main():
    """Main evaluation function."""
    args = parse_args()

    # Default to all if no specific component selected
    if not any([args.relevance, args.summarization, args.enrichment, args.all]):
        args.all = True

    if args.all:
        args.relevance = args.summarization = args.enrichment = True

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "sample_size": args.sample_size,
        "skip_llm_comparison": args.skip_llm_comparison,
    }

    # Run evaluations
    if args.relevance:
        results['relevance'] = evaluate_relevance(args.sample_size)

    if args.summarization:
        results['summarization'] = evaluate_summarization(
            args.sample_size,
            args.skip_llm_comparison
        )

    if args.enrichment:
        results['enrichment'] = evaluate_enrichment(
            args.sample_size,
            args.skip_llm_comparison
        )

    # Save results
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = OUTPUT_DIR / f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\nResults saved to: {output_path}")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 60)

    if 'relevance' in results and 'error' not in results['relevance']:
        logger.info(f"\nRelevance Classifier:")
        logger.info(f"  F1: {results['relevance']['f1']:.4f}")
        logger.info(f"  Latency: {results['relevance']['avg_latency_ms']:.2f}ms")

    if 'summarization' in results and 'error' not in results['summarization']:
        logger.info(f"\nSummarization:")
        if 'rouge1' in results['summarization']:
            logger.info(f"  ROUGE-1: {results['summarization']['rouge1']:.4f}")
        if 'bert_score_f1' in results['summarization']:
            logger.info(f"  BERTScore F1: {results['summarization']['bert_score_f1']:.4f}")
        logger.info(f"  Latency: {results['summarization']['avg_latency_ms']:.2f}ms")

    if 'enrichment' in results and 'error' not in results['enrichment']:
        logger.info(f"\nMulti-task Enrichment:")
        if 'avg_f1_weighted' in results['enrichment']:
            logger.info(f"  Avg F1: {results['enrichment']['avg_f1_weighted']:.4f}")
        logger.info(f"  Latency: {results['enrichment']['avg_latency_ms']:.2f}ms")

    return results


if __name__ == "__main__":
    main()
