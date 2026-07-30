"""Topic Report PPTX builder.

Renders a long-form Wiley-style report deck *directly from the Future
Horizons analysis* (``future_horizons_runs.raw_output``). Sister to
:mod:`forecast_bundle_pptx`, which renders the cadence-locked Forecast
Tracker back-test bundle — this one does NOT touch the multi-agent
supervisor and does NOT depend on evidence-scored assessments.

The reference deck is "Wiley Horizons Final (2).pptx" (the 2026-2030
Wiley Horizons foresight deliverable): forward-looking scenarios,
strategic recommendations, decision framework, next steps. The
Future Horizons analysis produces those fields directly into
``raw_output``; this module just shapes them into the Wiley deck format.

Slide order per deck:

* Intro template (8 slides — team / methodology / "What We Monitor")
* Cover
* (Cross-topic) Three Horizons Overview — if 2+ topics
* Per topic:
    - Divider
    - Three Horizons chart
    - Scenario deep-dives (H1/H2/H3 cards)
    - Strategic Recommendations
    - Key Insights
    - Next Steps
* Methodology appendix
"""
from __future__ import annotations

import json
import logging
import os
import re
from io import BytesIO
from typing import Optional

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from app.compliance.ai_disclosure import pptx_set_marker as _ai_pptx_marker

from app.services.forecast_pptx_export import (
    _add_methodology_appendix_slide,
    _add_briefing_synthesis_slide,
    _add_key_insights_slide,
    _add_strategic_recommendations_slide,
    _add_next_steps_slide,
    _add_black_swans_slide,
    _add_surprise_cluster_slide,
    _add_surprises_divider,
    _add_left_rail,
    _add_brand_mark,
    _add_brand_footer,
    _add_bg_image,
    _rect, _text, _truncate, _split_title,
    _horizon_color, _horizon_label, _horizon_full_label,
    WILEY_BG_SOFT, WILEY_BG_COVER, WILEY_BG_BOKEH,
    WILEY_NAVY, WILEY_TEAL, WILEY_TEAL_LT, WILEY_BODY, WILEY_MUTED,
    WILEY_CARD_BG,
    SLATE_DARK, SLATE_MID, SLATE_LIGHT, SLATE_BLACK,
    RULE_GRAY, WHITE,
)
from app.services.forecast_bundle_pptx import (
    _add_bundle_cover,
    _add_topic_divider,
    _add_topic_three_horizons_chart,
    _add_three_horizons_overview,
)
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)

INTRO_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static_assets", "topic_report_intro.pptx",
)


def _decode_raw_output(forecast_run: dict) -> dict:
    """Defensively decode ``forecast_run.raw_output`` to a dict.

    Some runs persist as plain dict, some as a JSON-encoded string, some as
    a double-encoded JSON string (known supervisor pitfall). Return ``{}``
    on any decode failure rather than raising — a missing forecast field
    just drops that slide.
    """
    raw = forecast_run.get("raw_output") if forecast_run else None
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


_CITE_RE = re.compile(r"\[(\d{1,3})\]")


def _text_cites(slide, *, x: float, y: float, w: float, h: float,
                text: str, articles: Optional[list] = None,
                font_size: float = 10.0, bold: bool = False,
                italic: bool = False, color=None, align=None,
                line_spacing: Optional[float] = None) -> None:
    """Render ``text`` with ``[N]`` citation markers as clickable hyperlinks.

    Each ``[N]`` token is split into its own pptx ``run`` with
    ``run.hyperlink.address`` set to ``articles[N-1]["uri"]`` so
    PowerPoint renders it as a clickable link. The bracketed text itself
    is styled bold + teal so readers can SEE it's a citation, not just
    plain text.

    Falls back to plain :func:`_text` when ``articles`` is empty, the text
    has no ``[N]`` markers, or any of the cited indices is out of range
    for the corpus (better to skip styling than mislead the reader).
    """
    if not articles or not text or "[" not in text:
        _text(slide, x=x, y=y, w=w, h=h, text=text or "",
              font_size=font_size, bold=bold, italic=italic,
              color=color, align=align, line_spacing=line_spacing)
        return

    parts = _CITE_RE.split(text)
    if len(parts) == 1:
        _text(slide, x=x, y=y, w=w, h=h, text=text,
              font_size=font_size, bold=bold, italic=italic,
              color=color, align=align, line_spacing=line_spacing)
        return

    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    try:
        tf.margin_left = tf.margin_right = 0
        tf.margin_top  = tf.margin_bottom = 0
    except Exception:
        pass
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = align
    if line_spacing is not None:
        try:
            p.line_spacing = line_spacing
        except Exception:
            pass

    body_color = color
    cite_color = WILEY_TEAL

    for i, chunk in enumerate(parts):
        if chunk is None or chunk == "":
            continue
        run = p.add_run()
        is_cite = (i % 2 == 1)
        if is_cite:
            try:
                n = int(chunk)
                article = articles[n - 1] if 1 <= n <= len(articles) else None
            except Exception:
                article = None
            run.text = f"[{chunk}]"
            run.font.size = Pt(font_size)
            run.font.bold = True
            try:
                run.font.color.rgb = cite_color if isinstance(cite_color, RGBColor) \
                    else RGBColor(*cite_color) if isinstance(cite_color, tuple) \
                    else cite_color
            except Exception:
                pass
            if article and (article.get("uri") or article.get("url")):
                try:
                    run.hyperlink.address = article.get("uri") or article.get("url")
                except Exception:
                    pass
        else:
            run.text = chunk
            run.font.size = Pt(font_size)
            run.font.bold = bold
            run.font.italic = italic
            if body_color is not None:
                try:
                    run.font.color.rgb = body_color if isinstance(body_color, RGBColor) \
                        else RGBColor(*body_color) if isinstance(body_color, tuple) \
                        else body_color
                except Exception:
                    pass


def _add_topic_references_slide(prs, articles: list, *,
                                topic: str, topic_idx: Optional[int] = None):
    """Numbered article-references slides at the end of each topic section.

    Visual companion to the ``[N]`` hyperlinks in the body slides — the
    reader can either click ``[15]`` (opens the article URL in a browser)
    or jump to this slide to see the full numbered list. Skips silently
    when ``articles`` is empty.

    When the cited corpus is larger than fits one slide (40 refs in a
    two-column grid), emits as many references slides as needed and
    labels them ``part 1 of N``, ``part 2 of N`` etc. — per Pascal's
    Jun 2026 feedback that references were silently dropped when the
    corpus ran past 40.
    """
    if not articles:
        return
    sw = 10.0
    body_top = 1.20
    body_bot = 5.50
    col_w    = (sw - 1.0 - 0.30) / 2
    col_x    = [0.5, 0.5 + col_w + 0.30]
    rows_per_col = max(1, int((body_bot - body_top) / 0.21))
    per_slide = rows_per_col * 2

    from app.services.html_report_common import clean_article_ref

    n_total = len(articles)
    n_slides = (n_total + per_slide - 1) // per_slide
    eyebrow_base = (f"TOPIC {topic_idx} · ARTICLE REFERENCES" if topic_idx is not None
                    else "ARTICLE REFERENCES")

    for slide_idx in range(n_slides):
        blank = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank)
        _add_bg_image(slide, WILEY_BG_SOFT)

        eyebrow = eyebrow_base
        if n_slides > 1:
            eyebrow = f"{eyebrow_base}  ·  PART {slide_idx + 1} OF {n_slides}"
        _text(slide, x=0.5, y=0.20, w=sw-1.0, h=0.22,
              text=eyebrow, font_size=9, bold=True, color=SLATE_MID)
        _text(slide, x=0.5, y=0.42, w=sw-1.0, h=0.40,
              text=f"{topic} — Source Corpus", font_size=18, bold=True, color=SLATE_DARK)
        # Subtitle: total count on slide 1, range "[A]–[B]" on subsequent slides.
        if slide_idx == 0:
            sub = f"{n_total} articles the LLM cited as [N] in this report"
        else:
            first = slide_idx * per_slide + 1
            last  = min(n_total, (slide_idx + 1) * per_slide)
            sub = f"References [{first}]–[{last}] of {n_total}"
        _text(slide, x=0.5, y=0.85, w=sw-1.0, h=0.22,
              text=sub, font_size=9, italic=True, color=SLATE_LIGHT)

        start = slide_idx * per_slide
        end   = min(n_total, start + per_slide)
        for i, a in enumerate(articles[start:end]):
            n_overall = start + i + 1  # 1-based citation index across all slides
            col = i // rows_per_col
            r   = i %  rows_per_col
            x = col_x[col]
            y = body_top + r * 0.21
            cleaned = clean_article_ref(a)
            title = cleaned["title"] or "—"
            source = cleaned["source"]
            date = cleaned["date"]
            meta_bits = [b for b in (source, date) if b]
            meta_suffix = f"  ·  {'  ·  '.join(meta_bits)}" if meta_bits else ""
            n_str = f"[{n_overall}]"
            _text(slide, x=x, y=y, w=0.45, h=0.18, text=n_str,
                  font_size=8, bold=True, color=WILEY_TEAL)
            uri = cleaned["uri"]
            if uri:
                tb = slide.shapes.add_textbox(
                    Inches(x + 0.42), Inches(y), Inches(col_w - 0.42), Inches(0.18))
                tf = tb.text_frame; tf.word_wrap = False
                try:
                    tf.margin_left = tf.margin_right = 0
                    tf.margin_top  = tf.margin_bottom = 0
                except Exception:
                    pass
                p = tf.paragraphs[0]
                run = p.add_run()
                run.text = _truncate(title + meta_suffix, 92)
                run.font.size = Pt(8)
                try:
                    run.font.color.rgb = WILEY_NAVY if isinstance(WILEY_NAVY, RGBColor) else None
                except Exception:
                    pass
                try:
                    run.hyperlink.address = uri
                except Exception:
                    pass
            else:
                _text(slide, x=x + 0.42, y=y, w=col_w - 0.42, h=0.18,
                      text=_truncate(title + meta_suffix, 92),
                      font_size=8, color=SLATE_BLACK)


def _assessment_view(topic: str, run_id: str, raw: dict) -> dict:
    """Build the ``assessment``-shaped dict the analyst-content slide
    builders consume.

    The existing helpers (``_add_strategic_recommendations_slide``,
    ``_add_key_insights_slide``, ``_add_next_steps_slide``) read from
    ``assessment.summary.{strategic_recommendations|key_insights|next_steps}``;
    we synthesize that ``summary`` object straight from
    ``forecast_run.raw_output``. The per-scenario slides do NOT go through
    this dict — they read raw scenarios directly via
    :func:`_add_forecast_scenario_slide`.
    """
    # The Three Horizons chart renderer
    # (``wiley_three_horizons_viz.collect_scenarios_for_render``) reads
    # ``assessment.scenario_verdicts`` to place title cards on the curves.
    # The per-scenario slides bypass this and read raw.scenarios directly,
    # but the chart still needs the shaped list to plot. Populate verdicts
    # with the minimal fields the renderer needs (horizon_type, title,
    # timeframe) so the chart actually shows scenarios.
    chart_verdicts: list = []
    for idx, s in enumerate(raw.get("scenarios") or []):
        if not isinstance(s, dict):
            continue
        chart_verdicts.append({
            "scenario_idx": idx,
            "scenario_title": s.get("title") or s.get("name") or f"Scenario {idx+1}",
            "horizon_type": (s.get("type") or "h1").lower(),
            "timeframe": s.get("timeframe") or "",
            "verdict_label": "Forecast",
            "top_articles": {},
        })
    return {
        "topic": topic,
        "run_id": run_id,
        "scenario_verdicts": chart_verdicts,
        "summary": {
            "topic": topic,
            # ``topic_briefing`` is what ``_add_briefing_synthesis_slide``
            # reads; the rerun prompt produces it so the slide gets fresh
            # content rather than falling back to a stale supervisor row.
            "topic_briefing": raw.get("topic_briefing") or {},
            "strategic_recommendations": raw.get("strategic_recommendations") or [],
            "key_insights": raw.get("key_insights") or [],
            "next_steps": raw.get("next_steps") or [],
            "convergences": raw.get("convergences") or [],
            "impact_timeline": raw.get("impact_timeline") or [],
            "future_signals": raw.get("future_signals") or [],
            "opportunities": raw.get("opportunities") or [],
            "disruption_scenarios": raw.get("disruption_scenarios") or [],
            "executive_decision_framework": raw.get("executive_decision_framework") or {},
        },
        "surprises": [],
        "evidence_count": 0,
    }


# ── 8-slide branded intro pack ────────────────────────────────────────
# Replaces the legacy ``app/static_assets/topic_report_intro.pptx`` template
# with dynamic slides built in the Forecast Tracker bundle's visual
# language (navy ground, pink rules, white cards, Aunoo brandmark).
# Each builder owns one slide; ``_add_branded_intro_pack`` is the
# orchestrator the deck builder calls.


def _intro_full_bleed_navy(prs, *, eyebrow: str, title: str, subtitle: str = "") -> object:
    """Common backdrop for navy intro slides — full-bleed navy + pink top
    and bottom rules + Aunoo brandmark top-right. Returns the slide so the
    caller can layer its specific content."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _rect(slide, x=0, y=0, w=sw, h=5.625, fill=WILEY_NAVY)
    _rect(slide, x=0, y=0, w=sw, h=0.08, fill=WILEY_TEAL)
    _rect(slide, x=0, y=5.55, w=sw, h=0.08, fill=WILEY_TEAL)
    _add_brand_mark(slide, x=8.9, y=0.3, w=0.7, h=0.6)
    if eyebrow:
        _text(slide, x=0.6, y=0.55, w=sw-1.2, h=0.30, text=eyebrow,
              font_size=10, bold=True, color=WILEY_TEAL)
    if title:
        _text(slide, x=0.6, y=0.85, w=sw-1.2, h=0.60, text=title,
              font_size=28, bold=True, color=WHITE)
    if subtitle:
        _text(slide, x=0.6, y=1.42, w=sw-1.2, h=0.35, text=subtitle,
              font_size=12, italic=True, color=WILEY_TEAL_LT)
    return slide


def _add_intro_cover_slide(prs, *, period_label: str):
    """Slide 1 — cover.

    Aunoo navy ground, big pink "WILEY HORIZONS · FORESIGHT" eyebrow,
    the period_label as the headline, "Topic Foresight Report"
    subtitle. Mirrors ``_add_bundle_cover`` from ``forecast_bundle_pptx``.
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _rect(slide, x=0, y=0, w=sw, h=5.625, fill=WILEY_NAVY)
    _rect(slide, x=0, y=0, w=sw, h=0.08, fill=WILEY_TEAL)
    _rect(slide, x=0, y=5.55, w=sw, h=0.08, fill=WILEY_TEAL)
    _text(slide, x=0.6, y=1.6, w=sw-1.2, h=0.40,
          text="WILEY HORIZONS · FORESIGHT",
          font_size=13, bold=True, color=WILEY_TEAL)
    _text(slide, x=0.6, y=2.10, w=sw-1.2, h=1.05, text=period_label,
          font_size=48, bold=True, color=WHITE)
    _text(slide, x=0.6, y=3.20, w=sw-1.2, h=0.40,
          text="Topic Foresight Report",
          font_size=18, italic=True, color=WILEY_TEAL_LT)
    _text(slide, x=0.6, y=4.4, w=sw-1.2, h=0.3,
          text="Produced by AunooAI · Contains AI-generated content",
          font_size=11, bold=True, color=WILEY_TEAL_LT, align=PP_ALIGN.CENTER)
    _add_brand_mark(slide, x=8.9, y=0.3, w=0.7, h=0.6)


def _add_intro_platform_slide(prs):
    """Slide 2 — what AunooAI is."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="| WE WATCH THE NEWS FOR YOU",
        title="An open strategic intelligence platform",
        subtitle="Continuous collection. Hybrid AI enrichment. Structured foresight.",
    )
    sw = 10.0
    # Body paragraph card
    _rect(slide, x=0.6, y=2.10, w=sw-1.2, h=2.75, fill=WILEY_CARD_BG)
    _rect(slide, x=0.6, y=2.10, w=sw-1.2, h=0.05, fill=WILEY_TEAL)
    body = (
        "AunooAI continuously collects, classifies and synthesises open-"
        "source information to produce structured foresight analyses for "
        "scientific publishers.\n\n"
        "The system combines automated multi-source collection with hybrid "
        "machine-learning and large-language-model enrichment, enabling "
        "analysts to move from raw information to actionable strategic "
        "insight."
    )
    _text(slide, x=0.95, y=2.35, w=sw-1.9, h=2.45, text=body,
          font_size=13, color=WILEY_BODY, line_spacing=1.45)


def _add_intro_team_slide(prs):
    """Slide 3 — analyst & data science team. Two-column card layout."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="THE TEAM",
        title="Analyst & Data Science Team",
        subtitle="Expert human oversight on every output.",
    )
    sw = 10.0
    members = [
        {
            "name": "Oliver Rochford",
            "role": "Lead Analyst · Strategic Advisor",
            "rows": [
                ("ADVISORY",
                 "n8n · Arcanna AI · Picus Security · Spektrum Security · Tesseract Analytics"),
                ("PAST ROLES",
                 "Research Director: Gartner, Securonix, Tenable · Cybersecurity Leadership: HP, Verizon"),
                ("SELECT PUBLICATIONS",
                 "Magic Quadrant SIEM (Gartner 2014-2017) · Innovation Tech Insight for SOAR (defined the SOAR category) · Quantifying the Attacker's First-Mover Advantage"),
                ("CITATIONS", "266 Google Scholar citations"),
            ],
        },
        {
            "name": "Dr. Lamine M. Aouad",
            "role": "Lead Data Scientist · Researcher & Academic",
            "rows": [
                ("CREDENTIALS",
                 "PhD, Computer Science — University of Lille 1 · Distributed Computing & Numerical Analysis"),
                ("PAST ROLES",
                 "Visiting Fellow, Marie Curie Institute Paris · Principal Researcher, Tenable · Principal Research Engineer, Symantec"),
                ("SELECT PUBLICATIONS",
                 "Quantifying the Attacker's First-Mover Advantage · Towards Improving Privacy of Synthetic DataSets · Distributed Apriori-like Frequent Itemsets Mining"),
                ("CITATIONS", "406 Google Scholar citations"),
            ],
        },
    ]
    cols_x = [0.6, 5.20]
    col_w = 4.20
    for col, m in zip(cols_x, members):
        _rect(slide, x=col, y=2.0, w=col_w, h=3.45, fill=WILEY_CARD_BG)
        _rect(slide, x=col, y=2.0, w=col_w, h=0.55, fill=WILEY_TEAL)
        _text(slide, x=col+0.18, y=2.08, w=col_w-0.36, h=0.30,
              text=m["name"], font_size=14, bold=True, color=WHITE)
        _text(slide, x=col+0.18, y=2.32, w=col_w-0.36, h=0.22,
              text=m["role"], font_size=9, italic=True, color=WILEY_TEAL_LT)
        y = 2.70
        for label, body in m["rows"]:
            _text(slide, x=col+0.20, y=y, w=col_w-0.40, h=0.20,
                  text=label, font_size=8, bold=True, color=WILEY_TEAL)
            _text(slide, x=col+0.20, y=y+0.22, w=col_w-0.40, h=0.40,
                  text=body, font_size=8.5, color=WILEY_BODY, line_spacing=1.25)
            y += 0.66


def _add_intro_human_ai_slide(prs):
    """Slide 4 — Why Human-AI Teaming Matters. Two-side comparison."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="METHODOLOGY",
        title="Why Human-AI Teaming Matters",
        subtitle="Grounded AI foresight guided by expert judgement.",
    )
    sw = 10.0
    panels = [
        {
            "header_bg": WILEY_NAVY,
            "title": "The Problem with AI Alone",
            "sub": "Why unassisted AI intelligence fails in practice.",
            "rows": [
                ("NO FORESIGHT FRAMEWORK",
                 "Generic LLMs summarise the past. Without embedded foresight structures, every prediction is word-pattern extrapolation."),
                ("NO CONTEXT MODEL",
                 "Without a domain ontology, AI confuses noise for novelty — the illusion of insight with no grounding."),
                ("NO FEEDBACK LOOP",
                 "Without continuous analyst validation, models drift, lose precision, and amplify bias."),
            ],
        },
        {
            "header_bg": WILEY_TEAL,
            "title": "The Aunoo Human-AI Retainer",
            "sub": "Grounded AI · Expert oversight · Continuous improvement.",
            "rows": [
                ("GROUNDED AI",
                 "LLMs guided by ontology-tagged, curated data. AI works from trusted signal — not raw internet noise."),
                ("FRACTIONAL ANALYST ON DEMAND",
                 "Expert analysts curate intelligence, validate insights, and challenge assumptions — your forward observer always on call."),
                ("SELF-LEARNING TOPIC MODELS",
                 "Analysts tune relevance scoring and refine scenario drivers so the system learns continuously."),
            ],
        },
    ]
    cols_x = [0.6, 5.20]
    col_w = 4.20
    for col, p in zip(cols_x, panels):
        _rect(slide, x=col, y=2.0, w=col_w, h=3.45, fill=WILEY_CARD_BG)
        _rect(slide, x=col, y=2.0, w=col_w, h=0.55, fill=p["header_bg"])
        _text(slide, x=col+0.18, y=2.08, w=col_w-0.36, h=0.30,
              text=p["title"], font_size=13.5, bold=True, color=WHITE)
        _text(slide, x=col+0.18, y=2.32, w=col_w-0.36, h=0.22,
              text=p["sub"], font_size=9, italic=True, color=WILEY_TEAL_LT)
        y = 2.70
        for label, body in p["rows"]:
            _text(slide, x=col+0.20, y=y, w=col_w-0.40, h=0.22,
                  text=label, font_size=9, bold=True, color=p["header_bg"])
            _text(slide, x=col+0.20, y=y+0.24, w=col_w-0.40, h=0.55,
                  text=body, font_size=9, color=WILEY_BODY, line_spacing=1.30)
            y += 0.86


def _add_intro_pipeline_slide(prs):
    """Slide 5 — How We Build the Intelligence. 3-step pipeline cards."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="PIPELINE",
        title="How We Build the Intelligence",
        subtitle="From raw information to enriched, analyst-ready signal.",
    )
    sw = 10.0
    steps = [
        ("01", "COLLECT",
         "Continuous gathering from 7 curated source types — mainstream news, pre-print and peer-reviewed research, and expert social commentary — across every relevant language and geography.",
         "Deduplicated · Scheduled · Configurable per topic"),
        ("02", "ENRICH",
         "Every article scored on 8 analytical dimensions: relevance, sentiment, time-to-impact, driver type, forward signal, source credibility, factuality, and thematic category.",
         "AI classifier + LLM adjudication · Confidence-scored"),
        ("03", "CONTEXTUALISE",
         "All outputs filtered through your organisational profile — your priorities, risk appetite, competitive landscape, and sector — so analysis speaks directly to Wiley's strategic position.",
         "Framed for scientific publishing · Org-profile aware"),
    ]
    card_w = 2.95
    gap = 0.10
    start_x = (sw - (3 * card_w + 2 * gap)) / 2
    card_y, card_h = 2.0, 3.40
    for i, (num, label, body, foot) in enumerate(steps):
        x = start_x + i * (card_w + gap)
        _rect(slide, x=x, y=card_y, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=x, y=card_y, w=card_w, h=0.65, fill=WILEY_TEAL)
        _text(slide, x=x+0.18, y=card_y+0.07, w=0.7, h=0.50,
              text=num, font_size=22, bold=True, color=WHITE)
        _text(slide, x=x+0.95, y=card_y+0.18, w=card_w-1.1, h=0.34,
              text=label, font_size=13, bold=True, color=WHITE)
        _text(slide, x=x+0.20, y=card_y+0.85, w=card_w-0.40, h=2.0,
              text=body, font_size=9.5, color=WILEY_BODY, line_spacing=1.35)
        _text(slide, x=x+0.20, y=card_y+card_h-0.40, w=card_w-0.40, h=0.30,
              text=foot, font_size=8, italic=True, color=WILEY_MUTED)


def _add_intro_lenses_slide(prs):
    """Slide 6 — How We Produce the Analysis. 5 lenses + deliverables."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="ANALYSIS",
        title="How We Produce the Analysis",
        subtitle="Five analytical lenses · One coherent foresight view.",
    )
    sw = 10.0
    lenses = [
        ("1", "CONSENSUS",  "What do most credible sources agree on?"),
        ("2", "STRATEGIC",  "What are the most important long-term implications?"),
        ("3", "SIGNALS",    "What is changing right now?"),
        ("4", "TIMELINE",   "How is this situation evolving over time?"),
        ("5", "HORIZONS",   "What futures are becoming possible?"),
    ]
    # Top row: 5 lens chips
    chip_w = (sw - 1.2 - 4 * 0.10) / 5
    chip_y, chip_h = 2.05, 1.20
    for i, (num, lab, q) in enumerate(lenses):
        x = 0.6 + i * (chip_w + 0.10)
        _rect(slide, x=x, y=chip_y, w=chip_w, h=chip_h, fill=WILEY_CARD_BG)
        _rect(slide, x=x, y=chip_y, w=chip_w, h=0.05, fill=WILEY_TEAL)
        _text(slide, x=x+0.10, y=chip_y+0.12, w=0.6, h=0.30,
              text=num, font_size=18, bold=True, color=WILEY_TEAL)
        _text(slide, x=x+0.65, y=chip_y+0.17, w=chip_w-0.75, h=0.30,
              text=lab, font_size=11, bold=True, color=WILEY_NAVY)
        _text(slide, x=x+0.10, y=chip_y+0.55, w=chip_w-0.20, h=0.60,
              text=q, font_size=8.5, color=WILEY_BODY, line_spacing=1.25)

    # What You Receive (4 deliverables)
    _text(slide, x=0.6, y=3.55, w=sw-1.2, h=0.28,
          text="WHAT YOU RECEIVE",
          font_size=10, bold=True, color=WILEY_TEAL)
    deliv = [
        ("Trend Synthesis",
         "Convergent signals from high-credibility sources, framed for strategic planning"),
        ("Early Warning",
         "Weak signals and outlier developments before they enter mainstream consensus"),
        ("Emerging Topics",
         "Automatically detected new themes with velocity and novelty scoring"),
        ("Cited Evidence",
         "Every claim traceable to source articles with credibility and bias ratings"),
    ]
    dw = (sw - 1.2 - 3 * 0.10) / 4
    dy, dh = 3.95, 1.40
    for i, (label, body) in enumerate(deliv):
        x = 0.6 + i * (dw + 0.10)
        _rect(slide, x=x, y=dy, w=dw, h=dh, fill=WILEY_CARD_BG)
        _text(slide, x=x+0.15, y=dy+0.12, w=dw-0.30, h=0.30,
              text=label, font_size=11.5, bold=True, color=WILEY_NAVY)
        _text(slide, x=x+0.15, y=dy+0.42, w=dw-0.30, h=dh-0.50,
              text=body, font_size=9, color=WILEY_BODY, line_spacing=1.30)


def _add_intro_calibration_slide(prs):
    """Slide 7 — How Analysis Is Calibrated to Wiley. 3-system breakdown."""
    slide = _intro_full_bleed_navy(
        prs, eyebrow="CALIBRATION",
        title="How Analysis Is Calibrated to Wiley",
        subtitle="Domain-specific · Evidence-based · Relevant to a scientific publisher.",
    )
    sw = 10.0
    systems = [
        ("Organisational Profile",
         "Who is this analysis for?",
         ["Industry & org type",
          "Key concerns & strategic priorities",
          "Risk tolerance & innovation appetite",
          "Decision-making style",
          "Competitive landscape",
          "Regulatory environment"],
         "Frames recommendations in terms of actions Wiley can actually take."),
        ("Topic Ontologies",
         "What vocabulary does this domain use?",
         ["Domain-specific categories",
          "Future signal types",
          "Sentiment framing",
          "Time-to-impact horizons",
          "Driver types"],
         "Each topic has its own classification structure — not a generic tag system."),
        ("Analysis Prompts",
         "How are they combined?",
         ["Versioned, lens-specific templates",
          "Ontology values injected as constraints",
          "Org profile injected as framing",
          "Article corpus with metadata",
          "Consistency controls (0.0–0.7)"],
         "Same evidence base, different profiles → fundamentally different outputs."),
    ]
    card_w = 2.95
    gap = 0.10
    start_x = (sw - (3 * card_w + 2 * gap)) / 2
    card_y, card_h = 2.0, 3.30
    for i, (title_, q, bullets, foot) in enumerate(systems):
        x = start_x + i * (card_w + gap)
        _rect(slide, x=x, y=card_y, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=x, y=card_y, w=card_w, h=0.65, fill=WILEY_TEAL if i % 2 == 0 else WILEY_NAVY)
        _text(slide, x=x+0.18, y=card_y+0.10, w=card_w-0.36, h=0.30,
              text=title_, font_size=13, bold=True, color=WHITE)
        _text(slide, x=x+0.18, y=card_y+0.36, w=card_w-0.36, h=0.22,
              text=q, font_size=9, italic=True, color=WILEY_TEAL_LT)
        y = card_y + 0.80
        for b in bullets:
            _rect(slide, x=x+0.22, y=y+0.10, w=0.07, h=0.07, fill=WILEY_TEAL)
            _text(slide, x=x+0.36, y=y, w=card_w-0.55, h=0.28,
                  text=b, font_size=9, color=WILEY_BODY, line_spacing=1.20)
            y += 0.30
        _text(slide, x=x+0.20, y=card_y+card_h-0.55, w=card_w-0.40, h=0.50,
              text=foot, font_size=8.5, italic=True, color=WILEY_MUTED,
              line_spacing=1.25)


def _add_intro_monitor_slide(prs, db=None):
    """Slide 8 — What We Monitor. Topic universe with article counts.

    Pulled live from ``forecast_topic_metadata`` joined to article counts
    when ``db`` is supplied; falls back to a static analyst-supplied list
    when the DB query fails. Showing real coverage matters more than
    static copy — different tenants have different scopes.
    """
    rows: list = []
    if db is not None:
        try:
            from sqlalchemy import text as sa_text
            res = db.facade._execute_with_rollback(sa_text("""
                SELECT a.topic, COUNT(*) AS articles
                FROM articles a
                WHERE a.topic IS NOT NULL AND a.topic <> ''
                GROUP BY a.topic
                ORDER BY articles DESC
                LIMIT 18
            """)).fetchall()
            for r in res:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                rows.append((rd["topic"], int(rd["articles"])))
        except Exception as e:
            logger.warning("intro monitor: topic-count query failed: %s", e)
    total = sum(c for _, c in rows)

    slide = _intro_full_bleed_navy(
        prs, eyebrow="COVERAGE",
        title="What We Monitor",
        subtitle=(f"{len(rows)} topics  ·  {total:,} articles analysed"
                  if rows else "Continuous topic coverage."),
    )
    if not rows:
        return
    sw = 10.0
    # 3-column grid
    cols = 3
    n_per_col = (len(rows) + cols - 1) // cols
    col_w = (sw - 1.2 - 2 * 0.20) / cols
    col_x = [0.6 + i * (col_w + 0.20) for i in range(cols)]
    grid_y = 2.05
    row_h = 0.36
    for idx, (topic, n) in enumerate(rows[: cols * n_per_col]):
        c = idx // n_per_col
        r = idx % n_per_col
        x = col_x[c]
        y = grid_y + r * row_h
        # Row card
        _rect(slide, x=x, y=y, w=col_w, h=row_h - 0.04, fill=WILEY_CARD_BG)
        _rect(slide, x=x, y=y, w=0.06, h=row_h - 0.04, fill=WILEY_TEAL)
        _text(slide, x=x+0.18, y=y+0.05, w=col_w-1.0, h=row_h-0.14,
              text=_truncate(topic, 38),
              font_size=9, bold=True, color=WILEY_BODY, line_spacing=1.15)
        # Count chip
        def _fmt(n):
            if n >= 10000:
                return f"{n/1000:.0f}k"
            if n >= 1000:
                return f"{n/1000:.1f}k"
            return str(n)
        _text(slide, x=x+col_w-0.85, y=y+0.05, w=0.80, h=row_h-0.14,
              text=_fmt(n), font_size=10, bold=True,
              color=WILEY_TEAL, align=PP_ALIGN.RIGHT)


def _add_branded_intro_pack(prs, *, period_label: str):
    """Emit the 8-slide branded intro pack at the head of the deck.

    Replaces the legacy static intro template. Each slide is built in the
    Forecast Tracker bundle's visual language (Wiley navy / pink rules /
    white cards / Aunoo brandmark) so the deck reads as one continuous
    deliverable rather than the static template stitched on top of
    dynamic content.
    """
    from app.database import get_database_instance
    db = None
    try:
        db = get_database_instance()
    except Exception:
        pass

    _add_intro_cover_slide(prs, period_label=period_label)
    _add_intro_platform_slide(prs)
    _add_intro_team_slide(prs)
    _add_intro_human_ai_slide(prs)
    _add_intro_pipeline_slide(prs)
    _add_intro_lenses_slide(prs)
    _add_intro_calibration_slide(prs)
    _add_intro_monitor_slide(prs, db=db)


def _add_forecast_scenario_slide(prs, scenario: dict, *, topic: Optional[str] = None,
                                 articles: Optional[list] = None):
    """Forward-looking per-scenario card — renders the forecast scenario
    itself, NOT a back-test of it.

    Mirrors the reference deck (`Wiley Horizons Final (2).pptx` slides
    50-54, 64-68, 95-99, 124-127): horizon left rail, title + timeframe,
    description body, three bottom cards.

    The bottom row degrades gracefully:
      - if the forecast carries ``primary_signal``, ``decision_fork`` and
        ``action_window`` (richer Future Horizons output), show those
        three cards
      - otherwise show **Timeframe**, **Sentiment**, **Horizon meaning**
        (three fields we always have from raw_output)

    Crucially: no "NEW EVIDENCE SINCE FORECAST", no "COUNTER-EVIDENCE",
    no "READ" calibration. Those belong to the back-test bundle, not a
    forward-looking forecast deck.
    """
    if not isinstance(scenario, dict):
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    horizon = (scenario.get("type") or "h1").lower()
    accent = _horizon_color(horizon)
    title = (scenario.get("title") or scenario.get("name") or "—").strip()
    description = (scenario.get("description") or "").strip()
    timeframe = (scenario.get("timeframe") or "").strip()
    sentiment = (scenario.get("sentiment") or "").strip()

    # Left rail — horizon chip + topic anchor. ``consensus_pct=None`` keeps
    # the (correctly-suppressed) consensus stamp out of forecast slides.
    _add_left_rail(slide, horizon=horizon, consensus_pct=None, topic=topic)

    # ── Title block ───────────────────────────────────────────────────
    title_lines = _split_title(title, max_chars=42)
    _text(slide, x=1.9, y=0.18, w=7.9, h=0.45, text=title_lines[0],
          font_size=18, bold=True, color=SLATE_DARK)
    if len(title_lines) > 1:
        _text(slide, x=1.9, y=0.60, w=7.9, h=0.45, text=title_lines[1],
              font_size=18, bold=True, color=SLATE_DARK)
        sub_y = 1.05
    else:
        sub_y = 0.66
    # Horizon descriptor right beneath the title (e.g. "H1 — Declining
    # System") so the reader has the framework label in view.
    _text(slide, x=1.9, y=sub_y, w=7.9, h=0.22,
          text=_horizon_full_label(horizon),
          font_size=9, bold=True, color=accent)

    # Timeframe chip — small caps to mirror the reference deck.
    if timeframe:
        _text(slide, x=1.9, y=sub_y + 0.26, w=7.9, h=0.22,
              text=f"TIMEFRAME  ·  {timeframe}",
              font_size=8.5, bold=True, color=SLATE_LIGHT)

    # ── Description body ──────────────────────────────────────────────
    if description:
        _text_cites(slide, x=1.9, y=1.75, w=7.9, h=2.15,
                    text=description, articles=articles,
                    font_size=11, color=SLATE_BLACK, line_spacing=1.30)

    # ── Bottom row: 3 plates ──────────────────────────────────────────
    # Prefer rich forecast fields when present; fall back to fields we
    # always have. Order: left → middle → right.
    primary_signal = (scenario.get("primary_signal") or "").strip()
    decision_fork  = scenario.get("decision_fork") or {}
    action_window  = (scenario.get("action_window") or scenario.get("timeframe") or "").strip()
    if isinstance(decision_fork, dict):
        fork_act   = (decision_fork.get("act") or "").strip()
        fork_defer = (decision_fork.get("defer") or decision_fork.get("delay") or "").strip()
    else:
        fork_act = fork_defer = ""

    plate_y, plate_h, plate_w = 4.20, 1.18, 2.55
    gap = 0.10
    x_left   = 1.90
    x_middle = x_left + plate_w + gap
    x_right  = x_middle + plate_w + gap

    def _plate(x: float, label: str, body: str, *, body_lines: int = 3,
               accent_color = accent):
        """White card with thin top accent + label + body."""
        _rect(slide, x=x, y=plate_y, w=plate_w, h=plate_h, fill=WHITE)
        _rect(slide, x=x, y=plate_y, w=plate_w, h=0.05, fill=accent_color)
        _text(slide, x=x + 0.15, y=plate_y + 0.12, w=plate_w - 0.30, h=0.22,
              text=label, font_size=8, bold=True, color=accent_color)
        if body:
            _text(slide, x=x + 0.15, y=plate_y + 0.38, w=plate_w - 0.30,
                  h=plate_h - 0.46,
                  text=body, font_size=9.5, color=SLATE_BLACK,
                  line_spacing=1.25)

    # LEFT plate — Primary signal (preferred) or Sentiment.
    if primary_signal:
        _plate(x_left, "PRIMARY SIGNAL", _truncate(primary_signal, 180))
    elif sentiment:
        _plate(x_left, "SENTIMENT", sentiment)
    else:
        _plate(x_left, "HORIZON", _horizon_label(horizon).replace("\n", " / "))

    # MIDDLE plate — Decision fork (preferred) or Horizon meaning.
    if fork_act or fork_defer:
        body_parts = []
        if fork_act:
            body_parts.append(f"✔ {_truncate(fork_act, 90)}")
        if fork_defer:
            body_parts.append(f"! {_truncate(fork_defer, 90)}")
        _plate(x_middle, "DECISION FORK", "\n".join(body_parts))
    else:
        _plate(x_middle, "HORIZON CLASS",
               _horizon_full_label(horizon).split(" — ", 1)[-1]
               if "—" in _horizon_full_label(horizon)
               else _horizon_full_label(horizon))

    # RIGHT plate — Action window (preferred) or Timeframe.
    if action_window:
        _plate(x_right, "ACTION WINDOW", action_window)
    elif timeframe:
        _plate(x_right, "TIMEFRAME", timeframe)
    else:
        _plate(x_right, "—", "")

    # Bottom rule for grounding. No brand-footer call — the left rail
    # already carries the AunooAI mark, and ``_add_brand_footer`` hardcodes
    # the "Forecast Tracker" label which is the wrong product for this deck.
    _rect(slide, x=1.9, y=plate_y + plate_h + 0.04, w=7.9, h=0.012,
          fill=RULE_GRAY)


def _add_key_insights_pure_slide(prs, assessment: dict, *, topic: str,
                                 topic_idx: Optional[int] = None,
                                 articles: Optional[list] = None):
    """Forecast-only Key Insights slide.

    The existing ``_add_key_insights_slide`` from forecast_pptx_export.py is
    written for the back-test bundle — it derives insights from
    scenario_verdicts + baseline_correction + surprises. For a Topic Report
    we want the forecast's own ``key_insights`` list (the prompt asks for
    4-5 strings), rendered as a clean bullet stack.

    Skips silently when fewer than 2 insights are present.
    """
    insights = ((assessment.get("summary") or {}).get("key_insights")) or []
    insights = [s for s in insights if isinstance(s, str) and s.strip()]
    if len(insights) < 2:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    eyebrow = (f"TOPIC {topic_idx} · KEY INSIGHTS" if topic_idx is not None
               else "KEY INSIGHTS")
    _text(slide, x=0.6, y=0.30, w=sw-1.2, h=0.28,
          text=eyebrow, font_size=10, bold=True, color=SLATE_MID)
    _text(slide, x=0.6, y=0.58, w=sw-1.2, h=0.50,
          text=topic, font_size=24, bold=True, color=SLATE_DARK)
    _text(slide, x=0.6, y=1.10, w=sw-1.2, h=0.30,
          text="Cross-source observations grounded in the analysed article set.",
          font_size=10.5, italic=True, color=SLATE_MID)

    # Bullet stack — each insight gets a pink leader dot + body
    y = 1.65
    row_h = (5.30 - y) / max(1, len(insights[:6]))
    for s in insights[:6]:
        _rect(slide, x=0.7, y=y + 0.18, w=0.10, h=0.10,
              fill=_horizon_color("h2"))
        _text_cites(slide, x=0.92, y=y + 0.04, w=sw - 1.5, h=row_h - 0.10,
                    text=_truncate(s, 350), articles=articles,
                    font_size=12, color=SLATE_BLACK, line_spacing=1.35)
        _rect(slide, x=0.7, y=y + row_h - 0.05, w=sw - 1.4, h=0.008,
              fill=RULE_GRAY)
        y += row_h


def _add_horizon_divider(prs, horizon: str, scenarios_in_horizon: list,
                         *, topic: str):
    """Section break between H1 → H2 → H3 horizons.

    Big horizon letter, full descriptor, and the list of scenario titles
    that follow. Reuses the left-rail visual language so the deck reads
    continuously into the per-scenario slides that come next.
    """
    if not scenarios_in_horizon:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    accent = _horizon_color(horizon)
    h_code = (horizon or "").upper()
    h_desc = _horizon_full_label(horizon)

    # Eyebrow + big H-code. ``font_size=180`` was rendering "H1"/"H2"/"H3"
    # ~3.5in wide and bleeding past the box; 110pt is the largest size
    # the 2-char H-code reliably fits within the left column without
    # overlapping the descriptor at x=3.4.
    _text(slide, x=0.7, y=0.45, w=sw-1.4, h=0.30,
          text=topic.upper(), font_size=10, bold=True, color=accent)
    _text(slide, x=0.5, y=0.95, w=2.8, h=1.9, text=h_code,
          font_size=110, bold=True, color=accent, align=PP_ALIGN.LEFT)
    _text(slide, x=3.4, y=1.50, w=sw-4.0, h=0.6, text=h_desc,
          font_size=26, bold=True, color=SLATE_DARK)
    _text(slide, x=3.4, y=2.10, w=sw-4.0, h=0.4,
          text=f"{len(scenarios_in_horizon)} scenario{'s' if len(scenarios_in_horizon)!=1 else ''} in this horizon",
          font_size=12, italic=True, color=SLATE_MID)

    # Scenario titles list
    _text(slide, x=0.7, y=3.30, w=sw-1.4, h=0.25, text="WHAT FOLLOWS",
          font_size=9, bold=True, color=accent)
    y = 3.58
    for idx, s in enumerate(scenarios_in_horizon, 1):
        title = (s.get("title") or s.get("name") or "—").strip()
        # Bullet + title
        _rect(slide, x=0.7, y=y+0.08, w=0.08, h=0.18, fill=accent)
        _text(slide, x=0.92, y=y, w=sw-1.6, h=0.32,
              text=f"{idx}.  {_truncate(title, 110)}",
              font_size=11, color=SLATE_BLACK)
        y += 0.36
        if y > 5.15:
            break


def _add_analysis_metadata_slide(prs, raw: dict, *, topic: str,
                                 topic_idx: Optional[int] = None):
    """Per-topic "About this analysis" slide.

    Renders the forecast-run metadata so the reader knows what model
    produced this view, against how many articles, for what persona, and
    when. Honest provenance — every Wiley-style deliverable should carry
    one. Pulls from ``raw_output`` fields populated by the Future Horizons
    pipeline.
    """
    if not raw:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    eyebrow = f"TOPIC {topic_idx} · ABOUT THIS ANALYSIS" if topic_idx is not None \
              else "ABOUT THIS ANALYSIS"
    _text(slide, x=0.6, y=0.30, w=sw-1.2, h=0.28,
          text=eyebrow, font_size=10, bold=True, color=SLATE_MID)
    _text(slide, x=0.6, y=0.58, w=sw-1.2, h=0.50,
          text=topic, font_size=24, bold=True, color=SLATE_DARK)
    _text(slide, x=0.6, y=1.10, w=sw-1.2, h=0.30,
          text="Provenance, scope and source quality of the Future Horizons run that this deck visualises.",
          font_size=10.5, italic=True, color=SLATE_MID)

    # Build a compact 2×3 grid of "stat" plates.
    def _fmt_int(v):
        try: return f"{int(v):,}"
        except Exception: return "—"

    gen_at = (raw.get("generated_at") or "").replace("T", " ")[:16]
    stats = [
        ("ARTICLES ANALYSED", _fmt_int(raw.get("articles_analyzed"))),
        ("CORPUS SCANNED",   _fmt_int(raw.get("total_articles_found"))),
        ("MODEL",            str(raw.get("model_used") or "—")),
        ("PERSONA",          str(raw.get("persona") or "—").title()),
        ("LOOKBACK",         f"{raw.get('timeframe_days') or '—'} days"),
        ("GENERATED",        gen_at or "—"),
    ]
    px, py = 0.6, 1.75
    pw, ph, gap = (sw - 1.2 - 2 * 0.20) / 3, 1.45, 0.20
    for i, (label, value) in enumerate(stats):
        col, row = i % 3, i // 3
        x = px + col * (pw + gap)
        y = py + row * (ph + 0.30)
        _rect(slide, x=x, y=y, w=pw, h=ph, fill=WHITE)
        _rect(slide, x=x, y=y, w=pw, h=0.05, fill=_horizon_color("h2"))
        _text(slide, x=x+0.18, y=y+0.18, w=pw-0.36, h=0.28,
              text=label, font_size=8.5, bold=True, color=SLATE_MID)
        _text(slide, x=x+0.18, y=y+0.48, w=pw-0.36, h=ph-0.55,
              text=value, font_size=20, bold=True, color=SLATE_DARK,
              line_spacing=1.05)


_SENTIMENT_COLOR = {
    "positive":     (0xD1, 0xE7, 0xDD),
    "neutral":      (0xE2, 0xE3, 0xE5),
    "critical":     (0xF8, 0xD7, 0xDA),
    "negative":     (0xF8, 0xD7, 0xDA),
    "warning":      (0xFF, 0xF3, 0xCD),
    "breakthrough": (0xD1, 0xE7, 0xDD),
}


def _sentiment_chip_color(label: str):
    """Background colour for a sentiment chip — falls back to grey."""
    from pptx.dml.color import RGBColor
    key = (label or "").lower().split("/")[0].strip()
    rgb = _SENTIMENT_COLOR.get(key, (0xE2, 0xE3, 0xE5))
    return RGBColor(*rgb)


def _classify_article_sentiment(article: dict) -> str:
    """Rough sentiment label for the supporting-articles chip.

    Articles in the corpus carry a numeric ``sentiment_score`` or a
    string ``sentiment`` (model-set). Both can be missing. Pick the
    string when present, else bucket the numeric, else "neutral".
    """
    s = (article.get("sentiment") or "").strip().lower()
    if s in ("positive", "negative", "neutral", "critical", "warning",
             "breakthrough"):
        return s
    try:
        v = float(article.get("sentiment_score"))
        if v >  0.20: return "positive"
        if v < -0.20: return "negative"
    except Exception:
        pass
    return "neutral"


def _add_supporting_articles_slide(prs, articles: list, *, topic: str,
                                   topic_idx: Optional[int] = None):
    """Compact "Key Supporting Articles" slide — 5–7 articles per topic.

    Mirrors the reference deck's per-article cards but compressed onto a
    single slide. Each row: sentiment chip + title + source · date.

    Skips entirely when fewer than 3 articles to surface — avoids a
    near-empty slide.
    """
    if not articles or len(articles) < 3:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    eyebrow = (f"TOPIC {topic_idx} · KEY SUPPORTING ARTICLES"
               if topic_idx is not None else "KEY SUPPORTING ARTICLES")
    _text(slide, x=0.6, y=0.30, w=sw-1.2, h=0.28,
          text=eyebrow, font_size=10, bold=True, color=SLATE_MID)
    _text(slide, x=0.6, y=0.58, w=sw-1.2, h=0.50,
          text=topic, font_size=24, bold=True, color=SLATE_DARK)
    _text(slide, x=0.6, y=1.10, w=sw-1.2, h=0.30,
          text="Recent on-topic evidence — filtered by topic-alignment score and ordered by publication date.",
          font_size=10.5, italic=True, color=SLATE_MID)

    # Article rows
    rows = articles[:7]
    row_y = 1.65
    row_h = (5.20 - row_y) / max(1, len(rows))
    for a in rows:
        # Sentiment chip (left)
        sent = _classify_article_sentiment(a)
        chip_fill = _sentiment_chip_color(sent)
        _rect(slide, x=0.6, y=row_y + 0.08, w=0.85, h=0.30, fill=chip_fill)
        _text(slide, x=0.62, y=row_y + 0.11, w=0.81, h=0.24,
              text=sent.upper(), font_size=8, bold=True, color=SLATE_DARK,
              align=PP_ALIGN.CENTER)

        # Title
        title = a.get("title") or "—"
        _text(slide, x=1.60, y=row_y + 0.04, w=sw - 2.20, h=0.34,
              text=_truncate(title, 110),
              font_size=11, bold=True, color=SLATE_DARK,
              line_spacing=1.20)

        # Source · date
        meta_bits = [b for b in (a.get("source"), a.get("date")) if b]
        meta = "  ·  ".join(meta_bits)
        if meta:
            _text(slide, x=1.60, y=row_y + 0.38, w=sw - 2.20, h=0.22,
                  text=meta, font_size=9, italic=True, color=SLATE_LIGHT)

        # Hairline rule
        _rect(slide, x=0.6, y=row_y + row_h - 0.02, w=sw - 1.2, h=0.008,
              fill=RULE_GRAY)
        row_y += row_h


def _add_executive_summary_card_slide(prs, summary: dict, *,
                                      topic_idx: Optional[int] = None,
                                      card_idx: Optional[int] = None,
                                      total_cards: Optional[int] = None):
    """One slide per Executive Summary card from the Future Horizons tab.

    Layout mirrors ``ui/src/components/horizons/ExecutiveSummaryCard.tsx``
    so the PPTX cards read like the React UI:

      * eyebrow "TOPIC n · EXECUTIVE SUMMARY (k of N)"
      * topic_title headline
      * horizon chip on the left, consensus % pill on the right
      * opening_statement body paragraph
      * MINORITY VIEW amber callout (when populated)
      * PRIMARY SIGNAL block
      * DECISION FORK (✔ / !) on the left, YOUR WINDOW (assessment +
        positioning) on the right

    Skips silently when ``summary`` is empty/malformed.
    """
    if not isinstance(summary, dict) or not summary.get("topic_title"):
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    # Vertical budget (slide is 10.0 × 5.625):
    #   header  0.15 → 0.78   (eyebrow + topic title)
    #   chips   0.85 → 1.21   (horizon + consensus row)
    #   body    1.30 → 1.92   (opening_statement)
    #   minor.  1.97 → 2.52   (minority view, optional)
    #   signal  2.58 → 3.36   (primary signal, optional)
    #   plates  3.45 → 5.45   (decision fork + your window, 2.0" tall)

    # Header / eyebrow / topic_title
    eyebrow_bits = []
    if topic_idx is not None:
        eyebrow_bits.append(f"TOPIC {topic_idx}")
    eyebrow_bits.append("EXECUTIVE SUMMARY")
    if card_idx is not None and total_cards:
        eyebrow_bits.append(f"{card_idx} of {total_cards}")
    eyebrow = "  ·  ".join(eyebrow_bits)
    _text(slide, x=0.5, y=0.15, w=sw-1.0, h=0.20, text=eyebrow,
          font_size=9, bold=True, color=SLATE_MID)
    _text(slide, x=0.5, y=0.36, w=sw-1.0, h=0.42,
          text=_truncate(summary.get("topic_title") or "", 90),
          font_size=18, bold=True, color=SLATE_DARK)

    # Horizon chip (left) + consensus % pill (right)
    horizon = (summary.get("primary_horizon") or "h1").lower()
    accent = _horizon_color(horizon)
    horizon_label = (summary.get("horizon_label")
                     or _horizon_full_label(horizon).split("—", 1)[-1].strip())
    _rect(slide, x=0.5, y=0.85, w=2.55, h=0.36, fill=accent)
    _text(slide, x=0.5, y=0.89, w=2.55, h=0.28,
          text=f"{horizon.upper()}  ·  {horizon_label}",
          font_size=10.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    cons = summary.get("consensus_percentage")
    if isinstance(cons, (int, float)):
        _rect(slide, x=sw - 2.55 - 0.5, y=0.85, w=2.55, h=0.36, fill=WILEY_TEAL)
        _text(slide, x=sw - 2.55 - 0.5, y=0.89, w=2.55, h=0.28,
              text=f"{int(cons)}% CONSENSUS",
              font_size=10.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # Opening statement body
    opening = (summary.get("opening_statement") or "").strip()
    if opening:
        _text(slide, x=0.5, y=1.30, w=sw-1.0, h=0.62,
              text=_truncate(opening, 280),
              font_size=10.5, color=SLATE_BLACK, line_spacing=1.25)

    # Minority view callout (optional)
    mv = summary.get("minority_view") or {}
    mv_pct = (mv.get("percentage_range") or "").strip()
    mv_text = (mv.get("statement") or "").strip()
    cy = 1.97
    if mv_text:
        AMBER_FILL = WILEY_TEAL_LT
        AMBER_BAR  = WILEY_TEAL
        _rect(slide, x=0.5, y=cy, w=sw-1.0, h=0.55, fill=AMBER_FILL)
        _rect(slide, x=0.5, y=cy, w=0.10, h=0.55, fill=AMBER_BAR)
        label = "MINORITY VIEW" + (f"  ·  {mv_pct}" if mv_pct else "")
        _text(slide, x=0.70, y=cy+0.04, w=sw-1.4, h=0.22,
              text=label, font_size=8.5, bold=True, color=AMBER_BAR)
        _text(slide, x=0.70, y=cy+0.24, w=sw-1.4, h=0.30,
              text=_truncate(mv_text, 220),
              font_size=9.5, color=SLATE_BLACK, line_spacing=1.20)
        cy += 0.61

    # PRIMARY SIGNAL block (optional)
    ps = (summary.get("primary_signal") or "").strip()
    if ps:
        label = "PRIMARY SIGNAL"
        if isinstance(cons, (int, float)):
            label = f"PRIMARY SIGNAL  ·  {int(cons)}% CONSENSUS"
        _text(slide, x=0.5, y=cy, w=sw-1.0, h=0.22,
              text=label, font_size=9, bold=True, color=WILEY_TEAL)
        _text(slide, x=0.5, y=cy+0.22, w=sw-1.0, h=0.56,
              text=_truncate(ps, 240),
              font_size=10.5, bold=True, color=SLATE_DARK, line_spacing=1.25)
        cy += 0.83

    # DECISION FORK (left card) + YOUR WINDOW (right card)
    fork = summary.get("decision_fork") or {}
    fa = fork.get("condition_a") or {}
    fb = fork.get("condition_b") or {}
    aw = summary.get("action_window") or {}
    aw_assess = aw.get("assessment") or {}
    aw_pos    = aw.get("positioning") or {}

    plate_y = max(cy, 3.45)
    plate_h = 5.45 - plate_y
    plate_w = (sw - 1.0 - 0.15) / 2
    xL = 0.5
    xR = 0.5 + plate_w + 0.15

    if fa.get("condition") or fb.get("condition"):
        _rect(slide, x=xL, y=plate_y, w=plate_w, h=plate_h, fill=WILEY_CARD_BG)
        _rect(slide, x=xL, y=plate_y, w=plate_w, h=0.05, fill=WILEY_NAVY)
        _text(slide, x=xL+0.18, y=plate_y+0.12, w=plate_w-0.36, h=0.22,
              text="DECISION FORK", font_size=9, bold=True, color=WILEY_NAVY)
        fy = plate_y + 0.42
        row_h = min(0.72, (plate_h - 0.50) / 2)
        for marker, frow in (("✔", fa), ("!", fb)):
            cond = (frow.get("condition") or "").strip()
            outc = (frow.get("outcome") or "").strip()
            if not cond and not outc:
                continue
            _text(slide, x=xL+0.18, y=fy, w=plate_w-0.36, h=0.26,
                  text=f"{marker}  {_truncate(cond, 60)}",
                  font_size=9.5, bold=True, color=accent)
            _text(slide, x=xL+0.36, y=fy+0.24, w=plate_w-0.54, h=0.42,
                  text=f"→ {_truncate(outc, 140)}",
                  font_size=8.5, color=SLATE_BLACK, line_spacing=1.20)
            fy += row_h

    if aw_assess.get("action") or aw_pos.get("action"):
        _rect(slide, x=xR, y=plate_y, w=plate_w, h=plate_h, fill=WILEY_CARD_BG)
        _rect(slide, x=xR, y=plate_y, w=plate_w, h=0.05, fill=WILEY_TEAL)
        _text(slide, x=xR+0.18, y=plate_y+0.12, w=plate_w-0.36, h=0.22,
              text="YOUR WINDOW", font_size=9, bold=True, color=WILEY_TEAL)
        ay = plate_y + 0.42
        row_h = min(0.72, (plate_h - 0.50) / 2)
        for row in (aw_assess, aw_pos):
            tf = (row.get("timeframe") or "").strip()
            act = (row.get("action") or "").strip()
            if not tf and not act:
                continue
            if tf:
                _text(slide, x=xR+0.18, y=ay, w=plate_w-0.36, h=0.22,
                      text=tf.upper(), font_size=9, bold=True, color=WILEY_TEAL)
            _text(slide, x=xR+0.18, y=ay+0.20, w=plate_w-0.36, h=0.48,
                  text=_truncate(act, 140),
                  font_size=9.5, color=SLATE_BLACK, line_spacing=1.25)
            ay += row_h

    # Source scenarios footer — link this card back to the H1/H2/H3
    # scenarios the LLM clustered. Tight one-line band below the plates
    # (slide bottom is 5.625; plates end at 5.45 → 0.13" footer).
    src = [s for s in (summary.get("source_scenarios") or []) if isinstance(s, dict)]
    src_bits = []
    for s in src:
        h = (s.get("horizon") or "").upper()
        t = (s.get("title") or "").strip()
        if t:
            src_bits.append(f"{h} {t}" if h else t)
    if src_bits:
        footer = "Based on: " + "  ·  ".join(src_bits)
        _text(slide, x=0.5, y=5.48, w=sw-1.0, h=0.13,
              text=_truncate(footer, 200),
              font_size=7.5, italic=True, color=SLATE_MID)


def _load_articles_corpus(db, run_id: str, topic: str) -> list:
    """Load the numbered article corpus the LLM cited as ``[1]``, ``[2]`` …

    Returns the persisted ``future_horizon_articles`` set for the run,
    preserving the prompt-time order (= [N] mapping). Falls back to the
    canonical on-topic SELECT for older runs that don't have an fha row
    set — same query the Topic Reports rerun uses, so [N] still resolves
    to roughly the same article. Each dict: ``{title, uri, source, date}``.
    """
    out: list = []
    try:
        from sqlalchemy import text as sa_text
        sql = sa_text("""
            SELECT a.uri, a.title, a.news_source, a.publication_date
            FROM future_horizon_articles fha
            JOIN articles a ON a.uri = fha.article_uri
            WHERE fha.horizon_id = :run_id
            ORDER BY fha.id ASC
        """)
        rows = db.facade._execute_with_rollback(sql, {"run_id": run_id}).fetchall()
        for r in rows:
            d = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
            if (d.get("title") or "").strip():
                out.append({
                    "title":  d.get("title"),
                    "uri":    d.get("uri") or "",
                    "source": (d.get("news_source") or "").strip(),
                    "date":   (d.get("publication_date") or "")[:10],
                })
    except Exception as e:
        logger.warning("Topic report: fha lookup failed for %s: %s", run_id, e)

    if out:
        return out

    # Fallback: rebuild the numbered list from the same SELECT the rerun
    # uses. Best-effort — may drift if the article corpus has changed.
    try:
        from app.routes.trend_convergence_routes import calculate_optimal_sample_size
        sample_size = calculate_optimal_sample_size("gpt-5.4", sample_size_mode="auto")
        from sqlalchemy import text as sa_text
        sql = sa_text(f"""
            SELECT uri, title, news_source, publication_date
            FROM articles
            WHERE topic = :topic
              AND analyzed = TRUE
              AND topic_alignment_score IS NOT NULL
              AND topic_alignment_score > 0.7
            ORDER BY topic_alignment_score DESC, publication_date DESC
            LIMIT {int(sample_size)}
        """)
        rows = db.facade._execute_with_rollback(sql, {"topic": topic}).fetchall()
        for r in rows:
            d = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
            if (d.get("title") or "").strip():
                out.append({
                    "title":  d.get("title"),
                    "uri":    d.get("uri") or "",
                    "source": (d.get("news_source") or "").strip(),
                    "date":   (d.get("publication_date") or "")[:10],
                })
        if out:
            logger.info("Topic report: rebuilt %d-article corpus for %s from "
                        "on-topic SELECT (no fha rows persisted)", len(out), topic)
    except Exception as e:
        logger.warning("Topic report: corpus fallback rebuild failed for %s: %s",
                       topic, e)
    return out


def _load_supporting_articles(db, topic: str, limit: int = 7) -> list:
    """Top recent on-topic articles for the supporting-articles slide.

    Wraps ``get_relevant_articles_for_topic`` (per memory note —
    filters on ``topic_alignment_score``). Returns plain dicts with
    title, uri, source, date, alignment. Sorted by date desc within
    the alignment-ranked set so the slide reads as "what's been
    published recently on this topic". Returns at most ``limit``.
    """
    try:
        rows = db.facade.get_relevant_articles_for_topic(
            topic, days_back=180, min_alignment=0.7, limit=limit * 3,
        ) or []
    except Exception as e:
        logger.warning("Topic report: get_relevant_articles_for_topic(%s) failed: %s",
                       topic, e)
        return []
    out: list = []
    for r in rows:
        d = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        title = (d.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "uri": d.get("uri") or "",
            "source": (d.get("news_source") or "").strip(),
            "date": (d.get("publication_date") or "")[:10],
            "alignment": d.get("topic_alignment_score"),
        })
    # Sort by date desc among the alignment-filtered set so the slide
    # leads with the freshest evidence.
    out.sort(key=lambda a: a["date"], reverse=True)
    return out[:limit]


def _load_consensus_for_topic(db, topic: str) -> Optional[dict]:
    """Latest completed consensus_analysis_runs payload for a topic.

    Returns the parsed ``raw_output`` dict, or ``None`` when no run
    exists for the topic. The matching slide builder isn't yet wired
    (the per-topic ``_add_consensus_outlier_slide`` is still back-test-
    framed); the context field is included so a future slide builder
    can consume it without another loader change.
    """
    try:
        from sqlalchemy import text as sa_text
        row = db.facade._execute_with_rollback(sa_text("""
            SELECT raw_output FROM consensus_analysis_runs
            WHERE topic = :topic
            ORDER BY created_at DESC LIMIT 1
        """), {"topic": topic}).fetchone()
    except Exception as e:
        logger.debug("consensus_analysis_runs lookup failed for %s: %s", topic, e)
        return None
    if not row:
        return None
    raw = row._mapping["raw_output"] if hasattr(row, "_mapping") else row[0]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    return raw if isinstance(raw, dict) else None


def _load_horizons_executive_summary(db, run_id: str) -> list:
    """Pull the cached Future Horizons Executive Summary cards for a run.

    Mirrors what the React Future Horizons tab loads — the canonical
    cards (consensus % / PRIMARY SIGNAL / DECISION FORK / YOUR WINDOW /
    MINORITY VIEW) live in ``analysis_versions_v2`` keyed
    ``horizons_exec_summary_{run_id}``. The Topic Reports rerun
    populates this row right after saving the fresh horizons run, so by
    the time the deck builder asks for it, it's there.

    Returns the ``summaries`` array (one entry per card), or ``[]`` when
    nothing is cached — the deck just skips those slides.
    """
    if not run_id:
        return []
    try:
        payload = db.facade.get_horizons_executive_summary(run_id) or {}
    except Exception as e:
        logger.debug("horizons exec summary load failed for %s: %s", run_id, e)
        return []
    summaries = payload.get("summaries") or []
    return summaries if isinstance(summaries, list) else []


def _load_eos_scenarios(db, topic: str) -> list:
    """Latest saved Extreme Outlier scenarios (Black Swans/Wildcards) for
    a topic. Read-only — never triggers generation.

    Returns a list of scenario dicts (or empty list when no recent scan).
    The 180-day window matches the bundle's read-only acceptance threshold.
    """
    try:
        row = db.facade.get_latest_saved_eos_for_topic(topic, max_age_days=180) or {}
    except Exception as e:
        logger.debug("saved_eos lookup failed for %s: %s", topic, e)
        return []
    scenarios = row.get("scenarios") or []
    return scenarios if isinstance(scenarios, list) else []


def resolve_items(topics: list[str]) -> list:
    """Resolve ``(assessment_view, forecast_run, None)`` triples for an
    explicit topic list. Each topic must have a stored future_horizons_runs
    row; topics without one are skipped.

    The ``assessment_view`` carries the FULL per-topic context that the
    deck builder walks: forecast raw_output (always), the latest
    ``forecast_assessments`` summary (for briefing / recs / next-steps
    slides when the supervisor has populated them), saved EOS scenarios
    (Black Swans), consensus analysis output, and the top supporting
    articles. Loaders are read-only and silently leave the corresponding
    field empty when nothing exists.
    """
    from sqlalchemy import text as sa_text
    from app.database import get_database_instance
    from app.services.wiley_delivery_service import _apply_overlay_display_names

    db = get_database_instance()
    items: list = []
    for topic in topics:
        topic = (topic or "").strip()
        if not topic:
            continue
        row = db.facade._execute_with_rollback(sa_text("""
            SELECT id FROM future_horizons_runs
            WHERE topic = :topic ORDER BY created_at DESC LIMIT 1
        """), {"topic": topic}).fetchone()
        if not row:
            logger.info("Topic report: skipping %s — no forecast run", topic)
            continue
        run_id = (row._mapping["id"] if hasattr(row, "_mapping") else row[0])
        forecast_run = db.facade.get_future_horizons_analysis(run_id) or {}
        raw = _decode_raw_output(forecast_run)

        # Pull the actual assessment row when present — its ``summary``
        # is where the supervisor pipeline writes briefing / strategic
        # recommendations / next steps, which the per-topic slide
        # builders read from. The forecast itself only populates these
        # for some topics; the assessment may have them for more.
        stored_assessment = None
        try:
            stored_assessment = db.facade.get_latest_forecast_assessment_by_topic(topic)
        except Exception as e:
            logger.debug("get_latest_forecast_assessment_by_topic(%s) failed: %s",
                         topic, e)

        assessment = _assessment_view(topic, run_id, raw)
        # Fresh-forecast values WIN over the stored supervisor summary.
        # The supervisor's stored summary fills gaps only — that way a
        # re-run via gpt-5.4 actually replaces stale text on the briefing /
        # strategic-recs / next-steps slides instead of the user seeing
        # the supervisor's old content from a prior run.
        stored_summary = (stored_assessment or {}).get("summary") or {}
        if stored_summary:
            merged_summary = dict(assessment["summary"])
            for k, v in stored_summary.items():
                if v in (None, [], {}, ""):
                    continue
                cur = merged_summary.get(k)
                if cur in (None, [], {}, ""):
                    merged_summary[k] = v
            assessment["summary"] = merged_summary
        # Carry the assessment's own surprises through too so the
        # Surprise Clusters slides can render when the supervisor has
        # tagged emerging themes.
        assessment["surprises"] = (stored_assessment or {}).get("surprises") or []

        # Per-topic context — the deck builder walks these.
        assessment["_eos_scenarios"]       = _load_eos_scenarios(db, topic)
        assessment["_consensus_payload"]   = _load_consensus_for_topic(db, topic)
        assessment["_supporting_articles"] = _load_supporting_articles(db, topic)
        assessment["_exec_summary_cards"]  = _load_horizons_executive_summary(db, run_id)
        # The numbered corpus the LLM cited (``[1]``, ``[2]`` … markers in
        # scenario / insight / rec body text resolve here). Per-topic
        # builders attach hyperlinks to each [N] run targeting the matching
        # article URL.
        assessment["_articles_corpus"]     = _load_articles_corpus(db, run_id, topic)

        items.append((assessment, forecast_run, None))
    return _apply_overlay_display_names(items)


def build_topic_report_pptx(
    items: list,
    *,
    period_label: str,
    template_path: Optional[str] = None,
) -> bytes:
    """Render the topic report PPTX.

    Parameters
    ----------
    items
        List of ``(assessment_view, forecast_run, None)`` triples from
        :func:`resolve_items`.
    period_label
        Free-form label shown on the cover (e.g. ``"Q3 2026"``).
    template_path
        Optional path to a static PPTX template to use as the deck base.
        When None (default) the deck is built from scratch and the
        branded 8-slide intro pack (cover / platform / team / methodology
        / pipeline / lenses / calibration / coverage) is emitted in the
        same Wiley navy + pink language as the Forecast Tracker bundle.
        Pass a path to fall back to the legacy static intro template.
    """
    if template_path and os.path.exists(template_path):
        prs = Presentation(template_path)
        intro_in_template = True
    else:
        prs = Presentation()
        intro_in_template = False
    prs.slide_width = Inches(10.0)
    prs.slide_height = Inches(5.625)

    topics = [(a.get("topic") or "—") for (a, _r, _p) in items]

    # Branded intro pack (slides 1-8) when no static template was supplied.
    # Otherwise the template's own slides are already in place.
    if not intro_in_template:
        _add_branded_intro_pack(prs, period_label=period_label)

    _add_bundle_cover(prs, period_label, "topic_report", topics, updates_only=False)
    if len(items) >= 2:
        _add_three_horizons_overview(prs, items, updates_only=False)

    for topic_idx, (assessment, forecast_run, _prior) in enumerate(items, 1):
        topic_name = assessment.get("topic") or "—"
        raw = _decode_raw_output(forecast_run or {})
        # Numbered corpus the LLM cited as ``[N]``. Threaded through the
        # body-text slide builders so each [N] gets a hyperlink to the
        # matching article URL — and rendered at the end of the topic
        # section as a full numbered references slide.
        articles_corpus = assessment.get("_articles_corpus") or []

        # ── Section openers (always rendered) ──────────────────────────
        _add_topic_divider(prs, assessment, forecast_run or {}, topic_idx=topic_idx)
        _add_analysis_metadata_slide(prs, raw, topic=topic_name, topic_idx=topic_idx)
        _add_topic_three_horizons_chart(prs, assessment, forecast_run or {}, topic_idx=topic_idx)

        # ── Analyst content (each helper returns silently when its data
        # source is empty, so the deck only carries slides we can fill).
        # ``_add_briefing_synthesis_slide`` reads ``summary.topic_briefing``,
        # which the supervisor pipeline populates per topic when bundles
        # have been generated; otherwise it short-circuits.
        _add_briefing_synthesis_slide(prs, assessment, topic_idx=topic_idx)

        # ── Executive Summary cards — the high-value cards the React
        # Future Horizons tab displays. Loaded from the canonical
        # ``analysis_versions_v2`` cache; populated by the rerun path.
        exec_cards = assessment.get("_exec_summary_cards") or []
        for k, card in enumerate(exec_cards, 1):
            _add_executive_summary_card_slide(
                prs, card, topic_idx=topic_idx,
                card_idx=k, total_cards=len(exec_cards),
            )

        _add_key_insights_pure_slide(prs, assessment, topic=topic_name, topic_idx=topic_idx,
                                     articles=articles_corpus)
        _add_strategic_recommendations_slide(prs, assessment)
        # Executive Decision Framework — render principles produced by the
        # gpt-5.4 Topic Report prompt. Existing cross-topic helper expects a
        # list of {headline, body}; pull principles[] out of the dict.
        edf = (assessment.get("summary") or {}).get("executive_decision_framework") or {}
        edf_principles = edf.get("principles") if isinstance(edf, dict) else None
        if edf_principles:
            from app.services.forecast_pptx_export import _add_executive_decision_framework_slide
            _add_executive_decision_framework_slide(prs, edf_principles)
        _add_next_steps_slide(prs, assessment)

        # ── Black Swans / Wildcards (saved_eos for this topic) ─────────
        eos = assessment.get("_eos_scenarios") or []
        if eos:
            _add_black_swans_slide(prs, {topic_name: eos})

        # ── Surprise clusters tagged on the assessment, if any ─────────
        surprises = sorted(assessment.get("surprises") or [],
                           key=lambda s: -(s.get("size") or 0))
        if surprises:
            _add_surprises_divider(prs, surprises)
            for sur in surprises[:4]:
                _add_surprise_cluster_slide(prs, sur)

        # ── Supporting articles (always at least 5 if any exist) ───────
        _add_supporting_articles_slide(
            prs, assessment.get("_supporting_articles") or [],
            topic=topic_name, topic_idx=topic_idx,
        )

        # ── Per-horizon scenario walk: divider + cards for H1, H2, H3 ──
        scenarios = raw.get("scenarios") or []
        by_horizon: dict = {"h1": [], "h2": [], "h3": []}
        for s in scenarios:
            if isinstance(s, dict):
                key = (s.get("type") or "h1").lower()
                if key in by_horizon:
                    by_horizon[key].append(s)
        for horizon in ("h1", "h2", "h3"):
            group = by_horizon[horizon]
            if not group:
                continue
            _add_horizon_divider(prs, horizon, group, topic=topic_name)
            for scenario in group:
                _add_forecast_scenario_slide(prs, scenario, topic=topic_name,
                                             articles=articles_corpus)

        # ── Article References slide (numbered corpus) — closes each
        #    topic section and resolves the [N] markers on the body slides.
        _add_topic_references_slide(prs, articles_corpus,
                                    topic=topic_name, topic_idx=topic_idx)

    _add_methodology_appendix_slide(prs)

    _ai_pptx_marker(prs)  # EU AI Act Art. 50 machine-readable marker
    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()
