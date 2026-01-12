"""
Email sharing routes for sending content via email.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import logging
import os
import urllib.parse

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


class IncidentData(BaseModel):
    """Single incident data for bulk share."""
    incident_name: str
    incident_type: Optional[str] = "event"
    significance: Optional[str] = "medium"
    description: Optional[str] = None
    entities: Optional[List[str]] = None
    strategic_relevance: Optional[str] = None
    plausibility: Optional[str] = None
    source_quality: Optional[str] = None


class ShareIncidentsRequest(BaseModel):
    """Request to share multiple incidents via email."""
    to_email: str
    topic: Optional[str] = None
    incidents: List[IncidentData]


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


class ShareEmergingTopicRequest(BaseModel):
    """Request to share an emerging topic via email."""
    to_email: str
    topic_id: Optional[int] = None
    topic_label: str
    topic_description: Optional[str] = None
    score: Optional[float] = None
    urgency: Optional[str] = None
    velocity: Optional[str] = None
    article_count: Optional[int] = None
    key_themes: Optional[List[str]] = None
    key_entities: Optional[List[str]] = None
    why_emerging: Optional[str] = None
    # Enhanced fields for full topic details
    key_takeaway: Optional[str] = None
    trend_score: Optional[dict] = None  # volume, velocity, diversity, novelty, composite
    actors: Optional[dict] = None  # companies, people, organizations
    events: Optional[dict] = None  # trigger_event, timeline, current_status
    implications: Optional[dict] = None  # industry_impact, regulatory, market
    organization_implications: Optional[dict] = None  # strategic_relevance, stakeholder_impact, risk_assessment, recommended_response
    articles: Optional[List[dict]] = None  # title, news_source, publication_date, uri


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


@router.post("/share/incidents", response_model=ShareResponse)
async def share_incidents(
    request: ShareIncidentsRequest,
    session=Depends(verify_session)
):
    """Share multiple incidents via email."""
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    if not request.incidents:
        raise HTTPException(status_code=400, detail="No incidents provided")

    count = len(request.incidents)
    topic_str = f" - {request.topic}" if request.topic else ""
    subject = f"[AuNoo AI] {count} Incident{'s' if count > 1 else ''}{topic_str}"

    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Incident Report</h1>',
        f'<p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0;">{count} incident{"s" if count > 1 else ""}{topic_str}</p>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
    ]

    for i, incident in enumerate(request.incidents, 1):
        # Significance badge color
        sig_color = {"high": "#dc3545", "medium": "#ffc107", "low": "#28a745"}.get(
            (incident.significance or "medium").lower(), "#6c757d"
        )
        sig_text_color = "#000" if (incident.significance or "").lower() == "medium" else "#fff"
        type_color = {"incident": "#dc3545", "event": "#0d6efd", "expertise": "#6f42c1", "trend": "#198754"}.get(
            (incident.incident_type or "event").lower(), "#6c757d"
        )

        html_parts.append(f'<div style="background: white; padding: 15px; border-radius: 4px; margin: {"0" if i == 1 else "12px"} 0 12px 0; border: 1px solid #e9ecef;">')
        html_parts.append(f'<h3 style="color: #333; margin: 0 0 8px 0; font-size: 16px;">{i}. {incident.incident_name}</h3>')

        # Badges
        html_parts.append('<div style="margin: 8px 0;">')
        if incident.incident_type:
            html_parts.append(f'<span style="background: {type_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin-right: 4px;">{incident.incident_type}</span>')
        if incident.significance:
            html_parts.append(f'<span style="background: {sig_color}; color: {sig_text_color}; padding: 3px 8px; border-radius: 4px; font-size: 11px; margin-right: 4px;">{incident.significance}</span>')
        if incident.plausibility:
            html_parts.append(f'<span style="background: #17a2b8; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px;">{incident.plausibility}</span>')
        html_parts.append('</div>')

        if incident.description:
            html_parts.append(f'<p style="margin: 10px 0 0 0; color: #555; font-size: 14px; line-height: 1.5;">{incident.description}</p>')

        if incident.strategic_relevance:
            html_parts.append(f'<p style="margin: 10px 0 0 0; color: #1976d2; font-size: 13px;"><strong>Strategic Relevance:</strong> {incident.strategic_relevance}</p>')

        if incident.entities:
            entities_html = " ".join([f'<span style="background: #e8eaf6; color: #3f51b5; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-right: 3px;">{e}</span>' for e in incident.entities[:5]])
            html_parts.append(f'<p style="margin: 10px 0 0 0;">{entities_html}</p>')

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
    text_parts = [f"Incident Report - {count} incident{'s' if count > 1 else ''}{topic_str}", ""]
    for i, incident in enumerate(request.incidents, 1):
        text_parts.append(f"{i}. {incident.incident_name}")
        text_parts.append(f"   Type: {incident.incident_type or 'N/A'} | Significance: {incident.significance or 'N/A'}")
        if incident.description:
            text_parts.append(f"   {incident.description[:200]}...")
        text_parts.append("")

    text_parts.extend(["---", "Shared from AuNoo AI"])
    body_text = "\n".join(text_parts)

    try:
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )

        if success:
            logger.info(f"{count} incidents shared via email to {request.to_email}")
            return ShareResponse(success=True, message=f"{count} incidents shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing incidents: {e}")
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


@router.post("/share/emerging-topic", response_model=ShareResponse)
async def share_emerging_topic(
    request: ShareEmergingTopicRequest,
    session=Depends(verify_session)
):
    """Share an emerging topic via email."""
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    # Build email content
    subject = f"[AuNoo AI] Emerging Topic: {request.topic_label}"

    # Build HTML email
    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 650px; margin: 0 auto;">',
        f'<div style="background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Emerging Topic</h1>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
        f'<h2 style="color: #333; margin-top: 0;">{request.topic_label}</h2>',
    ]

    # Badges
    badges_html = []
    if request.urgency:
        urgency_color = {"high": "#dc3545", "medium": "#ffc107", "low": "#28a745"}.get(request.urgency.lower(), "#6c757d")
        text_color = "#000" if request.urgency.lower() == "medium" else "#fff"
        badges_html.append(f'<span style="background: {urgency_color}; color: {text_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.urgency.capitalize()} Urgency</span>')
    if request.velocity:
        velocity_color = {"accelerating": "#28a745", "stable": "#6c757d", "decelerating": "#ffc107"}.get(request.velocity.lower(), "#6c757d")
        text_color = "#000" if request.velocity.lower() == "decelerating" else "#fff"
        badges_html.append(f'<span style="background: {velocity_color}; color: {text_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.velocity.capitalize()}</span>')
    if request.score is not None:
        badges_html.append(f'<span style="background: #17a2b8; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">Score: {round(request.score)}</span>')
    if request.article_count:
        badges_html.append(f'<span style="background: #6c757d; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{request.article_count} Signals</span>')

    if badges_html:
        html_parts.append(f'<p style="margin: 10px 0;">{"".join(badges_html)}</p>')

    if request.topic_description:
        html_parts.append(f'<div style="background: white; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #ec4899;">')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.topic_description}</p>')
        html_parts.append('</div>')

    # Key Takeaway
    if request.key_takeaway:
        html_parts.append(f'<div style="background: #f3e5f5; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #9c27b0;">')
        html_parts.append(f'<h4 style="color: #7b1fa2; margin: 0 0 8px 0;">Key Takeaway</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333;">{request.key_takeaway}</p>')
        html_parts.append('</div>')

    if request.why_emerging:
        html_parts.append(f'<div style="background: #fce4ec; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #e91e63;">')
        html_parts.append(f'<h4 style="color: #c2185b; margin: 0 0 8px 0;">Why This Is Emerging</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333;">{request.why_emerging}</p>')
        html_parts.append('</div>')

    # Trend Score breakdown
    if request.trend_score:
        ts = request.trend_score
        html_parts.append('<div style="background: white; padding: 15px; border-radius: 4px; margin: 15px 0; border: 1px solid #e9ecef;">')
        html_parts.append('<h4 style="color: #333; margin: 0 0 12px 0;">Trend Score Analysis</h4>')
        html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
        html_parts.append('<tr>')
        for label, value in [('Volume', ts.get('volume')), ('Velocity', ts.get('velocity')), ('Diversity', ts.get('diversity')), ('Novelty', ts.get('novelty')), ('Overall', ts.get('composite'))]:
            if value is not None:
                score_color = '#28a745' if value >= 70 else '#ffc107' if value >= 40 else '#6c757d'
                html_parts.append(f'<td style="text-align: center; padding: 8px;">')
                html_parts.append(f'<div style="font-size: 24px; font-weight: bold; color: {score_color};">{round(value)}</div>')
                html_parts.append(f'<div style="font-size: 11px; color: #666;">{label}</div>')
                html_parts.append('</td>')
        html_parts.append('</tr></table>')
        html_parts.append('</div>')

    # Actors section
    if request.actors:
        actors = request.actors
        has_actors = actors.get('companies') or actors.get('people') or actors.get('organizations')
        if has_actors:
            html_parts.append('<div style="margin: 15px 0;">')
            html_parts.append('<h4 style="color: #333; margin: 0 0 10px 0;">Key Actors</h4>')
            html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 6px;">')
            for company in (actors.get('companies') or [])[:5]:
                html_parts.append(f'<span style="background: #e3f2fd; color: #1565c0; padding: 4px 10px; border-radius: 4px; font-size: 12px;">🏢 {company}</span>')
            for person in (actors.get('people') or [])[:5]:
                html_parts.append(f'<span style="background: #e8f5e9; color: #2e7d32; padding: 4px 10px; border-radius: 4px; font-size: 12px;">👤 {person}</span>')
            for org in (actors.get('organizations') or [])[:5]:
                html_parts.append(f'<span style="background: #f3e5f5; color: #7b1fa2; padding: 4px 10px; border-radius: 4px; font-size: 12px;">🏛️ {org}</span>')
            html_parts.append('</div></div>')

    # Events section
    if request.events:
        events = request.events
        if events.get('trigger_event') or events.get('timeline'):
            html_parts.append('<div style="background: #e8f4f8; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #0288d1;">')
            html_parts.append('<h4 style="color: #01579b; margin: 0 0 10px 0;">Events & Timeline</h4>')
            if events.get('trigger_event'):
                html_parts.append(f'<p style="margin: 0 0 10px 0;"><strong>Trigger:</strong> {events["trigger_event"]}</p>')
            if events.get('timeline'):
                html_parts.append('<ul style="margin: 0; padding-left: 20px;">')
                for item in events['timeline'][:5]:
                    if isinstance(item, dict):
                        date = item.get('date', '')
                        event = item.get('event', '')
                        html_parts.append(f'<li style="margin: 4px 0; color: #333;">{date}: {event}</li>' if date else f'<li style="margin: 4px 0; color: #333;">{event}</li>')
                    else:
                        html_parts.append(f'<li style="margin: 4px 0; color: #333;">{item}</li>')
                html_parts.append('</ul>')
            html_parts.append('</div>')

    # Implications section
    if request.implications:
        impl = request.implications
        has_impl = impl.get('industry_impact') or impl.get('regulatory') or impl.get('market')
        if has_impl:
            html_parts.append('<div style="margin: 15px 0;">')
            html_parts.append('<h4 style="color: #333; margin: 0 0 10px 0;">Implications</h4>')
            html_parts.append('<table style="width: 100%; border-collapse: collapse;">')
            html_parts.append('<tr>')
            if impl.get('industry_impact'):
                html_parts.append(f'<td style="vertical-align: top; padding: 8px; background: #fff3e0; border-radius: 4px;">')
                html_parts.append(f'<div style="font-weight: bold; color: #e65100; margin-bottom: 4px;">Industry</div>')
                html_parts.append(f'<div style="font-size: 13px; color: #333;">{impl["industry_impact"]}</div>')
                html_parts.append('</td>')
            if impl.get('regulatory'):
                html_parts.append(f'<td style="vertical-align: top; padding: 8px; background: #fce4ec; border-radius: 4px;">')
                html_parts.append(f'<div style="font-weight: bold; color: #c2185b; margin-bottom: 4px;">Regulatory</div>')
                html_parts.append(f'<div style="font-size: 13px; color: #333;">{impl["regulatory"]}</div>')
                html_parts.append('</td>')
            if impl.get('market'):
                html_parts.append(f'<td style="vertical-align: top; padding: 8px; background: #e8f5e9; border-radius: 4px;">')
                html_parts.append(f'<div style="font-weight: bold; color: #2e7d32; margin-bottom: 4px;">Market</div>')
                html_parts.append(f'<div style="font-size: 13px; color: #333;">{impl["market"]}</div>')
                html_parts.append('</td>')
            html_parts.append('</tr></table>')
            html_parts.append('</div>')

    # Organization Implications section
    if request.organization_implications:
        org_impl = request.organization_implications
        has_org_impl = org_impl.get('strategic_relevance') or org_impl.get('stakeholder_impact') or org_impl.get('risk_assessment') or org_impl.get('recommended_response')
        if has_org_impl:
            html_parts.append('<div style="background: #e8eaf6; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #5c6bc0;">')
            html_parts.append('<h4 style="color: #3f51b5; margin: 0 0 12px 0;">Organization Impact</h4>')
            if org_impl.get('strategic_relevance'):
                html_parts.append(f'<div style="margin-bottom: 10px;"><strong style="color: #303f9f;">Strategic Relevance:</strong>')
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 13px;">{org_impl["strategic_relevance"]}</p></div>')
            if org_impl.get('stakeholder_impact'):
                html_parts.append(f'<div style="margin-bottom: 10px;"><strong style="color: #303f9f;">Stakeholder Impact:</strong>')
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 13px;">{org_impl["stakeholder_impact"]}</p></div>')
            if org_impl.get('risk_assessment'):
                html_parts.append(f'<div style="margin-bottom: 10px;"><strong style="color: #303f9f;">Risk Assessment:</strong>')
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 13px;">{org_impl["risk_assessment"]}</p></div>')
            if org_impl.get('recommended_response'):
                html_parts.append(f'<div style="margin-bottom: 0;"><strong style="color: #303f9f;">Recommended Response:</strong>')
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #333; font-size: 13px;">{org_impl["recommended_response"]}</p></div>')
            html_parts.append('</div>')

    if request.key_themes:
        html_parts.append(f'<p style="margin: 15px 0;"><strong>Key Themes:</strong></p>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 4px;">')
        for theme in request.key_themes[:10]:
            html_parts.append(f'<span style="background: #f3e5f5; color: #7b1fa2; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{theme}</span>')
        html_parts.append('</div>')

    if request.key_entities:
        html_parts.append(f'<p style="margin: 15px 0;"><strong>Key Entities:</strong></p>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 4px;">')
        for entity in request.key_entities[:10]:
            html_parts.append(f'<span style="background: #e8eaf6; color: #3f51b5; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{entity}</span>')
        html_parts.append('</div>')

    # Source Articles section
    if request.articles and len(request.articles) > 0:
        html_parts.append('<div style="margin: 20px 0;">')
        html_parts.append(f'<h4 style="color: #333; margin: 0 0 12px 0;">Source Articles ({len(request.articles)})</h4>')
        for i, article in enumerate(request.articles[:8], 1):
            title = article.get('title', 'Untitled')
            source = article.get('news_source', 'Unknown')
            date = article.get('publication_date', '')
            uri = article.get('uri', '')
            html_parts.append('<div style="background: white; padding: 10px; border-radius: 4px; margin: 8px 0; border: 1px solid #e9ecef;">')
            if uri:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. <a href="{uri}" style="color: #1976d2; text-decoration: none;">{title}</a></div>')
            else:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. {title}</div>')
            html_parts.append(f'<div style="font-size: 12px; color: #666;">{source}{" · " + date if date else ""}</div>')
            html_parts.append('</div>')
        html_parts.append('</div>')

    # Action buttons section
    html_parts.append('<div style="margin: 20px 0; padding: 15px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append('<div style="display: inline-block;">')
    # View in App button - links to Emerging Themes tab
    html_parts.append('<a href="https://bugfixing.aunoo.ai/explore?tab=emerging-topics" style="display: inline-block; background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">View Emerging Themes</a>')
    # Ask Auspex button
    auspex_query = urllib.parse.quote(f"Analyze this emerging theme in depth: {request.topic_label}")
    html_parts.append(f'<a href="https://bugfixing.aunoo.ai/explore?tab=auspex&query={auspex_query}" style="display: inline-block; background: #1976d2; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">Ask Auspex</a>')
    html_parts.append('</div>')
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
    text_parts = [f"Emerging Topic: {request.topic_label}", ""]
    text_parts.append(f"Score: {round(request.score) if request.score else 'N/A'} | Urgency: {request.urgency or 'N/A'} | {request.velocity or 'N/A'} | {request.article_count or 0} Signals")
    text_parts.append("")
    if request.topic_description:
        text_parts.append(request.topic_description)
        text_parts.append("")
    if request.key_takeaway:
        text_parts.append(f"Key Takeaway: {request.key_takeaway}")
        text_parts.append("")
    if request.why_emerging:
        text_parts.append(f"Why Emerging: {request.why_emerging}")
        text_parts.append("")
    if request.trend_score:
        ts = request.trend_score
        text_parts.append("Trend Score:")
        text_parts.append(f"  Volume: {round(ts.get('volume', 0))} | Velocity: {round(ts.get('velocity', 0))} | Diversity: {round(ts.get('diversity', 0))} | Novelty: {round(ts.get('novelty', 0))} | Overall: {round(ts.get('composite', 0))}")
        text_parts.append("")
    if request.actors:
        actors = request.actors
        if actors.get('companies'):
            text_parts.append(f"Companies: {', '.join(actors['companies'][:5])}")
        if actors.get('people'):
            text_parts.append(f"People: {', '.join(actors['people'][:5])}")
        if actors.get('organizations'):
            text_parts.append(f"Organizations: {', '.join(actors['organizations'][:5])}")
        text_parts.append("")
    if request.events and request.events.get('trigger_event'):
        text_parts.append(f"Trigger Event: {request.events['trigger_event']}")
        text_parts.append("")
    if request.implications:
        if request.implications.get('industry_impact'):
            text_parts.append(f"Industry Impact: {request.implications['industry_impact']}")
        if request.implications.get('regulatory'):
            text_parts.append(f"Regulatory: {request.implications['regulatory']}")
        if request.implications.get('market'):
            text_parts.append(f"Market: {request.implications['market']}")
        text_parts.append("")
    if request.key_themes:
        text_parts.append(f"Key Themes: {', '.join(request.key_themes[:10])}")
        text_parts.append("")
    if request.key_entities:
        text_parts.append(f"Key Entities: {', '.join(request.key_entities[:10])}")
        text_parts.append("")
    if request.articles:
        text_parts.append(f"Source Articles ({len(request.articles)}):")
        for i, art in enumerate(request.articles[:8], 1):
            text_parts.append(f"  {i}. {art.get('title', 'Untitled')} - {art.get('news_source', 'Unknown')}")
        text_parts.append("")
    text_parts.append("---")
    text_parts.append("Continue exploring in AuNoo AI:")
    text_parts.append("  View Emerging Themes: https://bugfixing.aunoo.ai/explore?tab=emerging-topics")
    text_parts.append(f"  Ask Auspex: https://bugfixing.aunoo.ai/explore?tab=auspex&query={auspex_query}")
    text_parts.append("")
    text_parts.append("Shared from AuNoo AI")
    body_text = "\n".join(text_parts)

    try:
        success = email_service.send_email(
            to_addresses=[request.to_email],
            subject=subject,
            body_html=body_html,
            body_text=body_text
        )

        if success:
            return ShareResponse(success=True, message="Emerging topic shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing emerging topic: {e}")
        raise HTTPException(status_code=500, detail=str(e))
