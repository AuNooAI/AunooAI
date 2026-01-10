"""
Monitor and schedule emerging topics detection.
Follows the same pattern as keyword_monitor.py.
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
    "next_check_time": None,
    "topics_detected": 0,
    "articles_analyzed": 0,
    "is_checking": False
}


def get_task_status() -> Dict:
    """Get the current status of the emerging topics monitor background task"""
    return _background_task_status.copy()


class EmergingTopicsMonitor:
    """Monitor for scheduled emerging topics detection."""

    def __init__(self, db: Database):
        self.db = db
        self._load_settings()

    def _load_settings(self) -> None:
        """Load settings from database."""
        try:
            conn = self.db.get_raw_connection()
            result = conn.execute(text("""
                SELECT
                    schedule_enabled, check_interval, interval_unit, min_articles,
                    sample_size, days_back, model, topic_filter,
                    notifications_enabled, notification_channels, min_confidence,
                    cooldown_minutes, email_recipients, bluesky_handle,
                    detection_type_filters, last_notification_time
                FROM emerging_topics_settings
                WHERE id = 1
            """))
            row = result.mappings().first()
            conn.close()

            if row:
                self.schedule_enabled = row['schedule_enabled']
                self.check_interval = row['check_interval']
                self.interval_unit = row['interval_unit']
                self.min_articles = row['min_articles']
                self.sample_size = row['sample_size'] or 200
                self.days_back = row['days_back'] or 7
                self.model = row['model'] or 'gpt-4o-mini'
                self.topic_filter = row['topic_filter']
                self.notifications_enabled = row['notifications_enabled']
                self.notification_channels = row['notification_channels'] or {}
                self.min_confidence = row['min_confidence'] or 0.7
                self.cooldown_minutes = row['cooldown_minutes'] or 360
                self.email_recipients = row['email_recipients'] or []
                self.bluesky_handle = row['bluesky_handle']
                self.detection_type_filters = row['detection_type_filters'] or ['accelerating', 'new_cluster']
                self.last_notification_time = row['last_notification_time']

                # Calculate interval in seconds
                if self.interval_unit == 'hours':
                    self.check_interval_seconds = self.check_interval * 3600
                elif self.interval_unit == 'days':
                    self.check_interval_seconds = self.check_interval * 86400
                else:
                    self.check_interval_seconds = self.check_interval * 60  # minutes
            else:
                self._set_defaults()

        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            self._set_defaults()

    def _set_defaults(self) -> None:
        """Set default values."""
        self.schedule_enabled = False
        self.check_interval = 24
        self.interval_unit = 'hours'
        self.check_interval_seconds = 86400  # 24 hours
        self.min_articles = 50
        self.sample_size = 200
        self.days_back = 7
        self.model = 'gpt-4o-mini'
        self.topic_filter = None
        self.notifications_enabled = False
        self.notification_channels = {}
        self.min_confidence = 0.7
        self.cooldown_minutes = 360
        self.email_recipients = []
        self.bluesky_handle = None
        self.detection_type_filters = ['accelerating', 'new_cluster']
        self.last_notification_time = None

    def _update_status(
        self,
        last_check_time: Optional[datetime] = None,
        next_check_time: Optional[datetime] = None,
        topics_detected: Optional[int] = None,
        articles_analyzed: Optional[int] = None,
        last_error: Optional[str] = None,
        is_running: Optional[bool] = None
    ) -> None:
        """Update monitor status in database."""
        try:
            conn = self.db.get_raw_connection()

            updates = []
            params = {"id": 1}

            if last_check_time is not None:
                updates.append("last_check_time = :last_check")
                params["last_check"] = last_check_time
            if next_check_time is not None:
                updates.append("next_check_time = :next_check")
                params["next_check"] = next_check_time
            if topics_detected is not None:
                updates.append("topics_detected = :topics")
                params["topics"] = topics_detected
            if articles_analyzed is not None:
                updates.append("articles_analyzed = :articles")
                params["articles"] = articles_analyzed
            if last_error is not None:
                updates.append("last_error = :error")
                params["error"] = last_error
            elif last_error == "":
                updates.append("last_error = NULL")
            if is_running is not None:
                updates.append("is_running = :running")
                params["running"] = is_running

            updates.append("updated_at = NOW()")

            if updates:
                conn.execute(text(f"""
                    UPDATE emerging_topics_monitor_status
                    SET {', '.join(updates)}
                    WHERE id = :id
                """), params)
                conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error updating status: {e}")

    async def run_detection(self) -> Dict[str, Any]:
        """Run emerging topics detection."""
        global _background_task_status

        _background_task_status["is_checking"] = True
        self._update_status(is_running=True)

        result = {
            "success": False,
            "topics_detected": 0,
            "articles_analyzed": 0,
            "new_topics": [],
            "error": None
        }

        try:
            # Import service here to avoid circular imports
            from app.services.emerging_topics.emerging_topics_service import (
                EmergingTopicsService,
                EmergingTopicsConfig
            )

            # Create config
            config = EmergingTopicsConfig(
                days_back=self.days_back,
                max_sample_articles=self.sample_size,
                model=self.model
            )

            # Initialize service
            service = EmergingTopicsService(config)

            # Run detection
            logger.info(f"Running emerging topics detection (filter: {self.topic_filter})")
            detection_result = await service.run_detection(
                topic_filter=self.topic_filter,
                days_back=self.days_back
            )

            topics = detection_result.get("emerging_topics", [])
            result["success"] = True
            result["topics_detected"] = len(topics)
            result["articles_analyzed"] = detection_result.get("articles_sampled", 0)

            # Filter for new/accelerating topics for notifications
            new_topics = [
                t for t in topics
                if t.get("detection_type") in self.detection_type_filters
                and t.get("confidence_score", 0) >= self.min_confidence
            ]
            result["new_topics"] = new_topics

            # Update global status
            _background_task_status["topics_detected"] = len(topics)
            _background_task_status["articles_analyzed"] = result["articles_analyzed"]
            _background_task_status["last_check_time"] = datetime.now()
            _background_task_status["last_error"] = None

            # Update database status
            self._update_status(
                last_check_time=datetime.now(),
                topics_detected=len(topics),
                articles_analyzed=result["articles_analyzed"],
                last_error="",
                is_running=False
            )

            # Send notifications if enabled and there are new topics
            if self.notifications_enabled and new_topics:
                await self._send_notifications(new_topics)

            logger.info(f"Detection complete: {len(topics)} topics detected")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Detection error: {error_msg}", exc_info=True)
            result["error"] = error_msg

            _background_task_status["last_error"] = error_msg
            self._update_status(last_error=error_msg, is_running=False)

        finally:
            _background_task_status["is_checking"] = False

        return result

    async def _send_notifications(self, topics: list) -> None:
        """Send notifications for detected topics."""
        try:
            # Check cooldown
            if self.last_notification_time:
                elapsed = (datetime.now() - self.last_notification_time).total_seconds() / 60
                if elapsed < self.cooldown_minutes:
                    logger.info(f"Notification cooldown active ({self.cooldown_minutes - elapsed:.0f} min remaining)")
                    return

            # Import notification service
            try:
                from app.services.emerging_topics_notification_service import (
                    EmergingTopicsNotificationService
                )
                notification_service = EmergingTopicsNotificationService(self.db)
                await notification_service.send_notifications(
                    topics=topics,
                    channels=self.notification_channels,
                    email_recipients=self.email_recipients,
                    bluesky_handle=self.bluesky_handle
                )

                # Update last notification time
                conn = self.db.get_raw_connection()
                conn.execute(text("""
                    UPDATE emerging_topics_settings
                    SET last_notification_time = NOW(), updated_at = NOW()
                    WHERE id = 1
                """))
                conn.commit()
                conn.close()

                logger.info(f"Sent notifications for {len(topics)} topics")

            except ImportError:
                logger.warning("Notification service not available")
            except Exception as e:
                logger.error(f"Failed to send notifications: {e}")

        except Exception as e:
            logger.error(f"Notification error: {e}")


async def run_emerging_topics_monitor():
    """Background task to periodically run emerging topics detection."""
    global _background_task_status

    db = Database()
    monitor = EmergingTopicsMonitor(db)

    logger.info("Emerging topics monitor background task started")
    _background_task_status["running"] = True

    while True:
        try:
            # Reload settings each iteration
            monitor._load_settings()

            if not monitor.schedule_enabled:
                logger.debug("Emerging topics scheduling is disabled")
                # Check again in 60 seconds
                await asyncio.sleep(60)
                continue

            # Calculate next check time
            next_check = datetime.now() + timedelta(seconds=monitor.check_interval_seconds)
            _background_task_status["next_check_time"] = next_check
            monitor._update_status(next_check_time=next_check)

            logger.info(
                f"Emerging topics detection scheduled - next check in "
                f"{monitor.check_interval} {monitor.interval_unit} at {next_check.strftime('%H:%M:%S')}"
            )

            # Sleep until next check
            await asyncio.sleep(monitor.check_interval_seconds)

            # Run detection
            if monitor.schedule_enabled:  # Re-check in case it was disabled
                logger.info("Starting scheduled emerging topics detection")
                result = await monitor.run_detection()

                if result["success"]:
                    logger.info(
                        f"Scheduled detection completed: {result['topics_detected']} topics, "
                        f"{result['articles_analyzed']} articles analyzed"
                    )
                else:
                    logger.error(f"Scheduled detection failed: {result['error']}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Emerging topics monitor error: {error_msg}", exc_info=True)
            _background_task_status["last_error"] = error_msg
            # Sleep before retrying
            await asyncio.sleep(60)


async def run_detection_now(db: Database, topic_filter: Optional[str] = None) -> Dict[str, Any]:
    """Run detection immediately (for manual triggering)."""
    monitor = EmergingTopicsMonitor(db)
    if topic_filter:
        monitor.topic_filter = topic_filter
    return await monitor.run_detection()
