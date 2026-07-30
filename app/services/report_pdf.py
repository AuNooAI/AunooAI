"""Render observer-agent markdown reports to PDF (reportlab).

Deliberately handles the subset LLM reports actually use — #–#### headings,
bullet/numbered lists, bold/italic/links, horizontal rules; table rows are
flattened to text lines. Never raises: on any failure the caller should fall
back to sending the email without the attachment.
"""

import io
import logging
import re
from html import escape

from app.compliance.ai_disclosure import disclosure_text, pdf_marker_kwargs

logger = logging.getLogger(__name__)


def _inline(text: str) -> str:
    """Markdown inline → reportlab paragraph markup (b/i/a subset)."""
    out = escape(text)
    out = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                 r'<a href="\2" color="#4055c6"><u>\1</u></a>', out)
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)
    out = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', out)
    out = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', out)
    return out


def markdown_report_to_pdf(title: str, markdown_text: str) -> bytes:
    """Return PDF bytes for a markdown report. Raises on hard failure."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    ListFlowable, ListItem, HRFlowable)

    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=10,
                          leading=14, spaceAfter=6)
    hstyles = {
        1: ParagraphStyle('h1x', parent=styles['Heading1'], fontSize=16, spaceBefore=14),
        2: ParagraphStyle('h2x', parent=styles['Heading2'], fontSize=14, spaceBefore=12),
        3: ParagraphStyle('h3x', parent=styles['Heading3'], fontSize=12, spaceBefore=10),
        4: ParagraphStyle('h4x', parent=styles['Heading4'], fontSize=11, spaceBefore=8),
    }

    flow = [Paragraph(_inline(title), styles['Title']), Spacer(1, 6 * mm)]
    list_buf: list = []
    list_kind = None  # 'ul' | 'ol'

    def flush_list():
        nonlocal list_buf, list_kind
        if list_buf:
            flow.append(ListFlowable(
                [ListItem(Paragraph(item, body)) for item in list_buf],
                bulletType='bullet' if list_kind == 'ul' else '1',
                leftIndent=14))
            flow.append(Spacer(1, 2 * mm))
        list_buf, list_kind = [], None

    for raw in (markdown_text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_list()
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if m:
            flush_list()
            flow.append(Paragraph(_inline(m.group(2)), hstyles[len(m.group(1))]))
            continue
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            flush_list()
            flow.append(HRFlowable(width="100%", color="#cccccc"))
            continue
        m = re.match(r'^[-*+]\s+(.*)$', stripped)
        if m:
            if list_kind != 'ul':
                flush_list()
                list_kind = 'ul'
            list_buf.append(_inline(m.group(1)))
            continue
        m = re.match(r'^\d+[.)]\s+(.*)$', stripped)
        if m:
            if list_kind != 'ol':
                flush_list()
                list_kind = 'ol'
            list_buf.append(_inline(m.group(1)))
            continue
        # table rows / separators → flatten to text (skip pure separators)
        if stripped.startswith('|'):
            if re.match(r'^[|\s:\-]+$', stripped):
                continue
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            flush_list()
            flow.append(Paragraph(_inline(' — '.join(c for c in cells if c)), body))
            continue
        flush_list()
        flow.append(Paragraph(_inline(stripped.lstrip('> ')), body))
    flush_list()

    # EU AI Act Art. 50 visible disclosure — closing footnote.
    disclosure = ParagraphStyle('ai_disclosure', parent=body, fontSize=8,
                                textColor="#6b7280", spaceBefore=6)
    flow.append(HRFlowable(width="100%", color="#e5e7eb"))
    flow.append(Paragraph(_inline(disclosure_text()), disclosure))

    buf = io.BytesIO()
    # EU AI Act Art. 50 machine-readable marker via PDF metadata.
    _m = pdf_marker_kwargs()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title,
                            author=_m["author"], subject=_m["subject"],
                            creator=_m["creator"], keywords=_m["keywords"],
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(flow)
    return buf.getvalue()
