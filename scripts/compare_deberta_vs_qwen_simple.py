#!/usr/bin/env python3
"""
Simple comparison: DeBERTa (CPU) vs Qwen via vLLM API (zero-shot).

Since GPU is occupied by vLLM, we:
1. Train DeBERTa on CPU (slower but works)
2. Test Qwen via existing vLLM API (zero-shot, no training)

Usage:
    python scripts/compare_deberta_vs_qwen_simple.py --field sentiment --samples 500
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)
from datasets import Dataset

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "models" / "comparison_test"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

VLLM_URL = "http://localhost:8766/v1/chat/completions"


def parse_args():
    parser = argparse.ArgumentParser(description='Compare DeBERTa vs Qwen')
    parser.add_argument('--field', type=str, default='sentiment',
                        choices=['sentiment', 'time_to_impact', 'driver_type', 'future_signal'])
    parser.add_argument('--samples', type=int, default=500)
    parser.add_argument('--topic', type=str, default='AI and Machine Learning')
    parser.add_argument('--epochs', type=int, default=3)
    parser.add_argument('--skip-deberta', action='store_true')
    parser.add_argument('--skip-qwen', action='store_true')
    return parser.parse_args()


def export_samples(topic: str, field: str, n_samples: int) -> pd.DataFrame:
    """Export training samples from database."""
    from app.database import Database

    logger.info(f"Exporting {n_samples} samples for {field} from topic '{topic}'")

    db = Database()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.title, a.summary, e.field_value, e.confidence
            FROM enrichment_training_samples e
            JOIN articles a ON e.article_uri = a.uri
            WHERE e.topic = :topic AND e.field_name = :field
              AND e.field_value IS NOT NULL AND e.field_value != ''
            ORDER BY RANDOM()
            LIMIT :limit
        """, {'topic': topic, 'field': field, 'limit': n_samples * 2})
        rows = cursor.fetchall()

    df = pd.DataFrame(rows, columns=['title', 'summary', 'label', 'confidence'])
    df['text'] = df.apply(lambda r: f"{r['title']}. {r['summary']}" if r['summary'] else r['title'], axis=1)

    logger.info(f"Exported {len(df)} samples")
    logger.info(f"Label distribution:\n{df['label'].value_counts()}")

    return df


def prepare_data(df: pd.DataFrame, test_size: float = 0.2, min_samples: int = 5):
    """Split data and create label mappings."""
    df = df.copy()

    label_counts = df['label'].value_counts()
    valid_labels = label_counts[label_counts >= min_samples].index.tolist()

    if len(valid_labels) < len(label_counts):
        removed = set(label_counts.index) - set(valid_labels)
        logger.warning(f"Removing rare labels: {removed}")
        df = df[df['label'].isin(valid_labels)]

    labels = sorted(df['label'].unique())
    label2id = {label: idx for idx, label in enumerate(labels)}
    id2label = {idx: label for label, idx in label2id.items()}

    df['label_id'] = df['label'].map(label2id)

    train_df, test_df = train_test_split(df, test_size=test_size, stratify=df['label_id'], random_state=42)

    logger.info(f"Train: {len(train_df)}, Test: {len(test_df)}, Labels: {labels}")

    return train_df, test_df, {'label2id': label2id, 'id2label': id2label, 'num_labels': len(labels), 'labels': labels}


def train_deberta_cpu(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_info: Dict,
    epochs: int,
    output_dir: Path,
) -> Dict[str, Any]:
    """Train DeBERTa on CPU with a smaller model."""
    logger.info("\n" + "="*60)
    logger.info("Training DeBERTa on CPU")
    logger.info("="*60)

    # Use a smaller, faster model for CPU training
    model_name = 'distilbert-base-uncased'  # Much faster on CPU

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=label_info['num_labels'],
        id2label=label_info['id2label'],
        label2id=label_info['label2id'],
    )

    def tokenize(examples):
        return tokenizer(examples['text'], padding='max_length', truncation=True, max_length=256)

    train_ds = Dataset.from_pandas(train_df[['text', 'label_id']].rename(columns={'label_id': 'labels'}))
    test_ds = Dataset.from_pandas(test_df[['text', 'label_id']].rename(columns={'label_id': 'labels'}))

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=['text'])
    test_ds = test_ds.map(tokenize, batched=True, remove_columns=['text'])

    training_args = TrainingArguments(
        output_dir=str(output_dir / "deberta"),
        num_train_epochs=epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=20,
        report_to="none",
        use_cpu=True,  # Force CPU
    )

    def compute_metrics(eval_pred):
        predictions, labels = eval_pred
        preds = np.argmax(predictions, axis=1)
        return {
            'accuracy': accuracy_score(labels, preds),
            'f1': f1_score(labels, preds, average='weighted'),
        }

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        compute_metrics=compute_metrics,
    )

    start_time = time.time()
    trainer.train()
    train_time = time.time() - start_time

    eval_results = trainer.evaluate()

    # Measure inference speed
    model.eval()
    sample_text = test_df.iloc[0]['text']
    inputs = tokenizer(sample_text, return_tensors='pt', padding=True, truncation=True, max_length=256)

    times = []
    for _ in range(20):
        start = time.time()
        with torch.no_grad():
            model(**inputs)
        times.append(time.time() - start)

    avg_inference_ms = np.mean(times) * 1000

    results = {
        'model': 'DistilBERT (CPU)',
        'model_name': model_name,
        'train_samples': len(train_df),
        'test_samples': len(test_df),
        'train_time_sec': train_time,
        'accuracy': eval_results['eval_accuracy'],
        'f1_weighted': eval_results['eval_f1'],
        'inference_ms': avg_inference_ms,
    }

    logger.info(f"\nDistilBERT Results:")
    logger.info(f"  Accuracy: {results['accuracy']:.4f}")
    logger.info(f"  F1 (weighted): {results['f1_weighted']:.4f}")
    logger.info(f"  Training time: {train_time:.1f}s")
    logger.info(f"  Inference (CPU): {avg_inference_ms:.1f}ms")

    return results


def test_qwen_vllm(
    test_df: pd.DataFrame,
    label_info: Dict,
    field_name: str,
) -> Dict[str, Any]:
    """Test Qwen via vLLM API (zero-shot, no training)."""
    logger.info("\n" + "="*60)
    logger.info("Testing Qwen via vLLM API (zero-shot)")
    logger.info("="*60)

    labels = label_info['labels']
    labels_str = ", ".join(labels)

    correct = 0
    total = 0
    inference_times = []

    # Test on subset for speed
    test_subset = test_df.head(50)

    for _, row in test_subset.iterrows():
        text = row['text'][:500]
        true_label = row['label']

        prompt = f"""Classify the {field_name} of this article.
Options: {labels_str}

Article: {text}

Reply with ONLY the classification label, nothing else."""

        start = time.time()

        try:
            response = requests.post(
                VLLM_URL,
                json={
                    "model": "Qwen/Qwen2.5-3B-Instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 20,
                    "temperature": 0,
                },
                timeout=30
            )
            inference_times.append(time.time() - start)

            if response.status_code == 200:
                result = response.json()
                answer = result['choices'][0]['message']['content'].strip()

                # Check if correct (fuzzy match)
                true_lower = true_label.lower()
                answer_lower = answer.lower()

                if true_lower in answer_lower or answer_lower in true_lower:
                    correct += 1
                elif any(l.lower() in answer_lower for l in labels if l.lower() == true_lower):
                    correct += 1

            total += 1

            if total % 10 == 0:
                logger.info(f"Processed {total}/{len(test_subset)}, accuracy so far: {correct/total:.2%}")

        except Exception as e:
            logger.warning(f"API error: {e}")
            total += 1

    accuracy = correct / total if total > 0 else 0
    avg_inference_ms = np.mean(inference_times) * 1000 if inference_times else 0

    results = {
        'model': 'Qwen-7B (vLLM, zero-shot)',
        'model_name': 'Qwen/Qwen2.5-7B-Instruct',
        'train_samples': 0,  # Zero-shot
        'test_samples': total,
        'train_time_sec': 0,  # No training
        'accuracy': accuracy,
        'f1_weighted': accuracy,  # Approximate
        'inference_ms': avg_inference_ms,
    }

    logger.info(f"\nQwen Zero-Shot Results:")
    logger.info(f"  Accuracy: {results['accuracy']:.4f}")
    logger.info(f"  Inference: {avg_inference_ms:.1f}ms")

    return results


def main():
    args = parse_args()

    logger.info("="*60)
    logger.info("DeBERTa (trained) vs Qwen (zero-shot) Comparison")
    logger.info("="*60)
    logger.info(f"Field: {args.field}")
    logger.info(f"Samples: {args.samples}")

    # Export data
    df = export_samples(args.topic, args.field, args.samples)

    if len(df) < args.samples:
        logger.warning(f"Only {len(df)} samples available")

    train_df, test_df, label_info = prepare_data(df.head(args.samples))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    # Train DeBERTa on CPU
    if not args.skip_deberta:
        deberta_results = train_deberta_cpu(train_df, test_df, label_info, args.epochs, OUTPUT_DIR)
        results.append(deberta_results)

    # Test Qwen via vLLM (zero-shot)
    if not args.skip_qwen:
        qwen_results = test_qwen_vllm(test_df, label_info, args.field)
        results.append(qwen_results)

    # Print comparison
    logger.info("\n" + "="*60)
    logger.info("COMPARISON RESULTS")
    logger.info("="*60)

    comparison_df = pd.DataFrame(results)
    print("\n" + comparison_df.to_string(index=False))

    with open(OUTPUT_DIR / "comparison_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    if len(results) == 2:
        trained = results[0]
        zeroshot = results[1]

        logger.info("\n" + "="*60)
        logger.info("SUMMARY")
        logger.info("="*60)
        logger.info(f"Accuracy:  Trained {trained['accuracy']:.4f} vs Zero-shot {zeroshot['accuracy']:.4f}")
        logger.info(f"Training:  {trained['train_time_sec']:.1f}s (on {trained['train_samples']} samples)")

        acc_diff = trained['accuracy'] - zeroshot['accuracy']
        if acc_diff > 0:
            logger.info(f"\n→ Training improved accuracy by {acc_diff:.2%}")
        else:
            logger.info(f"\n→ Zero-shot matched or exceeded trained model")


if __name__ == "__main__":
    main()
