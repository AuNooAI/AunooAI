"""
Analysis queue service for non-blocking bulk article processing.
Uses asyncio queues to prevent UI blocking during large operations.
"""
import asyncio
import logging
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class AnalysisTask:
    """Represents a single article analysis task"""
    url: str
    topic: str
    title: str = ""
    summary: str = ""
    source: str = ""
    publication_date: str = ""
    metadata: Dict = None

class AnalysisQueue:
    """Non-blocking queue for article analysis"""

    def __init__(self, max_concurrent: int = 3, max_queue_size: int = 100):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.task_queue = asyncio.Queue(maxsize=max_queue_size)
        self.result_queue = asyncio.Queue()
        self.workers = []
        self.is_running = False
        self.progress_callback = None
        self.completed_count = 0
        self.total_count = 0

    async def start_workers(self):
        """Start worker tasks for processing analysis"""
        if self.is_running:
            return

        self.is_running = True
        self.workers = []

        for i in range(self.max_concurrent):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)

        logger.info(f"Started {len(self.workers)} analysis workers")

    async def stop_workers(self):
        """Stop all worker tasks"""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel all workers
        for worker in self.workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers = []

        logger.info("Stopped all analysis workers")

    async def add_tasks(self, tasks: List[AnalysisTask], progress_callback: Callable = None):
        """Add analysis tasks to the queue"""
        if not self.is_running:
            await self.start_workers()

        self.progress_callback = progress_callback
        self.completed_count = 0
        self.total_count = len(tasks)

        for task in tasks:
            try:
                await self.task_queue.put(task)
            except asyncio.QueueFull:
                logger.warning(f"Analysis queue full, skipping task: {task.url}")

        logger.info(f"Added {len(tasks)} tasks to analysis queue")

    async def _worker(self, worker_name: str):
        """Worker coroutine for processing analysis tasks"""
        from app.bulk_research import BulkResearch
        from app.database import get_database_instance

        try:
            db = get_database_instance()
            bulk_research = BulkResearch(db)

            logger.debug(f"Analysis worker {worker_name} started")

            while self.is_running:
                try:
                    # Get task from queue with timeout
                    task = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=1.0
                    )

                    # Process the task
                    start_time = datetime.now()
                    try:
                        # Analyze single article
                        results = await bulk_research.analyze_bulk_urls(
                            urls=[task.url],
                            topic=task.topic,
                            summary_type='curious_ai',
                            model_name='gpt-4',
                            summary_length=50,
                            summary_voice='neutral'
                        )

                        result = {
                            'task': task,
                            'success': True,
                            'result': results[0] if results else None,
                            'processing_time': (datetime.now() - start_time).total_seconds(),
                            'worker': worker_name
                        }

                    except Exception as e:
                        result = {
                            'task': task,
                            'success': False,
                            'error': str(e),
                            'processing_time': (datetime.now() - start_time).total_seconds(),
                            'worker': worker_name
                        }
                        logger.error(f"Worker {worker_name} failed to process {task.url}: {e}")

                    # Put result in result queue
                    await self.result_queue.put(result)

                    # Update progress
                    self.completed_count += 1
                    if self.progress_callback:
                        try:
                            self.progress_callback(
                                self.completed_count,
                                task.title or task.url
                            )
                        except Exception as e:
                            logger.error(f"Progress callback error: {e}")

                    # Mark task as done
                    self.task_queue.task_done()

                    logger.debug(f"Worker {worker_name} completed task: {task.url}")

                except asyncio.TimeoutError:
                    # Timeout waiting for task, continue loop
                    continue

        except asyncio.CancelledError:
            logger.debug(f"Analysis worker {worker_name} cancelled")
        except Exception as e:
            logger.error(f"Analysis worker {worker_name} error: {e}")

    async def get_results(self) -> List[Dict]:
        """Get all completed results"""
        results = []

        while True:
            try:
                result = self.result_queue.get_nowait()
                results.append(result)
            except asyncio.QueueEmpty:
                break

        return results

    async def wait_completion(self, timeout: Optional[float] = None) -> List[Dict]:
        """Wait for all tasks to complete and return results"""
        try:
            # Wait for all tasks to be processed
            await asyncio.wait_for(self.task_queue.join(), timeout=timeout)

            # Collect all results
            results = await self.get_results()

            logger.info(f"Analysis queue completed: {len(results)} results")
            return results

        except asyncio.TimeoutError:
            logger.warning(f"Analysis queue timed out after {timeout} seconds")
            # Return partial results
            return await self.get_results()

    def get_progress(self) -> Dict:
        """Get current progress information"""
        return {
            'completed': self.completed_count,
            'total': self.total_count,
            'percentage': (self.completed_count / self.total_count * 100) if self.total_count > 0 else 0,
            'remaining': self.total_count - self.completed_count,
            'queue_size': self.task_queue.qsize(),
            'workers_active': len([w for w in self.workers if not w.done()]),
            'is_running': self.is_running
        }

# Global queue instance
_analysis_queue: Optional[AnalysisQueue] = None

def get_analysis_queue() -> AnalysisQueue:
    """Get or create the global analysis queue"""
    global _analysis_queue
    if _analysis_queue is None:
        _analysis_queue = AnalysisQueue(max_concurrent=2, max_queue_size=50)
    return _analysis_queue

async def shutdown_analysis_queue():
    """Shutdown the global analysis queue"""
    global _analysis_queue
    if _analysis_queue:
        await _analysis_queue.stop_workers()
        _analysis_queue = None