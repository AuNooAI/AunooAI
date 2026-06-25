#!/usr/bin/env python3
"""
Train a multi-task enrichment model for article analysis.

This script trains a model to predict multiple enrichment fields:
- Sentiment (3-class: Positive/Negative/Neutral)
- Time to Impact (4-class: Immediate/6 months/1 year/2+ years)
- Driver Type (6-class: accelerating/delaying/blocking/initiating/terminating/catalyzing)
- Future Signal (multi-class)
- Category (topic-specific, multi-label)

Architecture Options:
1. Multi-head classifier: Shared encoder with separate classification heads
2. Generative: Fine-tuned LLM with JSON output (Phi-3, Mistral)

This script implements Option 1 (multi-head) for efficiency.

Usage:
    python scripts/train_enrichment_model.py

    # With custom settings
    python scripts/train_enrichment_model.py --model deberta-v3-base --epochs 10

Requirements:
    pip install transformers datasets accelerate scikit-learn pandas torch

Output:
    models/enrichment_model/final/
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
)

from transformers import (
    AutoTokenizer,
    AutoModel,
    AutoConfig,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
    PreTrainedModel,
)
from datasets import Dataset

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "training"
OUTPUT_DIR = BASE_DIR / "models" / "enrichment_model"

# Model choices
MODELS = {
    'deberta-base': 'microsoft/deberta-base',
    'deberta-v3-base': 'microsoft/deberta-v3-base',
    'roberta-base': 'roberta-base',
    'bert-base': 'bert-base-uncased',
}

# Default hyperparameters
DEFAULT_MODEL = 'deberta-base'
BATCH_SIZE = 16
MAX_LENGTH = 256
LEARNING_RATE = 2e-5
NUM_EPOCHS = 10
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01

# Task definitions (will be populated from data)
TASKS = {
    'sentiment': {'type': 'single_label', 'num_labels': 0, 'labels': []},
    'time_to_impact': {'type': 'single_label', 'num_labels': 0, 'labels': []},
    'driver_type': {'type': 'single_label', 'num_labels': 0, 'labels': []},
    'future_signal': {'type': 'single_label', 'num_labels': 0, 'labels': []},
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train multi-task enrichment model')
    parser.add_argument('--model', type=str, default=DEFAULT_MODEL,
                        choices=list(MODELS.keys()),
                        help=f'Base model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--epochs', type=int, default=NUM_EPOCHS,
                        help=f'Number of training epochs (default: {NUM_EPOCHS})')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Batch size (default: {BATCH_SIZE})')
    parser.add_argument('--lr', type=float, default=LEARNING_RATE,
                        help=f'Learning rate (default: {LEARNING_RATE})')
    parser.add_argument('--max-length', type=int, default=MAX_LENGTH,
                        help=f'Max sequence length (default: {MAX_LENGTH})')
    parser.add_argument('--use-class-weights', action='store_true',
                        help='Use class weights for imbalanced tasks')
    parser.add_argument('--tasks', type=str, nargs='+',
                        default=['sentiment', 'time_to_impact', 'driver_type', 'future_signal'],
                        help='Tasks to train on')
    parser.add_argument('--device', type=str, default='auto',
                        choices=['auto', 'cpu', 'cuda'],
                        help='Device to train on (default: auto)')
    return parser.parse_args()


class MultiTaskModel(PreTrainedModel):
    """
    Multi-task classification model with shared encoder.

    Uses a shared transformer encoder with separate classification heads
    for each enrichment task.
    """

    def __init__(self, config, task_configs: Dict[str, Dict]):
        """
        Initialize multi-task model.

        Args:
            config: Base model config
            task_configs: Dict mapping task names to their configs
        """
        super().__init__(config)

        self.encoder = AutoModel.from_config(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob if hasattr(config, 'hidden_dropout_prob') else 0.1)

        # Create classification heads for each task
        self.classifiers = nn.ModuleDict()
        self.task_configs = task_configs

        for task_name, task_config in task_configs.items():
            num_labels = task_config['num_labels']
            self.classifiers[task_name] = nn.Linear(config.hidden_size, num_labels)

        # Initialize weights
        self.post_init()

    def forward(
        self,
        input_ids=None,
        attention_mask=None,
        token_type_ids=None,
        labels=None,
        task_name=None,
        **kwargs
    ):
        """Forward pass with optional task-specific loss computation."""
        outputs = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            **kwargs
        )

        # Get [CLS] token representation
        pooled_output = outputs.last_hidden_state[:, 0, :]
        pooled_output = self.dropout(pooled_output)

        # Compute logits for all tasks or specific task
        if task_name and task_name in self.classifiers:
            logits = {task_name: self.classifiers[task_name](pooled_output)}
        else:
            logits = {
                name: classifier(pooled_output)
                for name, classifier in self.classifiers.items()
            }

        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss()
            task_losses = []

            for task, task_logits in logits.items():
                if task in labels and labels[task] is not None:
                    task_labels = labels[task]
                    # Filter out -100 (ignore index)
                    mask = task_labels != -100
                    if mask.any():
                        task_loss = loss_fct(task_logits[mask], task_labels[mask])
                        task_losses.append(task_loss)

            # Average loss across tasks
            if task_losses:
                loss = torch.stack(task_losses).mean()

        return {
            'loss': loss,
            'logits': logits,
            'hidden_states': outputs.hidden_states if hasattr(outputs, 'hidden_states') else None,
        }


def load_training_data(data_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """
    Load enrichment training data and label mappings.

    Args:
        data_dir: Directory containing enrichment_train.json, etc.

    Returns:
        train_df, val_df, test_df, label_mappings
    """
    logger.info(f"Loading data from {data_dir}")

    train_df = pd.read_json(data_dir / "enrichment_train.json")
    val_df = pd.read_json(data_dir / "enrichment_val.json")
    test_df = pd.read_json(data_dir / "enrichment_test.json")

    # Load label mappings
    with open(data_dir / "label_mappings.json") as f:
        label_mappings = json.load(f)

    logger.info(f"Loaded: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    return train_df, val_df, test_df, label_mappings


def prepare_task_configs(label_mappings: Dict, tasks: List[str]) -> Dict[str, Dict]:
    """
    Prepare task configurations from label mappings.

    Args:
        label_mappings: Dict with label info for each field
        tasks: List of task names to include

    Returns:
        Dict mapping task names to their configs
    """
    task_configs = {}

    for task in tasks:
        if task in label_mappings:
            mapping = label_mappings[task]
            task_configs[task] = {
                'type': 'single_label',
                'num_labels': mapping['num_labels'],
                'labels': mapping['values'],
                'label2id': mapping['label2id'],
                'id2label': {int(k): v for k, v in mapping['id2label'].items()},
            }
            logger.info(f"Task '{task}': {task_configs[task]['num_labels']} labels")

    return task_configs


def prepare_text(row) -> str:
    """
    Prepare input text for classification.

    Args:
        row: DataFrame row with 'title', 'summary' columns

    Returns:
        Formatted text
    """
    title = str(row['title']).strip() if row['title'] else ""
    summary = str(row['summary']).strip() if row['summary'] else ""

    return f"{title}. {summary}"


def create_datasets(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    tokenizer,
    task_configs: Dict[str, Dict],
    max_length: int = MAX_LENGTH
) -> Tuple[Dataset, Dataset, Dataset]:
    """
    Create HuggingFace datasets from DataFrames.

    Args:
        train_df, val_df, test_df: Pandas DataFrames
        tokenizer: HuggingFace tokenizer
        task_configs: Task configuration dict
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

    # Convert labels to IDs
    for task, config in task_configs.items():
        label2id = config['label2id']

        for df in [train_df, val_df, test_df]:
            if task in df.columns:
                # Map labels to IDs, use -100 for unknown/missing
                df[f'{task}_id'] = df[task].apply(
                    lambda x: label2id.get(str(x), -100) if pd.notna(x) else -100
                )

    def tokenize_function(examples):
        """Tokenize and prepare labels."""
        tokenized = tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )

        # Add task labels
        for task in task_configs.keys():
            label_col = f'{task}_id'
            if label_col in examples:
                tokenized[f'label_{task}'] = examples[label_col]

        return tokenized

    # Determine columns to keep
    label_cols = ['text'] + [f'{task}_id' for task in task_configs.keys()]
    label_cols = [c for c in label_cols if c in train_df.columns]

    # Convert to HuggingFace datasets
    train_dataset = Dataset.from_pandas(train_df[label_cols], preserve_index=False).map(
        tokenize_function, batched=True, remove_columns=label_cols
    )
    val_dataset = Dataset.from_pandas(val_df[label_cols], preserve_index=False).map(
        tokenize_function, batched=True, remove_columns=label_cols
    )
    test_dataset = Dataset.from_pandas(test_df[label_cols], preserve_index=False).map(
        tokenize_function, batched=True, remove_columns=label_cols
    )

    return train_dataset, val_dataset, test_dataset


class MultiTaskTrainer(Trainer):
    """Custom trainer for multi-task learning."""

    def __init__(self, task_configs: Dict[str, Dict], **kwargs):
        super().__init__(**kwargs)
        self.task_configs = task_configs
        self.task_names = list(task_configs.keys())

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        # Debug once
        if not hasattr(self, '_debug_printed'):
            print(f"DEBUG - inputs keys: {list(inputs.keys())}")
            self._debug_printed = True

        # Extract labels for each task
        labels = {}
        for task in self.task_configs.keys():
            label_key = f'label_{task}'
            if label_key in inputs:
                labels[task] = inputs.pop(label_key)

        # Forward pass
        outputs = model(labels=labels, **inputs)

        loss = outputs['loss']
        if loss is None:
            print(f"WARNING - loss is None! labels keys: {list(labels.keys())}")
        return (loss, outputs) if return_outputs else loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
        """Override to handle multi-task outputs properly."""
        # Extract labels
        labels_dict = {}
        for task in self.task_names:
            label_key = f'label_{task}'
            if label_key in inputs:
                labels_dict[task] = inputs.pop(label_key)

        # Move inputs to device
        inputs = self._prepare_inputs(inputs)

        with torch.no_grad():
            outputs = model(labels=labels_dict, **inputs)
            loss = outputs['loss']
            logits_dict = outputs['logits']

        if prediction_loss_only:
            return (loss, None, None)

        # Convert logits dict to tuple for Trainer compatibility
        logits_tuple = tuple(logits_dict[task].detach() for task in self.task_names)

        # Convert labels dict to tuple
        labels_tuple = tuple(
            labels_dict[task].detach() if labels_dict.get(task) is not None else None
            for task in self.task_names
        )

        return (loss, logits_tuple, labels_tuple)


def compute_metrics_factory(task_configs: Dict[str, Dict]):
    """Create compute_metrics function for multi-task evaluation."""

    def compute_metrics(eval_pred):
        """Compute metrics for all tasks."""
        predictions, labels = eval_pred

        # Handle the case where predictions is a dict
        if isinstance(predictions, dict):
            logits = predictions
        else:
            # Assume predictions is a tuple of arrays for each task
            logits = {}
            for i, task in enumerate(task_configs.keys()):
                if i < len(predictions):
                    logits[task] = predictions[i]

        metrics = {}

        for task, config in task_configs.items():
            if task not in logits:
                continue

            task_logits = logits[task]
            task_preds = np.argmax(task_logits, axis=1)

            # Get labels for this task
            label_key = f'label_{task}'
            if isinstance(labels, dict) and label_key in labels:
                task_labels = labels[label_key]
            else:
                # Try to extract from tuple
                task_idx = list(task_configs.keys()).index(task)
                task_labels = labels[task_idx] if task_idx < len(labels) else None

            if task_labels is None:
                continue

            # Filter out -100 (ignore index)
            mask = task_labels != -100
            if not mask.any():
                continue

            valid_preds = task_preds[mask]
            valid_labels = task_labels[mask]

            # Compute metrics
            metrics[f'{task}_accuracy'] = accuracy_score(valid_labels, valid_preds)
            metrics[f'{task}_f1_macro'] = f1_score(valid_labels, valid_preds, average='macro', zero_division=0)
            metrics[f'{task}_f1_weighted'] = f1_score(valid_labels, valid_preds, average='weighted', zero_division=0)

        # Overall metric (average F1 across tasks)
        f1_scores = [v for k, v in metrics.items() if k.endswith('_f1_weighted')]
        if f1_scores:
            metrics['avg_f1_weighted'] = np.mean(f1_scores)

        return metrics

    return compute_metrics


class MultiTaskDataCollator:
    """Data collator that handles multi-task labels."""

    def __init__(self, tokenizer, task_configs):
        self.tokenizer = tokenizer
        self.task_configs = task_configs
        from transformers import default_data_collator
        self.default_collator = default_data_collator

    def __call__(self, features):
        # Use default collator which handles everything properly
        return self.default_collator(features)


def train(args):
    """Main training function."""
    logger.info("=" * 60)
    logger.info("Multi-Task Enrichment Model Training")
    logger.info("=" * 60)

    model_name = MODELS[args.model]
    logger.info(f"Model: {args.model} ({model_name})")
    logger.info(f"Epochs: {args.epochs}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Learning rate: {args.lr}")
    logger.info(f"Max length: {args.max_length}")
    logger.info(f"Tasks: {args.tasks}")

    # Check GPU and set device
    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device

    if device == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.info(f"Using CPU for training (device={args.device})")

    # Load data
    train_df, val_df, test_df, label_mappings = load_training_data(DATA_DIR)

    # Prepare task configs
    task_configs = prepare_task_configs(label_mappings, args.tasks)

    if not task_configs:
        raise ValueError("No valid tasks found in label mappings")

    # Load tokenizer
    logger.info(f"\nLoading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Create datasets
    train_dataset, val_dataset, test_dataset = create_datasets(
        train_df, val_df, test_df, tokenizer, task_configs, args.max_length
    )

    # Load base config and create model
    logger.info(f"Creating multi-task model with {len(task_configs)} heads")
    config = AutoConfig.from_pretrained(model_name)
    model = MultiTaskModel(config, task_configs)

    # Load pretrained weights into encoder
    pretrained = AutoModel.from_pretrained(model_name)
    model.encoder.load_state_dict(pretrained.state_dict())

    model.to(device)

    # Data collator
    data_collator = MultiTaskDataCollator(tokenizer, task_configs)

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
        metric_for_best_model="avg_f1_weighted",
        greater_is_better=True,
        save_total_limit=2,
        fp16=False,  # DeBERTa has issues with fp16, use fp32
        dataloader_num_workers=0 if device == "cpu" else 4,  # Reduce workers on CPU
        report_to="none",
        remove_unused_columns=False,  # Keep our custom label_* columns
        use_cpu=(device == "cpu"),  # Force CPU if specified
    )

    # Create compute_metrics function
    compute_metrics = compute_metrics_factory(task_configs)

    # Initialize trainer
    trainer = MultiTaskTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
        task_configs=task_configs,
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

    # Save model
    final_dir = OUTPUT_DIR / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"\nSaving model to {final_dir}")

    # Save model state dict (custom model, can't use save_pretrained directly)
    torch.save(model.state_dict(), final_dir / "pytorch_model.bin")
    tokenizer.save_pretrained(str(final_dir))
    config.save_pretrained(str(final_dir))

    # Save model config and metadata
    model_config = {
        "base_model": model_name,
        "model_type": args.model,
        "max_length": args.max_length,
        "tasks": {
            task: {
                "num_labels": cfg['num_labels'],
                "labels": cfg['labels'],
                "label2id": cfg['label2id'],
                "id2label": cfg['id2label'],
            }
            for task, cfg in task_configs.items()
        },
        "training": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
        },
        "metrics": {k: v for k, v in test_results.items() if isinstance(v, (int, float))},
    }

    with open(final_dir / "model_config.json", "w") as f:
        json.dump(model_config, f, indent=2)

    logger.info("\nTraining complete!")
    logger.info(f"Model saved to: {final_dir}")

    return trainer, test_results


if __name__ == "__main__":
    args = parse_args()
    train(args)
