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
from urllib.parse import quote
import re

logger = logging.getLogger(__name__)


def markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML for email rendering."""
    if not text:
        return ""

    # Extract markdown links before escaping HTML (to preserve URLs)
    # Store them temporarily with placeholders
    links = []
    def store_link(match):
        link_text = match.group(1)
        url = match.group(2)
        placeholder = f"__LINK_PLACEHOLDER_{len(links)}__"
        links.append((placeholder, link_text, url))
        return placeholder

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', store_link, text)

    # Escape HTML special chars
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Restore links as HTML anchors
    for placeholder, link_text, url in links:
        text = text.replace(placeholder, f'<a href="{url}" target="_blank" style="color: #667eea; text-decoration: underline;">{link_text}</a>')

    # Headers
    text = re.sub(r'^### (.+)$', r'<h4 style="color: #333; margin: 15px 0 8px 0;">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h3 style="color: #333; margin: 18px 0 10px 0;">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h2 style="color: #333; margin: 20px 0 12px 0;">\1</h2>', text, flags=re.MULTILINE)

    # Bold and italic
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Bullet points - convert to <uli> first
    text = re.sub(r'^[\-\*] (.+)$', r'<uli>\1</uli>', text, flags=re.MULTILINE)

    # Numbered lists - convert to <oli> first
    text = re.sub(r'^\d+\. (.+)$', r'<oli>\1</oli>', text, flags=re.MULTILINE)

    # Wrap consecutive <uli> items in <ul>
    text = re.sub(r'(<uli>.*?</uli>\n?)+', lambda m: '<ul style="margin: 10px 0; padding-left: 20px;">' + m.group(0).replace('<uli>', '<li style="margin: 4px 0;">').replace('</uli>', '</li>') + '</ul>', text)

    # Wrap consecutive <oli> items in <ol>
    text = re.sub(r'(<oli>.*?</oli>\n?)+', lambda m: '<ol style="margin: 10px 0; padding-left: 20px;">' + m.group(0).replace('<oli>', '<li style="margin: 4px 0;">').replace('</oli>', '</li>') + '</ol>', text)

    # Line breaks for paragraphs
    text = re.sub(r'\n\n+', '</p><p style="margin: 10px 0;">', text)
    text = f'<p style="margin: 10px 0;">{text}</p>'

    # Clean up empty paragraphs
    text = re.sub(r'<p[^>]*>\s*</p>', '', text)

    return text


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
                "Content-Type": "application/json",
                "User-Agent": "AunooAI/1.0"
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
        topic: Optional[str] = None,
        report_content: Optional[str] = None,
        podcast_url: Optional[str] = None,
        report_id: Optional[int] = None
    ) -> bool:
        """Send a signal alert email notification with optional report and podcast."""
        subject = f"[AuNoo AI] Signal Alert: {instruction_name}"

        topic_info = f" for topic '{topic}'" if topic else ""

        # Build Auspex deep link
        domain = os.getenv("DOMAIN", "localhost:10015")
        protocol = "https" if "localhost" not in domain else "http"
        base_url = f"{protocol}://{domain}"

        # Create a contextual Auspex query with article URLs
        auspex_query = f"Analyze the following signal alert findings from research agent '{instruction_name}':\n\n"
        for i, match in enumerate(matches[:5], 1):
            summary = match.get('summary', '')[:200]
            url = match.get('article_uri', '')
            if summary:
                auspex_query += f"{i}. {summary}\n"
                if url:
                    auspex_query += f"   Source: {url}\n"
        auspex_query += "\nProvide insights on these findings and suggest follow-up investigations."

        # URL encode the query
        encoded_query = quote(auspex_query)
        auspex_url = f"{base_url}/explore?auspex_query={encoded_query}"

        html_parts = [
            f"<h2>Signal Alert: {instruction_name}</h2>",
            f"<p>Your research agent <strong>{instruction_name}</strong> found {len(matches)} matching article(s){topic_info}.</p>",
        ]

        # Add Auspex button with table-based layout for better email client support
        # Using solid background color as fallback since gradients don't work in all email clients
        html_parts.append(f"""
        <table width="100%" cellspacing="0" cellpadding="0" style="margin: 20px 0;">
            <tr>
                <td align="center">
                    <table cellspacing="0" cellpadding="0">
                        <tr>
                            <td align="center" bgcolor="#667eea" style="background-color: #667eea; border-radius: 8px;">
                                <a href="{auspex_url}" target="_blank" style="display: inline-block; padding: 15px 30px; color: #ffffff; text-decoration: none; font-weight: bold; font-size: 16px;">
                                    🔍 Investigate with Auspex AI
                                </a>
                            </td>
                        </tr>
                    </table>
                    <p style="color: #666666; margin: 8px 0 0 0; font-size: 12px;">
                        Click to open AuNoo and analyze these findings with AI
                    </p>
                </td>
            </tr>
        </table>
        """)

        # Add Report Section if available
        if report_content:
            # Extract podcast section if embedded (so it doesn't get truncated)
            podcast_section = ""
            main_content = report_content
            podcast_marker = "## 🎙️ Audio Briefing"
            if podcast_marker in report_content:
                # Split at the divider before the podcast section
                parts = report_content.split("---\n\n## 🎙️ Audio Briefing")
                if len(parts) == 2:
                    main_content = parts[0].rstrip()
                    podcast_section = "## 🎙️ Audio Briefing" + parts[1]

            # Truncate main content if needed, but preserve podcast section
            truncated = ""
            if len(main_content) > 4000:
                main_content = main_content[:4000]
                if report_id:
                    report_url = f"{base_url}/explore?tab=reports&report_id={report_id}"
                    truncated = f'...<p><em>(Report truncated for email. <a href="{report_url}" style="color: #667eea;">View full report</a>)</em></p>'
                else:
                    truncated = '...<p><em>(Report truncated for email)</em></p>'

            # Convert to HTML
            report_html = markdown_to_html(main_content)
            podcast_html = markdown_to_html(podcast_section) if podcast_section else ""

            html_parts.append(f"""
            <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-left: 4px solid #667eea; border-radius: 4px;">
                <h3 style="margin-top: 0; color: #667eea;">📊 Generated Report</h3>
                <div style="font-family: inherit; line-height: 1.6;">
                    {report_html}{truncated}
                    {podcast_html}
                </div>
            </div>
            """)

        # Add Podcast Section if available
        if podcast_url:
            full_podcast_url = f"{base_url}{podcast_url}" if podcast_url.startswith('/') else podcast_url
            html_parts.append(f"""
            <div style="margin: 20px 0; padding: 15px; background: #f0e6ff; border-radius: 8px; text-align: center;">
                <h3 style="margin-top: 0; color: #764ba2;">🎙️ Audio Briefing Available</h3>
                <p style="margin: 10px 0;">Listen to an AI-generated podcast summary of these findings:</p>
                <a href="{full_podcast_url}" target="_blank" style="display: inline-block; background: #764ba2; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold;">
                    ▶️ Play Podcast
                </a>
            </div>
            """)

        html_parts.append("<hr>")
        html_parts.append("<h3>Matched Articles:</h3>")

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

        # Plain text version
        body_text = f"""Signal Alert: {instruction_name}

Found {len(matches)} matching article(s){topic_info}.

Investigate with Auspex AI: {auspex_url}

"""
        if report_content:
            body_text += f"""
--- GENERATED REPORT ---
{report_content[:2000]}{'...' if len(report_content) > 2000 else ''}
------------------------

"""
        if podcast_url:
            full_podcast_url = f"{base_url}{podcast_url}" if podcast_url.startswith('/') else podcast_url
            body_text += f"Listen to Audio Briefing: {full_podcast_url}\n\n"

        body_text += "--- MATCHED ARTICLES ---\n"
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
