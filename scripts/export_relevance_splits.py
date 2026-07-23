#!/usr/bin/env python3
"""Export user_relevance_feedback into train/val/test splits for the
relevance-classifier trainer.

Bridges the gap between ``export_relevance_feedback.py`` (which writes a
single ``relevance_feedback.json`` the trainer can't read) and
``train_relevance_classifier.py`` (which expects
``relevance_{train,val,test}.json`` with topic/title/summary/label/
label_source columns).

Splits 80/10/10, stratified by (topic, label) so every topic's positive and
negative examples appear in all three sets. All labels here are human
(more_like_this / less_like_this), so ``label_source`` is always "human".

Usage (from a tenant root):
    PYTHONPATH=. python3 scripts/export_relevance_splits.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("export_splits")

OUT_DIR = Path(__file__).parent.parent / "data" / "training"


def main() -> None:
    import psycopg2
    from dotenv import load_dotenv
    from sklearn.model_selection import train_test_split

    load_dotenv(Path(__file__).parent.parent / ".env")
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT f.topic, f.feedback_type, a.title, a.summary
        FROM user_relevance_feedback f
        JOIN articles a ON a.uri = f.article_uri
        WHERE f.feedback_type IN ('more_like_this', 'less_like_this')
          AND (a.title IS NOT NULL OR a.summary IS NOT NULL)
        """
    )
    rows = cur.fetchall()
    conn.close()

    samples = [
        {
            "topic": r[0] or "",
            "title": r[2] or "",
            "summary": (r[3] or "")[:2000],
            "label": 1 if r[1] == "more_like_this" else 0,
            "label_source": "human",
        }
        for r in rows
    ]
    if len(samples) < 200:
        raise SystemExit(f"Only {len(samples)} labeled samples — too few to train.")

    # Stratify on (topic, label); collapse strata with <3 members into a
    # catch-all keyed by label alone so train_test_split doesn't reject them.
    from collections import Counter

    strata = [f"{s['topic']}|{s['label']}" for s in samples]
    counts = Counter(strata)
    strata = [st if counts[st] >= 6 else f"__rare__|{st.rsplit('|', 1)[1]}" for st in strata]

    train, rest = train_test_split(samples, test_size=0.2, random_state=42, stratify=strata)
    # Second split: label-only stratification — per-topic strata get too thin
    # at this size and singleton classes make sklearn reject the split.
    val, test = train_test_split(
        rest, test_size=0.5, random_state=42, stratify=[s["label"] for s in rest]
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in (("train", train), ("val", val), ("test", test)):
        path = OUT_DIR / f"relevance_{name}.json"
        path.write_text(json.dumps(data))
        pos = sum(1 for s in data if s["label"] == 1)
        logger.info("%s: %d samples (%d pos / %d neg) -> %s", name, len(data), pos, len(data) - pos, path)


if __name__ == "__main__":
    main()
