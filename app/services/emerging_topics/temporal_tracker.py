"""
Temporal Tracker Service

Tracks cluster evolution over time to detect emerging patterns.
Compares cluster snapshots across time periods to identify:
- New clusters (topics that didn't exist before)
- Splitting clusters (emerging subtopics)
- Accelerating clusters (growing topics)
- Decelerating clusters (fading topics)
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from sqlalchemy import text

from app.database import get_database_instance
from .cluster_detector import ArticleCluster, ClusterResult

logger = logging.getLogger(__name__)


@dataclass
class TemporalConfig:
    """Configuration for temporal tracking."""
    lookback_days: int = 7
    acceleration_threshold: float = 0.20  # 20% growth rate increase
    split_distance_threshold: float = 0.4  # Centroid drift indicating split
    new_cluster_min_age_days: int = 2  # Min days for "new cluster" status
    composition_similarity_threshold: float = 0.3  # Jaccard similarity for matching


@dataclass
class ClusterChange:
    """Represents a detected change in cluster structure."""
    change_type: str  # 'new_cluster', 'splitting', 'accelerating', 'decelerating', 'merging'
    cluster_id: str
    previous_cluster_id: Optional[str] = None
    parent_cluster_ids: Optional[List[str]] = None

    # Metrics
    article_count: int = 0
    previous_article_count: int = 0
    growth_rate: float = 0.0
    velocity: str = "stable"  # 'accelerating', 'stable', 'decelerating'
    centroid_drift: float = 0.0
    composition_similarity: float = 0.0

    # Article URIs
    article_uris: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_type": self.change_type,
            "cluster_id": self.cluster_id,
            "previous_cluster_id": self.previous_cluster_id,
            "parent_cluster_ids": self.parent_cluster_ids,
            "article_count": self.article_count,
            "previous_article_count": self.previous_article_count,
            "growth_rate": round(self.growth_rate, 2),
            "velocity": self.velocity,
            "centroid_drift": round(self.centroid_drift, 4),
            "composition_similarity": round(self.composition_similarity, 4),
        }


class TemporalTracker:
    """
    Tracks cluster evolution and detects emerging patterns.
    """

    def __init__(self, config: Optional[TemporalConfig] = None):
        self.config = config or TemporalConfig()

    def _get_connection(self):
        """Get database connection."""
        db = get_database_instance()
        return db._temp_get_connection()

    def save_snapshot(
        self,
        cluster_result: ClusterResult,
        topic_filter: Optional[str] = None
    ) -> int:
        """
        Save cluster snapshot to the database.

        Returns number of snapshots saved.
        """
        if not cluster_result.clusters:
            return 0

        conn = None
        saved_count = 0

        try:
            conn = self._get_connection()

            for cluster in cluster_result.clusters:
                stmt = text("""
                    INSERT INTO cluster_snapshots (
                        snapshot_date, cluster_id, article_count,
                        centroid_embedding, avg_internal_distance, cluster_radius,
                        article_uris, topic_filter, cluster_label
                    ) VALUES (
                        :snapshot_date, :cluster_id, :article_count,
                        CAST(:centroid AS vector), :avg_distance, :radius,
                        :article_uris, :topic_filter, NULL
                    )
                    ON CONFLICT (snapshot_date, cluster_id, topic_filter)
                    DO UPDATE SET
                        article_count = EXCLUDED.article_count,
                        centroid_embedding = EXCLUDED.centroid_embedding,
                        avg_internal_distance = EXCLUDED.avg_internal_distance,
                        cluster_radius = EXCLUDED.cluster_radius,
                        article_uris = EXCLUDED.article_uris
                """)

                conn.execute(stmt, {
                    "snapshot_date": cluster_result.detection_date,
                    "cluster_id": cluster.cluster_id,
                    "article_count": len(cluster.article_uris),
                    "centroid": cluster.centroid_str,
                    "avg_distance": cluster.avg_internal_distance,
                    "radius": cluster.cluster_radius,
                    "article_uris": cluster.article_uris,
                    "topic_filter": topic_filter,
                })
                saved_count += 1

            conn.commit()
            logger.info(f"Saved {saved_count} cluster snapshots for {cluster_result.detection_date}")
            return saved_count

        except Exception as exc:
            logger.error(f"Error saving cluster snapshots: {exc}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()

    def get_snapshots(
        self,
        snapshot_date: date,
        topic_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get cluster snapshots for a specific date.
        """
        conn = None
        try:
            conn = self._get_connection()

            filter_clause = "WHERE snapshot_date = :date"
            params = {"date": snapshot_date}

            if topic_filter:
                filter_clause += " AND topic_filter = :topic"
                params["topic"] = topic_filter
            else:
                filter_clause += " AND topic_filter IS NULL"

            stmt = text(f"""
                SELECT
                    id, snapshot_date, cluster_id, article_count,
                    avg_internal_distance, cluster_radius,
                    centroid_drift, size_change, composition_similarity,
                    is_new, is_splitting, is_merging,
                    article_uris, cluster_label
                FROM cluster_snapshots
                {filter_clause}
            """)

            result = conn.execute(stmt, params)
            return [dict(row) for row in result.mappings()]

        except Exception as exc:
            logger.error(f"Error getting snapshots: {exc}")
            return []
        finally:
            if conn:
                conn.close()

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _calculate_centroid_drift(
        self,
        centroid1_str: str,
        centroid2_str: str
    ) -> float:
        """Calculate cosine distance between two centroid vectors."""
        conn = None
        try:
            conn = self._get_connection()

            stmt = text("""
                SELECT (CAST(:emb1 AS vector) <=> CAST(:emb2 AS vector)) as distance
            """)

            result = conn.execute(stmt, {
                "emb1": centroid1_str,
                "emb2": centroid2_str
            }).fetchone()

            return float(result[0]) if result else 0.0

        except Exception as exc:
            logger.error(f"Error calculating centroid drift: {exc}")
            return 0.0
        finally:
            if conn:
                conn.close()

    def compare_snapshots(
        self,
        current_clusters: List[ArticleCluster],
        previous_date: date,
        topic_filter: Optional[str] = None
    ) -> List[ClusterChange]:
        """
        Compare current clusters with previous snapshot to detect changes.
        """
        # Get previous snapshots
        previous_snapshots = self.get_snapshots(previous_date, topic_filter)

        if not previous_snapshots:
            # All clusters are new
            changes = []
            for cluster in current_clusters:
                change = ClusterChange(
                    change_type="new_cluster",
                    cluster_id=cluster.cluster_id,
                    article_count=len(cluster.article_uris),
                    article_uris=cluster.article_uris,
                    growth_rate=1.0,
                    velocity="accelerating",
                )
                changes.append(change)
            return changes

        changes = []

        # Build lookup for previous clusters
        prev_by_id = {s["cluster_id"]: s for s in previous_snapshots}
        prev_articles_by_id = {
            s["cluster_id"]: set(s["article_uris"]) if s["article_uris"] else set()
            for s in previous_snapshots
        }

        matched_previous = set()

        for cluster in current_clusters:
            current_articles = set(cluster.article_uris)

            # Try to match with previous cluster by article overlap
            best_match = None
            best_similarity = 0.0

            for prev_id, prev_articles in prev_articles_by_id.items():
                similarity = self._jaccard_similarity(current_articles, prev_articles)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = prev_id

            if best_match and best_similarity >= self.config.composition_similarity_threshold:
                # Matched cluster - check for changes
                matched_previous.add(best_match)
                prev_snapshot = prev_by_id[best_match]

                prev_count = prev_snapshot["article_count"] or 0
                current_count = len(cluster.article_uris)

                # Calculate growth rate
                if prev_count > 0:
                    growth_rate = (current_count - prev_count) / prev_count
                else:
                    growth_rate = 1.0 if current_count > 0 else 0.0

                # Determine velocity
                if growth_rate >= self.config.acceleration_threshold:
                    velocity = "accelerating"
                    change_type = "accelerating"
                elif growth_rate <= -self.config.acceleration_threshold:
                    velocity = "decelerating"
                    change_type = "decelerating"
                else:
                    velocity = "stable"
                    change_type = None  # No significant change

                # Check for splitting (large centroid drift despite match)
                centroid_drift = 0.0
                # (Would need to fetch previous centroid from DB for this)

                if change_type:
                    change = ClusterChange(
                        change_type=change_type,
                        cluster_id=cluster.cluster_id,
                        previous_cluster_id=best_match,
                        article_count=current_count,
                        previous_article_count=prev_count,
                        growth_rate=growth_rate,
                        velocity=velocity,
                        centroid_drift=centroid_drift,
                        composition_similarity=best_similarity,
                        article_uris=cluster.article_uris,
                    )
                    changes.append(change)

            else:
                # No match found - this is a new cluster
                change = ClusterChange(
                    change_type="new_cluster",
                    cluster_id=cluster.cluster_id,
                    article_count=len(cluster.article_uris),
                    article_uris=cluster.article_uris,
                    growth_rate=1.0,
                    velocity="accelerating",
                )
                changes.append(change)

        # Check for splits - clusters that split from existing ones
        # (Articles from one previous cluster now in multiple current clusters)
        for prev_id in prev_articles_by_id:
            if prev_id in matched_previous:
                continue

            prev_articles = prev_articles_by_id[prev_id]

            # Check if articles went to multiple clusters
            destination_clusters = []
            for cluster in current_clusters:
                overlap = len(prev_articles & set(cluster.article_uris))
                if overlap > 0:
                    destination_clusters.append((cluster.cluster_id, overlap))

            if len(destination_clusters) > 1:
                # Split detected
                for dest_id, overlap in destination_clusters:
                    change = ClusterChange(
                        change_type="splitting",
                        cluster_id=dest_id,
                        parent_cluster_ids=[prev_id],
                        article_count=overlap,
                        velocity="stable",
                    )
                    changes.append(change)

        logger.info(f"Detected {len(changes)} cluster changes")
        return changes

    def detect_new_clusters(
        self,
        current_clusters: List[ArticleCluster],
        previous_date: date,
        topic_filter: Optional[str] = None
    ) -> List[str]:
        """
        Identify clusters that are genuinely new (not matches to previous).
        """
        changes = self.compare_snapshots(current_clusters, previous_date, topic_filter)
        return [c.cluster_id for c in changes if c.change_type == "new_cluster"]

    def detect_accelerating_clusters(
        self,
        current_clusters: List[ArticleCluster],
        previous_date: date,
        topic_filter: Optional[str] = None
    ) -> List[ClusterChange]:
        """
        Identify clusters that are accelerating in growth.
        """
        changes = self.compare_snapshots(current_clusters, previous_date, topic_filter)
        return [c for c in changes if c.change_type == "accelerating"]

    def calculate_velocity_metrics(
        self,
        cluster_id: str,
        days: int = 7,
        topic_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate velocity metrics for a cluster over time.
        """
        conn = None
        try:
            conn = self._get_connection()

            filter_clause = """
                WHERE cluster_id = :cluster_id
                AND snapshot_date >= CURRENT_DATE - :days
            """
            params = {"cluster_id": cluster_id, "days": days}

            if topic_filter:
                filter_clause += " AND topic_filter = :topic"
                params["topic"] = topic_filter

            stmt = text(f"""
                SELECT snapshot_date, article_count
                FROM cluster_snapshots
                {filter_clause}
                ORDER BY snapshot_date ASC
            """)

            result = conn.execute(stmt, params)
            snapshots = list(result.mappings())

            if len(snapshots) < 2:
                return {"velocity": "unknown", "data_points": len(snapshots)}

            # Calculate daily growth
            first_count = snapshots[0]["article_count"] or 0
            last_count = snapshots[-1]["article_count"] or 0
            days_elapsed = (snapshots[-1]["snapshot_date"] - snapshots[0]["snapshot_date"]).days

            if days_elapsed > 0 and first_count > 0:
                total_growth = (last_count - first_count) / first_count
                daily_rate = total_growth / days_elapsed

                if daily_rate >= 0.05:  # 5% daily growth
                    velocity = "accelerating"
                elif daily_rate <= -0.05:
                    velocity = "decelerating"
                else:
                    velocity = "stable"
            else:
                velocity = "stable"
                total_growth = 0.0
                daily_rate = 0.0

            return {
                "velocity": velocity,
                "data_points": len(snapshots),
                "first_count": first_count,
                "last_count": last_count,
                "days_elapsed": days_elapsed,
                "total_growth": round(total_growth, 4),
                "daily_rate": round(daily_rate, 4),
            }

        except Exception as exc:
            logger.error(f"Error calculating velocity: {exc}")
            return {"velocity": "unknown", "error": str(exc)}
        finally:
            if conn:
                conn.close()

    def update_snapshot_evolution_metrics(
        self,
        current_date: date,
        previous_date: date,
        topic_filter: Optional[str] = None
    ) -> int:
        """
        Update evolution metrics (drift, size change, etc.) on current snapshots.
        """
        conn = None
        updated = 0

        try:
            conn = self._get_connection()

            # Get current and previous snapshots
            current_snapshots = self.get_snapshots(current_date, topic_filter)
            previous_snapshots = self.get_snapshots(previous_date, topic_filter)

            if not previous_snapshots:
                return 0

            prev_by_id = {s["cluster_id"]: s for s in previous_snapshots}

            for current in current_snapshots:
                cluster_id = current["cluster_id"]

                # Try to find matching previous cluster
                prev = None
                best_match_id = None

                # Simple ID-based matching first
                if cluster_id in prev_by_id:
                    prev = prev_by_id[cluster_id]
                    best_match_id = cluster_id

                if prev:
                    size_change = (current["article_count"] or 0) - (prev["article_count"] or 0)

                    # Update the snapshot
                    stmt = text("""
                        UPDATE cluster_snapshots
                        SET size_change = :size_change,
                            is_new = FALSE
                        WHERE id = :id
                    """)

                    conn.execute(stmt, {
                        "id": current["id"],
                        "size_change": size_change,
                    })
                    updated += 1
                else:
                    # Mark as new
                    stmt = text("""
                        UPDATE cluster_snapshots
                        SET is_new = TRUE
                        WHERE id = :id
                    """)
                    conn.execute(stmt, {"id": current["id"]})
                    updated += 1

            conn.commit()
            logger.info(f"Updated evolution metrics for {updated} snapshots")
            return updated

        except Exception as exc:
            logger.error(f"Error updating evolution metrics: {exc}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()
