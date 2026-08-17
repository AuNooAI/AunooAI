"""
Notification service for emerging topics alerts.
Supports email, in-app notifications, and Bluesky DMs.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.database import Database

logger = logging.getLogger(__name__)


class EmergingTopicsNotificationService:
    """Service for sending notifications about detected emerging topics."""

    def __init__(self, db: Database):
        self.db = db

    async def send_notifications(
        self,
        topics: List[Dict[str, Any]],
        channels: Dict[str, bool],
        email_recipients: Optional[List[str]] = None,
        bluesky_handle: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send notifications through enabled channels.

        Args:
            topics: List of topic dictionaries to notify about
            channels: Dict of channel -> enabled (e.g., {"email": True, "in_app": True})
            email_recipients: List of email addresses for email notifications
            bluesky_handle: Bluesky handle for DM notifications

        Returns:
            Dict with success status per channel
        """
        results = {
            "email": {"sent": False, "error": None},
            "in_app": {"sent": False, "error": None},
            "bluesky": {"sent": False, "error": None}
        }

        if not topics:
            logger.info("No topics to notify about")
            return results

        # Send email notifications
        if channels.get("email") and email_recipients:
            try:
                await self._send_email_notifications(topics, email_recipients)
                results["email"]["sent"] = True
                logger.info(f"Sent email notifications to {len(email_recipients)} recipients")
            except Exception as e:
                results["email"]["error"] = str(e)
                logger.error(f"Failed to send email notifications: {e}")

        # Send in-app notifications
        if channels.get("in_app"):
            try:
                self._create_in_app_notifications(topics)
                results["in_app"]["sent"] = True
                logger.info("Created in-app notifications")
            except Exception as e:
                results["in_app"]["error"] = str(e)
                logger.error(f"Failed to create in-app notifications: {e}")

        # Send Bluesky DM
        if channels.get("bluesky") and bluesky_handle:
            try:
                await self._send_bluesky_notification(topics, bluesky_handle)
                results["bluesky"]["sent"] = True
                logger.info(f"Sent Bluesky DM to {bluesky_handle}")
            except Exception as e:
                results["bluesky"]["error"] = str(e)
                logger.error(f"Failed to send Bluesky notification: {e}")

        return results

    async def _send_email_notifications(
        self,
        topics: List[Dict[str, Any]],
        recipients: List[str]
    ) -> None:
        """Send email notifications for detected topics."""
        try:
            from app.services.email_service import get_email_service, markdown_to_html

            email_service = get_email_service()
            if not email_service or not email_service.is_configured():
                logger.warning("Email service not configured")
                return

            # Build email content
            subject = f"Emerging Topics Alert: {len(topics)} new topic(s) detected"

            # Build markdown body
            body_lines = [
                f"# Emerging Topics Alert",
                f"",
                f"**{len(topics)} new or accelerating topic(s)** have been detected.",
                f"",
                f"---",
                f""
            ]

            for i, topic in enumerate(topics[:10], 1):  # Limit to 10 topics
                label = topic.get("topic_label", "Unknown Topic")
                description = topic.get("topic_description", "")[:200]
                article_count = topic.get("article_count", 0)
                detection_type = topic.get("detection_type", "unknown")
                confidence = topic.get("confidence_score", 0)

                # Get trend score if available
                trend_score = topic.get("trend_score", {})
                composite = trend_score.get("composite", 0) if isinstance(trend_score, dict) else 0

                body_lines.extend([
                    f"## {i}. {label}",
                    f"",
                    f"{description}...",
                    f"",
                    f"- **Articles:** {article_count}",
                    f"- **Type:** {detection_type}",
                    f"- **Confidence:** {confidence:.0%}" if confidence else "",
                    f"- **Score:** {composite:.0f}/100" if composite else "",
                    f"",
                    f"---",
                    f""
                ])

            body_lines.extend([
                f"",
                f"[View All Topics in Dashboard](/explore#emerging-topics)",
                f"",
                f"---",
                f"",
                f"*This is an automated notification from Aunoo AI.*"
            ])

            body = "\n".join(body_lines)
            html_body = self._build_email_html(body)

            # Send to each recipient
            for recipient in recipients:
                try:
                    email_service.send_email(
                        to_addresses=[recipient],
                        subject=subject,
                        body_html=html_body,
                        body_text=body,
                        ai_generated=True,
                    )
                except Exception as e:
                    logger.error(f"Failed to send email to {recipient}: {e}")

        except ImportError:
            logger.warning("Email service not available")
        except Exception as e:
            logger.error(f"Email notification error: {e}")
            raise

    def _build_email_html(self, markdown_body: str) -> str:
        """Build HTML email from markdown."""
        try:
            from app.services.email_service import markdown_to_html
            content_html = markdown_to_html(markdown_body)
        except ImportError:
            content_html = f"<pre>{markdown_body}</pre>"

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #ec4899, #8b5cf6); padding: 20px; border-radius: 8px 8px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">Emerging Topics Alert</h1>
            </div>
            <div style="background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                {content_html}
            </div>
            <div style="text-align: center; padding: 20px; color: #6b7280; font-size: 12px;">
                <p>Aunoo AI - Strategic Intelligence Platform</p>
            </div>
        </body>
        </html>
        """

    def _create_in_app_notifications(self, topics: List[Dict[str, Any]]) -> None:
        """Create in-app notifications for detected topics."""
        try:
            # Create a summary notification
            topic_count = len(topics)
            if topic_count == 1:
                topic = topics[0]
                title = f"New Emerging Topic: {topic.get('topic_label', 'Unknown')[:50]}"
                message = topic.get('topic_description', '')[:200]
            else:
                title = f"{topic_count} Emerging Topics Detected"
                labels = [t.get('topic_label', 'Unknown')[:30] for t in topics[:3]]
                message = f"Including: {', '.join(labels)}" + ("..." if topic_count > 3 else "")

            # Create notification (username=None for system-wide)
            self.db.facade.create_notification(
                username=None,  # System-wide notification
                type="emerging_topic_detected",
                title=title,
                message=message,
                link="/explore#emerging-topics"
            )

        except Exception as e:
            logger.error(f"In-app notification error: {e}")
            raise

    async def _send_bluesky_notification(
        self,
        topics: List[Dict[str, Any]],
        handle: str
    ) -> None:
        """Send Bluesky DM notification."""
        try:
            from app.services.bluesky_notification_service import BlueskyNotificationService

            bsky_service = BlueskyNotificationService()
            if not bsky_service.is_configured():
                logger.warning("Bluesky notification service not configured")
                return

            # Build message (300 char limit for DMs)
            topic_count = len(topics)
            if topic_count == 1:
                topic = topics[0]
                label = topic.get('topic_label', 'Unknown')[:50]
                message = f"🚨 Emerging Topic Alert\n\n{label}\n\nArticles: {topic.get('article_count', 0)}"
            else:
                labels = [t.get('topic_label', 'Unknown')[:25] for t in topics[:3]]
                message = f"🚨 {topic_count} Emerging Topics\n\n" + "\n".join(f"• {l}" for l in labels)
                if topic_count > 3:
                    message += f"\n...and {topic_count - 3} more"

            # Truncate to 300 chars
            if len(message) > 290:
                message = message[:287] + "..."

            await bsky_service.send_dm(handle, message)

        except ImportError:
            logger.warning("Bluesky notification service not available")
        except Exception as e:
            logger.error(f"Bluesky notification error: {e}")
            raise

    async def send_test_notification(
        self,
        channels: Dict[str, bool],
        email_recipients: Optional[List[str]] = None,
        bluesky_handle: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send a test notification through enabled channels."""
        test_topics = [{
            "topic_label": "Test Emerging Topic",
            "topic_description": "This is a test notification to verify your notification settings are working correctly.",
            "article_count": 5,
            "detection_type": "accelerating",
            "confidence_score": 0.85,
            "trend_score": {"composite": 75}
        }]

        return await self.send_notifications(
            topics=test_topics,
            channels=channels,
            email_recipients=email_recipients,
            bluesky_handle=bluesky_handle
        )
