#!/usr/bin/env python3
"""
Train a binary relevance classifier for article-topic matching.

This classifier determines whether an article is relevant to a given topic,
replacing/augmenting the LLM-based relevance scoring in the ingest pipeline.

Architecture:
    Input: [CLS] topic [SEP] title. summary [SEP]
    Output: relevance_score (0-1)

The model is trained on human-curated data (first ~2000 AI topic articles)
supplemented by LLM-labeled data (silver labels).

Usage:
    python scripts/train_relevance_classifier.py

    # With custom settings
    python scripts/train_relevance_classifier.py --model deberta-base --epochs 10

Requirements:
    pip install transformers datasets accelerate scikit-learn pandas torch

Output:
    models/relevance_classifier/final/
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
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    classification_report,
    confusion_matrix,
)

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
)
from datasets import Dataset

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "training"
OUTPUT_DIR = BASE_DIR / "models" / "relevance_classifier"

# Model choices
MODELS = {
    'deberta-base': 'microsoft/deberta-base',
    'deberta-v3-base': 'microsoft/deberta-v3-base',
    'roberta-base': 'roberta-base',
    'roberta-large': 'roberta-large',
}

# Default hyperparameters
DEFAULT_MODEL = 'deberta-base'
BATCH_SIZE = 16
MAX_LENGTH = 256  # Shorter since we use title + summary
LEARNING_RATE = 2e-5
NUM_EPOCHS = 10
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
    parser = argparse.ArgumentParser(description='Train relevance classifier')
    parser.add_argument('--model', type=str, default=DEFAULT_MODEL,
                        choices=list(MODELS.keys()),
                        help=f'Model to train (default: {DEFAULT_MODEL})')
    parser.add_argument('--epochs', type=int, default=NUM_EPOCHS,
                        help=f'Number of training epochs (default: {NUM_EPOCHS})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Batch size (default: {BATCH_SIZE})')
    parser.add_argument('--lr', type=float, default=LEARNING_RATE,
                        help=f'Learning rate (default: {LEARNING_RATE})')
    parser.add_argument('--max-length', type=int, default=MAX_LENGTH,
                        help=f'Max sequence length (default: {MAX_LENGTH})')
    parser.add_argument('--use-class-weights', action='store_true',
                        help='Use class weights for imbalanced data')
    parser.add_argument('--prioritize-human-labels', action='store_true', default=True,
                        help='Prioritize human-labeled data in training')
    return parser.parse_args()


def load_training_data(data_dir: Path, prioritize_human: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load training data from exported JSON files.

    Args:
        data_dir: Directory containing relevance_train.json, etc.
        prioritize_human: If True, weight human-labeled samples higher

    Returns:
        train_df, val_df, test_df
    """
    logger.info(f"Loading data from {data_dir}")

    train_df = pd.read_json(data_dir / "relevance_train.json")
    val_df = pd.read_json(data_dir / "relevance_val.json")
    test_df = pd.read_json(data_dir / "relevance_test.json")

    logger.info(f"Loaded: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # Log label distribution
    for name, df in [('train', train_df), ('val', val_df), ('test', test_df)]:
        pos = (df['label'] == 1).sum()
        neg = (df['label'] == 0).sum()
        human = (df['label_source'] == 'human').sum() if 'label_source' in df.columns else 0
        logger.info(f"  {name}: {pos} pos, {neg} neg, {human} human-labeled")

    return train_df, val_df, test_df


def prepare_text(row) -> str:
    """
    Prepare input text in format: topic [SEP] title. summary

    Args:
        row: DataFrame row with 'topic', 'title', 'summary' columns

    Returns:
        Formatted text string
    """
    topic = str(row['topic']).strip() if row['topic'] else ""
    title = str(row['title']).strip() if row['title'] else ""
    summary = str(row['summary']).strip() if row['summary'] else ""

    # Format: "topic [SEP] title. summary"
    # The tokenizer will handle the actual [SEP] token
    text = f"{topic} [SEP] {title}. {summary}"
    return text


def create_datasets(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    tokenizer,
    max_length: int = MAX_LENGTH
) -> Tuple[Dataset, Dataset, Dataset]:
    """
    Create HuggingFace datasets from DataFrames.

    Args:
        train_df, val_df, test_df: Pandas DataFrames
        tokenizer: HuggingFace tokenizer
        max_length: Maximum sequence length

    Returns:
        train_dataset, val_dataset, test_dataset
    """
    # Prepare text for each dataset
    train_df = train_df.copy()
    val_df = val_df.copy()
    test_df = test_df.copy()

    train_df['text'] = train_df.apply(prepare_text, axis=1)
    val_df['text'] = val_df.apply(prepare_text, axis=1)
    test_df['text'] = test_df.apply(prepare_text, axis=1)

    def tokenize_function(examples):
        """Tokenize examples."""
        tokenized = tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )
        # Labels are already 0/1 integers
        tokenized["labels"] = examples["label"]
        return tokenized

    # Convert to HuggingFace datasets
    train_dataset = Dataset.from_pandas(train_df[["text", "label"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )
    val_dataset = Dataset.from_pandas(val_df[["text", "label"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )
    test_dataset = Dataset.from_pandas(test_df[["text", "label"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )

    return train_dataset, val_dataset, test_dataset


def compute_metrics(eval_pred) -> Dict[str, float]:
    """
    Compute evaluation metrics.

    Args:
        eval_pred: EvalPrediction with predictions and label_ids

    Returns:
        Dictionary of metric names and values
    """
    predictions, labels = eval_pred

    # Get predicted class (argmax for binary classification)
    if len(predictions.shape) > 1 and predictions.shape[1] > 1:
        # Multi-class output, take argmax
        preds = predictions.argmax(axis=1)
        # Get probabilities for ROC-AUC
        probs = torch.softmax(torch.tensor(predictions), dim=1)[:, 1].numpy()
    else:
        # Single output, threshold at 0.5
        preds = (predictions > 0.5).astype(int).flatten()
        probs = predictions.flatten()

    # Compute metrics
    accuracy = accuracy_score(labels, preds)
    precision = precision_score(labels, preds, zero_division=0)
    recall = recall_score(labels, preds, zero_division=0)
    f1 = f1_score(labels, preds, zero_division=0)

    try:
        auc = roc_auc_score(labels, probs)
    except ValueError:
        auc = 0.0  # Can't compute AUC if only one class present

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": auc,
    }


class WeightedTrainer(Trainer):
    """Trainer with class weighting support."""

    def __init__(self, class_weights=None, **kwargs):
        super().__init__(**kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        if self.class_weights is not None:
            weight = torch.tensor(self.class_weights, device=logits.device)
            loss_fct = torch.nn.CrossEntropyLoss(weight=weight)
        else:
            loss_fct = torch.nn.CrossEntropyLoss()

        loss = loss_fct(logits, labels)
        return (loss, outputs) if return_outputs else loss


def calculate_class_weights(train_df: pd.DataFrame) -> List[float]:
    """
    Calculate class weights for imbalanced data.

    Uses inverse frequency with sqrt scaling.

    Args:
        train_df: Training DataFrame with 'label' column

    Returns:
        List of weights [weight_class_0, weight_class_1]
    """
    label_counts = train_df['label'].value_counts()
    total = len(train_df)

    weights = []
    for label in [0, 1]:
        count = label_counts.get(label, 1)
        # Inverse frequency with sqrt scaling
        weight = np.sqrt(total / (2 * count))
        weights.append(weight)

    # Normalize so they average to 1
    avg = sum(weights) / len(weights)
    weights = [w / avg for w in weights]

    logger.info(f"Class weights: {weights}")
    return weights


def train(args):
    """Main training function."""
    logger.info("=" * 60)
    logger.info("Relevance Classifier Training")
    logger.info("=" * 60)

    model_name = MODELS[args.model]
    logger.info(f"Model: {args.model} ({model_name})")
    logger.info(f"Epochs: {args.epochs}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Learning rate: {args.lr}")
    logger.info(f"Max length: {args.max_length}")

    # Check GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.info("Warning: No GPU detected, training will be slow")

    # Load data
    train_df, val_df, test_df = load_training_data(DATA_DIR, args.prioritize_human_labels)

    # Load tokenizer
    logger.info(f"\nLoading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Create datasets
    train_dataset, val_dataset, test_dataset = create_datasets(
        train_df, val_df, test_df, tokenizer, args.max_length
    )

    # Load model
    logger.info(f"Loading model: {model_name}")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=2,  # Binary classification
        problem_type="single_label_classification",
    )

    # Calculate class weights if requested
    class_weights = None
    if args.use_class_weights:
        class_weights = calculate_class_weights(train_df)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        gradient_accumulation_steps=2,
        learning_rate=args.lr,
        warmup_ratio=WARMUP_RATIO,
        weight_decay=WEIGHT_DECAY,
        max_grad_norm=1.0,
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        save_total_limit=2,
        fp16=False,  # DeBERTa has issues with fp16, use fp32
        dataloader_num_workers=4,
        report_to="none",
    )

    # Initialize trainer
    if class_weights:
        trainer = WeightedTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
            class_weights=class_weights,
        )
    else:
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
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
        logger.info(f"  {key}: {value:.4f}")

    # Detailed classification report
    logger.info("\nDetailed Classification Report:")
    predictions = trainer.predict(test_dataset)
    preds = predictions.predictions.argmax(axis=1)
    labels = predictions.label_ids

    logger.info(classification_report(
        labels, preds,
        target_names=['Irrelevant', 'Relevant'],
        digits=4
    ))

    # Confusion matrix
    cm = confusion_matrix(labels, preds)
    logger.info(f"\nConfusion Matrix:")
    logger.info(f"                 Predicted")
    logger.info(f"              Irrelevant  Relevant")
    logger.info(f"Actual Irrelevant  {cm[0][0]:6d}    {cm[0][1]:6d}")
    logger.info(f"       Relevant    {cm[1][0]:6d}    {cm[1][1]:6d}")

    # Save model
    final_dir = OUTPUT_DIR / "final"
    logger.info(f"\nSaving model to {final_dir}")
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    # Save model config and metadata
    config = {
        "model_name": model_name,
        "model_type": args.model,
        "num_labels": 2,
        "labels": ["irrelevant", "relevant"],
        "id2label": {0: "irrelevant", 1: "relevant"},
        "label2id": {"irrelevant": 0, "relevant": 1},
        "max_length": args.max_length,
        "input_format": "topic [SEP] title. summary",
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
            "use_class_weights": args.use_class_weights,
        },
        "metrics": {
            "test_accuracy": test_results.get("eval_accuracy", 0),
            "test_f1": test_results.get("eval_f1", 0),
            "test_precision": test_results.get("eval_precision", 0),
            "test_recall": test_results.get("eval_recall", 0),
            "test_auc": test_results.get("eval_auc", 0),
        },
        "recommended_threshold": 0.5,
    }

    with open(final_dir / "model_config.json", "w") as f:
        json.dump(config, f, indent=2)

    logger.info("\nTraining complete!")
    logger.info(f"Model saved to: {final_dir}")

    return trainer, test_results


if __name__ == "__main__":
    args = parse_args()
    train(args)
