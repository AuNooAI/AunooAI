"""
Novelty Scorer Service

Calculates novelty scores for articles based on their position in embedding space.
Uses pgvector for efficient distance calculations.

Novelty is computed from three components:
1. KNN Distance: Average distance to k-nearest neighbors (higher = more isolated)
2. Local Density: Number of articles within a radius (lower = sparser region)
3. Centroid Distance: Distance to nearest cluster centroid (higher = further from known topics)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import text

from app.database import get_database_instance

logger = logging.getLogger(__name__)


@dataclass
class NoveltyConfig:
    """Configuration for novelty scoring."""
    k_neighbors: int = 10
    density_radius: float = 0.3
    knn_weight: float = 0.40
    density_weight: float = 0.35
    centroid_weight: float = 0.25
    outlier_threshold: float = 75.0  # Score above which article is considered an outlier


@dataclass
class ArticleNoveltyScore:
    """Result of novelty score calculation for an article."""
    article_uri: str
    calculation_date: date

    # Component scores (0-100)
    knn_distance_score: float
    density_score: float
    centroid_distance_score: float
    composite_novelty_score: float

    # KNN details
    k_neighbors: int
    avg_knn_distance: float
    min_knn_distance: Optional[float] = None
    max_knn_distance: Optional[float] = None

    # Density details
    local_density: Optional[float] = None
    density_radius: Optional[float] = None

    # Cluster assignment
    nearest_cluster_id: Optional[str] = None
    distance_to_nearest_cluster: Optional[float] = None
    is_outlier: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_uri": self.article_uri,
            "calculation_date": str(self.calculation_date),
            "knn_distance_score": round(self.knn_distance_score, 2),
            "density_score": round(self.density_score, 2),
            "centroid_distance_score": round(self.centroid_distance_score, 2),
            "composite_novelty_score": round(self.composite_novelty_score, 2),
            "k_neighbors": self.k_neighbors,
            "avg_knn_distance": round(self.avg_knn_distance, 4) if self.avg_knn_distance else None,
            "local_density": self.local_density,
            "is_outlier": self.is_outlier,
            "nearest_cluster_id": self.nearest_cluster_id,
            "distance_to_nearest_cluster": round(self.distance_to_nearest_cluster, 4) if self.distance_to_nearest_cluster else None,
        }


class NoveltyScorer:
    """
    Calculates article novelty using pgvector distance queries.

    The novelty score indicates how "new" or "unusual" an article is
    relative to the existing corpus. Higher scores indicate more novel content.
    """

    def __init__(self, config: Optional[NoveltyConfig] = None):
        self.config = config or NoveltyConfig()
        self._corpus_stats: Optional[Dict[str, float]] = None

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def _calculate_corpus_stats(self, conn, topic_filter: Optional[str] = None) -> Dict[str, float]:
        """
        Calculate corpus-wide statistics for normalization.
        Returns average KNN distance and density for the corpus.
        """
        # Build filter clause
        filter_clause = "WHERE embedding IS NOT NULL"
        params = {}
        if topic_filter:
            filter_clause += " AND topic = :topic"
            params["topic"] = topic_filter

        # Sample corpus to get baseline statistics
        # Use a random sample of articles for efficiency
        stmt = text(f"""
            WITH sample_articles AS (
                SELECT uri, embedding
                FROM articles
                {filter_clause}
                ORDER BY RANDOM()
                LIMIT 100
            ),
            knn_distances AS (
                SELECT
                    s.uri,
                    knn.avg_knn_dist
                FROM sample_articles s
                CROSS JOIN LATERAL (
                    SELECT AVG(distance) as avg_knn_dist
                    FROM (
                        SELECT s.embedding <=> a.embedding as distance
                        FROM articles a
                        WHERE a.uri != s.uri
                        AND a.embedding IS NOT NULL
                        ORDER BY s.embedding <=> a.embedding
                        LIMIT :k
                    ) nearest_neighbors
                ) knn
            )
            SELECT
                AVG(avg_knn_dist) as corpus_avg_knn,
                STDDEV(avg_knn_dist) as corpus_std_knn,
                MAX(avg_knn_dist) as corpus_max_knn
            FROM knn_distances
            WHERE avg_knn_dist IS NOT NULL
        """)

        params["k"] = self.config.k_neighbors
        result = conn.execute(stmt, params).fetchone()

        if result and result[0]:
            return {
                "avg_knn_distance": float(result[0]),
                "std_knn_distance": float(result[1]) if result[1] else 0.1,
                "max_knn_distance": float(result[2]) if result[2] else 1.0,
            }

        # Fallback defaults
        return {
            "avg_knn_distance": 0.5,
            "std_knn_distance": 0.1,
            "max_knn_distance": 1.0,
        }

    def calculate_knn_scores(
        self,
        article_uris: List[str],
        topic_filter: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate KNN distance scores for a list of articles.

        Returns dict mapping URI to {avg_distance, min_distance, max_distance, score}
        """
        if not article_uris:
            return {}

        conn = None
        try:
            conn = self._get_connection()

            # Get corpus stats for normalization
            if self._corpus_stats is None:
                self._corpus_stats = self._calculate_corpus_stats(conn, topic_filter)

            results = {}

            # Process in batches for efficiency
            for uri in article_uris:
                # Get KNN distances for this article
                stmt = text("""
                    WITH article_embedding AS (
                        SELECT embedding FROM articles WHERE uri = :uri AND embedding IS NOT NULL
                    ),
                    neighbors AS (
                        SELECT
                            a.uri,
                            ae.embedding <=> a.embedding as distance
                        FROM articles a
                        CROSS JOIN article_embedding ae
                        WHERE a.uri != :uri
                        AND a.embedding IS NOT NULL
                        ORDER BY ae.embedding <=> a.embedding
                        LIMIT :k
                    )
                    SELECT
                        AVG(distance) as avg_dist,
                        MIN(distance) as min_dist,
                        MAX(distance) as max_dist
                    FROM neighbors
                """)

                result = conn.execute(stmt, {"uri": uri, "k": self.config.k_neighbors}).fetchone()

                if result and result[0] is not None:
                    avg_dist = float(result[0])
                    min_dist = float(result[1]) if result[1] else avg_dist
                    max_dist = float(result[2]) if result[2] else avg_dist

                    # Normalize score (0-100)
                    # Higher distance = higher novelty score
                    corpus_avg = self._corpus_stats["avg_knn_distance"]
                    corpus_std = self._corpus_stats["std_knn_distance"]

                    # Z-score normalization, clamped to 0-100
                    z_score = (avg_dist - corpus_avg) / corpus_std if corpus_std > 0 else 0
                    # Map z-score to 0-100 (z=0 -> 50, z=2 -> 100, z=-2 -> 0)
                    score = min(100, max(0, 50 + (z_score * 25)))

                    results[uri] = {
                        "avg_distance": avg_dist,
                        "min_distance": min_dist,
                        "max_distance": max_dist,
                        "score": score,
                    }
                else:
                    # No neighbors found - very novel
                    results[uri] = {
                        "avg_distance": 1.0,
                        "min_distance": 1.0,
                        "max_distance": 1.0,
                        "score": 100.0,
                    }

            return results

        except Exception as exc:
            logger.error(f"Error calculating KNN scores: {exc}")
            return {}
        finally:
            if conn:
                conn.close()

    def calculate_density_scores(
        self,
        article_uris: List[str],
        topic_filter: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate local density scores for a list of articles.

        Lower density = higher novelty (sparse region = less explored)
        """
        if not article_uris:
            return {}

        conn = None
        try:
            conn = self._get_connection()
            results = {}

            for uri in article_uris:
                # Count articles within radius
                stmt = text("""
                    SELECT COUNT(*) as density
                    FROM articles a
                    CROSS JOIN (SELECT embedding FROM articles WHERE uri = :uri) ref
                    WHERE a.uri != :uri
                    AND a.embedding IS NOT NULL
                    AND (ref.embedding <=> a.embedding) < :radius
                """)

                result = conn.execute(stmt, {
                    "uri": uri,
                    "radius": self.config.density_radius
                }).fetchone()

                local_density = int(result[0]) if result else 0

                # Convert to score (0-100)
                # Lower density = higher novelty
                # Use inverse: score = 100 / (1 + density)
                # This gives 100 for density=0, ~33 for density=2, ~10 for density=9
                score = 100.0 / (1 + local_density)

                results[uri] = {
                    "local_density": local_density,
                    "radius": self.config.density_radius,
                    "score": score,
                }

            return results

        except Exception as exc:
            logger.error(f"Error calculating density scores: {exc}")
            return {}
        finally:
            if conn:
                conn.close()

    def calculate_centroid_distances(
        self,
        article_uris: List[str],
        centroids: Optional[List[Tuple[str, str]]] = None  # List of (cluster_id, embedding_str)
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate distance to nearest cluster centroid.

        If no centroids provided, uses placeholder scoring based on
        distance to most similar article cluster (approximation).
        """
        if not article_uris:
            return {}

        conn = None
        try:
            conn = self._get_connection()
            results = {}

            if centroids:
                # Calculate actual centroid distances
                for uri in article_uris:
                    min_distance = float('inf')
                    nearest_cluster = None

                    # Get article embedding
                    stmt = text("SELECT embedding FROM articles WHERE uri = :uri")
                    result = conn.execute(stmt, {"uri": uri}).fetchone()
                    if not result or not result[0]:
                        continue

                    article_embedding = str(result[0])

                    for cluster_id, centroid_str in centroids:
                        # Calculate distance
                        dist_stmt = text("""
                            SELECT (CAST(:emb1 AS vector) <=> CAST(:emb2 AS vector)) as distance
                        """)
                        dist_result = conn.execute(dist_stmt, {
                            "emb1": article_embedding,
                            "emb2": centroid_str
                        }).fetchone()

                        if dist_result and dist_result[0] is not None:
                            distance = float(dist_result[0])
                            if distance < min_distance:
                                min_distance = distance
                                nearest_cluster = cluster_id

                    if min_distance < float('inf'):
                        # Normalize to 0-100 (distance of 0 = 0, distance of 1+ = 100)
                        score = min(100, min_distance * 100)
                        results[uri] = {
                            "nearest_cluster_id": nearest_cluster,
                            "distance": min_distance,
                            "score": score,
                        }
                    else:
                        results[uri] = {"score": 50.0}  # Default if no centroids match
            else:
                # No centroids provided - use default score
                for uri in article_uris:
                    results[uri] = {"score": 50.0}  # Neutral score

            return results

        except Exception as exc:
            logger.error(f"Error calculating centroid distances: {exc}")
            return {}
        finally:
            if conn:
                conn.close()

    def score_articles(
        self,
        article_uris: List[str],
        topic_filter: Optional[str] = None,
        centroids: Optional[List[Tuple[str, str]]] = None,
        calculation_date: Optional[date] = None
    ) -> List[ArticleNoveltyScore]:
        """
        Calculate complete novelty scores for a list of articles.

        Returns list of ArticleNoveltyScore objects with all component scores.
        """
        if not article_uris:
            return []

        calc_date = calculation_date or date.today()

        # Calculate all component scores
        knn_scores = self.calculate_knn_scores(article_uris, topic_filter)
        density_scores = self.calculate_density_scores(article_uris, topic_filter)
        centroid_scores = self.calculate_centroid_distances(article_uris, centroids)

        results = []
        for uri in article_uris:
            knn = knn_scores.get(uri, {"score": 50.0, "avg_distance": 0.5})
            density = density_scores.get(uri, {"score": 50.0, "local_density": 0})
            centroid = centroid_scores.get(uri, {"score": 50.0})

            # Calculate composite score
            composite = (
                self.config.knn_weight * knn["score"] +
                self.config.density_weight * density["score"] +
                self.config.centroid_weight * centroid["score"]
            )

            # Determine if outlier
            is_outlier = composite >= self.config.outlier_threshold

            score = ArticleNoveltyScore(
                article_uri=uri,
                calculation_date=calc_date,
                knn_distance_score=knn["score"],
                density_score=density["score"],
                centroid_distance_score=centroid["score"],
                composite_novelty_score=composite,
                k_neighbors=self.config.k_neighbors,
                avg_knn_distance=knn.get("avg_distance", 0.5),
                min_knn_distance=knn.get("min_distance"),
                max_knn_distance=knn.get("max_distance"),
                local_density=density.get("local_density"),
                density_radius=density.get("radius"),
                nearest_cluster_id=centroid.get("nearest_cluster_id"),
                distance_to_nearest_cluster=centroid.get("distance"),
                is_outlier=is_outlier,
            )
            results.append(score)

        logger.info(f"Calculated novelty scores for {len(results)} articles")
        return results

    def save_scores(self, scores: List[ArticleNoveltyScore]) -> int:
        """
        Save novelty scores to the database.

        Returns number of scores saved.
        """
        if not scores:
            return 0

        conn = None
        saved_count = 0

        try:
            conn = self._get_connection()

            for score in scores:
                # Upsert score
                stmt = text("""
                    INSERT INTO article_novelty_scores (
                        article_uri, calculation_date,
                        knn_distance_score, density_score, centroid_distance_score,
                        composite_novelty_score, k_neighbors, avg_knn_distance,
                        min_knn_distance, max_knn_distance, local_density,
                        density_radius, nearest_cluster_id, distance_to_nearest_cluster,
                        is_outlier
                    ) VALUES (
                        :uri, :calc_date,
                        :knn_score, :density_score, :centroid_score,
                        :composite, :k, :avg_knn,
                        :min_knn, :max_knn, :local_density,
                        :radius, :nearest_cluster, :cluster_distance,
                        :is_outlier
                    )
                    ON CONFLICT (article_uri, calculation_date)
                    DO UPDATE SET
                        knn_distance_score = EXCLUDED.knn_distance_score,
                        density_score = EXCLUDED.density_score,
                        centroid_distance_score = EXCLUDED.centroid_distance_score,
                        composite_novelty_score = EXCLUDED.composite_novelty_score,
                        is_outlier = EXCLUDED.is_outlier,
                        created_at = CURRENT_TIMESTAMP
                """)

                conn.execute(stmt, {
                    "uri": score.article_uri,
                    "calc_date": score.calculation_date,
                    "knn_score": score.knn_distance_score,
                    "density_score": score.density_score,
                    "centroid_score": score.centroid_distance_score,
                    "composite": score.composite_novelty_score,
                    "k": score.k_neighbors,
                    "avg_knn": score.avg_knn_distance,
                    "min_knn": score.min_knn_distance,
                    "max_knn": score.max_knn_distance,
                    "local_density": score.local_density,
                    "radius": score.density_radius,
                    "nearest_cluster": score.nearest_cluster_id,
                    "cluster_distance": score.distance_to_nearest_cluster,
                    "is_outlier": score.is_outlier,
                })
                saved_count += 1

            conn.commit()
            logger.info(f"Saved {saved_count} novelty scores to database")
            return saved_count

        except Exception as exc:
            logger.error(f"Error saving novelty scores: {exc}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()

    def get_high_novelty_articles(
        self,
        threshold: Optional[float] = None,
        days_back: int = 7,
        topic_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get articles with high novelty scores from the database.
        """
        threshold = threshold or self.config.outlier_threshold

        conn = None
        try:
            conn = self._get_connection()

            filter_clause = """
                WHERE ns.composite_novelty_score >= :threshold
                AND ns.calculation_date >= CURRENT_DATE - :days_back
            """
            params = {"threshold": threshold, "days_back": days_back, "limit": limit}

            if topic_filter:
                filter_clause += " AND a.topic = :topic"
                params["topic"] = topic_filter

            # DISTINCT ON keeps one row per article — its latest scoring run.
            # A plain join listed an article once per calculation_date, so a
            # frequently re-scored article filled the list with itself.
            stmt = text(f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (ns.article_uri)
                        ns.article_uri,
                        a.title,
                        ns.composite_novelty_score,
                        ns.knn_distance_score,
                        ns.density_score,
                        ns.centroid_distance_score,
                        ns.is_outlier,
                        ns.calculation_date,
                        a.publication_date,
                        a.topic
                    FROM article_novelty_scores ns
                    JOIN articles a ON a.uri = ns.article_uri
                    {filter_clause}
                    ORDER BY ns.article_uri, ns.calculation_date DESC, ns.id DESC
                ) latest
                ORDER BY composite_novelty_score DESC, article_uri
                LIMIT :limit
            """)

            result = conn.execute(stmt, params)

            articles = []
            for row in result.mappings():
                articles.append(dict(row))

            return articles

        except Exception as exc:
            logger.error(f"Error getting high novelty articles: {exc}")
            return []
        finally:
            if conn:
                conn.close()
