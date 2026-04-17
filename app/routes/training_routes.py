"""
Training Routes

API endpoints for the Adaptive Classification Training System.
Provides sample counts, training status, finetuning triggers, and run management.
"""

import logging
import os
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Model Latency Tracker (in-memory with rolling window)
# ============================================================================

class LatencyTracker:
    """Track model latency with rolling window for p50 calculation."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_samples: int = 100):
        if getattr(self, '_initialized', False):
            return
        self._max_samples = max_samples
        self._samples: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self._max_samples))
        self._initialized = True

    def record(self, model: str, latency_ms: float):
        """Record a latency measurement for a model."""
        if latency_ms and latency_ms > 0:
            self._samples[model].append(latency_ms)

    def get_p50(self, model: str) -> Optional[float]:
        """Get the p50 (median) latency for a model."""
        samples = list(self._samples[model])
        if not samples:
            return None
        sorted_samples = sorted(samples)
        return sorted_samples[len(sorted_samples) // 2]

    def get_stats(self) -> Dict[str, Dict]:
        """Get latency stats for all models."""
        return {
            model: {
                "p50": self.get_p50(model),
                "count": len(samples),
                "min": min(samples) if samples else None,
                "max": max(samples) if samples else None,
            }
            for model, samples in self._samples.items()
        }

    def clear(self, model: Optional[str] = None):
        """Clear latency stats for a model or all models."""
        if model:
            self._samples[model].clear()
        else:
            self._samples.clear()


def get_latency_tracker() -> LatencyTracker:
    """Get the singleton latency tracker."""
    return LatencyTracker()


# ============================================================================
# Confidence Stats Tracker (database-backed with 24-hour rolling window)
# ============================================================================

class ConfidenceStatsTracker:
    """
    Database-backed tracker for DeBERTa model confidence scores.
    Maintains a rolling 24-hour window of confidence readings per topic/field.
    Persists across service restarts.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._window_hours = 24

    def _get_connection(self):
        """Get a database connection."""
        from app.database import get_database_instance
        db = get_database_instance()
        return db._temp_get_connection()

    def record(self, topic: str, confidence_scores: Dict[str, float]):
        """
        Record confidence scores for a topic.

        Args:
            topic: The topic name
            confidence_scores: Dict of {field_name: confidence_score}
        """
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            for field, conf in confidence_scores.items():
                conn.execute(text("""
                    INSERT INTO enrichment_confidence_readings
                        (topic, field_name, confidence)
                    VALUES (:topic, :field, :confidence)
                """), {"topic": topic, "field": field, "confidence": conf})

            conn.commit()

            # Prune old readings periodically (every ~100 records)
            import random
            if random.random() < 0.01:
                self._prune_old_readings(conn)
                conn.commit()

        except Exception as e:
            logger.error(f"Error recording confidence: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def _prune_old_readings(self, conn=None):
        """Remove readings older than the window."""
        from sqlalchemy import text
        close_conn = False
        if conn is None:
            conn = self._get_connection()
            close_conn = True

        try:
            conn.execute(text("""
                DELETE FROM enrichment_confidence_readings
                WHERE recorded_at < NOW() - INTERVAL ':hours hours'
            """.replace(':hours', str(self._window_hours))))
            if close_conn:
                conn.commit()
        except Exception as e:
            logger.error(f"Error pruning old readings: {e}")
        finally:
            if close_conn and conn:
                conn.close()

    def get_stats(self, topic: Optional[str] = None) -> Dict:
        """
        Get confidence stats for topic(s).

        Returns dict with per-topic, per-field stats including:
        - avg_confidence: Average confidence over the window
        - min_confidence: Minimum confidence seen
        - max_confidence: Maximum confidence seen
        - reading_count: Number of readings
        - above_threshold_pct: Percentage of readings above 0.6 threshold
        """
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            # Get aggregated stats per topic/field
            query = """
                SELECT
                    topic,
                    field_name,
                    AVG(confidence) as avg_conf,
                    MIN(confidence) as min_conf,
                    MAX(confidence) as max_conf,
                    COUNT(*) as reading_count,
                    SUM(CASE WHEN confidence >= 0.6 THEN 1 ELSE 0 END) as above_threshold
                FROM enrichment_confidence_readings
                WHERE recorded_at > NOW() - INTERVAL '24 hours'
            """

            if topic:
                query += " AND topic = :topic"

            query += " GROUP BY topic, field_name ORDER BY topic, field_name"

            if topic:
                result = conn.execute(text(query), {"topic": topic})
            else:
                result = conn.execute(text(query))

            rows = result.fetchall()

            # Build result structure
            result_dict = {}
            for row in rows:
                t = row[0]
                field = row[1]
                avg_conf = row[2]
                min_conf = row[3]
                max_conf = row[4]
                count = row[5]
                above = row[6]

                if t not in result_dict:
                    result_dict[t] = {
                        "fields": {},
                        "overall_avg": 0,
                        "total_readings": 0,
                        "above_threshold_pct": 0,
                        "_all_confs_sum": 0,
                        "_all_count": 0,
                        "_above_total": 0,
                    }

                result_dict[t]["fields"][field] = {
                    "avg": round(avg_conf, 3) if avg_conf else 0,
                    "min": round(min_conf, 3) if min_conf else 0,
                    "max": round(max_conf, 3) if max_conf else 0,
                    "count": count,
                    "above_threshold_pct": round(above / count * 100, 1) if count else 0,
                }

                # Accumulate for overall stats
                result_dict[t]["_all_confs_sum"] += avg_conf * count if avg_conf else 0
                result_dict[t]["_all_count"] += count
                result_dict[t]["_above_total"] += above

            # Calculate overall stats per topic
            for t in result_dict:
                total = result_dict[t]["_all_count"]
                if total > 0:
                    result_dict[t]["overall_avg"] = round(result_dict[t]["_all_confs_sum"] / total, 3)
                    result_dict[t]["total_readings"] = total
                    result_dict[t]["above_threshold_pct"] = round(result_dict[t]["_above_total"] / total * 100, 1)

                # Remove internal accumulators
                del result_dict[t]["_all_confs_sum"]
                del result_dict[t]["_all_count"]
                del result_dict[t]["_above_total"]

            return result_dict

        except Exception as e:
            logger.error(f"Error getting confidence stats: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def clear(self, topic: Optional[str] = None):
        """Clear stats for a topic or all topics."""
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            if topic:
                conn.execute(text(
                    "DELETE FROM enrichment_confidence_readings WHERE topic = :topic"
                ), {"topic": topic})
            else:
                conn.execute(text("DELETE FROM enrichment_confidence_readings"))

            conn.commit()
        except Exception as e:
            logger.error(f"Error clearing confidence stats: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


def get_confidence_tracker() -> ConfidenceStatsTracker:
    """Get the singleton confidence tracker."""
    return ConfidenceStatsTracker()


# ============================================================================
# Relevance Confidence Stats Tracker (database-backed with 24-hour rolling window)
# ============================================================================

class RelevanceConfidenceTracker:
    """
    Database-backed tracker for relevance scoring confidence.
    Tracks hybrid score, classifier score, and embedding score per topic.
    Persists across service restarts.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._window_hours = 24

    def _get_connection(self):
        """Get a database connection."""
        from app.database import get_database_instance
        db = get_database_instance()
        return db._temp_get_connection()

    def record(self, topic: str, score: float, classifier_score: float = None,
               embedding_score: float = None, method: str = "hybrid", relevant: bool = None):
        """
        Record a relevance score for a topic.

        Args:
            topic: The topic name
            score: Combined relevance score (0-1)
            classifier_score: DeBERTa classifier score (optional)
            embedding_score: Embedding similarity score (optional)
            method: Scoring method used (hybrid, classifier_only, embedding_only, llm)
            relevant: Final relevance decision
        """
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            conn.execute(text("""
                INSERT INTO relevance_confidence_readings
                    (topic, score, classifier_score, embedding_score, method, relevant)
                VALUES (:topic, :score, :classifier_score, :embedding_score, :method, :relevant)
            """), {
                "topic": topic,
                "score": score,
                "classifier_score": classifier_score,
                "embedding_score": embedding_score,
                "method": method,
                "relevant": relevant
            })

            conn.commit()

            # Prune old readings periodically (every ~100 records)
            import random
            if random.random() < 0.01:
                self._prune_old_readings(conn)
                conn.commit()

        except Exception as e:
            logger.error(f"Error recording relevance confidence: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def _prune_old_readings(self, conn=None):
        """Remove readings older than the window."""
        from sqlalchemy import text
        close_conn = False
        if conn is None:
            conn = self._get_connection()
            close_conn = True

        try:
            conn.execute(text("""
                DELETE FROM relevance_confidence_readings
                WHERE recorded_at < NOW() - INTERVAL ':hours hours'
            """.replace(':hours', str(self._window_hours))))
            if close_conn:
                conn.commit()
        except Exception as e:
            logger.error(f"Error pruning old relevance readings: {e}")
        finally:
            if close_conn and conn:
                conn.close()

    def get_stats(self, topic: Optional[str] = None) -> Dict:
        """
        Get relevance confidence stats for topic(s).

        Returns dict with per-topic stats including:
        - avg_score: Average relevance score
        - avg_classifier: Average classifier score
        - avg_embedding: Average embedding score
        - relevant_pct: Percentage marked as relevant
        - method_breakdown: Count of each scoring method used
        """
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            # Get aggregated stats per topic
            query = """
                SELECT
                    topic,
                    COUNT(*) as total,
                    AVG(score) as avg_score,
                    MIN(score) as min_score,
                    MAX(score) as max_score,
                    AVG(classifier_score) as avg_classifier,
                    AVG(embedding_score) as avg_embedding,
                    SUM(CASE WHEN relevant = true THEN 1 ELSE 0 END) as relevant_count,
                    SUM(CASE WHEN relevant IS NOT NULL THEN 1 ELSE 0 END) as relevant_total,
                    SUM(CASE WHEN score < 0.35 OR score > 0.65 THEN 1 ELSE 0 END) as high_conf
                FROM relevance_confidence_readings
                WHERE recorded_at > NOW() - INTERVAL '24 hours'
            """

            if topic:
                query += " AND topic = :topic"

            query += " GROUP BY topic ORDER BY topic"

            if topic:
                result = conn.execute(text(query), {"topic": topic})
            else:
                result = conn.execute(text(query))

            rows = result.fetchall()

            # Get method breakdown separately
            method_query = """
                SELECT topic, method, COUNT(*) as count
                FROM relevance_confidence_readings
                WHERE recorded_at > NOW() - INTERVAL '24 hours'
            """
            if topic:
                method_query += " AND topic = :topic"
            method_query += " GROUP BY topic, method"

            if topic:
                method_result = conn.execute(text(method_query), {"topic": topic})
            else:
                method_result = conn.execute(text(method_query))

            method_rows = method_result.fetchall()

            # Build method breakdown dict
            method_breakdown = {}
            for row in method_rows:
                t = row[0]
                m = row[1]
                c = row[2]
                if t not in method_breakdown:
                    method_breakdown[t] = {}
                method_breakdown[t][m] = c

            # Build result structure
            result_dict = {}
            for row in rows:
                t = row[0]
                total = row[1]
                avg_score = row[2]
                min_score = row[3]
                max_score = row[4]
                avg_classifier = row[5]
                avg_embedding = row[6]
                relevant_count = row[7]
                relevant_total = row[8]
                high_conf = row[9]

                result_dict[t] = {
                    "total_readings": total,
                    "avg_score": round(avg_score, 3) if avg_score else 0,
                    "min_score": round(min_score, 3) if min_score else 0,
                    "max_score": round(max_score, 3) if max_score else 0,
                    "avg_classifier": round(avg_classifier, 3) if avg_classifier else None,
                    "avg_embedding": round(avg_embedding, 3) if avg_embedding else None,
                    "relevant_pct": round(relevant_count / relevant_total * 100, 1) if relevant_total else 0,
                    "method_breakdown": method_breakdown.get(t, {}),
                    "high_confidence_pct": round(high_conf / total * 100, 1) if total else 0,
                }

            return result_dict

        except Exception as e:
            logger.error(f"Error getting relevance confidence stats: {e}")
            return {}
        finally:
            if conn:
                conn.close()

    def clear(self, topic: Optional[str] = None):
        """Clear stats for a topic or all topics."""
        conn = None
        try:
            from sqlalchemy import text
            conn = self._get_connection()

            if topic:
                conn.execute(text(
                    "DELETE FROM relevance_confidence_readings WHERE topic = :topic"
                ), {"topic": topic})
            else:
                conn.execute(text("DELETE FROM relevance_confidence_readings"))

            conn.commit()
        except Exception as e:
            logger.error(f"Error clearing relevance confidence stats: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


def get_relevance_confidence_tracker() -> RelevanceConfidenceTracker:
    """Get the singleton relevance confidence tracker."""
    return RelevanceConfidenceTracker()

router = APIRouter(prefix="/api/training", tags=["Training"])


# Request/Response Models

class TopicFieldStatus(BaseModel):
    """Status for a single field within a topic."""
    field_name: str
    sample_count: int
    status: str  # 'red', 'yellow', 'green'
    threshold_green: int
    threshold_yellow: int


class TopicTrainingStatus(BaseModel):
    """Training status for a topic."""
    topic: str
    article_count: int
    total_samples: int
    field_counts: dict
    field_readiness: dict
    overall_status: str  # 'ready', 'partial', 'marginal', 'not_ready'
    latest_run: Optional[dict] = None


class FieldDistribution(BaseModel):
    """Distribution of values for a field."""
    topic: str
    field_name: str
    total_samples: int
    unique_values: int
    distribution: list
    min_per_class_met: bool


class TrainingReadiness(BaseModel):
    """Overall training readiness."""
    ready: bool
    total_samples: int
    min_required: int
    topics_count: int
    ready_topics_count: int
    ready_topics: List[str]
    green_fields_count: int


class TriggerFinetuneRequest(BaseModel):
    """Request to trigger finetuning."""
    topics: Optional[List[str]] = Field(default=None, description="Topics to include (default: all ready)")
    fields: Optional[List[str]] = Field(default=None, description="Fields to train (default: all)")


class TriggerFinetuneResponse(BaseModel):
    """Response from triggering finetuning."""
    run_id: str
    status: str
    topics_included: List[str]
    sample_count: int


class TrainingRun(BaseModel):
    """Training run details."""
    run_id: str
    status: str
    topics_included: Optional[list]
    fields_included: Optional[list]
    sample_count: Optional[int]
    metrics: Optional[dict]
    started_at: Optional[str]
    completed_at: Optional[str]
    created_at: Optional[str]
    error_message: Optional[str]


class RoutingStatus(BaseModel):
    """Routing status for a topic."""
    topic: str
    fields: dict
    deberta_available: bool
    qwen_available: bool


# Lazy load services
def get_bootstrap_service():
    from app.services.training_bootstrap_service import get_training_bootstrap_service
    return get_training_bootstrap_service()


def get_finetuning_service():
    from app.services.finetuning_service import get_finetuning_service
    return get_finetuning_service()


def get_hybrid_enrichment_service():
    from app.services.hybrid_enrichment_service import get_hybrid_enrichment_service
    return get_hybrid_enrichment_service()


# Endpoints

@router.get("/sample-counts")
async def get_sample_counts(topic: Optional[str] = Query(default=None)):
    """
    Get sample counts per topic per field.

    Args:
        topic: Optional topic to filter by
    """
    try:
        service = get_bootstrap_service()
        counts = await service.get_sample_counts(topic)
        return {
            "counts": counts,
            "thresholds": service.get_thresholds(),
        }
    except Exception as e:
        logger.error(f"Error getting sample counts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics-status", response_model=List[TopicTrainingStatus])
async def get_topics_status():
    """
    Get training status for all topics.

    Returns list of topics with sample counts, field readiness, overall status,
    and the latest training run that included each topic.
    """
    try:
        service = get_bootstrap_service()
        status = await service.get_all_topics_status()

        # Enrich with latest training run per topic
        conn = None
        try:
            from app.database import get_database_instance
            from sqlalchemy import text
            db = get_database_instance()
            conn = db._temp_get_connection()

            result = conn.execute(text("""
                SELECT run_id, status, topics_included, completed_at, started_at
                FROM training_runs
                ORDER BY created_at DESC
            """))
            runs = result.fetchall()

            for topic_data in status:
                topic_name = topic_data["topic"]
                topic_data["latest_run"] = None
                for run in runs:
                    topics_in_run = run[2] or []
                    if topic_name in topics_in_run:
                        topic_data["latest_run"] = {
                            "run_id": run[0],
                            "status": run[1],
                            "completed_at": run[3].isoformat() if run[3] else None,
                            "started_at": run[4].isoformat() if run[4] else None,
                        }
                        break
        except Exception as e:
            logger.warning(f"Could not enrich topics with run status: {e}")
        finally:
            if conn:
                conn.close()

        return status
    except Exception as e:
        logger.error(f"Error getting topics status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topic-status/{topic}", response_model=TopicTrainingStatus)
async def get_topic_status(topic: str):
    """
    Get training status for a specific topic.
    """
    try:
        service = get_bootstrap_service()
        all_status = await service.get_all_topics_status()

        topic_status = next((s for s in all_status if s["topic"] == topic), None)
        if not topic_status:
            raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")

        return topic_status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting topic status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/topics/{topic}/initialize-samples")
async def initialize_topic_samples(
    topic: str,
    limit: int = Query(default=100, description="Max articles to bootstrap per call"),
):
    """
    Initialize training samples for a topic from its existing analyzed articles.

    Finds articles that have been analyzed but don't yet have training samples,
    and runs bootstrap_classification on them to generate samples.
    """
    import asyncio
    try:
        service = get_bootstrap_service()
        from app.database import get_database_instance
        db = get_database_instance()

        # Find analyzed articles for this topic that lack training samples
        with db.get_connection() as conn:
            result = conn.execute("""
                SELECT a.uri, a.title, COALESCE(a.summary, '') as summary
                FROM articles a
                LEFT JOIN enrichment_training_samples ets
                    ON a.uri = ets.article_uri AND ets.topic = :topic
                WHERE a.topic = :topic
                  AND a.analyzed = true
                  AND a.uri IS NOT NULL
                  AND ets.article_uri IS NULL
                LIMIT :lim
            """, {"topic": topic, "lim": limit})
            articles = result.fetchall()

        if not articles:
            # Check if topic exists at all
            with db.get_connection() as conn:
                result = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE topic = :topic",
                    {"topic": topic})
                total = result.scalar()

            if total == 0:
                raise HTTPException(status_code=404, detail=f"No articles found for topic '{topic}'")

            return {
                "topic": topic,
                "message": "All analyzed articles already have training samples",
                "bootstrapped": 0,
                "errors": 0,
            }

        bootstrapped = 0
        errors = 0
        for row in articles:
            uri, title, summary = row[0], row[1], row[2]
            if not title:
                continue
            try:
                await service.bootstrap_classification(
                    article_uri=uri,
                    title=title,
                    summary=summary or title,
                    topic=topic,
                )
                bootstrapped += 1
            except Exception as e:
                logger.warning(f"Bootstrap failed for {uri[:60]}: {e}")
                errors += 1
            # Brief pause to avoid hammering the LLM API
            await asyncio.sleep(0.1)

        return {
            "topic": topic,
            "bootstrapped": bootstrapped,
            "errors": errors,
            "remaining": len(articles) - bootstrapped - errors,
            "message": f"Initialized {bootstrapped} training samples for '{topic}'"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initializing samples for topic {topic}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/topics/{topic}/initialize-relevance-feedback")
async def initialize_relevance_feedback(
    topic: str,
    high_threshold: float = Query(default=0.7, description="Score >= this → more_like_this"),
    low_threshold: float = Query(default=0.3, description="Score < this → less_like_this"),
    limit: int = Query(default=500, description="Max feedback entries to create"),
):
    """
    Auto-bootstrap relevance feedback from existing keyword_relevance_score values.

    Articles with high scores are marked 'more_like_this',
    articles with low scores are marked 'less_like_this'.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    try:
        # Insert high-relevance articles as "more_like_this"
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Count existing auto-bootstrapped feedback for this topic
            cursor.execute(
                "SELECT COUNT(*) FROM user_relevance_feedback WHERE topic = :topic AND user_id = 'auto_bootstrap'",
                {"topic": topic}
            )
            existing = cursor.fetchone()[0]

            more_count = 0
            less_count = 0

            # Insert "more_like_this" for high-scoring articles
            cursor.execute("""
                INSERT INTO user_relevance_feedback
                    (article_uri, topic, user_id, feedback_type, relevance_score, article_metadata)
                SELECT
                    a.uri,
                    :topic,
                    'auto_bootstrap',
                    'more_like_this',
                    a.keyword_relevance_score,
                    jsonb_build_object('title', a.title, 'source', 'auto_bootstrap')
                FROM articles a
                LEFT JOIN user_relevance_feedback urf
                    ON a.uri = urf.article_uri AND urf.user_id = 'auto_bootstrap'
                WHERE a.topic = :topic
                  AND a.analyzed = true
                  AND a.uri IS NOT NULL
                  AND a.keyword_relevance_score >= :high_thresh
                  AND urf.article_uri IS NULL
                ORDER BY a.keyword_relevance_score DESC
                LIMIT :lim
            """, {"topic": topic, "high_thresh": high_threshold, "lim": limit})
            more_count = cursor.rowcount

            # Insert "less_like_this" for low-scoring articles
            cursor.execute("""
                INSERT INTO user_relevance_feedback
                    (article_uri, topic, user_id, feedback_type, relevance_score, article_metadata)
                SELECT
                    a.uri,
                    :topic,
                    'auto_bootstrap',
                    'less_like_this',
                    a.keyword_relevance_score,
                    jsonb_build_object('title', a.title, 'source', 'auto_bootstrap')
                FROM articles a
                LEFT JOIN user_relevance_feedback urf
                    ON a.uri = urf.article_uri AND urf.user_id = 'auto_bootstrap'
                WHERE a.topic = :topic
                  AND a.analyzed = true
                  AND a.uri IS NOT NULL
                  AND a.keyword_relevance_score < :low_thresh
                  AND a.keyword_relevance_score IS NOT NULL
                  AND urf.article_uri IS NULL
                ORDER BY a.keyword_relevance_score ASC
                LIMIT :lim
            """, {"topic": topic, "low_thresh": low_threshold, "lim": limit})
            less_count = cursor.rowcount

            conn.commit()

        # Get new total
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM user_relevance_feedback WHERE topic = :topic",
                {"topic": topic}
            )
            total = cursor.fetchone()[0]

        return {
            "topic": topic,
            "more_like_this_added": more_count,
            "less_like_this_added": less_count,
            "total_added": more_count + less_count,
            "previously_existing": existing,
            "total_feedback": total,
            "message": f"Added {more_count} 'more' + {less_count} 'less' feedback entries for '{topic}' (total: {total})"
        }
    except Exception as e:
        logger.error(f"Error initializing relevance feedback for topic {topic}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/field-distribution/{topic}/{field}", response_model=FieldDistribution)
async def get_field_distribution(topic: str, field: str):
    """
    Get value distribution for a specific field in a topic.

    Shows how many samples exist for each value (e.g., Positive: 120, Negative: 85, ...)
    """
    try:
        service = get_bootstrap_service()
        distribution = await service.get_field_distribution(topic, field)
        return distribution
    except Exception as e:
        logger.error(f"Error getting field distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/readiness", response_model=TrainingReadiness)
async def check_readiness(
    topics: Optional[str] = Query(default=None, description="Comma-separated list of topics")
):
    """
    Check if there are enough samples for finetuning.

    Returns overall readiness status and which topics are ready.
    """
    try:
        service = get_finetuning_service()
        topic_list = topics.split(",") if topics else None
        readiness = await service.check_readiness(topic_list)
        return readiness
    except Exception as e:
        logger.error(f"Error checking readiness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-finetune", response_model=TriggerFinetuneResponse)
async def trigger_finetune(request: TriggerFinetuneRequest):
    """
    Trigger a finetuning run.

    Will fail if there are not enough samples. Use /readiness to check first.
    """
    try:
        service = get_finetuning_service()
        run_id = await service.trigger_finetune(
            topics=request.topics,
            fields=request.fields,
        )

        status = await service.get_run_status(run_id)

        return TriggerFinetuneResponse(
            run_id=run_id,
            status=status["status"],
            topics_included=status["topics_included"] or [],
            sample_count=status["sample_count"] or 0,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error triggering finetune: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TriggerRelevanceTrainingResponse(BaseModel):
    """Response from triggering relevance training."""
    status: str
    message: str
    feedback_count: int


@router.post("/trigger-relevance-training", response_model=TriggerRelevanceTrainingResponse)
async def trigger_relevance_training():
    """
    Trigger relevance classifier training using user feedback data.

    Uses the 'more like this' / 'less like this' feedback to train
    a binary relevance classifier.
    """
    import subprocess
    import os

    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        # Check if we have enough feedback data
        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text("SELECT COUNT(*) FROM user_relevance_feedback"))
        feedback_count = result.fetchone()[0]

        if feedback_count < 500:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough feedback data. Have {feedback_count}, need at least 500 samples."
            )

        conn.close()
        conn = None

        # Run the training script in the background
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts",
            "train_relevance_classifier.py"
        )

        if not os.path.exists(script_path):
            raise HTTPException(status_code=500, detail="Training script not found")

        # Start training in background
        process = subprocess.Popen(
            ["python", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        logger.info(f"Started relevance training with PID {process.pid}, feedback_count={feedback_count}")

        return TriggerRelevanceTrainingResponse(
            status="started",
            message=f"Relevance training started (PID: {process.pid}). Check models/relevance_classifier/ for results.",
            feedback_count=feedback_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering relevance training: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/runs", response_model=List[TrainingRun])
async def list_runs(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    List training runs.
    """
    try:
        service = get_finetuning_service()
        runs = await service.list_runs(status=status, limit=limit)
        return runs
    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=TrainingRun)
async def get_run_status(run_id: str):
    """
    Get status of a specific training run.
    """
    try:
        service = get_finetuning_service()
        status = await service.get_run_status(run_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{run_id}/deploy")
async def deploy_model(run_id: str):
    """
    Deploy (hot-swap) a trained model to production.

    Only works for completed training runs.
    """
    try:
        service = get_finetuning_service()
        success = await service.hot_swap_model(run_id)

        if success:
            return {"status": "deployed", "run_id": run_id}
        else:
            raise HTTPException(status_code=500, detail="Deployment failed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deploying model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    """
    Delete a training run record and its associated files.

    Useful for cleaning up failed or old runs.
    """
    try:
        service = get_finetuning_service()
        success = await service.delete_run(run_id)

        if success:
            return {"status": "deleted", "run_id": run_id}
        else:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback")
async def rollback_model():
    """
    Rollback to the previous model version.
    """
    try:
        service = get_finetuning_service()
        success = await service.rollback_model()

        if success:
            return {"status": "rolled_back"}
        else:
            raise HTTPException(status_code=500, detail="Rollback failed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling back: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routing/{topic}", response_model=RoutingStatus)
async def get_routing_status(topic: str):
    """
    Get routing status for a topic - which model (DeBERTa/Qwen/LLM) will be used for each field.
    """
    try:
        service = get_hybrid_enrichment_service()
        status = await service.get_routing_status(topic)
        return status
    except Exception as e:
        logger.error(f"Error getting routing status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thresholds")
async def get_thresholds():
    """
    Get the current training thresholds.
    """
    try:
        service = get_bootstrap_service()
        return service.get_thresholds()
    except Exception as e:
        logger.error(f"Error getting thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """
    Get overall training system status.
    """
    try:
        bootstrap = get_bootstrap_service()
        finetuning = get_finetuning_service()
        hybrid = get_hybrid_enrichment_service()

        return {
            "bootstrap_thresholds": bootstrap.get_thresholds(),
            "finetuning": finetuning.get_status(),
            "hybrid_enrichment": hybrid.get_status(),
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PipelineStatsResponse(BaseModel):
    """Response for pipeline stats."""
    articles_today: int
    relevance_passed: int
    topics_active: int
    inference_mode: str = "hybrid"  # 'local', 'hybrid', or 'external'


@router.get("/pipeline-stats", response_model=PipelineStatsResponse)
async def get_pipeline_stats():
    """
    Get article processing pipeline stats for today.

    Returns:
    - articles_today: Total articles processed today
    - relevance_passed: Articles that passed relevance threshold
    - topics_active: Number of active topics with articles today
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Get articles processed today (using submission_date column)
        result = conn.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE submission_date::date >= CURRENT_DATE
        """))
        articles_today = result.fetchone()[0] or 0

        # Get articles that passed relevance (using topic_alignment_score as relevance proxy)
        result = conn.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE submission_date::date >= CURRENT_DATE
            AND topic_alignment_score >= 0.5
        """))
        relevance_passed = result.fetchone()[0] or 0

        # Get active topics (topics with articles today)
        result = conn.execute(text("""
            SELECT COUNT(DISTINCT topic) FROM articles
            WHERE submission_date::date >= CURRENT_DATE
        """))
        topics_active = result.fetchone()[0] or 0

        # Get inference mode
        result = conn.execute(text("""
            SELECT inference_mode FROM keyword_monitor_settings WHERE id = 1
        """))
        row = result.fetchone()
        inference_mode = row[0] if row else 'hybrid'

        return PipelineStatsResponse(
            articles_today=articles_today,
            relevance_passed=relevance_passed,
            topics_active=topics_active,
            inference_mode=inference_mode,
        )

    except Exception as e:
        logger.error(f"Error getting pipeline stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Confidence Stats Endpoints
# ============================================================================

class ConfidenceReading(BaseModel):
    """Request to record confidence readings."""
    topic: str
    confidence_scores: Dict[str, float]  # {field_name: confidence}


@router.get("/confidence-stats")
async def get_confidence_stats(topic: Optional[str] = Query(default=None)):
    """
    Get DeBERTa model confidence stats for the last 24 hours.

    Returns per-topic, per-field stats:
    - avg: Average confidence
    - min/max: Range of confidence values
    - count: Number of readings
    - above_threshold_pct: % of readings >= 0.6 threshold

    Args:
        topic: Optional topic to filter by
    """
    try:
        tracker = get_confidence_tracker()
        stats = tracker.get_stats(topic)
        return {
            "stats": stats,
            "threshold": 0.6,
            "window_hours": 24,
        }
    except Exception as e:
        logger.error(f"Error getting confidence stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confidence-stats")
async def record_confidence(reading: ConfidenceReading):
    """
    Record confidence readings from the enrichment service.

    Called internally by the automated ingest service when DeBERTa is used.
    """
    try:
        tracker = get_confidence_tracker()
        tracker.record(reading.topic, reading.confidence_scores)
        return {"status": "recorded"}
    except Exception as e:
        logger.error(f"Error recording confidence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/confidence-stats")
async def clear_confidence_stats(topic: Optional[str] = Query(default=None)):
    """
    Clear confidence stats for a topic or all topics.
    """
    try:
        tracker = get_confidence_tracker()
        tracker.clear(topic)
        return {"status": "cleared", "topic": topic or "all"}
    except Exception as e:
        logger.error(f"Error clearing confidence stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Relevance Confidence Stats Endpoints
# ============================================================================

class RelevanceReading(BaseModel):
    """Request to record relevance readings."""
    topic: str
    score: float
    classifier_score: Optional[float] = None
    embedding_score: Optional[float] = None
    method: str = "hybrid"
    relevant: Optional[bool] = None


@router.get("/relevance-confidence-stats")
async def get_relevance_confidence_stats(topic: Optional[str] = Query(default=None)):
    """
    Get relevance scoring confidence stats for the last 24 hours.

    Returns per-topic stats:
    - avg_score: Average combined relevance score
    - avg_classifier: Average DeBERTa classifier score
    - avg_embedding: Average embedding similarity score
    - relevant_pct: Percentage of articles marked as relevant
    - method_breakdown: Count of each scoring method used
    - high_confidence_pct: % of scores clearly above/below threshold

    Args:
        topic: Optional topic to filter by
    """
    try:
        tracker = get_relevance_confidence_tracker()
        stats = tracker.get_stats(topic)
        return {
            "stats": stats,
            "relevance_threshold": 0.5,
            "confidence_threshold": 0.35,  # Below 0.35 or above 0.65 = high confidence
            "window_hours": 24,
        }
    except Exception as e:
        logger.error(f"Error getting relevance confidence stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relevance-confidence-stats")
async def record_relevance_confidence(reading: RelevanceReading):
    """
    Record relevance score readings from the relevance service.

    Called internally by the automated ingest service when relevance is scored.
    """
    try:
        tracker = get_relevance_confidence_tracker()
        tracker.record(
            topic=reading.topic,
            score=reading.score,
            classifier_score=reading.classifier_score,
            embedding_score=reading.embedding_score,
            method=reading.method,
            relevant=reading.relevant
        )
        return {"status": "recorded"}
    except Exception as e:
        logger.error(f"Error recording relevance confidence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/relevance-confidence-stats")
async def clear_relevance_confidence_stats(topic: Optional[str] = Query(default=None)):
    """
    Clear relevance confidence stats for a topic or all topics.
    """
    try:
        tracker = get_relevance_confidence_tracker()
        tracker.clear(topic)
        return {"status": "cleared", "topic": topic or "all"}
    except Exception as e:
        logger.error(f"Error clearing relevance confidence stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# User Relevance Feedback Endpoints
# ============================================================================

class RelevanceFeedbackRequest(BaseModel):
    """Request to record user relevance feedback."""
    article_uri: str
    topic: str
    feedback_type: str  # 'more_like_this' or 'less_like_this'
    relevance_score: Optional[float] = None
    classifier_score: Optional[float] = None
    embedding_score: Optional[float] = None
    article_metadata: Optional[dict] = None


class RelevanceFeedbackResponse(BaseModel):
    """Response for recorded feedback."""
    id: int
    article_uri: str
    topic: str
    feedback_type: str
    created_at: str


class RelevanceFeedbackStats(BaseModel):
    """Stats about user feedback."""
    topic: str
    total_feedback: int
    more_like_this: int
    less_like_this: int
    recent_feedback: int  # last 7 days


@router.post("/relevance-feedback", response_model=RelevanceFeedbackResponse)
async def record_relevance_feedback(request: RelevanceFeedbackRequest):
    """
    Record user feedback on article relevance.

    Called when user clicks "more like this" or "less like this" on an article.
    Used to improve relevance model training.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        if request.feedback_type not in ('more_like_this', 'less_like_this'):
            raise HTTPException(
                status_code=400,
                detail="feedback_type must be 'more_like_this' or 'less_like_this'"
            )

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Upsert feedback (replace if user already gave feedback on this article)
        result = conn.execute(text("""
            INSERT INTO user_relevance_feedback
                (article_uri, topic, user_id, feedback_type, relevance_score,
                 classifier_score, embedding_score, article_metadata)
            VALUES (:uri, :topic, :user_id, :feedback_type, :relevance_score,
                 :classifier_score, :embedding_score, :metadata)
            ON CONFLICT (article_uri, user_id)
            DO UPDATE SET
                feedback_type = EXCLUDED.feedback_type,
                relevance_score = EXCLUDED.relevance_score,
                classifier_score = EXCLUDED.classifier_score,
                embedding_score = EXCLUDED.embedding_score,
                article_metadata = EXCLUDED.article_metadata,
                created_at = NOW()
            RETURNING id, created_at
        """), {
            "uri": request.article_uri,
            "topic": request.topic,
            "user_id": None,
            "feedback_type": request.feedback_type,
            "relevance_score": request.relevance_score,
            "classifier_score": request.classifier_score,
            "embedding_score": request.embedding_score,
            "metadata": str(request.article_metadata) if request.article_metadata else None,
        })

        row = result.fetchone()
        conn.commit()

        logger.info(f"Recorded relevance feedback: {request.feedback_type} for {request.article_uri[:50]}...")

        return RelevanceFeedbackResponse(
            id=row[0],
            article_uri=request.article_uri,
            topic=request.topic,
            feedback_type=request.feedback_type,
            created_at=row[1].isoformat() if row[1] else datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error recording relevance feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/relevance-feedback")
async def get_relevance_feedback(
    topic: Optional[str] = Query(default=None, description="Filter by topic"),
    feedback_type: Optional[str] = Query(default=None, description="Filter by feedback type"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Get user relevance feedback records.

    Used for reviewing feedback and exporting for training.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build query with optional filters
        query = """
            SELECT id, article_uri, topic, user_id, feedback_type,
                   relevance_score, classifier_score, embedding_score,
                   article_metadata, created_at
            FROM user_relevance_feedback
            WHERE 1=1
        """
        params = {}

        if topic:
            query += " AND topic = :topic"
            params["topic"] = topic

        if feedback_type:
            query += " AND feedback_type = :feedback_type"
            params["feedback_type"] = feedback_type

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

        result = conn.execute(text(query), params)
        rows = result.fetchall()

        # Get total count
        count_query = "SELECT COUNT(*) FROM user_relevance_feedback WHERE 1=1"
        count_params = {}
        if topic:
            count_query += " AND topic = :topic"
            count_params["topic"] = topic
        if feedback_type:
            count_query += " AND feedback_type = :feedback_type"
            count_params["feedback_type"] = feedback_type

        count_result = conn.execute(text(count_query), count_params)
        total = count_result.fetchone()[0]

        feedback_list = []
        for row in rows:
            feedback_list.append({
                "id": row[0],
                "article_uri": row[1],
                "topic": row[2],
                "user_id": row[3],
                "feedback_type": row[4],
                "relevance_score": row[5],
                "classifier_score": row[6],
                "embedding_score": row[7],
                "article_metadata": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
            })

        return {
            "feedback": feedback_list,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error getting relevance feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/relevance-feedback/stats")
async def get_relevance_feedback_stats(
    topic: Optional[str] = Query(default=None, description="Filter by topic"),
):
    """
    Get aggregated stats about user relevance feedback.

    Returns counts per topic and feedback type.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        query = """
            SELECT
                topic,
                COUNT(*) as total,
                SUM(CASE WHEN feedback_type = 'more_like_this' THEN 1 ELSE 0 END) as more_like_this,
                SUM(CASE WHEN feedback_type = 'less_like_this' THEN 1 ELSE 0 END) as less_like_this,
                SUM(CASE WHEN created_at > NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) as recent
            FROM user_relevance_feedback
        """

        if topic:
            query += " WHERE topic = :topic GROUP BY topic"
            result = conn.execute(text(query), {"topic": topic})
        else:
            query += " GROUP BY topic ORDER BY total DESC"
            result = conn.execute(text(query))

        rows = result.fetchall()

        stats = []
        for row in rows:
            stats.append({
                "topic": row[0],
                "total_feedback": row[1],
                "more_like_this": row[2],
                "less_like_this": row[3],
                "recent_feedback": row[4],
            })

        # Get overall totals
        totals_result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN feedback_type = 'more_like_this' THEN 1 ELSE 0 END) as more_like_this,
                SUM(CASE WHEN feedback_type = 'less_like_this' THEN 1 ELSE 0 END) as less_like_this
            FROM user_relevance_feedback
        """))
        totals = totals_result.fetchone()

        return {
            "by_topic": stats,
            "totals": {
                "total_feedback": totals[0] or 0,
                "more_like_this": totals[1] or 0,
                "less_like_this": totals[2] or 0,
            }
        }

    except Exception as e:
        logger.error(f"Error getting relevance feedback stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.delete("/relevance-feedback/{feedback_id}")
async def delete_relevance_feedback(feedback_id: int):
    """
    Delete a specific relevance feedback record.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text(
            "DELETE FROM user_relevance_feedback WHERE id = :id RETURNING id"
        ), {"id": feedback_id})
        row = result.fetchone()
        conn.commit()

        if not row:
            raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")

        return {"status": "deleted", "id": feedback_id}

    except HTTPException:
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting relevance feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Model Configuration Endpoint
# ============================================================================

class ModelInfo(BaseModel):
    """Information about a model."""
    name: str
    type: str  # 'local' or 'external'
    status: str  # 'available', 'unavailable'
    latency: Optional[str] = None
    description: str
    tooltip: str = ""  # User-friendly explanation
    port: Optional[int] = None
    cost: str = "FREE"
    usage: Optional[str] = None  # What pipeline stages use this model


class ModelConfigResponse(BaseModel):
    """Response for model configuration."""
    local_models: List[ModelInfo]
    external_models: List[ModelInfo]


@router.get("/model-config", response_model=ModelConfigResponse)
async def get_model_config():
    """
    Get the current model configuration.

    Returns information about all models (local and external) used in the pipeline.
    Latencies are p50 values from actual service calls when available.
    """
    import requests

    # Check vLLM model availability and get model info
    def check_vllm(port: int) -> tuple:
        """Returns (available, model_name)"""
        try:
            response = requests.get(f"http://localhost:{port}/v1/models", timeout=2)
            if response.status_code == 200:
                models = response.json().get("data", [])
                if models:
                    return True, models[0].get("id", "Unknown")
            return False, None
        except:
            return False, None

    # Get live latency measurements
    tracker = get_latency_tracker()

    def format_latency(model: str, default: str) -> str:
        """Format latency with p50 if available, otherwise use default estimate."""
        p50 = tracker.get_p50(model)
        if p50 is None:
            return default  # Fallback to estimate
        if p50 < 1000:
            return f"{int(p50)}ms"
        return f"{p50/1000:.1f}s"

    # Check DeBERTa availability
    deberta_available = False
    deberta_threshold = 500
    try:
        hybrid = get_hybrid_enrichment_service()
        status = hybrid.get_status()
        deberta_available = status.get("deberta_available", False)
        deberta_threshold = status.get("deberta_threshold", 500)
    except:
        pass

    vllm_port = int(os.getenv("VLLM_PORT", "8765"))
    phi3_available, phi3_model = check_vllm(vllm_port)
    qwen_available, qwen_model = check_vllm(vllm_port)

    # Local models with detailed tooltips and live latencies
    local_models = [
        ModelInfo(
            name="DeBERTa",
            type="local",
            status="available" if deberta_available else "unavailable",
            latency=format_latency('DeBERTa', '~56ms'),
            description="Relevance, Classification",
            tooltip=f"Fine-tuned DeBERTa-v3-base model running on CPU. Classifies sentiment, time_to_impact, driver_type, and future_signal. Requires {deberta_threshold}+ training samples per topic. Falls back to GPT when confidence < 0.6.",
            usage="Enrichment (4 fields), Relevance scoring",
            cost="FREE",
        ),
        ModelInfo(
            name="Phi-3",
            type="local",
            status="available" if phi3_available else "unavailable",
            latency=format_latency('Phi-3', '~3.5s'),
            description="Summary, Tags",
            tooltip=f"Microsoft Phi-3-mini-4k-instruct running on vLLM (GPU). Generates article summaries and refines KeyBERT tags with NER. Model: {phi3_model or 'Not loaded'}",
            usage="Summarization, Tag refinement + NER",
            port=vllm_port,
            cost="FREE",
        ),
        ModelInfo(
            name="Qwen",
            type="local",
            status="available" if qwen_available else "unavailable",
            latency=format_latency('Qwen', '~5s'),
            description="Explanations, Category",
            tooltip=f"Qwen2.5-3B-Instruct running on vLLM (GPU). Zero-shot category classification and generates human-readable explanations for classification decisions. Model: {qwen_model or 'Not loaded'}",
            usage="Category classification, Explanation generation",
            port=vllm_port,
            cost="FREE",
        ),
        ModelInfo(
            name="KeyBERT",
            type="local",
            status="available",
            latency=format_latency('KeyBERT', '~100ms'),
            description="Keyword extraction",
            tooltip="KeyBERT with all-MiniLM-L6-v2 embeddings. Extracts key phrases from article text using BERT embeddings and cosine similarity. Results are refined by Phi-3 for NER.",
            usage="Tag extraction (initial)",
            cost="FREE",
        ),
        ModelInfo(
            name="MiniLM",
            type="local",
            status="available",
            latency=format_latency('MiniLM', '~50ms'),
            description="Embedding similarity",
            tooltip="sentence-transformers/all-MiniLM-L6-v2 for semantic similarity. Used in hybrid relevance scoring to compare article content with topic descriptions.",
            usage="Relevance scoring (embedding component)",
            cost="FREE",
        ),
    ]

    # External models (LLM fallbacks)
    external_models = [
        ModelInfo(
            name="gpt-4o-mini",
            type="external",
            status="available",
            latency=format_latency('gpt-4o-mini', '~2-5s'),
            description="Fallback for all stages",
            tooltip="OpenAI gpt-4o-mini used as fallback when: (1) Local models unavailable, (2) DeBERTa confidence < 0.6, (3) Topics with < 500 training samples, (4) Relevance score in uncertain range (0.3-0.7). Cost is per-article average.",
            usage="Fallback: Summary, Category, Enrichment, Explanations, Tags",
            cost="~$0.001/article",
        ),
    ]

    return ModelConfigResponse(
        local_models=local_models,
        external_models=external_models,
    )


@router.get("/latency-stats")
async def get_latency_stats():
    """
    Get live latency statistics for all tracked models.

    Returns p50 (median), min, max, and sample count for each model
    from a rolling window of the last 100 measurements.
    """
    tracker = get_latency_tracker()
    return {
        "stats": tracker.get_stats(),
        "max_samples": tracker._max_samples,
    }


class CostSavingsStats(BaseModel):
    """Cost savings statistics from model usage."""
    total_articles: int
    local_model_count: int  # Articles processed by local models only
    llm_fallback_count: int  # Articles that used LLM fallback
    local_percentage: float  # Percentage processed locally (free)
    estimated_llm_cost: float  # Estimated cost if all used LLM
    actual_llm_cost: float  # Actual LLM cost for fallback articles
    savings_amount: float  # Estimated savings
    savings_percentage: float  # Percentage savings
    method_breakdown: dict  # Breakdown by method
    window_hours: int


@router.get("/cost-savings")
async def get_cost_savings(hours: int = 24):
    """
    Get cost savings statistics based on actual model usage.

    Calculates what percentage of articles were processed by free local models
    vs paid LLM fallback. Uses data from relevance_confidence_readings and
    enrichment_confidence_readings tables.

    Args:
        hours: Time window in hours (default 24)
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Get relevance scoring method breakdown
        result = conn.execute(text("""
            SELECT
                method,
                COUNT(*) as count
            FROM relevance_confidence_readings
            WHERE recorded_at > NOW() - INTERVAL :hours
            GROUP BY method
        """.replace(':hours', f"'{hours} hours'")))

        method_breakdown = {}
        total_relevance = 0
        llm_relevance = 0

        for row in result.fetchall():
            method, count = row[0], row[1]
            method_breakdown[method] = count
            total_relevance += count
            # Count LLM usage: any method containing 'llm'
            if 'llm' in method.lower():
                llm_relevance += count

        # Get enrichment model source breakdown from enrichment readings
        # We track DeBERTa usage via confidence readings
        # For now, we estimate based on relevance method breakdown

        # Get total articles processed in time window (using articles table)
        result = conn.execute(text("""
            SELECT COUNT(*) FROM articles
            WHERE submission_date::timestamp > NOW() - INTERVAL :hours
        """.replace(':hours', f"'{hours} hours'")))

        total_articles = result.fetchone()[0] or 0

        # Calculate costs
        # Assume ~$0.001 per article for LLM (gpt-4o-mini for summary + enrichment)
        COST_PER_LLM_ARTICLE = 0.001

        # Local model count = total - articles that used LLM fallback
        # For relevance, methods without 'llm' are local-only
        local_relevance = total_relevance - llm_relevance

        # Calculate percentages
        if total_relevance > 0:
            local_percentage = (local_relevance / total_relevance) * 100
        else:
            local_percentage = 100.0  # Default to 100% if no data

        # Estimate costs
        estimated_llm_cost = total_articles * COST_PER_LLM_ARTICLE
        actual_llm_cost = llm_relevance * COST_PER_LLM_ARTICLE
        savings_amount = estimated_llm_cost - actual_llm_cost

        if estimated_llm_cost > 0:
            savings_percentage = (savings_amount / estimated_llm_cost) * 100
        else:
            savings_percentage = 100.0

        return CostSavingsStats(
            total_articles=total_articles,
            local_model_count=local_relevance,
            llm_fallback_count=llm_relevance,
            local_percentage=round(local_percentage, 1),
            estimated_llm_cost=round(estimated_llm_cost, 4),
            actual_llm_cost=round(actual_llm_cost, 4),
            savings_amount=round(savings_amount, 4),
            savings_percentage=round(savings_percentage, 1),
            method_breakdown=method_breakdown,
            window_hours=hours,
        )

    except Exception as e:
        logger.error(f"Error calculating cost savings: {e}")
        # Return defaults if no data yet
        return CostSavingsStats(
            total_articles=0,
            local_model_count=0,
            llm_fallback_count=0,
            local_percentage=100.0,
            estimated_llm_cost=0.0,
            actual_llm_cost=0.0,
            savings_amount=0.0,
            savings_percentage=100.0,
            method_breakdown={},
            window_hours=hours,
        )
    finally:
        if conn:
            conn.close()


# ============================================================================
# Preclassifier Training Endpoints
# ============================================================================

def get_preclassifier_service():
    from app.services.preclassifier_training_service import get_preclassifier_training_service
    return get_preclassifier_training_service()


class TrainPreclassifierRequest(BaseModel):
    """Optional parameters for preclassifier training."""
    epochs: Optional[int] = None
    batch_size: Optional[int] = None


@router.get("/preclassifiers")
async def list_preclassifiers():
    """
    List all preclassifiers with sample counts, readiness, and model status.
    """
    try:
        service = get_preclassifier_service()
        preclassifiers = service.list_all()
        return {"preclassifiers": preclassifiers}
    except Exception as e:
        logger.error(f"Error listing preclassifiers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preclassifiers/{classifier_id}/status")
async def get_preclassifier_status(classifier_id: str):
    """
    Get detailed status for a specific preclassifier.
    """
    try:
        service = get_preclassifier_service()
        status = service.get_status(classifier_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting preclassifier status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preclassifiers/{classifier_id}/train")
async def train_preclassifier(classifier_id: str, request: TrainPreclassifierRequest = None):
    """
    Export data and trigger training for a preclassifier.
    """
    try:
        service = get_preclassifier_service()
        req = request or TrainPreclassifierRequest()
        result = service.train(
            classifier_id,
            epochs=req.epochs,
            batch_size=req.batch_size,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error training preclassifier: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preclassifiers/{classifier_id}/reload")
async def reload_preclassifier(classifier_id: str):
    """
    Force-reload a preclassifier model after training.
    """
    try:
        service = get_preclassifier_service()
        result = service.reload_model(classifier_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error reloading preclassifier: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/relevance-feedback/article/{article_uri:path}")
async def get_article_feedback(article_uri: str):
    """
    Get feedback for a specific article.

    Used to show current feedback state in the UI.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text("""
            SELECT id, topic, user_id, feedback_type, created_at
            FROM user_relevance_feedback
            WHERE article_uri = :uri
        """), {"uri": article_uri})

        row = result.fetchone()

        if not row:
            return {"has_feedback": False, "feedback": None}

        return {
            "has_feedback": True,
            "feedback": {
                "id": row[0],
                "topic": row[1],
                "user_id": row[2],
                "feedback_type": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
            }
        }

    except Exception as e:
        logger.error(f"Error getting article feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Inference Mode Settings
# ============================================================================

class InferenceModeRequest(BaseModel):
    """Request model for setting inference mode."""
    mode: str = Field(..., description="Inference mode: 'local', 'hybrid', or 'external'")


@router.get("/inference-mode")
async def get_inference_mode():
    """
    Get the current inference mode setting.

    Returns:
        mode: 'local' (DeBERTa only), 'hybrid' (DeBERTa + GPT fallback), or 'external' (GPT only)
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        result = conn.execute(text("""
            SELECT inference_mode FROM keyword_monitor_settings WHERE id = 1
        """))
        row = result.fetchone()

        mode = row[0] if row else 'hybrid'
        return {"mode": mode}

    except Exception as e:
        logger.error(f"Error getting inference mode: {e}")
        # Return default on error
        return {"mode": "hybrid"}
    finally:
        if conn:
            conn.close()


def check_local_models_available() -> dict:
    """
    Check if local models are available and can be loaded.

    Returns dict with:
        available: bool - True if all critical local models are ready
        models: dict - Status of each model
        missing: list - Names of unavailable models
    """
    models_status = {}
    missing = []

    # Check relevance classifier (DeBERTa)
    try:
        from app.services.relevance_classifier_service import get_relevance_classifier
        classifier = get_relevance_classifier()
        relevance_available = classifier.is_available()
        models_status["relevance_classifier"] = {
            "available": relevance_available,
            "name": "DeBERTa Relevance",
            "error": classifier._load_error if not relevance_available else None
        }
        if not relevance_available:
            missing.append("DeBERTa Relevance Classifier")
    except Exception as e:
        models_status["relevance_classifier"] = {"available": False, "name": "DeBERTa Relevance", "error": str(e)}
        missing.append("DeBERTa Relevance Classifier")

    # Check hybrid relevance service (embedding + classifier)
    try:
        from app.services.hybrid_relevance_service import get_hybrid_relevance_service
        hybrid = get_hybrid_relevance_service()
        hybrid_available = hybrid.is_available()
        models_status["hybrid_relevance"] = {
            "available": hybrid_available,
            "name": "Hybrid Relevance (Embedding)",
            "error": None if hybrid_available else "Embedding model not loaded"
        }
        if not hybrid_available:
            missing.append("Hybrid Relevance Embedding")
    except Exception as e:
        models_status["hybrid_relevance"] = {"available": False, "name": "Hybrid Relevance", "error": str(e)}
        missing.append("Hybrid Relevance")

    # Check enrichment DeBERTa
    try:
        from app.services.enrichment_service import get_enrichment_service
        enrichment = get_enrichment_service()
        enrichment_available = enrichment.is_available()
        models_status["enrichment"] = {
            "available": enrichment_available,
            "name": "DeBERTa Enrichment",
            "error": None if enrichment_available else "Enrichment model not loaded"
        }
        if not enrichment_available:
            missing.append("DeBERTa Enrichment")
    except Exception as e:
        models_status["enrichment"] = {"available": False, "name": "DeBERTa Enrichment", "error": str(e)}
        missing.append("DeBERTa Enrichment")

    # Check Phi-3 vLLM (summarization) on port 8765
    try:
        from app.services.summarization_service import get_summarization_service
        summarizer = get_summarization_service()
        # Reset cache to get fresh status
        summarizer.reset_vllm_check()
        status = summarizer.get_status()
        phi3_available = status.get("vllm_available", False)
        models_status["phi3_summarization"] = {
            "available": phi3_available,
            "name": "Phi-3 (Summarization)",
            "error": None if phi3_available else "vLLM not running on port 8765"
        }
        if not phi3_available:
            missing.append("Phi-3 (Summarization)")
    except Exception as e:
        models_status["phi3_summarization"] = {"available": False, "name": "Phi-3 (Summarization)", "error": str(e)}
        missing.append("Phi-3 (Summarization)")

    # Check Qwen vLLM (category)
    try:
        from app.services.category_service import get_category_service
        category_svc = get_category_service()
        # Reset cache to get fresh status
        category_svc.reset_availability_check()
        qwen_available = category_svc.is_available()
        models_status["qwen_category"] = {
            "available": qwen_available,
            "name": "Qwen (Category)",
            "error": None if qwen_available else f"vLLM not running on port {os.getenv('VLLM_PORT', '8765')}"
        }
        if not qwen_available:
            missing.append("Qwen (Category)")
    except Exception as e:
        models_status["qwen_category"] = {"available": False, "name": "Qwen (Category)", "error": str(e)}
        missing.append("Qwen (Category)")

    # Check KeyBERT (tagging)
    try:
        from app.services.keybert_tagging_service import get_keybert_tagging_service
        keybert_svc = get_keybert_tagging_service()
        keybert_available = keybert_svc.is_available()
        models_status["keybert_tagging"] = {
            "available": keybert_available,
            "name": "KeyBERT (Tagging)",
            "error": None if keybert_available else "KeyBERT model not loaded"
        }
        if not keybert_available:
            missing.append("KeyBERT (Tagging)")
    except Exception as e:
        models_status["keybert_tagging"] = {"available": False, "name": "KeyBERT (Tagging)", "error": str(e)}
        missing.append("KeyBERT (Tagging)")

    # Check External LLM (GPT) - requires valid API key
    external_llm_available = False
    external_llm_models = []
    external_llm_error = None
    try:
        from app.ai_models import get_available_models
        available_models = get_available_models()
        if available_models and len(available_models) > 0:
            external_llm_available = True
            external_llm_models = [m.get('name') for m in available_models[:3]]  # First 3
        else:
            external_llm_error = "No API keys configured (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)"
    except Exception as e:
        external_llm_error = str(e)

    models_status["external_llm"] = {
        "available": external_llm_available,
        "name": "External LLM (GPT/Claude)",
        "error": external_llm_error,
        "configured_models": external_llm_models
    }

    # All critical LOCAL models must be available for local mode
    all_available = len(missing) == 0

    return {
        "available": all_available,
        "models": models_status,
        "missing": missing,
        "external_llm_available": external_llm_available
    }


@router.get("/local-models-status")
async def get_local_models_status():
    """
    Check status of all local models required for 'local' inference mode.

    Returns availability status for each local model.
    """
    return check_local_models_available()


@router.put("/inference-mode")
async def set_inference_mode(request: InferenceModeRequest):
    """
    Set the inference mode for article processing.

    Args:
        mode: 'local' (DeBERTa only, fast/free), 'hybrid' (DeBERTa + GPT fallback), or 'external' (GPT only)

    Returns:
        Success status and the new mode
    """
    valid_modes = ['local', 'hybrid', 'external']
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{request.mode}'. Must be one of: {valid_modes}"
        )

    # If switching to local mode, verify local models are available
    if request.mode == 'local':
        model_check = check_local_models_available()
        if not model_check["available"]:
            missing_str = ", ".join(model_check["missing"])
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to local mode - missing models: {missing_str}. Use 'hybrid' mode instead."
            )

    # If switching to external mode, verify API keys are configured
    if request.mode == 'external':
        model_check = check_local_models_available()
        if not model_check.get("external_llm_available", False):
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to external mode - no API keys configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in environment."
            )

    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        conn.execute(text("""
            UPDATE keyword_monitor_settings SET inference_mode = :mode WHERE id = 1
        """), {"mode": request.mode})
        conn.commit()

        logger.info(f"Inference mode changed to: {request.mode}")
        return {"success": True, "mode": request.mode}

    except Exception as e:
        logger.error(f"Error setting inference mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Relevance Triage - Rapid Article Classification
# ============================================================================

@router.get("/triage-articles")
async def get_triage_articles(
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(50, ge=1, le=200, description="Max articles to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Get analyzed articles that haven't been reviewed yet for relevance triage.

    Returns articles where user_preference IS NULL, ordered by publication_date DESC.
    """
    conn = None
    try:
        from app.database import get_database_instance
        from sqlalchemy import text

        db = get_database_instance()
        conn = db._temp_get_connection()

        # Build WHERE clause
        where_clauses = ["analyzed = TRUE", "user_preference IS NULL"]
        params = {"limit": limit, "offset": offset}

        if topic:
            where_clauses.append("topic = :topic")
            params["topic"] = topic

        where_sql = " AND ".join(where_clauses)

        # Get total count of unreviewed articles
        count_result = conn.execute(
            text(f"SELECT COUNT(*) FROM articles WHERE {where_sql}"),
            params,
        ).fetchone()
        total_available = count_result[0] if count_result else 0

        # Get total existing feedback count (for progress tracking)
        feedback_count_result = conn.execute(
            text("SELECT COUNT(*) FROM articles WHERE user_preference IS NOT NULL")
        ).fetchone()
        total_feedback = feedback_count_result[0] if feedback_count_result else 0

        # Fetch articles
        rows = conn.execute(
            text(f"""
                SELECT uri, title, summary, news_source, publication_date,
                       category, topic, sentiment, tags, keyword_relevance_score
                FROM articles
                WHERE {where_sql}
                ORDER BY publication_date DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        articles = []
        for row in rows:
            articles.append({
                "uri": row[0],
                "title": row[1],
                "summary": row[2],
                "news_source": row[3],
                "publication_date": row[4],
                "category": row[5],
                "topic": row[6],
                "sentiment": row[7],
                "tags": row[8],
                "keyword_relevance_score": row[9],
            })

        # Get distinct topics for filter dropdown
        topic_rows = conn.execute(
            text("SELECT DISTINCT topic FROM articles WHERE analyzed = TRUE AND user_preference IS NULL AND topic IS NOT NULL ORDER BY topic")
        ).fetchall()
        available_topics = [r[0] for r in topic_rows]

        return {
            "articles": articles,
            "total_available": total_available,
            "total_feedback": total_feedback,
            "available_topics": available_topics,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error fetching triage articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/data-quality")
async def get_data_quality_report(
    hours: int = 24,
    samples: int = 5,
):
    """Run a data quality audit across all topics with recent approved articles."""
    try:
        from app.database import Database
        from app.services.data_quality_service import DataQualityService

        db = Database()
        dqs = DataQualityService(db)
        report = dqs.nightly_report(hours=hours, sample_per_topic=samples)
        return report

    except Exception as e:
        logger.error(f"Error running data quality report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-quality/topic/{topic}")
async def get_topic_quality(
    topic: str,
    samples: int = 10,
    hours: int = 168,
):
    """Run a data quality audit for a single topic."""
    try:
        from app.database import Database
        from app.services.data_quality_service import DataQualityService

        db = Database()
        dqs = DataQualityService(db)

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, summary FROM articles
                WHERE ingest_status = 'approved'
                  AND topic = :topic
                  AND submission_date >= :cutoff
                  AND category IS NOT NULL
                ORDER BY RANDOM()
                LIMIT :limit
            """, {"topic": topic, "cutoff": cutoff, "limit": samples})
            rows = cursor.fetchall()

        if not rows:
            return {"topic": topic, "sampled": 0, "passed": 0, "failed": 0, "error": 0, "pass_rate": 1.0, "failures": []}

        articles = [{"title": r[0], "summary": r[1]} for r in rows]
        report = dqs.audit_batch(topic, articles, sample_size=len(articles))
        return report

    except Exception as e:
        logger.error(f"Error running topic quality check: {e}")
        raise HTTPException(status_code=500, detail=str(e))
