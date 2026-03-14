#!/usr/bin/env python3
"""
KeyBERT Tagging Evaluation Script

Compares KeyBERT-generated tags vs LLM-generated tags.
Measures semantic similarity, latency, and tag diversity.

Usage:
    python scripts/evaluate_keybert_tags.py --sample-size 100
    python scripts/evaluate_keybert_tags.py --sample-size 50 --verbose
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sqlalchemy import text

from app.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_sample_articles(db: Database, sample_size: int) -> List[Dict[str, Any]]:
    """Get a sample of articles with existing LLM-generated tags."""
    with db.get_session() as session:
        result = session.execute(
            text("""
                SELECT
                    a.uri,
                    a.title,
                    a.summary,
                    a.tags,
                    r.raw_markdown
                FROM articles a
                LEFT JOIN raw_articles r ON a.uri = r.uri
                WHERE a.tags IS NOT NULL
                  AND a.tags != ''
                  AND a.summary IS NOT NULL
                  AND length(a.summary) > 50
                ORDER BY a.ingested_at DESC
                LIMIT :limit
            """),
            {"limit": sample_size}
        )

        articles = []
        for row in result:
            articles.append({
                "uri": row.uri,
                "title": row.title,
                "summary": row.summary,
                "llm_tags": [t.strip() for t in row.tags.split(",") if t.strip()],
                "content": row.raw_markdown[:2000] if row.raw_markdown else None,
            })

        return articles


def compute_semantic_similarity(
    keybert_tags: List[str],
    llm_tags: List[str],
    embedding_model
) -> float:
    """Compute semantic similarity between KeyBERT and LLM tags."""
    if not keybert_tags or not llm_tags:
        return 0.0

    # Encode all tags
    kb_embeddings = embedding_model.encode(keybert_tags)
    llm_embeddings = embedding_model.encode(llm_tags)

    # Compute cosine similarities
    # For each KeyBERT tag, find max similarity to any LLM tag
    similarities = []
    for kb_emb in kb_embeddings:
        max_sim = max(
            np.dot(kb_emb, llm_emb) / (np.linalg.norm(kb_emb) * np.linalg.norm(llm_emb))
            for llm_emb in llm_embeddings
        )
        similarities.append(max_sim)

    return float(np.mean(similarities))


def compute_diversity_score(tags: List[str], embedding_model) -> float:
    """
    Compute diversity score for a set of tags.
    Higher score = more diverse (less semantic overlap between tags).
    """
    if len(tags) < 2:
        return 1.0

    embeddings = embedding_model.encode(tags)

    # Compute pairwise similarities
    similarities = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sim = np.dot(embeddings[i], embeddings[j]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
            )
            similarities.append(sim)

    # Diversity = 1 - average similarity
    avg_similarity = np.mean(similarities)
    return float(1 - avg_similarity)


def evaluate_keybert(
    articles: List[Dict[str, Any]],
    tagging_service,
    embedding_model,
    verbose: bool = False
) -> Dict[str, Any]:
    """Run evaluation comparing KeyBERT vs LLM tags."""

    results = []
    total_kb_latency = 0

    for i, article in enumerate(articles):
        if verbose:
            logger.info(f"Processing article {i+1}/{len(articles)}: {article['title'][:50]}...")

        # Extract KeyBERT tags
        kb_result = tagging_service.extract_tags(
            title=article["title"],
            summary=article["summary"],
            content=article.get("content")
        )

        keybert_tags = kb_result.get("tags", [])
        llm_tags = article["llm_tags"]
        latency = kb_result.get("latency_ms", 0)
        total_kb_latency += latency

        # Compute metrics
        semantic_sim = compute_semantic_similarity(keybert_tags, llm_tags, embedding_model)
        kb_diversity = compute_diversity_score(keybert_tags, embedding_model)
        llm_diversity = compute_diversity_score(llm_tags, embedding_model)

        result = {
            "uri": article["uri"],
            "title": article["title"][:80],
            "keybert_tags": keybert_tags,
            "llm_tags": llm_tags,
            "semantic_similarity": semantic_sim,
            "keybert_diversity": kb_diversity,
            "llm_diversity": llm_diversity,
            "latency_ms": latency,
        }
        results.append(result)

        if verbose:
            logger.info(f"  KeyBERT: {keybert_tags}")
            logger.info(f"  LLM:     {llm_tags}")
            logger.info(f"  Similarity: {semantic_sim:.3f}, KB Diversity: {kb_diversity:.3f}")

    # Aggregate statistics
    semantic_sims = [r["semantic_similarity"] for r in results]
    kb_diversities = [r["keybert_diversity"] for r in results]
    llm_diversities = [r["llm_diversity"] for r in results]
    latencies = [r["latency_ms"] for r in results]

    # Tag coverage analysis
    all_kb_tags = [tag for r in results for tag in r["keybert_tags"]]
    all_llm_tags = [tag for r in results for tag in r["llm_tags"]]

    summary = {
        "sample_size": len(articles),
        "metrics": {
            "semantic_similarity": {
                "mean": float(np.mean(semantic_sims)),
                "std": float(np.std(semantic_sims)),
                "min": float(np.min(semantic_sims)),
                "max": float(np.max(semantic_sims)),
            },
            "keybert_diversity": {
                "mean": float(np.mean(kb_diversities)),
                "std": float(np.std(kb_diversities)),
            },
            "llm_diversity": {
                "mean": float(np.mean(llm_diversities)),
                "std": float(np.std(llm_diversities)),
            },
            "latency_ms": {
                "mean": float(np.mean(latencies)),
                "std": float(np.std(latencies)),
                "p50": float(np.percentile(latencies, 50)),
                "p95": float(np.percentile(latencies, 95)),
                "total": total_kb_latency,
            },
        },
        "tag_analysis": {
            "keybert": {
                "total_tags": len(all_kb_tags),
                "unique_tags": len(set(all_kb_tags)),
                "avg_tags_per_article": len(all_kb_tags) / len(results),
                "top_10": Counter(all_kb_tags).most_common(10),
            },
            "llm": {
                "total_tags": len(all_llm_tags),
                "unique_tags": len(set(all_llm_tags)),
                "avg_tags_per_article": len(all_llm_tags) / len(results),
                "top_10": Counter(all_llm_tags).most_common(10),
            },
        },
        "individual_results": results,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Evaluate KeyBERT tagging vs LLM tags")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of articles to evaluate")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output per article")
    parser.add_argument("--output", "-o", type=str, help="Output file path (JSON)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("KeyBERT Tagging Evaluation")
    logger.info("=" * 60)

    # Initialize database
    logger.info("Connecting to database...")
    db = Database()

    # Initialize KeyBERT service
    logger.info("Loading KeyBERT tagging service...")
    from app.services.keybert_tagging_service import get_keybert_tagging_service
    tagging_service = get_keybert_tagging_service()

    if not tagging_service.is_available():
        logger.error("KeyBERT service not available. Please install keybert: pip install keybert")
        sys.exit(1)

    # Get embedding model for similarity computation
    embedding_model = tagging_service.get_embedding_model()

    # Get sample articles
    logger.info(f"Fetching {args.sample_size} sample articles with existing LLM tags...")
    articles = get_sample_articles(db, args.sample_size)
    logger.info(f"Found {len(articles)} articles")

    if not articles:
        logger.error("No articles found with tags. Please run the ingest pipeline first.")
        sys.exit(1)

    # Run evaluation
    logger.info("Running evaluation...")
    results = evaluate_keybert(articles, tagging_service, embedding_model, verbose=args.verbose)

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)

    metrics = results["metrics"]

    print(f"\nSample Size: {results['sample_size']} articles")

    print("\n--- Semantic Similarity (KeyBERT vs LLM) ---")
    print(f"  Mean:  {metrics['semantic_similarity']['mean']:.3f}")
    print(f"  Std:   {metrics['semantic_similarity']['std']:.3f}")
    print(f"  Range: [{metrics['semantic_similarity']['min']:.3f}, {metrics['semantic_similarity']['max']:.3f}]")

    print("\n--- Tag Diversity ---")
    print(f"  KeyBERT: {metrics['keybert_diversity']['mean']:.3f} (higher = more diverse)")
    print(f"  LLM:     {metrics['llm_diversity']['mean']:.3f}")

    print("\n--- Latency ---")
    print(f"  Mean:  {metrics['latency_ms']['mean']:.1f} ms")
    print(f"  P50:   {metrics['latency_ms']['p50']:.1f} ms")
    print(f"  P95:   {metrics['latency_ms']['p95']:.1f} ms")
    print(f"  Total: {metrics['latency_ms']['total']:.0f} ms")

    print("\n--- Tag Analysis ---")
    kb_analysis = results["tag_analysis"]["keybert"]
    llm_analysis = results["tag_analysis"]["llm"]
    print(f"  KeyBERT - Total: {kb_analysis['total_tags']}, Unique: {kb_analysis['unique_tags']}, Avg/article: {kb_analysis['avg_tags_per_article']:.1f}")
    print(f"  LLM     - Total: {llm_analysis['total_tags']}, Unique: {llm_analysis['unique_tags']}, Avg/article: {llm_analysis['avg_tags_per_article']:.1f}")

    print("\n--- Top 10 KeyBERT Tags ---")
    for tag, count in kb_analysis["top_10"]:
        print(f"  {tag}: {count}")

    print("\n--- Top 10 LLM Tags ---")
    for tag, count in llm_analysis["top_10"]:
        print(f"  {tag}: {count}")

    # Save results
    output_path = args.output or "data/evaluation/keybert_evaluation.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Remove individual results for cleaner output (optional)
    results_to_save = {k: v for k, v in results.items() if k != "individual_results"}
    results_to_save["sample_results"] = results["individual_results"][:10]  # Save first 10 only

    with open(output_path, "w") as f:
        json.dump(results_to_save, f, indent=2)

    logger.info(f"\nResults saved to: {output_path}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
