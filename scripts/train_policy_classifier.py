#!/usr/bin/env python3
"""
Train a multi-label classifier for Trump Policy Tracker categories.

Usage:
    python scripts/train_policy_classifier.py

Requirements:
    pip install transformers datasets accelerate scikit-learn pandas torch

The script fine-tunes ModernBERT (or DeBERTa) on the curated policy tracker dataset
for 10-class multi-label classification.
"""

import os
import pandas as pd
import numpy as np
import torch
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, precision_score, recall_score, classification_report

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
)
from datasets import Dataset

# Configuration
BASE_DIR = Path(__file__).parent.parent
DATA_PATH = BASE_DIR / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"
OUTPUT_DIR = BASE_DIR / "models/policy_classifier"

# Model choice - DeBERTa-base (v1) uses standard LayerNorm and works reliably
MODEL_NAME = "microsoft/deberta-base"

# Category mapping from CSV columns to simplified names
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

# Training hyperparameters
BATCH_SIZE = 8  # Reduced for DeBERTa memory requirements
MAX_LENGTH = 512  # Longer context for full text
LEARNING_RATE = 2e-5  # Standard for transformer fine-tuning
NUM_EPOCHS = 15  # More epochs for DeBERTa to converge
WARMUP_RATIO = 0.1
USE_CLASS_WEIGHTS = True  # Enable to help with class imbalance


def load_and_prepare_data():
    """Load CSV and prepare for training."""
    print(f"Loading data from {DATA_PATH}")

    # Read CSV, skip the license header row
    df = pd.read_csv(DATA_PATH, skiprows=1)

    print(f"Loaded {len(df)} records")

    # Get category columns (the ones with Yes/No values)
    category_cols = list(CATEGORY_COLUMNS.keys())

    # Verify columns exist
    missing = [c for c in category_cols if c not in df.columns]
    if missing:
        print(f"Warning: Missing columns: {missing}")
        print(f"Available columns: {df.columns.tolist()}")

    # Create binary labels (Yes=1, No=0)
    labels = []
    for _, row in df.iterrows():
        label = [1 if row.get(col, "No") == "Yes" else 0 for col in category_cols]
        labels.append(label)

    df["labels"] = labels

    # Use Title as the text input
    df["text"] = df["Title"].fillna("")

    # Remove rows with empty text
    df = df[df["text"].str.len() > 0]

    print(f"After filtering: {len(df)} records")

    # Show label distribution and calculate class weights
    print("\nCategory distribution:")
    category_counts = []
    for i, (orig_name, short_name) in enumerate(CATEGORY_COLUMNS.items()):
        count = sum(1 for label in df["labels"] if label[i] == 1)
        category_counts.append(count)
        print(f"  {short_name}: {count} ({count/len(df)*100:.1f}%)")

    # Calculate pos_weight for BCEWithLogitsLoss (inverse frequency)
    # Higher weight = model penalized more for missing this class
    # Using sqrt scaling and lower max for DeBERTa compatibility
    import math
    total = len(df)
    pos_weights = []
    for count in category_counts:
        # Gentler weight calculation: sqrt of inverse frequency, clamped
        raw_weight = (total - count) / max(count, 1)
        weight = min(math.sqrt(raw_weight), 3.0)  # Max 3.0 for stability
        pos_weights.append(weight)

    print("\nClass weights (pos_weight for BCE):")
    for i, (_, short_name) in enumerate(CATEGORY_COLUMNS.items()):
        print(f"  {short_name}: {pos_weights[i]:.2f}")

    df.attrs["pos_weights"] = pos_weights

    return df


def create_datasets(df, tokenizer):
    """Split data and create HuggingFace datasets."""
    # Split: 80% train, 10% val, 10% test
    train_df, temp_df = train_test_split(df, test_size=0.2, random_state=42)
    val_df, test_df = train_test_split(temp_df, test_size=0.5, random_state=42)

    print(f"\nSplit sizes: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=MAX_LENGTH,
        )
        # Convert labels to float tensor for BCEWithLogitsLoss
        tokenized["labels"] = [list(map(float, label)) for label in examples["labels"]]
        return tokenized

    train_dataset = Dataset.from_pandas(train_df[["text", "labels"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )
    val_dataset = Dataset.from_pandas(val_df[["text", "labels"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )
    test_dataset = Dataset.from_pandas(test_df[["text", "labels"]]).map(
        tokenize_function, batched=True, remove_columns=["text"]
    )

    return train_dataset, val_dataset, test_dataset, test_df


def compute_metrics(eval_pred):
    """Compute multi-label classification metrics."""
    predictions, labels = eval_pred

    # Apply sigmoid and threshold at 0.5
    predictions = torch.sigmoid(torch.tensor(predictions)).numpy()
    predictions = (predictions > 0.5).astype(int)
    labels = labels.astype(int)

    # Compute metrics
    f1_micro = f1_score(labels, predictions, average="micro", zero_division=0)
    f1_macro = f1_score(labels, predictions, average="macro", zero_division=0)
    f1_weighted = f1_score(labels, predictions, average="weighted", zero_division=0)
    precision = precision_score(labels, predictions, average="micro", zero_division=0)
    recall = recall_score(labels, predictions, average="micro", zero_division=0)

    return {
        "f1_micro": f1_micro,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
        "precision": precision,
        "recall": recall,
    }


class MultiLabelTrainer(Trainer):
    """Custom trainer for multi-label classification with BCEWithLogitsLoss."""

    def __init__(self, pos_weights=None, **kwargs):
        super().__init__(**kwargs)
        self.pos_weights = pos_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        # Ensure labels are float for BCE loss
        labels = labels.float()

        # Use class weights if provided
        if self.pos_weights is not None:
            pos_weight = torch.tensor(self.pos_weights, device=logits.device)
            loss_fct = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        else:
            loss_fct = torch.nn.BCEWithLogitsLoss()

        loss = loss_fct(logits, labels)

        return (loss, outputs) if return_outputs else loss


def train():
    """Main training function."""
    print(f"Using model: {MODEL_NAME}")
    print(f"Output directory: {OUTPUT_DIR}")

    # Check GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("Warning: No GPU detected, training will be slow")

    # Load data
    df = load_and_prepare_data()

    # Load tokenizer and model
    print(f"\nLoading tokenizer and model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    num_labels = len(CATEGORY_COLUMNS)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=num_labels,
        problem_type="multi_label_classification",
    )

    # Create datasets
    train_dataset, val_dataset, test_dataset, test_df = create_datasets(df, tokenizer)

    # Get class weights
    pos_weights = df.attrs.get("pos_weights") if USE_CLASS_WEIGHTS else None
    if pos_weights:
        print(f"\nUsing class weights to boost underrepresented categories")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE * 2,
        gradient_accumulation_steps=2,  # Effective batch size = 8 * 2 = 16
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        weight_decay=0.01,
        max_grad_norm=1.0,  # Gradient clipping for stability
        logging_dir=str(OUTPUT_DIR / "logs"),
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_micro",
        greater_is_better=True,
        save_total_limit=2,
        fp16=False,  # Disable mixed precision for DeBERTa stability
        bf16=False,
        dataloader_num_workers=4,
        report_to="none",  # Disable wandb/tensorboard
    )

    # Initialize trainer
    trainer = MultiLabelTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5)],
        pos_weights=pos_weights,
    )

    # Train
    print("\n" + "=" * 50)
    print("Starting training...")
    print("=" * 50)

    trainer.train()

    # Evaluate on test set
    print("\n" + "=" * 50)
    print("Evaluating on test set...")
    print("=" * 50)

    test_results = trainer.evaluate(test_dataset)
    print(f"\nTest Results:")
    for key, value in test_results.items():
        print(f"  {key}: {value:.4f}")

    # Detailed classification report
    print("\nDetailed Classification Report:")
    predictions = trainer.predict(test_dataset)
    preds = torch.sigmoid(torch.tensor(predictions.predictions)).numpy()
    preds = (preds > 0.5).astype(int)
    labels = predictions.label_ids.astype(int)

    category_names = list(CATEGORY_COLUMNS.values())
    print(classification_report(labels, preds, target_names=category_names, zero_division=0))

    # Save model and tokenizer
    print(f"\nSaving model to {OUTPUT_DIR}")
    trainer.save_model(str(OUTPUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "final"))


    # Save category mapping for inference
    import json
    with open(OUTPUT_DIR / "final" / "category_mapping.json", "w") as f:
        json.dump({
            "categories": category_names,
            "id2label": {i: name for i, name in enumerate(category_names)},
            "label2id": {name: i for i, name in enumerate(category_names)},
            "recommended_threshold": 0.55,  # Balanced threshold for precision/recall
        }, f, indent=2)

    print("\nTraining complete!")
    print(f"Model saved to: {OUTPUT_DIR / 'final'}")

    return trainer, test_results


if __name__ == "__main__":
    train()
