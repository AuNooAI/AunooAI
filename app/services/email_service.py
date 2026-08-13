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

import base64
import os
import smtplib
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
from urllib.parse import quote
import re

from app.compliance.ai_disclosure import (
    disclosure_footer_html,
    disclosure_text,
    email_headers,
)

logger = logging.getLogger(__name__)


# Inline styles per tag — email clients ignore <style> blocks, so styles must
# ride on the elements themselves.
_EMAIL_TAG_STYLES = {
    'h1': 'font-size:20px;color:#333;margin:20px 0 12px 0;',
    'h2': 'font-size:18px;color:#333;margin:18px 0 10px 0;',
    'h3': 'font-size:16px;color:#333;margin:15px 0 8px 0;',
    'h4': 'font-size:14px;color:#333;margin:12px 0 6px 0;',
    'h5': 'font-size:13px;color:#333;margin:10px 0 5px 0;',
    'p': 'margin:10px 0;',
    'ul': 'margin:10px 0;padding-left:20px;',
    'ol': 'margin:10px 0;padding-left:20px;',
    'li': 'margin:4px 0;',
    'table': 'border-collapse:collapse;margin:10px 0;',
    'th': 'border:1px solid #ddd;padding:6px 8px;background:#f3f4f6;text-align:left;',
    'td': 'border:1px solid #ddd;padding:6px 8px;',
    'code': 'background:#f3f4f6;padding:1px 4px;border-radius:3px;',
    'blockquote': 'border-left:3px solid #ddd;margin:10px 0;padding-left:12px;color:#555;',
    'hr': 'border:none;border-top:1px solid #ddd;margin:16px 0;',
}


def markdown_to_html(text: str) -> str:
    """Convert markdown to email-safe HTML.

    Uses the real markdown renderer (handles #### headers, nested lists,
    tables — the regex fallback leaked those raw into emails), then stamps
    inline styles onto the tags for email-client compatibility."""
    if not text:
        return ""
    try:
        import markdown as _md
        # ATX headers indented by 1-3 spaces render as paragraphs in this
        # markdown build (LLMs sometimes emit " # Title"); de-indent them so a
        # leading-space heading still becomes <h1>..<h6>.
        text = re.sub(r'(?m)^[ \t]{1,3}(#{1,6}\s)', r'\1', text)
        html = _md.markdown(text, extensions=["tables", "sane_lists", "nl2br"])
        html = re.sub(
            r'<(h1|h2|h3|h4|h5|p|ul|ol|li|table|th|td|code|blockquote|hr)>',
            lambda m: f'<{m.group(1)} style="{_EMAIL_TAG_STYLES[m.group(1)]}">',
            html,
        )
        html = html.replace(
            '<a href', '<a style="color:#667eea;text-decoration:underline;" href')
        return html
    except Exception as e:
        logger.warning(f"markdown renderer unavailable, using legacy converter: {e}")
        return _legacy_markdown_to_html(text)


def _legacy_markdown_to_html(text: str) -> str:
    """Regex-based fallback converter (pre-2026-07 behavior)."""
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


def social_ref(uri: str, fallback: Optional[str] = None) -> dict:
    """Parse a match URL into {short, profile, post, platform, kind}.

    For social posts `short` is the display handle (with @) and `profile`/`post`
    are the account and post URLs. Anything that isn't a recognised social post
    is a web article: it's labelled with its domain, not "Social" — most observer
    matches are news, and calling them posts mislabels the whole source list."""
    u = (uri or "").strip()
    m = re.match(r'https?://(?:www\.)?bsky\.app/profile/([^/?#]+)/post/', u)
    if m:
        h = m.group(1)
        return {"short": "@" + h.split('.')[0], "profile": f"https://bsky.app/profile/{h}",
                "post": u, "platform": "Bluesky", "kind": "social"}
    m = re.match(r'https?://(?:www\.)?(?:x|twitter)\.com/([^/?#]+)/status/', u)
    if m:
        h = m.group(1)
        return {"short": "@" + h, "profile": f"https://x.com/{h}", "post": u,
                "platform": "X", "kind": "social"}
    m = re.match(r'https?://(?:www\.)?reddit\.com/(r/[^/?#]+)', u)
    if m:
        sub = m.group(1)
        return {"short": sub, "profile": f"https://reddit.com/{sub}", "post": u,
                "platform": "Reddit", "kind": "social"}
    m = re.match(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/', u)
    if m:
        return {"short": fallback or "Instagram post", "profile": u, "post": u,
                "platform": "Instagram", "kind": "social"}
    m = re.match(r'https?://(?:www\.)?tiktok\.com/(@[^/?#]+)/video/', u)
    if m:
        h = m.group(1)
        return {"short": h, "profile": f"https://www.tiktok.com/{h}", "post": u,
                "platform": "TikTok", "kind": "social"}
    # Web article — show the publisher domain and link to the site, not "Social".
    m = re.match(r'https?://([^/?#]+)', u)
    if m:
        host = m.group(1).split('@')[-1]
        return {"short": fallback or re.sub(r'^www\.', '', host),
                "profile": f"https://{host}/", "post": u,
                "platform": "News", "kind": "web"}
    return {"short": fallback or "source", "profile": u or "#", "post": u or "#",
            "platform": "Source", "kind": "web"}


def linkify_handles_md(md: str, matches: Optional[List[dict]]) -> str:
    """Turn plain @handles in report markdown into links to the account profile,
    using the URLs from the matched posts. Longest handles first so overlapping
    prefixes don't mis-link; skips handles already inside a link."""
    if not md or not matches:
        return md
    prof = {}
    for m in matches:
        r = social_ref(m.get("article_uri", ""))
        if r["short"].startswith("@") and r["profile"] and r["profile"] != "#":
            prof.setdefault(r["short"], r["profile"])
    for h in sorted(prof, key=len, reverse=True):
        md = re.sub(r'(?<![\[\w/])' + re.escape(h) + r'(?![\w.])',
                    f'[{h}]({prof[h]})', md)
    return md


def render_matched_sources_html(matches: Optional[List[dict]]) -> str:
    """Clean, linked 'sources' cards for the matched posts — account link,
    platform, quote/summary, and a post link. Shared by the alert email and the
    online report so both show the same complete, navigable source list."""
    if not matches:
        return ""
    cards = []
    for m in matches:
        r = social_ref(m.get("article_uri", ""))
        summary = (m.get("summary") or "").strip()
        threat = (m.get("threat_level") or "medium").lower()
        conf = m.get("confidence", 0) or 0
        try:
            conf_s = f"{float(conf):.0%}"
        except Exception:
            conf_s = str(conf)
        color = {"high": "#dc3545", "medium": "#d39e00", "low": "#28a745"}.get(threat, "#6c757d")
        link_label = "view post" if r.get("kind") == "social" else "read article"
        post_link = (f' &nbsp;·&nbsp; <a href="{r["post"]}" style="color:#4055c6;">{link_label} ↗</a>'
                     if r["post"] and r["post"] != "#" else "")
        cards.append(
            '<div style="margin:0 0 12px 0;padding:12px 14px;border:1px solid #e5e7eb;border-radius:8px;">'
            '<p style="margin:0 0 6px 0;">'
            f'<a href="{r["profile"]}" style="color:#4055c6;font-weight:bold;text-decoration:none;">{r["short"]}</a>'
            f'<span style="color:#888;"> · {r["platform"]}</span>{post_link}</p>'
            f'<p style="margin:0 0 6px 0;color:#333;">{summary}</p>'
            '<p style="margin:0;font-size:12px;color:#555;"><strong>Priority:</strong> '
            f'<span style="color:{color};font-weight:bold;">{threat.upper()}</span> &nbsp;|&nbsp; '
            f'<strong>Confidence:</strong> {conf_s}</p></div>')
    return "\n".join(cards)


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
        from_email: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Send an email.

        ``extra_headers`` (optional) sets additional message headers, e.g. the
        ``X-AI-Generated`` marker on AI-generated content (EU AI Act Art. 50).

        ``attachments`` (optional) is a list of dicts each shaped as::

            {"filename": str, "content": bytes, "mime_type": str}

        Both providers carry the bytes through to the recipient with the
        given filename and MIME type. Resend base64-encodes them in the
        JSON body; SMTP wraps them as MIME parts.
        """
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
        from_email: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
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

            if extra_headers:
                data["headers"] = extra_headers

            if attachments:
                data["attachments"] = [
                    {
                        "filename": a["filename"],
                        "content": base64.b64encode(a["content"]).decode("ascii"),
                        # Resend accepts content_type for MIME hinting
                        "content_type": a.get("mime_type", "application/octet-stream"),
                    }
                    for a in attachments
                ]

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
        from_email: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        if not self.is_configured():
            logger.warning("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD.")
            return False

        try:
            # When carrying attachments we need a 'mixed' container with the
            # 'alternative' part nested inside it. For text-only we keep the
            # simpler 'alternative' container.
            if attachments:
                msg = MIMEMultipart("mixed")
                alt = MIMEMultipart("alternative")
                if body_text:
                    alt.attach(MIMEText(body_text, "plain"))
                alt.attach(MIMEText(body_html, "html"))
                msg.attach(alt)
                for a in attachments:
                    mime_type = a.get("mime_type", "application/octet-stream")
                    maintype, _, subtype = mime_type.partition("/")
                    part = MIMEBase(maintype or "application", subtype or "octet-stream")
                    part.set_payload(a["content"])
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{a["filename"]}"',
                    )
                    msg.attach(part)
            else:
                msg = MIMEMultipart("alternative")
                if body_text:
                    msg.attach(MIMEText(body_text, "plain"))
                msg.attach(MIMEText(body_html, "html"))

            msg["Subject"] = subject
            msg["From"] = from_email or self.from_email
            msg["To"] = ", ".join(to_addresses)
            for _hk, _hv in (extra_headers or {}).items():
                msg[_hk] = _hv

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
        from_email: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
        ai_generated: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Send an email using the configured provider.

        Set ``ai_generated=True`` for emails whose body is AI-generated
        content (reports, briefings, alerts): a visible disclosure footer is
        appended and an ``X-AI-Generated`` marker header is attached, per EU
        AI Act Article 50. Leave it False for transactional mail (password
        resets, verification), which must not be labelled as AI content.

        See :meth:`EmailProvider.send_email` for the ``attachments`` shape.
        """
        if not to_addresses:
            logger.warning("No recipients specified for email")
            return False

        headers = dict(extra_headers or {})
        if ai_generated:
            body_html = f"{body_html}{disclosure_footer_html()}"
            if body_text is not None:
                body_text = f"{body_text}\n\n{disclosure_text()}"
            headers.update(email_headers())

        return self.provider.send_email(
            to_addresses=to_addresses,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            from_email=from_email,
            attachments=attachments,
            extra_headers=headers or None,
        )

    def send_signal_alert_email(
        self,
        to_address: str,
        instruction_name: str,
        matches: List[dict],
        topic: Optional[str] = None,
        report_content: Optional[str] = None,
        podcast_url: Optional[str] = None,
        report_id: Optional[int] = None,
        report_download_url: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
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
            # Link @handles in the narrative to their account profiles (inline).
            report_content = linkify_handles_md(report_content, matches)
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
                <h3 style="margin-top: 0; color: #667eea;">📊 AI-Generated Report</h3>
                <div style="font-family: inherit; line-height: 1.6;">
                    {report_html}{truncated}
                    {podcast_html}
                </div>
            </div>
            """)

        # No-auth download links for the full report (signed, time-limited)
        if report_download_url:
            pdf_url = (report_download_url.replace('fmt=html', 'fmt=pdf')
                       if 'fmt=' in report_download_url
                       else report_download_url + '&fmt=pdf')
            html_parts.append(f"""
            <p style="margin: 12px 0; text-align: center;">
                <a href="{report_download_url}" target="_blank" style="display: inline-block; background: #667eea; color: white; padding: 8px 18px; border-radius: 5px; text-decoration: none; font-weight: bold; margin-right: 8px;">📄 View full report</a>
                <a href="{pdf_url}" target="_blank" style="display: inline-block; background: #4b5563; color: white; padding: 8px 18px; border-radius: 5px; text-decoration: none; font-weight: bold;">⬇️ Download PDF</a>
            </p>
            <p style="text-align: center; color: #999; font-size: 11px; margin: 4px 0 0 0;">No login needed — links are valid for 30 days.</p>
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
        html_parts.append("<h3>Matched sources:</h3>")
        html_parts.append(render_matched_sources_html(matches))

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
--- AI-GENERATED REPORT ---
{report_content[:2000]}{'...' if len(report_content) > 2000 else ''}
------------------------

"""
        if podcast_url:
            full_podcast_url = f"{base_url}{podcast_url}" if podcast_url.startswith('/') else podcast_url
            body_text += f"Listen to Audio Briefing: {full_podcast_url}\n\n"

        body_text += "--- MATCHED ARTICLES ---\n"
        for i, match in enumerate(matches[:10], 1):
            body_text += f"Match {i}: {match.get('summary', 'No summary')}\n"
            body_text += f"Priority: {match.get('threat_level', 'medium')} | Confidence: {match.get('confidence', 0):.0%}\n\n"

        if report_download_url:
            body_text += f"\nDownload full report (no login needed, 30 days): {report_download_url}\n"

        return self.send_email(
            to_addresses=[to_address],
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments,
            ai_generated=True,
        )


# Global instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the singleton email service instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
