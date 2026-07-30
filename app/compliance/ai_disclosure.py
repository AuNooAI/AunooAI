"""EU AI Act Article 50 transparency helpers.

Single source of truth for the two things every AI-generated artifact must
carry once the AI Act transparency rules apply (visible obligation 2 Aug 2026,
machine-readable marking 2 Dec 2026 for existing systems):

  1. a VISIBLE disclosure that the content is AI-generated, and
  2. an embedded MACHINE-READABLE marker (document metadata / email header).

Every output surface (reports, decks, emails, HTML/PDF exports) pulls its
wording and marker from here so the disclosure is consistent and can be
updated in one place. Helpers are defensive: a marker must never break
artifact generation, so metadata setters swallow their own errors.
"""
from __future__ import annotations

from typing import Any, Dict

# --- Canonical wording -------------------------------------------------------
AI_DISCLOSURE_SHORT = "Contains AI-generated content."
AI_DISCLOSURE_LONG = (
    "Contains AI-generated content produced by AunooAI. "
    "Verify against cited sources before external use."
)

# Machine-readable marker embedded in document/file metadata and headers.
AI_MARKER_VALUE = "AunooAI; ai-generated=true; standard=EU-AI-Act-Art50"
AI_GENERATOR = "AunooAI (AI-generated content)"

_ROBOT = "\U0001F916"  # 🤖


# --- Visible disclosure ------------------------------------------------------
def disclosure_text(long: bool = True) -> str:
    """Plain-text disclosure line for text email bodies / markdown output."""
    return AI_DISCLOSURE_LONG if long else AI_DISCLOSURE_SHORT


def disclosure_markdown(long: bool = True) -> str:
    """Markdown disclosure block (leading separator) for generated documents."""
    return f"\n\n---\n\n{_ROBOT} *{disclosure_text(long)}*\n"


def disclosure_footer_html(long: bool = True) -> str:
    """Styled footer <div> for HTML report / email bodies (visible disclosure)."""
    return (
        '<div class="ai-disclosure" role="note" '
        'style="margin-top:16px;padding:10px 14px;border-top:1px solid #e5e7eb;'
        'font-size:12px;line-height:1.5;color:#6b7280;">'
        f"{_ROBOT} {disclosure_text(long)}"
        "</div>"
    )


# --- Machine-readable markers ------------------------------------------------
def html_meta_tags() -> str:
    """<meta> tags marking an HTML document as AI-generated (machine-readable)."""
    return (
        f'<meta name="generator" content="{AI_GENERATOR}">'
        '<meta name="ai-generated" content="true">'
        f'<meta name="ai-disclosure" content="{AI_DISCLOSURE_SHORT}">'
    )


def email_headers() -> Dict[str, str]:
    """Extra headers marking an email as carrying AI-generated content."""
    return {"X-AI-Generated": "true", "X-AI-Generated-By": "AunooAI"}


def pdf_marker_kwargs() -> Dict[str, str]:
    """Metadata for PDF generators (reportlab setAuthor/setKeywords, fpdf,
    jsPDF setProperties). Callers map these onto their library's API."""
    return {
        "creator": AI_GENERATOR,
        "author": "AunooAI",
        "keywords": "ai-generated, EU-AI-Act-Art50",
        "subject": AI_DISCLOSURE_SHORT,
    }


def pptx_set_marker(prs: Any) -> None:
    """Embed the AI-generated marker in a python-pptx presentation's core props."""
    try:
        cp = prs.core_properties
        cp.comments = AI_MARKER_VALUE
        cp.category = "AI-generated"
        if not cp.author:
            cp.author = "AunooAI"
        kw = (cp.keywords or "").strip()
        cp.keywords = (kw + "; " if kw else "") + "ai-generated"
    except Exception:  # never let a marker break deck generation
        pass


def docx_set_marker(doc: Any) -> None:
    """Embed the AI-generated marker in a python-docx document's core props."""
    try:
        cp = doc.core_properties
        cp.comments = AI_MARKER_VALUE
        cp.category = "AI-generated"
        kw = (cp.keywords or "").strip()
        cp.keywords = (kw + "; " if kw else "") + "ai-generated"
    except Exception:  # never let a marker break document generation
        pass
