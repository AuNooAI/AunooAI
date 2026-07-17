#!/usr/bin/env python3
"""Compare relevance classifiers on the held-out test split.

Scores one or more model directories against ``data/training/relevance_test.json``
using the exact input format the trainer and the hybrid service use
(``topic [SEP] title. summary``, max_length 256). Reports accuracy,
precision/recall/F1 (relevant class), and ROC-AUC per model.

Usage (from a tenant root):
    .venv/bin/python3 scripts/eval_relevance_models.py \
        models/relevance_classifier/final \
        models/relevance_classifier_candidate/final
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE = Path(__file__).parent.parent
TEST_PATH = BASE / "data" / "training" / "relevance_test.json"
MAX_LENGTH = 256
BATCH = 32


def prepare_text(s: dict) -> str:
    return f"{(s.get('topic') or '').strip()} [SEP] {(s.get('title') or '').strip()}. {(s.get('summary') or '').strip()}"


@torch.no_grad()
def evaluate(model_dir: str, samples: list[dict], device: str) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device).eval()
    texts = [prepare_text(s) for s in samples]
    labels = np.array([int(s["label"]) for s in samples])
    probs: list[float] = []
    for i in range(0, len(texts), BATCH):
        enc = tokenizer(
            texts[i : i + BATCH], truncation=True, max_length=MAX_LENGTH,
            padding=True, return_tensors="pt",
        ).to(device)
        logits = model(**enc).logits
        if logits.shape[-1] == 2:
            p = torch.softmax(logits, dim=-1)[:, 1]
        else:
            p = torch.sigmoid(logits.squeeze(-1))
        probs.extend(p.cpu().tolist())
    probs_arr = np.array(probs)
    preds = (probs_arr >= 0.5).astype(int)
    return {
        "n": len(labels),
        "accuracy": float(accuracy_score(labels, preds)),
        "precision_rel": float(precision_score(labels, preds, zero_division=0)),
        "recall_rel": float(recall_score(labels, preds, zero_division=0)),
        "f1_rel": float(f1_score(labels, preds, zero_division=0)),
        "roc_auc": float(roc_auc_score(labels, probs_arr)),
    }


def main() -> None:
    model_dirs = sys.argv[1:]
    if not model_dirs:
        raise SystemExit(__doc__)
    samples = json.loads(TEST_PATH.read_text())
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"test set: {len(samples)} samples | device: {device}\n")
    for md in model_dirs:
        try:
            m = evaluate(md, samples, device)
            print(f"{md}")
            print(
                f"  acc={m['accuracy']:.3f}  P(rel)={m['precision_rel']:.3f} "
                f"R(rel)={m['recall_rel']:.3f}  F1(rel)={m['f1_rel']:.3f}  AUC={m['roc_auc']:.3f}\n"
            )
        except Exception as e:  # noqa: BLE001
            print(f"{md}: FAILED — {e}\n")


if __name__ == "__main__":
    main()
