"""Standalone Future Horizons HTML export.

Renders a single topic's Three Horizons scenarios + the Executive Summary
cards (the React tab's `ExecutiveSummaryCard` content) into one
self-contained HTML document. Used by
``GET /api/trend-convergence/horizons/{run_id}/download.html``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.services.html_report_common import (
    BASE_CSS, esc, html_document, section_open,
    render_executive_summary_cards, render_scenarios,
)

logger = logging.getLogger(__name__)


_HORIZONS_EXTRA_CSS = """
/* Three Horizons chart — mirrors the React FutureHorizons SVG layout */
.horizons-chart-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; margin: 0 0 1.6rem 0; }
.horizons-chart-head { background: linear-gradient(to right, #eff6ff, #f5f3ff, #f0fdf4); padding: .85rem 1.1rem; border-bottom: 1px solid #e5e7eb; }
.horizons-chart-head h3 { color: #111827; font-size: 1.05rem; margin: 0 0 .15rem; }
.horizons-chart-head p { color: #6b7280; font-size: .88rem; margin: 0; }
.horizons-chart { position: relative; background: linear-gradient(to bottom right, #fdf2f8, #faf5ff, #eff6ff); height: 480px; overflow: visible; }
.horizons-chart svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.horizon-label { position: absolute; left: .6rem; color: #fff; padding: .35rem .7rem; border-radius: 4px; font-size: .82rem; font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.12); transform: translateY(-50%); }
.horizon-label.h1 { background: #2563eb; top: 25%; }
.horizon-label.h2 { background: #9333ea; top: 85%; }
.horizon-label.h3 { background: #16a34a; top: 95%; }
.scenario-marker { position: absolute; transform: translate(-50%, -50%); max-width: 160px; }
.scenario-marker .card-inner { background: #fff; border: 2px solid; border-radius: 4px; padding: .25rem .45rem; box-shadow: 0 1px 3px rgba(0,0,0,.10); font-size: 9.5px; font-weight: 700; color: #111827; line-height: 1.15; }
.scenario-marker.h1 .card-inner { background: #eff6ff; border-color: #2563eb; }
.scenario-marker.h2 .card-inner { background: #faf5ff; border-color: #9333ea; }
.scenario-marker.h3 .card-inner { background: #f0fdf4; border-color: #16a34a; }
.horizons-chart-timeline { display: flex; justify-content: space-between; padding: .7rem 2rem; background: #f9fafb; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: .85rem; }
.horizons-chart-timeline .tick { text-align: center; }
.horizons-chart-timeline .year { color: #111827; font-weight: 700; }
.horizons-chart-timeline .tag { color: #6b7280; font-size: .72rem; margin-top: .1rem; }

/* Three-column scenario layout — mirrors the React 'Three Horizons Columns' grid */
.horizon-columns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1.2rem; }
.horizon-col-head { color: #fff; padding: .75rem 1rem; border-radius: 8px 8px 0 0; text-align: center; }
.horizon-col-head .label { font-weight: 700; font-size: .95rem; }
.horizon-col-head .subtitle { font-size: .78rem; opacity: .9; margin-top: .15rem; }
.horizon-col-head.h1 { background: #2563eb; }
.horizon-col-head.h2 { background: #9333ea; }
.horizon-col-head.h3 { background: #16a34a; }
.horizon-col-body { background: #f9fafb; padding: .85rem; border: 1px solid #e5e7eb; border-top: 0; border-radius: 0 0 8px 8px; min-height: 12rem; display: flex; flex-direction: column; gap: .65rem; }
.horizon-col-body .empty { color: #9ca3af; font-style: italic; font-size: .88rem; text-align: center; padding: 1rem 0; }
.col-scenario-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: .65rem .8rem; }
.col-scenario-card h4 { font-size: .9rem; margin: 0 0 .35rem; color: #111827; line-height: 1.3; }
.col-scenario-card .timeframe { color: #6b7280; font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; margin-bottom: .35rem; }
.col-scenario-card .desc { color: #4b5563; font-size: .82rem; }
.col-scenario-card .sentiment { display: inline-block; padding: .1rem .4rem; border-radius: 3px; font-size: .65rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; margin-top: .4rem; background: #e2e3e5; color: #1f2937; }

/* Article refs */
.article-refs { padding: 0; margin: 0; list-style: none; counter-reset: refs; }
.article-refs li { padding: .55rem 0 .55rem 2.4rem; border-bottom: 1px solid #f3f4f6; position: relative; counter-increment: refs; }
.article-refs li::before { content: "[" counter(refs) "]"; position: absolute; left: 0; top: .55rem; color: #d6346c; font-weight: 700; font-size: .85rem; min-width: 2rem; }
.article-refs .title { color: #111827; font-weight: 600; }
.article-refs .title a { color: #111827; text-decoration: none; border-bottom: 1px solid transparent; }
.article-refs .title a:hover { border-bottom-color: #d6346c; color: #d6346c; }
.article-refs .ref-meta { color: #6b7280; font-size: .82rem; margin-top: .15rem; }

@media (max-width: 720px) {
  .horizon-columns { grid-template-columns: 1fr; }
  .horizons-chart { height: 360px; }
}
"""


# Path strings for the three wave curves — verbatim from the React SVG.
_H1_CURVE_PATH = "M 0,25 Q 25,28 50,45 T 100,75"
_H2_CURVE_PATH = "M 0,85 Q 25,75 40,55 Q 55,35 70,40 Q 85,45 100,60"
_H3_CURVE_PATH = "M 0,95 Q 30,95 50,85 Q 70,75 85,55 T 100,20"


def _parse_timeframe(timeframe: str) -> tuple:
    """Pull (start_year, end_year) out of a "YYYY-YYYY" timeframe string."""
    import re as _re
    if not timeframe:
        return (2025, 2040)
    years = _re.findall(r"\d{4}", timeframe)
    if len(years) >= 2:
        return (int(years[0]), int(years[1]))
    if len(years) == 1:
        y = int(years[0])
        return (y, y)
    return (2025, 2040)


def _bezier_q(t: float, p0: tuple, p1: tuple, p2: tuple) -> float:
    """Quadratic Bezier y value at t for control points p0/p1/p2."""
    mt = 1 - t
    return mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]


def _y_on_curve(x: float, wave: str) -> float:
    """Y position on the named wave at the given X (0-100). Mirrors
    ``getYOnCurve`` in the React FutureHorizons component so scenario
    markers land on the curve."""
    t = max(0.0, min(1.0, x / 100.0))
    if wave == "h1":
        if t <= 0.5:
            return _bezier_q(t / 0.5, (0, 25), (25, 28), (50, 45))
        return _bezier_q((t - 0.5) / 0.5, (50, 45), (75, 62), (100, 75))
    if wave == "h2":
        if t <= 0.4:
            return _bezier_q(t / 0.4, (0, 85), (25, 75), (40, 55))
        if t <= 0.7:
            return _bezier_q((t - 0.4) / 0.3, (40, 55), (55, 35), (70, 40))
        return _bezier_q((t - 0.7) / 0.3, (70, 40), (85, 45), (100, 60))
    # h3
    if t <= 0.5:
        return _bezier_q(t / 0.5, (0, 95), (30, 95), (50, 85))
    return _bezier_q((t - 0.5) / 0.5, (50, 85), (70, 75), (100, 20))


def _scenario_position(scenario: dict, type_index: int, total_in_type: int) -> tuple:
    """Mirror the React ``calculateHorizonPosition`` so markers land in the
    same place. Returns (x_pct, y_pct)."""
    start, end = _parse_timeframe(scenario.get("timeframe") or "")
    avg_year = (start + end) / 2
    base_x = 10 + ((avg_year - 2025) / 15) * 75
    spread = ((type_index / (total_in_type - 1) - 0.5) * 55) if total_in_type > 1 else 0
    x = max(8, min(92, base_x + spread))
    y = _y_on_curve(x, (scenario.get("type") or "h1").lower())
    y += ((type_index % 3) - 1) * 12   # alternating vertical offset
    return (x, y)


_H1_DESC = ("Current Paradigm / Declining — dominant practices that are gradually "
            "fading as new innovations emerge.")
_H2_DESC = ("Transition / Innovation — experimental approaches and the period where "
            "old and new coexist.")
_H3_DESC = ("Future Vision / Emerging — transformative visions becoming reality.")


def _render_horizons_chart(scenarios: list) -> str:
    """Render the inline SVG Three Horizons chart with scenario markers
    placed on the wave curves. Mirrors the React tab's chart so the HTML
    download feels like a snapshot of that view.
    """
    scenarios = [s for s in (scenarios or []) if isinstance(s, dict)]
    by_horizon = {"h1": [], "h2": [], "h3": []}
    for s in scenarios:
        h = (s.get("type") or "h1").lower()
        if h in by_horizon:
            by_horizon[h].append(s)
    for h in by_horizon:
        by_horizon[h].sort(key=lambda s: _parse_timeframe(s.get("timeframe") or "")[0])

    parts: list = ['<div class="horizons-chart-wrap">']
    parts.append('<div class="horizons-chart-head">')
    parts.append('<h3>Three Horizons Model</h3>')
    parts.append('<p>Visualising the transition from current systems (H1) through emerging innovations (H2) to future visions (H3).</p>')
    parts.append('</div>')
    parts.append('<div class="horizons-chart">')

    # Inline SVG — same paths + gradients as the React component.
    parts.append('<svg viewBox="0 0 100 100" preserveAspectRatio="none">')
    parts.append('<defs>'
                 '<linearGradient id="h1Gradient" x1="0%" y1="0%" x2="100%" y2="0%">'
                 '<stop offset="0%" stop-color="#3b82f6" stop-opacity="0.7"/>'
                 '<stop offset="50%" stop-color="#ec4899" stop-opacity="0.3"/>'
                 '<stop offset="100%" stop-color="#93c5fd" stop-opacity="0.2"/>'
                 '</linearGradient>'
                 '<linearGradient id="h2Gradient" x1="0%" y1="0%" x2="100%" y2="0%">'
                 '<stop offset="0%" stop-color="#a855f7" stop-opacity="0.3"/>'
                 '<stop offset="50%" stop-color="#ec4899" stop-opacity="0.7"/>'
                 '<stop offset="100%" stop-color="#c084fc" stop-opacity="0.3"/>'
                 '</linearGradient>'
                 '<linearGradient id="h3Gradient" x1="0%" y1="0%" x2="100%" y2="0%">'
                 '<stop offset="0%" stop-color="#22c55e" stop-opacity="0.2"/>'
                 '<stop offset="50%" stop-color="#f472b6" stop-opacity="0.4"/>'
                 '<stop offset="100%" stop-color="#4ade80" stop-opacity="0.7"/>'
                 '</linearGradient></defs>')
    # H1 fill + stroke
    parts.append(f'<path d="{_H1_CURVE_PATH} L 100,100 L 0,100 Z" fill="url(#h1Gradient)"/>')
    parts.append(f'<path d="{_H1_CURVE_PATH}" fill="none" stroke="#2563eb" stroke-width="0.6"/>')
    # H2 fill + stroke
    parts.append(f'<path d="{_H2_CURVE_PATH} L 100,100 L 0,100 Z" fill="url(#h2Gradient)"/>')
    parts.append(f'<path d="{_H2_CURVE_PATH}" fill="none" stroke="#9333ea" stroke-width="0.6"/>')
    # H3 fill + stroke
    parts.append(f'<path d="{_H3_CURVE_PATH} L 100,100 L 0,100 Z" fill="url(#h3Gradient)"/>')
    parts.append(f'<path d="{_H3_CURVE_PATH}" fill="none" stroke="#16a34a" stroke-width="0.6"/>')
    # NOW marker
    parts.append('<circle cx="3" cy="50" r="2" fill="#1f2937"/>')
    parts.append('<text x="3" y="58" font-size="3" fill="#1f2937" text-anchor="middle" font-weight="bold">NOW</text>')
    parts.append('</svg>')

    # Horizon labels on the left
    parts.append('<div class="horizon-label h1" title="' + esc(_H1_DESC) + '">Current</div>')
    parts.append('<div class="horizon-label h2" title="' + esc(_H2_DESC) + '">Transition</div>')
    parts.append('<div class="horizon-label h3" title="' + esc(_H3_DESC) + '">Future</div>')

    # Scenario marker cards positioned on the curves
    for horizon in ("h1", "h2", "h3"):
        group = by_horizon[horizon]
        for i, scenario in enumerate(group):
            x, y = _scenario_position(scenario, i, len(group))
            title = scenario.get("title") or "—"
            timeframe = scenario.get("timeframe") or ""
            description = (scenario.get("description") or "").strip()
            tooltip_bits = [b for b in (timeframe, description[:160]) if b]
            tooltip = "  ·  ".join(tooltip_bits) if tooltip_bits else title
            parts.append(
                f'<div class="scenario-marker {horizon}" '
                f'style="left:{x:.2f}%;top:{y:.2f}%" title="{esc(tooltip)}">'
                f'<div class="card-inner">{esc(title)}</div></div>'
            )

    parts.append('</div>')  # /horizons-chart

    # Timeline footer
    parts.append('<div class="horizons-chart-timeline">')
    for year, tag in [("2025", "Present"), ("2029", "Short-term"),
                      ("2033", "Mid-term"), ("2037", "Long-term"),
                      ("2040", "Horizon")]:
        parts.append(
            f'<div class="tick"><span class="year">{year}</span>'
            f'<div class="tag">{tag}</div></div>'
        )
    parts.append('</div>')

    parts.append('</div>')  # /horizons-chart-wrap
    return "\n".join(parts)


def _render_horizon_columns(scenarios: list) -> str:
    """Three side-by-side columns of scenario cards, matching the React
    "Three Horizons Columns" grid."""
    scenarios = [s for s in (scenarios or []) if isinstance(s, dict)]
    if not scenarios:
        return ""
    by_horizon = {"h1": [], "h2": [], "h3": []}
    for s in scenarios:
        h = (s.get("type") or "h1").lower()
        if h in by_horizon:
            by_horizon[h].append(s)
    headers = [
        ("h1", "Current", "Declining Systems"),
        ("h2", "Transition", "Emerging Innovations"),
        ("h3", "Future", "Emerging Vision"),
    ]
    parts: list = [section_open("Detailed Scenarios", eyebrow="THREE HORIZONS COLUMNS")]
    parts.append('<div class="horizon-columns">')
    for horizon, label, subtitle in headers:
        parts.append('<div>')
        parts.append(f'<div class="horizon-col-head {horizon}">')
        parts.append(f'<div class="label">{esc(label)}</div>')
        parts.append(f'<div class="subtitle">{esc(subtitle)}</div>')
        parts.append('</div>')
        parts.append('<div class="horizon-col-body">')
        group = by_horizon[horizon]
        if not group:
            parts.append('<div class="empty">No scenarios in this horizon.</div>')
        else:
            for s in group:
                title = s.get("title") or "—"
                tf = s.get("timeframe") or ""
                sent = (s.get("sentiment") or "").strip()
                desc = (s.get("description") or "").strip()
                parts.append('<div class="col-scenario-card">')
                if tf:
                    parts.append(f'<div class="timeframe">{esc(tf)}</div>')
                parts.append(f'<h4>{esc(title)}</h4>')
                if desc:
                    parts.append(f'<div class="desc">{esc(desc)}</div>')
                if sent:
                    parts.append(f'<span class="sentiment">{esc(sent)}</span>')
                parts.append('</div>')
        parts.append('</div></div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def _render_article_references(articles: list) -> str:
    """Numbered article-references list. Mirrors the [1], [2] citation
    markers the scenario descriptions and executive-summary cards use.
    """
    refs = [a for a in (articles or []) if isinstance(a, dict)
            and (a.get("title") or "").strip()]
    if not refs:
        return ""
    parts: list = [section_open("Article References", eyebrow="SOURCE CORPUS")]
    parts.append(f'<style>{_HORIZONS_EXTRA_CSS}</style>')
    parts.append('<ol class="article-refs">')
    for a in refs:
        title = a.get("title") or ""
        url = a.get("url") or a.get("uri") or ""
        source = a.get("source") or a.get("news_source") or ""
        date = (a.get("date") or a.get("publication_date") or "")[:10]
        title_html = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(title)}</a>'
                      if url else esc(title))
        meta_bits = [b for b in (source, date) if b]
        parts.append('<li>')
        parts.append(f'<div class="title">{title_html}</div>')
        if meta_bits:
            parts.append(f'<div class="ref-meta">{esc("  ·  ".join(meta_bits))}</div>')
        parts.append('</li>')
    parts.append('</ol></section>')
    return "\n".join(parts)


def build_horizons_html(
    topic: str,
    scenarios: list,
    summaries: Optional[list] = None,
    *,
    generated_at: Optional[str] = None,
    model_used: Optional[str] = None,
    articles: Optional[list] = None,
) -> bytes:
    """Render a Future Horizons analysis as a standalone HTML page.

    ``scenarios`` is the ``raw_output.scenarios`` array (list of
    ``{type, title, description, timeframe, sentiment}`` dicts).
    ``summaries`` is the ``analysis_versions_v2[horizons_exec_summary_*]``
    array. ``articles`` is the numbered corpus the LLM cited — rendered
    as a numbered "Article References" list at the bottom so the [n]
    citations in scenario descriptions resolve.
    """
    body_parts: list = []

    # Cover
    body_parts.append('<div class="cover">')
    body_parts.append('<div class="eyebrow">WILEY HORIZONS · FUTURE HORIZONS</div>')
    body_parts.append(f'<h1>{esc(topic)}</h1>')
    body_parts.append('<div class="subtitle">Three Horizons foresight  ·  Produced by AunooAI</div>')
    meta_bits = []
    if generated_at:
        meta_bits.append(esc(generated_at[:19].replace("T", " ")))
    if model_used:
        meta_bits.append(f"model: {esc(model_used)}")
    n_s = len([s for s in (scenarios or []) if isinstance(s, dict)])
    n_c = len([c for c in (summaries or []) if isinstance(c, dict)])
    n_a = len([a for a in (articles or []) if isinstance(a, dict)])
    meta_bits.append(f"{n_s} scenarios")
    if n_c:
        meta_bits.append(f"{n_c} executive summary cards")
    if n_a:
        meta_bits.append(f"{n_a} articles")
    body_parts.append(
        f'<div style="margin-top:1rem;color:#fbcfe4;font-size:.92rem">'
        f'{"  ·  ".join(meta_bits)}</div>'
    )
    body_parts.append('</div>')

    # Inject the chart + column CSS once, up front.
    body_parts.append(f'<style>{_HORIZONS_EXTRA_CSS}</style>')

    # Three Horizons SVG chart at the top — same shape the React tab shows
    # (gradients, curves, NOW marker, scenario markers placed on the curves,
    # timeline footer).
    body_parts.append(_render_horizons_chart(scenarios or []))

    # Executive Summary cards (the React tab's `ExecutiveSummaryCard` content).
    body_parts.append(render_executive_summary_cards(summaries or []))

    # Three Horizons Columns — H1/H2/H3 side-by-side with the full scenario
    # cards (timeframe / title / description / sentiment chip).
    body_parts.append(_render_horizon_columns(scenarios or []))

    # Numbered article references — resolves the [n] citations in the
    # scenario descriptions and exec-summary cards above.
    body_parts.append(_render_article_references(articles or []))

    body_parts.append(
        '<footer class="meta">'
        f'Future Horizons rendered {esc(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))}'
        '  ·  AunooAI Wiley Horizons Foresight'
        '</footer>'
    )

    return html_document(f"Future Horizons — {topic}", "\n".join(body_parts)).encode("utf-8")
