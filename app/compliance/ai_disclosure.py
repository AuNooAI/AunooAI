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

import re
from typing import Any, Dict, Iterable, List, Optional

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


# ---------------------------------------------------------------------------
# Model names for disclosures
# ---------------------------------------------------------------------------
# A litellm response reports the model under its raw Bedrock id, e.g.
# "us.anthropic.claude-haiku-4-5-20251001-v1:0". The usage ledger stores the
# same. Neither is fit for a compliance notice, so every disclosure surface
# maps through here.
_MODEL_LABELS = [
    (re.compile(r'claude-sonnet-4-5'), 'Claude Sonnet 4.5'),
    (re.compile(r'claude-sonnet-5'),   'Claude Sonnet 5'),
    (re.compile(r'claude-opus-5'),     'Claude Opus 5'),
    (re.compile(r'claude-haiku-4-5'),  'Claude Haiku 4.5'),
    (re.compile(r'nova-pro'),          'Nova Pro'),
    (re.compile(r'nova-lite'),         'Nova Lite'),
    (re.compile(r'nova-micro'),        'Nova Micro'),
    (re.compile(r'kimi-k2[.-]5'),      'Kimi K2.5'),
    (re.compile(r'kimi-k2'),           'Kimi K2'),
    (re.compile(r'gpt-5\.4-mini'),    'GPT-5.4 mini'),
    (re.compile(r'gpt-5\.4'),         'GPT-5.4'),
    (re.compile(r'gpt-5\.5-mini'),    'GPT-5.5 mini'),
    (re.compile(r'gpt-5\.5'),         'GPT-5.5'),
]


def model_label(raw_id: Optional[str]) -> str:
    """Human label for a raw model id ("moonshotai.kimi-k2.5" -> "Kimi K2.5")."""
    low = (raw_id or '').lower()
    for pat, label in _MODEL_LABELS:
        if pat.search(low):
            return label
    # Unknown id: drop the provider path, region prefix and version suffix so
    # it at least reads as a model name rather than an ARN fragment.
    core = (raw_id or '').split('/')[-1]
    core = re.sub(r'^(us|eu|global|apac)\.', '', core)
    core = re.sub(r'-v\d+:\d+$', '', core)
    return core


def model_labels(raw_ids: Iterable[Optional[str]]) -> List[str]:
    """Distinct labels, first-seen order, empty ids skipped."""
    out: List[str] = []
    for rid in raw_ids:
        label = model_label(rid)
        if label and label not in out:
            out.append(label)
    return out


def response_model_id(response: Any, requested: Optional[str] = None) -> str:
    """The model a litellm response actually came from, falling back to the
    id that was requested. Mirrors what the usage ledger records."""
    rid = getattr(response, 'model', None) if response is not None else None
    return str(rid) if rid else str(requested or '')
