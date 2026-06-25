"""
Monitor and schedule threat intelligence processing.
Follows the same pattern as geopolitical_hotspots_monitor.py.
"""

import logging
import asyncio
from datetime import datetime, timedelta
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
    """Get the current status of the threat intelligence monitor background task"""
    return _background_task_status.copy()


def calculate_next_run(
    schedule_type: str,
    schedule_interval: int = 1,
    schedule_unit: str = 'hours',
    schedule_time: Optional[Any] = None,
    from_time: Optional[datetime] = None
) -> datetime:
    """
    Calculate the next run time based on schedule configuration.

    Args:
        schedule_type: 'interval' or 'daily'
        schedule_interval: Number of units between runs
        schedule_unit: 'minutes', 'hours', 'days', or 'weeks'
        schedule_time: Time of day to run (for daily schedules)
        from_time: Base time to calculate from (defaults to now)

    Returns:
        datetime: Next scheduled run time
    """
    now = from_time or datetime.now()

    if schedule_type == 'interval':
        # Interval-based scheduling
        if schedule_unit == 'minutes':
            return now + timedelta(minutes=schedule_interval)
        elif schedule_unit == 'hours':
            return now + timedelta(hours=schedule_interval)
        elif schedule_unit == 'days':
            return now + timedelta(days=schedule_interval)
        elif schedule_unit == 'weeks':
            return now + timedelta(weeks=schedule_interval)
        else:
            # Default to hours
            return now + timedelta(hours=schedule_interval)

    elif schedule_type == 'daily':
        # Daily at specific time
        if schedule_time:
            # schedule_time could be a time object or string
            if hasattr(schedule_time, 'hour'):
                hour = schedule_time.hour
                minute = schedule_time.minute
            else:
                # Parse string like "14:00"
                try:
                    parts = str(schedule_time).split(':')
                    hour = int(parts[0])
                    minute = int(parts[1]) if len(parts) > 1 else 0
                except:
                    hour, minute = 0, 0

            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        else:
            # No time specified, run same time tomorrow
            return now + timedelta(days=1)

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
                SELECT id, name, topic, batch_size, model, process_all,
                       schedule_enabled, schedule_type, schedule_interval,
                       schedule_unit, schedule_time,
                       last_run_at, next_run_at, run_count
                FROM threat_intel_schedules
                WHERE schedule_enabled = true
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

            updates.append("last_run_articles_processed = :articles_processed")
            params["articles_processed"] = articles_processed

            updates.append("last_run_threats_created = :threats_extracted")
            params["threats_extracted"] = threats_extracted

            updates.append("last_run_threats_updated = :actors_identified")
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
            article_limit = schedule.get('batch_size', 50)
            days_back = 7  # Default to 7 days back for articles

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
                    schedule_type=schedule.get('schedule_type', 'interval'),
                    schedule_interval=schedule.get('schedule_interval', 24),
                    schedule_unit=schedule.get('schedule_unit', 'hours'),
                    schedule_time=schedule.get('schedule_time')
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
                        model='gpt-5.4-mini'
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
                        # Run NER extraction on article text
                        try:
                            from app.utils.ner_extractor import extract_entities
                            article_text = f"{article.get('title', '')} {article.get('summary', '')}"
                            ner_entities = extract_entities(article_text)

                            if ner_entities.get('organizations'):
                                threat_data['ner_organizations'] = ner_entities['organizations']
                            if ner_entities.get('locations'):
                                threat_data['ner_locations'] = ner_entities['locations']
                            if ner_entities.get('persons'):
                                threat_data['ner_persons'] = ner_entities['persons']
                            if ner_entities.get('products'):
                                threat_data['ner_products'] = ner_entities['products']
                        except Exception as ner_err:
                            logger.warning(f"NER extraction failed: {ner_err}")

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

            # Update threat trends (escalating/declining)
            try:
                from scripts.calculate_threat_trends import (
                    get_threat_article_counts,
                    get_threat_ioc_counts,
                    calculate_trend,
                    update_threat_trends,
                    update_recent_article_counts
                )
                logger.info("Calculating threat trends...")
                article_data = get_threat_article_counts(days=7)
                ioc_data = get_threat_ioc_counts(days=7)

                trends_to_update = {}
                for threat_id, data in article_data.items():
                    ioc_info = ioc_data.get(threat_id, {'current_iocs': 0, 'previous_iocs': 0})
                    new_trend, _ = calculate_trend(
                        current_articles=data['current_count'],
                        previous_articles=data['previous_count'],
                        current_iocs=ioc_info['current_iocs'],
                        previous_iocs=ioc_info['previous_iocs'],
                        severity_score=data['severity_score']
                    )
                    trends_to_update[threat_id] = new_trend

                updated = update_threat_trends(trends_to_update)
                update_recent_article_counts(days=7)
                logger.info(f"Updated trends for {updated} threats")
            except Exception as e:
                logger.warning(f"Failed to update threat trends: {e}")

            result["success"] = True
            result["articles_processed"] = stats["processed"]
            result["threats_extracted"] = stats["threats"]
            result["actors_identified"] = stats["actors"]

            # Calculate next run time
            next_run = calculate_next_run(
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval', 24),
                schedule_unit=schedule.get('schedule_unit', 'hours'),
                schedule_time=schedule.get('schedule_time')
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
                schedule_type=schedule.get('schedule_type', 'interval'),
                schedule_interval=schedule.get('schedule_interval', 24),
                schedule_unit=schedule.get('schedule_unit', 'hours'),
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
            SELECT id, name, topic, batch_size, model, process_all,
                   schedule_enabled, schedule_type, schedule_interval,
                   schedule_unit, schedule_time,
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
