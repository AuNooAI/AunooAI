"""
Cluster Detector Service

Detects clusters in article embeddings using HDBSCAN.
HDBSCAN is ideal because it:
- Automatically determines the number of clusters
- Handles varying densities
- Identifies outliers naturally
- Produces hierarchical structure
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import text

try:
    import hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    logging.warning("hdbscan not installed. Using fallback clustering.")

from sklearn.metrics.pairwise import cosine_distances

from app.database import get_database_instance

logger = logging.getLogger(__name__)


@dataclass
class ClusterConfig:
    """Configuration for cluster detection."""
    min_cluster_size: int = 5
    min_samples: int = 3
    cluster_selection_epsilon: float = 0.0
    metric: str = 'precomputed'  # Use precomputed distance matrix
    days_back: int = 7  # How many days of articles to cluster


@dataclass
class ArticleCluster:
    """Represents a single cluster of articles."""
    cluster_id: str
    article_uris: List[str]
    centroid: Optional[np.ndarray] = None
    centroid_str: Optional[str] = None
    avg_internal_distance: float = 0.0
    cluster_radius: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "article_count": len(self.article_uris),
            "article_uris": self.article_uris,
            "avg_internal_distance": round(self.avg_internal_distance, 4),
            "cluster_radius": round(self.cluster_radius, 4),
        }


@dataclass
class ClusterResult:
    """Result of cluster detection."""
    clusters: List[ArticleCluster]
    outliers: List[str]  # Article URIs that didn't cluster
    total_articles: int
    detection_date: date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_count": len(self.clusters),
            "outlier_count": len(self.outliers),
            "total_articles": self.total_articles,
            "detection_date": str(self.detection_date),
            "clusters": [c.to_dict() for c in self.clusters],
            "outlier_uris": self.outliers[:20],  # Limit for response size
        }


class ClusterDetector:
    """
    Detects clusters in article embeddings using HDBSCAN.
    """

    def __init__(self, config: Optional[ClusterConfig] = None):
        self.config = config or ClusterConfig()

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def fetch_embeddings(
        self,
        topic_filter: Optional[str] = None,
        days_back: Optional[int] = None,
        article_uris: Optional[List[str]] = None
    ) -> Tuple[List[str], np.ndarray]:
        """
        Fetch article embeddings from the database.

        Returns tuple of (article_uris, embedding_matrix).
        """
        days = days_back or self.config.days_back
        conn = None

        try:
            conn = self._get_connection()

            if article_uris:
                # Fetch specific articles
                placeholders = ", ".join([f":uri_{i}" for i in range(len(article_uris))])
                params = {f"uri_{i}": uri for i, uri in enumerate(article_uris)}

                stmt = text(f"""
                    SELECT uri, embedding
                    FROM articles
                    WHERE uri IN ({placeholders})
                    AND embedding IS NOT NULL
                    ORDER BY publication_date DESC
                """)
            else:
                # Fetch recent articles
                # publication_date is TEXT, so cast to date for comparison
                filter_clause = """
                    WHERE embedding IS NOT NULL
                    AND publication_date::date >= CURRENT_DATE - :days_back
                """
                params = {"days_back": days}

                if topic_filter:
                    filter_clause += " AND topic = :topic"
                    params["topic"] = topic_filter

                stmt = text(f"""
                    SELECT uri, embedding
                    FROM articles
                    {filter_clause}
                    ORDER BY publication_date DESC
                    LIMIT 5000
                """)

            result = conn.execute(stmt, params)

            uris = []
            embeddings = []

            for row in result.mappings():
                uris.append(row["uri"])
                # Parse embedding string to numpy array
                emb_str = str(row["embedding"])
                # Remove brackets and parse
                emb_values = emb_str.strip("[]").split(",")
                embedding = np.array([float(v) for v in emb_values])
                embeddings.append(embedding)

            if embeddings:
                embedding_matrix = np.vstack(embeddings)
                logger.info(f"Fetched {len(uris)} embeddings with shape {embedding_matrix.shape}")
                return uris, embedding_matrix
            else:
                return [], np.array([])

        except Exception as exc:
            logger.error(f"Error fetching embeddings: {exc}")
            return [], np.array([])
        finally:
            if conn:
                conn.close()

    def compute_distance_matrix(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Compute pairwise cosine distance matrix.
        """
        if len(embeddings) == 0:
            return np.array([])

        # Compute cosine distances
        distances = cosine_distances(embeddings)

        # Ensure symmetric and non-negative
        distances = (distances + distances.T) / 2
        np.fill_diagonal(distances, 0)

        return distances

    def _calculate_cluster_metrics(
        self,
        cluster_embeddings: np.ndarray,
        distance_matrix: np.ndarray,
        cluster_indices: List[int]
    ) -> Tuple[np.ndarray, float, float]:
        """
        Calculate centroid and distance metrics for a cluster.
        """
        # Calculate centroid (mean of embeddings)
        centroid = np.mean(cluster_embeddings, axis=0)

        # Calculate average internal distance
        if len(cluster_indices) > 1:
            cluster_distances = distance_matrix[np.ix_(cluster_indices, cluster_indices)]
            # Upper triangle excluding diagonal
            upper_triangle = cluster_distances[np.triu_indices_from(cluster_distances, k=1)]
            avg_distance = float(np.mean(upper_triangle)) if len(upper_triangle) > 0 else 0.0

            # Cluster radius (max distance from centroid)
            centroid_distances = cosine_distances([centroid], cluster_embeddings)[0]
            radius = float(np.max(centroid_distances))
        else:
            avg_distance = 0.0
            radius = 0.0

        return centroid, avg_distance, radius

    def detect_clusters(
        self,
        topic_filter: Optional[str] = None,
        days_back: Optional[int] = None,
        article_uris: Optional[List[str]] = None
    ) -> ClusterResult:
        """
        Detect clusters in article embeddings using HDBSCAN.
        """
        # Fetch embeddings
        uris, embeddings = self.fetch_embeddings(topic_filter, days_back, article_uris)

        if len(uris) < self.config.min_cluster_size:
            logger.warning(f"Not enough articles ({len(uris)}) for clustering")
            return ClusterResult(
                clusters=[],
                outliers=uris,
                total_articles=len(uris),
                detection_date=date.today()
            )

        # Compute distance matrix
        distance_matrix = self.compute_distance_matrix(embeddings)

        if not HDBSCAN_AVAILABLE:
            # Fallback to simple distance-based clustering
            return self._fallback_clustering(uris, embeddings, distance_matrix)

        # Run HDBSCAN
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            min_samples=self.config.min_samples,
            cluster_selection_epsilon=self.config.cluster_selection_epsilon,
            metric='precomputed'
        )

        try:
            labels = clusterer.fit_predict(distance_matrix)
        except Exception as exc:
            logger.error(f"HDBSCAN clustering failed: {exc}")
            return self._fallback_clustering(uris, embeddings, distance_matrix)

        # Process clusters
        clusters = []
        outliers = []

        unique_labels = set(labels)
        unique_labels.discard(-1)  # Remove noise label

        for label in unique_labels:
            cluster_indices = [i for i, l in enumerate(labels) if l == label]
            cluster_uris = [uris[i] for i in cluster_indices]
            cluster_embeddings = embeddings[cluster_indices]

            # Calculate cluster metrics
            centroid, avg_distance, radius = self._calculate_cluster_metrics(
                cluster_embeddings, distance_matrix, cluster_indices
            )

            # Convert centroid to string for storage
            centroid_str = "[" + ",".join([str(v) for v in centroid]) + "]"

            cluster = ArticleCluster(
                cluster_id=f"cluster_{label}_{date.today().isoformat()}",
                article_uris=cluster_uris,
                centroid=centroid,
                centroid_str=centroid_str,
                avg_internal_distance=avg_distance,
                cluster_radius=radius
            )
            clusters.append(cluster)

        # Identify outliers
        outlier_indices = [i for i, l in enumerate(labels) if l == -1]
        outliers = [uris[i] for i in outlier_indices]

        result = ClusterResult(
            clusters=clusters,
            outliers=outliers,
            total_articles=len(uris),
            detection_date=date.today()
        )

        logger.info(
            f"Detected {len(clusters)} clusters and {len(outliers)} outliers "
            f"from {len(uris)} articles"
        )

        return result

    def _fallback_clustering(
        self,
        uris: List[str],
        embeddings: np.ndarray,
        distance_matrix: np.ndarray
    ) -> ClusterResult:
        """
        Simple distance-based clustering fallback when HDBSCAN is not available.

        Uses greedy clustering with a tight threshold for semantic coherence.
        """
        threshold = 0.15  # Tighter threshold for better coherence (cosine dist)
        min_cluster_size = self.config.min_cluster_size
        assigned = set()
        clusters = []

        # Sort articles by average distance to find natural cluster seeds
        avg_distances = np.mean(distance_matrix, axis=1)
        seed_order = np.argsort(avg_distances)  # Start with most central articles

        for seed_idx in seed_order:
            uri = uris[seed_idx]
            if uri in assigned:
                continue

            # Find all articles within threshold of this seed
            nearby_indices = []
            nearby_uris = []

            for j, other_uri in enumerate(uris):
                if other_uri in assigned:
                    continue
                if distance_matrix[seed_idx, j] < threshold:
                    nearby_indices.append(j)
                    nearby_uris.append(other_uri)

            # Only create cluster if we have enough tightly related articles
            if len(nearby_uris) >= min_cluster_size:
                # Verify cluster coherence - check avg internal distance
                if len(nearby_indices) > 1:
                    cluster_dist = distance_matrix[np.ix_(nearby_indices, nearby_indices)]
                    avg_internal = np.mean(cluster_dist[np.triu_indices_from(cluster_dist, k=1)])
                    # Skip if cluster isn't coherent
                    if avg_internal > threshold * 1.5:
                        continue

                for u in nearby_uris:
                    assigned.add(u)

                cluster_embeddings = embeddings[nearby_indices]
                centroid, avg_distance, radius = self._calculate_cluster_metrics(
                    cluster_embeddings, distance_matrix, nearby_indices
                )
                centroid_str = "[" + ",".join([str(v) for v in centroid]) + "]"

                cluster = ArticleCluster(
                    cluster_id=f"cluster_{len(clusters)}_{date.today().isoformat()}",
                    article_uris=nearby_uris,
                    centroid=centroid,
                    centroid_str=centroid_str,
                    avg_internal_distance=avg_distance,
                    cluster_radius=radius
                )
                clusters.append(cluster)

        # Remaining unassigned are outliers
        outliers = [uri for uri in uris if uri not in assigned]

        logger.info(f"Fallback clustering: {len(clusters)} clusters, {len(outliers)} outliers (threshold={threshold})")

        return ClusterResult(
            clusters=clusters,
            outliers=outliers,
            total_articles=len(uris),
            detection_date=date.today()
        )

    def identify_proto_clusters(
        self,
        outlier_uris: List[str],
        min_size: int = 3
    ) -> List[ArticleCluster]:
        """
        Identify potential proto-clusters from outliers.

        Proto-clusters are small groups of outliers that are close together
        and might be forming a new cluster.
        """
        if len(outlier_uris) < min_size:
            return []

        # Fetch embeddings for outliers
        uris, embeddings = self.fetch_embeddings(article_uris=outlier_uris)

        if len(uris) < min_size:
            return []

        # Compute distances
        distance_matrix = self.compute_distance_matrix(embeddings)

        # Find small groups using lower threshold
        threshold = 0.25  # Tighter threshold for proto-clusters
        assigned = set()
        proto_clusters = []

        for i, uri in enumerate(uris):
            if uri in assigned:
                continue

            # Find nearby outliers
            nearby_indices = [i]
            nearby_uris = [uri]

            for j, other_uri in enumerate(uris):
                if other_uri in assigned or j == i:
                    continue
                if distance_matrix[i, j] < threshold:
                    nearby_indices.append(j)
                    nearby_uris.append(other_uri)

            if len(nearby_uris) >= min_size:
                # This is a proto-cluster
                for u in nearby_uris:
                    assigned.add(u)

                cluster_embeddings = embeddings[nearby_indices]
                centroid = np.mean(cluster_embeddings, axis=0)
                centroid_str = "[" + ",".join([str(v) for v in centroid]) + "]"

                proto = ArticleCluster(
                    cluster_id=f"proto_{len(proto_clusters)}_{date.today().isoformat()}",
                    article_uris=nearby_uris,
                    centroid=centroid,
                    centroid_str=centroid_str,
                    avg_internal_distance=float(np.mean(distance_matrix[np.ix_(nearby_indices, nearby_indices)])),
                    cluster_radius=0.0
                )
                proto_clusters.append(proto)

        logger.info(f"Found {len(proto_clusters)} proto-clusters from {len(outlier_uris)} outliers")
        return proto_clusters

    def get_cluster_centroids(
        self,
        clusters: List[ArticleCluster]
    ) -> List[Tuple[str, str]]:
        """
        Extract cluster centroids as (cluster_id, embedding_string) tuples.
        Useful for novelty scoring against known clusters.
        """
        return [
            (c.cluster_id, c.centroid_str)
            for c in clusters
            if c.centroid_str
        ]
