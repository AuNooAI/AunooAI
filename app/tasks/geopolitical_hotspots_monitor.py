"""
Monitor and schedule geopolitical hotspots processing.
Follows the same pattern as observer_agent_monitor.py.
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

# Track trend update status
_trend_update_status = {
    "running": False,
    "last_run_time": None,
    "last_result": None,
    "last_error": None
}


def get_task_status() -> Dict:
    """Get the current status of the geopolitical hotspots monitor background task"""
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
        schedule_time: Time of day to run (for daily type) - can be time, timedelta, or string
        from_time: Base time to calculate from (defaults to now)

    Returns:
        datetime: Next scheduled run time
    """
    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        # Convert schedule_time to hour and minute
        # PostgreSQL TIME columns may return as timedelta, time, or string
        hour = 0
        minute = 0

        if isinstance(schedule_time, dt_time):
            hour = schedule_time.hour
            minute = schedule_time.minute
        elif isinstance(schedule_time, timedelta):
            # PostgreSQL TIME columns often return as timedelta
            total_seconds = int(schedule_time.total_seconds())
            hour = total_seconds // 3600
            minute = (total_seconds % 3600) // 60
        elif isinstance(schedule_time, str):
            # Handle string format "HH:MM" or "HH:MM:SS"
            try:
                parts = schedule_time.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Could not parse schedule_time string: {schedule_time}")
                hour = 9  # Default to 9:00 AM
                minute = 0
        else:
            logger.warning(f"Unknown schedule_time type: {type(schedule_time)}")

        # For daily schedules, find the next occurrence of schedule_time
        next_run = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule_type == 'interval' and schedule_interval and schedule_unit:
        # For interval schedules, add the interval to now
        if schedule_unit == 'minutes':
            delta = timedelta(minutes=schedule_interval)
        elif schedule_unit == 'hours':
            delta = timedelta(hours=schedule_interval)
        elif schedule_unit == 'days':
            delta = timedelta(days=schedule_interval)
        else:
            delta = timedelta(hours=schedule_interval)  # Default to hours
        return now + delta

    # Default: run in 24 hours
    return now + timedelta(hours=24)


class GeopoliticalHotspotsMonitor:
    """Monitor for scheduled geopolitical hotspots processing."""

    def __init__(self, db: Database):
        self.db = db
        self.running_schedules: set = set()

    def get_due_schedules(self) -> List[Dict]:
        """Get all schedules that are due to run (next_run_at <= NOW())."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, topic, batch_size, model, process_all,
                       schedule_type, schedule_interval, schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count,
                       notify_on_complete, notify_threshold
                FROM geopolitical_schedules
                WHERE schedule_enabled = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            schedules = [dict(row._mapping) for row in result]
            conn.close()
            return schedules
        except Exception as e:
            logger.error(f"Error getting due geopolitical schedules: {e}")
            return []

    def update_schedule_status(
        self,
        schedule_id: int,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[datetime] = None,
        articles_processed: int = 0,
        hotspots_created: int = 0,
        hotspots_updated: int = 0
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

            updates.append("last_run_hotspots_created = :hotspots_created")
            params["hotspots_created"] = hotspots_created

            updates.append("last_run_hotspots_updated = :hotspots_updated")
            params["hotspots_updated"] = hotspots_updated

            if status == 'success':
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            conn.execute(text(f"""
                UPDATE geopolitical_schedules
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating geopolitical schedule status: {e}")

    async def run_schedule(self, schedule: Dict) -> Dict[str, Any]:
        """
        Execute a single schedule's processing.

        Returns:
            Dict with success status and results
        """
        schedule_id = schedule['id']
        schedule_name = schedule['name']

        result = {
            "success": False,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "articles_processed": 0,
            "hotspots_created": 0,
            "hotspots_updated": 0,
            "error": None
        }

        if schedule_id in self.running_schedules:
            logger.info(f"Geopolitical schedule {schedule_name} is already running, skipping")
            return result

        self.running_schedules.add(schedule_id)
        self.update_schedule_status(schedule_id, 'running')

        try:
            # Import the geopolitical service
            from app.services.geopolitical_service import (
                get_geopolitical_service,
                extract_location_with_llm,
                DEFAULT_GEOPOLITICAL_TOPIC
            )
            from app.database import get_database_instance

            service = get_geopolitical_service()

            # Get configuration from schedule
            topic = schedule.get('topic') or DEFAULT_GEOPOLITICAL_TOPIC
            batch_size = schedule.get('batch_size', 50)
            model = schedule.get('model', 'gpt-4o-mini')
            process_all = schedule.get('process_all', False)

            # Adaptive batching: calculate batch size based on backlog
            # If batch_size is 0, auto-calculate to clear backlog in ~24 hours
            if batch_size == 0 or schedule.get('adaptive_batch', False):
                try:
                    # Count unprocessed articles
                    conn = get_database_instance()._temp_get_connection()
                    unprocessed_result = conn.execute(text("""
                        SELECT COUNT(*)
                        FROM articles a
                        LEFT JOIN hotspot_articles ha ON a.uri = ha.article_uri
                        WHERE ha.article_uri IS NULL
                        AND (:topic IS NULL OR a.topic = :topic)
                    """), {"topic": topic})
                    unprocessed_count = unprocessed_result.fetchone()[0]
                    conn.close()

                    if unprocessed_count > 0:
                        # Calculate runs per day based on schedule
                        interval_hours = schedule.get('schedule_interval', 6)
                        if schedule.get('schedule_unit') == 'minutes':
                            interval_hours = interval_hours / 60
                        elif schedule.get('schedule_unit') == 'days':
                            interval_hours = interval_hours * 24

                        runs_per_day = max(1, 24 / interval_hours)

                        # Target: clear backlog in 24 hours, cap at 2000 per batch
                        calculated_batch = min(2000, max(50, int(unprocessed_count / runs_per_day) + 10))

                        logger.info(f"Adaptive batching: {unprocessed_count} unprocessed, {runs_per_day:.1f} runs/day, batch_size={calculated_batch}")
                        batch_size = calculated_batch
                    else:
                        batch_size = 50  # Default when no backlog
                except Exception as e:
                    logger.warning(f"Failed to calculate adaptive batch size: {e}, using default")
                    batch_size = batch_size if batch_size > 0 else 50

            logger.info(f"Running geopolitical schedule: {schedule_name} (ID: {schedule_id}, topic: {topic}, batch={batch_size})")

            # Get articles to process
            articles = service.get_unprocessed_articles(
                limit=batch_size,
                topic=topic,
                process_all=process_all
            )

            if not articles:
                logger.info(f"No articles to process for schedule {schedule_name}")
                result["success"] = True

                # Calculate next run time
                next_run = calculate_next_run(
                    schedule_type=schedule.get('schedule_type', 'interval'),
                    schedule_interval=schedule.get('schedule_interval'),
                    schedule_unit=schedule.get('schedule_unit'),
                    schedule_time=schedule.get('schedule_time')
                )
                self.update_schedule_status(schedule_id, 'success', next_run_at=next_run)
                return result

            stats = {
                "processed": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0
            }

            for article in articles:
                try:
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.3)

                    # Extract location using LLM
                    location_result = await extract_location_with_llm(
                        article['title'] or "",
                        article['summary'] or "",
                        article['category'] or "",
                        model
                    )

                    if location_result.get('no_location'):
                        stats["skipped"] += 1
                        continue

                    # Validate required fields
                    if not location_result.get('location_name') or not location_result.get('latitude') or not location_result.get('longitude'):
                        stats["skipped"] += 1
                        continue

                    # Check if hotspot exists
                    conn = get_database_instance().get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id FROM geopolitical_hotspots
                        WHERE location_name = ? AND country_code = ?
                    """, [location_result['location_name'], location_result.get('country_code')])
                    existing = cursor.fetchone()
                    cursor.close()
                    conn.close()

                    is_new = existing is None

                    # Create or update hotspot
                    hotspot_id = service.create_or_update_hotspot(location_result, topic=topic)

                    # Link article to hotspot
                    service.link_article_to_hotspot(
                        hotspot_id,
                        article['uri'],
                        relevance_score=1.0,
                        mention_type='primary'
                    )

                    if is_new:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                    stats["processed"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"Error processing article in schedule {schedule_name}: {e}")

            # Update country stats
            try:
                service.update_country_stats()
            except Exception as e:
                logger.warning(f"Failed to update country stats: {e}")

            # Update hotspot trends based on article sentiment
            try:
                trend_result = service.update_hotspot_trends()
                logger.info(f"Hotspot trends updated: {trend_result['updated']} changed")
            except Exception as e:
                logger.warning(f"Failed to update hotspot trends: {e}")

            result["success"] = True
            result["articles_processed"] = stats["processed"]
            result["hotspots_created"] = stats["created"]
            result["hotspots_updated"] = stats["updated"]

            # Calculate next run time
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
                articles_processed=stats["processed"],
                hotspots_created=stats["created"],
                hotspots_updated=stats["updated"]
            )

            # Send notification if configured
            if schedule.get('notify_on_complete') and stats["processed"] >= schedule.get('notify_threshold', 1):
                await self._send_notification(schedule, stats)

            logger.info(
                f"Geopolitical schedule {schedule_name} completed. "
                f"Processed: {stats['processed']}, Created: {stats['created']}, Updated: {stats['updated']}. "
                f"Next run: {next_run}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running geopolitical schedule {schedule_name}: {error_msg}", exc_info=True)
            result["error"] = error_msg

            # Still calculate next run time even on error
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
        """Send notification about completed processing."""
        try:
            db = get_database_instance()
            topic = schedule.get('topic') or 'Geopolitical Hotspots'

            title = f"Geopolitical Hotspots Update: {schedule.get('name', 'Scheduled Run')}"
            message = (
                f"Processed {stats['processed']} articles for '{topic}'.\n"
                f"New hotspots: {stats['created']}, Updated: {stats['updated']}"
            )

            # Create notification in database
            db.facade.create_notification(
                username=None,  # System-wide notification
                type='geopolitical_hotspots',
                title=title,
                message=message,
                link='/explore?tab=geohotspots'
            )

            logger.info(f"Notification created for geopolitical schedule {schedule.get('name')}")

        except Exception as e:
            logger.error(f"Failed to send notification for geopolitical schedule: {e}")


async def run_geopolitical_hotspots_monitor():
    """Background task to periodically check and run scheduled geopolitical processing."""
    global _background_task_status

    db = Database()
    monitor = GeopoliticalHotspotsMonitor(db)

    logger.info("Geopolitical hotspots monitor background task started")
    _background_task_status["running"] = True

    # Check every 60 seconds
    check_interval = 60

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            # Get schedules that are due to run
            due_schedules = monitor.get_due_schedules()
            _background_task_status["schedules_checked"] = len(due_schedules)

            if due_schedules:
                logger.info(f"Found {len(due_schedules)} geopolitical schedules due to run")

                # Run each due schedule
                for schedule in due_schedules:
                    try:
                        result = await monitor.run_schedule(schedule)
                        if result["success"]:
                            _background_task_status["schedules_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running geopolitical schedule {schedule.get('name')}: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Geopolitical hotspots monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        # Wait before next check
        await asyncio.sleep(check_interval)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    """Run a specific schedule immediately (for manual triggering)."""
    monitor = GeopoliticalHotspotsMonitor(db)

    # Get the schedule details
    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, topic, batch_size, model, process_all,
                   schedule_type, schedule_interval, schedule_unit, schedule_time,
                   last_run_at, next_run_at, run_count,
                   notify_on_complete, notify_threshold
            FROM geopolitical_schedules
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


def get_trend_update_status() -> Dict:
    """Get the current status of the trend update task."""
    return _trend_update_status.copy()


async def run_hotspot_trend_updates():
    """
    Background task to update hotspot trends every 6 hours.

    Analyzes article sentiment to determine if hotspots are
    escalating, de-escalating, or stable.
    """
    global _trend_update_status

    logger.info("Hotspot trend update background task started (6-hour interval)")

    # 6 hours in seconds
    update_interval = 6 * 60 * 60

    # Initial delay of 5 minutes to let other services start
    await asyncio.sleep(300)

    while True:
        try:
            _trend_update_status["running"] = True

            from app.services.geopolitical_service import get_geopolitical_service
            service = get_geopolitical_service()

            logger.info("Running scheduled hotspot trend update...")
            # update_hotspot_trends runs sync SQLAlchemy queries — push to a
            # worker thread so the main event loop stays responsive while the
            # potentially-long DB work runs (caught blocking the loop for
            # tens of seconds via SIGUSR1 stack dump, 2026-05-21).
            result = await asyncio.to_thread(
                service.update_hotspot_trends, 7, 30,
            )

            _trend_update_status["last_run_time"] = datetime.now()
            _trend_update_status["last_result"] = result
            _trend_update_status["last_error"] = None

            logger.info(
                f"Hotspot trend update completed: "
                f"{result['updated']} updated, "
                f"{result['escalating']} escalating, "
                f"{result['de_escalating']} de-escalating, "
                f"{result['stable']} stable"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Hotspot trend update error: {error_msg}", exc_info=True)
            _trend_update_status["last_error"] = error_msg

        finally:
            _trend_update_status["running"] = False

        # Wait 6 hours before next update
        await asyncio.sleep(update_interval)
