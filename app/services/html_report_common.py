"""Shared HTML rendering primitives for the on-demand foresight exports.

All three foresight HTML exports (Topic Report, Future Horizons, Consensus
Analysis) share the same Wiley pink/navy palette + base layout so the
downloads look like one consistent product. This module owns the base
``BASE_CSS`` block + a few small primitives (escape helper, section
opener) so each renderer module is just the content layout.

Keep this file *thin* — anything tab-specific belongs in the per-tab
``*_html.py`` builder.
"""
from __future__ import annotations

import html as _html


# Wiley pink + navy palette. Mirrors topic_report_pptx + forecast_pptx_export
# so the PPTX and HTML feel like one deliverable.
BASE_CSS = """
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

/* Three-card row */
.three-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: .85rem; }
.three-cards .card { margin: 0; }
.three-cards .card-header { color: #fff; padding: .55rem .8rem; border-radius: 4px; font-weight: 700; font-size: .9rem; }
.three-cards .card-header.teal { background: #d6346c; }
.three-cards .card-header.navy { background: #111827; }

/* Executive summary card (also used outside Topic Reports) */
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
.es-fork .marker.ok { color: #047857; font-weight: 700; }
.es-fork .marker.alt { color: #b45309; font-weight: 700; }
.es-fork .outcome { color: #4b5563; font-size: .92rem; margin-top: .15rem; }
.es-window .tf { font-weight: 700; color: #d6346c; font-size: .78rem; letter-spacing: .04em; text-transform: uppercase; margin-top: .55rem; }
.es-window .action { color: #1f2937; margin-top: .15rem; }

/* Bullet list */
.bullet-list { padding: 0; margin: 0; list-style: none; }
.bullet-list li { padding: .55rem 0 .55rem 1.5rem; position: relative; border-bottom: 1px solid #f3f4f6; }
.bullet-list li:last-child { border-bottom: 0; }
.bullet-list li::before { content: ""; position: absolute; left: 0; top: 1.0rem; width: .6rem; height: .6rem; background: #d6346c; border-radius: 2px; }

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

/* Articles table */
.articles { width: 100%; border-collapse: collapse; }
.articles td { padding: .55rem .35rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.sent-chip { display: inline-block; padding: .15rem .55rem; border-radius: 4px; font-size: .68rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.sent-chip.positive, .sent-chip.breakthrough { background: #d1e7dd; color: #065f46; }
.sent-chip.negative, .sent-chip.critical { background: #f8d7da; color: #8b1a42; }
.sent-chip.warning { background: #fff3cd; color: #92400e; }
.sent-chip.neutral, .sent-chip.mixed { background: #e2e3e5; color: #1f2937; }

/* Consensus-specific */
.consensus-meter { display: flex; align-items: center; gap: .55rem; margin: .35rem 0; }
.consensus-bar { flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }
.consensus-bar > span { display: block; height: 100%; background: #d6346c; }
.consensus-value { font-weight: 700; color: #111827; font-size: .9rem; min-width: 3rem; text-align: right; }

/* Footer */
footer.meta { color: #6b7280; font-size: .82rem; margin-top: 3rem; text-align: center; }

@media (max-width: 720px) {
  .three-cards, .es-bottom { grid-template-columns: 1fr; }
}
"""


def esc(v) -> str:
    """HTML-escape any scalar value, returning empty string for None."""
    if v is None:
        return ""
    return _html.escape(str(v))


def section_open(title: str, *, eyebrow: str = "") -> str:
    """Open a ``.section`` with an optional pink eyebrow + title heading."""
    parts = ['<section class="section">']
    if eyebrow:
        parts.append(f'<p class="section-eyebrow">{esc(eyebrow)}</p>')
    parts.append(f'<h2>{esc(title)}</h2>')
    return "\n".join(parts)


def html_document(title: str, body: str) -> str:
    """Wrap a body fragment in the standard self-contained HTML document."""
    return (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{esc(title)}</title>'
        f'<style>{BASE_CSS}</style></head><body>'
        '<div class="container">'
        + body
        + '</div></body></html>'
    )


def render_executive_summary_cards(cards: list) -> str:
    """Reusable Executive Summary card stack — same shape used by both the
    Topic Report HTML and the standalone Future Horizons HTML. Each ``card``
    is one entry from ``analysis_versions_v2[horizons_exec_summary_*]``.
    """
    if not cards:
        return ""
    parts = [section_open("Executive Summary", eyebrow="HORIZON-ANCHORED VIEW")]
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
        aw_a = aw.get("assessment") or {}
        aw_p = aw.get("positioning") or {}

        parts.append('<div class="es-card">')
        parts.append(f'<div class="es-eyebrow">Card {k} of {len(cards)}</div>')
        parts.append(f'<h3>{esc(title)}</h3>')
        parts.append('<div class="es-meta">')
        parts.append(f'<span class="es-pill {horizon}">{horizon.upper()} · {esc(h_label)}</span>')
        if cons_pct:
            parts.append(f'<span class="es-pill consensus">{cons_pct} CONSENSUS</span>')
        parts.append('</div>')
        if opening:
            parts.append(f'<p>{esc(opening)}</p>')
        if mv.get("statement"):
            pct = mv.get("percentage_range") or ""
            label = "Minority view" + (f"  ·  {pct}" if pct else "")
            parts.append('<div class="es-minority">')
            parts.append(f'<div class="label">{esc(label)}</div>')
            parts.append(f'<div>{esc(mv.get("statement") or "")}</div>')
            parts.append('</div>')
        if signal:
            label = "Primary signal" + (f"  ·  {cons_pct} consensus" if cons_pct else "")
            parts.append(f'<div class="es-signal-label">{esc(label)}</div>')
            parts.append(f'<p class="es-signal">{esc(signal)}</p>')
        if (fa.get("condition") or fb.get("condition") or
            aw_a.get("action") or aw_p.get("action")):
            parts.append('<div class="es-bottom">')
            if fa.get("condition") or fb.get("condition"):
                parts.append('<div class="es-fork"><div class="label">Decision fork</div>')
                if fa.get("condition") or fa.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker ok">✔</span> {esc(fa.get("condition") or "")}</div>')
                    if fa.get("outcome"):
                        parts.append(f'<div class="outcome">→ {esc(fa.get("outcome") or "")}</div>')
                    parts.append('</div>')
                if fb.get("condition") or fb.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker alt">!</span> {esc(fb.get("condition") or "")}</div>')
                    if fb.get("outcome"):
                        parts.append(f'<div class="outcome">→ {esc(fb.get("outcome") or "")}</div>')
                    parts.append('</div>')
                parts.append('</div>')
            if aw_a.get("action") or aw_p.get("action"):
                parts.append('<div class="es-window"><div class="label">Your window</div>')
                for row in (aw_a, aw_p):
                    tf = row.get("timeframe") or ""
                    act = row.get("action") or ""
                    if tf:
                        parts.append(f'<div class="tf">{esc(tf)}</div>')
                    if act:
                        parts.append(f'<div class="action">{esc(act)}</div>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def render_scenarios(scenarios: list) -> str:
    """Render Three Horizons scenarios grouped under H1/H2/H3 headers."""
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
    parts = [section_open("Three Horizons", eyebrow="FORECAST SCENARIOS")]
    for horizon in ("h1", "h2", "h3"):
        group = by_horizon[horizon]
        if not group:
            continue
        parts.append('<div class="horizon-section">')
        parts.append(f'<h3 class="{horizon}">{esc(labels[horizon])}</h3>')
        for s in group:
            timeframe = s.get("timeframe") or ""
            sentiment = s.get("sentiment") or ""
            meta = "  ·  ".join([b for b in (horizon.upper(), timeframe, sentiment) if b])
            parts.append(f'<div class="scenario-card {horizon}">')
            parts.append(f'<div class="scenario-meta">{esc(meta)}</div>')
            parts.append(f'<h4>{esc(s.get("title") or "—")}</h4>')
            desc = (s.get("description") or "").strip()
            if desc:
                parts.append(f'<p class="desc">{esc(desc)}</p>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)
