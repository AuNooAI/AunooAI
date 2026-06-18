"""
Monitor and schedule newsfeed dashboard generation.
Follows the same pattern as emerging_topics_monitor.py.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from sqlalchemy import text

from app.database import Database

logger = logging.getLogger(__name__)

# Global variable to track task status
_background_task_status = {
    "running": False,
    "last_check_time": None,
    "last_error": None,
    "is_checking": False
}


def get_task_status() -> Dict:
    """Get the current status of the newsfeed dashboard monitor background task"""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    check_interval: int,
    interval_unit: str,
    schedule_time: Optional[Any] = None,
    from_time: Optional[datetime] = None
) -> datetime:
    """Calculate the next run time based on schedule configuration."""
    from datetime import time as dt_time

    now = from_time or datetime.now()

    if schedule_type == 'daily' and schedule_time:
        # For daily schedule, calculate next occurrence of the time
        if isinstance(schedule_time, str):
            try:
                hour, minute = map(int, schedule_time.split(':'))
                schedule_time = dt_time(hour, minute)
            except:
                schedule_time = dt_time(9, 0)

        next_run = now.replace(
            hour=schedule_time.hour,
            minute=schedule_time.minute,
            second=0,
            microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run
    else:
        # For interval schedule
        if interval_unit == 'hours':
            delta = timedelta(hours=check_interval)
        elif interval_unit == 'days':
            delta = timedelta(days=check_interval)
        else:
            delta = timedelta(hours=check_interval)

        return now + delta


class NewsfeedDashboardMonitor:
    """Monitor for scheduled newsfeed dashboard generation."""

    def __init__(self, db: Database):
        self.db = db

    def get_settings(self) -> Optional[Dict]:
        """Get current scheduler settings."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT schedule_enabled, schedule_type, check_interval, interval_unit, schedule_time,
                       generate_briefing, generate_highlights, generate_narratives,
                       persona, model, topic_filter
                FROM newsfeed_dashboard_settings
                WHERE id = 1
            """))
            row = result.mappings().first()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return None

    def get_status(self) -> Optional[Dict]:
        """Get current monitor status."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT last_run_time, next_run_time, last_run_status,
                       last_error, is_running, run_count
                FROM newsfeed_dashboard_monitor_status
                WHERE id = 1
            """))
            row = result.mappings().first()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return None

    def is_due(self) -> bool:
        """Check if dashboard generation is due."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT s.schedule_enabled, st.next_run_time, st.is_running
                FROM newsfeed_dashboard_settings s
                CROSS JOIN newsfeed_dashboard_monitor_status st
                WHERE s.id = 1 AND st.id = 1
            """))
            row = result.mappings().first()
            conn.close()

            if not row:
                return False

            if not row['schedule_enabled']:
                return False

            if row['is_running']:
                return False

            if row['next_run_time'] is None:
                return True

            return datetime.now() >= row['next_run_time']

        except Exception as e:
            logger.error(f"Error checking if due: {e}")
            return False

    def update_status(
        self,
        is_running: bool = None,
        last_run_time: datetime = None,
        last_run_status: str = None,
        last_error: str = None,
        next_run_time: datetime = None,
        increment_run_count: bool = False
    ) -> None:
        """Update monitor status."""
        try:
            conn = self.db._temp_get_connection()

            updates = []
            params = {}

            if is_running is not None:
                updates.append("is_running = :is_running")
                params["is_running"] = is_running

            if last_run_time is not None:
                updates.append("last_run_time = :last_run_time")
                params["last_run_time"] = last_run_time

            if last_run_status is not None:
                updates.append("last_run_status = :last_run_status")
                params["last_run_status"] = last_run_status

            if last_error is not None:
                updates.append("last_error = :last_error")
                params["last_error"] = last_error
            elif last_run_status == 'success':
                updates.append("last_error = NULL")

            if next_run_time is not None:
                updates.append("next_run_time = :next_run_time")
                params["next_run_time"] = next_run_time

            if increment_run_count:
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            if updates:
                conn.execute(text(f"""
                    UPDATE newsfeed_dashboard_monitor_status
                    SET {', '.join(updates)}
                    WHERE id = 1
                """), params)
                conn.commit()

            conn.close()

        except Exception as e:
            logger.error(f"Error updating status: {e}")

    async def run_generation(self, settings: Dict) -> Dict[str, Any]:
        """Run dashboard generation based on settings and save snapshot."""
        import time
        start_time = time.time()

        result = {
            "success": False,
            "briefing_generated": False,
            "highlights_generated": False,
            "narratives_generated": False,
            "error": None
        }

        # Data to save in snapshot
        briefing_articles = None
        highlights_data = None
        narratives_data = None

        try:
            # Generate briefing (six articles)
            if settings.get('generate_briefing', True):
                try:
                    from app.routes.news_feed_routes import _generate_six_articles_internal
                    briefing_articles = await _generate_six_articles_internal(
                        persona=settings.get('persona', 'CEO'),
                        model=settings.get('model', 'gpt-5.4-mini'),
                        topic=settings.get('topic_filter')
                    )
                    result["briefing_generated"] = briefing_articles is not None and len(briefing_articles) > 0
                    if result["briefing_generated"]:
                        logger.info(f"Briefing generated: {len(briefing_articles)} articles")
                except Exception as e:
                    logger.error(f"Failed to generate briefing: {e}")
                    result["error"] = f"Briefing: {str(e)}"

            # Generate highlights/incidents
            if settings.get('generate_highlights', True):
                try:
                    from app.routes.news_feed_routes import _regenerate_highlights_internal
                    await _regenerate_highlights_internal(
                        topic=settings.get('topic_filter')
                    )
                    result["highlights_generated"] = True
                    logger.info("Highlights generated successfully")
                except Exception as e:
                    logger.error(f"Failed to generate highlights: {e}")
                    if result["error"]:
                        result["error"] += f"; Highlights: {str(e)}"
                    else:
                        result["error"] = f"Highlights: {str(e)}"

            # Generate narratives
            if settings.get('generate_narratives', False):
                try:
                    from app.routes.news_feed_routes import _regenerate_narratives_internal
                    await _regenerate_narratives_internal(
                        topic=settings.get('topic_filter')
                    )
                    result["narratives_generated"] = True
                    logger.info("Narratives generated successfully")
                except Exception as e:
                    logger.error(f"Failed to generate narratives: {e}")
                    if result["error"]:
                        result["error"] += f"; Narratives: {str(e)}"
                    else:
                        result["error"] = f"Narratives: {str(e)}"

            result["success"] = (
                result["briefing_generated"] or
                result["highlights_generated"] or
                result["narratives_generated"]
            )

            # Save dashboard snapshot if anything was generated
            if result["success"]:
                try:
                    from app.routes.news_feed_routes import save_dashboard_snapshot
                    generation_duration = time.time() - start_time

                    snapshot_id = save_dashboard_snapshot(
                        topic=settings.get('topic_filter'),
                        persona=settings.get('persona', 'CEO'),
                        model=settings.get('model', 'gpt-5.4-mini'),
                        briefing_articles=briefing_articles,
                        highlights_data=highlights_data,
                        narratives_data=narratives_data,
                        generation_duration=generation_duration,
                        error_message=result.get("error")
                    )

                    if snapshot_id:
                        logger.info(f"Dashboard snapshot saved (ID: {snapshot_id})")
                    else:
                        logger.warning("Failed to save dashboard snapshot")

                except Exception as e:
                    logger.error(f"Error saving dashboard snapshot: {e}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Dashboard generation failed: {e}")

        return result


async def run_newsfeed_dashboard_monitor():
    """Background task to periodically check and run dashboard generation."""
    global _background_task_status

    db = Database()
    monitor = NewsfeedDashboardMonitor(db)

    logger.info("Newsfeed dashboard monitor background task started")
    _background_task_status["running"] = True

    # Check every 60 seconds
    check_interval = 60

    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()

            # Check if generation is due
            if monitor.is_due():
                settings = monitor.get_settings()
                if settings and settings.get('schedule_enabled'):
                    logger.info("Dashboard generation is due, starting...")

                    # Mark as running
                    monitor.update_status(is_running=True)

                    try:
                        # Run generation
                        result = await monitor.run_generation(settings)

                        # Calculate next run time
                        next_run = calculate_next_run(
                            schedule_type=settings.get('schedule_type', 'interval'),
                            check_interval=settings.get('check_interval', 24),
                            interval_unit=settings.get('interval_unit', 'hours'),
                            schedule_time=settings.get('schedule_time')
                        )

                        # Update status - only set error if overall run failed
                        monitor.update_status(
                            is_running=False,
                            last_run_time=datetime.now(),
                            last_run_status='success' if result['success'] else 'error',
                            last_error=result.get('error') if not result['success'] else None,
                            next_run_time=next_run,
                            increment_run_count=result['success']
                        )

                        logger.info(f"Dashboard generation complete. Next run: {next_run}")

                    except Exception as e:
                        logger.error(f"Dashboard generation error: {e}")
                        monitor.update_status(
                            is_running=False,
                            last_run_status='error',
                            last_error=str(e)
                        )

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Newsfeed dashboard monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        # Wait before next check
        await asyncio.sleep(check_interval)


async def run_dashboard_generation_now(db: Database, topic_filter: Optional[str] = None) -> Dict[str, Any]:
    """Run dashboard generation immediately (for manual triggering)."""
    monitor = NewsfeedDashboardMonitor(db)

    # Get settings
    settings = monitor.get_settings() or {}

    # Override topic filter if provided
    if topic_filter:
        settings['topic_filter'] = topic_filter

    # Mark as running
    monitor.update_status(is_running=True)

    try:
        result = await monitor.run_generation(settings)

        # Calculate next run if scheduling is enabled
        if settings.get('schedule_enabled'):
            next_run = calculate_next_run(
                schedule_type=settings.get('schedule_type', 'interval'),
                check_interval=settings.get('check_interval', 24),
                interval_unit=settings.get('interval_unit', 'hours'),
                schedule_time=settings.get('schedule_time')
            )
        else:
            next_run = None

        # Update status - only set error if overall run failed
        monitor.update_status(
            is_running=False,
            last_run_time=datetime.now(),
            last_run_status='success' if result['success'] else 'error',
            last_error=result.get('error') if not result['success'] else None,
            next_run_time=next_run,
            increment_run_count=result['success']
        )

        return result

    except Exception as e:
        monitor.update_status(
            is_running=False,
            last_run_status='error',
            last_error=str(e)
        )
        return {"success": False, "error": str(e)}
