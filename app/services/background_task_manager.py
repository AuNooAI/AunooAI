"""
Background task manager for handling long-running bulk operations without blocking the UI.
Uses FastAPI's BackgroundTasks and asyncio for efficient task management.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, Callable, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
import json

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskInfo:
    id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    total_items: int = 0
    processed_items: int = 0
    current_item: Optional[str] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key in ['created_at', 'started_at', 'completed_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        # Convert enum to value
        data['status'] = data['status'].value
        return data

class BackgroundTaskManager:
    """Manages background tasks for bulk operations"""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._max_concurrent_tasks = 3
        self._task_cleanup_interval = 3600  # 1 hour

    def create_task(self, name: str, total_items: int = 0, metadata: Optional[Dict] = None) -> str:
        """Create a new background task and return its ID"""
        task_id = str(uuid.uuid4())

        task_info = TaskInfo(
            id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            total_items=total_items,
            metadata=metadata or {}
        )

        self._tasks[task_id] = task_info
        logger.info(f"Created background task: {name} (ID: {task_id})")
        return task_id

    async def run_task(self, task_id: str, task_func: Callable, *args, **kwargs) -> None:
        """Run a background task"""
        if task_id not in self._tasks:
            raise ValueError(f"Task {task_id} not found")

        task_info = self._tasks[task_id]

        # Check if we have too many running tasks
        if len(self._running_tasks) >= self._max_concurrent_tasks:
            logger.warning(f"Too many concurrent tasks, queuing task {task_id}")
            return

        task_info.status = TaskStatus.RUNNING
        task_info.started_at = datetime.now()

        try:
            # Create progress callback
            def update_progress(processed: int, current: str = None):
                task_info.processed_items = processed
                task_info.current_item = current
                if task_info.total_items > 0:
                    task_info.progress = (processed / task_info.total_items) * 100
                logger.debug(f"Task {task_id} progress: {task_info.progress:.1f}%")

            # Add progress callback to kwargs
            kwargs['progress_callback'] = update_progress

            # Run the task
            logger.info(f"Starting task {task_id}: {task_info.name}")

            # Create asyncio task
            async_task = asyncio.create_task(task_func(*args, **kwargs))
            self._running_tasks[task_id] = async_task

            # Wait for completion
            result = await async_task

            task_info.result = result
            task_info.status = TaskStatus.COMPLETED
            task_info.completed_at = datetime.now()
            task_info.progress = 100.0

            logger.info(f"Task {task_id} completed successfully")

        except asyncio.CancelledError:
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now()
            logger.info(f"Task {task_id} was cancelled")

        except Exception as e:
            task_info.status = TaskStatus.FAILED
            task_info.error = str(e)
            task_info.completed_at = datetime.now()
            logger.error(f"Task {task_id} failed: {e}")

        finally:
            # Clean up running task reference
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task information by ID"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """Get task status as dictionary"""
        task = self.get_task(task_id)
        return task.to_dict() if task else None

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict]:
        """List all tasks, optionally filtered by status"""
        tasks = []
        for task in self._tasks.values():
            if status is None or task.status == status:
                tasks.append(task.to_dict())

        # Sort by creation time, newest first
        tasks.sort(key=lambda x: x['created_at'], reverse=True)
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task"""
        if task_id in self._running_tasks:
            async_task = self._running_tasks[task_id]
            async_task.cancel()
            logger.info(f"Cancelled task {task_id}")
            return True
        return False

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old completed/failed tasks"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

        to_remove = []
        for task_id, task_info in self._tasks.items():
            if (task_info.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                task_info.created_at.timestamp() < cutoff_time):
                to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]
            logger.debug(f"Cleaned up old task {task_id}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old tasks")

    def get_running_tasks_count(self) -> int:
        """Get number of currently running tasks"""
        return len(self._running_tasks)

    def get_task_summary(self) -> Dict:
        """Get summary of all tasks"""
        summary = {
            "total": len(self._tasks),
            "running": 0,
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }

        for task in self._tasks.values():
            summary[task.status.value] += 1

        return summary

# Global task manager instance
_task_manager: Optional[BackgroundTaskManager] = None

def get_task_manager() -> BackgroundTaskManager:
    """Get or create the global task manager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager

# Convenience functions for bulk operations
async def run_bulk_analysis_task(urls: List[str], topic: str, progress_callback=None, **analysis_params):
    """Background task wrapper for bulk analysis using analysis queue"""
    try:
        from app.services.analysis_queue import get_analysis_queue, AnalysisTask
        from app.bulk_research import BulkResearch
        from app.database import get_database_instance

        # Get analysis queue for non-blocking processing
        analysis_queue = get_analysis_queue()

        # Setup progress tracking
        if progress_callback:
            progress_callback(0, f"Starting analysis of {len(urls)} articles")

        # Create analysis tasks
        tasks = []
        for url in urls:
            task = AnalysisTask(
                url=url,
                topic=topic,
                metadata=analysis_params
            )
            tasks.append(task)

        # Add tasks to queue with progress callback
        await analysis_queue.add_tasks(tasks, progress_callback)

        # Wait for completion with timeout (30 minutes max)
        task_results = await analysis_queue.wait_completion(timeout=1800)

        # Process results
        analysis_results = []
        success_count = 0
        error_count = 0

        for task_result in task_results:
            if task_result['success']:
                analysis_results.append(task_result['result'])
                success_count += 1
            else:
                # Create error result
                error_result = {
                    'uri': task_result['task'].url,
                    'error': task_result['error'],
                    'title': 'Analysis Failed',
                    'topic': task_result['task'].topic
                }
                analysis_results.append(error_result)
                error_count += 1

        # Save results in batches
        if analysis_results:
            db = get_database_instance()
            bulk_research = BulkResearch(db)

            save_results = await bulk_research.save_bulk_articles(analysis_results)

            logger.info(f"Bulk analysis completed: {success_count} analyzed, {error_count} errors, "
                       f"{len(save_results['success'])} saved, {len(save_results['errors'])} save errors")

        return {
            "success": True,
            "analyzed_count": success_count,
            "error_count": error_count,
            "saved_count": len(save_results.get('success', [])) if 'save_results' in locals() else 0,
            "save_errors": len(save_results.get('errors', [])) if 'save_results' in locals() else 0,
            "results": analysis_results
        }

    except Exception as e:
        logger.error(f"Bulk analysis task failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def run_bulk_save_task(articles: List[Dict]):
    """Background task wrapper for bulk article saving"""
    from app.bulk_research import BulkResearch
    from app.database import get_database_instance

    try:
        db = get_database_instance()
        bulk_research = BulkResearch(db)

        # Save articles
        results = await bulk_research.save_bulk_articles(articles)

        return {
            "success": True,
            "saved_count": len(results["success"]),
            "error_count": len(results["errors"]),
            "results": results
        }

    except Exception as e:
        logger.error(f"Bulk save task failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def run_auto_ingest_task(progress_callback=None):
    """Background task wrapper for auto-ingest pipeline with progress tracking"""
    from app.services.auto_ingest_service import get_auto_ingest_service

    try:
        service = get_auto_ingest_service()

        # Override the service's internal progress to use our callback
        if progress_callback:
            # Get pending articles for accurate progress tracking
            pending_articles = await service.get_pending_articles(limit=100)
            total_articles = len(pending_articles)

            progress_callback(0, f"Starting auto-ingest for {total_articles} articles")

            # Create a modified version of the auto-ingest that reports progress
            results = await _run_auto_ingest_with_progress(service, progress_callback, total_articles)
        else:
            # Run without progress tracking
            results = await service.run_auto_ingest()

        return {
            "success": True,
            "results": results
        }

    except Exception as e:
        logger.error(f"Auto-ingest task failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

async def _run_auto_ingest_with_progress(service, progress_callback, total_articles):
    """Run auto-ingest pipeline with progress updates"""
    if not service.config.enabled:
        return {"success": False, "message": "Auto-ingest is disabled"}

    if service._running:
        return {"success": False, "message": "Auto-ingest is already running"}

    service._running = True
    start_time = datetime.now()

    try:
        logger.info("Starting auto-ingest pipeline with progress tracking")

        # Get pending articles
        pending_articles = await service.get_pending_articles(limit=50)

        if not pending_articles:
            progress_callback(total_articles, "No pending articles found")
            return {
                "success": True,
                "message": "No pending articles",
                "processed": 0,
                "ingested": 0
            }

        # Process in batches with progress updates
        total_results = {
            'processed': 0,
            'ingested': 0,
            'rejected_relevance': 0,
            'rejected_quality': 0,
            'errors': 0,
            'details': []
        }

        processed_count = 0
        for i in range(0, len(pending_articles), service.config.batch_size):
            batch = pending_articles[i:i + service.config.batch_size]
            batch_num = i // service.config.batch_size + 1

            progress_callback(
                processed_count,
                f"Processing batch {batch_num} ({len(batch)} articles)"
            )

            batch_results = await service.process_articles_batch(batch)

            # Aggregate results
            for key in ['processed', 'ingested', 'rejected_relevance', 'rejected_quality', 'errors']:
                total_results[key] += batch_results[key]
            total_results['details'].extend(batch_results['details'])

            # Update progress
            processed_count += len(batch)
            progress_callback(
                processed_count,
                f"Completed batch {batch_num}: {batch_results['ingested']} ingested, {batch_results['errors']} errors"
            )

            # Brief pause between batches
            await asyncio.sleep(0.5)

        duration = (datetime.now() - start_time).total_seconds()

        progress_callback(
            total_articles,
            f"Auto-ingest completed: {total_results['ingested']} ingested, {total_results['errors']} errors"
        )

        logger.info(f"Auto-ingest completed in {duration:.1f}s: "
                   f"{total_results['ingested']} ingested, "
                   f"{total_results['rejected_relevance']} rejected (relevance), "
                   f"{total_results['rejected_quality']} rejected (quality), "
                   f"{total_results['errors']} errors")

        return {
            "success": True,
            "duration_seconds": duration,
            **total_results
        }

    except Exception as e:
        logger.error(f"Auto-ingest pipeline failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": (datetime.now() - start_time).total_seconds()
        }
    finally:
        service._running = False

async def run_keyword_check_task(progress_callback=None, group_id=None):
    """Background task wrapper for keyword checking with progress tracking

    Args:
        progress_callback: Optional callback for progress updates
        group_id: Optional group ID to filter keywords by specific group
    """
    from app.database import get_database_instance
    from app.tasks.keyword_monitor import KeywordMonitor

    try:
        db = get_database_instance()
        monitor = KeywordMonitor(db)

        if progress_callback:
            if group_id:
                progress_callback(0, f"Starting keyword check for group {group_id}...")
            else:
                progress_callback(0, "Starting keyword check...")

        # Run the keyword check with optional group_id filter and progress callback
        result = await monitor.check_keywords(group_id=group_id, progress_callback=progress_callback)

        if progress_callback:
            articles_found = result.get('new_articles', 0) if result else 0
            group_info = f" for group {group_id}" if group_id else ""
            progress_callback(100, f"Keyword check{group_info} completed: {articles_found} new articles found")

        if result is None:
            return {
                "success": False,
                "error": "Keyword check returned None - check collector initialization"
            }

        if result.get("success", False):
            logger.info(f"Background keyword check completed: {result.get('new_articles', 0)} new articles found")
            return {
                "success": True,
                "new_articles": result.get('new_articles', 0),
                "message": result.get('message', 'Keyword check completed'),
                **result
            }
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"Background keyword check failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    except Exception as e:
        logger.error(f"Keyword check task failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }