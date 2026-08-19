"""
Emerging Topics API Routes

Provides endpoints for:
- Running emerging topic detection
- Retrieving detected emerging topics
- Getting high-novelty articles
- Managing proto-clusters
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import json
import logging

from app.services.emerging_topics import (
    get_emerging_topics_service,
    EmergingTopicsConfig,
    DetectionAlreadyRunning,
    DetectionRunLock,
    normalize_filters,
    validate_filters,
    ALLOWED_FILTERS,
)
from app.security.session import verify_session, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emerging-topics", tags=["Emerging Topics"])


# ============================================================================
# SSE framing
#
# Every frame is a named event plus one data line, terminated by a blank line.
# Clients that only look for "data: " keep working; clients that listen for
# named events now get "progress", "complete", and "error" instead of having to
# infer the outcome from the payload.
# ============================================================================

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse_frame(payload: Dict[str, Any], event: Optional[str] = None) -> str:
    """Serialize one payload as an SSE frame."""
    name = event or payload.get("event") or "progress"
    body = json.dumps(payload, default=str)
    return f"event: {name}\ndata: {body}\n\n"


def sse_error(message: str, code: str = "detection_failed", **extra) -> str:
    """An error frame for a failure the generator itself has to report."""
    payload = {"event": "error", "status": "failed", "code": code, "message": message}
    payload.update(extra)
    return sse_frame(payload, "error")


def _lock_conflict(exc: DetectionAlreadyRunning) -> HTTPException:
    """409 with a machine-readable code, raised before any run row exists."""
    return HTTPException(
        status_code=409,
        detail={
            "code": exc.code,
            "message": str(exc),
            "topic_filter": exc.topic_filter,
        },
    )


# ============================================================================
# Request/Response Models
# ============================================================================

class DetectionRequest(BaseModel):
    """Request model for running emerging topic detection."""
    topic: Optional[str] = Field(
        None,
        description="Topic filter to limit detection scope"
    )
    days_back: int = Field(
        7,
        ge=1,
        le=30,
        description="Number of days to include in analysis"
    )
    min_confidence: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for emerging topics"
    )
    include_proto_clusters: bool = Field(
        True,
        description="Include proto-clusters (early-stage emerging topics)"
    )
    stream: bool = Field(
        True,
        description="Whether to stream progress updates"
    )
    # V2 Config Parameters
    sample_size: int = Field(
        250,
        ge=50,
        le=500,
        description="Number of articles to sample for theme proposal"
    )
    distance_threshold: float = Field(
        0.85,
        ge=0.3,
        le=1.0,
        description="Cosine distance threshold for article assignment"
    )
    min_articles_per_theme: int = Field(
        3,
        ge=2,
        le=20,
        description="Minimum articles required for a valid theme"
    )
    max_articles_per_theme: int = Field(
        30,
        ge=10,
        le=100,
        description="Maximum articles to assign per theme"
    )
    model: str = Field(
        "gpt-5.4",
        description="AI model to use for theme proposal and analysis"
    )


class EmergingTopicResponse(BaseModel):
    """Response model for an emerging topic."""
    id: int
    topic_label: str
    topic_description: str
    detection_date: str
    detection_type: str
    article_count: int
    growth_rate: float
    velocity: str
    confidence_score: float
    key_themes: List[str]
    representative_keywords: List[str]
    status: str


class NoveltyScoreResponse(BaseModel):
    """Response model for article novelty score."""
    article_uri: str
    article_title: str
    composite_novelty_score: float
    knn_distance_score: float
    density_score: float
    centroid_distance_score: float
    is_outlier: bool
    calculation_date: str


# ============================================================================
# Streaming Helper
# ============================================================================

def _build_service(request: "DetectionRequest"):
    """Build a service configured from one detection request."""
    from app.services.emerging_topics import EmergingTopicsService, EmergingTopicsConfig
    from app.ai_models import get_ai_model

    config = EmergingTopicsConfig(
        max_sample_articles=request.sample_size,
        theme_distance_threshold=request.distance_threshold,
        min_articles_for_theme=request.min_articles_per_theme,
        max_articles_per_theme=request.max_articles_per_theme,
        days_back=request.days_back,
        model=request.model
    )
    return EmergingTopicsService(config=config, ai_model_getter=get_ai_model)


async def stream_detection(request: "DetectionRequest", lock: DetectionRunLock):
    """Stream one detection run as SSE frames.

    The lock is taken by the endpoint before the stream starts, so a second run
    in the same scope is refused with a status code rather than a mid-stream
    error. It is released here in ``finally``, which covers success, failure,
    and the client hanging up.
    """
    service = _build_service(request)
    try:
        async for update in service.run_detection_streaming(
            topic_filter=request.topic,
            days_back=request.days_back,
            run_lock=lock,
        ):
            yield sse_frame(update)
    except Exception as exc:
        logger.exception("Emerging topics stream failed")
        yield sse_error(f"{exc.__class__.__name__}: {exc}")
    finally:
        lock.release()


# ============================================================================
# Detection Endpoints
# ============================================================================

@router.post("/detect")
async def run_detection(
    request: DetectionRequest,
    session=Depends(require_admin)
):
    """
    Run emerging topic detection.

    If stream=True, returns a Server-Sent Events stream with progress updates.
    Otherwise, returns the complete detection result.

    Detection writes global state, so it is admin-only, and only one run per
    scope may be in flight — a second one gets 409 ``detection_already_running``.
    """
    try:
        lock = DetectionRunLock(request.topic).acquire()
    except DetectionAlreadyRunning as exc:
        raise _lock_conflict(exc)

    if request.stream:
        return StreamingResponse(
            stream_detection(request, lock),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    try:
        service = _build_service(request)
        return await service.run_detection(
            topic_filter=request.topic,
            days_back=request.days_back,
            run_lock=lock,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Emerging topics detection failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": getattr(exc, "code", "detection_failed"),
                "message": f"{exc.__class__.__name__}: {exc}",
            },
        )
    finally:
        lock.release()


@router.post("/detect/sync")
async def run_detection_sync(
    request: DetectionRequest,
    session=Depends(require_admin)
):
    """
    Run emerging topic detection synchronously (no streaming).
    Returns the complete detection result, or an error status if the run failed.
    """
    try:
        lock = DetectionRunLock(request.topic).acquire()
    except DetectionAlreadyRunning as exc:
        raise _lock_conflict(exc)

    try:
        service = _build_service(request)
        return await service.run_detection(
            topic_filter=request.topic,
            days_back=request.days_back,
            run_lock=lock,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Emerging topics detection failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": getattr(exc, "code", "detection_failed"),
                "message": f"{exc.__class__.__name__}: {exc}",
            },
        )
    finally:
        lock.release()


# ============================================================================
# Config Endpoint
# ============================================================================

class DetectionConfig(BaseModel):
    """Configuration for emerging topic detection."""
    sample_size: int = 250
    days_back: int = 7
    distance_threshold: float = 0.85
    min_articles_per_theme: int = 3
    max_articles_per_theme: int = 30


@router.get("/config")
async def get_detection_config(
    session=Depends(verify_session)
):
    """Get default detection configuration."""
    return {
        "sample_size": {"default": 250, "min": 50, "max": 500, "description": "Number of articles to sample for theme proposal"},
        "days_back": {"default": 7, "min": 1, "max": 30, "description": "Number of days to look back"},
        "distance_threshold": {"default": 0.85, "min": 0.3, "max": 1.0, "description": "Cosine distance threshold for article assignment (higher = more lenient)"},
        "min_articles_per_theme": {"default": 3, "min": 2, "max": 20, "description": "Minimum articles required for a valid theme"},
        "max_articles_per_theme": {"default": 30, "min": 10, "max": 100, "description": "Maximum articles to assign per theme"},
    }


# ============================================================================
# Batch Detection Endpoint
# ============================================================================

class BatchDetectionRequest(BaseModel):
    """Request model for batch detection across selected or all topics."""
    topics: Optional[List[str]] = Field(
        None,
        description="Specific topics to scan. If empty/null, scans all configured topics."
    )
    days_back: int = Field(7, ge=1, le=30)
    sample_size: int = Field(250, ge=50, le=500)
    distance_threshold: float = Field(0.85, ge=0.3, le=1.0)
    min_articles_per_theme: int = Field(3, ge=2, le=20)
    max_articles_per_theme: int = Field(30, ge=10, le=100)
    model: str = Field("gpt-5.4", description="AI model to use for theme proposal and analysis")


async def stream_batch_detection(request: BatchDetectionRequest):
    """Stream batch detection across selected or all topics.

    Each topic is its own scope, so each takes its own lock: a topic already
    being scanned elsewhere is reported and skipped, and the rest of the batch
    carries on.
    """
    from app.services.emerging_topics import EmergingTopicsService, EmergingTopicsConfig
    from app.ai_models import get_ai_model
    from app.config.config import load_config

    config = load_config()

    # Use provided topics or fall back to all configured topics
    if request.topics and len(request.topics) > 0:
        topics = request.topics
    else:
        topics = [t["name"] for t in config.get("topics", [])]

    total_topics = len(topics)
    all_themes = []
    failed_topics = []

    if not total_topics:
        yield sse_frame({
            "event": "complete",
            "status": "completed",
            "step": 0,
            "progress": 100,
            "message": "No topics configured to scan",
            "total_themes": 0,
            "topics_scanned": 0,
            "emerging_topics": [],
        })
        return

    yield sse_frame({
        "event": "progress",
        "step": 0,
        "progress": 0,
        "message": f"Starting batch detection across {total_topics} topics...",
    })

    for i, topic_name in enumerate(topics):
        base_progress = (i / total_topics) * 100

        yield sse_frame({
            "event": "progress",
            "step": i + 1,
            "progress": base_progress,
            "message": f"Scanning topic {i + 1}/{total_topics}: {topic_name}",
            "current_topic": topic_name,
        })

        et_config = EmergingTopicsConfig(
            max_sample_articles=request.sample_size,
            theme_distance_threshold=request.distance_threshold,
            min_articles_for_theme=request.min_articles_per_theme,
            max_articles_per_theme=request.max_articles_per_theme,
            days_back=request.days_back,
            model=request.model
        )

        service = EmergingTopicsService(config=et_config, ai_model_getter=get_ai_model)

        try:
            lock = DetectionRunLock(topic_name).acquire()
        except DetectionAlreadyRunning as exc:
            failed_topics.append(topic_name)
            yield sse_error(
                str(exc), code=exc.code, current_topic=topic_name, step=i + 1,
                progress=base_progress,
            )
            continue

        topic_themes = []
        topic_failed = False
        try:
            async for update in service.run_detection_streaming(
                topic_filter=topic_name,
                days_back=request.days_back,
                run_lock=lock,
            ):
                sub_progress = update.get('progress', 0)
                adjusted_progress = base_progress + (sub_progress / total_topics)
                msg = update.get('message', '')

                if update.get("event") == "error":
                    topic_failed = True
                    yield sse_error(
                        f"[{topic_name}] {msg}",
                        code=update.get("code", "detection_failed"),
                        current_topic=topic_name,
                        step=i + 1,
                        progress=adjusted_progress,
                        run_id=update.get("run_id"),
                    )
                    continue

                yield sse_frame({
                    "event": "progress",
                    "step": i + 1,
                    "progress": adjusted_progress,
                    "message": f"[{topic_name}] {msg}",
                    "current_topic": topic_name,
                })

                if update.get("event") == "complete":
                    topic_themes = update.get("emerging_topics", [])
                    all_themes.extend(topic_themes)

        except Exception as exc:
            topic_failed = True
            logger.exception(f"Error detecting topics for {topic_name}")
            yield sse_error(
                f"Error scanning {topic_name}: {exc.__class__.__name__}: {exc}",
                code=getattr(exc, "code", "detection_failed"),
                current_topic=topic_name,
                step=i + 1,
                progress=base_progress,
            )
        finally:
            lock.release()

        if topic_failed:
            failed_topics.append(topic_name)
            continue

        yield sse_frame({
            "event": "progress",
            "step": i + 1,
            "progress": base_progress + (100 / total_topics),
            "message": f"Completed {topic_name}: {len(topic_themes)} themes found",
            "topic_complete": topic_name,
            "themes_found": len(topic_themes),
        })

    scanned = total_topics - len(failed_topics)
    summary = (
        f"Batch detection complete: {len(all_themes)} total themes across "
        f"{scanned} of {total_topics} topics"
    )
    if failed_topics:
        summary += f" ({len(failed_topics)} failed: {', '.join(failed_topics[:5])})"

    yield sse_frame({
        "event": "complete",
        "status": "completed" if not failed_topics else "partial",
        "step": total_topics + 1,
        "progress": 100,
        "message": summary,
        "total_themes": len(all_themes),
        "topics_scanned": scanned,
        "topics_failed": failed_topics,
        "emerging_topics": all_themes,
    })


@router.post("/detect/batch")
async def run_batch_detection(
    request: BatchDetectionRequest,
    session=Depends(require_admin)
):
    """
    Run emerging topic detection across ALL configured topics.
    Returns a Server-Sent Events stream with progress updates.
    """
    return StreamingResponse(
        stream_batch_detection(request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/available-topics")
async def get_available_topics(
    session=Depends(verify_session)
):
    """Get list of configured topics for batch detection."""
    from app.config.config import load_config

    config = load_config()
    topics = [{"name": t["name"], "description": t.get("description", "")} for t in config.get("topics", [])]

    return {
        "count": len(topics),
        "topics": topics
    }


# ============================================================================
# Emerging Topics Endpoints
# ============================================================================

@router.get("/topics")
async def get_emerging_topics(
    topic: Optional[str] = Query(None, description="Topic filter"),
    days_back: int = Query(7, ge=1, le=30, description="Days to look back"),
    detection_type: Optional[str] = Query(None, description="Filter by type: new_cluster, accelerating, splitting, proto_cluster"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    session=Depends(verify_session)
):
    """
    Get detected emerging topics.
    """
    service = get_emerging_topics_service()
    topics = service.get_emerging_topics(
        topic_filter=topic,
        days_back=days_back,
        detection_type=detection_type,
        min_confidence=min_confidence,
        limit=limit
    )
    return {
        "count": len(topics),
        "topics": [t.to_dict() for t in topics]
    }


@router.get("/retired")
async def get_retired_topics(
    topic: Optional[str] = Query(None, description="Topic filter"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    session=Depends(verify_session)
):
    """
    Get retired emerging topics.
    """
    service = get_emerging_topics_service()
    topics = service.get_retired_topics(
        topic_filter=topic,
        limit=limit
    )
    return {
        "count": len(topics),
        "topics": [t.to_dict() for t in topics]
    }


@router.get("/topics/{topic_id}")
async def get_emerging_topic_detail(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Get detailed info for a specific emerging topic.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # The canonical v2 projection. The analysis blocks (actors, events,
        # implications, organization_implications, signals, synthesis) and the
        # component scores were missing here, so the UI's detail panel fell back
        # to v1 fields and "model_used" was read off a synthesis column that was
        # never selected — which is why it always showed a guessed model.
        stmt = text("""
            SELECT
                et.id, et.topic_label, et.topic_description, et.detection_date,
                et.detection_type, et.cluster_id, et.article_count, et.growth_rate,
                et.velocity, et.confidence_score, et.key_themes, et.representative_keywords,
                et.emergence_rationale, et.article_uris, et.sample_article_uris, et.status,
                et.topic_filter,
                et.actors, et.events, et.implications, et.organization_implications,
                et.signals, et.synthesis, et.future_horizons,
                et.volume_score, et.velocity_score, et.diversity_score,
                et.novelty_score, et.composite_score,
                et.first_detection_date, et.last_detection_date,
                et.detection_count, et.consecutive_detections, et.missed_runs,
                th.source_count
            FROM emerging_topics et
            LEFT JOIN LATERAL (
                SELECT h.source_count
                FROM topic_history h
                JOIN detection_runs dr ON dr.id = h.detection_run_id
                WHERE h.topic_id = et.id
                ORDER BY dr.run_date DESC, h.id DESC
                LIMIT 1
            ) th ON TRUE
            WHERE et.id = :topic_id
        """)

        result = conn.execute(stmt, {"topic_id": topic_id}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Emerging topic not found")

        row = dict(result._mapping)

        def _as_dict(value):
            """JSONB comes back parsed; older rows may hold a JSON string."""
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (ValueError, TypeError):
                    return {}
            return value or {}

        for jsonb_field in (
            "actors", "events", "implications", "organization_implications",
            "signals", "synthesis",
        ):
            row[jsonb_field] = _as_dict(row.get(jsonb_field))

        # Fetch article details with novelty scores, in the topic's own ranking
        article_uris = row.get("article_uris") or []
        articles = []

        if article_uris:
            wanted = article_uris[:20]
            placeholders = ", ".join([f":uri_{i}" for i in range(len(wanted))])
            params = {f"uri_{i}": uri for i, uri in enumerate(wanted)}

            # LATERAL, not a join: an article accumulates one novelty row per
            # calculation date, and a plain join returned the article once per
            # row — the same headline listed three times.
            article_stmt = text(f"""
                SELECT a.uri, a.title, a.summary, a.news_source, a.publication_date,
                       COALESCE(ns.composite_novelty_score, 0) as novelty_score,
                       ns.knn_distance_score,
                       ns.is_outlier
                FROM articles a
                LEFT JOIN LATERAL (
                    SELECT n.composite_novelty_score, n.knn_distance_score, n.is_outlier
                    FROM article_novelty_scores n
                    WHERE n.article_uri = a.uri
                    ORDER BY n.calculation_date DESC, n.id DESC
                    LIMIT 1
                ) ns ON TRUE
                WHERE a.uri IN ({placeholders})
            """)

            article_result = conn.execute(article_stmt, params)
            by_uri = {}
            for a_row in article_result.mappings():
                by_uri[a_row["uri"]] = {
                    **dict(a_row),
                    "novelty_score": round(a_row["novelty_score"], 1) if a_row["novelty_score"] else 0,
                }
            articles = [by_uri[uri] for uri in wanted if uri in by_uri]

        # model_used is recorded on the topic's synthesis at analysis time.
        synthesis = row.get("synthesis") or {}
        model_used = synthesis.get("model_used") if isinstance(synthesis, dict) else None
        if not model_used:
            # Older rows predate the field. Say so rather than inventing one.
            model_used = None

        return {
            **row,
            "detection_date": str(row["detection_date"]) if row["detection_date"] else None,
            "first_detection_date": str(row["first_detection_date"]) if row.get("first_detection_date") else None,
            "last_detection_date": str(row["last_detection_date"]) if row.get("last_detection_date") else None,
            "trend_score": {
                "volume": round(row.get("volume_score") or 0, 1),
                "velocity": round(row.get("velocity_score") or 0, 1),
                "diversity": round(row.get("diversity_score") or 0, 1),
                "novelty": round(row.get("novelty_score") or 0, 1),
                "composite": round(row.get("composite_score") or 0, 1),
            },
            "source_count": row.get("source_count") or 0,
            "articles": articles,
            "model_used": model_used
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching topic detail {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error fetching topic: {str(exc)}")
    finally:
        if conn:
            conn.close()


@router.delete("/topics/{topic_id}")
async def delete_emerging_topic(
    topic_id: int,
    session=Depends(require_admin)
):
    """
    Delete an emerging topic.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()
        stmt = text("DELETE FROM emerging_topics WHERE id = :topic_id")
        result = conn.execute(stmt, {"topic_id": topic_id})
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Topic not found")

        logger.info(f"Deleted emerging topic {topic_id}")
        return {"success": True, "message": f"Deleted topic {topic_id}"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error deleting topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.delete("/topics")
async def clear_emerging_topics(
    topic: Optional[str] = Query(None, description="Topic filter to clear (optional, clears all if not specified)"),
    session=Depends(require_admin)
):
    """
    Clear all emerging topics, optionally filtered by topic.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        if topic:
            stmt = text("DELETE FROM emerging_topics WHERE topic_filter = :topic")
            result = conn.execute(stmt, {"topic": topic})
        else:
            stmt = text("DELETE FROM emerging_topics")
            result = conn.execute(stmt)

        conn.commit()

        logger.info(f"Cleared {result.rowcount} emerging topics" + (f" for topic '{topic}'" if topic else ""))
        return {
            "success": True,
            "deleted_count": result.rowcount,
            "message": f"Cleared {result.rowcount} topics"
        }

    except Exception as exc:
        logger.error(f"Error clearing topics: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Detection Runs & History Endpoints
# ============================================================================

@router.get("/runs")
async def get_detection_runs(
    topic: Optional[str] = Query(None, description="Topic filter"),
    days_back: int = Query(30, ge=1, le=365, description="Days to look back"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    session=Depends(verify_session)
):
    """
    Get history of detection runs.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        filter_clause = "WHERE run_date >= NOW() - INTERVAL ':days_back days'"
        params = {"days_back": days_back, "limit": limit}

        if topic:
            filter_clause += " AND topic_filter = :topic"
            params["topic"] = topic

        stmt = text(f"""
            SELECT
                id, run_date, topic_filter, config, topics_detected,
                articles_sampled, model_used, duration_seconds, status, created_at
            FROM detection_runs
            {filter_clause}
            ORDER BY run_date DESC
            LIMIT :limit
        """.replace(":days_back days", f"{days_back} days"))

        result = conn.execute(stmt, params)

        runs = []
        for row in result.mappings():
            runs.append({
                "id": row["id"],
                "run_date": row["run_date"].isoformat() if row["run_date"] else None,
                "topic_filter": row["topic_filter"],
                "config": row["config"],
                "topics_detected": row["topics_detected"],
                "articles_sampled": row["articles_sampled"],
                "model_used": row["model_used"],
                "duration_seconds": row["duration_seconds"],
                "status": row["status"],
            })

        return {"count": len(runs), "runs": runs}

    except Exception as exc:
        logger.error(f"Error getting detection runs: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.get("/topics/{topic_id}/history")
async def get_topic_history(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Get historical snapshots for a topic across detection runs.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        stmt = text("""
            SELECT
                th.id, th.detection_run_id, dr.run_date,
                th.article_count, th.growth_rate, th.velocity, th.confidence_score,
                th.volume_score, th.velocity_score, th.diversity_score,
                th.novelty_score, th.composite_score, th.source_count,
                th.captured_at
            FROM topic_history th
            JOIN detection_runs dr ON th.detection_run_id = dr.id
            WHERE th.topic_id = :topic_id
            ORDER BY dr.run_date ASC
        """)

        result = conn.execute(stmt, {"topic_id": topic_id})

        history = []
        for row in result.mappings():
            history.append({
                "id": row["id"],
                "run_id": row["detection_run_id"],
                "run_date": row["run_date"].isoformat() if row["run_date"] else None,
                "article_count": row["article_count"],
                "growth_rate": row["growth_rate"],
                "velocity": row["velocity"],
                "confidence_score": row["confidence_score"],
                "volume_score": row["volume_score"],
                "velocity_score": row["velocity_score"],
                "diversity_score": row["diversity_score"],
                "novelty_score": row["novelty_score"],
                "composite_score": row["composite_score"],
                "source_count": row["source_count"],
            })

        return {
            "topic_id": topic_id,
            "count": len(history),
            "history": history
        }

    except Exception as exc:
        logger.error(f"Error getting topic history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.get("/batch-history")
async def get_batch_history(
    topic_ids: str = Query(..., description="Comma-separated topic IDs"),
    session=Depends(verify_session)
):
    """
    Get history for multiple topics in a single request.
    Returns a dictionary keyed by topic_id with history arrays.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    # Parse topic IDs
    try:
        ids = [int(x.strip()) for x in topic_ids.split(",") if x.strip()]
        if not ids:
            return {"histories": {}}
        if len(ids) > 50:
            raise HTTPException(status_code=400, detail="Maximum 50 topics allowed")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid topic_ids format")

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        stmt = text("""
            SELECT
                th.topic_id, th.detection_run_id, dr.run_date,
                th.composite_score, th.volume_score, th.velocity_score,
                th.diversity_score, th.novelty_score
            FROM topic_history th
            JOIN detection_runs dr ON th.detection_run_id = dr.id
            WHERE th.topic_id = ANY(:topic_ids)
            ORDER BY th.topic_id, dr.run_date ASC
        """)

        result = conn.execute(stmt, {"topic_ids": ids})

        # Group by topic_id
        histories: Dict[int, list] = {tid: [] for tid in ids}
        for row in result.mappings():
            tid = row["topic_id"]
            if tid in histories:
                histories[tid].append({
                    "run_date": row["run_date"].isoformat() if row["run_date"] else None,
                    "composite_score": row["composite_score"],
                    "volume_score": row["volume_score"],
                    "velocity_score": row["velocity_score"],
                    "diversity_score": row["diversity_score"],
                    "novelty_score": row["novelty_score"],
                })

        return {"histories": histories}

    except Exception as exc:
        logger.error(f"Error getting batch history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.get("/topics/{topic_id}/trajectory")
async def get_topic_trajectory(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Get computed trajectory analysis for a topic.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Get topic info
        topic_stmt = text("""
            SELECT first_detection_date, last_detection_date, detection_count, consecutive_detections
            FROM emerging_topics WHERE id = :topic_id
        """)
        topic_row = conn.execute(topic_stmt, {"topic_id": topic_id}).fetchone()

        if not topic_row:
            raise HTTPException(status_code=404, detail="Topic not found")

        # Get history for trend calculation
        history_stmt = text("""
            SELECT th.composite_score, th.article_count
            FROM topic_history th
            JOIN detection_runs dr ON th.detection_run_id = dr.id
            WHERE th.topic_id = :topic_id
            ORDER BY dr.run_date ASC
        """)
        history = conn.execute(history_stmt, {"topic_id": topic_id}).fetchall()

        # Calculate trajectory
        trajectory = "stable"
        avg_score_change = 0.0

        if len(history) >= 2:
            scores = [h[0] for h in history if h[0] is not None]
            if len(scores) >= 2:
                changes = [scores[i] - scores[i-1] for i in range(1, len(scores))]
                avg_score_change = sum(changes) / len(changes)

                if avg_score_change > 5:
                    trajectory = "rising"
                elif avg_score_change < -5:
                    trajectory = "declining"
                elif max(changes) - min(changes) > 20:
                    trajectory = "volatile"

        return {
            "topic_id": topic_id,
            "first_detection_date": topic_row[0].isoformat() if topic_row[0] else None,
            "last_detection_date": topic_row[1].isoformat() if topic_row[1] else None,
            "detection_count": topic_row[2] or 1,
            "consecutive_detections": topic_row[3] or 1,
            "trajectory": trajectory,
            "avg_score_change": round(avg_score_change, 2),
            "history_points": len(history),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error getting topic trajectory: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Novelty Endpoints
# ============================================================================

@router.get("/novelty-scores")
async def get_novelty_scores(
    topic: Optional[str] = Query(None, description="Topic filter"),
    date: Optional[str] = Query(None, description="Calculation date (YYYY-MM-DD)"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum novelty score"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    session=Depends(verify_session)
):
    """
    Get article novelty scores.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        filter_clause = "WHERE ns.composite_novelty_score >= :min_score"
        params = {"min_score": min_score, "limit": limit}

        if date:
            filter_clause += " AND ns.calculation_date = :date"
            params["date"] = date
        else:
            filter_clause += " AND ns.calculation_date >= CURRENT_DATE - 7"

        if topic:
            filter_clause += " AND a.topic = :topic"
            params["topic"] = topic

        # One row per article — its most recent scoring run inside the window.
        # Without DISTINCT ON, an article re-scored on seven consecutive days
        # took seven of the result slots. With an explicit date this is a no-op:
        # (article_uri, calculation_date) is unique.
        stmt = text(f"""
            SELECT * FROM (
                SELECT DISTINCT ON (ns.article_uri)
                    ns.article_uri,
                    a.title as article_title,
                    ns.composite_novelty_score,
                    ns.knn_distance_score,
                    ns.density_score,
                    ns.centroid_distance_score,
                    ns.is_outlier,
                    ns.calculation_date
                FROM article_novelty_scores ns
                JOIN articles a ON a.uri = ns.article_uri
                {filter_clause}
                ORDER BY ns.article_uri, ns.calculation_date DESC, ns.id DESC
            ) latest
            ORDER BY composite_novelty_score DESC, article_uri
            LIMIT :limit
        """)

        result = conn.execute(stmt, params)

        scores = []
        for row in result.mappings():
            scores.append({
                **dict(row),
                "calculation_date": str(row["calculation_date"]) if row["calculation_date"] else None
            })

        return {"count": len(scores), "scores": scores}

    finally:
        if conn:
            conn.close()


@router.get("/high-novelty")
async def get_high_novelty_articles(
    threshold: float = Query(70.0, ge=0.0, le=100.0, description="Novelty threshold"),
    days_back: int = Query(3, ge=1, le=14, description="Days to look back"),
    topic: Optional[str] = Query(None, description="Topic filter"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    session=Depends(verify_session)
):
    """
    Get articles with high novelty scores.
    """
    service = get_emerging_topics_service()
    articles = service.get_high_novelty_articles(
        threshold=threshold,
        days_back=days_back,
        topic_filter=topic,
        limit=limit
    )
    return {"count": len(articles), "articles": articles}


# ============================================================================
# Proto-Cluster Endpoints
# ============================================================================

@router.get("/proto-clusters")
async def get_proto_clusters(
    days_back: int = Query(7, ge=1, le=14, description="Days to look back"),
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session)
):
    """
    Get proto-clusters (outliers that are coalescing into potential clusters).
    """
    service = get_emerging_topics_service()
    topics = service.get_emerging_topics(
        topic_filter=topic,
        days_back=days_back,
        detection_type="proto_cluster",
        limit=50
    )
    return {
        "count": len(topics),
        "proto_clusters": [t.to_dict() for t in topics]
    }


# ============================================================================
# Cluster Evolution Endpoints
# ============================================================================

@router.get("/cluster-evolution/{cluster_id}")
async def get_cluster_evolution(
    cluster_id: str,
    days_back: int = Query(14, ge=1, le=30, description="Days to look back"),
    session=Depends(verify_session)
):
    """
    Get temporal evolution of a cluster.
    """
    from app.services.emerging_topics import TemporalTracker

    tracker = TemporalTracker()
    metrics = tracker.calculate_velocity_metrics(cluster_id, days_back)

    return {
        "cluster_id": cluster_id,
        "metrics": metrics
    }


@router.get("/cluster-snapshots")
async def get_cluster_snapshots(
    date: str = Query(..., description="Snapshot date (YYYY-MM-DD)"),
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(verify_session)
):
    """
    Get cluster snapshots for a specific date.
    """
    from datetime import datetime
    from app.services.emerging_topics import TemporalTracker

    try:
        snapshot_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    tracker = TemporalTracker()
    snapshots = tracker.get_snapshots(snapshot_date, topic)

    return {
        "date": date,
        "topic_filter": topic,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots
    }


# ============================================================================
# Tracking Endpoints
# ============================================================================

@router.get("/tracked")
async def get_tracked_topics(
    session=Depends(verify_session)
):
    """
    Get all emerging topics tracked by the current user.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Ensure tracking table exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tracked_emerging_topics (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                topic_id INTEGER NOT NULL REFERENCES emerging_topics(id) ON DELETE CASCADE,
                tracked_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, topic_id)
            )
        """))
        conn.commit()

        # Get user identifier from session
        user_id = session.get("user", {}).get("email", "anonymous")

        # Fetch tracked topics with their details
        stmt = text("""
            SELECT
                et.id, et.topic_label, et.topic_description, et.detection_date,
                et.detection_type, et.article_count, et.velocity, et.key_themes,
                et.representative_keywords, et.confidence_score,
                tet.tracked_at
            FROM tracked_emerging_topics tet
            JOIN emerging_topics et ON et.id = tet.topic_id
            WHERE tet.user_id = :user_id
            ORDER BY tet.tracked_at DESC
        """)

        result = conn.execute(stmt, {"user_id": user_id})
        topics = []
        for row in result.mappings():
            topic_dict = dict(row)
            topic_dict["detection_date"] = str(topic_dict["detection_date"]) if topic_dict["detection_date"] else None
            topic_dict["tracked_at"] = str(topic_dict["tracked_at"]) if topic_dict["tracked_at"] else None
            topic_dict["key_entities"] = topic_dict.pop("representative_keywords", [])
            topic_dict["trend_score"] = {"composite": topic_dict.pop("confidence_score", 0) * 100}
            topics.append(topic_dict)

        return {"topics": topics, "count": len(topics)}

    except Exception as exc:
        logger.error(f"Error fetching tracked topics: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.post("/topics/{topic_id}/track")
async def track_topic(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Track (save) an emerging topic for the current user.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Ensure tracking table exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tracked_emerging_topics (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                topic_id INTEGER NOT NULL REFERENCES emerging_topics(id) ON DELETE CASCADE,
                tracked_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, topic_id)
            )
        """))
        conn.commit()

        # Get user identifier from session
        user_id = session.get("user", {}).get("email", "anonymous")

        # Check if topic exists
        check_stmt = text("SELECT id FROM emerging_topics WHERE id = :topic_id")
        topic = conn.execute(check_stmt, {"topic_id": topic_id}).fetchone()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")

        # Insert tracking record (ignore if already exists)
        stmt = text("""
            INSERT INTO tracked_emerging_topics (user_id, topic_id, tracked_at)
            VALUES (:user_id, :topic_id, NOW())
            ON CONFLICT (user_id, topic_id) DO NOTHING
        """)
        conn.execute(stmt, {"user_id": user_id, "topic_id": topic_id})
        conn.commit()

        logger.info(f"User {user_id} tracked topic {topic_id}")
        return {"success": True, "message": f"Topic {topic_id} tracked"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error tracking topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.delete("/topics/{topic_id}/track")
async def untrack_topic(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Untrack (remove from saved) an emerging topic for the current user.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Get user identifier from session
        user_id = session.get("user", {}).get("email", "anonymous")

        # Delete tracking record
        stmt = text("""
            DELETE FROM tracked_emerging_topics
            WHERE user_id = :user_id AND topic_id = :topic_id
        """)
        result = conn.execute(stmt, {"user_id": user_id, "topic_id": topic_id})
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Topic not tracked")

        logger.info(f"User {user_id} untracked topic {topic_id}")
        return {"success": True, "message": f"Topic {topic_id} untracked"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error untracking topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.post("/topics/{topic_id}/retire")
async def retire_topic(
    topic_id: int,
    session=Depends(require_admin)
):
    """
    Manually retire an emerging topic (move to archived/retired status).
    """
    service = get_emerging_topics_service()
    success = service.retire_topic(topic_id)

    if not success:
        raise HTTPException(status_code=404, detail="Topic not found or already retired")

    logger.info(f"Retired topic {topic_id}")
    return {"success": True, "message": f"Topic {topic_id} retired"}


@router.post("/topics/{topic_id}/restore")
async def restore_topic(
    topic_id: int,
    session=Depends(require_admin)
):
    """
    Restore a retired emerging topic back to active status.
    """
    service = get_emerging_topics_service()
    success = service.restore_topic(topic_id)

    if not success:
        raise HTTPException(status_code=404, detail="Topic not found or already active")

    logger.info(f"Restored topic {topic_id}")
    return {"success": True, "message": f"Topic {topic_id} restored"}


@router.get("/topics/{topic_id}/track-status")
async def get_track_status(
    topic_id: int,
    session=Depends(verify_session)
):
    """
    Check if the current user has tracked a specific topic.
    """
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Get user identifier from session
        user_id = session.get("user", {}).get("email", "anonymous")

        # Check if tracked
        stmt = text("""
            SELECT 1 FROM tracked_emerging_topics
            WHERE user_id = :user_id AND topic_id = :topic_id
        """)
        result = conn.execute(stmt, {"user_id": user_id, "topic_id": topic_id}).fetchone()

        return {"tracked": result is not None, "topic_id": topic_id}

    except Exception as exc:
        logger.error(f"Error checking track status for topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


# ============================================================================
# Dashboard Widget Endpoint
# ============================================================================

@router.get("/dashboard-widget")
async def get_dashboard_widget_data(
    topic: Optional[str] = Query(None, description="Topic filter"),
    limit: int = Query(5, ge=1, le=10, description="Number of topics to show"),
    session=Depends(verify_session)
):
    """
    Get data for the emerging topics dashboard widget.
    Returns a compact summary suitable for displaying in a widget.
    """
    service = get_emerging_topics_service()

    # Get recent emerging topics
    topics = service.get_emerging_topics(
        topic_filter=topic,
        days_back=7,
        min_confidence=0.5,
        limit=limit
    )

    # Get summary stats
    all_recent = service.get_emerging_topics(
        topic_filter=topic,
        days_back=7,
        limit=100
    )

    by_type = {}
    for t in all_recent:
        by_type[t.detection_type] = by_type.get(t.detection_type, 0) + 1

    return {
        "summary": {
            "total_emerging_topics": len(all_recent),
            "by_type": by_type,
            "accelerating_count": by_type.get("accelerating", 0),
            "new_cluster_count": by_type.get("new_cluster", 0),
            "proto_cluster_count": by_type.get("proto_cluster", 0),
        },
        "top_topics": [
            {
                "id": t.id,
                "label": t.topic_label,
                "description": t.topic_description[:100] + "..." if len(t.topic_description) > 100 else t.topic_description,
                "type": t.detection_type,
                "article_count": t.article_count,
                "velocity": t.velocity,
                "confidence": round(t.confidence_score, 2),
                "themes": t.key_themes[:3],
            }
            for t in topics
        ]
    }


# ============================================================================
# Schedule & Notification Endpoints
# ============================================================================

class ScheduleSettingsRequest(BaseModel):
    """Request model for schedule settings."""
    schedule_enabled: Optional[bool] = None
    check_interval: Optional[int] = Field(None, ge=1, le=168)  # 1-168 hours (1 week)
    interval_unit: Optional[str] = Field(None, pattern="^(hours|days)$")
    min_articles: Optional[int] = Field(None, ge=10, le=1000)
    sample_size: Optional[int] = Field(None, ge=50, le=500)
    days_back: Optional[int] = Field(None, ge=1, le=30)
    model: Optional[str] = None
    topic_filter: Optional[str] = None


class NotificationSettingsRequest(BaseModel):
    """Request model for notification settings."""
    notifications_enabled: Optional[bool] = None
    notification_channels: Optional[Dict[str, bool]] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    cooldown_minutes: Optional[int] = Field(None, ge=30, le=1440)  # 30 min - 24 hours
    email_recipients: Optional[List[str]] = None
    bluesky_handle: Optional[str] = None
    detection_type_filters: Optional[List[str]] = None

    @field_validator("detection_type_filters")
    @classmethod
    def _check_filters(cls, value):
        """Reject unknown filters, and store legacy ones under their v2 name."""
        if value is None:
            return None
        try:
            return validate_filters(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


@router.get("/schedule/status")
async def get_schedule_status(
    session=Depends(verify_session)
):
    """Get current schedule and monitor status."""
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import datetime, timedelta

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Get settings
        settings_result = conn.execute(text("""
            SELECT
                schedule_enabled, check_interval, interval_unit, min_articles,
                sample_size, days_back, model, topic_filter
            FROM emerging_topics_settings
            WHERE id = 1
        """))
        settings = settings_result.mappings().first()

        # Get status
        status_result = conn.execute(text("""
            SELECT
                last_check_time, next_check_time, topics_detected,
                articles_analyzed, last_error, is_running
            FROM emerging_topics_monitor_status
            WHERE id = 1
        """))
        status = status_result.mappings().first()

        settings_dict = dict(settings) if settings else {}
        status_dict = dict(status) if status else {}

        # Calculate next_check_time if schedule is enabled but next_check_time is missing
        if settings_dict.get('schedule_enabled') and not status_dict.get('next_check_time'):
            check_interval = settings_dict.get('check_interval', 24)
            interval_unit = settings_dict.get('interval_unit', 'hours')

            if interval_unit == 'hours':
                interval_seconds = check_interval * 3600
            elif interval_unit == 'days':
                interval_seconds = check_interval * 86400
            else:  # minutes
                interval_seconds = check_interval * 60

            # Calculate from last_check_time if available, otherwise from now
            base_time = status_dict.get('last_check_time')
            if isinstance(base_time, str):
                base_time = datetime.fromisoformat(base_time.replace('Z', '+00:00'))
            if not base_time:
                base_time = datetime.now()

            next_check = base_time + timedelta(seconds=interval_seconds)
            status_dict['next_check_time'] = next_check.isoformat()

        return {
            "settings": settings_dict,
            "status": status_dict,
        }
    finally:
        conn.close()


@router.post("/schedule/settings")
async def update_schedule_settings(
    request: ScheduleSettingsRequest,
    session=Depends(require_admin)
):
    """Update schedule settings."""
    from app.database import get_database_instance
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        updates = []
        params = {}

        if request.schedule_enabled is not None:
            updates.append("schedule_enabled = :schedule_enabled")
            params["schedule_enabled"] = request.schedule_enabled
        if request.check_interval is not None:
            updates.append("check_interval = :check_interval")
            params["check_interval"] = request.check_interval
        if request.interval_unit is not None:
            updates.append("interval_unit = :interval_unit")
            params["interval_unit"] = request.interval_unit
        if request.min_articles is not None:
            updates.append("min_articles = :min_articles")
            params["min_articles"] = request.min_articles
        if request.sample_size is not None:
            updates.append("sample_size = :sample_size")
            params["sample_size"] = request.sample_size
        if request.days_back is not None:
            updates.append("days_back = :days_back")
            params["days_back"] = request.days_back
        if request.model is not None:
            updates.append("model = :model")
            params["model"] = request.model
        if request.topic_filter is not None:
            updates.append("topic_filter = :topic_filter")
            params["topic_filter"] = request.topic_filter if request.topic_filter else None

        if updates:
            updates.append("updated_at = NOW()")
            conn.execute(text(f"""
                UPDATE emerging_topics_settings
                SET {', '.join(updates)}
                WHERE id = 1
            """), params)
            conn.commit()

        return {"success": True, "message": "Schedule settings updated"}
    except Exception as e:
        logger.error(f"Failed to update schedule settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/schedule/run-now")
async def run_detection_now(
    topic: Optional[str] = Query(None, description="Topic filter"),
    session=Depends(require_admin)
):
    """Trigger an immediate detection run."""
    from app.database import get_database_instance
    from app.tasks.emerging_topics_monitor import run_detection_now

    try:
        db = get_database_instance()
        result = await run_detection_now(db, topic_filter=topic)

        return {
            "success": result.get("success", False),
            "topics_detected": result.get("topics_detected", 0),
            "articles_analyzed": result.get("articles_analyzed", 0),
            "run_id": result.get("run_id"),
            "error": result.get("error"),
            "code": result.get("code"),
        }
    except DetectionAlreadyRunning as exc:
        raise _lock_conflict(exc)
    except Exception as e:
        logger.exception("Failed to run detection")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notifications/settings")
async def get_notification_settings(
    session=Depends(verify_session)
):
    """Get notification settings."""
    from app.database import get_database_instance
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        result = conn.execute(text("""
            SELECT
                notifications_enabled, notification_channels, min_confidence,
                cooldown_minutes, email_recipients, bluesky_handle,
                detection_type_filters, last_notification_time
            FROM emerging_topics_settings
            WHERE id = 1
        """))
        row = result.mappings().first()

        if row:
            return {
                "notifications_enabled": row["notifications_enabled"],
                "notification_channels": row["notification_channels"] or {},
                "min_confidence": row["min_confidence"],
                "cooldown_minutes": row["cooldown_minutes"],
                "email_recipients": row["email_recipients"] or [],
                "bluesky_handle": row["bluesky_handle"],
                # Legacy values are mapped to their v2 equivalent on the way
                # out, so the UI shows what the monitor will actually match.
                "detection_type_filters": normalize_filters(row["detection_type_filters"]),
                "stored_detection_type_filters": row["detection_type_filters"] or [],
                "allowed_detection_type_filters": list(ALLOWED_FILTERS),
                "last_notification_time": row["last_notification_time"].isoformat() if row["last_notification_time"] else None,
            }
        return {}
    finally:
        conn.close()


@router.post("/notifications/settings")
async def update_notification_settings(
    request: NotificationSettingsRequest,
    session=Depends(require_admin)
):
    """Update notification settings."""
    from app.database import get_database_instance
    from sqlalchemy import text
    import json

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        updates = []
        params = {}

        if request.notifications_enabled is not None:
            updates.append("notifications_enabled = :notifications_enabled")
            params["notifications_enabled"] = request.notifications_enabled
        if request.notification_channels is not None:
            updates.append("notification_channels = :channels::jsonb")
            params["channels"] = json.dumps(request.notification_channels)
        if request.min_confidence is not None:
            updates.append("min_confidence = :min_confidence")
            params["min_confidence"] = request.min_confidence
        if request.cooldown_minutes is not None:
            updates.append("cooldown_minutes = :cooldown_minutes")
            params["cooldown_minutes"] = request.cooldown_minutes
        if request.email_recipients is not None:
            updates.append("email_recipients = :recipients::jsonb")
            params["recipients"] = json.dumps(request.email_recipients)
        if request.bluesky_handle is not None:
            updates.append("bluesky_handle = :bluesky_handle")
            params["bluesky_handle"] = request.bluesky_handle if request.bluesky_handle else None
        if request.detection_type_filters is not None:
            updates.append("detection_type_filters = :filters::jsonb")
            params["filters"] = json.dumps(request.detection_type_filters)

        if updates:
            updates.append("updated_at = NOW()")
            conn.execute(text(f"""
                UPDATE emerging_topics_settings
                SET {', '.join(updates)}
                WHERE id = 1
            """), params)
            conn.commit()

        return {"success": True, "message": "Notification settings updated"}
    except Exception as e:
        logger.error(f"Failed to update notification settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/notifications/test")
async def send_test_notification(
    session=Depends(require_admin)
):
    """Send a test notification through enabled channels."""
    from app.database import get_database_instance
    from app.services.emerging_topics_notification_service import EmergingTopicsNotificationService
    from sqlalchemy import text

    db = get_database_instance()
    conn = db._temp_get_connection()

    try:
        # Get current settings
        result = conn.execute(text("""
            SELECT notification_channels, email_recipients, bluesky_handle
            FROM emerging_topics_settings
            WHERE id = 1
        """))
        row = result.mappings().first()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Settings not found")

        channels = row["notification_channels"] or {}
        email_recipients = row["email_recipients"] or []
        bluesky_handle = row["bluesky_handle"]

        # Send test notification
        notification_service = EmergingTopicsNotificationService(db)
        results = await notification_service.send_test_notification(
            channels=channels,
            email_recipients=email_recipients,
            bluesky_handle=bluesky_handle
        )

        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to send test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Future Horizons Integration
# ============================================================================

class FutureHorizonsRequest(BaseModel):
    """Request model for running Future Horizons on an emerging topic."""
    model: str = Field("gpt-5.4", description="AI model to use")
    future_horizon: int = Field(15, ge=5, le=30, description="Years into the future to project")


@router.post("/topics/{topic_id}/future-horizons")
async def analyze_topic_in_horizons(
    topic_id: int,
    request: FutureHorizonsRequest,
    session=Depends(verify_session)
):
    """
    Run Future Horizons (Futures Cone) analysis on an emerging topic.
    Uses the topic as the central driver/signal and projects forward.
    """
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.ai_models import get_ai_model
    from datetime import datetime
    from collections import Counter

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # 1. Fetch the emerging topic
        topic_stmt = text("""
            SELECT
                id, topic_label, topic_description, emergence_rationale,
                article_uris, key_themes, representative_keywords
            FROM emerging_topics
            WHERE id = :topic_id
        """)
        topic_row = conn.execute(topic_stmt, {"topic_id": topic_id}).fetchone()

        if not topic_row:
            raise HTTPException(status_code=404, detail="Emerging topic not found")

        topic_data = dict(topic_row._mapping)
        article_uris = topic_data.get("article_uris") or []

        if not article_uris:
            raise HTTPException(status_code=400, detail="Topic has no associated articles")

        # 2. Fetch full article data for those URIs
        articles = []
        if article_uris:
            placeholders = ", ".join([f":uri_{i}" for i in range(min(len(article_uris), 50))])
            params = {f"uri_{i}": uri for i, uri in enumerate(article_uris[:50])}

            article_stmt = text(f"""
                SELECT uri, title, summary, publication_date, sentiment, category,
                       future_signal, driver_type, time_to_impact, quality_score
                FROM articles
                WHERE uri IN ({placeholders})
            """)
            article_result = conn.execute(article_stmt, params)

            for row in article_result.mappings():
                articles.append(dict(row))

        conn.close()
        conn = None

        if not articles:
            raise HTTPException(status_code=400, detail="Could not fetch articles for topic")

        logger.info(f"Running Future Horizons on topic '{topic_data['topic_label']}' with {len(articles)} articles")

        # 3. Load the emerging topic driver prompt
        import os
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "prompts", "future_horizons", "emerging_topic_driver.json"
        )

        prompt_template = None
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                prompt_template = json.load(f)

        # 4. Prepare article references for the prompt
        article_refs = []
        for i, article in enumerate(articles[:30], 1):
            article_refs.append(f"[{i}] {article.get('title', 'Untitled')} ({article.get('publication_date', 'Unknown date')[:10] if article.get('publication_date') else 'Unknown date'})")

        # Analyze patterns
        sentiments = [a.get('sentiment') for a in articles if a.get('sentiment')]
        categories = [a.get('category') for a in articles if a.get('category')]
        drivers = [a.get('driver_type') for a in articles if a.get('driver_type')]
        signals = [a.get('future_signal') for a in articles if a.get('future_signal')]
        time_impacts = [a.get('time_to_impact') for a in articles if a.get('time_to_impact')]

        sentiment_counts = Counter(sentiments)
        category_counts = Counter(categories)
        driver_counts = Counter(drivers)

        articles_summary = f"""**Data Overview:**
- Total articles: {len(articles)}

**Sentiment Distribution:**
{chr(10).join([f"- {s}: {c}" for s, c in sentiment_counts.most_common(5)])}

**Category Distribution:**
{chr(10).join([f"- {cat}: {c}" for cat, c in category_counts.most_common(5)])}

**Driver Types:**
{chr(10).join([f"- {d}: {c}" for d, c in driver_counts.most_common(5)])}
"""

        # 5. Build the prompt
        if prompt_template:
            user_prompt = prompt_template.get("user_prompt", "")
            system_prompt = prompt_template.get("system_prompt", "")

            # Replace variables
            user_prompt = user_prompt.replace("{topic_label}", topic_data.get("topic_label", ""))
            user_prompt = user_prompt.replace("{topic_description}", topic_data.get("topic_description", ""))
            user_prompt = user_prompt.replace("{emergence_rationale}", topic_data.get("emergence_rationale", "Based on recent article analysis"))
            user_prompt = user_prompt.replace("{article_count}", str(len(articles)))
            user_prompt = user_prompt.replace("{article_references}", "\n".join(article_refs))
            user_prompt = user_prompt.replace("{articles}", articles_summary)
            user_prompt = user_prompt.replace("{org_context}", "")
            user_prompt = user_prompt.replace("{action_vocabulary}", "")
        else:
            # Fallback prompt
            system_prompt = "You are a strategic foresight expert using the Futures Cone framework."
            user_prompt = f"""EMERGING DRIVER: {topic_data.get('topic_label', '')}

Description: {topic_data.get('topic_description', '')}

Why This Is Emerging: {topic_data.get('emergence_rationale', 'Based on recent article analysis')}

Evidence Base ({len(articles)} articles):
{chr(10).join(article_refs)}

{articles_summary}

Project forward using the Futures Cone framework. Generate 10-14 scenarios:
- 3-4 Probable (most likely if trend continues)
- 3-4 Plausible (realistic given evidence)
- 2-3 Possible (could happen with major shifts)
- 2-3 Preferable (desirable outcomes)

Return JSON with this structure:
{{
  "scenarios": [
    {{
      "type": "probable|plausible|possible|preferable",
      "title": "Scenario title",
      "description": "How the emerging topic leads to this future (1-2 sentences)",
      "timeframe": "2025-2040",
      "sentiment": "Positive|Negative|Mixed|Neutral",
      "driver_connection": "How the topic drives this scenario"
    }}
  ]
}}"""

        # 6. Call AI model
        ai_model = get_ai_model(request.model)
        if not ai_model:
            raise HTTPException(status_code=400, detail=f"Model '{request.model}' not available")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = await ai_model.agenerate_response(messages)

        # 7. Parse response
        try:
            # Extract JSON from response
            json_str = response
            if '```json' in response:
                json_start = response.find('```json') + 7
                json_end = response.find('```', json_start)
                if json_end > json_start:
                    json_str = response[json_start:json_end]
            elif '{' in response:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                json_str = response[json_start:json_end]

            futures_data = json.loads(json_str)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Future Horizons response: {e}")
            logger.error(f"Response: {response[:500]}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response")

        # 8. Add metadata and calculate positions
        current_year = datetime.now().year

        if 'scenarios' in futures_data:
            # Group scenarios by type for positioning
            scenarios_by_type = {}
            for scenario in futures_data['scenarios']:
                scenario_type = scenario.get('type', 'plausible')
                if scenario_type not in scenarios_by_type:
                    scenarios_by_type[scenario_type] = []
                scenarios_by_type[scenario_type].append(scenario)

            # Add positions
            for scenario_type, scenarios in scenarios_by_type.items():
                for i, scenario in enumerate(scenarios):
                    timeframe = scenario.get('timeframe', '')
                    # Determine time period
                    time_period = 'mid'
                    if timeframe:
                        if any(y in timeframe for y in ['2025', '2026', '2027']):
                            time_period = 'short'
                        elif any(y in timeframe for y in ['2033', '2034', '2035', '2036', '2037', '2038', '2039', '2040']):
                            time_period = 'long'

                    # Calculate position (simplified grid)
                    type_row = {'probable': 0.2, 'plausible': 0.4, 'possible': 0.6, 'preferable': 0.15, 'wildcard': 0.8}
                    time_col = {'short': 0.2, 'mid': 0.5, 'long': 0.8}

                    base_y = type_row.get(scenario_type, 0.4) * 100
                    base_x = time_col.get(time_period, 0.5) * 100

                    # Offset for multiple scenarios of same type
                    offset = (i - len(scenarios) / 2) * 8

                    scenario['position'] = {
                        'x': max(5, min(95, base_x + offset)),
                        'y': max(5, min(95, base_y))
                    }

        # Add timeline
        futures_data['timeline'] = [
            {'year': current_year, 'label': 'Present'},
            {'year': current_year + 3, 'label': 'Short-term'},
            {'year': current_year + 8, 'label': 'Mid-term'},
            {'year': current_year + 15, 'label': 'Long-term'}
        ]

        futures_data['metadata'] = {
            'topic_id': topic_id,
            'topic_label': topic_data.get('topic_label'),
            'topic_description': topic_data.get('topic_description'),
            'emergence_rationale': topic_data.get('emergence_rationale'),
            'articles_analyzed': len(articles),
            'model_used': request.model,
            'generated_at': datetime.now().isoformat(),
            'analysis_type': 'emerging_topic_driver'
        }

        logger.info(f"Generated Future Horizons with {len(futures_data.get('scenarios', []))} scenarios")

        return futures_data

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error running Future Horizons on topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()


@router.post("/topics/{topic_id}/save-horizons")
async def save_topic_horizons(
    topic_id: int,
    horizons_data: dict,
    session=Depends(require_admin)
):
    """
    Save Future Horizons analysis to an emerging topic.
    """
    from app.database import get_database_instance
    from sqlalchemy import text

    db = get_database_instance()
    conn = None

    try:
        conn = db._temp_get_connection()

        # Update the topic with horizons data
        update_stmt = text("""
            UPDATE emerging_topics
            SET future_horizons = CAST(:horizons AS jsonb),
                updated_at = NOW()
            WHERE id = :topic_id
        """)

        result = conn.execute(update_stmt, {
            "topic_id": topic_id,
            "horizons": json.dumps(horizons_data)
        })
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Topic not found")

        logger.info(f"Saved Future Horizons to topic {topic_id}")

        return {"success": True, "message": "Future Horizons saved to theme"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error saving Future Horizons to topic {topic_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if conn:
            conn.close()
