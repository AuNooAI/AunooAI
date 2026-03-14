"""
Monitor and schedule science funding tracker classification.
Follows the same pattern as policy_tracker_monitor.py.
Uses LLM-first classification with keyword fallback.
"""

import logging
import asyncio
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional, Any, List, Union
from sqlalchemy import text

from app.database import Database, get_database_instance

logger = logging.getLogger(__name__)

# Global variable to track task status
_background_task_status = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "schedules_checked": 0,
    "schedules_run": 0,
    "is_checking": False
}


def get_task_status() -> Dict:
    """Get the current status of the science funding monitor background task."""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    schedule_interval: Optional[int],
    schedule_unit: Optional[str],
    schedule_time: Optional[Any],
    from_time: Optional[datetime] = None
) -> datetime:
    """
    Calculate the next run time based on schedule configuration.

    Args:
        schedule_type: 'interval' or 'daily'
        schedule_interval: Interval value (for interval type)
        schedule_unit: 'minutes', 'hours', or 'days' (for interval type)
        schedule_time: Time of day to run (for daily type)
        from_time: Base time to calculate from (defaults to now)

    Returns:
        datetime: Next scheduled run time
    """
    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        hour = 0
        minute = 0

        if isinstance(schedule_time, dt_time):
            hour = schedule_time.hour
            minute = schedule_time.minute
        elif isinstance(schedule_time, timedelta):
            total_seconds = int(schedule_time.total_seconds())
            hour = total_seconds // 3600
            minute = (total_seconds % 3600) // 60
        elif isinstance(schedule_time, str):
            try:
                parts = schedule_time.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Could not parse schedule_time string: {schedule_time}")
                hour = 9
                minute = 0
        else:
            logger.warning(f"Unknown schedule_time type: {type(schedule_time)}")

        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule_type == 'interval' and schedule_interval and schedule_unit:
        if schedule_unit == 'minutes':
            delta = timedelta(minutes=schedule_interval)
        elif schedule_unit == 'hours':
            delta = timedelta(hours=schedule_interval)
        elif schedule_unit == 'days':
            delta = timedelta(days=schedule_interval)
        else:
            delta = timedelta(hours=schedule_interval)
        return now + delta

    return now + timedelta(hours=24)


class ScienceFundingMonitor:
    """Monitor for scheduled science funding classification."""

    def __init__(self, db: Database):
        self.db = db
        self.running_schedules: set = set()

    def get_due_schedules(self) -> List[Dict]:
        """Get all schedules that are due to run."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, topic, run_type, days_back,
                       schedule_type, schedule_interval, schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count,
                       notify_on_complete, notify_threshold
                FROM science_tracker_schedules
                WHERE schedule_enabled = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            schedules = [dict(row._mapping) for row in result]
            conn.close()
            return schedules
        except Exception as e:
            logger.error(f"Error getting due science tracker schedules: {e}")
            return []

    def update_schedule_status(
        self,
        schedule_id: int,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[datetime] = None,
        articles_processed: int = 0,
        articles_categorized: int = 0
    ) -> None:
        """Update a schedule's run status and next run time."""
        try:
            conn = self.db._temp_get_connection()

            updates = ["last_run_at = NOW()", "last_run_status = :status"]
            params = {"id": schedule_id, "status": status}

            if error:
                updates.append("last_run_error = :error")
                params["error"] = error
            else:
                updates.append("last_run_error = NULL")

            if next_run_at:
                updates.append("next_run_at = :next_run")
                params["next_run"] = next_run_at

            updates.append("last_run_articles_processed = :articles_processed")
            params["articles_processed"] = articles_processed

            updates.append("last_run_articles_categorized = :articles_categorized")
            params["articles_categorized"] = articles_categorized

            if status == 'success':
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            conn.execute(text(f"""
                UPDATE science_tracker_schedules
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating science tracker schedule status: {e}")

    async def run_schedule(self, schedule: Dict) -> Dict[str, Any]:
        """Execute a single schedule's classification using LLM-first approach."""
        schedule_id = schedule['id']
        schedule_name = schedule['name']

        result = {
            "success": False,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "articles_processed": 0,
            "articles_categorized": 0,
            "error": None
        }

        if schedule_id in self.running_schedules:
            logger.info(f"Science tracker schedule {schedule_name} is already running, skipping")
            return result

        self.running_schedules.add(schedule_id)
        self.update_schedule_status(schedule_id, 'running')

        try:
            from app.routes.science_funding_routes import (
                run_classification_task,
                get_date_range_filter
            )

            db = get_database_instance()
            conn = db._temp_get_connection()

            topic = schedule.get('topic')
            run_type = schedule.get('run_type', 'incremental')
            days_back = schedule.get('days_back', 30)

            logger.info(f"Running science tracker schedule: {schedule_name} (ID: {schedule_id}, topic: {topic})")

            # Create a run record
            run_result = conn.execute(text("""
                INSERT INTO science_tracker_runs (topic, run_type, status)
                VALUES (:topic, :run_type, 'running')
                RETURNING id
            """), {"topic": topic, "run_type": run_type})
            run_id = run_result.fetchone()[0]
            conn.commit()
            conn.close()

            # Run LLM-first classification
            await run_classification_task(run_id, topic, run_type, days_back)

            # Get the results
            conn = db._temp_get_connection()
            run_info = conn.execute(text("""
                SELECT articles_processed, articles_categorized
                FROM science_tracker_runs
                WHERE id = :id
            """), {"id": run_id}).fetchone()
            conn.close()

            if run_info:
                result["articles_processed"] = run_info[0] or 0
                result["articles_categorized"] = run_info[1] or 0

            result["success"] = True

            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval'),
                schedule_unit=schedule.get('schedule_unit'),
                schedule_time=schedule.get('schedule_time')
            )

            self.update_schedule_status(
                schedule_id,
                'success',
                next_run_at=next_run,
                articles_processed=result["articles_processed"],
                articles_categorized=result["articles_categorized"]
            )

            if schedule.get('notify_on_complete') and result["articles_categorized"] >= schedule.get('notify_threshold', 10):
                await self._send_notification(schedule, result)

            logger.info(
                f"Science tracker schedule {schedule_name} completed. "
                f"Processed: {result['articles_processed']}, Categorized: {result['articles_categorized']}. "
                f"Next run: {next_run}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running science tracker schedule {schedule_name}: {error_msg}", exc_info=True)
            result["error"] = error_msg

            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval'),
                schedule_unit=schedule.get('schedule_unit'),
                schedule_time=schedule.get('schedule_time')
            )
            self.update_schedule_status(schedule_id, 'error', error=error_msg, next_run_at=next_run)

        finally:
            self.running_schedules.discard(schedule_id)

        return result

    async def _send_notification(self, schedule: Dict, stats: Dict) -> None:
        """Send notification about completed classification."""
        try:
            db = get_database_instance()
            topic = schedule.get('topic') or 'Science Funding Tracker'

            title = f"Science Tracker Update: {schedule.get('name', 'Scheduled Run')}"
            message = (
                f"Classified {stats['articles_categorized']} articles for '{topic}'.\n"
                f"Total processed: {stats['articles_processed']}"
            )

            db.facade.create_notification(
                username=None,
                type='science_tracker',
                title=title,
                message=message,
                link='/explore?tab=sciencewatch'
            )

            logger.info(f"Notification created for science tracker schedule {schedule.get('name')}")

        except Exception as e:
            logger.error(f"Failed to send notification for science tracker schedule: {e}")


async def run_science_funding_monitor():
    """Background task to periodically check and run scheduled science funding classification."""
    global _background_task_status

    db = Database()
    monitor = ScienceFundingMonitor(db)

    logger.info("Science funding monitor background task started")
    _background_task_status["running"] = True

    check_interval = 60

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            due_schedules = monitor.get_due_schedules()
            _background_task_status["schedules_checked"] = len(due_schedules)

            if due_schedules:
                logger.info(f"Found {len(due_schedules)} science tracker schedules due to run")

                for schedule in due_schedules:
                    try:
                        result = await monitor.run_schedule(schedule)
                        if result["success"]:
                            _background_task_status["schedules_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running science tracker schedule {schedule.get('name')}: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Science funding monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        await asyncio.sleep(check_interval)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    """Run a specific schedule immediately (for manual triggering)."""
    monitor = ScienceFundingMonitor(db)

    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, topic, run_type, days_back,
                   schedule_type, schedule_interval, schedule_unit, schedule_time,
                   last_run_at, next_run_at, run_count,
                   notify_on_complete, notify_threshold
            FROM science_tracker_schedules
            WHERE id = :id
        """), {"id": schedule_id})
        row = result.mappings().first()
        conn.close()

        if not row:
            return {"success": False, "error": "Schedule not found"}

        schedule = dict(row)
        return await monitor.run_schedule(schedule)

    except Exception as e:
        return {"success": False, "error": str(e)}
