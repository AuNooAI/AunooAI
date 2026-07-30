"""Standalone Word DOCX renderer for the on-demand Topic Report.

Consumes the same ``items`` list ``topic_report_pptx.build_topic_report_pptx``
walks — so the DOCX content (Briefing Synthesis, Executive Summary
cards, Key Insights, Strategic Recommendations, Executive Decision
Framework, Next Steps, Black Swans, Three Horizons scenarios, Article
References) is identical to the PPTX/HTML.

NOT to be confused with ``forecast_bundle_docx.build_bundle_docx`` —
that renders the cadence-locked Forecast Tracker bundle (back-test
framing, review-pending banner, baseline-correction terminology). This
module renders the forecast-driven foresight deck.

Output: a single ``.docx`` byte blob. Inline ``[N]`` citation markers
are emitted as Word hyperlinks targeting the article URL directly so
clicking jumps to the source.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.services.topic_report_pptx import _decode_raw_output
from app.services.html_report_common import clean_article_ref
from app.compliance.ai_disclosure import (
    disclosure_text as _ai_text,
    docx_set_marker as _ai_docx_marker,
)

logger = logging.getLogger(__name__)


# Wiley palette — same hex values as the PPTX/HTML builders.
WILEY_NAVY  = RGBColor(0x11, 0x18, 0x27)
WILEY_TEAL  = RGBColor(0xD6, 0x34, 0x6C)   # branded pink, named "teal" elsewhere
WILEY_BODY  = RGBColor(0x1F, 0x29, 0x37)
WILEY_MUTED = RGBColor(0x6B, 0x72, 0x80)
SLATE_LIGHT = RGBColor(0x9C, 0xA3, 0xAF)

_CITE_RE = re.compile(r"\[(\d{1,3})\]")


# ── DOCX primitives ─────────────────────────────────────────────────


def _set_default_styles(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = WILEY_BODY


def _heading(doc: Document, text: str, *, size_pt: float, color=WILEY_NAVY,
             before_pt: float = 12, after_pt: float = 4, bold: bool = True) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before_pt)
    p.paragraph_format.space_after  = Pt(after_pt)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size_pt)
    run.font.color.rgb = color


def _eyebrow(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(8.5)
    run.font.color.rgb = WILEY_TEAL


def _hr(doc: Document) -> None:
    """Thin teal bottom border — python-docx has no native hr."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "D6346C")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_hyperlink_run(paragraph, text: str, url: str, *, bold: bool = True,
                       color=WILEY_TEAL, size_pt: float = 11) -> None:
    """Insert a hyperlink run inside an existing paragraph.

    python-docx omits hyperlink support, so we drop the OOXML in
    ourselves: relate the URL to the document part, then wrap a styled
    run in a ``<w:hyperlink r:id="…">``.
    """
    if not url:
        run = paragraph.add_run(text)
        run.bold = bold
        run.font.size = Pt(size_pt)
        run.font.color.rgb = color
        return
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    # color
    c = OxmlElement("w:color")
    c.set(qn("w:val"), "D6346C")
    rPr.append(c)
    # underline
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)
    # bold
    if bold:
        rPr.append(OxmlElement("w:b"))
    # size (half-points)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size_pt * 2)))
    rPr.append(sz)
    new_run.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _add_body_with_citations(doc: Document, text: str, articles=None, *,
                             bold: bool = False, italic: bool = False,
                             size_pt: float = 11, color=WILEY_BODY,
                             space_after_pt: float = 8) -> None:
    """Append a paragraph; split on ``[N]`` and hyperlink each citation
    run to the matching article URL.

    When ``articles`` is empty or ``N`` is out of range, the citation
    stays as bold-pink ``[N]`` text (still visually marked, just not
    clickable). Body chunks stay plain.
    """
    if not text:
        return
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after_pt)

    parts = _CITE_RE.split(text) if articles else [text]
    if len(parts) == 1:
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(size_pt)
        run.font.color.rgb = color
        return

    for i, chunk in enumerate(parts):
        if not chunk:
            continue
        is_cite = (i % 2 == 1)
        if is_cite:
            try:
                n = int(chunk)
                entry = articles[n - 1] if 1 <= n <= len(articles) else None
            except Exception:
                entry = None
            url = ""
            if entry:
                url = (entry.get("uri") or entry.get("url") or "").strip()
            label = f"[{chunk}]"
            if url:
                _add_hyperlink_run(p, label, url, bold=True,
                                   color=WILEY_TEAL, size_pt=size_pt)
            else:
                run = p.add_run(label)
                run.bold = True
                run.font.size = Pt(size_pt)
                run.font.color.rgb = WILEY_TEAL
        else:
            run = p.add_run(chunk)
            run.bold = bold
            run.italic = italic
            run.font.size = Pt(size_pt)
            run.font.color.rgb = color


def _bullet(doc: Document, text: str, articles=None) -> None:
    """Bulleted body paragraph with citation linkification."""
    if not text:
        return
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(4)
    parts = _CITE_RE.split(text) if articles else [text]
    if len(parts) == 1:
        run = p.add_run(text)
        run.font.size = Pt(11)
        run.font.color.rgb = WILEY_BODY
        return
    for i, chunk in enumerate(parts):
        if not chunk:
            continue
        if i % 2 == 1:
            try:
                n = int(chunk)
                entry = articles[n - 1] if 1 <= n <= len(articles) else None
            except Exception:
                entry = None
            url = (entry.get("uri") or entry.get("url") or "").strip() if entry else ""
            label = f"[{chunk}]"
            if url:
                _add_hyperlink_run(p, label, url, bold=True, color=WILEY_TEAL)
            else:
                r = p.add_run(label)
                r.bold = True
                r.font.size = Pt(11)
                r.font.color.rgb = WILEY_TEAL
        else:
            r = p.add_run(chunk)
            r.font.size = Pt(11)
            r.font.color.rgb = WILEY_BODY


# ── Section renderers ──────────────────────────────────────────────


def _render_cover(doc: Document, period_label: str, period: str,
                  topics: list) -> None:
    _eyebrow(doc, "Wiley Horizons · Foresight")
    _heading(doc, period, size_pt=26, color=WILEY_NAVY,
             before_pt=2, after_pt=4)
    _heading(doc, "Topic Foresight Report", size_pt=14,
             color=WILEY_MUTED, bold=False, before_pt=0, after_pt=2)
    sub = ", ".join(t for t in topics if t)
    if sub:
        _heading(doc, f"{len(topics)} topic{'s' if len(topics) != 1 else ''}: {sub}",
                 size_pt=11, color=WILEY_MUTED, bold=False,
                 before_pt=2, after_pt=14)
    _hr(doc)


def _render_topic_divider(doc: Document, topic: str, topic_idx: int) -> None:
    _eyebrow(doc, f"Topic {topic_idx}")
    _heading(doc, topic, size_pt=22, color=WILEY_NAVY,
             before_pt=12, after_pt=10)


def _render_briefing(doc: Document, brief: dict, articles=None) -> None:
    if not brief or not brief.get("lede"):
        return
    _heading(doc, "Briefing Synthesis", size_pt=15, color=WILEY_NAVY,
             before_pt=14, after_pt=4)
    if brief.get("headline"):
        _add_body_with_citations(doc, brief["headline"], italic=True,
                                 color=WILEY_MUTED, space_after_pt=8)
    _add_body_with_citations(doc, brief.get("lede") or "", articles)
    iv = (brief.get("intelligence_view") or "").strip()
    if iv:
        _heading(doc, "The Aunoo Intelligence View", size_pt=12,
                 color=WILEY_TEAL, before_pt=6, after_pt=2)
        _add_body_with_citations(doc, iv, articles)
    tensions = brief.get("tensions") or []
    if tensions:
        _heading(doc, "Defining Tensions", size_pt=12, color=WILEY_TEAL,
                 before_pt=6, after_pt=2)
        for t in tensions[:4]:
            if not isinstance(t, dict):
                continue
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run((t.get("name") or "").upper() + "  ")
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = WILEY_TEAL
            body = (t.get("body") or "").strip()
            if body:
                _add_body_with_citations(doc, body, articles, space_after_pt=4)


def _render_exec_summary_cards(doc: Document, cards: list, articles=None) -> None:
    cards = [c for c in (cards or []) if isinstance(c, dict)]
    if not cards:
        return
    _heading(doc, "Executive Summary", size_pt=15, color=WILEY_NAVY,
             before_pt=14, after_pt=4)
    for k, c in enumerate(cards, 1):
        horizon = (c.get("primary_horizon") or "").upper()
        h_label = c.get("horizon_label") or ""
        cons = c.get("consensus_percentage")
        cons_pct = f"{int(cons)}%" if isinstance(cons, (int, float)) else ""
        title = c.get("topic_title") or ""

        _eyebrow(doc, f"Card {k} of {len(cards)}")
        _heading(doc, title, size_pt=13, color=WILEY_NAVY,
                 before_pt=4, after_pt=2)

        meta_bits = []
        if horizon: meta_bits.append(f"{horizon} · {h_label}".strip(" ·"))
        if cons_pct: meta_bits.append(f"{cons_pct} CONSENSUS")
        if meta_bits:
            _add_body_with_citations(doc, "  ·  ".join(meta_bits),
                                     bold=True, color=WILEY_TEAL,
                                     size_pt=10, space_after_pt=4)
        opening = (c.get("opening_statement") or "").strip()
        if opening:
            _add_body_with_citations(doc, opening, articles)

        mv = c.get("minority_view") or {}
        if mv.get("statement"):
            pct = mv.get("percentage_range") or ""
            label = "MINORITY VIEW" + (f"  ·  {pct}" if pct else "")
            _add_body_with_citations(doc, label, bold=True,
                                     color=WILEY_TEAL, size_pt=9,
                                     space_after_pt=2)
            _add_body_with_citations(doc, mv["statement"], articles, italic=True)

        signal = (c.get("primary_signal") or "").strip()
        if signal:
            lab = "PRIMARY SIGNAL" + (f"  ·  {cons_pct} CONSENSUS" if cons_pct else "")
            _add_body_with_citations(doc, lab, bold=True, color=WILEY_TEAL,
                                     size_pt=9, space_after_pt=2)
            _add_body_with_citations(doc, signal, articles, bold=True)

        fork = c.get("decision_fork") or {}
        fa = fork.get("condition_a") or {}
        fb = fork.get("condition_b") or {}
        if fa.get("condition") or fb.get("condition"):
            _add_body_with_citations(doc, "DECISION FORK", bold=True,
                                     color=WILEY_NAVY, size_pt=9,
                                     space_after_pt=2)
            for marker, frow in (("✔", fa), ("!", fb)):
                cond = (frow.get("condition") or "").strip()
                outc = (frow.get("outcome") or "").strip()
                if cond or outc:
                    _add_body_with_citations(
                        doc, f"{marker}  {cond}", articles,
                        bold=True, size_pt=10, space_after_pt=2,
                    )
                    if outc:
                        _add_body_with_citations(
                            doc, f"     → {outc}", articles,
                            size_pt=10, space_after_pt=4,
                        )
        aw = c.get("action_window") or {}
        aw_a = aw.get("assessment") or {}
        aw_p = aw.get("positioning") or {}
        if aw_a.get("action") or aw_p.get("action"):
            _add_body_with_citations(doc, "YOUR WINDOW", bold=True,
                                     color=WILEY_TEAL, size_pt=9,
                                     space_after_pt=2)
            for row in (aw_a, aw_p):
                tf = (row.get("timeframe") or "").strip()
                act = (row.get("action") or "").strip()
                if tf:
                    _add_body_with_citations(doc, tf.upper(), bold=True,
                                             color=WILEY_TEAL, size_pt=9,
                                             space_after_pt=2)
                if act:
                    _add_body_with_citations(doc, act, articles,
                                             space_after_pt=4)
        src = [s for s in (c.get("source_scenarios") or []) if isinstance(s, dict)]
        if src:
            _add_body_with_citations(doc, "Based on scenarios", bold=True,
                                     color=WILEY_MUTED, size_pt=9,
                                     space_after_pt=2)
            for s in src:
                h = (s.get("horizon") or "").upper()
                t = (s.get("title") or "").strip()
                if t:
                    _add_body_with_citations(
                        doc, f"  {h}  ·  {t}" if h else f"  {t}",
                        size_pt=10, space_after_pt=2,
                    )


def _render_bullet_list(doc: Document, title: str, items: list,
                        articles=None) -> None:
    items = [s for s in (items or []) if isinstance(s, str) and s.strip()]
    if not items:
        return
    _heading(doc, title, size_pt=14, color=WILEY_NAVY,
             before_pt=12, after_pt=4)
    for s in items[:8]:
        _bullet(doc, s, articles)


def _render_strategic_recs(doc: Document, recs: list, articles=None) -> None:
    recs = [r for r in (recs or []) if isinstance(r, dict)]
    if not recs:
        return
    _heading(doc, "Strategic Recommendations", size_pt=14, color=WILEY_NAVY,
             before_pt=12, after_pt=4)
    for r in recs[:3]:
        _heading(doc, (r.get("headline") or "—"), size_pt=12,
                 color=WILEY_TEAL, before_pt=6, after_pt=2)
        rationale = (r.get("rationale") or "").strip()
        if rationale:
            _add_body_with_citations(doc, rationale, articles)
        horizon = (r.get("horizon") or "").strip()
        if horizon:
            _add_body_with_citations(doc, f"Horizon: {horizon}",
                                     italic=True, color=WILEY_MUTED,
                                     size_pt=10, space_after_pt=4)


def _render_decision_framework(doc: Document, principles: list,
                               articles=None) -> None:
    principles = [p for p in (principles or []) if isinstance(p, dict)]
    if not principles:
        return
    _heading(doc, "Executive Decision Framework", size_pt=14,
             color=WILEY_NAVY, before_pt=12, after_pt=4)
    for p in principles[:3]:
        _heading(doc, (p.get("headline") or "—"), size_pt=12,
                 color=WILEY_TEAL, before_pt=6, after_pt=2)
        body = (p.get("body") or "").strip()
        if body:
            _add_body_with_citations(doc, body, articles)


def _render_next_steps(doc: Document, steps: list, articles=None) -> None:
    steps = [s for s in (steps or []) if isinstance(s, dict)]
    if not steps:
        return
    _heading(doc, "Next Steps", size_pt=14, color=WILEY_NAVY,
             before_pt=12, after_pt=4)
    for i, s in enumerate(steps[:3], 1):
        cat = (s.get("category") or f"Step {i}").upper()
        _eyebrow(doc, cat)
        action = (s.get("action") or "").strip()
        if action:
            _add_body_with_citations(doc, action, articles)


def _render_black_swans(doc: Document, eos: list, articles=None) -> None:
    eos = [s for s in (eos or []) if isinstance(s, dict)]
    if not eos:
        return
    _heading(doc, "Black Swans & Wildcards", size_pt=14,
             color=WILEY_NAVY, before_pt=12, after_pt=4)

    def _coerce(v, default=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return {"low": 0.1, "medium": 0.3, "high": 0.6,
                    "very_high": 0.85}.get(
                        (v or "").strip().lower().replace(" ", "_"),
                        default,
                    )
    eos_sorted = sorted(eos,
                        key=lambda s: -_coerce(s.get("impact_rating"), 5.0)
                                       * _coerce(s.get("probability"), 0.2))
    for s in eos_sorted[:4]:
        cat = (s.get("category") or "black_swan").lower().replace("_", " ").upper()
        _eyebrow(doc, cat)
        _heading(doc, (s.get("name") or "—"), size_pt=12,
                 color=WILEY_NAVY, before_pt=2, after_pt=2)
        trajectory = (s.get("trajectory") or s.get("description") or "").strip()
        if trajectory:
            _add_body_with_citations(doc, trajectory, articles)
        impact = s.get("impact_rating")
        timeframe = s.get("timeframe") or ""
        meta_bits = []
        if impact is not None:
            try: meta_bits.append(f"Impact {int(impact)}/10")
            except Exception: pass
        if timeframe: meta_bits.append(timeframe)
        if meta_bits:
            _add_body_with_citations(doc, "  ·  ".join(meta_bits),
                                     italic=True, color=WILEY_MUTED,
                                     size_pt=10, space_after_pt=4)


def _render_scenarios(doc: Document, scenarios: list, articles=None) -> None:
    scenarios = [s for s in (scenarios or []) if isinstance(s, dict)]
    if not scenarios:
        return
    _heading(doc, "Three Horizons", size_pt=14, color=WILEY_NAVY,
             before_pt=12, after_pt=4)
    labels = {"h1": "H1 — Declining Systems",
              "h2": "H2 — Transition / Innovation",
              "h3": "H3 — Future Vision"}
    by_horizon = {"h1": [], "h2": [], "h3": []}
    for s in scenarios:
        h = (s.get("type") or "h1").lower()
        if h in by_horizon:
            by_horizon[h].append(s)
    for horizon in ("h1", "h2", "h3"):
        group = by_horizon[horizon]
        if not group:
            continue
        _heading(doc, labels[horizon], size_pt=12, color=WILEY_TEAL,
                 before_pt=8, after_pt=2)
        for s in group:
            title = (s.get("title") or "—").strip()
            tf = (s.get("timeframe") or "").strip()
            sentiment = (s.get("sentiment") or "").strip()
            meta = "  ·  ".join([b for b in (horizon.upper(), tf, sentiment) if b])
            _add_body_with_citations(doc, meta, bold=True,
                                     color=WILEY_MUTED, size_pt=9,
                                     space_after_pt=2)
            _heading(doc, title, size_pt=11.5, color=WILEY_NAVY,
                     before_pt=2, after_pt=2)
            desc = (s.get("description") or "").strip()
            if desc:
                _add_body_with_citations(doc, desc, articles)


def _render_article_references(doc: Document, articles: list) -> None:
    refs = [a for a in (articles or []) if isinstance(a, dict)
            and (a.get("title") or "").strip()]
    if not refs:
        return
    _heading(doc, "Article References", size_pt=14, color=WILEY_NAVY,
             before_pt=14, after_pt=4)
    _add_body_with_citations(
        doc, f"{len(refs)} articles the LLM cited as [N] in this report",
        italic=True, color=SLATE_LIGHT, size_pt=10, space_after_pt=8,
    )
    for n, a in enumerate(refs, 1):
        cleaned = clean_article_ref(a)
        title = cleaned["title"] or "—"
        uri = cleaned["uri"]
        source = cleaned["source"]
        date = cleaned["date"]
        meta_bits = [b for b in (source, date) if b]

        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        num = p.add_run(f"[{n}]  ")
        num.bold = True
        num.font.size = Pt(10)
        num.font.color.rgb = WILEY_TEAL
        if uri:
            _add_hyperlink_run(p, title, uri, bold=False,
                               color=WILEY_NAVY, size_pt=10)
        else:
            r = p.add_run(title)
            r.font.size = Pt(10)
            r.font.color.rgb = WILEY_NAVY
        if meta_bits:
            r = p.add_run("    " + "  ·  ".join(meta_bits))
            r.font.size = Pt(9)
            r.font.color.rgb = WILEY_MUTED


# ── Public entry point ────────────────────────────────────────────


def build_topic_report_docx(items: list, *, period_label: str,
                            period: Optional[str] = None) -> bytes:
    """Render the topic-report DOCX.

    Same ``items`` triple list ``build_topic_report_pptx`` consumes.
    Output mirrors the HTML: cover → per-topic divider → briefing →
    exec summary cards → key insights → strategic recs → decision
    framework → next steps → black swans → three horizons → article
    references → topic separator. ``[N]`` markers are emitted as Word
    hyperlinks pointing directly at the article URL.
    """
    doc = Document()
    _set_default_styles(doc)

    topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    period_display = period or period_label
    _render_cover(doc, period_label, period_display, topics)

    for topic_idx, (assessment, forecast_run, _prior) in enumerate(items, 1):
        topic_name = assessment.get("topic") or "—"
        raw = _decode_raw_output(forecast_run or {})
        summary = assessment.get("summary") or {}
        # Numbered corpus the LLM cited.
        articles = (assessment.get("_articles_corpus")
                    or assessment.get("_supporting_articles") or [])

        _render_topic_divider(doc, topic_name, topic_idx)
        _render_briefing(doc, summary.get("topic_briefing") or {}, articles)
        _render_exec_summary_cards(doc, assessment.get("_exec_summary_cards") or [], articles)
        _render_bullet_list(doc, "Key Insights",
                            summary.get("key_insights") or [], articles)
        _render_strategic_recs(doc, summary.get("strategic_recommendations") or [],
                               articles)
        edf = summary.get("executive_decision_framework") or {}
        _render_decision_framework(doc,
            edf.get("principles") if isinstance(edf, dict) else None, articles)
        _render_next_steps(doc, summary.get("next_steps") or [], articles)
        _render_black_swans(doc, assessment.get("_eos_scenarios") or [], articles)
        _render_scenarios(doc, raw.get("scenarios") or [], articles)
        _render_article_references(doc, articles)
        _hr(doc)

    # Footer line
    _add_body_with_citations(
        doc,
        f"Topic report rendered {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        f"  ·  AunooAI Wiley Horizons Foresight",
        italic=True, color=WILEY_MUTED, size_pt=9, space_after_pt=0,
    )
    # EU AI Act Art. 50 visible disclosure
    _add_body_with_citations(
        doc, _ai_text(), italic=True, color=WILEY_MUTED, size_pt=9, space_after_pt=0,
    )

    _ai_docx_marker(doc)  # EU AI Act Art. 50 machine-readable marker
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()
