#!/usr/bin/env python3
"""
Export User Relevance Feedback for Training

Exports user feedback data from the database for training the relevance model.
Creates a dataset with:
- Positive examples (more_like_this) labeled as relevant
- Negative examples (less_like_this) labeled as not relevant

Output: JSON file with article content and relevance labels.
"""

import json
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def export_relevance_feedback(output_dir: str = "data/training", min_samples: int = 10) -> dict:
    """
    Export user relevance feedback for training.

    Args:
        output_dir: Directory to save the exported data
        min_samples: Minimum samples per topic to include

    Returns:
        dict with export statistics
    """
    db = get_db()
    cursor = db.cursor()

    # Get all feedback with article content
    cursor.execute("""
        SELECT
            f.article_uri,
            f.topic,
            f.feedback_type,
            f.relevance_score,
            f.classifier_score,
            f.embedding_score,
            f.created_at,
            a.title,
            a.content,
            a.summary,
            a.category,
            a.news_source,
            a.tags
        FROM user_relevance_feedback f
        JOIN articles a ON f.article_uri = a.uri
        ORDER BY f.topic, f.created_at
    """)

    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} feedback records")

    # Organize by topic
    by_topic = {}
    for row in rows:
        topic = row[1]
        if topic not in by_topic:
            by_topic[topic] = {"more_like_this": [], "less_like_this": []}

        record = {
            "uri": row[0],
            "topic": row[1],
            "feedback_type": row[2],
            "relevance_score": row[3],
            "classifier_score": row[4],
            "embedding_score": row[5],
            "feedback_date": row[6].isoformat() if row[6] else None,
            "title": row[7],
            "content": row[8],
            "summary": row[9],
            "category": row[10],
            "source": row[11],
            "tags": row[12],
        }

        if row[2] == "more_like_this":
            by_topic[topic]["more_like_this"].append(record)
        else:
            by_topic[topic]["less_like_this"].append(record)

    # Create training dataset
    training_samples = []
    stats = {
        "total_feedback": len(rows),
        "topics": {},
        "total_positive": 0,
        "total_negative": 0,
        "skipped_topics": [],
    }

    for topic, data in by_topic.items():
        total = len(data["more_like_this"]) + len(data["less_like_this"])

        stats["topics"][topic] = {
            "more_like_this": len(data["more_like_this"]),
            "less_like_this": len(data["less_like_this"]),
            "total": total,
        }

        if total < min_samples:
            logger.info(f"Skipping {topic}: only {total} samples (min: {min_samples})")
            stats["skipped_topics"].append(topic)
            continue

        # Add positive samples (relevant)
        for record in data["more_like_this"]:
            # Use summary + first 500 chars of content for embedding
            text = record["summary"] or ""
            if record["content"]:
                text += " " + record["content"][:500]

            training_samples.append({
                "text": text.strip(),
                "label": 1,  # relevant
                "topic": topic,
                "uri": record["uri"],
                "title": record["title"],
                "feedback_type": "more_like_this",
            })
            stats["total_positive"] += 1

        # Add negative samples (not relevant)
        for record in data["less_like_this"]:
            text = record["summary"] or ""
            if record["content"]:
                text += " " + record["content"][:500]

            training_samples.append({
                "text": text.strip(),
                "label": 0,  # not relevant
                "topic": topic,
                "uri": record["uri"],
                "title": record["title"],
                "feedback_type": "less_like_this",
            })
            stats["total_negative"] += 1

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Save training data
    output_file = os.path.join(output_dir, "relevance_feedback.json")
    with open(output_file, "w") as f:
        json.dump({
            "samples": training_samples,
            "stats": stats,
            "exported_at": datetime.utcnow().isoformat(),
        }, f, indent=2)

    logger.info(f"Exported {len(training_samples)} samples to {output_file}")
    logger.info(f"  Positive (more_like_this): {stats['total_positive']}")
    logger.info(f"  Negative (less_like_this): {stats['total_negative']}")
    logger.info(f"  Topics included: {len(stats['topics']) - len(stats['skipped_topics'])}")
    logger.info(f"  Topics skipped: {len(stats['skipped_topics'])}")

    # Also create per-topic files for fine-grained training
    for topic, data in by_topic.items():
        if topic in stats["skipped_topics"]:
            continue

        topic_samples = [s for s in training_samples if s["topic"] == topic]
        if topic_samples:
            safe_topic = topic.replace(" ", "_").replace("/", "_").lower()
            topic_file = os.path.join(output_dir, f"relevance_feedback_{safe_topic}.json")
            with open(topic_file, "w") as f:
                json.dump({
                    "topic": topic,
                    "samples": topic_samples,
                    "positive_count": stats["topics"][topic]["more_like_this"],
                    "negative_count": stats["topics"][topic]["less_like_this"],
                }, f, indent=2)
            logger.info(f"  Created topic file: {topic_file}")

    return stats


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Export user relevance feedback for training")
    parser.add_argument("--output-dir", default="data/training", help="Output directory")
    parser.add_argument("--min-samples", type=int, default=10, help="Minimum samples per topic")
    args = parser.parse_args()

    stats = export_relevance_feedback(
        output_dir=args.output_dir,
        min_samples=args.min_samples,
    )

    print("\n" + "=" * 50)
    print("Export Summary")
    print("=" * 50)
    print(f"Total feedback: {stats['total_feedback']}")
    print(f"Positive samples: {stats['total_positive']}")
    print(f"Negative samples: {stats['total_negative']}")
    print(f"Topics included: {len(stats['topics']) - len(stats['skipped_topics'])}")

    if stats['skipped_topics']:
        print(f"\nSkipped topics (< min samples): {', '.join(stats['skipped_topics'])}")


if __name__ == "__main__":
    main()
