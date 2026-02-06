#!/usr/bin/env python3
"""
Train a multi-label DeBERTa classifier for brand watcher categories.

Distills LLM classifications into a fast local DeBERTa model.

Usage:
    python scripts/train_brand_watcher_classifier.py
    python scripts/train_brand_watcher_classifier.py --epochs 10 --batch-size 8

Prerequisites:
    python scripts/export_brand_watcher_training_data.py
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data/training"
DEFAULT_OUTPUT_DIR = BASE_DIR / "models/brand_watcher_classifier"
DEFAULT_MODEL = "microsoft/deberta-base"

CATEGORIES = [
    "Product & Innovation",
    "Financial Performance",
    "Leadership & Governance",
    "Brand Sentiment & Perception",
    "Competitive Landscape",
    "Legal & Regulatory",
    "Partnerships & Alliances",
    "ESG & Social Responsibility",
    "Customer & Product Issues",
    "Market Strategy & Expansion",
    "Media & Advertising",
]


def load_training_data():
    train_path = DATA_DIR / "brand_watcher_train.json"
    val_path = DATA_DIR / "brand_watcher_val.json"
    test_path = DATA_DIR / "brand_watcher_test.json"
    mapping_path = DATA_DIR / "brand_watcher_label_mappings.json"

    for p in [train_path, val_path, test_path]:
        if not p.exists():
            print(f"Missing: {p}")
            print("Run: python scripts/export_brand_watcher_training_data.py")
            raise FileNotFoundError(p)

    with open(train_path) as f:
        train_data = json.load(f)
    with open(val_path) as f:
        val_data = json.load(f)
    with open(test_path) as f:
        test_data = json.load(f)

    categories = CATEGORIES
    if mapping_path.exists():
        with open(mapping_path) as f:
            mapping = json.load(f)
            categories = mapping.get("categories", CATEGORIES)

    num_labels = len(categories)
    print(f"Loaded: train={len(train_data)}, val={len(val_data)}, test={len(test_data)}")
    print(f"Categories ({num_labels}): {categories}")

    print("\nCategory distribution (train):")
    category_counts = [0] * num_labels
    for sample in train_data:
        for i, v in enumerate(sample["labels"]):
            category_counts[i] += v

    pos_weights = []
    total = len(train_data)
    for i, cat in enumerate(categories):
        count = category_counts[i]
        pct = count / total * 100
        raw_weight = (total - count) / max(count, 1)
        weight = min(math.sqrt(raw_weight), 3.0)
        pos_weights.append(weight)
        print(f"  {cat}: {count} ({pct:.1f}%) weight={weight:.2f}")

    return train_data, val_data, test_data, categories, pos_weights


def create_datasets(train_data, val_data, test_data, tokenizer, max_length):
    def make_dataset(data):
        texts = [s["text"] for s in data]
        labels = [s["labels"] for s in data]
        return Dataset.from_dict({"text": texts, "labels": labels})

    def tokenize_fn(examples):
        tokenized = tokenizer(
            examples["text"], padding="max_length", truncation=True, max_length=max_length,
        )
        tokenized["labels"] = [list(map(float, label)) for label in examples["labels"]]
        return tokenized

    train_ds = make_dataset(train_data).map(tokenize_fn, batched=True, remove_columns=["text"])
    val_ds = make_dataset(val_data).map(tokenize_fn, batched=True, remove_columns=["text"])
    test_ds = make_dataset(test_data).map(tokenize_fn, batched=True, remove_columns=["text"])
    return train_ds, val_ds, test_ds


def compute_metrics(eval_pred):
    predictions, labels = eval_pred
    predictions = torch.sigmoid(torch.tensor(predictions)).numpy()
    predictions = (predictions > 0.5).astype(int)
    labels = labels.astype(int)

    return {
        "f1_micro": f1_score(labels, predictions, average="micro", zero_division=0),
        "f1_macro": f1_score(labels, predictions, average="macro", zero_division=0),
        "f1_weighted": f1_score(labels, predictions, average="weighted", zero_division=0),
        "precision": precision_score(labels, predictions, average="micro", zero_division=0),
        "recall": recall_score(labels, predictions, average="micro", zero_division=0),
    }


class MultiLabelTrainer(Trainer):
    def __init__(self, pos_weights=None, **kwargs):
        super().__init__(**kwargs)
        self.pos_weights = pos_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels").float()
        outputs = model(**inputs)
        logits = outputs.logits
        if self.pos_weights is not None:
            pos_weight = torch.tensor(self.pos_weights, device=logits.device)
            loss_fct = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        else:
            loss_fct = torch.nn.BCEWithLogitsLoss()
        loss = loss_fct(logits, labels)
        return (loss, outputs) if return_outputs else loss


def train(
    model_name: str = DEFAULT_MODEL,
    output_dir: str = None,
    epochs: int = 15,
    batch_size: int = 8,
    max_length: int = 512,
    learning_rate: float = 2e-5,
    use_class_weights: bool = True,
    early_stopping_patience: int = 5,
):
    output_path = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    final_path = output_path / "final"

    print(f"Model: {model_name}")
    print(f"Output: {final_path}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        print("Warning: No GPU detected")

    train_data, val_data, test_data, categories, pos_weights = load_training_data()
    num_labels = len(categories)

    print(f"\nLoading tokenizer and model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=num_labels, problem_type="multi_label_classification",
    )

    train_ds, val_ds, test_ds = create_datasets(train_data, val_data, test_data, tokenizer, max_length)

    training_args = TrainingArguments(
        output_dir=str(output_path),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        gradient_accumulation_steps=2,
        learning_rate=learning_rate,
        warmup_ratio=0.1,
        weight_decay=0.01,
        max_grad_norm=1.0,
        logging_dir=str(output_path / "logs"),
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_micro",
        greater_is_better=True,
        save_total_limit=2,
        fp16=False,
        bf16=False,
        dataloader_num_workers=4,
        report_to="none",
    )

    trainer = MultiLabelTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=early_stopping_patience)],
        pos_weights=pos_weights if use_class_weights else None,
    )

    print("\n" + "=" * 60)
    print("Starting training...")
    print("=" * 60)
    trainer.train()

    print("\n" + "=" * 60)
    print("Evaluating on test set...")
    print("=" * 60)

    test_results = trainer.evaluate(test_ds)
    print(f"\nTest Results:")
    for key, value in test_results.items():
        print(f"  {key}: {value:.4f}")

    print("\nDetailed Classification Report:")
    predictions = trainer.predict(test_ds)
    preds = torch.sigmoid(torch.tensor(predictions.predictions)).numpy()
    preds = (preds > 0.5).astype(int)
    labels = predictions.label_ids.astype(int)
    print(classification_report(labels, preds, target_names=categories, zero_division=0))

    print("\nThreshold optimization:")
    best_threshold = 0.5
    best_f1 = 0
    for threshold in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]:
        t_preds = (torch.sigmoid(torch.tensor(predictions.predictions)).numpy() > threshold).astype(int)
        f1 = f1_score(labels, t_preds, average="micro", zero_division=0)
        print(f"  threshold={threshold:.2f}: F1={f1:.4f}")
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    print(f"  Best threshold: {best_threshold} (F1={best_f1:.4f})")

    print(f"\nSaving model to {final_path}")
    final_path.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_path))
    tokenizer.save_pretrained(str(final_path))

    config = {
        "model_name": model_name,
        "categories": categories,
        "id2label": {i: cat for i, cat in enumerate(categories)},
        "label2id": {cat: i for i, cat in enumerate(categories)},
        "num_labels": num_labels,
        "recommended_threshold": best_threshold,
        "test_metrics": {k: float(v) for k, v in test_results.items()},
        "training_config": {
            "epochs": epochs, "batch_size": batch_size,
            "max_length": max_length, "learning_rate": learning_rate,
            "use_class_weights": use_class_weights,
        },
        "data_sizes": {
            "train": len(train_data), "val": len(val_data), "test": len(test_data),
        },
    }
    with open(final_path / "category_mapping.json", "w") as f:
        json.dump(config, f, indent=2)

    print("\nTraining complete!")
    print(f"Model saved to: {final_path}")
    print(f"Recommended threshold: {best_threshold}")
    return trainer, test_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train brand watcher classifier")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--no-class-weights", action="store_true")
    parser.add_argument("--patience", type=int, default=5)
    args = parser.parse_args()

    train(
        model_name=args.model,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        learning_rate=args.lr,
        use_class_weights=not args.no_class_weights,
        early_stopping_patience=args.patience,
    )
