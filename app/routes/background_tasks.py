"""
API routes for managing background tasks and bulk operations.
Provides non-blocking endpoints for bulk analysis and saving operations.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Dict, Optional
import logging

from app.services.background_task_manager import (
    get_task_manager,
    run_bulk_analysis_task,
    run_bulk_save_task
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/background-tasks", tags=["background-tasks"])

@router.post("/bulk-analysis")
async def start_bulk_analysis(
    background_tasks: BackgroundTasks,
    request_data: Dict
):
    """Start a background bulk analysis task"""
    try:
        # Extract parameters
        urls = request_data.get("urls", [])
        topic = request_data.get("topic", "")
        summary_type = request_data.get("summary_type", "curious_ai")
        model_name = request_data.get("model_name", "gpt-4")
        summary_length = request_data.get("summary_length", 50)
        summary_voice = request_data.get("summary_voice", "neutral")

        if not urls:
            raise HTTPException(status_code=400, detail="No URLs provided")

        if not topic:
            raise HTTPException(status_code=400, detail="Topic is required")

        # Create background task
        task_manager = get_task_manager()
        task_id = task_manager.create_task(
            name=f"Bulk Analysis: {topic}",
            total_items=len(urls),
            metadata={
                "topic": topic,
                "url_count": len(urls),
                "summary_type": summary_type,
                "model_name": model_name
            }
        )

        # Start the background task
        background_tasks.add_task(
            task_manager.run_task,
            task_id,
            run_bulk_analysis_task,
            urls=urls,
            topic=topic,
            summary_type=summary_type,
            model_name=model_name,
            summary_length=summary_length,
            summary_voice=summary_voice
        )

        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "message": f"Started bulk analysis for {len(urls)} URLs"
        })

    except Exception as e:
        logger.error(f"Failed to start bulk analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk-save")
async def start_bulk_save(
    background_tasks: BackgroundTasks,
    request_data: Dict
):
    """Start a background bulk save task"""
    try:
        articles = request_data.get("articles", [])

        if not articles:
            raise HTTPException(status_code=400, detail="No articles provided")

        # Create background task
        task_manager = get_task_manager()
        task_id = task_manager.create_task(
            name="Bulk Article Save",
            total_items=len(articles),
            metadata={
                "article_count": len(articles)
            }
        )

        # Start the background task
        background_tasks.add_task(
            task_manager.run_task,
            task_id,
            run_bulk_save_task,
            articles=articles
        )

        return JSONResponse({
            "success": True,
            "task_id": task_id,
            "message": f"Started bulk save for {len(articles)} articles"
        })

    except Exception as e:
        logger.error(f"Failed to start bulk save: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a background task"""
    try:
        task_manager = get_task_manager()
        task_info = task_manager.get_task_status(task_id)

        if not task_info:
            raise HTTPException(status_code=404, detail="Task not found")

        return JSONResponse({
            "success": True,
            "task": task_info
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks")
async def list_tasks(status: Optional[str] = None):
    """List all background tasks, optionally filtered by status"""
    try:
        task_manager = get_task_manager()

        # Convert status string to enum if provided
        status_filter = None
        if status:
            from app.services.background_task_manager import TaskStatus
            try:
                status_filter = TaskStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        tasks = task_manager.list_tasks(status_filter)

        return JSONResponse({
            "success": True,
            "tasks": tasks,
            "summary": task_manager.get_task_summary()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running background task"""
    try:
        task_manager = get_task_manager()
        success = task_manager.cancel_task(task_id)

        if not success:
            # Check if task exists
            task_info = task_manager.get_task(task_id)
            if not task_info:
                raise HTTPException(status_code=404, detail="Task not found")
            else:
                raise HTTPException(status_code=400, detail="Task is not running")

        return JSONResponse({
            "success": True,
            "message": "Task cancelled successfully"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup")
async def cleanup_old_tasks(max_age_hours: int = 24):
    """Clean up old completed/failed tasks"""
    try:
        task_manager = get_task_manager()
        task_manager.cleanup_old_tasks(max_age_hours)

        return JSONResponse({
            "success": True,
            "message": f"Cleaned up tasks older than {max_age_hours} hours"
        })

    except Exception as e:
        logger.error(f"Failed to cleanup tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_task_summary():
    """Get summary of all background tasks"""
    try:
        task_manager = get_task_manager()
        summary = task_manager.get_task_summary()

        return JSONResponse({
            "success": True,
            "summary": summary
        })

    except Exception as e:
        logger.error(f"Failed to get task summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))