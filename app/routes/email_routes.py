"""
Email sharing routes for sending content via email.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import logging
import os

from app.security.session import verify_session
from app.services.email_service import get_email_service, markdown_to_html

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailStatusResponse(BaseModel):
    """Response for email status check."""
    configured: bool
    provider: Optional[str] = None


class ShareIncidentRequest(BaseModel):
    """Request to share an incident via email."""
    to_email: str
    incident_name: str
    incident_type: Optional[str] = "event"
    significance: Optional[str] = "medium"
    description: Optional[str] = None
    topic: Optional[str] = None
    entities: Optional[List[str]] = None
    strategic_relevance: Optional[str] = None
    plausibility: Optional[str] = None
    source_quality: Optional[str] = None


class ShareNarrativeRequest(BaseModel):
    """Request to share a narrative via email."""
    to_email: str
    narrative_name: str
    description: Optional[str] = None
    key_points: Optional[List[str]] = None
    topic: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    article_count: Optional[int] = None
    source_count: Optional[int] = None
    key_entities: Optional[List[str]] = None


class ShareBriefingRequest(BaseModel):
    """Request to share a briefing via email."""
    to_email: str
    persona: str
    executive_summary: Optional[str] = None
    articles: Optional[List[dict]] = None  # title, headline, executive_takeaway, category, source, date
    key_themes: Optional[List[str]] = None


class ShareResponse(BaseModel):
    """Response for share requests."""
    success: bool
    message: str


@router.get("/email/status", response_model=EmailStatusResponse)
async def get_email_status(session=Depends(verify_session)):
    """Check if email service is configured and available."""
    email_service = get_email_service()
    provider = os.getenv("EMAIL_PROVIDER", "resend")

    return EmailStatusResponse(
        configured=email_service.is_available(),
        provider=provider if email_service.is_available() else None
    )


@router.post("/share/incident", response_model=ShareResponse)
async def share_incident(
    request: ShareIncidentRequest,
    session=Depends(verify_session)
):
    """Share an incident via email."""
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    # Build email content
    subject = f"[AuNoo AI] Incident: {request.incident_name}"

    # Build HTML email
    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Incident Alert</h1>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
        f'<h2 style="color: #333; margin-top: 0;">{request.incident_name}</h2>',
    ]

    # Badges
    badges_html = []
    if request.incident_type:
        type_color = {"incident": "#dc3545", "event": "#0d6efd", "expertise": "#6f42c1", "trend": "#198754"}.get(request.incident_type.lower(), "#6c757d")
        badges_html.append(f'<span style="background: {type_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.incident_type}</span>')
    if request.significance:
        sig_color = {"high": "#dc3545", "medium": "#ffc107", "low": "#28a745"}.get(request.significance.lower(), "#6c757d")
        badges_html.append(f'<span style="background: {sig_color}; color: {"#000" if request.significance.lower() == "medium" else "#fff"}; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.significance}</span>')
    if request.plausibility:
        badges_html.append(f'<span style="background: #17a2b8; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">Plausibility: {request.plausibility}</span>')
    if request.source_quality:
        badges_html.append(f'<span style="background: #6c757d; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">Source: {request.source_quality}</span>')

    if badges_html:
        html_parts.append(f'<p style="margin: 10px 0;">{"".join(badges_html)}</p>')

    if request.topic:
        html_parts.append(f'<p style="color: #666; margin: 5px 0;"><strong>Topic:</strong> {request.topic}</p>')

    if request.description:
        html_parts.append(f'<div style="background: white; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #667eea;">')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.description}</p>')
        html_parts.append('</div>')

    if request.strategic_relevance:
        html_parts.append(f'<div style="background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #2196f3;">')
        html_parts.append(f'<h4 style="color: #1976d2; margin: 0 0 8px 0;">Strategic Relevance</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333;">{request.strategic_relevance}</p>')
        html_parts.append('</div>')

    if request.entities:
        html_parts.append(f'<p style="margin: 15px 0;"><strong>Key Entities:</strong></p>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 4px;">')
        for entity in request.entities[:10]:
            html_parts.append(f'<span style="background: #e8eaf6; color: #3f51b5; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{entity}</span>')
        html_parts.append('</div>')

    html_parts.extend([
        '</div>',
        '<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e9ecef; border-top: none;">',
        '<p style="color: #666; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong></p>',
        '</div>',
        '</div>'
    ])

    body_html = '\n'.join(html_parts)

    # Plain text version
    body_text = f"""Incident: {request.incident_name}

Type: {request.incident_type or 'N/A'}
Significance: {request.significance or 'N/A'}
{f'Topic: {request.topic}' if request.topic else ''}
{f'Plausibility: {request.plausibility}' if request.plausibility else ''}
{f'Source Quality: {request.source_quality}' if request.source_quality else ''}

{request.description or ''}

{f'Strategic Relevance: {request.strategic_relevance}' if request.strategic_relevance else ''}

{f'Key Entities: {", ".join(request.entities[:10])}' if request.entities else ''}

---
Shared from AuNoo AI
"""

    try:
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )

        if success:
            logger.info(f"Incident shared via email to {request.to_email}")
            return ShareResponse(success=True, message="Incident shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing incident: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/share/narrative", response_model=ShareResponse)
async def share_narrative(
    request: ShareNarrativeRequest,
    session=Depends(verify_session)
):
    """Share a narrative via email."""
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Narrative: {request.narrative_name}"

    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Narrative Insight</h1>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
        f'<h2 style="color: #333; margin-top: 0;">{request.narrative_name}</h2>',
    ]

    # Badges row - sentiment, confidence, counts
    badges_html = []
    if request.sentiment:
        sentiment_color = {"positive": "#28a745", "negative": "#dc3545", "neutral": "#6c757d", "mixed": "#ffc107"}.get(request.sentiment.lower(), "#6c757d")
        text_color = "#000" if request.sentiment.lower() == "mixed" else "#fff"
        badges_html.append(f'<span style="background: {sentiment_color}; color: {text_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.sentiment}</span>')
    if request.confidence:
        badges_html.append(f'<span style="background: #17a2b8; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{int(request.confidence)}% confidence</span>')
    if request.article_count:
        badges_html.append(f'<span style="background: #6c757d; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.article_count} articles</span>')
    if request.source_count:
        badges_html.append(f'<span style="background: #6c757d; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{request.source_count} sources</span>')

    if badges_html:
        html_parts.append(f'<p style="margin: 10px 0;">{"".join(badges_html)}</p>')

    if request.topic:
        html_parts.append(f'<p style="color: #666;"><strong>Topic:</strong> {request.topic}</p>')

    if request.description:
        html_parts.append(f'<div style="background: white; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #11998e;">')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.description}</p>')
        html_parts.append('</div>')

    if request.key_points:
        html_parts.append('<h4 style="color: #333;">Key Points:</h4>')
        html_parts.append('<ul style="padding-left: 20px;">')
        for point in request.key_points:
            html_parts.append(f'<li style="margin: 8px 0; color: #333;">{point}</li>')
        html_parts.append('</ul>')

    if request.key_entities:
        html_parts.append(f'<p style="margin: 15px 0;"><strong>Key Entities:</strong></p>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 4px;">')
        for entity in request.key_entities[:10]:
            html_parts.append(f'<span style="background: #e8f5e9; color: #2e7d32; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{entity}</span>')
        html_parts.append('</div>')

    html_parts.extend([
        '</div>',
        '<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e9ecef; border-top: none;">',
        '<p style="color: #666; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong></p>',
        '</div>',
        '</div>'
    ])

    body_html = '\n'.join(html_parts)

    body_text = f"""Narrative: {request.narrative_name}

{f'Topic: {request.topic}' if request.topic else ''}

{request.description or ''}

{f'Key Points:' if request.key_points else ''}
{chr(10).join(f'- {p}' for p in (request.key_points or []))}

---
Shared from AuNoo AI
"""

    try:
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )

        if success:
            return ShareResponse(success=True, message="Narrative shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing narrative: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/share/briefing", response_model=ShareResponse)
async def share_briefing(
    request: ShareBriefingRequest,
    session=Depends(verify_session)
):
    """Share a briefing via email."""
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Executive Briefing - {request.persona}"

    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Executive Briefing</h1>',
        f'<p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0;">{request.persona} Perspective</p>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
    ]

    if request.executive_summary:
        html_parts.append(f'<div style="background: linear-gradient(135deg, #fdf2f8 0%, #faf5ff 100%); padding: 15px; border-radius: 4px; margin-bottom: 15px; border-left: 4px solid #ec4899;">')
        html_parts.append(f'<h4 style="color: #be185d; margin: 0 0 8px 0;">Executive Summary</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.executive_summary}</p>')
        html_parts.append('</div>')

    if request.articles:
        html_parts.append('<h4 style="color: #333;">Top Stories:</h4>')
        for i, article in enumerate(request.articles[:6], 1):
            title = article.get('title') or article.get('headline', 'Untitled')
            takeaway = article.get('executive_takeaway', '')
            category = article.get('category', '')
            source = article.get('source', '')
            date = article.get('date', '')
            url = article.get('url', '')

            # Build source/date line
            source_info = []
            if source:
                source_info.append(source)
            if date:
                source_info.append(date)
            source_line = ', '.join(source_info)

            html_parts.append(f'<div style="background: white; padding: 12px; border-radius: 4px; margin: 8px 0; border: 1px solid #e9ecef;">')
            # Title with optional link
            if url:
                html_parts.append(f'<p style="margin: 0; font-weight: 600; color: #333;">{i}. <a href="{url}" style="color: #333; text-decoration: none;">{title}</a></p>')
            else:
                html_parts.append(f'<p style="margin: 0; font-weight: 600; color: #333;">{i}. {title}</p>')
            # Source and date
            if source_line:
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #888; font-size: 12px;">{source_line}</p>')
            # Category badge
            if category:
                html_parts.append(f'<span style="background: #e2e8f0; color: #475569; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-top: 6px; display: inline-block;">{category}</span>')
            # Takeaway
            if takeaway:
                html_parts.append(f'<p style="margin: 8px 0 0 0; color: #666; font-size: 14px;">{takeaway}</p>')
            html_parts.append('</div>')

    if request.key_themes:
        html_parts.append('<h4 style="color: #333; margin-top: 20px;">Key Themes:</h4>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 6px;">')
        for theme in request.key_themes:
            html_parts.append(f'<span style="background: white; color: #333; padding: 6px 12px; border-radius: 20px; font-size: 13px; border: 1px solid #e9ecef;">{theme}</span>')
        html_parts.append('</div>')

    html_parts.extend([
        '</div>',
        '<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid #e9ecef; border-top: none;">',
        '<p style="color: #666; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong></p>',
        '</div>',
        '</div>'
    ])

    body_html = '\n'.join(html_parts)

    body_text = f"""Executive Briefing - {request.persona}

{request.executive_summary or ''}

Top Stories:
{chr(10).join(f'{i+1}. {a.get("title", "Untitled")}' for i, a in enumerate((request.articles or [])[:6]))}

{f'Key Themes: {", ".join(request.key_themes)}' if request.key_themes else ''}

---
Shared from AuNoo AI
"""

    try:
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )

        if success:
            return ShareResponse(success=True, message="Briefing shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing briefing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
