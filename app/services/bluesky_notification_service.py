"""
Bluesky Notification Service for sending direct messages.

Uses the same credentials as the Bluesky collector:
- PROVIDER_BLUESKY_USERNAME: Bluesky handle (e.g., yourname.bsky.social)
- PROVIDER_BLUESKY_PASSWORD: App password (create at bsky.app/settings/app-passwords)

Note: Bluesky DMs require both users to follow each other or have DMs open.
"""

import os
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BlueskyNotificationService:
    """Service for sending Bluesky direct messages."""

    def __init__(self):
        self.username = os.getenv('PROVIDER_BLUESKY_USERNAME')
        self.password = os.getenv('PROVIDER_BLUESKY_PASSWORD')
        self.client = None
        self._initialized = False

    def _ensure_authenticated(self) -> bool:
        """Ensure we have an authenticated client."""
        if self._initialized and self.client:
            return True

        if not self.username or not self.password:
            logger.warning("Bluesky credentials not configured")
            return False

        try:
            from atproto import Client
            self.client = Client()
            self.client.login(self.username, self.password)
            self._initialized = True
            logger.info(f"Bluesky notification service authenticated as {self.username}")
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate Bluesky: {e}")
            return False

    def is_available(self) -> bool:
        """Check if Bluesky notification service is available."""
        return bool(self.username and self.password)

    def _resolve_handle_to_did(self, handle: str) -> Optional[str]:
        """Resolve a Bluesky handle to its DID."""
        if not self._ensure_authenticated():
            return None

        try:
            # Remove @ prefix if present
            handle = handle.lstrip('@')

            # Add .bsky.social if no domain
            if '.' not in handle:
                handle = f"{handle}.bsky.social"

            response = self.client.com.atproto.identity.resolve_handle(
                params={"handle": handle}
            )
            return response.did
        except Exception as e:
            logger.error(f"Failed to resolve handle {handle}: {e}")
            return None

    def _get_or_create_conversation(self, recipient_did: str) -> Optional[str]:
        """Get or create a conversation with the recipient."""
        if not self._ensure_authenticated():
            return None

        try:
            # Get existing conversations to check if one exists
            response = self.client.chat.bsky.convo.get_convo_for_members(
                params={"members": [recipient_did]}
            )

            if response and hasattr(response, 'convo') and response.convo:
                return response.convo.id

            # If no conversation exists, this will create one
            return response.convo.id if response.convo else None

        except Exception as e:
            logger.error(f"Failed to get/create conversation: {e}")
            return None

    def send_dm(
        self,
        recipient_handle: str,
        message: str
    ) -> bool:
        """
        Send a direct message to a Bluesky user.

        Args:
            recipient_handle: Bluesky handle (e.g., user.bsky.social or @user)
            message: Message text to send

        Returns:
            True if message was sent successfully
        """
        if not self._ensure_authenticated():
            return False

        try:
            # Resolve handle to DID
            recipient_did = self._resolve_handle_to_did(recipient_handle)
            if not recipient_did:
                logger.error(f"Could not resolve handle: {recipient_handle}")
                return False

            # Get or create conversation
            convo_id = self._get_or_create_conversation(recipient_did)
            if not convo_id:
                logger.error(f"Could not get conversation with {recipient_handle}")
                return False

            # Send the message
            self.client.chat.bsky.convo.send_message(
                data={
                    "convo_id": convo_id,
                    "message": {
                        "text": message
                    }
                }
            )

            logger.info(f"Bluesky DM sent to {recipient_handle}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Bluesky DM to {recipient_handle}: {e}")
            return False

    def send_signal_alert_dm(
        self,
        recipient_handle: str,
        instruction_name: str,
        matches: List[dict],
        topic: Optional[str] = None
    ) -> bool:
        """
        Send a signal alert as a Bluesky DM.

        Args:
            recipient_handle: Bluesky handle to send to
            instruction_name: Name of the signal instruction
            matches: List of matched articles
            topic: Optional topic filter

        Returns:
            True if message was sent successfully
        """
        topic_info = f" ({topic})" if topic else ""

        # Build message (Bluesky has character limits, keep it concise)
        message_parts = [
            f"🚨 Signal Alert: {instruction_name}{topic_info}",
            f"Found {len(matches)} match(es):",
            ""
        ]

        # Add top 3 matches (brief)
        for i, match in enumerate(matches[:3], 1):
            summary = match.get('summary', 'No summary')[:100]
            threat = match.get('threat_level', 'medium')
            threat_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(threat, '⚪')
            message_parts.append(f"{threat_emoji} {summary}...")

        if len(matches) > 3:
            message_parts.append(f"\n+{len(matches) - 3} more matches")

        message_parts.append("\n📊 View details in AuNoo dashboard")

        message = "\n".join(message_parts)

        # Bluesky has a 300 character limit per message, truncate if needed
        if len(message) > 290:
            message = message[:287] + "..."

        return self.send_dm(recipient_handle, message)


# Global instance
_bluesky_notification_service: Optional[BlueskyNotificationService] = None


def get_bluesky_notification_service() -> BlueskyNotificationService:
    """Get the singleton Bluesky notification service instance."""
    global _bluesky_notification_service
    if _bluesky_notification_service is None:
        _bluesky_notification_service = BlueskyNotificationService()
    return _bluesky_notification_service
