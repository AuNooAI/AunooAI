"""
Email Service for sending notifications.

Supports multiple email providers:
1. Resend (free tier: 100 emails/day) - Recommended
2. SMTP (traditional)

Configure via environment variables:
- EMAIL_PROVIDER: "resend" or "smtp" (default: resend)

For Resend:
- RESEND_API_KEY: Your Resend API key (get free at resend.com)
- RESEND_FROM_EMAIL: Sender email (must be verified domain or onboarding@resend.dev for testing)

For SMTP:
- SMTP_HOST: SMTP server hostname
- SMTP_PORT: SMTP server port (default: 587)
- SMTP_USER: SMTP username
- SMTP_PASSWORD: SMTP password
- SMTP_FROM_EMAIL: Default sender email
- SMTP_USE_TLS: Whether to use TLS (default: true)
"""

import os
import smtplib
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass

    @abstractmethod
    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        """Send an email."""
        pass


class ResendProvider(EmailProvider):
    """Email provider using Resend API (free tier: 100 emails/day)."""

    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        if not self.is_configured():
            logger.warning("Resend not configured. Set RESEND_API_KEY environment variable.")
            return False

        try:
            import urllib.request
            import urllib.error

            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "from": from_email or self.from_email,
                "to": to_addresses,
                "subject": subject,
                "html": body_html
            }

            if body_text:
                data["text"] = body_text

            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                logger.info(f"Resend email sent successfully: {result.get('id')}")
                return True

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            logger.error(f"Resend API error: {e.code} - {error_body}")
            return False
        except Exception as e:
            logger.error(f"Error sending email via Resend: {e}")
            return False


class SMTPProvider(EmailProvider):
    """Traditional SMTP email provider."""

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "noreply@aunoo.ai")
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    def is_configured(self) -> bool:
        return bool(self.host and self.user and self.password)

    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        if not self.is_configured():
            logger.warning("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email or self.from_email
            msg["To"] = ", ".join(to_addresses)

            if body_text:
                msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.host, self.port) as server:
                if self.use_tls:
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.sendmail(
                    from_email or self.from_email,
                    to_addresses,
                    msg.as_string()
                )

            logger.info(f"SMTP email sent to {', '.join(to_addresses)}")
            return True

        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False


class EmailService:
    """Service for sending email notifications with multiple provider support."""

    def __init__(self):
        provider_name = os.getenv("EMAIL_PROVIDER", "resend").lower()

        if provider_name == "smtp":
            self.provider = SMTPProvider()
        else:
            self.provider = ResendProvider()

        self.provider_name = provider_name

    def is_available(self) -> bool:
        """Check if email service is available."""
        return self.provider.is_configured()

    def send_email(
        self,
        to_addresses: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> bool:
        """Send an email using the configured provider."""
        if not to_addresses:
            logger.warning("No recipients specified for email")
            return False

        return self.provider.send_email(
            to_addresses=to_addresses,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            from_email=from_email
        )

    def send_signal_alert_email(
        self,
        to_address: str,
        instruction_name: str,
        matches: List[dict],
        topic: Optional[str] = None
    ) -> bool:
        """Send a signal alert email notification."""
        subject = f"[AuNoo AI] Signal Alert: {instruction_name}"

        topic_info = f" for topic '{topic}'" if topic else ""
        html_parts = [
            f"<h2>Signal Alert: {instruction_name}</h2>",
            f"<p>Your research agent <strong>{instruction_name}</strong> found {len(matches)} matching article(s){topic_info}.</p>",
            "<hr>",
            "<h3>Matched Articles:</h3>",
        ]

        for i, match in enumerate(matches[:10], 1):
            article_uri = match.get('article_uri', 'N/A')
            summary = match.get('summary', 'No summary available')
            threat_level = match.get('threat_level', 'medium')
            confidence = match.get('confidence', 0)
            reasoning = match.get('reasoning', '')

            threat_color = {
                'high': '#dc3545',
                'medium': '#ffc107',
                'low': '#28a745'
            }.get(threat_level, '#6c757d')

            html_parts.append(f"""
            <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 8px;">
                <h4 style="margin-top: 0;">Match {i}</h4>
                <p><strong>Article:</strong> <a href="{article_uri}">{article_uri}</a></p>
                <p><strong>Summary:</strong> {summary}</p>
                <p>
                    <strong>Threat Level:</strong>
                    <span style="color: {threat_color}; font-weight: bold;">{threat_level.upper()}</span>
                    &nbsp;|&nbsp;
                    <strong>Confidence:</strong> {confidence:.0%}
                </p>
                {f'<p><strong>Reasoning:</strong> {reasoning}</p>' if reasoning else ''}
            </div>
            """)

        if len(matches) > 10:
            html_parts.append(f"<p><em>... and {len(matches) - 10} more matches.</em></p>")

        html_parts.extend([
            "<hr>",
            "<p style='color: #666; font-size: 12px;'>",
            "Automated notification from AuNoo AI Research Agents.",
            "</p>"
        ])

        body_html = "\n".join(html_parts)

        body_text = f"""Signal Alert: {instruction_name}

Found {len(matches)} matching article(s){topic_info}.

"""
        for i, match in enumerate(matches[:10], 1):
            body_text += f"Match {i}: {match.get('summary', 'No summary')}\n"
            body_text += f"Threat: {match.get('threat_level', 'medium')} | Confidence: {match.get('confidence', 0):.0%}\n\n"

        return self.send_email(
            to_addresses=[to_address],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )


# Global instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the singleton email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
