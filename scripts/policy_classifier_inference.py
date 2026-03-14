#!/usr/bin/env python3
"""
Inference script for the trained policy classifier.

Usage:
    # Single article
    python scripts/policy_classifier_inference.py "Trump threatens tariffs on Denmark over Greenland"

    # From database (batch)
    python scripts/policy_classifier_inference.py --from-db --limit 100

    # Interactive mode
    python scripts/policy_classifier_inference.py --interactive
"""

import argparse
import json
import torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = BASE_DIR / "models/policy_classifier/final"

# Default confidence threshold (can be overridden by model config)
CONFIDENCE_THRESHOLD = 0.55


class PolicyClassifier:
    """Inference wrapper for the trained policy classifier."""

    def __init__(self, model_path: str = None):
        self.model_path = Path(model_path) if model_path else MODEL_PATH

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                "Run train_policy_classifier.py first."
            )

        print(f"Loading model from {self.model_path}")

        # Default to CPU - RoBERTa inference is fast enough on CPU
        # and avoids conflicts with vLLM or other GPU processes
        import os
        if os.environ.get("FORCE_CUDA", "").lower() == "true":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = "cpu"
        print(f"Using device: {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        # Load model - convert to float32 on CPU to avoid NaN issues
        if self.device == "cpu":
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_path, torch_dtype=torch.float32
            )
        else:
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self.model.to(self.device)
        self.model.eval()

        # Load category mapping
        with open(self.model_path / "category_mapping.json") as f:
            mapping = json.load(f)
            self.categories = mapping["categories"]
            self.id2label = {int(k): v for k, v in mapping["id2label"].items()}
            self.recommended_threshold = mapping.get("recommended_threshold", CONFIDENCE_THRESHOLD)

        print(f"Loaded {len(self.categories)} categories (recommended threshold: {self.recommended_threshold})")

    def classify(self, text: str, threshold: float = CONFIDENCE_THRESHOLD) -> dict:
        """
        Classify a single text.

        Returns:
            dict with 'categories' (list of predicted categories) and
            'scores' (dict of category -> confidence score)
        """
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.sigmoid(outputs.logits).cpu().numpy()[0]

        # Get all scores
        scores = {self.id2label[i]: float(prob) for i, prob in enumerate(probs)}

        # Get categories above threshold
        predicted = [
            self.id2label[i]
            for i, prob in enumerate(probs)
            if prob >= threshold
        ]

        return {
            "text": text[:100] + "..." if len(text) > 100 else text,
            "categories": predicted,
            "scores": scores,
        }

    def classify_batch(self, texts: list[str], threshold: float = CONFIDENCE_THRESHOLD) -> list[dict]:
        """Classify multiple texts efficiently."""
        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.sigmoid(outputs.logits).cpu().numpy()

        results = []
        for i, text in enumerate(texts):
            scores = {self.id2label[j]: float(prob) for j, prob in enumerate(probs[i])}
            predicted = [
                self.id2label[j]
                for j, prob in enumerate(probs[i])
                if prob >= threshold
            ]
            results.append({
                "text": text[:100] + "..." if len(text) > 100 else text,
                "categories": predicted,
                "scores": scores,
            })

        return results


def classify_from_database(classifier, limit: int = 100):
    """Classify unclassified articles from the database."""
    import sys
    sys.path.insert(0, str(BASE_DIR))

    from app.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get articles without policy classifications
    cursor.execute("""
        SELECT a.uri, a.title
        FROM articles a
        WHERE a.topic = 'Trump Administration Tracker'
        AND a.title IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM policy_article_categories pac
            WHERE pac.article_uri = a.uri
            AND pac.classification_method = 'ml_model'
        )
        ORDER BY a.publication_date DESC
        LIMIT ?
    """, (limit,))

    articles = cursor.fetchall()
    print(f"Found {len(articles)} unclassified articles")

    if not articles:
        print("No articles to classify")
        return

    # Classify in batches
    batch_size = 32
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        texts = [a[1] for a in batch]
        uris = [a[0] for a in batch]

        results = classifier.classify_batch(texts)

        for uri, result in zip(uris, results):
            if result["categories"]:
                print(f"\n{result['text']}")
                print(f"  Categories: {', '.join(result['categories'])}")

                # Optionally save to database
                for category in result["categories"]:
                    score = result["scores"][category]
                    cursor.execute("""
                        INSERT OR IGNORE INTO policy_article_categories
                        (article_uri, category, topic, confidence, classification_method)
                        VALUES (?, ?, 'Trump Administration Tracker', ?, 'ml_model')
                    """, (uri, category, score))

        conn.commit()
        print(f"Processed {min(i + batch_size, len(articles))}/{len(articles)}")

    conn.close()
    print("\nClassification complete!")


def interactive_mode(classifier):
    """Interactive classification mode."""
    print("\nInteractive Policy Classifier")
    print("Enter article titles/text to classify (Ctrl+C to exit)\n")

    while True:
        try:
            text = input("Text: ").strip()
            if not text:
                continue

            result = classifier.classify(text)

            if result["categories"]:
                print(f"Categories: {', '.join(result['categories'])}")
            else:
                print("No categories matched (below threshold)")

            print("\nAll scores:")
            sorted_scores = sorted(result["scores"].items(), key=lambda x: x[1], reverse=True)
            for cat, score in sorted_scores:
                bar = "█" * int(score * 20)
                marker = " ← predicted" if score >= CONFIDENCE_THRESHOLD else ""
                print(f"  {cat:25s} {score:.3f} {bar}{marker}")
            print()

        except KeyboardInterrupt:
            print("\nExiting")
            break


def main():
    parser = argparse.ArgumentParser(description="Policy Classifier Inference")
    parser.add_argument("text", nargs="?", help="Text to classify")
    parser.add_argument("--from-db", action="store_true", help="Classify from database")
    parser.add_argument("--limit", type=int, default=100, help="Limit for database classification")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--threshold", type=float, default=0.5, help="Confidence threshold")
    parser.add_argument("--model-path", type=str, help="Path to model directory")

    args = parser.parse_args()

    classifier = PolicyClassifier(args.model_path)

    if args.interactive:
        interactive_mode(classifier)
    elif args.from_db:
        classify_from_database(classifier, args.limit)
    elif args.text:
        result = classifier.classify(args.text, args.threshold)
        print(f"\nText: {result['text']}")
        if result["categories"]:
            print(f"Categories: {', '.join(result['categories'])}")
        else:
            print("No categories matched")
        print("\nScores:")
        for cat, score in sorted(result["scores"].items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat}: {score:.3f}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
