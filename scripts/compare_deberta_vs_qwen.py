#!/usr/bin/env python3
"""
Compare DeBERTa vs Qwen (LoRA) on 500 training samples.

This script:
1. Exports 500 samples from enrichment_training_samples table
2. Trains DeBERTa classifier
3. Fine-tunes Qwen with LoRA (4-bit quantized)
4. Evaluates both on held-out test set
5. Compares accuracy, F1, and inference speed

Usage:
    python scripts/compare_deberta_vs_qwen.py --field sentiment --samples 500

Requirements:
    pip install transformers datasets peft bitsandbytes accelerate
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
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig,
)
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training

# Configuration
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "models" / "comparison_test"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Compare DeBERTa vs Qwen on classification')
    parser.add_argument('--field', type=str, default='sentiment',
                        choices=['sentiment', 'time_to_impact', 'driver_type', 'future_signal'],
                        help='Field to train on')
    parser.add_argument('--samples', type=int, default=500,
                        help='Number of training samples to use')
    parser.add_argument('--topic', type=str, default='AI and Machine Learning',
                        help='Topic to filter by')
    parser.add_argument('--deberta-model', type=str, default='microsoft/deberta-base',
                        help='DeBERTa model name (use deberta-base for lower memory)')
    parser.add_argument('--qwen-model', type=str, default='Qwen/Qwen2.5-1.5B-Instruct',
                        help='Qwen model name (smaller for faster testing)')
    parser.add_argument('--epochs', type=int, default=3,
                        help='Training epochs')
    parser.add_argument('--skip-deberta', action='store_true',
                        help='Skip DeBERTa training')
    parser.add_argument('--skip-qwen', action='store_true',
                        help='Skip Qwen LoRA training')
    return parser.parse_args()


def export_samples(topic: str, field: str, n_samples: int) -> pd.DataFrame:
    """Export training samples from database."""
    from app.database import Database

    logger.info(f"Exporting {n_samples} samples for {field} from topic '{topic}'")

    db = Database()
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get samples with article text
        cursor.execute("""
            SELECT
                a.title,
                a.summary,
                e.field_value,
                e.confidence
            FROM enrichment_training_samples e
            JOIN articles a ON e.article_uri = a.uri
            WHERE e.topic = :topic
              AND e.field_name = :field
              AND e.field_value IS NOT NULL
              AND e.field_value != ''
            ORDER BY RANDOM()
            LIMIT :limit
        """, {'topic': topic, 'field': field, 'limit': n_samples * 2})  # Get extra for test split

        rows = cursor.fetchall()

    df = pd.DataFrame(rows, columns=['title', 'summary', 'label', 'confidence'])
    df['text'] = df.apply(lambda r: f"{r['title']}. {r['summary']}" if r['summary'] else r['title'], axis=1)

    logger.info(f"Exported {len(df)} samples")
    logger.info(f"Label distribution:\n{df['label'].value_counts()}")

    return df


def prepare_data(df: pd.DataFrame, test_size: float = 0.2, min_samples: int = 5) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """Split data and create label mappings."""
    df = df.copy()

    # Filter out rare labels (need at least min_samples for stratified split)
    label_counts = df['label'].value_counts()
    valid_labels = label_counts[label_counts >= min_samples].index.tolist()

    if len(valid_labels) < len(label_counts):
        removed = set(label_counts.index) - set(valid_labels)
        logger.warning(f"Removing rare labels with <{min_samples} samples: {removed}")
        df = df[df['label'].isin(valid_labels)]

    # Create label mapping
    labels = sorted(df['label'].unique())
    label2id = {label: idx for idx, label in enumerate(labels)}
    id2label = {idx: label for label, idx in label2id.items()}

    df['label_id'] = df['label'].map(label2id)

    # Split
    train_df, test_df = train_test_split(df, test_size=test_size, stratify=df['label_id'], random_state=42)

    logger.info(f"Train: {len(train_df)}, Test: {len(test_df)}, Labels: {labels}")

    return train_df, test_df, {'label2id': label2id, 'id2label': id2label, 'num_labels': len(labels)}


def train_deberta(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_info: Dict,
    model_name: str,
    epochs: int,
    output_dir: Path,
) -> Dict[str, Any]:
    """Train DeBERTa classifier."""
    logger.info("\n" + "="*60)
    logger.info("Training DeBERTa")
    logger.info("="*60)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=label_info['num_labels'],
        id2label=label_info['id2label'],
        label2id=label_info['label2id'],
    )
    model.to(device)

    # Create datasets
    def tokenize(examples):
        return tokenizer(examples['text'], padding='max_length', truncation=True, max_length=256)

    train_ds = Dataset.from_pandas(train_df[['text', 'label_id']].rename(columns={'label_id': 'labels'}))
    test_ds = Dataset.from_pandas(test_df[['text', 'label_id']].rename(columns={'label_id': 'labels'}))

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=['text'])
    test_ds = test_ds.map(tokenize, batched=True, remove_columns=['text'])

    # Training args (smaller batch sizes for limited GPU memory)
    training_args = TrainingArguments(
        output_dir=str(output_dir / "deberta"),
        num_train_epochs=epochs,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=8,
        gradient_accumulation_steps=4,
        learning_rate=2e-5,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=20,
        report_to="none",
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

    # Train
    start_time = time.time()
    trainer.train()
    train_time = time.time() - start_time

    # Evaluate
    eval_results = trainer.evaluate()

    # Measure inference speed
    model.eval()
    sample_text = test_df.iloc[0]['text']
    inputs = tokenizer(sample_text, return_tensors='pt', padding=True, truncation=True, max_length=256)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Warmup
    for _ in range(5):
        with torch.no_grad():
            model(**inputs)

    # Measure
    times = []
    for _ in range(50):
        start = time.time()
        with torch.no_grad():
            model(**inputs)
        times.append(time.time() - start)

    avg_inference_ms = np.mean(times) * 1000

    results = {
        'model': 'DeBERTa',
        'model_name': model_name,
        'train_samples': len(train_df),
        'test_samples': len(test_df),
        'train_time_sec': train_time,
        'accuracy': eval_results['eval_accuracy'],
        'f1_weighted': eval_results['eval_f1'],
        'inference_ms': avg_inference_ms,
    }

    logger.info(f"\nDeBERTa Results:")
    logger.info(f"  Accuracy: {results['accuracy']:.4f}")
    logger.info(f"  F1 (weighted): {results['f1_weighted']:.4f}")
    logger.info(f"  Training time: {train_time:.1f}s")
    logger.info(f"  Inference: {avg_inference_ms:.1f}ms")

    return results


def train_qwen_lora(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    label_info: Dict,
    model_name: str,
    epochs: int,
    output_dir: Path,
    field_name: str,
) -> Dict[str, Any]:
    """Train Qwen with LoRA."""
    logger.info("\n" + "="*60)
    logger.info("Training Qwen with LoRA")
    logger.info("="*60)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Quantization config for 4-bit
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model with quantization
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # Prepare for training
    model = prepare_model_for_kbit_training(model)

    # LoRA config
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Prepare data with instruction format
    labels_str = ", ".join(label_info['id2label'].values())

    def format_prompt(row):
        return f"""Classify the following article's {field_name}.
Options: {labels_str}

Article: {row['text'][:500]}

{field_name.replace('_', ' ').title()}: {row['label']}"""

    def format_test_prompt(row):
        return f"""Classify the following article's {field_name}.
Options: {labels_str}

Article: {row['text'][:500]}

{field_name.replace('_', ' ').title()}:"""

    train_df = train_df.copy()
    train_df['prompt'] = train_df.apply(format_prompt, axis=1)

    # Tokenize
    def tokenize(examples):
        result = tokenizer(
            examples['prompt'],
            padding='max_length',
            truncation=True,
            max_length=512,
        )
        result['labels'] = result['input_ids'].copy()
        return result

    train_ds = Dataset.from_pandas(train_df[['prompt']])
    train_ds = train_ds.map(tokenize, batched=True, remove_columns=['prompt'])

    # Training args (smaller for LoRA)
    training_args = TrainingArguments(
        output_dir=str(output_dir / "qwen_lora"),
        num_train_epochs=epochs,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_ratio=0.1,
        weight_decay=0.01,
        logging_steps=10,
        save_strategy="epoch",
        fp16=True,
        report_to="none",
        optim="paged_adamw_8bit",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        tokenizer=tokenizer,
    )

    # Train
    start_time = time.time()
    trainer.train()
    train_time = time.time() - start_time

    # Evaluate by generating
    model.eval()
    correct = 0
    total = 0
    inference_times = []

    for _, row in test_df.iterrows():
        prompt = format_test_prompt(row)
        inputs = tokenizer(prompt, return_tensors='pt', truncation=True, max_length=512)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        start = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=10,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
        inference_times.append(time.time() - start)

        generated = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Extract the answer after the prompt
        answer = generated[len(prompt):].strip().split('\n')[0].strip()

        # Check if correct (fuzzy match)
        true_label = row['label'].lower()
        if true_label in answer.lower() or answer.lower() in true_label:
            correct += 1
        total += 1

        if total >= 50:  # Limit evaluation for speed
            break

    accuracy = correct / total
    avg_inference_ms = np.mean(inference_times) * 1000

    results = {
        'model': 'Qwen-LoRA',
        'model_name': model_name,
        'train_samples': len(train_df),
        'test_samples': total,
        'train_time_sec': train_time,
        'accuracy': accuracy,
        'f1_weighted': accuracy,  # Approximate
        'inference_ms': avg_inference_ms,
    }

    logger.info(f"\nQwen-LoRA Results:")
    logger.info(f"  Accuracy: {results['accuracy']:.4f}")
    logger.info(f"  Training time: {train_time:.1f}s")
    logger.info(f"  Inference: {avg_inference_ms:.1f}ms")

    return results


def main():
    args = parse_args()

    logger.info("="*60)
    logger.info("DeBERTa vs Qwen Comparison Test")
    logger.info("="*60)
    logger.info(f"Field: {args.field}")
    logger.info(f"Samples: {args.samples}")
    logger.info(f"Topic: {args.topic}")

    # Export data
    df = export_samples(args.topic, args.field, args.samples)

    if len(df) < args.samples:
        logger.warning(f"Only {len(df)} samples available, using all of them")

    # Prepare data
    train_df, test_df, label_info = prepare_data(df.head(args.samples))

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    # Train DeBERTa
    if not args.skip_deberta:
        deberta_results = train_deberta(
            train_df, test_df, label_info,
            args.deberta_model, args.epochs, OUTPUT_DIR
        )
        results.append(deberta_results)

    # Train Qwen LoRA
    if not args.skip_qwen:
        qwen_results = train_qwen_lora(
            train_df, test_df, label_info,
            args.qwen_model, args.epochs, OUTPUT_DIR, args.field
        )
        results.append(qwen_results)

    # Print comparison
    logger.info("\n" + "="*60)
    logger.info("COMPARISON RESULTS")
    logger.info("="*60)

    comparison_df = pd.DataFrame(results)
    print("\n" + comparison_df.to_string(index=False))

    # Save results
    with open(OUTPUT_DIR / "comparison_results.json", "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\nResults saved to {OUTPUT_DIR / 'comparison_results.json'}")

    # Summary
    if len(results) == 2:
        deberta = results[0]
        qwen = results[1]

        logger.info("\n" + "="*60)
        logger.info("SUMMARY")
        logger.info("="*60)
        logger.info(f"Accuracy:  DeBERTa {deberta['accuracy']:.4f} vs Qwen {qwen['accuracy']:.4f}")
        logger.info(f"Speed:     DeBERTa {deberta['inference_ms']:.1f}ms vs Qwen {qwen['inference_ms']:.1f}ms")
        logger.info(f"Training:  DeBERTa {deberta['train_time_sec']:.1f}s vs Qwen {qwen['train_time_sec']:.1f}s")

        if deberta['accuracy'] >= qwen['accuracy']:
            logger.info(f"\n→ DeBERTa wins on accuracy ({deberta['accuracy']:.4f} >= {qwen['accuracy']:.4f})")
        else:
            logger.info(f"\n→ Qwen wins on accuracy ({qwen['accuracy']:.4f} > {deberta['accuracy']:.4f})")

        speed_ratio = qwen['inference_ms'] / deberta['inference_ms']
        logger.info(f"→ DeBERTa is {speed_ratio:.1f}x faster on inference")


if __name__ == "__main__":
    main()
