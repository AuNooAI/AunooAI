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
import logging as _logging
import re as _re
import urllib.parse as _urlparse

from app.compliance.ai_disclosure import (
    disclosure_footer_html as _ai_footer,
    html_meta_tags as _ai_meta,
)

_log = _logging.getLogger(__name__)


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

/* Executive Summary card — "Based on scenarios" footer */
.es-sources { margin-top: .9rem; padding-top: .8rem; border-top: 1px dashed #e5e7eb; }
.es-sources .label { color: #6b7280; font-weight: 700; font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; margin-bottom: .3rem; }
.es-sources ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .2rem; }
.es-sources li { color: #1f2937; font-size: .9rem; }
.es-srctag { display: inline-block; padding: 0 .35rem; border-radius: 3px; font-weight: 700; font-size: .68rem; letter-spacing: .04em; color: #fff; vertical-align: baseline; margin-right: .35rem; }
.es-srctag.h1 { background: #d6346c; }
.es-srctag.h2 { background: #b45309; }
.es-srctag.h3 { background: #0e7490; }

/* Inline citations — clickable [N] markers that jump to the article ref list */
a.cite { display: inline-block; padding: 0 .3rem; margin: 0 .05rem; background: #fee9f5; color: #8b1a42; border-radius: 3px; font-weight: 700; font-size: .82em; text-decoration: none; vertical-align: baseline; }
a.cite:hover { background: #fbcfe4; }

/* Article references list (target for the [N] anchors) */
.article-refs { padding-left: 1.3rem; margin: 0; }
.article-refs li { padding: .55rem 0; border-bottom: 1px solid #f3f4f6; scroll-margin-top: 1rem; }
.article-refs li:last-child { border-bottom: 0; }
.article-refs li:target { background: #fff7e6; box-shadow: inset 4px 0 0 #d6346c; padding-left: .6rem; }
.article-refs .title { font-weight: 600; color: #111827; }
.article-refs .ref-meta { color: #6b7280; font-size: .82rem; margin-top: .15rem; }

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


_CITATION_RE = _re.compile(r"\[(\d{1,3})\]")


def linkify_citations(escaped_html: str, articles: list | None = None) -> str:
    """Wrap ``[N]`` markers in already-HTML-escaped text with anchors.

    When ``articles`` is given (the numbered corpus the LLM cited),
    each ``[N]`` becomes an anchor pointing DIRECTLY at the publisher's
    URL (``articles[N-1]["uri"]`` / ``["url"]``), opens in a new tab.
    This is what a reader expects from a clickable citation.

    Without ``articles`` (or for an out-of-range ``N``), falls back to
    the in-document jump ``#ref-N`` — still useful when the page also
    renders a numbered references list at the bottom.
    """
    if not escaped_html or "[" not in escaped_html:
        return escaped_html or ""

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
            return (f'<a class="cite" href="{esc(href)}" target="_blank" '
                    f'rel="noopener">[{n_str}]</a>')
        return f'<a class="cite" href="#ref-{n_str}">[{n_str}]</a>'

    return _CITATION_RE.sub(_replace, escaped_html)


def esc_cites(v, articles: list | None = None) -> str:
    """``esc()`` + ``linkify_citations()`` — use anywhere body text may carry
    ``[N]`` citations. Pass ``articles`` to make the ``[N]`` links open the
    publisher URL directly (the common, reader-expected behaviour).
    """
    return linkify_citations(esc(v), articles=articles)


_TITLE_PUBLISHER_RE = _re.compile(r"\s+[–—-]\s+([^–—-]{2,60})\s*$")

_GOOGLE_NEWS_RE = _re.compile(r"^https?://(?:[a-z0-9.-]+\.)?google\.com/", _re.IGNORECASE)


def _google_search_url(title: str, publisher: str = "") -> str:
    """Build a Google Search URL that lands on the article.

    Decoding ``news.google.com/rss/articles/CBMi…`` redirects offline is
    fragile (Google rotates the encoding; HEAD lands on a consent page).
    A search query is short, clickable, and reliably brings the article
    up as the first hit — better UX than the 500-char redirect.
    """
    q = (title or "").strip()
    if publisher:
        q = f'{q} {publisher}'.strip()
    return f"https://www.google.com/search?q={_urlparse.quote_plus(q)}"


def resolve_google_news_uris(articles: list, **_kwargs) -> None:
    """Rewrite Google News redirect URIs in place to a short search URL.

    Mutates each article's URI field — works on both ``uri`` and ``url``
    keys (different loaders use different conventions). If the URL points
    at a Google aggregator, replace it with a ``google.com/search?q=…``
    URL built from the title + publisher. Non-Google URIs are left
    untouched. Compatible with the older HTTP-resolving signature —
    extra kwargs are accepted and ignored.
    """
    if not articles:
        return
    for a in articles:
        if not isinstance(a, dict):
            continue
        # Find whichever URL key this article uses.
        key = "uri" if a.get("uri") else ("url" if a.get("url") else None)
        if not key:
            continue
        uri = a.get(key) or ""
        if not _GOOGLE_NEWS_RE.match(uri):
            continue
        cleaned = clean_article_ref(a)
        a[key] = _google_search_url(cleaned["title"], cleaned["source"])


def clean_article_ref(article: dict) -> dict:
    """Return ``{title, uri, source, date}`` with two cleanups applied:

    1. **Source promotion.** Articles ingested via Google News carry
       ``news_source = "news.google.com"`` and a long redirect URI like
       ``https://news.google.com/rss/articles/CBMi…``. The real publisher
       is buried in the title's trailing `" - Publisher"` segment. When
       the stored source is empty or a known aggregator, hoist that
       publisher into ``source`` so the reader sees the actual outlet.
    2. **Title suffix strip.** Once the publisher is in ``source``, drop
       the `" - Publisher"` tail from the displayed title — the reader
       gets the headline + outlet shown as separate fields rather than a
       stuffed string.

    Accepts a dict with any subset of ``title / uri / url / source /
    news_source / date / publication_date``. Always returns the same four
    keys. Doesn't touch the URI — the redirect still works.
    """
    title = (article.get("title") or "").strip()
    uri = article.get("uri") or article.get("url") or ""
    source = (article.get("source") or article.get("news_source") or "").strip()
    date = (article.get("date") or article.get("publication_date") or "")[:10]

    aggregators = {"news.google.com", "google.com", "consent.google.com"}
    publisher = ""
    m = _TITLE_PUBLISHER_RE.search(title)
    if m:
        publisher = m.group(1).strip()

    if publisher and (not source or source.lower() in aggregators):
        source = publisher
        title = _TITLE_PUBLISHER_RE.sub("", title)

    return {"title": title, "uri": uri, "source": source, "date": date}


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
        + _ai_meta()  # EU AI Act Art. 50 machine-readable marker
        + f'<title>{esc(title)}</title>'
        f'<style>{BASE_CSS}</style></head><body>'
        '<div class="container">'
        + body
        + _ai_footer()  # EU AI Act Art. 50 visible disclosure
        + '</div></body></html>'
    )


def render_executive_summary_cards(cards: list, articles: list | None = None) -> str:
    """Reusable Executive Summary card stack — same shape used by both the
    Topic Report HTML and the standalone Future Horizons HTML. Each ``card``
    is one entry from ``analysis_versions_v2[horizons_exec_summary_*]``.

    ``articles`` (optional) is the numbered corpus the LLM cited; when
    given, any ``[N]`` markers in card body text become direct anchors
    to the publisher URLs.
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
            parts.append(f'<p>{esc_cites(opening, articles)}</p>')
        if mv.get("statement"):
            pct = mv.get("percentage_range") or ""
            label = "Minority view" + (f"  ·  {pct}" if pct else "")
            parts.append('<div class="es-minority">')
            parts.append(f'<div class="label">{esc(label)}</div>')
            parts.append(f'<div>{esc_cites(mv.get("statement") or "", articles)}</div>')
            parts.append('</div>')
        if signal:
            label = "Primary signal" + (f"  ·  {cons_pct} consensus" if cons_pct else "")
            parts.append(f'<div class="es-signal-label">{esc(label)}</div>')
            parts.append(f'<p class="es-signal">{esc_cites(signal, articles)}</p>')
        # Source scenarios — list the H1/H2/H3 scenario titles the card
        # draws from, so the reader can trace each summary back to the
        # underlying forecast scenarios.
        src = [s for s in (c.get("source_scenarios") or []) if isinstance(s, dict)]
        if src:
            parts.append('<div class="es-sources">')
            parts.append('<div class="label">Based on scenarios</div>')
            parts.append('<ul>')
            for s in src:
                h = (s.get("horizon") or "").upper()
                t = (s.get("title") or "").strip()
                if not t:
                    continue
                tag = (f'<span class="es-srctag {h.lower()}">{esc(h)}</span>'
                       if h else "")
                parts.append(f'<li>{tag} {esc(t)}</li>')
            parts.append('</ul></div>')

        if (fa.get("condition") or fb.get("condition") or
            aw_a.get("action") or aw_p.get("action")):
            parts.append('<div class="es-bottom">')
            if fa.get("condition") or fb.get("condition"):
                parts.append('<div class="es-fork"><div class="label">Decision fork</div>')
                if fa.get("condition") or fa.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker ok">✔</span> {esc_cites(fa.get("condition") or "", articles)}</div>')
                    if fa.get("outcome"):
                        parts.append(f'<div class="outcome">→ {esc_cites(fa.get("outcome") or "", articles)}</div>')
                    parts.append('</div>')
                if fb.get("condition") or fb.get("outcome"):
                    parts.append('<div class="row">')
                    parts.append(f'<div><span class="marker alt">!</span> {esc_cites(fb.get("condition") or "", articles)}</div>')
                    if fb.get("outcome"):
                        parts.append(f'<div class="outcome">→ {esc_cites(fb.get("outcome") or "", articles)}</div>')
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
                        parts.append(f'<div class="action">{esc_cites(act, articles)}</div>')
                parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def render_scenarios(scenarios: list, articles: list | None = None) -> str:
    """Render Three Horizons scenarios grouped under H1/H2/H3 headers.

    ``articles`` (optional) is the numbered corpus the LLM cited; when
    given, any ``[N]`` markers in scenario descriptions become direct
    anchors to the publisher URLs.
    """
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
                parts.append(f'<p class="desc">{esc_cites(desc, articles)}</p>')
            parts.append('</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)
