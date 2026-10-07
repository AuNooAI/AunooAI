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
from app.security.session import verify_session, verify_session_api

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auto-ingest", tags=["auto-ingest"])

@router.get("/config", dependencies=[Depends(verify_session_api)])
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

@router.post("/config", dependencies=[Depends(verify_session_api)])
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

@router.get("/status", dependencies=[Depends(verify_session_api)])
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

async def _run_all_groups_task(progress_callback=None, username=None):
    """Collect every active keyword group now, each with its own providers,
    language, threshold and social handling.

    Until 7 Oct 2026 this button read unread rows from ``keyword_alerts``
    (empty on every site, and the query named columns ``articles`` does not
    have, so the route answered 500) and sent them through ingest with the
    topic ``general``, which no site has configured.
    """
    from app.database import get_database_instance
    from app.tasks.keyword_monitor import KeywordMonitor

    db = get_database_instance()
    result = await KeywordMonitor(db).check_all_groups(
        progress_callback=progress_callback, username=username)
    if username:
        try:
            db.facade.create_notification(
                username=username,
                type='auto_ingest_complete' if result.get("success") else 'auto_ingest_error',
                title='Auto-Collect Complete' if result.get("success") else 'Auto-Collect Failed',
                message=(f"Checked {result.get('groups_checked', 0)} groups: "
                         f"{result.get('new_articles', 0)} new articles, "
                         f"{len(result.get('errors') or [])} errors"),
                link='/gather'
            )
        except Exception as notif_err:
            logger.error(f"Failed to create auto-collect notification: {notif_err}")
    return {"success": bool(result.get("success")), "results": result}


@router.post("/run")
async def run_auto_ingest(background_tasks: BackgroundTasks, session=Depends(verify_session)):
    """Collect every active keyword group now, as a tracked background task."""
    try:
        from app.services.background_task_manager import get_task_manager
        from app.database import get_database_instance

        username = session.get("user", {}).get("username")
        db = get_database_instance()
        groups = db.facade.get_active_keyword_groups()
        if not groups:
            return JSONResponse({
                "success": True,
                "message": "No active keyword groups to collect",
                "total_groups": 0
            })

        task_manager = get_task_manager()
        task_id = task_manager.create_task(
            name="Auto-Collect: all groups",
            total_items=len(groups),
            metadata={"type": "auto_ingest", "groups_count": len(groups), "username": username}
        )
        background_tasks.add_task(task_manager.run_task, task_id, _run_all_groups_task,
                                  username=username)
        return JSONResponse({
            "success": True,
            "message": f"Collecting {len(groups)} keyword groups",
            "task_id": task_id,
            "total_groups": len(groups),
            "status_url": f"/api/background-tasks/task/{task_id}"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start auto-collect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/run-sync", dependencies=[Depends(verify_session_api)])
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

@router.get("/pending", dependencies=[Depends(verify_session_api)])
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

@router.get("/models", dependencies=[Depends(verify_session_api)])
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

@router.post("/enable", dependencies=[Depends(verify_session_api)])
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

@router.post("/disable", dependencies=[Depends(verify_session_api)])
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

@router.get("/stats", dependencies=[Depends(verify_session_api)])
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