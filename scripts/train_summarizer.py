#!/usr/bin/env python3
"""
Train a summarization model for article summarization.

This script fine-tunes T5-base or BART-large on LLM-generated summaries
(knowledge distillation) to create a fast, local summarization model.

Evaluation uses multiple metrics:
- ROUGE (ROUGE-1, ROUGE-2, ROUGE-L) for n-gram overlap
- BERTScore for semantic similarity
- Length statistics for summary quality

Usage:
    python scripts/train_summarizer.py

    # With custom settings
    python scripts/train_summarizer.py --model t5-base --epochs 5

Requirements:
    pip install transformers datasets accelerate torch rouge-score bert-score

Output:
    models/summarizer/final/
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
    EarlyStoppingCallback,
)
from datasets import Dataset

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "training"
OUTPUT_DIR = BASE_DIR / "models" / "summarizer"

# Model choices
MODELS = {
    't5-small': 't5-small',
    't5-base': 't5-base',
    'bart-base': 'facebook/bart-base',
    'bart-large': 'facebook/bart-large',
    'bart-large-cnn': 'facebook/bart-large-cnn',
    'pegasus-xsum': 'google/pegasus-xsum',
}

# Default hyperparameters
DEFAULT_MODEL = 't5-base'
BATCH_SIZE = 4
MAX_SOURCE_LENGTH = 1024  # Input article length
MAX_TARGET_LENGTH = 128   # Summary length
LEARNING_RATE = 3e-5
NUM_EPOCHS = 5
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train summarization model')
    parser.add_argument('--model', type=str, default=DEFAULT_MODEL,
                        choices=list(MODELS.keys()),
                        help=f'Model to train (default: {DEFAULT_MODEL})')
    parser.add_argument('--epochs', type=int, default=NUM_EPOCHS,
                        help=f'Number of training epochs (default: {NUM_EPOCHS})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Batch size (default: {BATCH_SIZE})')
    parser.add_argument('--lr', type=float, default=LEARNING_RATE,
                        help=f'Learning rate (default: {LEARNING_RATE})')
    parser.add_argument('--max-source-length', type=int, default=MAX_SOURCE_LENGTH,
                        help=f'Max source sequence length (default: {MAX_SOURCE_LENGTH})')
    parser.add_argument('--max-target-length', type=int, default=MAX_TARGET_LENGTH,
                        help=f'Max target sequence length (default: {MAX_TARGET_LENGTH})')
    parser.add_argument('--use-title-prefix', action='store_true', default=True,
                        help='Prepend title to content as context')
    parser.add_argument('--skip-bert-score', action='store_true',
                        help='Skip BERTScore computation (faster evaluation)')
    return parser.parse_args()


def load_training_data(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load summarization training data from exported JSON files.

    Args:
        data_dir: Directory containing summarization_train.json, etc.

    Returns:
        train_df, val_df, test_df
    """
    logger.info(f"Loading data from {data_dir}")

    train_df = pd.read_json(data_dir / "summarization_train.json")
    val_df = pd.read_json(data_dir / "summarization_val.json")
    test_df = pd.read_json(data_dir / "summarization_test.json")

    logger.info(f"Loaded: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # Log statistics
    for name, df in [('train', train_df), ('val', val_df), ('test', test_df)]:
        logger.info(f"  {name}:")
        logger.info(f"    Content length: mean={df['content_length'].mean():.0f}, median={df['content_length'].median():.0f}")
        logger.info(f"    Summary length: mean={df['summary_length'].mean():.0f}, median={df['summary_length'].median():.0f}")

    return train_df, val_df, test_df


def prepare_source_text(row, use_title_prefix: bool = True) -> str:
    """
    Prepare source text for summarization.

    Args:
        row: DataFrame row with 'title', 'content' columns
        use_title_prefix: Whether to prepend title

    Returns:
        Formatted source text
    """
    title = str(row['title']).strip() if row['title'] else ""
    content = str(row['content']).strip() if row['content'] else ""

    if use_title_prefix and title:
        # For T5, use task prefix
        return f"summarize: {title}\n\n{content}"
    else:
        return f"summarize: {content}"


def create_datasets(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    tokenizer,
    max_source_length: int,
    max_target_length: int,
    use_title_prefix: bool = True,
) -> Tuple[Dataset, Dataset, Dataset]:
    """
    Create HuggingFace datasets from DataFrames.

    Args:
        train_df, val_df, test_df: Pandas DataFrames
        tokenizer: HuggingFace tokenizer
        max_source_length: Maximum source sequence length
        max_target_length: Maximum target sequence length
        use_title_prefix: Whether to prepend title to content

    Returns:
        train_dataset, val_dataset, test_dataset
    """
    # Prepare source text for each dataset
    train_df = train_df.copy()
    val_df = val_df.copy()
    test_df = test_df.copy()

    train_df['source'] = train_df.apply(lambda x: prepare_source_text(x, use_title_prefix), axis=1)
    val_df['source'] = val_df.apply(lambda x: prepare_source_text(x, use_title_prefix), axis=1)
    test_df['source'] = test_df.apply(lambda x: prepare_source_text(x, use_title_prefix), axis=1)

    def preprocess_function(examples):
        """Tokenize source and target."""
        # Tokenize inputs
        model_inputs = tokenizer(
            examples["source"],
            max_length=max_source_length,
            truncation=True,
            padding="max_length",
        )

        # Tokenize targets (as_target_tokenizer is deprecated, use text_target)
        labels = tokenizer(
            text_target=examples["summary"],
            max_length=max_target_length,
            truncation=True,
            padding="max_length",
        )

        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    # Convert to HuggingFace datasets
    train_dataset = Dataset.from_pandas(train_df[["source", "summary"]]).map(
        preprocess_function, batched=True, remove_columns=["source", "summary"]
    )
    val_dataset = Dataset.from_pandas(val_df[["source", "summary"]]).map(
        preprocess_function, batched=True, remove_columns=["source", "summary"]
    )
    test_dataset = Dataset.from_pandas(test_df[["source", "summary"]]).map(
        preprocess_function, batched=True, remove_columns=["source", "summary"]
    )

    return train_dataset, val_dataset, test_dataset, val_df, test_df


def compute_rouge_metrics(predictions: List[str], references: List[str]) -> Dict[str, float]:
    """
    Compute ROUGE metrics.

    Args:
        predictions: Generated summaries
        references: Reference summaries

    Returns:
        Dict with ROUGE-1, ROUGE-2, ROUGE-L scores
    """
    try:
        from rouge_score import rouge_scorer
    except ImportError:
        logger.warning("rouge_score not installed. Install with: pip install rouge-score")
        return {}

    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)

    scores = {
        'rouge1_f': [],
        'rouge1_p': [],
        'rouge1_r': [],
        'rouge2_f': [],
        'rouge2_p': [],
        'rouge2_r': [],
        'rougeL_f': [],
        'rougeL_p': [],
        'rougeL_r': [],
    }

    for pred, ref in zip(predictions, references):
        result = scorer.score(ref, pred)
        scores['rouge1_f'].append(result['rouge1'].fmeasure)
        scores['rouge1_p'].append(result['rouge1'].precision)
        scores['rouge1_r'].append(result['rouge1'].recall)
        scores['rouge2_f'].append(result['rouge2'].fmeasure)
        scores['rouge2_p'].append(result['rouge2'].precision)
        scores['rouge2_r'].append(result['rouge2'].recall)
        scores['rougeL_f'].append(result['rougeL'].fmeasure)
        scores['rougeL_p'].append(result['rougeL'].precision)
        scores['rougeL_r'].append(result['rougeL'].recall)

    return {k: np.mean(v) for k, v in scores.items()}


def compute_bert_score(predictions: List[str], references: List[str]) -> Dict[str, float]:
    """
    Compute BERTScore for semantic similarity.

    Args:
        predictions: Generated summaries
        references: Reference summaries

    Returns:
        Dict with BERTScore precision, recall, F1
    """
    try:
        from bert_score import score as bert_score
    except ImportError:
        logger.warning("bert_score not installed. Install with: pip install bert-score")
        return {}

    P, R, F1 = bert_score(
        predictions,
        references,
        lang='en',
        verbose=False,
        rescale_with_baseline=True
    )

    return {
        'bert_score_p': P.mean().item(),
        'bert_score_r': R.mean().item(),
        'bert_score_f1': F1.mean().item(),
    }


def compute_length_stats(predictions: List[str], references: List[str]) -> Dict[str, float]:
    """
    Compute length statistics for generated summaries.

    Args:
        predictions: Generated summaries
        references: Reference summaries

    Returns:
        Dict with length statistics
    """
    pred_lengths = [len(p.split()) for p in predictions]
    ref_lengths = [len(r.split()) for r in references]

    return {
        'pred_length_mean': np.mean(pred_lengths),
        'pred_length_std': np.std(pred_lengths),
        'ref_length_mean': np.mean(ref_lengths),
        'ref_length_std': np.std(ref_lengths),
        'length_ratio': np.mean(pred_lengths) / max(np.mean(ref_lengths), 1),
    }


def create_metric_function(tokenizer, skip_bert_score: bool = False):
    """
    Create compute_metrics function for trainer.

    Args:
        tokenizer: HuggingFace tokenizer
        skip_bert_score: Whether to skip BERTScore computation

    Returns:
        compute_metrics function
    """
    def compute_metrics(eval_pred):
        predictions, labels = eval_pred

        # Decode predictions
        decoded_preds = tokenizer.batch_decode(predictions, skip_special_tokens=True)

        # Replace -100 in labels (padding) with pad token id
        labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
        decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

        # Clean up
        decoded_preds = [pred.strip() for pred in decoded_preds]
        decoded_labels = [label.strip() for label in decoded_labels]

        # Compute metrics
        metrics = {}

        # ROUGE scores
        rouge_metrics = compute_rouge_metrics(decoded_preds, decoded_labels)
        metrics.update(rouge_metrics)

        # BERTScore (optional, slow)
        if not skip_bert_score:
            bert_metrics = compute_bert_score(decoded_preds, decoded_labels)
            metrics.update(bert_metrics)

        # Length statistics
        length_stats = compute_length_stats(decoded_preds, decoded_labels)
        metrics.update(length_stats)

        return metrics

    return compute_metrics


def train(args):
    """Main training function."""
    logger.info("=" * 60)
    logger.info("Summarization Model Training")
    logger.info("=" * 60)

    model_name = MODELS[args.model]
    logger.info(f"Model: {args.model} ({model_name})")
    logger.info(f"Epochs: {args.epochs}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Learning rate: {args.lr}")
    logger.info(f"Max source length: {args.max_source_length}")
    logger.info(f"Max target length: {args.max_target_length}")

    # Check GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.info("Warning: No GPU detected, training will be slow")

    # Load data
    train_df, val_df, test_df = load_training_data(DATA_DIR)

    # Load tokenizer
    logger.info(f"\nLoading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Create datasets
    train_dataset, val_dataset, test_dataset, val_df_processed, test_df_processed = create_datasets(
        train_df, val_df, test_df, tokenizer,
        args.max_source_length, args.max_target_length,
        args.use_title_prefix
    )

    # Load model
    logger.info(f"Loading model: {model_name}")
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    # Data collator
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
    )

    # Training arguments
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=4,  # Effective batch size = 4 * 4 = 16
        learning_rate=args.lr,
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        max_grad_norm=1.0,
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=100,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="rouge1_f",
        greater_is_better=True,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        dataloader_num_workers=4,
        report_to="none",
        predict_with_generate=True,
        generation_max_length=args.max_target_length,
        generation_num_beams=4,
    )

    # Create compute_metrics function
    compute_metrics = create_metric_function(tokenizer, args.skip_bert_score)

    # Initialize trainer
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    # Train
    logger.info("\n" + "=" * 50)
    logger.info("Starting training...")
    logger.info("=" * 50)

    trainer.train()

    # Evaluate on test set
    logger.info("\n" + "=" * 50)
    logger.info("Evaluating on test set...")
    logger.info("=" * 50)

    test_results = trainer.evaluate(test_dataset)
    logger.info(f"\nTest Results:")
    for key, value in test_results.items():
        if isinstance(value, float):
            logger.info(f"  {key}: {value:.4f}")
        else:
            logger.info(f"  {key}: {value}")

    # Generate sample predictions
    logger.info("\nSample Predictions:")
    sample_indices = np.random.choice(len(test_df_processed), min(5, len(test_df_processed)), replace=False)

    for idx in sample_indices:
        row = test_df_processed.iloc[idx]

        # Generate summary
        inputs = tokenizer(
            prepare_source_text(row, args.use_title_prefix),
            max_length=args.max_source_length,
            truncation=True,
            return_tensors="pt"
        ).to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=args.max_target_length,
                num_beams=4,
                early_stopping=True,
            )

        pred_summary = tokenizer.decode(outputs[0], skip_special_tokens=True)

        logger.info(f"\n--- Sample {idx} ---")
        logger.info(f"Title: {row['title'][:100]}...")
        logger.info(f"Reference: {row['summary']}")
        logger.info(f"Generated: {pred_summary}")

    # Save model
    final_dir = OUTPUT_DIR / "final"
    logger.info(f"\nSaving model to {final_dir}")
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Save model config and metadata
    config = {
        "model_name": model_name,
        "model_type": args.model,
        "max_source_length": args.max_source_length,
        "max_target_length": args.max_target_length,
        "use_title_prefix": args.use_title_prefix,
        "input_format": "summarize: title\\n\\ncontent" if args.use_title_prefix else "summarize: content",
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
        },
        "metrics": {
            "test_rouge1_f": test_results.get("eval_rouge1_f", 0),
            "test_rouge2_f": test_results.get("eval_rouge2_f", 0),
            "test_rougeL_f": test_results.get("eval_rougeL_f", 0),
            "test_bert_score_f1": test_results.get("eval_bert_score_f1", 0),
        },
        "generation_config": {
            "max_length": args.max_target_length,
            "num_beams": 4,
            "early_stopping": True,
        },
    }

    with open(final_dir / "model_config.json", "w") as f:
        json.dump(config, f, indent=2)

    logger.info("\nTraining complete!")
    logger.info(f"Model saved to: {final_dir}")

    return trainer, test_results


if __name__ == "__main__":
    args = parse_args()
    train(args)
