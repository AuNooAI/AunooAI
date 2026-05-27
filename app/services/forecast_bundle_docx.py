"""Word-document renderer for the Wiley quarterly bundle.

Produces a focused executive briefing (not a slide-by-slide dump) modelled
on the human-authored reference ``docs/Wiley_Horizons_Executive_Summary_May2026.docx``:

* Title + period subtitle
* The 5-section exec-summary letter from ``wiley_exec_summary_agent``
  (bolded section headers + body)
* Cross-cutting strategic themes (1 paragraph each)
* Executive Decision Framework (3 leadership priorities)
* Per-topic appendix — for each topic in the bundle, a 1-paragraph
  status summary citing consensus drift, biggest mover, and top
  briefing tension

The PPTX is still the primary artefact for in-meeting presentation. This
docx exists so the same content ships as an emailable briefing without
the slide-design overhead.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor

logger = logging.getLogger(__name__)


# Aunoo / Wiley brand colours mirroring the PPTX palette so the docx
# header rule and section accents read as the same brand.
WILEY_NAVY = RGBColor(0x14, 0x1F, 0x33)
WILEY_TEAL = RGBColor(0xE0, 0x29, 0x6C)  # Aunoo pink — used as accent
WILEY_BODY = RGBColor(0x2A, 0x2D, 0x33)
WILEY_MUTED = RGBColor(0x6B, 0x70, 0x78)


CUSTOMER_LABEL = {
    "Above baseline": "Strengthening",
    "At baseline":    "Stable",
    "Below baseline": "Cooling",
}


def build_bundle_docx(
    items: list,
    *,
    period_label: str,
    cadence: str,
    updates_only: bool,
    bundle_synthesis: Optional[dict] = None,
    eos_per_topic: Optional[dict] = None,
    review_findings: Optional[list] = None,
    review_verdict: Optional[str] = None,
) -> bytes:
    """Render the bundle as a Word document. Returns the file bytes."""
    synth = bundle_synthesis or {}
    exec_summary = synth.get("exec_summary") or {}
    strategic_overview = (synth.get("strategic_overview") or "").strip()
    cross_themes = synth.get("cross_cutting_themes") or []
    decision_framework = synth.get("executive_decision_framework") or []

    doc = Document()
    _set_default_styles(doc)

    # Cover header: title + period
    _h1(doc, "Wiley Horizons — Executive Summary")
    sub_period = period_label
    if updates_only:
        sub_period = f"{period_label} update"
    _subtitle(doc, sub_period)
    _hrule(doc)

    # Review-pending notice when applicable — leads the docx so the reader
    # knows the same blocking findings the deck shows.
    if review_verdict == "revision_requested" and review_findings:
        _review_pending_block(doc, review_findings)
        _hrule(doc)

    # 1. Executive summary letter (the rewritten 5-section briefing)
    letter = (exec_summary or {}).get("letter") or ""
    if letter.strip():
        _render_markdown_paragraphs(doc, letter)
    elif strategic_overview:
        # Fallback when the exec-summary agent didn't run / didn't produce
        # a letter — use the strategic overview as the body. Single para,
        # no section headers.
        _para(doc, strategic_overview)

    # 2. Cross-cutting strategic themes
    if cross_themes:
        _hrule(doc)
        _h2(doc, "Cross-cutting strategic themes")
        for theme in cross_themes:
            if not isinstance(theme, dict):
                continue
            lead = (theme.get("lead") or "").strip()
            body = (theme.get("body") or "").strip()
            if lead:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                run = p.add_run(lead)
                run.bold = True
                run.font.size = Pt(11)
                run.font.color.rgb = WILEY_NAVY
                if body:
                    sep = p.add_run(" ")
                    sep.font.size = Pt(11)
                    bod = p.add_run(body)
                    bod.font.size = Pt(11)
                    bod.font.color.rgb = WILEY_BODY
            elif body:
                _para(doc, body)

    # 3. Executive decision framework
    if decision_framework:
        _hrule(doc)
        _h2(doc, "Executive decision framework")
        for item in decision_framework:
            if not isinstance(item, dict):
                continue
            headline = (item.get("headline") or "").strip()
            body = (item.get("body") or "").strip()
            if headline:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                r1 = p.add_run(headline)
                r1.bold = True
                r1.font.size = Pt(11)
                r1.font.color.rgb = WILEY_NAVY
                if body:
                    sep = p.add_run(" — ")
                    sep.font.size = Pt(11)
                    r2 = p.add_run(body)
                    r2.font.size = Pt(11)
                    r2.font.color.rgb = WILEY_BODY

    # 4. Per-topic appendix
    if items:
        _hrule(doc)
        _h2(doc, "Topic summaries")
        for assessment, _run, prior in items:
            _render_topic_block(doc, assessment, prior, eos_per_topic or {})

    # Signoff footer
    _hrule(doc)
    signoff = (exec_summary or {}).get("signoff") \
              or f"AunooAI Editorial Team · {period_label}"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"— {signoff}")
    run.italic = True
    run.font.size = Pt(10)
    run.font.color.rgb = WILEY_TEAL

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ── Document-level helpers ──────────────────────────────────────────


def _set_default_styles(doc: Document) -> None:
    """Set a clean default body font + margins. Word's defaults give a
    weird Calibri 11 + huge top margin; this aligns to the docx reference."""
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = WILEY_BODY


def _h1(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(22)
    run.font.color.rgb = WILEY_NAVY


def _h2(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = WILEY_NAVY


def _subtitle(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(11)
    run.font.color.rgb = WILEY_MUTED


def _para(doc: Document, text: str, *, italic: bool = False) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    run.italic = italic
    run.font.size = Pt(11)
    run.font.color.rgb = WILEY_BODY


def _hrule(doc: Document) -> None:
    """Insert a thin horizontal rule below the previous paragraph by
    setting its bottom border. python-docx doesn't expose horizontal
    rules natively, so we drop in the OOXML."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "E0296C")
    pBdr.append(bottom)
    pPr.append(pBdr)


# ── Body renderers ──────────────────────────────────────────────────


_BOLD_MARKER = re.compile(r"\*\*(.+?)\*\*")


def _render_markdown_paragraphs(doc: Document, body: str) -> None:
    """Render text with **inline bold** and \\n\\n paragraph breaks.

    Mirrors the slide-side renderer so the exec-summary letter from the
    LLM agent renders identically in both formats.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]
    for para_text in paragraphs:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        cursor = 0
        for m in _BOLD_MARKER.finditer(para_text):
            if m.start() > cursor:
                _append_run(p, para_text[cursor:m.start()], bold=False)
            _append_run(p, m.group(1), bold=True)
            cursor = m.end()
        if cursor < len(para_text):
            _append_run(p, para_text[cursor:], bold=False)


def _append_run(paragraph, text: str, *, bold: bool = False,
                italic: bool = False, color: RGBColor = WILEY_BODY,
                size_pt: float = 11) -> None:
    r = paragraph.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.size = Pt(size_pt)
    r.font.color.rgb = color


def _render_topic_block(doc: Document, assessment: dict, prior: Optional[dict],
                        eos_per_topic: dict) -> None:
    """One short subsection per topic — heading + 1-2 paragraph summary
    citing consensus drift, biggest mover, and the topic's briefing
    tension if available.
    """
    topic = assessment.get("topic") or "—"
    summary = assessment.get("summary") or {}
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})

    # Headline line for the topic
    n_scen = len(verdicts)
    n_above = sum(1 for v in verdicts
                  if ((bc_per.get(str(v.get("scenario_idx"))) or {}).get("label") or v.get("verdict_label")) == "Above baseline")
    n_below = sum(1 for v in verdicts
                  if ((bc_per.get(str(v.get("scenario_idx"))) or {}).get("label") or v.get("verdict_label")) == "Below baseline")
    n_at = sum(1 for v in verdicts
               if ((bc_per.get(str(v.get("scenario_idx"))) or {}).get("label") or v.get("verdict_label")) == "At baseline")

    # Headline line as h3
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(topic)
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = WILEY_NAVY

    # Status distribution as a small stats line
    parts = []
    if n_scen:
        parts.append(f"{n_scen} scenario{'' if n_scen == 1 else 's'} tracked")
    if n_above:
        parts.append(f"{n_above} Strengthening")
    if n_at:
        parts.append(f"{n_at} Stable")
    if n_below:
        parts.append(f"{n_below} Cooling")
    if parts:
        stats_p = doc.add_paragraph()
        stats_p.paragraph_format.space_after = Pt(2)
        sr = stats_p.add_run(" · ".join(parts))
        sr.italic = True
        sr.font.size = Pt(10)
        sr.font.color.rgb = WILEY_MUTED

    # Body paragraph: briefing lede when present, else the biggest mover.
    briefing = summary.get("topic_briefing") or {}
    lede = (briefing.get("lede") or "").strip()
    body_paragraph = None
    if lede:
        body_paragraph = lede
    else:
        # Synthesise a one-liner from the biggest-mover data.
        biggest = _topic_biggest_mover(verdicts, bc_per)
        if biggest:
            net_pct = biggest["delta_pct"]
            sign = "+" if net_pct >= 0 else ""
            body_paragraph = (
                f"The biggest movement was {biggest['scenario']} "
                f"({sign}{net_pct:.2f}% confirmation delta)."
            )
    if body_paragraph:
        _para(doc, body_paragraph)

    # Surface the first tension if present — second short paragraph.
    tensions = briefing.get("tensions") or []
    if tensions:
        first = tensions[0]
        body = (first.get("body") if isinstance(first, dict) else str(first)).strip()
        if body:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(8)
            lead_run = p.add_run("Defining tension. ")
            lead_run.bold = True
            lead_run.font.size = Pt(11)
            lead_run.font.color.rgb = WILEY_NAVY
            body_run = p.add_run(body)
            body_run.font.size = Pt(11)
            body_run.font.color.rgb = WILEY_BODY


def _topic_biggest_mover(verdicts: list, bc_per: dict) -> Optional[dict]:
    biggest = None
    for v in verdicts:
        key = str(v.get("scenario_idx"))
        net = (bc_per.get(key) or {}).get("net_rate")
        if net is None:
            continue
        if biggest is None or abs(net) > abs(biggest["net_rate"]):
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            biggest = {
                "scenario": deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—",
                "net_rate": net,
                "delta_pct": net * 100,
            }
    return biggest


def _review_pending_block(doc: Document, findings: list) -> None:
    """Render the reviewer's blocking errors as a leading callout."""
    errors = [f for f in findings if f.get("severity") == "error"]
    if not errors:
        return
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run("REVIEW PENDING — DO NOT SHIP")
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor(0xC0, 0x1F, 0x1F)
    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(6)
    sr = sub.add_run(
        f"AunooAI's LLM-as-judge reviewer flagged {len(errors)} blocking "
        f"finding{'' if len(errors) == 1 else 's'} on this bundle."
    )
    sr.italic = True
    sr.font.size = Pt(10)
    sr.font.color.rgb = WILEY_MUTED
    for f in errors[:5]:
        artefact = (f.get("artefact_key") or "").strip()
        finding = (f.get("finding") or "").strip()
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        head = p.add_run(f"  • {artefact}: ")
        head.bold = True
        head.font.size = Pt(10)
        head.font.color.rgb = RGBColor(0xC0, 0x1F, 0x1F)
        body = p.add_run(finding)
        body.font.size = Pt(10)
        body.font.color.rgb = WILEY_BODY
