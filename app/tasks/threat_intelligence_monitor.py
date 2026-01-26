"""
Monitor and schedule threat intelligence processing.
Follows the same pattern as geopolitical_hotspots_monitor.py.
"""

import logging
import asyncio
from datetime import datetime, timedelta
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
    """Get the current status of the threat intelligence monitor background task"""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    hour: int = 0,
    day_of_week: int = 0,
    from_time: Optional[datetime] = None
) -> datetime:
    """
    Calculate the next run time based on schedule configuration.

    Args:
        schedule_type: 'hourly', 'daily', or 'weekly'
        hour: Hour of day to run (for daily/weekly)
        day_of_week: Day of week (0=Sunday) for weekly
        from_time: Base time to calculate from (defaults to now)

    Returns:
        datetime: Next scheduled run time
    """
    now = from_time or datetime.now()

    if schedule_type == 'hourly':
        # Next hour
        next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_run

    elif schedule_type == 'daily':
        # Next occurrence of specified hour
        next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run

    elif schedule_type == 'weekly':
        # Next occurrence of specified day and hour
        days_until = (day_of_week - now.weekday()) % 7
        if days_until == 0 and now.hour >= hour:
            days_until = 7
        next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_until)
        return next_run

    # Default: run in 24 hours
    return now + timedelta(hours=24)


class ThreatIntelligenceMonitor:
    """Monitor for scheduled threat intelligence processing."""

    def __init__(self, db: Database):
        self.db = db
        self.running_schedules: set = set()

    def get_due_schedules(self) -> List[Dict]:
        """Get all schedules that are due to run (next_run_at <= NOW())."""
        try:
            conn = self.db._temp_get_connection()
            result = conn.execute(text("""
                SELECT id, name, schedule_type, hour, day_of_week,
                       article_limit, days_back, is_active,
                       last_run_at, next_run_at, run_count
                FROM threat_intel_schedules
                WHERE is_active = true
                  AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """))
            schedules = [dict(row._mapping) for row in result]
            conn.close()
            return schedules
        except Exception as e:
            logger.error(f"Error getting due threat intel schedules: {e}")
            return []

    def update_schedule_status(
        self,
        schedule_id: int,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[datetime] = None,
        articles_processed: int = 0,
        threats_extracted: int = 0,
        actors_identified: int = 0
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

            updates.append("articles_processed = :articles_processed")
            params["articles_processed"] = articles_processed

            updates.append("threats_extracted = :threats_extracted")
            params["threats_extracted"] = threats_extracted

            updates.append("actors_identified = :actors_identified")
            params["actors_identified"] = actors_identified

            if status == 'success':
                updates.append("run_count = run_count + 1")

            updates.append("updated_at = NOW()")

            conn.execute(text(f"""
                UPDATE threat_intel_schedules
                SET {', '.join(updates)}
                WHERE id = :id
            """), params)
            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating threat intel schedule status: {e}")

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
            "threats_extracted": 0,
            "actors_identified": 0,
            "error": None
        }

        if schedule_id in self.running_schedules:
            logger.info(f"Threat intel schedule {schedule_name} is already running, skipping")
            return result

        self.running_schedules.add(schedule_id)
        self.update_schedule_status(schedule_id, 'running')

        try:
            # Import the threat intelligence service
            from app.services.threat_intelligence_service import (
                get_threat_intelligence_service,
                extract_threat_with_llm,
            )

            service = get_threat_intelligence_service()

            # Get configuration from schedule
            article_limit = schedule.get('article_limit', 50)
            days_back = schedule.get('days_back', 1)

            logger.info(f"Running threat intel schedule: {schedule_name} (ID: {schedule_id}, limit: {article_limit}, days: {days_back})")

            # Get articles to process
            articles = service.get_unprocessed_articles(
                limit=article_limit,
                days_back=days_back
            )

            if not articles:
                logger.info(f"No articles to process for schedule {schedule_name}")
                result["success"] = True

                # Calculate next run time
                next_run = calculate_next_run(
                    schedule_type=schedule.get('schedule_type', 'daily'),
                    hour=schedule.get('hour', 0),
                    day_of_week=schedule.get('day_of_week', 0)
                )
                self.update_schedule_status(schedule_id, 'success', next_run_at=next_run)
                return result

            stats = {
                "processed": 0,
                "threats": 0,
                "actors": 0,
                "skipped": 0,
                "errors": 0
            }

            unique_actors = set()

            for article in articles:
                try:
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                    # Extract threats using LLM
                    extraction_result = await extract_threat_with_llm(
                        article['title'] or "",
                        article['summary'] or "",
                        article['content'] or "",
                        model='gpt-4o-mini'
                    )

                    if extraction_result.get('no_threat'):
                        stats["skipped"] += 1
                        # Mark article as processed even if no threat
                        service.mark_article_processed(article['uri'])
                        continue

                    # Process extracted threats
                    threats = extraction_result.get('threats', [])
                    if not threats and extraction_result.get('threat_name'):
                        # Single threat format
                        threats = [extraction_result]

                    for threat_data in threats:
                        # Create or update threat
                        threat_id = service.create_or_update_threat(threat_data)

                        if threat_id:
                            # Link article to threat
                            service.link_article_to_threat(
                                threat_id,
                                article['uri'],
                                relevance_score=threat_data.get('confidence', 0.8)
                            )
                            stats["threats"] += 1

                            # Track actors
                            if threat_data.get('threat_actor_name'):
                                unique_actors.add(threat_data['threat_actor_name'])

                            # Extract IOCs if present
                            iocs = threat_data.get('iocs', [])
                            for ioc in iocs:
                                service.create_ioc(
                                    indicator_type=ioc.get('type'),
                                    indicator_value=ioc.get('value'),
                                    threat_id=threat_id,
                                    confidence=ioc.get('confidence', 70),
                                    source_article_uri=article['uri']
                                )

                    # Mark article as processed
                    service.mark_article_processed(article['uri'])
                    stats["processed"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"Error processing article in schedule {schedule_name}: {e}")

            stats["actors"] = len(unique_actors)

            # Update daily stats
            try:
                service.update_daily_stats()
            except Exception as e:
                logger.warning(f"Failed to update daily stats: {e}")

            result["success"] = True
            result["articles_processed"] = stats["processed"]
            result["threats_extracted"] = stats["threats"]
            result["actors_identified"] = stats["actors"]

            # Calculate next run time
            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'daily'),
                hour=schedule.get('hour', 0),
                day_of_week=schedule.get('day_of_week', 0)
            )

            self.update_schedule_status(
                schedule_id,
                'success',
                next_run_at=next_run,
                articles_processed=stats["processed"],
                threats_extracted=stats["threats"],
                actors_identified=stats["actors"]
            )

            # Send notification if configured
            await self._send_notification(schedule, stats)

            logger.info(
                f"Threat intel schedule {schedule_name} completed. "
                f"Processed: {stats['processed']}, Threats: {stats['threats']}, Actors: {stats['actors']}. "
                f"Next run: {next_run}"
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error running threat intel schedule {schedule_name}: {error_msg}", exc_info=True)
            result["error"] = error_msg

            # Still calculate next run time even on error
            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'daily'),
                hour=schedule.get('hour', 0),
                day_of_week=schedule.get('day_of_week', 0)
            )
            self.update_schedule_status(schedule_id, 'error', error=error_msg, next_run_at=next_run)

        finally:
            self.running_schedules.discard(schedule_id)

        return result

    async def _send_notification(self, schedule: Dict, stats: Dict) -> None:
        """Send notification about completed processing."""
        try:
            db = get_database_instance()

            title = f"Threat Intelligence Update: {schedule.get('name', 'Scheduled Run')}"
            message = (
                f"Processed {stats['processed']} articles.\n"
                f"Threats extracted: {stats['threats']}, Actors identified: {stats['actors']}"
            )

            # Create notification in database
            db.facade.create_notification(
                username=None,  # System-wide notification
                type='threat_intelligence',
                title=title,
                message=message,
                link='/explore?tab=threatintel'
            )

            logger.info(f"Notification created for threat intel schedule {schedule.get('name')}")

        except Exception as e:
            logger.error(f"Failed to send notification for threat intel schedule: {e}")


async def run_threat_intelligence_monitor():
    """Background task to periodically check and run scheduled threat processing."""
    global _background_task_status

    db = Database()
    monitor = ThreatIntelligenceMonitor(db)

    logger.info("Threat intelligence monitor background task started")
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
                logger.info(f"Found {len(due_schedules)} threat intel schedules due to run")

                # Run each due schedule
                for schedule in due_schedules:
                    try:
                        result = await monitor.run_schedule(schedule)
                        if result["success"]:
                            _background_task_status["schedules_run"] += 1
                    except Exception as e:
                        logger.error(f"Error running threat intel schedule {schedule.get('name')}: {e}")

            _background_task_status["last_error"] = None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Threat intelligence monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg

        finally:
            _background_task_status["is_checking"] = False

        # Wait before next check
        await asyncio.sleep(check_interval)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    """Run a specific schedule immediately (for manual triggering)."""
    monitor = ThreatIntelligenceMonitor(db)

    # Get the schedule details
    try:
        conn = db._temp_get_connection()
        result = conn.execute(text("""
            SELECT id, name, schedule_type, hour, day_of_week,
                   article_limit, days_back, is_active,
                   last_run_at, next_run_at, run_count
            FROM threat_intel_schedules
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
