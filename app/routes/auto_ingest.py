"""
API routes for auto-ingest functionality.
Handles configuration, status, and manual triggering of auto-ingest pipeline.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Optional
import logging

from app.services.auto_ingest_service import get_auto_ingest_service
from app.ai_models import get_available_models
from app.security.session import verify_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auto-ingest", tags=["auto-ingest"])

@router.get("/config")
async def get_auto_ingest_config():
    """Get current auto-ingest configuration"""
    try:
        service = get_auto_ingest_service()
        config = service.get_config()

        return JSONResponse({
            "success": True,
            "config": config
        })
    except Exception as e:
        logger.error(f"Failed to get auto-ingest config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/config")
async def update_auto_ingest_config(config_updates: Dict):
    """Update auto-ingest configuration"""
    try:
        service = get_auto_ingest_service()

        # Validate configuration updates
        valid_keys = {
            'enabled', 'quality_control_enabled', 'min_relevance_threshold',
            'llm_model', 'llm_temperature', 'batch_size', 'max_concurrent_batches'
        }

        invalid_keys = set(config_updates.keys()) - valid_keys
        if invalid_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid configuration keys: {invalid_keys}"
            )

        # Update configuration
        success = service.update_config(config_updates)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

        return JSONResponse({
            "success": True,
            "message": "Configuration updated successfully",
            "config": service.get_config()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update auto-ingest config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_auto_ingest_status():
    """Get current auto-ingest status"""
    try:
        service = get_auto_ingest_service()
        status = service.get_status()

        # Add additional status info
        pending_articles = await service.get_pending_articles(limit=100)
        status['pending_articles_count'] = len(pending_articles)

        return JSONResponse({
            "success": True,
            "status": status
        })
    except Exception as e:
        logger.error(f"Failed to get auto-ingest status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run")
async def run_auto_ingest(background_tasks: BackgroundTasks, session=Depends(verify_session)):
    """Manually trigger auto-ingest pipeline with progress tracking"""
    try:
        from app.services.background_task_manager import get_task_manager, run_auto_ingest_task
        from app.database import get_database_instance

        # Get username from session for notifications
        username = session.get("user", {}).get("username")

        # Get pending articles count for progress tracking
        db = get_database_instance()
        pending_articles = db.facade.get_unread_alerts()
        total_articles = len(pending_articles)

        if total_articles == 0:
            return JSONResponse({
                "success": True,
                "message": "No pending articles to process",
                "total_articles": 0
            })

        # Create notification for manual auto-ingest start
        try:
            db.facade.create_notification(
                username=username,
                type='auto_ingest_started',
                title='Auto-Collect Started',
                message=f'Processing {total_articles} pending articles...',
                link='/keyword-alerts'
            )
        except Exception as notif_err:
            logger.error(f"Failed to create auto-ingest start notification: {notif_err}")

        # Create background task with progress tracking
        task_manager = get_task_manager()
        task_id = task_manager.create_task(
            name="Auto-Ingest Pipeline",
            total_items=total_articles,
            metadata={"type": "auto_ingest", "articles_count": total_articles, "username": username}
        )

        # Run auto-ingest as background task with username for notifications
        background_tasks.add_task(
            task_manager.run_task,
            task_id,
            run_auto_ingest_task,
            username=username
        )

        return JSONResponse({
            "success": True,
            "message": "Auto-ingest pipeline started with database progress tracking",
            "task_id": task_id,
            "total_articles": total_articles,
            "status_url": f"/api/background-tasks/task/{task_id}"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start auto-ingest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run-sync")
async def run_auto_ingest_sync():
    """Run auto-ingest pipeline synchronously (for testing)"""
    try:
        service = get_auto_ingest_service()

        if service.is_running():
            raise HTTPException(
                status_code=409,
                detail="Auto-ingest is already running"
            )

        # Run auto-ingest synchronously
        results = await service.run_auto_ingest()

        return JSONResponse({
            "success": True,
            "results": results
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run auto-ingest sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pending")
async def get_pending_articles(limit: Optional[int] = 20):
    """Get articles pending auto-ingest"""
    try:
        service = get_auto_ingest_service()
        articles = await service.get_pending_articles(limit=limit)

        return JSONResponse({
            "success": True,
            "articles": articles,
            "count": len(articles)
        })

    except Exception as e:
        logger.error(f"Failed to get pending articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models")
async def get_available_llm_models():
    """Get available LLM models for auto-ingest"""
    try:
        models = get_available_models()

        return JSONResponse({
            "success": True,
            "models": models
        })

    except Exception as e:
        logger.error(f"Failed to get available models: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/enable")
async def enable_auto_ingest():
    """Enable auto-ingest"""
    try:
        service = get_auto_ingest_service()
        success = service.update_config({"enabled": True})

        if not success:
            raise HTTPException(status_code=500, detail="Failed to enable auto-ingest")

        return JSONResponse({
            "success": True,
            "message": "Auto-ingest enabled"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable auto-ingest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/disable")
async def disable_auto_ingest():
    """Disable auto-ingest"""
    try:
        service = get_auto_ingest_service()
        success = service.update_config({"enabled": False})

        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable auto-ingest")

        return JSONResponse({
            "success": True,
            "message": "Auto-ingest disabled"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable auto-ingest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_auto_ingest_stats():
    """Get auto-ingest statistics"""
    try:
        service = get_auto_ingest_service()

        # Get statistics from database
        with service.db.get_connection() as conn:
            cursor = conn.cursor()

            # Count auto-ingested articles
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE auto_ingested = 1
            """)
            auto_ingested_count = cursor.fetchone()[0]

            # Count pending alerts
            cursor.execute("""
                SELECT COUNT(*) FROM keyword_article_matches kam
                LEFT JOIN articles a ON kam.article_uri = a.uri
                WHERE (a.uri IS NULL OR a.auto_ingested = 0)
                  AND kam.article_uri IS NOT NULL
                  AND kam.article_uri != ''
                  AND kam.is_read = 0
            """)
            pending_count = cursor.fetchone()[0]

            # Get recent auto-ingest activity (based on articles with auto_ingested flag)
            cursor.execute("""
                SELECT DATE(submission_date) as date, COUNT(*) as count
                FROM articles
                WHERE auto_ingested = 1
                  AND submission_date >= datetime('now', '-30 days')
                GROUP BY DATE(submission_date)
                ORDER BY date DESC
                LIMIT 30
            """)
            recent_activity = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]

        return JSONResponse({
            "success": True,
            "stats": {
                "auto_ingested_total": auto_ingested_count,
                "pending_total": pending_count,
                "recent_activity": recent_activity,
                "status": service.get_status()
            }
        })

    except Exception as e:
        logger.error(f"Failed to get auto-ingest stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))