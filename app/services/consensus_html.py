"""Standalone Consensus Analysis HTML export.

Renders the per-topic Consensus Analysis (`consensus_analysis_runs.raw_output`)
into one self-contained HTML document. Used by
``GET /api/trend-convergence/consensus/{run_id}/download.html``.

Output mirrors what the React ``ConsensusCategoryCard`` displays per
category: name + description + consensus summary + sentiment distribution
bars + confidence level + outliers + strategic implications. Plus the
top-level ``key_insights`` quotes that span categories.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.services.html_report_common import (
    esc, html_document, section_open,
)

logger = logging.getLogger(__name__)


_CONSENSUS_EXTRA_CSS = """
/* Consensus card — matches the React ConsensusCategoryCard layout */
.cat-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 1.2rem 1.4rem; margin: 0 0 1.2rem 0; border-left: 5px solid #d6346c; }
.cat-eyebrow { color: #6b7280; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: .72rem; }
.cat-card h3 { font-size: 1.4rem; margin: .2rem 0 .35rem; }
.cat-articles { display: inline-block; padding: .15rem .55rem; border-radius: 4px; background: #fee9f5; color: #8b1a42; font-weight: 700; font-size: .72rem; }

/* Header row — title on the left, consensus % badge on the right */
.cat-header { display: flex; gap: 1rem; align-items: flex-start; justify-content: space-between; }
.cat-header .lhs { flex: 1; min-width: 0; }
.consensus-badge { padding: .55rem 1rem; border-radius: 999px; font-weight: 700; font-size: 1rem; border: 1px solid; flex-shrink: 0; }

/* Consensus metrics grid (5 stat boxes) */
.metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: .55rem; margin-top: 1rem; }
.metric-box { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: .55rem .7rem; }
.metric-box .label { font-size: .65rem; color: #6b7280; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
.metric-box .value { color: #111827; font-weight: 700; margin-top: .25rem; font-size: .95rem; word-break: break-word; }
.metric-badge { display: inline-block; padding: .12rem .5rem; border-radius: 4px; font-size: .75rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.metric-badge.strong   { background: #d1fae5; color: #065f46; }
.metric-badge.moderate { background: #fef3c7; color: #92400e; }
.metric-badge.emerging { background: #e0e7ff; color: #3730a3; }
.metric-badge.high     { background: #d1fae5; color: #065f46; }
.metric-badge.medium   { background: #fef3c7; color: #92400e; }
.metric-badge.low      { background: #fee2e2; color: #991b1b; }

/* Sentiment distribution */
.sent-bars { display: flex; gap: .25rem; margin: 1rem 0 .35rem; height: 16px; border-radius: 4px; overflow: hidden; background: #f3f4f6; }
.sent-bars > span { display: block; height: 100%; }
.sent-bars .positive { background: #16a34a; }
.sent-bars .neutral  { background: #94a3b8; }
.sent-bars .critical { background: #dc2626; }
.sent-legend { font-size: .78rem; color: #6b7280; display: flex; gap: 1rem; flex-wrap: wrap; }
.sent-legend .swatch { display: inline-block; width: .7rem; height: .7rem; border-radius: 2px; margin-right: .25rem; vertical-align: middle; }

/* Outliers grid (optimistic | pessimistic) */
.outliers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.1rem; }
.outliers-grid .col h4 { font-size: .85rem; letter-spacing: .04em; text-transform: uppercase; margin: 0 0 .55rem; }
.outliers-grid .col.optimistic h4   { color: #10b981; }
.outliers-grid .col.pessimistic h4  { color: #ef4444; }
.outlier-card { border: 1px solid #e5e7eb; border-radius: 6px; padding: .65rem .8rem; margin-bottom: .55rem; background: #fff; }
.outlier-card.optimistic  { border-left: 4px solid #10b981; background: #f0fdf4; }
.outlier-card.pessimistic { border-left: 4px solid #ef4444; background: #fef2f2; }
.outlier-card .scenario { color: #111827; font-weight: 700; font-size: .95rem; }
.outlier-card .details  { color: #4b5563; font-size: .9rem; margin-top: .25rem; }
.outlier-card .reference { color: #6b7280; font-size: .75rem; margin-top: .35rem; letter-spacing: .02em; }

/* Decision windows */
.dw-list { padding: 0; margin: 1rem 0 0; list-style: none; }
.dw-item { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: .65rem .85rem; margin-bottom: .55rem; border-left: 4px solid #d6346c; }
.dw-item .urg { display: inline-block; padding: .1rem .45rem; border-radius: 4px; font-size: .65rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; margin-right: .35rem; }
.dw-item .urg.critical { background: #fee2e2; color: #991b1b; }
.dw-item .urg.high     { background: #fef3c7; color: #92400e; }
.dw-item .urg.medium   { background: #e0e7ff; color: #3730a3; }
.dw-item .urg.low      { background: #f3f4f6; color: #6b7280; }
.dw-item .action  { color: #111827; font-weight: 600; }
.dw-item .meta    { color: #6b7280; font-size: .82rem; margin-top: .2rem; }
.dw-item .rationale { color: #4b5563; font-size: .9rem; margin-top: .35rem; }

/* Timeframe analysis */
.tf-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; margin-top: .9rem; }
.tf-box { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: .65rem .8rem; }
.tf-box .label { font-size: .68rem; color: #6b7280; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.tf-box .content { color: #1f2937; margin-top: .35rem; font-size: .9rem; }
.milestones-list { padding: 0; margin: .75rem 0 0; list-style: none; }
.milestone-item { display: grid; grid-template-columns: 4rem 1fr; gap: .85rem; padding: .35rem 0; align-items: flex-start; }
.milestone-item .year { color: #d6346c; font-weight: 700; font-size: 1.05rem; }
.milestone-item .title { color: #111827; font-weight: 600; font-size: .9rem; }
.milestone-item .significance { color: #6b7280; font-size: .82rem; margin-top: .15rem; }

/* Sub-section headings within a category card */
.cat-sub-title { font-size: .9rem; font-weight: 700; color: #d6346c; letter-spacing: .04em; text-transform: uppercase; margin: 1.1rem 0 .35rem; display: flex; align-items: center; gap: .35rem; }
.implication { background: #f9fafb; border-left: 4px solid #d6346c; padding: .65rem 1rem; border-radius: 4px; margin-top: 1rem; }
.implication .label { font-weight: 700; color: #d6346c; font-size: .74rem; letter-spacing: .05em; text-transform: uppercase; }
.implication p { margin: .25rem 0 0; color: #1f2937; }
.insight { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .85rem 1rem; margin-bottom: .65rem; }
.insight blockquote { margin: 0 0 .35rem; padding: 0 0 0 .85rem; border-left: 3px solid #d6346c; color: #111827; font-style: italic; }
.insight .source { color: #6b7280; font-size: .82rem; }
.cat-articles-section { margin-top: 1rem; }
.cat-articles-section h4 { font-size: .82rem; letter-spacing: .04em; text-transform: uppercase; color: #6b7280; margin: 0 0 .4rem; }
.cat-articles-list { padding: 0; margin: 0; list-style: none; border-top: 1px solid #f3f4f6; }
.cat-articles-list li { padding: .55rem 0; border-bottom: 1px solid #f3f4f6; }
.cat-articles-list .title { display: block; color: #111827; font-weight: 600; }
.cat-articles-list .title a { color: #111827; text-decoration: none; border-bottom: 1px solid transparent; }
.cat-articles-list .title a:hover { border-bottom-color: #d6346c; color: #d6346c; }
.cat-articles-list .article-meta { color: #6b7280; font-size: .82rem; margin-top: .15rem; }
.cat-articles-list .article-summary { color: #4b5563; font-size: .9rem; margin-top: .25rem; }
.cat-articles-list .sent-chip { display: inline-block; padding: .12rem .45rem; border-radius: 4px; font-size: .65rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; margin-right: .3rem; }
.cat-articles-list .sent-chip.positive { background: #d1e7dd; color: #065f46; }
.cat-articles-list .sent-chip.negative,
.cat-articles-list .sent-chip.critical { background: #f8d7da; color: #8b1a42; }
.cat-articles-list .sent-chip.neutral,
.cat-articles-list .sent-chip.mixed { background: #e2e3e5; color: #1f2937; }
.cat-articles-list .sent-chip.warning { background: #fff3cd; color: #92400e; }
"""


def _normalize_distribution(dist: dict) -> dict:
    """The React card normalizes fractions / raw counts / percentages into
    percentages. Mirror that here so the bars line up the same way."""
    p = float(dist.get("positive") or 0)
    n = float(dist.get("neutral") or 0)
    c = float(dist.get("critical") or 0)
    total = p + n + c
    if total <= 0:
        return {"positive": 0.0, "neutral": 0.0, "critical": 0.0}
    if 0.9 <= total <= 1.1:
        return {"positive": p * 100, "neutral": n * 100, "critical": c * 100}
    if total < 10:
        return {"positive": (p / total) * 100,
                "neutral":  (n / total) * 100,
                "critical": (c / total) * 100}
    return {"positive": p, "neutral": n, "critical": c}


_BADGE_PALETTE = [
    ("#a855f7", "#9333ea"),  # purple
    ("#f97316", "#ea580c"),  # orange
    ("#3b82f6", "#2563eb"),  # blue
    ("#10b981", "#059669"),  # green
    ("#ec4899", "#db2777"),  # pink
    ("#6366f1", "#4f46e5"),  # indigo
]


def _badge_strength(label: str) -> str:
    """Map a strength/quality label to a metric-badge CSS class."""
    key = (label or "").strip().lower()
    return key if key in {"strong", "moderate", "emerging", "high", "medium", "low"} else "moderate"


def _render_category(category: dict, idx: int) -> str:
    name = category.get("category_name") or f"Category {idx+1}"
    desc = category.get("category_description") or ""
    n_articles = category.get("articles_analyzed")
    consensus_type = category.get("1_consensus_type") or {}
    confidence    = category.get("3_confidence_level") or {}
    optimistic    = category.get("4_optimistic_outliers") or []
    pessimistic   = category.get("5_pessimistic_outliers") or []
    implications  = category.get("7_strategic_implications") or ""
    decision_windows = category.get("8_key_decision_windows") or []
    timeframe = category.get("9_timeframe_analysis") or {}

    cons_pct = confidence.get("majority_agreement")
    cons_pct_int = int(cons_pct) if isinstance(cons_pct, (int, float)) else None

    border_color, badge_color = _BADGE_PALETTE[idx % len(_BADGE_PALETTE)]
    badge_bg = f"{badge_color}20"  # 20% alpha hex suffix
    badge_border = f"{badge_color}40"

    parts: list = [f'<div class="cat-card" style="border-left-color:{badge_color}">']

    # Header: title + description on the left, consensus % badge on the right
    parts.append('<div class="cat-header">')
    parts.append('<div class="lhs">')
    parts.append(f'<div class="cat-eyebrow">CATEGORY {idx + 1}</div>')
    parts.append(f'<h3>{esc(name)}</h3>')
    if desc:
        parts.append(f'<p style="color:#6b7280;margin:.15rem 0 .55rem">{esc(desc)}</p>')
    chips = []
    if n_articles is not None:
        chips.append(f'<span class="cat-articles">{esc(str(int(n_articles)))} ARTICLES</span>')
    if chips:
        parts.append(" ".join(chips))
    parts.append('</div>')
    if cons_pct_int is not None:
        parts.append(
            f'<div class="consensus-badge" '
            f'style="background:{badge_bg};color:{badge_color};border-color:{badge_border}">'
            f'{cons_pct_int}% Consensus</div>'
        )
    parts.append('</div>')  # /cat-header

    # Consensus summary
    summary_text = consensus_type.get("summary") or ""
    if summary_text:
        parts.append(f'<p style="margin-top:.85rem">{esc(summary_text)}</p>')

    # Consensus Metrics grid — mirrors the React 5-stat row
    metric_cells = []
    if consensus_type.get("summary"):
        metric_cells.append(("Consensus Type", esc(consensus_type.get("summary") or ""), None))
    if cons_pct_int is not None:
        metric_cells.append(("Agreement", f"{cons_pct_int}%", None))
    if confidence.get("consensus_strength"):
        s = str(confidence["consensus_strength"])
        metric_cells.append(("Strength",
                             f'<span class="metric-badge {_badge_strength(s)}">{esc(s)}</span>',
                             True))
    if confidence.get("evidence_quality"):
        q = str(confidence["evidence_quality"])
        metric_cells.append(("Evidence Quality",
                             f'<span class="metric-badge {_badge_strength(q)}">{esc(q)}</span>',
                             True))
    if n_articles is not None:
        metric_cells.append(("Articles", esc(str(int(n_articles))), None))
    if metric_cells:
        parts.append('<div class="metrics-grid">')
        for label, value, is_html in metric_cells:
            parts.append(
                f'<div class="metric-box"><div class="label">{esc(label)}</div>'
                f'<div class="value">{value}</div></div>'
            )
        parts.append('</div>')

    # Sentiment distribution
    dist = _normalize_distribution(consensus_type.get("distribution") or {})
    p, n, c = dist["positive"], dist["neutral"], dist["critical"]
    if p + n + c > 0:
        parts.append('<div class="sent-bars">')
        parts.append(f'<span class="positive" style="width:{p:.1f}%"></span>')
        parts.append(f'<span class="neutral"  style="width:{n:.1f}%"></span>')
        parts.append(f'<span class="critical" style="width:{c:.1f}%"></span>')
        parts.append('</div>')
        parts.append(
            '<div class="sent-legend">'
            f'<span><span class="swatch" style="background:#16a34a"></span>Positive {p:.0f}%</span>'
            f'<span><span class="swatch" style="background:#94a3b8"></span>Neutral {n:.0f}%</span>'
            f'<span><span class="swatch" style="background:#dc2626"></span>Critical {c:.0f}%</span>'
            '</div>'
        )

    # Strategic implications — styled call-out box (mirrors the React box)
    if implications:
        parts.append('<div class="implication" style="margin-top:1.1rem">')
        parts.append('<div class="label">💡 Strategic Implications</div>')
        parts.append(f'<p>{esc(implications)}</p>')
        parts.append('</div>')

    # Outlier perspectives — two columns of CARDS (not bullets), each with
    # scenario name + year + details + source_percentage + reference
    has_opt = any(isinstance(o, dict) for o in optimistic)
    has_pes = any(isinstance(o, dict) for o in pessimistic)
    if has_opt or has_pes:
        parts.append('<div class="cat-sub-title">🔍 Outlier Perspectives</div>')
        parts.append('<div class="outliers-grid">')
        for which, label, group, css in (("optimistic", "Optimistic Outliers", optimistic, "optimistic"),
                                          ("pessimistic", "Pessimistic Outliers", pessimistic, "pessimistic")):
            group = [o for o in group if isinstance(o, dict)]
            parts.append(f'<div class="col {css}"><h4>{esc(label)}</h4>')
            if not group:
                parts.append(f'<p style="color:#9ca3af;font-style:italic">No {label.lower()} captured.</p>')
            for o in group[:5]:
                scen = o.get("scenario") or "—"
                year = o.get("year")
                details = o.get("details") or ""
                ref = o.get("reference") or ""
                src_pct = o.get("source_percentage")
                yr_html = f' ({esc(str(int(year)))})' if isinstance(year, (int, float)) else ''
                parts.append(f'<div class="outlier-card {css}">')
                parts.append(f'<div class="scenario">{esc(scen)}{yr_html}</div>')
                if details:
                    parts.append(f'<div class="details">{esc(details)}</div>')
                ref_bits = []
                if isinstance(src_pct, (int, float)):
                    ref_bits.append(f'{int(src_pct)}% of sources')
                if ref:
                    ref_bits.append(esc(ref))
                if ref_bits:
                    parts.append(f'<div class="reference">{" • ".join(ref_bits)}</div>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')  # /outliers-grid

    # Timeframe analysis (immediate / short-term / mid-term + key milestones)
    if isinstance(timeframe, dict) and (timeframe.get("immediate") or timeframe.get("short_term")
                                         or timeframe.get("mid_term")):
        parts.append('<div class="cat-sub-title">📅 Timeframe Analysis</div>')
        parts.append('<div class="tf-grid">')
        for label, key in (("Immediate (0-6 months)", "immediate"),
                           ("Short-term (6-18 months)", "short_term"),
                           ("Mid-term (18-36 months)", "mid_term")):
            content = (timeframe.get(key) or "").strip()
            if not content:
                continue
            parts.append(
                f'<div class="tf-box"><div class="label">{esc(label)}</div>'
                f'<div class="content">{esc(content)}</div></div>'
            )
        parts.append('</div>')
        milestones = timeframe.get("key_milestones") or []
        milestones = [m for m in milestones if isinstance(m, dict)]
        if milestones:
            parts.append('<div style="margin-top:1rem">')
            parts.append('<div style="font-size:.78rem;font-weight:700;color:#6b7280;letter-spacing:.04em;text-transform:uppercase">Key Milestones</div>')
            parts.append('<ul class="milestones-list">')
            for m in milestones:
                year = m.get("year") or ""
                title = m.get("milestone") or ""
                sig = m.get("significance") or ""
                parts.append('<li class="milestone-item">')
                parts.append(f'<div class="year">{esc(str(year))}</div>')
                parts.append('<div>')
                if title:
                    parts.append(f'<div class="title">{esc(title)}</div>')
                if sig:
                    parts.append(f'<div class="significance">{esc(sig)}</div>')
                parts.append('</div></li>')
            parts.append('</ul></div>')

    # Decision windows
    dw = [d for d in (decision_windows or []) if isinstance(d, dict)]
    if dw:
        parts.append('<div class="cat-sub-title">⏱ Key Decision Windows</div>')
        parts.append('<ul class="dw-list">')
        for d in dw[:5]:
            urg = (d.get("urgency") or "medium").strip().lower()
            action = d.get("action") or ""
            window = d.get("window") or ""
            owner  = d.get("owner") or ""
            rationale = d.get("rationale") or ""
            parts.append('<li class="dw-item">')
            parts.append(
                f'<span class="urg {esc(urg)}">{esc(urg.upper())}</span>'
                f'<span class="action">{esc(action)}</span>'
            )
            meta_bits = []
            if window:
                meta_bits.append(esc(window))
            if owner:
                meta_bits.append(f"Owner: {esc(owner)}")
            if meta_bits:
                parts.append(f'<div class="meta">{" · ".join(meta_bits)}</div>')
            if rationale:
                parts.append(f'<div class="rationale">{esc(rationale)}</div>')
            parts.append('</li>')
        parts.append('</ul>')

    # Key articles cited for this category
    articles = category.get("6_key_articles") or []
    articles = [a for a in articles if isinstance(a, dict) and (a.get("title") or "").strip()]
    if articles:
        parts.append('<div class="cat-articles-section">')
        parts.append(f'<h4>Supporting articles ({len(articles)})</h4>')
        parts.append('<ul class="cat-articles-list">')
        for a in articles:
            title = a.get("title") or ""
            url = a.get("url") or ""
            summary = (a.get("summary") or "").strip()
            sentiment = (a.get("sentiment") or "neutral").lower().split("/")[0].strip() or "neutral"
            relevance = a.get("relevance_score")
            title_html = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(title)}</a>'
                          if url else esc(title))
            parts.append('<li>')
            parts.append(
                f'<span class="title"><span class="sent-chip {esc(sentiment)}">{esc(sentiment.upper())}</span>'
                f'{title_html}</span>'
            )
            meta_bits = []
            if isinstance(relevance, (int, float)):
                try:
                    val = float(relevance)
                    if val > 1.0:
                        meta_bits.append(f"Relevance {int(val)}")
                    else:
                        meta_bits.append(f"Relevance {val:.2f}")
                except Exception:
                    pass
            if url:
                try:
                    host = url.split("//", 1)[-1].split("/", 1)[0]
                    if host:
                        meta_bits.append(host)
                except Exception:
                    pass
            if meta_bits:
                parts.append(f'<div class="article-meta">{esc("  ·  ".join(meta_bits))}</div>')
            if summary:
                parts.append(f'<div class="article-summary">{esc(summary)}</div>')
            parts.append('</li>')
        parts.append('</ul></div>')

    parts.append('</div>')
    return "\n".join(parts)


def _render_key_insights(insights: list) -> str:
    insights = [i for i in (insights or []) if isinstance(i, dict)]
    if not insights:
        return ""
    parts = [section_open("Key Insights", eyebrow="CROSS-CATEGORY QUOTES")]
    for ins in insights:
        quote = ins.get("quote") or ""
        source = ins.get("source") or ""
        relevance = ins.get("relevance") or ""
        if not quote:
            continue
        parts.append('<div class="insight">')
        parts.append(f'<blockquote>{esc(quote)}</blockquote>')
        meta_bits = [b for b in (source, relevance) if b]
        if meta_bits:
            parts.append(f'<div class="source">{esc("  ·  ".join(meta_bits))}</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def build_consensus_html(
    topic: str,
    payload: dict,
    *,
    generated_at: Optional[str] = None,
    model_used: Optional[str] = None,
) -> bytes:
    """Render the Consensus Analysis for a topic as standalone HTML.

    ``payload`` is the parsed ``consensus_analysis_runs.raw_output`` dict.
    Expected keys: ``categories[]``, ``key_insights[]``, ``generated_at``,
    ``model_used``, ``articles_analyzed`` — but any missing field just
    short-circuits its section.
    """
    payload = payload or {}
    categories = payload.get("categories") or []
    key_insights = payload.get("key_insights") or []
    n_articles = payload.get("articles_analyzed") or payload.get("total_articles_found")
    gen = generated_at or payload.get("generated_at") or ""
    model = model_used or payload.get("model_used") or ""

    body_parts: list = []

    # Cover
    body_parts.append('<div class="cover">')
    body_parts.append('<div class="eyebrow">WILEY HORIZONS · CONSENSUS ANALYSIS</div>')
    body_parts.append(f'<h1>{esc(topic)}</h1>')
    body_parts.append('<div class="subtitle">Cross-source convergence  ·  Produced by AunooAI</div>')
    meta_bits = []
    if gen:
        meta_bits.append(esc(gen[:19].replace("T", " ")))
    if model:
        meta_bits.append(f"model: {esc(model)}")
    if n_articles:
        meta_bits.append(f"{int(n_articles)} articles")
    if categories:
        meta_bits.append(f"{len(categories)} categories")
    if meta_bits:
        body_parts.append(
            f'<div style="margin-top:1rem;color:#fbcfe4;font-size:.92rem">'
            f'{"  ·  ".join(meta_bits)}</div>'
        )
    body_parts.append('</div>')

    # Category cards
    if categories:
        body_parts.append(section_open("Consensus by Category",
                                      eyebrow="CROSS-SOURCE THEMES"))
        for i, cat in enumerate(categories):
            if isinstance(cat, dict):
                body_parts.append(_render_category(cat, i))
        body_parts.append('</section>')

    # Cross-category key insights
    body_parts.append(_render_key_insights(key_insights))

    # Footer
    body_parts.append(
        '<footer class="meta">'
        f'Consensus Analysis rendered {esc(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))}'
        '  ·  AunooAI Wiley Horizons Foresight'
        '</footer>'
    )

    return html_document(
        f"Consensus Analysis — {topic}",
        f'<style>{_CONSENSUS_EXTRA_CSS}</style>' + "\n".join(body_parts),
    ).encode("utf-8")
