"""Standalone HTML renderer for the on-demand Topic Report.

Consumes the SAME ``items`` list ``topic_report_pptx.build_topic_report_pptx``
walks — so the HTML content (Briefing Synthesis, Executive Summary
cards, Key Insights, Strategic Recommendations, Executive Decision
Framework, Next Steps, Black Swans, Supporting Articles, per-scenario
H1/H2/H3 cards) is identical to the PPTX deck.

NOT to be confused with ``forecast_bundle_html.build_bundle_html`` — that
renders the cadence-locked Forecast Tracker bundle (back-test framing).
This module renders the FORECAST-driven foresight deck.

Output: a single self-contained HTML document (embedded CSS, no JS
deps, no external assets). Saved to disk by the route handler and
served as ``text/html``.
"""
from __future__ import annotations

import html as _html
import logging
import re as _re
from datetime import datetime
from typing import Optional

from app.services.topic_report_pptx import _decode_raw_output
from app.services.html_report_common import clean_article_ref
from app.compliance.ai_disclosure import (
    disclosure_footer_html as _ai_footer,
    html_meta_tags as _ai_meta,
)
from app.services.horizons_html import render_horizons_chart, _HORIZONS_EXTRA_CSS

logger = logging.getLogger(__name__)


# Wiley pink + navy palette (mirrors topic_report_pptx + forecast_pptx_export)
_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1f2937; background: #f8fafc; line-height: 1.55; }
a { color: #d6346c; }
h1, h2, h3, h4 { color: #111827; line-height: 1.25; margin: 0 0 .55rem 0; font-weight: 700; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 1.6rem 0; }
small { color: #6b7280; }
.container { max-width: 920px; margin: 0 auto; padding: 1.4rem 1.4rem 4rem; }

/* Cover */
.cover { background: #111827; color: #fff; padding: 2.4rem 1.6rem 2.6rem; border-radius: 12px; margin: 0 0 1.6rem 0; border-top: 4px solid #d6346c; border-bottom: 4px solid #d6346c; }
.cover .eyebrow { color: #d6346c; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .8rem; }
.cover h1 { color: #fff; font-size: 2.8rem; margin: .35rem 0 .25rem; letter-spacing: -0.02em; }
.cover .subtitle { color: #fbcfe4; font-style: italic; }

/* Section header */
.section-eyebrow { color: #d6346c; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .75rem; margin: 0 0 .3rem 0; }
.section h2 { font-size: 1.6rem; }

/* Topic divider */
.topic-divider { background: #111827; color: #fff; padding: 1.8rem 1.4rem; border-radius: 10px; margin: 2rem 0 1rem; }
.topic-divider .eyebrow { color: #d6346c; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .8rem; }
.topic-divider h2 { color: #fff; font-size: 2.1rem; margin: .25rem 0 0; }

/* Card primitives */
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.1rem; margin: 0 0 .9rem 0; }
.card-accent-top { border-top: 4px solid #d6346c; }

/* Briefing synthesis */
.briefing-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.briefing-tensions { background: #d6346c; color: #fff; border-radius: 8px; padding: 1rem 1.1rem; }
.briefing-tensions h3 { color: #fff; margin-bottom: .3rem; }
.briefing-tensions .tension-name { font-weight: 700; text-transform: uppercase; font-size: .8rem; letter-spacing: .05em; margin-top: .8rem; color: #fee9f5; }
.briefing-tensions .tension-body { font-size: .92rem; opacity: 0.95; }
.briefing-iview { background: #111827; color: #e5e7eb; border-radius: 8px; padding: 1rem 1.1rem; }
.briefing-iview h3 { color: #fff; }

/* Executive summary card */
.es-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 1.1rem 1.2rem; margin: 0 0 1rem 0; }
.es-card .es-eyebrow { color: #6b7280; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .68rem; }
.es-card h3 { font-size: 1.25rem; margin-top: .25rem; }
.es-meta { display: flex; gap: .55rem; margin: .75rem 0 .9rem; flex-wrap: wrap; }
.es-pill { padding: .35rem .8rem; border-radius: 999px; font-weight: 700; font-size: .78rem; }
.es-pill.h1 { background: #fee9f5; color: #8b1a42; }
.es-pill.h2 { background: #fff7e6; color: #9a3412; }
.es-pill.h3 { background: #e0f2fe; color: #075985; }
.es-pill.consensus { background: #d6346c; color: #fff; }
.es-minority { background: #fff7e6; border-left: 4px solid #f59e0b; padding: .55rem .8rem; border-radius: 4px; margin: .5rem 0; }
.es-minority .label { font-weight: 700; color: #92400e; font-size: .72rem; letter-spacing: .05em; text-transform: uppercase; }
.es-signal-label { color: #d6346c; font-weight: 700; font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; margin-top: 1rem; }
.es-signal { font-weight: 600; color: #111827; margin: .35rem 0 0; }
.es-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1rem; }
.es-fork, .es-window { border: 1px solid #e5e7eb; border-radius: 8px; padding: .8rem .95rem; }
.es-fork { border-top: 3px solid #111827; }
.es-window { border-top: 3px solid #d6346c; }
.es-fork .label, .es-window .label { font-weight: 700; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: #6b7280; }
.es-fork .row { margin-top: .55rem; }
.es-fork .row .marker { font-weight: 700; }
.es-fork .marker.ok { color: #047857; }
.es-fork .marker.alt { color: #b45309; }
.es-fork .outcome { color: #4b5563; font-size: .92rem; margin-top: .15rem; }
.es-window .tf { font-weight: 700; color: #d6346c; font-size: .78rem; letter-spacing: .04em; text-transform: uppercase; margin-top: .55rem; }
.es-window .action { color: #1f2937; margin-top: .15rem; }

/* Insights / recs / next steps */
.bullet-list { padding: 0; margin: 0; list-style: none; }
.bullet-list li { padding: .55rem 0 .55rem 1.5rem; position: relative; border-bottom: 1px solid #f3f4f6; }
.bullet-list li:last-child { border-bottom: 0; }
.bullet-list li::before { content: ""; position: absolute; left: 0; top: 1.0rem; width: .6rem; height: .6rem; background: #d6346c; border-radius: 2px; }

/* Three-card row */
.three-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: .85rem; }
.three-cards .card { margin: 0; }
.three-cards .card-header { color: #fff; padding: .55rem .8rem; border-radius: 4px; font-weight: 700; font-size: .9rem; }
.three-cards .card-header.teal { background: #d6346c; }
.three-cards .card-header.navy { background: #111827; }

/* Horizon section */
.horizon-section { margin: 1.6rem 0 0; }
.horizon-section h3 { display: inline-block; padding: .25rem .7rem; border-radius: 4px; color: #fff; font-size: 1rem; }
.horizon-section h3.h1 { background: #d6346c; }
.horizon-section h3.h2 { background: #b45309; }
.horizon-section h3.h3 { background: #0e7490; }

/* Scenario card */
.scenario-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem 1.1rem; margin: .6rem 0; border-left: 4px solid #d6346c; }
.scenario-card.h1 { border-left-color: #d6346c; }
.scenario-card.h2 { border-left-color: #b45309; }
.scenario-card.h3 { border-left-color: #0e7490; }
.scenario-card h4 { font-size: 1.05rem; margin-bottom: .3rem; }
.scenario-meta { font-size: .82rem; color: #6b7280; font-weight: 600; letter-spacing: .03em; text-transform: uppercase; }
.scenario-card .desc { margin-top: .4rem; color: #1f2937; }

/* Executive Summary card — "Based on scenarios" footer */
.es-sources { margin-top: .9rem; padding-top: .8rem; border-top: 1px dashed #e5e7eb; }
.es-sources .label { color: #6b7280; font-weight: 700; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; margin-bottom: .3rem; }
.es-sources ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .2rem; }
.es-sources li { color: #1f2937; font-size: .9rem; }
.es-srctag { display: inline-block; padding: 0 .35rem; border-radius: 3px; font-weight: 700; font-size: .68rem; letter-spacing: .04em; color: #fff; vertical-align: baseline; margin-right: .35rem; }
.es-srctag.h1 { background: #d6346c; }
.es-srctag.h2 { background: #b45309; }
.es-srctag.h3 { background: #0e7490; }

/* Inline citations — clickable [N] markers jumping to article refs */
a.cite { display: inline-block; padding: 0 .3rem; margin: 0 .05rem; background: #fee9f5; color: #8b1a42; border-radius: 3px; font-weight: 700; font-size: .82em; text-decoration: none; vertical-align: baseline; }
a.cite:hover { background: #fbcfe4; }

/* Numbered article-references list (target for the [N] anchors) */
.article-refs { padding-left: 1.3rem; margin: 0; }
.article-refs li { padding: .55rem 0; border-bottom: 1px solid #f3f4f6; scroll-margin-top: 1rem; }
.article-refs li:last-child { border-bottom: 0; }
.article-refs li:target { background: #fff7e6; box-shadow: inset 4px 0 0 #d6346c; padding-left: .6rem; }
.article-refs .title { font-weight: 600; color: #111827; }
.article-refs .ref-meta { color: #6b7280; font-size: .82rem; margin-top: .15rem; }

/* Articles table */
.articles { width: 100%; border-collapse: collapse; }
.articles td { padding: .55rem .35rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.sent-chip { display: inline-block; padding: .15rem .55rem; border-radius: 4px; font-size: .68rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.sent-chip.positive, .sent-chip.breakthrough { background: #d1e7dd; color: #065f46; }
.sent-chip.negative, .sent-chip.critical { background: #f8d7da; color: #8b1a42; }
.sent-chip.warning { background: #fff3cd; color: #92400e; }
.sent-chip.neutral, .sent-chip.mixed { background: #e2e3e5; color: #1f2937; }

/* Footer */
footer.meta { color: #6b7280; font-size: .82rem; margin-top: 3rem; text-align: center; }

@media (max-width: 720px) {
  .briefing-grid, .three-cards, .es-bottom { grid-template-columns: 1fr; }
}
"""


def _esc(v) -> str:
    """HTML-escape any scalar value, returning empty string for None."""
    if v is None:
        return ""
    return _html.escape(str(v))


_CITE_RE = _re.compile(r"\[(\d{1,3})\]")


def _esc_cites(v, topic_idx: int, articles: list | None = None) -> str:
    """``_esc`` + linkify ``[N]`` citations.

    When ``articles`` is given (the topic's numbered corpus), each
    ``[N]`` becomes an anchor that opens the publisher URL in a new
    tab. Without it, falls back to ``#ref-{topic_idx}-N`` — the
    in-document jump to the references list at the bottom of this
    topic's section.
    """
    escaped = _esc(v)
    if not escaped or "[" not in escaped:
        return escaped

    def _replace(m):
        n_str = m.group(1)
        try:
            n = int(n_str)
        except ValueError:
            return m.group(0)
        href = None
        if articles and 1 <= n <= len(articles):
            entry = articles[n - 1] or {}
            href = (entry.get("uri") or entry.get("url") or "").strip()
        if href:
            return (f'<a class="cite" href="{_esc(href)}" target="_blank" '
                    f'rel="noopener">[{n_str}]</a>')
        return f'<a class="cite" href="#ref-{topic_idx}-{n_str}">[{n_str}]</a>'

    return _CITE_RE.sub(_replace, escaped)


def _section_open(title: str, *, eyebrow: str = "") -> str:
    parts = ['<section class="section">']
    if eyebrow:
        parts.append(f'<p class="section-eyebrow">{_esc(eyebrow)}</p>')
    parts.append(f'<h2>{_esc(title)}</h2>')
    return "\n".join(parts)


def _topic_divider(topic: str, idx: int) -> str:
    return (
        f'<div class="topic-divider">'
        f'  <div class="eyebrow">TOPIC {idx}</div>'
        f'  <h2>{_esc(topic)}</h2>'
        f'</div>'
    )


def _render_briefing(brief: dict, topic_idx: int, articles=None) -> str:
    if not brief or not brief.get("lede"):
        return ""
    tensions = brief.get("tensions") or []
    parts = [_section_open("Briefing Synthesis", eyebrow="THE ECOSYSTEM AT A CROSSROADS")]
    headline = brief.get("headline") or ""
    if headline:
        parts.append(f'<p style="color:#6b7280;font-style:italic;margin:.1rem 0 1rem">{_esc(headline)}</p>')
    parts.append('<div class="briefing-grid">')
    # Left — tensions
    parts.append('<div class="briefing-tensions">')
    parts.append('<h3>Defining Tensions</h3>')
    for t in tensions[:4]:
        parts.append(f'<div class="tension-name">{_esc(t.get("name") or "")}</div>')
        parts.append(f'<div class="tension-body">{_esc_cites(t.get("body") or "", topic_idx, articles)}</div>')
    parts.append('</div>')
    # Right — Aunoo intelligence view
    parts.append('<div class="briefing-iview">')
    parts.append('<h3>The Aunoo Intelligence View</h3>')
    parts.append(f'<p>{_esc_cites(brief.get("lede") or "", topic_idx, articles)}</p>')
    iv = (brief.get("intelligence_view") or "").strip()
    if iv:
        parts.append(f'<p>{_esc_cites(iv, topic_idx, articles)}</p>')
    parts.append('</div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def _render_executive_summary(cards: list, topic_idx: int, articles=None) -> str:
    if not cards:
        return ""
    parts = [_section_open("Executive Summary", eyebrow="HORIZON-ANCHORED VIEW")]
    for k, c in enumerate(cards, 1):
        if not isinstance(c, dict):
            continue
        horizon = (c.get("primary_horizon") or "h1").lower()
        h_label = c.get("horizon_label") or ""
        cons = c.get("consensus_percentage")
        cons_pct = f"{int(cons)}%" if isinstance(cons, (int, float)) else ""
        title = c.get("topic_title") or "—"
        opening = c.get("opening_statement") or ""
        mv = c.get("minority_view") or {}
        signal = c.get("primary_signal") or ""
        fork = c.get("decision_fork") or {}
        fa = fork.get("condition_a") or {}
        fb = fork.get("condition_b") or {}
        aw = c.get("action_window") or {}
        aw_assess = aw.get("assessment") or {}
        aw_pos    = aw.get("positioning") or {}

        parts.append('<div class="es-card">')
        parts.append(f'<div class="es-eyebrow">Card {k} of {len(cards)}</div>')
        parts.append(f'<h3>{_esc(title)}</h3>')
        parts.append('<div class="es-meta">')
        parts.append(f'<span class="es-pill {horizon}">{horizon.upper()} · {_esc(h_label)}</span>')
        if cons_pct:
            parts.append(f'<span class="es-pill consensus">{cons_pct} CONSENSUS</span>')
        parts.append('</div>')
        if opening:
            parts.append(f'<p>{_esc_cites(opening, topic_idx, articles)}</p>')
        # Minority view
        if mv.get("statement"):
            pct = mv.get("percentage_range") or ""
            label = "Minority view" + (f"  ·  {pct}" if pct else "")
            parts.append('<div class="es-minority">')
            parts.append(f'<div class="label">{_esc(label)}</div>')
            parts.append(f'<div>{_esc_cites(mv.get("statement") or "", topic_idx, articles)}</div>')
            parts.append('</div>')
        # Primary signal
        if signal:
            label = "Primary signal" + (f"  ·  {cons_pct} consensus" if cons_pct else "")
            parts.append(f'<div class="es-signal-label">{_esc(label)}</div>')
            parts.append(f'<p class="es-signal">{_esc_cites(signal, topic_idx, articles)}</p>')
        # Source scenarios — link this card back to the H1/H2/H3 scenarios
        # the LLM clustered.
        src_list = [s for s in (c.get("source_scenarios") or []) if isinstance(s, dict)]
        if src_list:
            parts.append('<div class="es-sources">')
            parts.append('<div class="label">Based on scenarios</div>')
            parts.append('<ul>')
            for s in src_list:
                h = (s.get("horizon") or "").upper()
                t = (s.get("title") or "").strip()
                if not t:
                    continue
                tag = (f'<span class="es-srctag {h.lower()}">{_esc(h)}</span>'
                       if h else "")
                parts.append(f'<li>{tag} {_esc(t)}</li>')
            parts.append('</ul></div>')

        # Fork + window
        if (fa.get("condition") or fb.get("condition") or
            aw_assess.get("action") or aw_pos.get("action")):
            parts.append('<div class="es-bottom">')
            if fa.get("condition") or fb.get("condition"):
                parts.append('<div class="es-fork"><div class="label">Decision fork</div>')
                if fa.get("condition") or fa.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker ok">✔</span> {_esc_cites(fa.get("condition") or "", topic_idx, articles)}</div>')
                    if fa.get("outcome"):
                        parts.append(f'<div class="outcome">→ {_esc_cites(fa.get("outcome") or "", topic_idx, articles)}</div>')
                    parts.append('</div>')
                if fb.get("condition") or fb.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker alt">!</span> {_esc_cites(fb.get("condition") or "", topic_idx, articles)}</div>')
                    if fb.get("outcome"):
                        parts.append(f'<div class="outcome">→ {_esc_cites(fb.get("outcome") or "", topic_idx, articles)}</div>')
                    parts.append('</div>')
                parts.append('</div>')
            if aw_assess.get("action") or aw_pos.get("action"):
                parts.append('<div class="es-window"><div class="label">Your window</div>')
                for row in (aw_assess, aw_pos):
                    tf = row.get("timeframe") or ""
                    act = row.get("action") or ""
                    if tf:
                        parts.append(f'<div class="tf">{_esc(tf)}</div>')
                    if act:
                        parts.append(f'<div class="action">{_esc_cites(act, topic_idx, articles)}</div>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def _render_bullet_list(title: str, items: list, topic_idx: int, *, eyebrow: str = "", articles=None) -> str:
    items = [s for s in (items or []) if isinstance(s, str) and s.strip()]
    if not items:
        return ""
    parts = [_section_open(title, eyebrow=eyebrow), '<ul class="bullet-list">']
    for s in items[:8]:
        parts.append(f'<li>{_esc_cites(s, topic_idx, articles)}</li>')
    parts.append('</ul></section>')
    return "\n".join(parts)


def _render_strategic_recs(recs: list, topic_idx: int, articles=None) -> str:
    recs = [r for r in (recs or []) if isinstance(r, dict)]
    if not recs:
        return ""
    parts = [_section_open("Strategic Recommendations", eyebrow="THREE STRATEGIC PRIORITIES")]
    parts.append('<div class="three-cards">')
    palette = ["teal", "navy", "teal"]
    for i, r in enumerate(recs[:3]):
        header_cls = palette[i % 3]
        parts.append('<div class="card card-accent-top">')
        parts.append(f'<div class="card-header {header_cls}">{_esc(r.get("headline") or "—")}</div>')
        parts.append(f'<p style="margin:.7rem 0">{_esc_cites(r.get("rationale") or "", topic_idx, articles)}</p>')
        horizon = r.get("horizon") or ""
        if horizon:
            parts.append(f'<small style="color:#6b7280">Horizon: {_esc(horizon)}</small>')
        parts.append('</div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def _render_decision_framework(principles: list, topic_idx: int, articles=None) -> str:
    principles = [p for p in (principles or []) if isinstance(p, dict)]
    if not principles:
        return ""
    parts = [_section_open("Executive Decision Framework", eyebrow="LEADERSHIP PRINCIPLES")]
    parts.append('<div class="three-cards">')
    palette = ["teal", "navy", "teal"]
    for i, p in enumerate(principles[:3]):
        header_cls = palette[i % 3]
        parts.append('<div class="card card-accent-top">')
        parts.append(f'<div class="card-header {header_cls}">{_esc(p.get("headline") or "—")}</div>')
        parts.append(f'<p style="margin:.7rem 0">{_esc_cites(p.get("body") or "", topic_idx, articles)}</p>')
        parts.append('</div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def _render_next_steps(steps: list, topic_idx: int, articles=None) -> str:
    steps = [s for s in (steps or []) if isinstance(s, dict)]
    if not steps:
        return ""
    parts = [_section_open("Next Steps", eyebrow="IMMEDIATE PRIORITIES")]
    parts.append('<div class="three-cards">')
    for i, s in enumerate(steps[:3]):
        parts.append('<div class="card card-accent-top">')
        cat = s.get("category") or f"Step {i+1}"
        parts.append(f'<div class="card-header teal">{_esc(cat)}</div>')
        parts.append(f'<p style="margin:.7rem 0">{_esc_cites(s.get("action") or "", topic_idx, articles)}</p>')
        parts.append('</div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def _render_black_swans(eos: list, topic_idx: int, articles=None) -> str:
    eos = [s for s in (eos or []) if isinstance(s, dict)]
    if not eos:
        return ""
    parts = [_section_open("Black Swans & Wildcards", eyebrow="HIGH-IMPACT, LOW-PROBABILITY")]

    def _coerce(v, default=0.0):
        # ``probability`` is sometimes a categorical string ("low"/"medium"/
        # "high") and ``impact_rating`` is sometimes an int. Bucket the
        # categoricals so sort doesn't blow up; pass numerics through.
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
        impact = s.get("impact_rating")
        impact_str = f"Impact {int(impact)}/10" if impact is not None else ""
        timeframe = s.get("timeframe") or ""
        parts.append('<div class="card">')
        parts.append(f'<div class="scenario-meta">{_esc(cat)}</div>')
        parts.append(f'<h4>{_esc(s.get("name") or "—")}</h4>')
        trajectory = (s.get("trajectory") or s.get("description") or "").strip()
        if trajectory:
            parts.append(f'<p>{_esc_cites(trajectory, topic_idx, articles)}</p>')
        if impact_str or timeframe:
            meta = "  ·  ".join([m for m in (impact_str, timeframe) if m])
            parts.append(f'<small>{_esc(meta)}</small>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def _render_supporting_articles(articles: list, topic_idx: int) -> str:
    """Numbered article-references list. The ``[N]`` citations in this
    topic's body text resolve to ``#ref-{topic_idx}-N`` anchors here.
    """
    articles = [a for a in (articles or []) if isinstance(a, dict)]
    if len(articles) < 3:
        return ""
    parts = [_section_open("Article References", eyebrow="SOURCE CORPUS")]
    parts.append('<ol class="article-refs">')
    for n, a in enumerate(articles, 1):
        c = clean_article_ref(a)
        title = c["title"] or "—"
        uri = c["uri"]
        src = c["source"]
        date = c["date"]
        sent = (a.get("sentiment") or "").lower().split("/")[0]
        title_html = (f'<a href="{_esc(uri)}" target="_blank" rel="noopener">{_esc(title)}</a>'
                      if uri else _esc(title))
        meta_bits = [b for b in (src, date) if b]
        parts.append(f'<li id="ref-{topic_idx}-{n}">')
        parts.append(f'<div class="title">{title_html}</div>')
        if meta_bits or sent:
            meta = "  ·  ".join(meta_bits)
            extras = []
            if meta:
                extras.append(_esc(meta))
            if sent:
                extras.append(f'<span class="sent-chip {_esc(sent)}">{_esc(sent.upper())}</span>')
            parts.append(f'<div class="ref-meta">{"  ".join(extras)}</div>')
        parts.append('</li>')
    parts.append('</ol></section>')
    return "\n".join(parts)


def _render_scenarios(scenarios: list, topic: str, topic_idx: int, articles=None) -> str:
    scenarios = [s for s in (scenarios or []) if isinstance(s, dict)]
    if not scenarios:
        return ""
    by_horizon = {"h1": [], "h2": [], "h3": []}
    for s in scenarios:
        h = (s.get("type") or "h1").lower()
        if h in by_horizon:
            by_horizon[h].append(s)
    labels = {"h1": "H1 — Declining Systems",
              "h2": "H2 — Transition / Innovation",
              "h3": "H3 — Future Vision"}
    parts = [_section_open("Three Horizons", eyebrow="FORECAST SCENARIOS")]
    for horizon in ("h1", "h2", "h3"):
        group = by_horizon[horizon]
        if not group:
            continue
        parts.append('<div class="horizon-section">')
        parts.append(f'<h3 class="{horizon}">{_esc(labels[horizon])}</h3>')
        for s in group:
            timeframe = s.get("timeframe") or ""
            sentiment = s.get("sentiment") or ""
            meta = "  ·  ".join([b for b in (horizon.upper(), timeframe, sentiment) if b])
            parts.append(f'<div class="scenario-card {horizon}">')
            parts.append(f'<div class="scenario-meta">{_esc(meta)}</div>')
            parts.append(f'<h4>{_esc(s.get("title") or "—")}</h4>')
            desc = (s.get("description") or "").strip()
            if desc:
                parts.append(f'<p class="desc">{_esc_cites(desc, topic_idx, articles)}</p>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def build_topic_report_html(items: list, *, period_label: str,
                            period: Optional[str] = None) -> bytes:
    """Render the same content the PPTX builder produces as a single
    self-contained HTML document.

    Layout: cover → per-topic sections (divider → briefing → exec
    summary cards → key insights → strategic recs → decision framework
    → next steps → black swans → supporting articles → scenarios) →
    methodology footer.
    """
    topics_str = ", ".join((a.get("topic") or "—") for (a, _r, _p) in items)
    period_display = period or period_label

    body_parts: list = []
    # Cover
    body_parts.append('<div class="cover">')
    body_parts.append('<div class="eyebrow">WILEY HORIZONS · FORESIGHT</div>')
    body_parts.append(f'<h1>{_esc(period_display)}</h1>')
    body_parts.append('<div class="subtitle">Topic Foresight Report  ·  Produced by AunooAI</div>')
    body_parts.append(f'<div style="margin-top:1rem;color:#fbcfe4;font-size:.92rem">'
                      f'{len(items)} topic{"s" if len(items) != 1 else ""}: {_esc(topics_str)}</div>')
    body_parts.append('</div>')

    # Inject the chart + columns CSS once, up front — same shared block
    # the Future Horizons HTML uses so the topic-report chart looks
    # identical (palette, curves, marker style).
    body_parts.append(f'<style>{_HORIZONS_EXTRA_CSS}</style>')

    # Per topic
    for topic_idx, (assessment, forecast_run, _prior) in enumerate(items, 1):
        topic_name = assessment.get("topic") or "—"
        raw = _decode_raw_output(forecast_run or {})
        summary = assessment.get("summary") or {}
        # Numbered corpus the LLM cited as [1], [2] … Each body-text
        # renderer takes this and turns [N] into a direct anchor to the
        # publisher URL — opens in a new tab. Falls back to ``#ref-T-N``
        # (the in-document references list) when corpus is unavailable.
        articles = assessment.get("_articles_corpus") or \
                   assessment.get("_supporting_articles") or []

        body_parts.append(_topic_divider(topic_name, topic_idx))

        # Three Horizons SVG chart — the visual the React tab shows
        # (gradients, curves, NOW marker, scenario markers placed on the
        # curves, timeline footer). Same renderer the standalone Future
        # Horizons HTML uses, so the two downloads stay visually in sync.
        scenarios_for_chart = raw.get("scenarios") or []
        if scenarios_for_chart:
            body_parts.append(render_horizons_chart(scenarios_for_chart))

        # Briefing Synthesis
        brief = summary.get("topic_briefing") or {}
        body_parts.append(_render_briefing(brief, topic_idx, articles=articles))

        # Executive Summary cards (the React-tab cards)
        body_parts.append(_render_executive_summary(
            assessment.get("_exec_summary_cards") or [],
            topic_idx, articles=articles,
        ))

        # Key Insights
        body_parts.append(_render_bullet_list(
            "Key Insights", summary.get("key_insights") or [], topic_idx,
            eyebrow="CROSS-SOURCE OBSERVATIONS", articles=articles,
        ))

        # Strategic Recommendations
        body_parts.append(_render_strategic_recs(
            summary.get("strategic_recommendations") or [],
            topic_idx, articles=articles,
        ))

        # Executive Decision Framework
        edf = summary.get("executive_decision_framework") or {}
        principles = edf.get("principles") if isinstance(edf, dict) else None
        body_parts.append(_render_decision_framework(principles or [], topic_idx,
                                                     articles=articles))

        # Next Steps
        body_parts.append(_render_next_steps(summary.get("next_steps") or [], topic_idx,
                                             articles=articles))

        # Black Swans
        body_parts.append(_render_black_swans(
            assessment.get("_eos_scenarios") or [],
            topic_idx, articles=articles,
        ))

        # Three Horizons scenarios
        body_parts.append(_render_scenarios(
            raw.get("scenarios") or [], topic_name, topic_idx,
            articles=articles,
        ))

        # Article References (numbered list — target for the [N] citations
        # in this topic's exec-summary cards, scenarios, and recs).
        body_parts.append(_render_supporting_articles(
            assessment.get("_supporting_articles") or [],
            topic_idx,
        ))

        body_parts.append("<hr />")

    body_parts.append(
        '<footer class="meta">'
        f'Topic report rendered {_esc(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))}'
        '  ·  AunooAI Wiley Horizons Foresight'
        '</footer>'
    )
    body_parts.append(_ai_footer())  # EU AI Act Art. 50 visible disclosure

    html = (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        + _ai_meta()  # EU AI Act Art. 50 machine-readable marker
        + f'<title>Topic Report — {_esc(period_display)}</title>'
        f'<style>{_CSS}</style></head><body>'
        '<div class="container">'
        + "\n".join(body_parts)
        + '</div></body></html>'
    )
    return html.encode("utf-8")
