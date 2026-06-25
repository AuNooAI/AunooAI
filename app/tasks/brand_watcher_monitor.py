"""
Monitor and execute scheduled brand watcher classification.
Follows the same pattern as policy_tracker_monitor.py.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional, Any, List
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
    """Get the current status of the brand watcher monitor background task."""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    schedule_interval: Optional[int],
    schedule_unit: Optional[str],
    schedule_time: Optional[Any],
    from_time: Optional[datetime] = None
) -> datetime:
    """Calculate the next run time based on schedule configuration."""
    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        hour, minute = 0, 0
        if isinstance(schedule_time, dt_time):
            hour, minute = schedule_time.hour, schedule_time.minute
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
                hour, minute = 9, 0

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


class BrandWatcherMonitor:
    """Monitor for scheduled brand watcher classification."""

    def __init__(self, db: Database):
        self.db = db
        self.running_schedules: set = set()

    def get_due_schedules(self) -> List[Dict]:
        """Get all schedules that are due to run (next_run_at <= NOW())."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, brand_id, run_type, days_back, topics,
                       schedule_type, schedule_interval, schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count,
                       notify_on_complete, notify_threshold
                FROM bw_tracker_schedules
                WHERE schedule_enabled = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            schedules = [dict(row._mapping) for row in result]
            conn.close()
            return schedules
        except Exception as e:
            logger.error(f"Error getting due brand watcher schedules: {e}")
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
                UPDATE bw_tracker_schedules
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating brand watcher schedule status: {e}")

    async def run_schedule(self, schedule: Dict) -> Dict[str, Any]:
        """Execute a single schedule's classification."""
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
            logger.info(f"Brand watcher schedule {schedule_name} is already running, skipping")
            return result

        self.running_schedules.add(schedule_id)
        self.update_schedule_status(schedule_id, 'running')

        try:
            from app.routes.brand_watcher_routes import _run_classification_task
            from app.database import get_database_instance

            db = get_database_instance()
            conn = db._temp_get_connection()

            brand_id = schedule.get('brand_id')
            run_type = schedule.get('run_type', 'incremental')
            days_back = schedule.get('days_back', 30)

            # Parse topics from JSONB column
            raw_topics = schedule.get('topics')
            if isinstance(raw_topics, str):
                try:
                    topics = json.loads(raw_topics)
                except (json.JSONDecodeError, TypeError):
                    topics = None
            elif isinstance(raw_topics, list):
                topics = raw_topics
            else:
                topics = None

            logger.info(f"Running brand watcher schedule: {schedule_name} (ID: {schedule_id}, brand_id: {brand_id}, topics: {topics})")

            # Create a run record
            run_result = conn.execute(text("""
                INSERT INTO bw_tracker_runs (brand_id, run_type, status)
                VALUES (:brand_id, :run_type, 'running')
                RETURNING id
            """), {"brand_id": brand_id, "run_type": run_type})
            run_id = run_result.fetchone()[0]
            conn.commit()
            conn.close()

            # Run classification
            await _run_classification_task(run_id, brand_id, run_type, days_back, topics)

            # Get the results
            conn = db._temp_get_connection()
            run_info = conn.execute(text("""
                SELECT articles_processed, articles_categorized
                FROM bw_tracker_runs
                WHERE id = :id
            """), {"id": run_id}).fetchone()
            conn.close()

            if run_info:
                result["articles_processed"] = run_info[0] or 0
                result["articles_categorized"] = run_info[1] or 0

            result["success"] = True

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
                articles_processed=result["articles_processed"],
                articles_categorized=result["articles_categorized"]
            )

            # Send notification if configured
            if schedule.get('notify_on_complete') and result["articles_categorized"] >= schedule.get('notify_threshold', 10):
                await self._send_notification(schedule, result)

            # Check for category spikes
            await self._check_category_spikes(brand_id, schedule_name)

            logger.info(
                f"Brand watcher schedule {schedule_name} completed. "
                f"Processed: {result['articles_processed']}, Categorized: {result['articles_categorized']}. "
                f"Next run: {next_run}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running brand watcher schedule {schedule_name}: {error_msg}", exc_info=True)
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
            brand_name = schedule.get('name', 'Brand Watcher')

            title = f"Brand Watcher: {brand_name}"
            message = (
                f"Classified {stats['articles_categorized']} articles.\n"
                f"Total processed: {stats['articles_processed']}"
            )

            db.facade.create_notification(
                username=None,
                type='brand_watcher',
                title=title,
                message=message,
                link='/newsfeed?tab=brand-watcher'
            )
            logger.info(f"Notification created for brand watcher schedule {schedule.get('name')}")
        except Exception as e:
            logger.error(f"Failed to send notification for brand watcher schedule: {e}")

    async def _check_category_spikes(self, brand_id: Optional[int], schedule_name: str) -> None:
        """Check for category spikes after classification and create alerts."""
        try:
            db = get_database_instance()
            conn = db._temp_get_connection()

            brand_filter = "AND bac.brand_id = :brand_id" if brand_id else ""
            params = {}
            if brand_id:
                params["brand_id"] = brand_id

            # Get category counts for last 7 days
            recent_result = conn.execute(text(f"""
                SELECT bac.category, COUNT(DISTINCT bac.article_uri) as cnt
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE a.publication_date >= (NOW() - INTERVAL '7 days')::text
                {brand_filter}
                GROUP BY bac.category
            """), params)
            recent_counts = {row[0]: row[1] for row in recent_result.fetchall()}

            # Get 30-day rolling average (per week)
            avg_result = conn.execute(text(f"""
                SELECT bac.category, COUNT(DISTINCT bac.article_uri) / 4.0 as avg_weekly
                FROM bw_article_categories bac
                JOIN articles a ON bac.article_uri = a.uri
                WHERE a.publication_date >= (NOW() - INTERVAL '30 days')::text
                  AND a.publication_date < (NOW() - INTERVAL '7 days')::text
                {brand_filter}
                GROUP BY bac.category
            """), params)
            avg_counts = {row[0]: float(row[1]) for row in avg_result.fetchall()}

            conn.close()

            # Check for spikes (2x average)
            for category, count in recent_counts.items():
                avg = avg_counts.get(category, 0)
                if avg > 0 and count >= avg * 2 and count >= 5:
                    # Get brand name for notification
                    brand_display = schedule_name
                    if brand_id:
                        try:
                            conn2 = db._temp_get_connection()
                            br = conn2.execute(text(
                                "SELECT display_name FROM bw_brands WHERE id = :id"
                            ), {"id": brand_id}).fetchone()
                            conn2.close()
                            if br:
                                brand_display = br[0]
                        except Exception:
                            pass

                    db.facade.create_notification(
                        username=None,
                        type='brand_watcher_alert',
                        title=f'Spike: {category} for {brand_display}',
                        message=f'{count} articles this week (avg: {avg:.0f}/week)',
                        link='/newsfeed?tab=brand-watcher'
                    )
                    logger.info(f"Spike alert: {category} for {brand_display} - {count} articles (avg: {avg:.0f})")

        except Exception as e:
            logger.error(f"Error checking category spikes: {e}")


def _check_auto_retrain(db: Database) -> None:
    """Check if the SLM classifier should be retrained.

    Runs weekly: if 500+ new classified articles since last training,
    triggers a background retrain.
    """
    import os
    import subprocess

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    marker_file = os.path.join(base_dir, "models", "brand_watcher_classifier", ".last_train_timestamp")

    # Check marker
    last_train = datetime.min
    if os.path.exists(marker_file):
        try:
            with open(marker_file, 'r') as f:
                last_train = datetime.fromisoformat(f.read().strip())
        except Exception:
            pass

    # Only check weekly
    if (datetime.now() - last_train).days < 7:
        return

    try:
        conn = db._temp_get_connection()
        count = conn.execute(text("""
            SELECT COUNT(*) FROM bw_article_categories
            WHERE classified_at > :since
        """), {"since": last_train}).scalar() or 0
        conn.close()

        if count < 500:
            logger.debug(f"Auto-retrain check: only {count} new classifications since last train, skipping")
            return

        logger.info(f"Auto-retrain triggered: {count} new classifications since last train at {last_train}")

        # Run training script in background
        train_script = os.path.join(base_dir, "scripts", "train_brand_watcher_classifier.py")
        if os.path.exists(train_script):
            subprocess.Popen(
                ["python", train_script],
                cwd=base_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Update marker
            os.makedirs(os.path.dirname(marker_file), exist_ok=True)
            with open(marker_file, 'w') as f:
                f.write(datetime.now().isoformat())

            db.facade.create_notification(
                username=None,
                type='brand_watcher',
                title='Brand Watcher: SLM Retrain Started',
                message=f'Auto-retrain triggered with {count} new classified articles.',
                link='/newsfeed?tab=brand-watcher'
            )
        else:
            logger.warning(f"Training script not found: {train_script}")

    except Exception as e:
        logger.error(f"Auto-retrain check error: {e}")


async def run_brand_watcher_monitor():
    """Background task to periodically check and run scheduled brand watcher classification."""
    global _background_task_status

    db = Database()
    monitor = BrandWatcherMonitor(db)

    logger.info("Brand watcher monitor background task started")
    _background_task_status["running"] = True

    check_interval = 60
    retrain_check_counter = 0

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            # Get schedules that are due to run
            due_schedules = monitor.get_due_schedules()
            _background_task_status["schedules_checked"] = len(due_schedules)

            if due_schedules:
                logger.info(f"Found {len(due_schedules)} brand watcher schedules due to run")

                for schedule in due_schedules:
                    try:
                        result = await monitor.run_schedule(schedule)
                        if result["success"]:
                            _background_task_status["schedules_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running brand watcher schedule {schedule.get('name')}: {e}")

            # Check auto-retrain every ~60 monitor cycles (~1 hour)
            retrain_check_counter += 1
            if retrain_check_counter >= 60:
                retrain_check_counter = 0
                try:
                    _check_auto_retrain(db)
                except Exception as e:
                    logger.error(f"Auto-retrain check failed: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Brand watcher monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        await asyncio.sleep(check_interval)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    """Run a specific schedule immediately (for manual triggering)."""
    monitor = BrandWatcherMonitor(db)

    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, brand_id, run_type, days_back, topics,
                   schedule_type, schedule_interval, schedule_unit, schedule_time,
                   last_run_at, next_run_at, run_count,
                   notify_on_complete, notify_threshold
            FROM bw_tracker_schedules
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
