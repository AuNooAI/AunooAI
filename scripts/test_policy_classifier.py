#!/usr/bin/env python3
"""
Interactive test script for the policy classifier.

Usage:
    python scripts/test_policy_classifier.py                    # Interactive mode
    python scripts/test_policy_classifier.py "article text"     # Single classification
    python scripts/test_policy_classifier.py --compare          # Compare ML vs keywords
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_classifier():
    """Load the classifier (shows progress)."""
    print("Loading ML classifier models...")
    from app.services.policy_classifier_service import get_classifier_service

    classifier = get_classifier_service()
    loaded = classifier.load_models()

    if loaded:
        status = classifier.get_status()
        print(f"✓ Models loaded: RoBERTa={status['roberta_loaded']}, DeBERTa={status['deberta_loaded']}")
        print(f"  Device: {status['device']}, Threshold: {status['threshold']}")
    else:
        print(f"✗ Failed to load models: {classifier._load_error}")

    return classifier, loaded


def classify_text(classifier, text, show_scores=True):
    """Classify a single text."""
    result = classifier.classify(text, return_scores=True)

    print(f"\nText: {text[:100]}{'...' if len(text) > 100 else ''}")
    print(f"Categories: {result['categories'] or '(none)'}")

    if show_scores and result.get('scores'):
        print("All scores:")
        for cat, score in sorted(result['scores'].items(), key=lambda x: -x[1]):
            bar = "█" * int(score * 20)
            marker = " ← predicted" if score >= 0.5 else ""
            print(f"  {cat:25s} {score:.3f} {bar}{marker}")


def compare_methods(text):
    """Compare ML vs keyword classification."""
    from app.routes.policy_tracker_routes import (
        _categorize_article_ml,
        _categorize_article_keywords
    )

    print(f"\nText: {text[:100]}{'...' if len(text) > 100 else ''}")
    print("-" * 60)

    # Keyword-based
    keyword_cats = _categorize_article_keywords(text, "")
    print(f"Keyword categories: {keyword_cats or '(none)'}")

    # ML-based
    ml_cats, ml_scores, ml_success = _categorize_article_ml(text, "")
    if ml_success:
        print(f"ML categories:      {ml_cats or '(none)'}")
        if ml_scores:
            top3 = sorted(ml_scores.items(), key=lambda x: -x[1])[:3]
            print(f"Top ML scores:      {', '.join([f'{c}: {s:.2f}' for c, s in top3])}")
    else:
        print("ML: (not available)")


def interactive_mode(classifier):
    """Interactive classification mode."""
    print("\n" + "=" * 60)
    print("Interactive Policy Classifier")
    print("Enter text to classify (Ctrl+C to exit)")
    print("=" * 60)

    while True:
        try:
            text = input("\nText: ").strip()
            if not text:
                continue
            classify_text(classifier, text)
        except KeyboardInterrupt:
            print("\nExiting")
            break


def main():
    parser = argparse.ArgumentParser(description="Test policy classifier")
    parser.add_argument("text", nargs="?", help="Text to classify")
    parser.add_argument("--compare", action="store_true", help="Compare ML vs keyword methods")
    parser.add_argument("--batch", action="store_true", help="Run batch of test cases")

    args = parser.parse_args()

    # Load classifier
    classifier, loaded = load_classifier()

    if not loaded:
        print("\nFalling back to keyword-based classification")

    if args.compare:
        # Compare mode
        test_texts = [
            args.text or "Trump threatens tariffs on Denmark over Greenland",
            "ICE conducts raids in sanctuary cities",
            "Trump fires FBI director investigating his campaign",
            "CDC removes climate change data from website",
            "Harvard professor fired for DEI research",
        ]
        print("\n" + "=" * 60)
        print("Comparing ML vs Keyword Classification")
        print("=" * 60)
        for text in test_texts:
            compare_methods(text)
            print()

    elif args.batch:
        # Batch test mode
        test_texts = [
            "Trump threatens tariffs on Denmark over Greenland",
            "ICE conducts raids in sanctuary cities across California",
            "Trump fires FBI director James Comey investigating Russia ties",
            "CDC removes climate change data from government website",
            "Harvard professor terminated for DEI diversity research",
            "Stephen Miller announces mass deportation plan",
            "Supreme Court blocks Trump travel ban order",
            "EPA administrator Scott Pruitt faces ethics investigation",
            "Trump pardons former campaign chairman Paul Manafort",
            "Pentagon announces troop deployment to US-Mexico border",
        ]
        print("\n" + "=" * 60)
        print("Batch Classification Test")
        print("=" * 60)
        for text in test_texts:
            classify_text(classifier, text, show_scores=False)

    elif args.text:
        # Single classification
        classify_text(classifier, args.text)

    else:
        # Interactive mode
        interactive_mode(classifier)


if __name__ == "__main__":
    main()
