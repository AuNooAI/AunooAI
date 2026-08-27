"""
Email sharing routes for sending content via email.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Union
import re


def get_base_url(http_request: Request) -> str:
    """Extract base URL from the request (e.g., https://wileytest.aunoo.ai)."""
    return str(http_request.url).replace(str(http_request.url.path), "").rstrip("/")
import logging
import os
import urllib.parse

from app.security.session import verify_session_api
from app.services.email_service import get_email_service, markdown_to_html

logger = logging.getLogger(__name__)

# Color constants for email templates
COLORS = {
    'primary': '#ec4899',
    'primary_dark': '#be185d',
    'secondary': '#8b5cf6',
    'text': '#333',
    'text_muted': '#666',
    'text_light': '#888',
    'background': '#f8f9fa',
    'border': '#e9ecef',
    'success': '#28a745',
    'warning': '#ffc107',
    'danger': '#dc3545',
    'info': '#17a2b8',
}


def build_email_header(title: str, gradient_start: str = None, gradient_end: str = None) -> list[str]:
    """Build a gradient header for email templates."""
    start = gradient_start or COLORS['primary']
    end = gradient_end or COLORS['secondary']
    return [
        '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background-color: {start}; padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">{title}</h1>',
        '</div>',
        f'<div style="background: {COLORS["background"]}; padding: 20px; border: 1px solid {COLORS["border"]}; border-top: none;">',
    ]


def build_email_footer() -> list[str]:
    """Build the standard email footer."""
    return [
        '</div>',
        f'<div style="background: #f1f3f4; padding: 15px; text-align: center; border-radius: 0 0 8px 8px; border: 1px solid {COLORS["border"]}; border-top: none;">',
        f'<p style="color: {COLORS["text_muted"]}; font-size: 12px; margin: 0;">Shared from <strong>AuNoo AI</strong></p>',
        '</div>',
        '</div>'
    ]


def build_clickable_title(title: str, url: str = None, level: int = 2) -> str:
    """Build a title that links to URL if available."""
    tag = f'h{level}'
    if url:
        return f'<{tag} style="margin-top: 0; line-height: 1.4;"><a href="{url}" style="color: {COLORS["text"]}; text-decoration: none;">{title}</a></{tag}>'
    return f'<{tag} style="color: {COLORS["text"]}; margin-top: 0; line-height: 1.4;">{title}</{tag}>'


def build_url_section(url: str) -> list[str]:
    """Build a prominent URL section with link text and button."""
    if not url:
        return []
    return [
        f'<p style="margin: 15px 0 8px 0;"><a href="{url}" style="color: {COLORS["primary"]}; font-size: 13px; text-decoration: underline;">🔗 Read full article →</a></p>',
        f'<p style="margin: 0 0 15px 0; font-size: 11px; color: {COLORS["text_light"]}; word-break: break-all;">{url}</p>',
        '<div style="margin: 10px 0; text-align: center;">',
        f'<a href="{url}" style="display: inline-block; background-color: {COLORS["primary"]}; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Read Full Article</a>',
        '</div>'
    ]


def build_info_box(title: str, content: str, bg_color: str, border_color: str, title_color: str) -> list[str]:
    """Build a styled info box with title and content."""
    return [
        f'<div style="background: {bg_color}; padding: 10px; border-radius: 4px; margin: 10px 0; border-left: 3px solid {border_color};">',
        f'<p style="color: {title_color}; margin: 0 0 4px 0; font-size: 11px; text-transform: uppercase; font-weight: 600;">{title}</p>',
        f'<p style="margin: 0; color: {COLORS["text"]}; font-size: 13px; line-height: 1.5;">{content}</p>',
        '</div>'
    ]


def log_share_request(request_type: str, fields: dict) -> None:
    """Log share request details for debugging."""
    logger.info(f"{request_type} share request received:")
    for key, value in fields.items():
        if isinstance(value, str) and len(value) > 50:
            value = f"{value[:50]}..."
        logger.info(f"  - {key}: '{value}'")


router = APIRouter()


class EmailStatusResponse(BaseModel):
    """Response for email status check."""
    configured: bool
    provider: Optional[str] = None


def _backfill_missing_sources(articles: Optional[List["ArticleRef"]]) -> None:
    """Fill in a missing outlet name from the articles table, by URL.

    The frontend already falls back across the two metadata key spellings
    an incident's outlet can be stored under (see HighlightsSection.tsx /
    SavedIncidentsSection.tsx, 2026-08-11 / 2026-08-24) — but that only
    helps when SOME key was written. An incident promoted from an article
    whose in-memory object had no source populated at all (observed on a
    manually-submitted article, 2026-08-24) has no key to fall back to;
    the URL is enough to look the real outlet up directly. Best-effort:
    logs and leaves ``source`` unset on any failure or missing row.
    """
    missing = [a for a in (articles or []) if not a.source and a.url]
    if not missing:
        return
    try:
        from app.database import get_database_instance
        from sqlalchemy import text
        conn = get_database_instance()._temp_get_connection()
        for a in missing:
            row = conn.execute(
                text("SELECT news_source FROM articles WHERE uri = :u"),
                {"u": a.url}).mappings().first()
            if row and row.get("news_source"):
                a.source = row["news_source"]
    except Exception as e:
        logger.warning(f"share: source backfill failed: {e}")


def _flatten_to_text(v, sep="; "):
    """Flatten an object, list, or scalar into one string."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, dict):
        return sep.join(f"{k}: {val}" for k, val in v.items())
    if isinstance(v, (list, tuple)):
        return sep.join(_flatten_to_text(item, ", ") for item in v)
    return str(v)


def _coerce_to_text(v):
    """Coerce a field the email renders as text.

    Incidents are written by an LLM, so a field documented as a string
    sometimes arrives as an object (timeline = {"announced": "2026-06-17"})
    or a number. Flatten it rather than reject the whole share with a 422.
    """
    return _flatten_to_text(v)


def _coerce_to_str_list(v):
    """Coerce a field the email renders as bullets into a list of strings."""
    if v is None or (isinstance(v, list) and all(isinstance(i, str) for i in v)):
        return v
    if isinstance(v, str):
        parts = [p.strip() for p in re.split(r"[;\n]", v) if p.strip()]
        return parts or None
    if isinstance(v, dict):
        return [f"{k}: {val}" for k, val in v.items()] or None
    if isinstance(v, (list, tuple)):
        return [_flatten_to_text(item, ", ") for item in v] or None
    return [str(v)]


def _coerce_text_or_list(v):
    """Coerce a field the email renders as bullets when it is a list.

    Keeps a list of strings as a list so the bullets survive; anything else
    becomes a single string.
    """
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return [_flatten_to_text(item, ", ") for item in v] or None
    return _flatten_to_text(v)


class ArticleRef(BaseModel):
    """Article reference for incident sharing."""
    title: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None


class AnalystNoteRef(BaseModel):
    """Analyst note reference for incident sharing."""
    id: str
    timestamp: str
    analyst: str
    comment: str


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
    credibility_summary: Optional[str] = None
    timeline: Optional[Union[str, List[str]]] = None  # Can be string or array
    investigation_leads: Optional[Union[str, List[str]]] = None  # Can be string or array
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    articles: Optional[List[ArticleRef]] = None
    analyst_notes: Optional[List[AnalystNoteRef]] = None

    _coerce_text = field_validator(
        'incident_name', 'incident_type', 'significance', 'description', 'topic',
        'strategic_relevance', 'plausibility', 'source_quality',
        'credibility_summary', 'first_seen', 'last_seen',
        mode='before')(_coerce_to_text)
    _coerce_entities = field_validator(
        'entities', mode='before')(_coerce_to_str_list)
    _coerce_bulleted = field_validator(
        'timeline', 'investigation_leads', mode='before')(_coerce_text_or_list)


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
    articles: Optional[List[ArticleRef]] = None
    analyst_notes: Optional[List[AnalystNoteRef]] = None

    _coerce_text = field_validator(
        'incident_name', 'incident_type', 'significance', 'description',
        'strategic_relevance', 'plausibility', 'source_quality',
        mode='before')(_coerce_to_text)
    _coerce_lists = field_validator('entities', mode='before')(_coerce_to_str_list)


class ShareIncidentsRequest(BaseModel):
    """Request to share multiple incidents via email."""
    to_email: str
    topic: Optional[str] = None
    incidents: List[IncidentData]


class NarrativeArticleRef(BaseModel):
    """Article reference for narrative sharing."""
    title: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    date: Optional[str] = None


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
    articles: Optional[List[NarrativeArticleRef]] = None


class ShareBriefingRequest(BaseModel):
    """Request to share a briefing via email."""
    to_email: str
    persona: str
    executive_summary: Optional[str] = None
    articles: Optional[List[dict]] = None  # title, headline, executive_takeaway, category, source, date
    key_themes: Optional[List[str]] = None


class ShareBriefingCardRequest(BaseModel):
    """Request to share a single briefing card via email."""
    to_email: str
    title: str
    headline: Optional[str] = None
    executive_takeaway: Optional[str] = None
    strategic_relevance: Optional[str] = None
    category: Optional[str] = None
    signal_strength: Optional[str] = None
    risk_opportunity: Optional[str] = None
    time_horizon: Optional[str] = None
    source: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    summary: Optional[str] = None
    executive_actions: Optional[List[str]] = None
    scores: Optional[dict] = None  # relevance, impact, actionability, timeliness, credibility, overall


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


class ShareArticleRequest(BaseModel):
    """Request to share an article via email."""
    to_email: str
    title: str
    url: Optional[str] = None
    source: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[str] = None
    topic: Optional[str] = None
    sentiment: Optional[str] = None
    publication_date: Optional[str] = None


class ShareExecutiveSummaryRequest(BaseModel):
    """Request to share an executive summary via email."""
    to_email: str
    topic_title: str
    research_topic: Optional[str] = None
    primary_horizon: Optional[str] = None
    horizon_label: Optional[str] = None
    opening_statement: Optional[str] = None
    consensus_percentage: Optional[int] = None
    minority_view: Optional[dict] = None  # percentage_range, statement
    primary_signal: Optional[str] = None
    decision_fork: Optional[dict] = None  # condition_a, condition_b
    action_window: Optional[dict] = None  # assessment, positioning
    source_scenarios: Optional[List[str]] = None


class ShareResponse(BaseModel):
    """Response for share requests."""
    success: bool
    message: str


@router.get("/email/status", response_model=EmailStatusResponse)
async def get_email_status(session=Depends(verify_session_api)):
    """Check if email service is configured and available."""
    email_service = get_email_service()
    provider = os.getenv("EMAIL_PROVIDER", "resend")

    return EmailStatusResponse(
        configured=email_service.is_available(),
        provider=provider if email_service.is_available() else None
    )


@router.post("/share/incident", response_model=ShareResponse)
async def share_incident(
    http_request: Request,
    request: ShareIncidentRequest,
    session=Depends(verify_session_api)
):
    """Share an incident via email."""
    base_url = get_base_url(http_request)
    logger.info(f"share_incident called with incident_name={request.incident_name}, to_email={request.to_email}")
    logger.info(f"share_incident analyst_notes received: {request.analyst_notes}")
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    _backfill_missing_sources(request.articles)

    # Build email content
    subject = f"[AuNoo AI] Incident: {request.incident_name}"

    # Build HTML email
    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background-color: #667eea; padding: 20px; border-radius: 8px 8px 0 0;">',
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

    if request.credibility_summary:
        html_parts.append(f'<div style="background: #fff3e0; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #ff9800;">')
        html_parts.append(f'<h4 style="color: #e65100; margin: 0 0 8px 0;">Credibility Assessment</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333;">{request.credibility_summary}</p>')
        html_parts.append('</div>')

    # Timeline
    if request.first_seen or request.last_seen or request.timeline:
        html_parts.append(f'<div style="background: #fce4ec; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #e91e63;">')
        html_parts.append(f'<h4 style="color: #c2185b; margin: 0 0 8px 0;">Timeline</h4>')
        if request.first_seen or request.last_seen:
            timeline_text = []
            if request.first_seen:
                timeline_text.append(f'First seen: {request.first_seen}')
            if request.last_seen:
                timeline_text.append(f'Last seen: {request.last_seen}')
            html_parts.append(f'<p style="margin: 0 0 8px 0; color: #333; font-size: 13px;">{" | ".join(timeline_text)}</p>')
        if request.timeline:
            # Handle both string and list formats
            if isinstance(request.timeline, list):
                html_parts.append('<ul style="margin: 0; padding-left: 20px;">')
                for item in request.timeline:
                    html_parts.append(f'<li style="margin: 4px 0; color: #333;">{item}</li>')
                html_parts.append('</ul>')
            else:
                html_parts.append(f'<p style="margin: 0; color: #333;">{request.timeline}</p>')
        html_parts.append('</div>')

    if request.investigation_leads:
        html_parts.append(f'<div style="background: #f3e5f5; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #9c27b0;">')
        html_parts.append(f'<h4 style="color: #7b1fa2; margin: 0 0 8px 0;">Investigation Leads</h4>')
        # Handle both string and list formats
        if isinstance(request.investigation_leads, list):
            html_parts.append('<ul style="margin: 0; padding-left: 20px;">')
            for lead in request.investigation_leads[:5]:
                html_parts.append(f'<li style="margin: 4px 0; color: #333;">{lead}</li>')
            html_parts.append('</ul>')
        else:
            html_parts.append(f'<p style="margin: 0; color: #333;">{request.investigation_leads}</p>')
        html_parts.append('</div>')

    if request.entities:
        html_parts.append(f'<p style="margin: 15px 0;"><strong>Key Entities:</strong></p>')
        html_parts.append('<div style="display: flex; flex-wrap: wrap; gap: 4px;">')
        for entity in request.entities[:10]:
            html_parts.append(f'<span style="background: #e8eaf6; color: #3f51b5; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{entity}</span>')
        html_parts.append('</div>')

    # Source articles
    if request.articles and len(request.articles) > 0:
        html_parts.append('<div style="margin: 20px 0; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        html_parts.append(f'<h4 style="color: #333; margin: 0 0 12px 0;">Source Articles ({len(request.articles)})</h4>')
        for i, article in enumerate(request.articles[:5], 1):
            title = article.title or 'Untitled'
            source = article.source or 'Unknown'
            url = article.url or ''
            html_parts.append('<div style="background: white; padding: 10px; border-radius: 4px; margin: 8px 0; border: 1px solid #e9ecef;">')
            if url:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. <a href="{url}" style="color: #1976d2; text-decoration: none;">{title}</a></div>')
            else:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. {title}</div>')
            html_parts.append(f'<div style="font-size: 12px; color: #666;">{source}</div>')
            if article.summary:
                html_parts.append(f'<div style="font-size: 13px; color: #555; margin-top: 6px; line-height: 1.4;">{article.summary[:200]}{"..." if len(article.summary) > 200 else ""}</div>')
            html_parts.append('</div>')
        html_parts.append('</div>')

    # Analyst notes section
    if request.analyst_notes and len(request.analyst_notes) > 0:
        html_parts.append('<div style="margin: 20px 0; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        html_parts.append(f'<h4 style="color: #d97706; margin: 0 0 12px 0;">📝 Analyst Notes ({len(request.analyst_notes)})</h4>')
        for note in request.analyst_notes:
            # Format timestamp
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(note.timestamp.replace('Z', '+00:00'))
                formatted_date = ts.strftime('%d %b %Y %H:%M')
            except:
                formatted_date = note.timestamp
            html_parts.append('<div style="background: #fffbeb; padding: 12px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #f59e0b;">')
            html_parts.append(f'<div style="font-size: 12px; color: #92400e; margin-bottom: 6px;"><strong>{note.analyst}</strong> · {formatted_date}</div>')
            html_parts.append(f'<div style="font-size: 13px; color: #333; line-height: 1.5; white-space: pre-wrap;">{note.comment}</div>')
            html_parts.append('</div>')
        html_parts.append('</div>')

    # Action buttons section - build rich Auspex query with context
    auspex_context_parts = [f"Analyze this incident: {request.incident_name}"]
    if request.description:
        auspex_context_parts.append(f"\nDescription: {request.description[:300]}")
    if request.entities:
        auspex_context_parts.append(f"\nKey entities: {', '.join(request.entities[:5])}")
    if request.articles:
        article_titles = [a.title for a in request.articles[:3] if a.title]
        if article_titles:
            auspex_context_parts.append(f"\nSource articles: {'; '.join(article_titles)}")
    auspex_context_parts.append("\n\nProvide strategic analysis and implications.")
    auspex_query = urllib.parse.quote(''.join(auspex_context_parts))
    html_parts.append('<div style="margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append('<div style="display: inline-block;">')
    # View Highlights button
    html_parts.append(f'<a href="{base_url}/explore?tab=highlights" style="display: inline-block; background-color: #667eea; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">View Highlights</a>')
    # Ask Auspex button
    html_parts.append(f'<a href="{base_url}/explore?auspex_query={auspex_query}" style="display: inline-block; background: #1976d2; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">Ask Auspex</a>')
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

    # Plain text version - build article list
    articles_text = ""
    if request.articles:
        articles_text = "\n\nSource Articles:\n" + "\n".join([
            f"  {i+1}. {a.title or 'Untitled'} - {a.source or 'Unknown'}" + (f"\n      {a.url}" if a.url else "")
            for i, a in enumerate(request.articles[:5])
        ])

    # Build timeline text
    timeline_text = ""
    if request.first_seen or request.last_seen or request.timeline:
        timeline_parts = []
        if request.first_seen:
            timeline_parts.append(f"First seen: {request.first_seen}")
        if request.last_seen:
            timeline_parts.append(f"Last seen: {request.last_seen}")
        if request.timeline:
            # Handle both string and list formats
            if isinstance(request.timeline, list):
                timeline_parts.append("Timeline:\n" + "\n".join(f"  - {item}" for item in request.timeline))
            else:
                timeline_parts.append(f"Timeline: {request.timeline}")
        timeline_text = "\n" + "\n".join(timeline_parts)

    # Build investigation leads text
    leads_text = ""
    if request.investigation_leads:
        # Handle both string and list formats
        if isinstance(request.investigation_leads, list):
            leads_text = "\n\nInvestigation Leads:\n" + "\n".join([f"  - {lead}" for lead in request.investigation_leads[:5]])
        else:
            leads_text = f"\n\nInvestigation Leads:\n  {request.investigation_leads}"

    body_text = f"""Incident: {request.incident_name}

Type: {request.incident_type or 'N/A'}
Significance: {request.significance or 'N/A'}
{f'Topic: {request.topic}' if request.topic else ''}
{f'Plausibility: {request.plausibility}' if request.plausibility else ''}
{f'Source Quality: {request.source_quality}' if request.source_quality else ''}{timeline_text}

{request.description or ''}

{f'Strategic Relevance: {request.strategic_relevance}' if request.strategic_relevance else ''}

{f'Credibility Assessment: {request.credibility_summary}' if request.credibility_summary else ''}{leads_text}

{f'Key Entities: {", ".join(request.entities[:10])}' if request.entities else ''}{articles_text}

---
Continue exploring in AuNoo AI:
  View Highlights: {base_url}/explore?tab=highlights
  Ask Auspex: {base_url}/explore?auspex_query={auspex_query}

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


@router.post("/share/article", response_model=ShareResponse)
async def share_article(
    request: ShareArticleRequest,
    session=Depends(verify_session_api)
):
    """Share an article via email."""
    log_share_request("Article", {
        "to_email": request.to_email,
        "title": request.title,
        "url": request.url,
        "source": request.source,
        "category": request.category,
    })

    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Article: {request.title[:60]}{'...' if len(request.title) > 60 else ''}"

    # Build HTML email using helpers
    html_parts = build_email_header("Shared Article")
    html_parts.append(build_clickable_title(request.title, request.url))

    # Source and date
    source_info = []
    if request.source:
        source_info.append(request.source)
    if request.publication_date:
        try:
            from datetime import datetime
            date_obj = datetime.fromisoformat(request.publication_date.replace('Z', '+00:00'))
            source_info.append(date_obj.strftime('%B %d, %Y'))
        except:
            source_info.append(request.publication_date)
    if source_info:
        html_parts.append(f'<p style="color: {COLORS["text_muted"]}; margin: 5px 0; font-size: 14px;">{" · ".join(source_info)}</p>')

    # Badges
    badges_html = []
    if request.category:
        badges_html.append(f'<span style="background: {COLORS["primary"]}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.category}</span>')
    if request.topic:
        badges_html.append(f'<span style="background: {COLORS["secondary"]}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.topic}</span>')
    if request.sentiment:
        sentiment_color = {"positive": COLORS["success"], "negative": COLORS["danger"], "neutral": "#6c757d", "mixed": COLORS["warning"]}.get(request.sentiment.lower(), "#6c757d")
        text_color = "#000" if request.sentiment.lower() in ["mixed", "neutral"] else "#fff"
        badges_html.append(f'<span style="background: {sentiment_color}; color: {text_color}; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{request.sentiment}</span>')

    if badges_html:
        html_parts.append(f'<p style="margin: 15px 0;">{"".join(badges_html)}</p>')

    if request.summary:
        html_parts.extend(build_info_box("Summary", request.summary, "white", COLORS["primary"], COLORS["primary_dark"]))

    html_parts.extend(build_url_section(request.url))
    html_parts.extend(build_email_footer())

    body_html = '\n'.join(html_parts)

    # Plain text version
    body_text = f"""Article: {request.title}

{f'Source: {request.source}' if request.source else ''}
{f'Date: {request.publication_date}' if request.publication_date else ''}
{f'Category: {request.category}' if request.category else ''}
{f'Topic: {request.topic}' if request.topic else ''}

{request.summary or ''}

{f'Read full article: {request.url}' if request.url else ''}

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
            logger.info(f"Article shared via email to {request.to_email}")
            return ShareResponse(success=True, message="Article shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing article: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/share/incidents", response_model=ShareResponse)
async def share_incidents(
    request: ShareIncidentsRequest,
    session=Depends(verify_session_api)
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

    for incident in request.incidents:
        _backfill_missing_sources(incident.articles)

    count = len(request.incidents)
    topic_str = f" - {request.topic}" if request.topic else ""
    subject = f"[AuNoo AI] {count} Incident{'s' if count > 1 else ''}{topic_str}"

    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background-color: #667eea; padding: 20px; border-radius: 8px 8px 0 0;">',
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

        # Source articles for this incident
        if incident.articles and len(incident.articles) > 0:
            html_parts.append('<div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #eee;">')
            html_parts.append(f'<p style="margin: 0 0 6px 0; font-size: 11px; color: #666; font-weight: 600;">Source Articles:</p>')
            for j, article in enumerate(incident.articles[:3], 1):
                title = article.title or 'Untitled'
                source = article.source or ''
                url = article.url or ''
                if url:
                    html_parts.append(f'<p style="margin: 2px 0; font-size: 12px; color: #555;">• <a href="{url}" style="color: #1976d2; text-decoration: none;">{title}</a>{" - " + source if source else ""}</p>')
                else:
                    html_parts.append(f'<p style="margin: 2px 0; font-size: 12px; color: #555;">• {title}{" - " + source if source else ""}</p>')
            html_parts.append('</div>')

        # Analyst notes for this incident
        if incident.analyst_notes and len(incident.analyst_notes) > 0:
            html_parts.append('<div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #fef3c7;">')
            html_parts.append(f'<p style="margin: 0 0 6px 0; font-size: 11px; color: #d97706; font-weight: 600;">📝 Analyst Notes ({len(incident.analyst_notes)}):</p>')
            for note in incident.analyst_notes[:3]:
                # Format timestamp
                try:
                    from datetime import datetime
                    ts = datetime.fromisoformat(note.timestamp.replace('Z', '+00:00'))
                    formatted_date = ts.strftime('%d %b %H:%M')
                except:
                    formatted_date = note.timestamp[:10] if len(note.timestamp) > 10 else note.timestamp
                html_parts.append(f'<div style="background: #fffbeb; padding: 8px; border-radius: 4px; margin: 4px 0; border-left: 2px solid #f59e0b;">')
                html_parts.append(f'<p style="margin: 0; font-size: 11px; color: #92400e;"><strong>{note.analyst}</strong> · {formatted_date}</p>')
                html_parts.append(f'<p style="margin: 4px 0 0 0; font-size: 12px; color: #333;">{note.comment[:150]}{"..." if len(note.comment) > 150 else ""}</p>')
                html_parts.append('</div>')
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
    http_request: Request,
    request: ShareNarrativeRequest,
    session=Depends(verify_session_api)
):
    """Share a narrative via email."""
    base_url = get_base_url(http_request)
    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Narrative: {request.narrative_name}"

    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background-color: #11998e; padding: 20px; border-radius: 8px 8px 0 0;">',
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

    # Source articles
    if request.articles and len(request.articles) > 0:
        html_parts.append('<div style="margin: 20px 0; padding-top: 15px; border-top: 1px solid #e9ecef;">')
        html_parts.append(f'<h4 style="color: #333; margin: 0 0 12px 0;">Source Articles ({len(request.articles)})</h4>')
        for i, article in enumerate(request.articles[:8], 1):
            title = article.title or 'Untitled'
            source = article.source or 'Unknown'
            url = article.url or ''
            date = article.date or ''
            html_parts.append('<div style="background: white; padding: 10px; border-radius: 4px; margin: 8px 0; border: 1px solid #e9ecef;">')
            if url:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. <a href="{url}" style="color: #2e7d32; text-decoration: none;">{title}</a></div>')
            else:
                html_parts.append(f'<div style="font-weight: 500; color: #333; margin-bottom: 4px;">{i}. {title}</div>')
            source_line = source + (f" · {date}" if date else "")
            html_parts.append(f'<div style="font-size: 12px; color: #666;">{source_line}</div>')
            if article.summary:
                html_parts.append(f'<div style="font-size: 13px; color: #555; margin-top: 6px; line-height: 1.4;">{article.summary[:200]}{"..." if len(article.summary) > 200 else ""}</div>')
            html_parts.append('</div>')
        html_parts.append('</div>')

    # Action buttons section - build rich Auspex query with context
    auspex_context_parts = [f"Analyze this narrative: {request.narrative_name}"]
    if request.description:
        auspex_context_parts.append(f"\nDescription: {request.description[:300]}")
    if request.key_entities:
        auspex_context_parts.append(f"\nKey entities: {', '.join(request.key_entities[:5])}")
    if request.articles:
        article_titles = [a.title for a in request.articles[:3] if a.title]
        if article_titles:
            auspex_context_parts.append(f"\nSource articles: {'; '.join(article_titles)}")
    auspex_context_parts.append("\n\nProvide strategic analysis, key implications, and recommended actions.")
    auspex_query = urllib.parse.quote(''.join(auspex_context_parts))
    html_parts.append('<div style="margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append('<div style="display: inline-block;">')
    # View Narratives button
    html_parts.append(f'<a href="{base_url}/explore?tab=narratives" style="display: inline-block; background-color: #11998e; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">View Narratives</a>')
    # Ask Auspex button
    html_parts.append(f'<a href="{base_url}/explore?auspex_query={auspex_query}" style="display: inline-block; background: #1976d2; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">Ask Auspex</a>')
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

    # Plain text version - build article list
    articles_text = ""
    if request.articles:
        articles_text = "\n\nSource Articles:\n" + "\n".join([
            f"  {i+1}. {a.title or 'Untitled'} - {a.source or 'Unknown'}" + (f"\n      {a.url}" if a.url else "")
            for i, a in enumerate(request.articles[:8])
        ])

    body_text = f"""Narrative: {request.narrative_name}

{f'Topic: {request.topic}' if request.topic else ''}

{request.description or ''}

{f'Key Points:' if request.key_points else ''}
{chr(10).join(f'- {p}' for p in (request.key_points or []))}{articles_text}

---
Continue exploring in AuNoo AI:
  View Narratives: {base_url}/explore?tab=narratives
  Ask Auspex: {base_url}/explore?auspex_query={auspex_query}

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
    session=Depends(verify_session_api)
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
        f'<div style="background-color: #8b5cf6; padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Executive Briefing</h1>',
        f'<p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0;">{request.persona} Perspective</p>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
    ]

    if request.executive_summary:
        html_parts.append(f'<div style="background-color: #fdf2f8; padding: 15px; border-radius: 4px; margin-bottom: 15px; border-left: 4px solid #ec4899;">')
        html_parts.append(f'<h4 style="color: #be185d; margin: 0 0 8px 0;">Executive Summary</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.executive_summary}</p>')
        html_parts.append('</div>')

    if request.articles:
        html_parts.append('<h4 style="color: #333;">Top Stories:</h4>')
        # Debug: log article data to see what's being received
        logger.info(f"Briefing share - received {len(request.articles)} articles")
        for idx, art in enumerate(request.articles[:3]):
            logger.info(f"Article {idx}: url={art.get('url')}, uri={art.get('uri')}, title={art.get('title', '')[:50]}")
        for i, article in enumerate(request.articles[:6], 1):
            title = article.get('title') or article.get('headline', 'Untitled')
            takeaway = article.get('executive_takeaway', '')
            strategic_relevance = article.get('strategic_relevance', '')
            summary = article.get('summary', '')
            category = article.get('category', '')
            source = article.get('source', '')
            date = article.get('date', '')
            url = article.get('url', '') or article.get('uri', '')
            time_horizon = article.get('time_horizon', '')
            signal_strength = article.get('signal_strength', '')
            risk_opportunity = article.get('risk_opportunity', '')

            # Build source/date line
            source_info = []
            if source:
                source_info.append(source)
            if date:
                source_info.append(date)
            source_line = ', '.join(source_info)

            html_parts.append(f'<div style="background: white; padding: 12px; border-radius: 4px; margin: 8px 0; border: 1px solid #e9ecef;">')
            # Title with optional link
            logger.info(f"Article {i} in HTML: url='{url}', truthy={bool(url)}")
            if url:
                html_parts.append(f'<p style="margin: 0; font-weight: 600; color: #333;">{i}. <a href="{url}" style="color: #ec4899; text-decoration: none;">{title}</a></p>')
            else:
                html_parts.append(f'<p style="margin: 0; font-weight: 600; color: #333;">{i}. {title}</p>')
            # Source and date
            if source_line:
                html_parts.append(f'<p style="margin: 4px 0 0 0; color: #888; font-size: 12px;">{source_line}</p>')
            # Badges row
            badges = []
            if category:
                badges.append(f'<span style="background: #e2e8f0; color: #475569; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{category}</span>')
            if time_horizon:
                badges.append(f'<span style="background: #dbeafe; color: #1e40af; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{time_horizon}</span>')
            if signal_strength:
                badges.append(f'<span style="background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{signal_strength}</span>')
            if risk_opportunity:
                color = '#dcfce7' if 'opportunity' in risk_opportunity.lower() else '#fee2e2'
                text_color = '#166534' if 'opportunity' in risk_opportunity.lower() else '#991b1b'
                badges.append(f'<span style="background: {color}; color: {text_color}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{risk_opportunity}</span>')
            if badges:
                html_parts.append(f'<p style="margin: 6px 0; display: flex; flex-wrap: wrap; gap: 4px;">{" ".join(badges)}</p>')
            # Why This Matters (Executive Takeaway)
            if takeaway:
                html_parts.append(f'<div style="background-color: #fdf2f8; padding: 10px; border-radius: 4px; margin: 10px 0; border-left: 3px solid #ec4899;">')
                html_parts.append(f'<p style="color: #be185d; margin: 0 0 4px 0; font-size: 11px; text-transform: uppercase; font-weight: 600;">Why This Matters</p>')
                html_parts.append(f'<p style="margin: 0; color: #333; font-size: 13px; line-height: 1.5;">{takeaway}</p>')
                html_parts.append('</div>')

            # Strategic Relevance
            if strategic_relevance:
                html_parts.append(f'<div style="background: #e3f2fd; padding: 10px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #2196f3;">')
                html_parts.append(f'<p style="color: #1565c0; margin: 0 0 4px 0; font-size: 11px; text-transform: uppercase; font-weight: 600;">Strategic Relevance</p>')
                html_parts.append(f'<p style="margin: 0; color: #333; font-size: 13px; line-height: 1.5;">{strategic_relevance}</p>')
                html_parts.append('</div>')

            # Summary (if no takeaway)
            if summary and not takeaway:
                html_parts.append(f'<p style="margin: 8px 0; color: #666; font-size: 13px; line-height: 1.5;">{summary[:300]}{"..." if len(summary) > 300 else ""}</p>')

            # Executive Actions
            executive_actions = article.get('executive_actions') or article.get('executive_action', [])
            if executive_actions:
                if isinstance(executive_actions, str):
                    executive_actions = [executive_actions]
                if executive_actions:
                    html_parts.append(f'<div style="margin: 8px 0;">')
                    html_parts.append(f'<p style="color: #666; margin: 0 0 6px 0; font-size: 11px; text-transform: uppercase; font-weight: 600;">Recommended Actions</p>')
                    for action in executive_actions[:3]:
                        html_parts.append(f'<p style="margin: 2px 0; color: #333; font-size: 12px;">→ {action}</p>')
                    html_parts.append('</div>')

            # Scores
            scores = article.get('scores', {})
            if scores and isinstance(scores, dict) and len(scores) > 0:
                score_items = []
                for key in ['relevance', 'impact', 'actionability', 'credibility', 'overall']:
                    if scores.get(key) is not None:
                        label = key.capitalize()
                        score_items.append(f'<span style="margin-right: 12px; font-size: 11px;"><strong>{scores[key]}</strong> {label}</span>')
                if score_items:
                    html_parts.append(f'<p style="margin: 8px 0 0 0; color: #666;">{" ".join(score_items)}</p>')

            # Read more link - make it very visible
            if url:
                html_parts.append(f'<p style="margin: 10px 0 0 0;"><a href="{url}" style="color: #ec4899; font-size: 12px; text-decoration: underline;">🔗 Read full article →</a></p>')
                html_parts.append(f'<p style="margin: 2px 0 0 0; font-size: 10px; color: #999; word-break: break-all;">{url}</p>')
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

    # Build detailed plain text for articles
    article_texts = []
    for i, a in enumerate((request.articles or [])[:6], 1):
        article_text = f"{i}. {a.get('title', 'Untitled')}"
        if a.get('source') or a.get('date'):
            article_text += f"\n   Source: {a.get('source', '')} {a.get('date', '')}"
        if a.get('executive_takeaway'):
            article_text += f"\n   Key Takeaway: {a.get('executive_takeaway')}"
        if a.get('strategic_relevance'):
            article_text += f"\n   Strategic Relevance: {a.get('strategic_relevance')}"
        if a.get('url') or a.get('uri'):
            link = a.get('url') or a.get('uri')
            article_text += f"\n   Read more: {link}"
        article_texts.append(article_text)

    body_text = f"""Executive Briefing - {request.persona}

{request.executive_summary or ''}

Top Stories:
{chr(10).join(article_texts)}

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


@router.post("/share/briefing-card", response_model=ShareResponse)
async def share_briefing_card(
    http_request: Request,
    request: ShareBriefingCardRequest,
    session=Depends(verify_session_api)
):
    """Share a single briefing card via email with all rich data."""
    base_url = get_base_url(http_request)
    # Debug: log all fields for troubleshooting
    logger.info(f"Briefing card share request received:")
    logger.info(f"  - to_email: {request.to_email}")
    logger.info(f"  - title: '{request.title[:50] if request.title else 'None'}'")
    logger.info(f"  - url: '{request.url}'")
    logger.info(f"  - source: '{request.source}'")
    logger.info(f"  - category: '{request.category}'")
    logger.info(f"  - executive_actions: {request.executive_actions}")
    logger.info(f"  - scores: {request.scores}")

    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Briefing: {request.title[:60]}{'...' if len(request.title) > 60 else ''}"

    # Build HTML email with all the rich briefing data
    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">',
        f'<div style="background-color: #8b5cf6; padding: 20px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0; font-size: 24px;">Intelligence Briefing</h1>',
        f'</div>',
        f'<div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef; border-top: none;">',
    ]

    # Category badge
    if request.category:
        category_colors = {
            'policy': '#9333ea',
            'market': '#10b981',
            'tech': '#3b82f6',
            'workforce': '#f97316',
            'security': '#64748b',
            'society': '#14b8a6',
        }
        cat_color = category_colors.get(request.category.lower(), '#6b7280')
        html_parts.append(f'<span style="background: {cat_color}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; text-transform: uppercase; font-weight: 600;">{request.category}</span>')

    # Title (clickable if URL available)
    if request.url:
        html_parts.append(f'<h2 style="margin: 12px 0 8px 0; line-height: 1.4;"><a href="{request.url}" style="color: #333; text-decoration: none;">{request.title}</a></h2>')
    else:
        html_parts.append(f'<h2 style="color: #333; margin: 12px 0 8px 0; line-height: 1.4;">{request.title}</h2>')

    # Source and date
    source_info = []
    if request.source:
        source_info.append(request.source)
    if request.date:
        try:
            from datetime import datetime
            date_obj = datetime.fromisoformat(request.date.replace('Z', '+00:00'))
            source_info.append(date_obj.strftime('%B %d, %Y'))
        except:
            source_info.append(request.date)
    if source_info:
        html_parts.append(f'<p style="color: #666; margin: 0 0 8px 0; font-size: 14px;">{" · ".join(source_info)}</p>')
    # Add visible article link
    if request.url:
        html_parts.append(f'<p style="margin: 0 0 15px 0;"><a href="{request.url}" style="color: #ec4899; font-size: 13px; text-decoration: none;">🔗 Read original article →</a></p>')

    # Rating badges row
    badges_html = []
    if request.risk_opportunity:
        risk_colors = {'opportunity': '#10b981', 'risk': '#ef4444', 'mixed': '#f59e0b'}
        risk_color = risk_colors.get(request.risk_opportunity.lower(), '#6b7280')
        risk_icon = {'opportunity': '↑', 'risk': '↓', 'mixed': '⚡'}.get(request.risk_opportunity.lower(), '')
        badges_html.append(f'<span style="background: {risk_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{risk_icon} {request.risk_opportunity}</span>')
    if request.time_horizon:
        time_colors = {'immediate': '#f97316', 'short-term': '#eab308', 'short': '#eab308', 'medium': '#eab308', 'long-term': '#14b8a6', 'long': '#14b8a6'}
        time_color = time_colors.get(request.time_horizon.lower(), '#6b7280')
        badges_html.append(f'<span style="background: {time_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{request.time_horizon}</span>')
    if request.signal_strength:
        signal_colors = {'strong': '#ec4899', 'moderate': '#3b82f6', 'weak': '#9ca3af'}
        signal_color = signal_colors.get(request.signal_strength.lower(), '#6b7280')
        badges_html.append(f'<span style="background: {signal_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">{request.signal_strength}</span>')
    if request.scores and request.scores.get('overall'):
        badges_html.append(f'<span style="background: #ec4899; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">Score: {request.scores["overall"]}/5</span>')

    if badges_html:
        html_parts.append(f'<p style="margin: 0 0 15px 0;">{"".join(badges_html)}</p>')

    # Executive Takeaway - "Why This Matters"
    if request.executive_takeaway:
        html_parts.append(f'<div style="background-color: #fdf2f8; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #ec4899;">')
        html_parts.append(f'<h4 style="color: #be185d; margin: 0 0 8px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Why This Matters</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.executive_takeaway}</p>')
        html_parts.append('</div>')

    # Summary
    if request.summary:
        html_parts.append(f'<div style="margin: 15px 0;">')
        html_parts.append(f'<h4 style="color: #666; margin: 0 0 8px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Summary</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.summary}</p>')
        html_parts.append('</div>')

    # Strategic Relevance
    if request.strategic_relevance:
        html_parts.append(f'<div style="background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #2196f3;">')
        html_parts.append(f'<h4 style="color: #1565c0; margin: 0 0 8px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Strategic Relevance</h4>')
        html_parts.append(f'<p style="margin: 0; color: #333; line-height: 1.6;">{request.strategic_relevance}</p>')
        html_parts.append('</div>')

    # Executive Actions
    if request.executive_actions and len(request.executive_actions) > 0:
        html_parts.append(f'<div style="margin: 15px 0;">')
        html_parts.append(f'<h4 style="color: #666; margin: 0 0 12px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Recommended Actions</h4>')
        html_parts.append('<ul style="margin: 0; padding-left: 0; list-style: none;">')
        for action in request.executive_actions:
            html_parts.append(f'<li style="margin: 8px 0; color: #333; display: flex; align-items: flex-start;"><span style="color: #ec4899; margin-right: 8px;">→</span><span>{action}</span></li>')
        html_parts.append('</ul>')
        html_parts.append('</div>')

    # Scores breakdown
    if request.scores and len(request.scores) > 1:
        html_parts.append(f'<div style="background: white; padding: 15px; border-radius: 4px; margin: 15px 0; border: 1px solid #e9ecef;">')
        html_parts.append(f'<h4 style="color: #666; margin: 0 0 12px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Score Breakdown</h4>')
        html_parts.append('<table style="width: 100%; border-collapse: collapse;"><tr>')
        score_labels = [('relevance', 'Relevance'), ('impact', 'Impact'), ('actionability', 'Actionability'), ('timeliness', 'Timeliness'), ('credibility', 'Credibility')]
        for key, label in score_labels:
            if request.scores.get(key) is not None:
                html_parts.append(f'<td style="text-align: center; padding: 8px;"><div style="font-size: 20px; font-weight: bold; color: #333;">{request.scores[key]}</div><div style="font-size: 11px; color: #666;">{label}</div></td>')
        html_parts.append('</tr></table>')
        html_parts.append('</div>')

    # Read article button
    if request.url:
        html_parts.append(f'<div style="margin: 20px 0; text-align: center;">')
        html_parts.append(f'<a href="{request.url}" style="display: inline-block; background-color: #8b5cf6; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">Read Full Article</a>')
        html_parts.append('</div>')

    # Action buttons - View in App and Ask Auspex
    auspex_context = f"Analyze this briefing: {request.title}"
    if request.executive_takeaway:
        auspex_context += f"\n\nKey takeaway: {request.executive_takeaway[:200]}"
    if request.strategic_relevance:
        auspex_context += f"\n\nStrategic relevance: {request.strategic_relevance[:200]}"
    auspex_context += "\n\nProvide deeper analysis and additional strategic recommendations."
    auspex_query = urllib.parse.quote(auspex_context)

    html_parts.append('<div style="margin: 20px 0; padding: 15px; background-color: #f3f4f6; border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append('<div style="display: inline-block;">')
    html_parts.append(f'<a href="{base_url}/explore" style="display: inline-block; background-color: #ec4899; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">View Your Briefing</a>')
    html_parts.append(f'<a href="{base_url}/explore?auspex_query={auspex_query}" style="display: inline-block; background-color: #1976d2; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">Ask Auspex</a>')
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
    text_parts = [f"Intelligence Briefing: {request.title}", ""]
    if request.category:
        text_parts.append(f"Category: {request.category}")
    if request.source or request.date:
        text_parts.append(f"{request.source or ''} · {request.date or ''}")
    text_parts.append("")

    # Rating badges
    ratings = []
    if request.risk_opportunity:
        ratings.append(f"Risk/Opportunity: {request.risk_opportunity}")
    if request.time_horizon:
        ratings.append(f"Time Horizon: {request.time_horizon}")
    if request.signal_strength:
        ratings.append(f"Signal: {request.signal_strength}")
    if request.scores and request.scores.get('overall'):
        ratings.append(f"Score: {request.scores['overall']}/5")
    if ratings:
        text_parts.append(" | ".join(ratings))
        text_parts.append("")

    if request.executive_takeaway:
        text_parts.append("WHY THIS MATTERS:")
        text_parts.append(request.executive_takeaway)
        text_parts.append("")

    if request.summary:
        text_parts.append("SUMMARY:")
        text_parts.append(request.summary)
        text_parts.append("")

    if request.strategic_relevance:
        text_parts.append("STRATEGIC RELEVANCE:")
        text_parts.append(request.strategic_relevance)
        text_parts.append("")

    if request.executive_actions:
        text_parts.append("RECOMMENDED ACTIONS:")
        for action in request.executive_actions:
            text_parts.append(f"  → {action}")
        text_parts.append("")

    if request.scores and len(request.scores) > 1:
        scores_text = ", ".join([f"{k.capitalize()}: {v}" for k, v in request.scores.items() if v is not None and k != 'overall'])
        if scores_text:
            text_parts.append(f"Scores: {scores_text}")
            text_parts.append("")

    if request.url:
        text_parts.append(f"Read full article: {request.url}")
        text_parts.append("")

    text_parts.append("---")
    text_parts.append("Continue exploring in AuNoo AI:")
    text_parts.append(f"  View Your Briefing: {base_url}/explore")
    text_parts.append(f"  Ask Auspex: {base_url}/explore?auspex_query={auspex_query}")
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
            logger.info(f"Briefing card shared via email to {request.to_email}")
            return ShareResponse(success=True, message="Briefing shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing briefing card: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/share/emerging-topic", response_model=ShareResponse)
async def share_emerging_topic(
    http_request: Request,
    request: ShareEmergingTopicRequest,
    session=Depends(verify_session_api)
):
    """Share an emerging topic via email."""
    base_url = get_base_url(http_request)
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
        f'<div style="background-color: #8b5cf6; padding: 20px; border-radius: 8px 8px 0 0;">',
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

    # Action buttons section - build rich Auspex query with context
    auspex_context_parts = [f"Analyze this emerging topic: {request.topic_label}"]
    if request.topic_description:
        auspex_context_parts.append(f"\nDescription: {request.topic_description[:300]}")
    if request.why_emerging:
        auspex_context_parts.append(f"\nWhy emerging: {request.why_emerging[:200]}")
    if request.key_entities:
        auspex_context_parts.append(f"\nKey entities: {', '.join(request.key_entities[:5])}")
    if request.articles:
        article_titles = [a.get('title') for a in request.articles[:3] if a.get('title')]
        if article_titles:
            auspex_context_parts.append(f"\nSource articles: {'; '.join(article_titles)}")
    auspex_context_parts.append("\n\nProvide strategic analysis, market implications, and recommended monitoring approach.")
    auspex_query = urllib.parse.quote(''.join(auspex_context_parts))

    html_parts.append('<div style="margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append('<div style="display: inline-block;">')
    # View in App button - links to Emerging Themes tab
    html_parts.append(f'<a href="{base_url}/explore?tab=emerging-topics" style="display: inline-block; background-color: #8b5cf6; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">View Emerging Themes</a>')
    html_parts.append(f'<a href="{base_url}/explore?auspex_query={auspex_query}" style="display: inline-block; background: #1976d2; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; margin: 0 6px;">Ask Auspex</a>')
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
    text_parts.append(f"  View Emerging Themes: {base_url}/explore?tab=emerging-topics")
    text_parts.append(f"  Ask Auspex: {base_url}/explore?auspex_query={auspex_query}")
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


@router.post("/share/executive-summary", response_model=ShareResponse)
async def share_executive_summary(
    http_request: Request,
    request: ShareExecutiveSummaryRequest,
    session=Depends(verify_session_api)
):
    """Share an executive summary via email with all rich data."""
    base_url = get_base_url(http_request)
    logger.info(f"Executive summary share request received for topic: {request.topic_title}")

    email_service = get_email_service()

    if not email_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Email service not configured. Set RESEND_API_KEY environment variable."
        )

    subject = f"[AuNoo AI] Strategic Insight: {request.topic_title}"

    # Get horizon colors
    horizon_colors = {
        'h1': '#2563eb',  # blue
        'h2': '#9333ea',  # purple
        'h3': '#16a34a',  # green
    }
    horizon_color = horizon_colors.get(request.primary_horizon or 'h1', '#6b7280')
    horizon_display = {
        'h1': 'H1 - Declining System',
        'h2': 'H2 - Transition/Innovation',
        'h3': 'H3 - Future Vision'
    }

    # Build HTML email
    html_parts = [
        f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 640px; margin: 0 auto;">',
        f'<div style="background-color: {horizon_color}; padding: 24px; border-radius: 8px 8px 0 0;">',
        f'<h1 style="color: white; margin: 0 0 8px 0; font-size: 22px; font-weight: 700;">Strategic Insight</h1>',
    ]

    if request.research_topic:
        html_parts.append(f'<p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 14px;">Research Topic: {request.research_topic}</p>')

    html_parts.append('</div>')
    html_parts.append(f'<div style="background: #f8f9fa; padding: 24px; border: 1px solid #e9ecef; border-top: none;">')

    # Topic title and horizon badge
    html_parts.append(f'<div style="margin-bottom: 16px;">')
    html_parts.append(f'<h2 style="color: #1e293b; margin: 0 0 12px 0; font-size: 18px; font-weight: 700; letter-spacing: 0.5px;">{request.topic_title}</h2>')
    if request.primary_horizon:
        html_parts.append(f'<span style="background: {horizon_color}; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600;">{horizon_display.get(request.primary_horizon, request.primary_horizon)}</span>')
    html_parts.append('</div>')

    # Opening statement with consensus percentage
    if request.opening_statement:
        html_parts.append(f'<p style="color: #334155; margin: 16px 0; line-height: 1.7; font-size: 15px;">{request.opening_statement}*</p>')

    # Minority view
    if request.minority_view:
        pct_range = request.minority_view.get('percentage_range', '')
        statement = request.minority_view.get('statement', '')
        html_parts.append(f'<p style="color: #64748b; margin: 0 0 16px 0; padding-left: 12px; border-left: 3px solid #cbd5e1; font-style: italic; font-size: 14px;">')
        html_parts.append(f'<span style="font-style: normal; font-weight: 600; color: #475569;">*Minority view ({pct_range}):</span> {statement}')
        html_parts.append('</p>')

    # Primary Signal box
    if request.primary_signal and request.consensus_percentage:
        consensus_color = '#16a34a' if request.consensus_percentage >= 80 else '#d97706' if request.consensus_percentage >= 60 else '#ea580c'
        html_parts.append(f'<div style="background: #f1f5f9; padding: 16px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0;">')
        html_parts.append(f'<p style="margin: 0; line-height: 1.6; font-size: 14px; color: #334155;">')
        html_parts.append(f'<span style="font-weight: 700; color: {consensus_color};">Primary Signal ({request.consensus_percentage}% consensus):</span> {request.primary_signal}')
        html_parts.append('</p></div>')

    # Decision Fork section
    if request.decision_fork:
        condition_a = request.decision_fork.get('condition_a', {})
        condition_b = request.decision_fork.get('condition_b', {})

        html_parts.append(f'<div style="margin: 24px 0; padding-top: 20px; border-top: 1px solid #e2e8f0;">')
        html_parts.append(f'<h3 style="color: #64748b; margin: 0 0 16px 0; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">Decision Fork</h3>')

        if condition_a.get('condition') and condition_a.get('outcome'):
            html_parts.append(f'<div style="margin-bottom: 12px; display: flex; gap: 8px;">')
            html_parts.append(f'<span style="color: #64748b; flex-shrink: 0;">-</span>')
            html_parts.append(f'<p style="margin: 0; font-size: 14px; color: #334155;"><strong>{condition_a["condition"]}</strong> → {condition_a["outcome"]}</p>')
            html_parts.append('</div>')

        if condition_b.get('condition') and condition_b.get('outcome'):
            html_parts.append(f'<div style="display: flex; gap: 8px;">')
            html_parts.append(f'<span style="color: #64748b; flex-shrink: 0;">-</span>')
            html_parts.append(f'<p style="margin: 0; font-size: 14px; color: #334155;"><strong>{condition_b["condition"]}</strong> → {condition_b["outcome"]}</p>')
            html_parts.append('</div>')

        html_parts.append('</div>')

    # Action Window
    if request.action_window:
        assessment = request.action_window.get('assessment', {})
        positioning = request.action_window.get('positioning', {})

        html_parts.append(f'<div style="margin: 20px 0; padding-top: 20px; border-top: 1px solid #e2e8f0;">')
        html_parts.append(f'<div style="display: inline-flex; align-items: center; gap: 8px;">')
        html_parts.append(f'<span style="background: #dbeafe; color: #1d4ed8; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; border: 1px solid #bfdbfe;">Your Window</span>')
        html_parts.append(f'<span style="font-size: 14px; color: #334155;">')

        window_parts = []
        if assessment.get('timeframe') and assessment.get('action'):
            window_parts.append(f"<strong>{assessment['timeframe']}</strong> to {assessment['action']}")
        if positioning.get('timeframe') and positioning.get('action'):
            window_parts.append(f"<strong>{positioning['timeframe']}</strong> to {positioning['action']}")

        html_parts.append('; '.join(window_parts))
        html_parts.append('</span></div></div>')

    # Source scenarios
    if request.source_scenarios and len(request.source_scenarios) > 0:
        html_parts.append(f'<div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e8f0;">')
        html_parts.append(f'<p style="color: #94a3b8; font-size: 12px; margin: 0 0 8px 0;">Based on {len(request.source_scenarios)} underlying scenario{"s" if len(request.source_scenarios) > 1 else ""}:</p>')
        html_parts.append('<ul style="margin: 0; padding-left: 20px; color: #64748b; font-size: 12px;">')
        for scenario in request.source_scenarios[:5]:
            html_parts.append(f'<li style="margin: 4px 0;">{scenario}</li>')
        if len(request.source_scenarios) > 5:
            html_parts.append(f'<li style="margin: 4px 0; font-style: italic;">...and {len(request.source_scenarios) - 5} more</li>')
        html_parts.append('</ul></div>')

    # Action buttons - View in App (use solid color for email client compatibility)
    html_parts.append('<div style="margin: 24px 0; padding: 16px; background-color: #f3f4f6; border-radius: 8px; text-align: center;">')
    html_parts.append('<p style="color: #666; font-size: 12px; margin: 0 0 12px 0;">Continue exploring in AuNoo AI</p>')
    html_parts.append(f'<a href="{base_url}/anticipate" style="display: inline-block; background-color: #8b5cf6; color: white; padding: 10px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">View Future Horizons</a>')
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
    text_parts = [f"Strategic Insight: {request.topic_title}", ""]
    if request.research_topic:
        text_parts.append(f"Research Topic: {request.research_topic}")
    if request.primary_horizon:
        text_parts.append(f"Horizon: {horizon_display.get(request.primary_horizon, request.primary_horizon)}")
    text_parts.append("")

    if request.opening_statement:
        text_parts.append(request.opening_statement + "*")
        text_parts.append("")

    if request.minority_view:
        pct_range = request.minority_view.get('percentage_range', '')
        statement = request.minority_view.get('statement', '')
        text_parts.append(f"*Minority view ({pct_range}): {statement}")
        text_parts.append("")

    if request.primary_signal and request.consensus_percentage:
        text_parts.append(f"Primary Signal ({request.consensus_percentage}% consensus): {request.primary_signal}")
        text_parts.append("")

    if request.decision_fork:
        text_parts.append("DECISION FORK:")
        condition_a = request.decision_fork.get('condition_a', {})
        condition_b = request.decision_fork.get('condition_b', {})
        if condition_a.get('condition') and condition_a.get('outcome'):
            text_parts.append(f"- {condition_a['condition']} → {condition_a['outcome']}")
        if condition_b.get('condition') and condition_b.get('outcome'):
            text_parts.append(f"- {condition_b['condition']} → {condition_b['outcome']}")
        text_parts.append("")

    if request.action_window:
        assessment = request.action_window.get('assessment', {})
        positioning = request.action_window.get('positioning', {})
        window_parts = []
        if assessment.get('timeframe') and assessment.get('action'):
            window_parts.append(f"{assessment['timeframe']} to {assessment['action']}")
        if positioning.get('timeframe') and positioning.get('action'):
            window_parts.append(f"{positioning['timeframe']} to {positioning['action']}")
        text_parts.append(f"Your Window: {'; '.join(window_parts)}")
        text_parts.append("")

    if request.source_scenarios:
        text_parts.append(f"Based on {len(request.source_scenarios)} underlying scenario(s)")
        text_parts.append("")

    text_parts.append("---")
    text_parts.append("Continue exploring in AuNoo AI:")
    text_parts.append(f"  View Future Horizons: {base_url}/anticipate")
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
            return ShareResponse(success=True, message="Executive summary shared successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email")

    except Exception as e:
        logger.error(f"Error sharing executive summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
