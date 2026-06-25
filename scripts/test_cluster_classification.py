#!/usr/bin/env python3
"""
Test cluster-based classification vs individual article classification.

Hypothesis: Clustering similar articles and classifying the cluster
(via concatenated headlines or majority vote) will improve coverage
for borderline cases while filtering noise.

Usage:
    python scripts/test_cluster_classification.py
    python scripts/test_cluster_classification.py --csv path/to/data.csv
    python scripts/test_cluster_classification.py --threshold 0.4 --cluster-similarity 0.85
"""

import argparse
import sys
import csv
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Default training data path
DEFAULT_CSV = Path(__file__).parent.parent / "spec-files-aunoo/trump_action_tracker_eda/data/trump-actions__1_.csv"


# CSV column to internal category mapping (exact column names from CSV)
CSV_CATEGORY_MAP = {
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

CATEGORIES = list(CSV_CATEGORY_MAP.values())


def load_articles_from_csv(csv_path: str, limit: int = 1000) -> List[Dict]:
    """Load articles from Trump Action Tracker CSV with ground truth labels."""
    articles = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find header row
    lines = content.strip().split('\n')
    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("Index,"):
            header_idx = i
            break

    csv_data = '\n'.join(lines[header_idx:])
    reader = csv.DictReader(csv_data.split('\n'))

    for row in reader:
        title = row.get("Title", "").strip()
        url = row.get("URL", "").strip()
        date = row.get("Date", "").strip()

        if not title:
            continue

        # Extract ground truth labels
        ground_truth = []
        for csv_col, internal_name in CSV_CATEGORY_MAP.items():
            if row.get(csv_col, "").strip().lower() == "yes":
                ground_truth.append(internal_name)

        articles.append({
            "uri": url,
            "title": title,
            "summary": "",
            "date": date,
            "embedding": None,
            "ground_truth": ground_truth  # Add ground truth labels
        })

        if len(articles) >= limit:
            break

    return articles


def generate_embeddings(articles: List[Dict], model_name: str = "all-MiniLM-L6-v2") -> List[Dict]:
    """Generate embeddings for articles using sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    # Get texts to embed
    texts = [a["title"] for a in articles]

    print(f"Generating embeddings for {len(texts)} articles...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    # Attach embeddings to articles
    for article, embedding in zip(articles, embeddings):
        article["embedding"] = embedding

    return articles


def get_articles_with_embeddings_from_db(topic: str, limit: int = 1000) -> List[Dict]:
    """Fetch articles with their embeddings from pgvector."""
    from app.database import get_database_instance
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()

    # Get articles with embeddings (embedding is directly in articles table)
    result = conn.execute(text("""
        SELECT uri, title, summary, publication_date, embedding
        FROM articles
        WHERE topic = :topic
        AND title IS NOT NULL
        AND embedding IS NOT NULL
        ORDER BY publication_date DESC
        LIMIT :limit
    """), {"topic": topic, "limit": limit})

    articles = []
    for row in result:
        uri, title, summary, pub_date, embedding = row
        # Convert pgvector to numpy array
        if embedding:
            if isinstance(embedding, str):
                # Parse string format [1,2,3,...]
                embedding = np.array([float(x) for x in embedding.strip('[]').split(',')])
            elif hasattr(embedding, '__iter__'):
                embedding = np.array(list(embedding))
            else:
                embedding = np.array(embedding)
        articles.append({
            "uri": uri,
            "title": title,
            "summary": summary or "",
            "date": pub_date,
            "embedding": embedding
        })

    conn.close()
    return articles


def cluster_articles(articles: List[Dict], similarity_threshold: float = 0.85) -> List[List[Dict]]:
    """
    Cluster articles by embedding similarity using greedy clustering.

    Args:
        articles: List of article dicts with 'embedding' key
        similarity_threshold: Cosine similarity threshold for clustering

    Returns:
        List of clusters (each cluster is a list of articles)
    """
    from sklearn.metrics.pairwise import cosine_similarity

    # Filter articles with valid embeddings
    valid_articles = [a for a in articles if a["embedding"] is not None and len(a["embedding"]) > 0]

    if not valid_articles:
        return []

    # Build embedding matrix
    embeddings = np.vstack([a["embedding"] for a in valid_articles])

    # Compute pairwise similarities
    similarities = cosine_similarity(embeddings)

    # Greedy clustering
    clusters = []
    assigned = set()

    for i, article in enumerate(valid_articles):
        if i in assigned:
            continue

        # Start new cluster
        cluster = [article]
        assigned.add(i)

        # Find similar articles
        for j, other in enumerate(valid_articles):
            if j in assigned:
                continue
            if similarities[i, j] >= similarity_threshold:
                cluster.append(other)
                assigned.add(j)

        clusters.append(cluster)

    return clusters


def classify_individual(classifier, articles: List[Dict], threshold: float = 0.5) -> Dict[str, Dict]:
    """Classify each article individually."""
    results = {}

    for article in articles:
        text = f"{article['title']}. {article['summary'][:200]}" if article['summary'] else article['title']
        result = classifier.classify(text, threshold=threshold, return_scores=True)
        results[article['uri']] = {
            "title": article['title'],
            "categories": result['categories'],
            "scores": result['scores'],
            "max_score": max(result['scores'].values()) if result['scores'] else 0
        }

    return results


def classify_cluster_concatenated(classifier, cluster: List[Dict], threshold: float = 0.5) -> Dict:
    """Classify cluster by concatenating top headlines."""
    # Take up to 5 headlines
    headlines = [a['title'] for a in cluster[:5]]
    combined_text = " | ".join(headlines)

    result = classifier.classify(combined_text, threshold=threshold, return_scores=True)

    return {
        "method": "concatenated",
        "headlines_used": len(headlines),
        "categories": result['categories'],
        "scores": result['scores'],
        "max_score": max(result['scores'].values()) if result['scores'] else 0
    }


def classify_cluster_majority(classifier, cluster: List[Dict], threshold: float = 0.5) -> Dict:
    """Classify cluster by averaging scores across all articles."""
    all_scores = defaultdict(list)

    for article in cluster:
        text = article['title']
        result = classifier.classify(text, threshold=threshold, return_scores=True)
        for cat, score in result['scores'].items():
            all_scores[cat].append(score)

    # Average scores
    avg_scores = {cat: np.mean(scores) for cat, scores in all_scores.items()}
    categories = [cat for cat, score in avg_scores.items() if score >= threshold]

    return {
        "method": "majority_vote",
        "articles_in_cluster": len(cluster),
        "categories": categories,
        "scores": avg_scores,
        "max_score": max(avg_scores.values()) if avg_scores else 0
    }


def classify_cluster_any_above(classifier, cluster: List[Dict], threshold: float = 0.5) -> Dict:
    """Classify cluster: category assigned if ANY article scores above threshold."""
    max_scores = defaultdict(float)

    for article in cluster:
        text = article['title']
        result = classifier.classify(text, threshold=threshold, return_scores=True)
        for cat, score in result['scores'].items():
            max_scores[cat] = max(max_scores[cat], score)

    categories = [cat for cat, score in max_scores.items() if score >= threshold]

    return {
        "method": "any_above",
        "articles_in_cluster": len(cluster),
        "categories": categories,
        "scores": dict(max_scores),
        "max_score": max(max_scores.values()) if max_scores else 0
    }


def compute_metrics(predictions: List[List[str]], ground_truth: List[List[str]]) -> Dict:
    """Compute F1, precision, recall for multi-label classification."""
    from sklearn.preprocessing import MultiLabelBinarizer
    from sklearn.metrics import f1_score, precision_score, recall_score

    # Binarize labels
    mlb = MultiLabelBinarizer(classes=CATEGORIES)
    y_true = mlb.fit_transform(ground_truth)
    y_pred = mlb.transform(predictions)

    # Compute metrics
    f1_micro = f1_score(y_true, y_pred, average='micro', zero_division=0)
    f1_macro = f1_score(y_true, y_pred, average='macro', zero_division=0)
    precision = precision_score(y_true, y_pred, average='micro', zero_division=0)
    recall = recall_score(y_true, y_pred, average='micro', zero_division=0)

    # Exact match (all labels correct)
    exact_match = np.mean([set(p) == set(g) for p, g in zip(predictions, ground_truth)])

    return {
        "f1_micro": f1_micro,
        "f1_macro": f1_macro,
        "precision": precision,
        "recall": recall,
        "exact_match": exact_match
    }


def compare_methods(articles: List[Dict], clusters: List[List[Dict]], classifier, threshold: float = 0.5):
    """Compare individual vs cluster classification methods with accuracy metrics."""

    print(f"\n{'='*70}")
    print(f"COMPARISON: Individual vs Cluster Classification (with ACCURACY)")
    print(f"{'='*70}")
    print(f"Total articles: {len(articles)}")
    print(f"Total clusters: {len(clusters)}")
    print(f"Avg cluster size: {np.mean([len(c) for c in clusters]):.1f}")
    print(f"Classification threshold: {threshold}")

    # Check if we have ground truth
    has_ground_truth = all('ground_truth' in a for a in articles)
    if not has_ground_truth:
        print("\nWARNING: No ground truth labels - only coverage metrics available")

    # Individual classification
    print(f"\n--- Individual Classification ---")
    individual_results = classify_individual(classifier, articles, threshold)

    individual_classified = sum(1 for r in individual_results.values() if r['categories'])
    individual_unclassified = len(individual_results) - individual_classified

    print(f"Coverage: {individual_classified}/{len(articles)} ({individual_classified/len(articles)*100:.1f}%)")

    if has_ground_truth:
        ind_predictions = [individual_results[a['uri']]['categories'] for a in articles]
        ind_ground_truth = [a['ground_truth'] for a in articles]
        ind_metrics = compute_metrics(ind_predictions, ind_ground_truth)
        print(f"F1 Micro: {ind_metrics['f1_micro']:.4f}")
        print(f"F1 Macro: {ind_metrics['f1_macro']:.4f}")
        print(f"Precision: {ind_metrics['precision']:.4f}")
        print(f"Recall: {ind_metrics['recall']:.4f}")
        print(f"Exact Match: {ind_metrics['exact_match']:.2%}")

    # Cluster classification methods
    methods = {
        "concatenated": classify_cluster_concatenated,
        "majority_vote": classify_cluster_majority,
        "any_above": classify_cluster_any_above,
    }

    # Build article to cluster mapping
    article_to_cluster = {}
    for cluster in clusters:
        for article in cluster:
            article_to_cluster[article['uri']] = cluster

    results_summary = {"individual": ind_metrics if has_ground_truth else None}

    for method_name, method_fn in methods.items():
        print(f"\n--- Cluster Classification: {method_name} ---")

        # Get predictions for each article via its cluster
        cluster_predictions = {}
        cluster_cache = {}  # Cache cluster results

        for article in articles:
            cluster = article_to_cluster.get(article['uri'])
            if cluster:
                cluster_key = tuple(a['uri'] for a in cluster)
                if cluster_key not in cluster_cache:
                    cluster_cache[cluster_key] = method_fn(classifier, cluster, threshold)
                cluster_predictions[article['uri']] = cluster_cache[cluster_key]['categories']
            else:
                cluster_predictions[article['uri']] = []

        cluster_classified = sum(1 for cats in cluster_predictions.values() if cats)
        print(f"Coverage: {cluster_classified}/{len(articles)} ({cluster_classified/len(articles)*100:.1f}%)")

        if has_ground_truth:
            clust_preds = [cluster_predictions[a['uri']] for a in articles]
            clust_ground_truth = [a['ground_truth'] for a in articles]
            clust_metrics = compute_metrics(clust_preds, clust_ground_truth)
            print(f"F1 Micro: {clust_metrics['f1_micro']:.4f}")
            print(f"F1 Macro: {clust_metrics['f1_macro']:.4f}")
            print(f"Precision: {clust_metrics['precision']:.4f}")
            print(f"Recall: {clust_metrics['recall']:.4f}")
            print(f"Exact Match: {clust_metrics['exact_match']:.2%}")
            results_summary[method_name] = clust_metrics

            # Compare to individual
            f1_diff = clust_metrics['f1_micro'] - ind_metrics['f1_micro']
            print(f"Δ F1 vs Individual: {f1_diff:+.4f} ({'better' if f1_diff > 0 else 'worse' if f1_diff < 0 else 'same'})")

    # Summary table
    if has_ground_truth:
        print(f"\n{'='*70}")
        print("SUMMARY: F1 Micro Scores")
        print(f"{'='*70}")
        print(f"{'Method':<20} {'F1 Micro':<10} {'Exact Match':<12} {'Δ vs Individual':<15}")
        print("-" * 60)
        for method, metrics in results_summary.items():
            if metrics:
                delta = metrics['f1_micro'] - ind_metrics['f1_micro'] if method != 'individual' else 0
                delta_str = f"{delta:+.4f}" if method != 'individual' else "-"
                print(f"{method:<20} {metrics['f1_micro']:.4f}     {metrics['exact_match']:.2%}        {delta_str}")

    # Analyze clusters that filtered noise
    print(f"\n--- Noise Filtering Analysis ---")
    singleton_clusters = [c for c in clusters if len(c) == 1]
    print(f"Singleton clusters (potential noise): {len(singleton_clusters)}")

    # Show some singletons that were unclassified
    unclassified_singletons = []
    for cluster in singleton_clusters:
        article = cluster[0]
        ind_result = individual_results.get(article['uri'], {})
        if not ind_result.get('categories'):
            unclassified_singletons.append({
                "title": article['title'],
                "max_score": ind_result.get('max_score', 0)
            })

    print(f"Unclassified singletons: {len(unclassified_singletons)}")
    if unclassified_singletons[:5]:
        print(f"\nExample filtered noise (singletons, unclassified):")
        for s in unclassified_singletons[:5]:
            print(f"  - \"{s['title'][:70]}...\" (max: {s['max_score']:.3f})")


def analyze_cluster_examples(clusters: List[List[Dict]], classifier, n_examples: int = 3):
    """Show detailed examples of cluster classification."""

    print(f"\n{'='*70}")
    print(f"CLUSTER EXAMPLES (showing {n_examples} multi-article clusters)")
    print(f"{'='*70}")

    # Get multi-article clusters
    multi_clusters = sorted([c for c in clusters if len(c) >= 3], key=len, reverse=True)[:n_examples]

    for i, cluster in enumerate(multi_clusters):
        print(f"\n--- Cluster {i+1} ({len(cluster)} articles) ---")

        # Show headlines
        print("Headlines:")
        for article in cluster[:5]:
            print(f"  • {article['title'][:80]}")
        if len(cluster) > 5:
            print(f"  ... and {len(cluster) - 5} more")

        # Individual classifications
        print("\nIndividual classifications:")
        for article in cluster[:3]:
            result = classifier.classify(article['title'], return_scores=True)
            cats = result['categories'] or "(none)"
            max_score = max(result['scores'].values())
            print(f"  • {cats} (max: {max_score:.3f})")

        # Cluster classifications
        concat_result = classify_cluster_concatenated(classifier, cluster)
        majority_result = classify_cluster_majority(classifier, cluster)
        any_result = classify_cluster_any_above(classifier, cluster)

        print(f"\nCluster classifications:")
        print(f"  Concatenated: {concat_result['categories'] or '(none)'} (max: {concat_result['max_score']:.3f})")
        print(f"  Majority vote: {majority_result['categories'] or '(none)'} (max: {majority_result['max_score']:.3f})")
        print(f"  Any above:    {any_result['categories'] or '(none)'} (max: {any_result['max_score']:.3f})")


def main():
    parser = argparse.ArgumentParser(description="Test cluster-based classification")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV),
                        help="Path to CSV file with training data")
    parser.add_argument("--from-db", action="store_true",
                        help="Load from database instead of CSV")
    parser.add_argument("--topic", type=str, default="Trump Administration Tracker",
                        help="Topic to analyze (when using --from-db)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max articles to process")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Classification threshold")
    parser.add_argument("--cluster-similarity", type=float, default=0.85,
                        help="Cosine similarity threshold for clustering")
    parser.add_argument("--embedding-model", type=str, default="all-MiniLM-L6-v2",
                        help="Sentence transformer model for embeddings")
    parser.add_argument("--examples", action="store_true",
                        help="Show detailed cluster examples")

    args = parser.parse_args()

    print(f"Loading policy classifier...")
    from app.services.policy_classifier_service import get_classifier_service
    classifier = get_classifier_service()
    if not classifier.load_models():
        print("Failed to load classifier models")
        return

    # Load articles
    if args.from_db:
        print(f"Fetching articles from database for topic: {args.topic}")
        articles = get_articles_with_embeddings_from_db(args.topic, args.limit)
        print(f"Found {len(articles)} articles with embeddings")
    else:
        print(f"Loading articles from CSV: {args.csv}")
        articles = load_articles_from_csv(args.csv, args.limit)
        print(f"Loaded {len(articles)} articles")

        # Generate embeddings
        articles = generate_embeddings(articles, args.embedding_model)

    if not articles:
        print("No articles found!")
        return

    print(f"\nClustering articles (similarity threshold: {args.cluster_similarity})...")
    clusters = cluster_articles(articles, args.cluster_similarity)
    print(f"Created {len(clusters)} clusters")

    # Size distribution
    sizes = [len(c) for c in clusters]
    print(f"Cluster sizes: min={min(sizes)}, max={max(sizes)}, median={np.median(sizes):.0f}")

    # Compare methods
    compare_methods(articles, clusters, classifier, args.threshold)

    # Show examples if requested
    if args.examples:
        analyze_cluster_examples(clusters, classifier)

    print(f"\n{'='*70}")
    print("DONE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
