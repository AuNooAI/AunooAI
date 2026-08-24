"""A market as one self-contained HTML file.

Deliberately thin. ``html_report_common`` already supplies the document shell,
the base stylesheet and — importantly — the EU AI Act Article 50 markers, both
the machine-readable meta tag and the visible footer. Hand-rolling a second
document wrapper here would duplicate that and quietly ship a report without
the disclosure.

Charts are **inline SVG**, drawn from the stored figures with no library. That
is the same choice ``horizons_html`` makes and for the same reason: the page
has to render with no network access at all, so a CDN chart library or a remote
image is not an option. matplotlib PNGs are the deck path, not this one.

Nothing here computes. It renders what ``market_analysis`` and
``market_publish`` already returned.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.html_report_common import esc, html_document, section_open

logger = logging.getLogger(__name__)

# The report's own styles, appended to BASE_CSS. Only what the shared sheet
# does not already carry.
EXTRA_CSS = """
.mm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: .7rem; margin: .8rem 0 1rem; }
.mm-stat { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .7rem .85rem; }
.mm-stat .v { font-size: 1.5rem; font-weight: 700; color: #111827; }
.mm-stat .l { font-size: .72rem; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; }
.mm-stat .h { font-size: .74rem; color: #6b7280; margin-top: .25rem; }
.mm-cover { font-size: .76rem; color: #92400e; background: #fff8e6;
            border: 1px solid #fde68a; border-radius: 5px; padding: .3rem .5rem;
            display: inline-block; margin: 0 0 .6rem; }
.mm-cover.full { color: #065f46; background: #ecfdf5; border-color: #a7f3d0; }
.mm-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
.mm-table th { text-align: left; font-size: .7rem; text-transform: uppercase;
               letter-spacing: .05em; color: #6b7280; padding: .35rem .4rem;
               border-bottom: 1px solid #e5e7eb; }
.mm-table td { padding: .35rem .4rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
.mm-num { text-align: right; font-variant-numeric: tabular-nums; }
.mm-kind { display: inline-block; font-size: .68rem; padding: .1rem .4rem;
           border-radius: 4px; background: #ecfdf5; color: #065f46;
           border: 1px solid #a7f3d0; }
.mm-src { font-size: .74rem; color: #6b7280; }
svg.mm-chart { display: block; width: 100%; height: auto; }
details summary { cursor: pointer; font-size: .82rem; color: #475569;
                  padding: .3rem 0; }
.mm-reading { font-size: .95rem; margin: .2rem 0 .6rem; display: flex;
             align-items: center; gap: 6px; font-weight: 600; }
.mm-reading .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.mm-reading.pos { color: #0f7a4e; }
.mm-reading.pos .dot { background: #30a46c; }
.mm-reading.neg { color: #be123c; }
.mm-reading.neg .dot { background: #e5484d; }
.mm-reading.neutral { color: #374151; }
.mm-reading.neutral .dot { background: #9ca3af; }
"""


def _stat(label: str, value: str, hint: str = "") -> str:
    return (f'<div class="mm-stat"><div class="l">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div>'
            + (f'<div class="h">{esc(hint)}</div>' if hint else "")
            + "</div>")


def _signed(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"+{value:g}" if value > 0 else f"{value:g}"


def _reading(net: Optional[float], *, subject: str = "Coverage in the latest week"
            ) -> str:
    """A plain-English positive/negative/mixed line with a colored dot.

    A raw signed percentage ("+22%") makes a reader do the sign-reading
    themselves. This says it in words and repeats the call in color, so
    color is never the only signal.
    """
    if net is None:
        return ""
    tone = "pos" if net > 10 else "neg" if net < -10 else "neutral"
    verb = "leaned positive" if tone == "pos" else \
           "leaned negative" if tone == "neg" else "was mixed"
    sign = "+" if net > 0 else ""
    return (f'<p class="mm-reading {tone}"><span class="dot"></span>'
            f'{esc(subject)} {verb} ({sign}{net}%).</p>')


def _money(musd: Optional[float]) -> str:
    """A funding total in the unit a reader would actually say out loud.

    $1,038M is technically correct and reads like a spreadsheet cell. Above
    $1,000M this switches to billions, which is how anyone would describe the
    figure in a sentence.
    """
    if musd is None:
        return "—"
    if musd >= 1000:
        return f"${musd / 1000:.3f}B"
    return f"${musd:,.0f}M"


def _fmt_range(start: str, end: str) -> str:
    """An ISO date pair as a reader would write it: '24 July–22 August 2026'.

    ``days=30`` alone leaves the actual boundary to the reader's arithmetic;
    every other report on this platform states the period it covers in
    words, not just as a parameter.
    """
    from datetime import date
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return f"{start} – {end}"
    if s.year == e.year:
        return f"{s.strftime('%-d %B')}–{e.strftime('%-d %B %Y')}"
    return f"{s.strftime('%-d %B %Y')} – {e.strftime('%-d %B %Y')}"


def _pct_row(label: str, measured: int, total: int) -> str:
    pct = f"{measured / total * 100:.0f}%" if total else "—"
    return (f'<tr><td>{esc(label)}</td>'
            f'<td class="mm-num">{measured} / {total}</td>'
            f'<td class="mm-num">{pct}</td></tr>')


def _coverage(coverage: Optional[Dict[str, Any]]) -> str:
    """The denominator, rendered so it cannot be skipped past.

    Amber when partial, green when complete. A chart in this report without one
    of these is a chart whose author forgot to say what it rests on. The
    ``label`` coming from ``market_analysis._coverage()`` is already a full
    clause ("81 of 83 vendors have a founding year") — no "Based on" prefix
    needed, and stacking one on produced "Based on 81 of 83 vendors have a
    founding year," which does not parse as a sentence.
    """
    if not coverage:
        return ""
    cls = "mm-cover full" if coverage.get("complete") else "mm-cover"
    label = coverage.get("label", "")
    return f'<div class="{cls}">{esc(label[:1].upper() + label[1:] if label else label)}.</div>'


# ---------------------------------------------------------------------------
# Which coverage items are material
# ---------------------------------------------------------------------------
#
# The matched corpus mixes deduplicated vendor announcements with practitioner
# chatter, "for hire" posts, and repeated coverage of the same story from a
# dozen accounts. A flat list of 1,313 items reads as noise even when a real
# acquisition is sitting in it. This is a keyword heuristic, not a model call —
# consistent with the rest of this module, which reads what a regex-based scan
# already decided rather than asking an LLM to re-judge it. A vendor's own post
# already carries a real ``review_kind`` from that review pass; only
# third-party coverage needs the regex.

_MATERIAL_PATTERNS = (
    ("acquisition", re.compile(r"\bacqui(r(e|es|ed|ing)|sition)\b", re.I)),
    ("funding", re.compile(r"\braises?\s+\$|\bseries\s+[a-e]\b|\bfunding\s+round\b", re.I)),
    ("partnership", re.compile(r"\bpartner(s|ed|ship)?\b", re.I)),
    ("launch", re.compile(r"\blaunch(es|ed|ing)?\b|\bunveils?\b|\bintroduc(es|ed|ing)\b", re.I)),
    ("customer", re.compile(r"\bselects?\b|\bdeploys?\b|\bnames\s+\w+\s+as\s+(a\s+)?customer\b", re.I)),
)


def _material_kind(article: Dict[str, Any]) -> Optional[str]:
    """The kind of material development this item is, or None.

    A vendor's own post already carries ``review_kind`` from the review pass
    in ``market_analysis.signal_noise`` — trusted as-is, including
    ``hiring``, which despite the name is a named appointment ("Ryan Burke
    as VP Sales"), not an open job listing — those come from a different
    table entirely and were never review-classified this way. Everything
    else (third-party news, research) is matched against the same keyword
    set used to describe vendor claims, so a headline and a vendor post are
    judged the same way.
    """
    kind = article.get("review_kind")
    if kind in ("launch", "partnership", "customer", "funding", "acquisition", "hiring"):
        return kind
    text_value = f"{article.get('title') or ''} {article.get('summary') or ''}"
    for name, pattern in _MATERIAL_PATTERNS:
        if pattern.search(text_value):
            return name
    return None


def _corroboration(article: Dict[str, Any]) -> str:
    """Whether a claim rests on the vendor's own word or on more than that.

    Reuses the same-story clustering already computed for dedup — a vendor
    post whose cluster also holds a non-vendor item has independent coverage
    of the same event; one with no cluster, or a cluster of vendor posts
    only, does not. This is a real check against what was actually
    collected, not a guess: it can only ever say "vendor source only" when
    that is genuinely all this system has seen.
    """
    if article.get("article_class") not in ("vendor", "social"):
        return "Third-party reporting"
    cluster = article.get("cluster")
    others = (cluster or {}).get("others") or []
    if any((o.get("article_class") not in ("vendor", "social")) for o in others):
        size = cluster["size"]
        return f"Independently corroborated ({size} sources)"
    return "Vendor source only"


_STORY_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "is", "are", "its", "it's", "new", "ai", "soc",
}


def _merge_same_story(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A second, looser dedup pass scoped to one already-narrow kind group.

    ``market_corpus.cluster()`` requires 6+ non-stopword content words
    before it will even compare two items — a deliberate floor for
    clustering the *whole* corpus, where a short overlap is too likely to be
    coincidence. That floor also means a short tweet-style post can never be
    matched to anything, so four separate posts about the same Cribl/Radiant
    acquisition survived as four rows. Within one kind group the search
    space is small and already homogeneous — everything here already passed
    the same event-type classification — so a looser 2-shared-word bar is
    safe here even though it would false-merge too eagerly applied globally.
    """
    def _words(a: Dict[str, Any]) -> set:
        text_value = f"{a.get('title') or ''} {a.get('summary') or ''}".lower()
        text_value = re.sub(r"https?://\S+", " ", text_value)
        return {w for w in re.findall(r"[a-z][a-z0-9']{3,}", text_value)
                if w not in _STORY_STOP}

    word_sets = [_words(a) for a in rows]
    used = [False] * len(rows)
    out: List[Dict[str, Any]] = []
    for i, a in enumerate(rows):
        if used[i]:
            continue
        used[i] = True
        merged = dict(a)
        base = a.get("cluster") or {}
        extra_size, extra_others = 0, []
        for j in range(i + 1, len(rows)):
            if used[j] or len(word_sets[i] & word_sets[j]) < 2:
                continue
            used[j] = True
            other_cluster = rows[j].get("cluster") or {}
            extra_size += other_cluster.get("size", 1)
            extra_others.append(rows[j])
            extra_others.extend(other_cluster.get("others", []))
        if extra_others:
            merged["cluster"] = {
                "size": base.get("size", 1) + extra_size,
                "others": base.get("others", []) + extra_others,
            }
        out.append(merged)
    return out


def _coverage_row(a: Dict[str, Any], *, kind: Optional[str] = None) -> str:
    cluster = a.get("cluster")
    extra = (f' <span class="mm-kind">+{cluster["size"] - 1} more like this</span>'
             if cluster and cluster.get("size", 1) > 1 else "")
    badge = f'<span class="mm-kind">{esc(kind)}</span> ' if kind else ""
    # A named-hire post's own title is usually generic company chatter
    # ("Security teams are drowning in alerts") — the reviewer already
    # extracted who actually joined into review_reason, which is what a
    # reader of an "Executive changes" list wants to see.
    headline = (a.get("review_reason") if kind == "hiring" and a.get("review_reason")
                else a.get("title")) or a["uri"]
    return (f'<tr><td>{badge}<a href="{esc(a["uri"])}">'
            f'{esc(headline)}</a>{extra}'
            f'<div class="mm-src">{esc(a.get("news_source") or "")}'
            f' · {esc((a.get("published") or "")[:10])}</div></td></tr>')


# ---------------------------------------------------------------------------
# Charts, hand-drawn as SVG
# ---------------------------------------------------------------------------

def _bar_chart(rows: List[Dict[str, Any]], *, label_key: str, value_key: str,
               height: int = 180, colour: str = "#475569") -> str:
    """A plain vertical bar chart.

    Written out rather than pulled from a library because the page must render
    with no network access. Forty lines of SVG is cheaper than that constraint
    being violated by a script tag someone adds later.
    """
    rows = [r for r in rows if r.get(value_key) is not None]
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l, pad_b, pad_t = 720, 34, 42, 10
    peak = max(float(r[value_key]) for r in rows) or 1
    plot_h = height - pad_b - pad_t
    slot = (width - pad_l - 8) / len(rows)
    bar_w = max(3.0, slot * 0.68)

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" '
             f'role="img" preserveAspectRatio="xMidYMid meet">']
    # Baseline and one gridline at the top of the scale.
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{width - 8}" y2="{pad_t}" '
                 'stroke="#e5e7eb" stroke-width="1"/>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + 4}" text-anchor="end" '
                 f'font-size="10" fill="#9ca3af">{int(peak)}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{width - 8}" '
                 f'y2="{pad_t + plot_h}" stroke="#9ca3af" stroke-width="1"/>')

    for i, row in enumerate(rows):
        value = float(row[value_key])
        bar_h = (value / peak) * plot_h
        x = pad_l + i * slot + (slot - bar_w) / 2
        y = pad_t + plot_h - bar_h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                     f'height="{bar_h:.1f}" fill="{colour}" rx="2"><title>'
                     f'{esc(str(row[label_key]))}: {esc(str(row[value_key]))}'
                     '</title></rect>')
        # Only label every nth category when they would collide.
        step = max(1, len(rows) // 14)
        if i % step == 0:
            parts.append(
                f'<text x="{pad_l + i * slot + slot / 2:.1f}" '
                f'y="{pad_t + plot_h + 14}" text-anchor="middle" font-size="10" '
                f'fill="#6b7280">{esc(str(row[label_key])[:10])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _stacked_chart(rows: List[Dict[str, Any]], *, label_key: str,
                   series: List[tuple], height_per_row: int = 20) -> str:
    """Horizontal stacked bars — one row per vendor, one segment per verdict."""
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l = 720, 150
    row_h = height_per_row
    height = len(rows) * row_h + 24
    peak = max(sum(float(r.get(k) or 0) for k, _, _ in series) for r in rows) or 1
    scale = (width - pad_l - 90) / peak

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" role="img" '
             'preserveAspectRatio="xMidYMid meet">']
    for i, row in enumerate(rows):
        y = i * row_h + 4
        parts.append(f'<text x="{pad_l - 6}" y="{y + row_h * 0.68:.1f}" '
                     'text-anchor="end" font-size="11" fill="#374151">'
                     f'{esc(str(row[label_key])[:26])}</text>')
        x = pad_l
        total = 0
        for key, colour, name in series:
            value = float(row.get(key) or 0)
            total += value
            if value <= 0:
                continue
            seg = value * scale
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{seg:.1f}" '
                         f'height="{row_h - 6}" fill="{colour}"><title>'
                         f'{esc(name)}: {int(value)}</title></rect>')
            x += seg
        parts.append(f'<text x="{x + 6:.1f}" y="{y + row_h * 0.68:.1f}" '
                     f'font-size="10" fill="#6b7280">{int(total)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _line_chart(rows: List[Dict[str, Any]], *, x_key: str,
                series: List[tuple], height: int = 200) -> str:
    """One or more lines over an ordered x-axis.

    A None value breaks the line rather than being drawn as zero — used for
    weeks below a coverage or scored-count floor, where "no data" and "zero"
    read as the same point unless the gap is real.
    """
    if not rows:
        return '<p class="mm-src">Nothing to plot.</p>'
    all_vals = [float(r[key]) for key, _, _ in series for r in rows
                if r.get(key) is not None]
    if not all_vals:
        return '<p class="mm-src">Nothing to plot.</p>'

    width, pad_l, pad_r, pad_t, pad_b = 720, 40, 12, 22, 24
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(rows)
    step = plot_w / max(1, n - 1)
    lo, hi = min(0.0, min(all_vals)), max(0.0, max(all_vals))
    span = (hi - lo) or 1.0

    def _x(i: int) -> float:
        return pad_l + i * step

    def _y(v: float) -> float:
        return pad_t + plot_h - (v - lo) / span * plot_h

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" '
             'role="img" preserveAspectRatio="xMidYMid meet">']
    zero_y = _y(0)
    parts.append(f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{width - pad_r}" '
                f'y2="{zero_y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + 4}" text-anchor="end" '
                f'font-size="10" fill="#9ca3af">{hi:.0f}</text>')
    parts.append(f'<text x="{pad_l - 6}" y="{pad_t + plot_h}" text-anchor="end" '
                f'font-size="10" fill="#9ca3af">{lo:.0f}</text>')

    for key, colour, name in series:
        segments: List[List[tuple]] = []
        current: List[tuple] = []
        for i, row in enumerate(rows):
            value = row.get(key)
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append((_x(i), _y(float(value))))
        if current:
            segments.append(current)
        for seg in segments:
            if len(seg) == 1:
                x, y = seg[0]
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" '
                            f'fill="{colour}"/>')
                continue
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in seg)
            parts.append(f'<path d="{d}" fill="none" stroke="{colour}" '
                        'stroke-width="2"/>')

    label_idx = sorted({0, n // 2, n - 1})
    for i in label_idx:
        parts.append(f'<text x="{_x(i):.1f}" y="{height - 6}" '
                    'text-anchor="middle" font-size="10" fill="#6b7280">'
                    f'{esc(str(rows[i][x_key])[:10])}</text>')

    if len(series) > 1:
        lx = pad_l
        for key, colour, name in series:
            parts.append(f'<rect x="{lx}" y="2" width="8" height="8" '
                        f'fill="{colour}"/>')
            parts.append(f'<text x="{lx + 11}" y="10" font-size="9" '
                        f'fill="#374151">{esc(name)}</text>')
            lx += 20 + len(name) * 5.2
    parts.append("</svg>")
    return "".join(parts)


def _scatter(rows: List[Dict[str, Any]], *, x_key: str, y_key: str,
             label_key: str, x_label: str, y_label: str) -> str:
    """Two 0-100 scores against each other."""
    pts = [r for r in rows
           if r.get(x_key) is not None and r.get(y_key) is not None]
    if not pts:
        return '<p class="mm-src">No vendor has both scores.</p>'

    width, height, pad = 720, 320, 44
    plot_w, plot_h = width - pad - 16, height - pad - 16

    parts = [f'<svg class="mm-chart" viewBox="0 0 {width} {height}" role="img" '
             'preserveAspectRatio="xMidYMid meet">']
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = 16 + plot_h * (1 - frac)
        parts.append(f'<line x1="{pad}" y1="{gy:.1f}" x2="{width - 16}" '
                     f'y2="{gy:.1f}" stroke="#f3f4f6" stroke-width="1"/>')
        parts.append(f'<text x="{pad - 6}" y="{gy + 4:.1f}" text-anchor="end" '
                     f'font-size="10" fill="#9ca3af">{int(frac * 100)}</text>')
    for point in pts:
        cx = pad + (float(point[x_key]) / 100) * plot_w
        cy = 16 + plot_h * (1 - float(point[y_key]) / 100)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#475569" '
                     f'fill-opacity="0.75"><title>{esc(str(point[label_key]))}: '
                     f'{x_label} {point[x_key]}, {y_label} {point[y_key]}'
                     '</title></circle>')
        # A hover tooltip is useless once this file is shared, printed or
        # screenshotted — a scatter with no visible identity next to each
        # point is unreadable outside a live browser. Short direct labels,
        # accepting some overlap on a dense chart, beat no identity at all.
        name = str(point[label_key])[:16]
        parts.append(f'<text x="{cx + 7:.1f}" y="{cy + 3:.1f}" font-size="8" '
                     f'fill="#475569">{esc(name)}</text>')
    parts.append(f'<text x="{width / 2}" y="{height - 6}" text-anchor="middle" '
                 f'font-size="10" fill="#6b7280">{esc(x_label)}</text>')
    parts.append(f'<text x="12" y="{height / 2}" font-size="10" fill="#6b7280" '
                 f'transform="rotate(-90 12 {height / 2})" text-anchor="middle">'
                 f'{esc(y_label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def build_market_report(conn, market: Dict[str, Any], *, days: int = 30
                        ) -> bytes:
    """One market, one file, no external requests.

    Hierarchy: findings first, market facts, material developments, the
    signals behind them, what vendors say, what everyone else says, the
    registry, how much of it we actually watched, and raw records last,
    collapsed. A reader should be able to stop after "What changed" and
    already know what happened this period.
    """
    from app.services import market_analysis as man
    from app.services import market_corpus as mcorp
    from app.services import market_publish as mp

    overview = mp.build_overview(conn, market, days=days)
    analyses = {}
    for name in man.ANALYSES:
        try:
            analyses[name] = man.run(conn, market["id"], name)
        except Exception as exc:  # noqa: BLE001 — a missing panel is not a
            logger.warning("report analysis %s failed: %s", name, exc)

    formation = analyses.get("formation")
    sn = analyses.get("signal_noise")
    funding = analyses.get("funding")
    hiring = analyses.get("hiring")
    sov = analyses.get("share_of_voice")

    try:
        pc = man.period_comparison(conn, market["id"], days=days)
    except Exception as exc:  # noqa: BLE001 — the report still stands without it
        logger.warning("period comparison failed: %s", exc)
        pc = None

    try:
        voices = man.top_voices(conn, market["id"], days=days, limit=20)
    except Exception as exc:  # noqa: BLE001 — the report still stands without it
        logger.warning("top voices failed: %s", exc)
        voices = None

    # Fetched once, up front — "What changed", "Material vendor moves",
    # "Market discussion", the registry sort and "Raw coverage" all read the
    # same deduplicated, classified list rather than re-querying per section.
    dataset = mp.build_dataset(conn, market["id"])
    vendor_names = [d["vendor"] for d in dataset]
    articles = mcorp.articles(conn, market["id"], limit=60, days=days)
    clustered = mcorp.cluster(articles, vendor_names) if articles else []
    classified = [(a, _material_kind(a)) for a in clustered]
    material_rows = [(a, k) for a, k in classified if k]

    # Per-vendor, from the same material list: when a vendor last had a
    # material development in this window, and how many. Keyed by vendor
    # name — build_dataset() has no brand_id today, and the display name is
    # exactly what both lists already share.
    last_material: Dict[str, str] = {}
    announced_30d: Dict[str, int] = {}
    for a, _k in material_rows:
        pub = a.get("published") or ""
        for v in a.get("vendors") or []:
            name = v.get("vendor")
            if not name:
                continue
            if pub > last_material.get(name, ""):
                last_material[name] = pub
            announced_30d[name] = announced_30d.get(name, 0) + 1

    hire_lead = None
    if hiring and hiring.get("by_vendor") and hiring.get("openings"):
        top = hiring["by_vendor"]
        total_open = hiring["openings"]
        if len(top) >= 2:
            hire_lead = (f'{esc(top[0]["vendor"])} accounts for {top[0]["openings"]} '
                        f'of the {total_open} observed openings, with '
                        f'{esc(top[1]["vendor"])} accounting for another '
                        f'{top[1]["openings"]}.')
        else:
            hire_lead = (f'{esc(top[0]["vendor"])} accounts for {top[0]["openings"]} '
                        f'of the {total_open} observed openings.')

    generated = datetime.now(timezone.utc)
    body: List[str] = [f"<style>{EXTRA_CSS}</style>"]

    # ================================================================
    # Header
    # ================================================================
    period_range = _fmt_range(*pc["current_range"]) if pc else None
    body.append('<header class="report-header">')
    body.append(f'<h1>{esc(market["name"])} — {days}-Day Market Monitor</h1>')
    body.append('<p class="lede">Material changes across products, customers, '
               'partnerships, hiring, funding, acquisitions and market '
               'positioning.</p>')
    if period_range:
        body.append(f'<p class="mm-src">{esc(period_range)} · generated '
                    f'{generated.strftime("%d %B %Y")}</p>')
    else:
        body.append(f'<p class="mm-src">Covering the last {days} days · '
                    f'generated {generated.strftime("%d %B %Y")}</p>')
    body.append("</header>")

    # ---- Market scope
    body.append(section_open("Market scope"))
    scope_text = market.get("market_scope_description")
    if scope_text:
        body.append(f'<p>{esc(scope_text)}</p>')
        if market.get("inclusion_criteria"):
            body.append(f'<p><strong>Included:</strong> '
                        f'{esc(market["inclusion_criteria"])}</p>')
        if market.get("exclusion_criteria"):
            body.append(f'<p><strong>Excluded:</strong> '
                        f'{esc(market["exclusion_criteria"])}</p>')
    else:
        body.append('<p class="mm-src">Market scope has not been defined for '
                    'this market. Coverage below can include vendors or '
                    "stories outside the tracked cohort's actual boundary — "
                    'set a scope description to state that boundary '
                    'explicitly.</p>')
    body.append("</section>")

    # ================================================================
    # What changed — the primary analytical section
    # ================================================================
    changed_points: List[str] = []
    if formation and formation.get("vendors_in_scope"):
        changed_points.append(
            f'This market remains young: {formation["founded_since_2023"]} of '
            f'{formation["vendors_in_scope"]} vendors were founded in 2023 or '
            'later.')
    kind_n: Dict[str, int] = {}
    if sn and sn.get("signal_kinds"):
        kind_n = {k["kind"]: k["n"] for k in sn["signal_kinds"]}
        launch_n = kind_n.get("launch", 0)
        commercial_n = sum(kind_n.get(k, 0) for k in
                           ("partnership", "customer", "funding", "acquisition"))
        if launch_n or commercial_n:
            changed_points.append(
                f'Vendor announcements are weighted toward product launches: '
                f'{launch_n} of them, against {commercial_n} partnership, '
                'customer, funding and acquisition claims combined.')
    if hire_lead:
        changed_points.append(f'Observed hiring is concentrated: {hire_lead}')
    if kind_n.get("acquisition") or any(k == "acquisition" for _, k in material_rows):
        changed_points.append(
            'Recent coverage also includes at least one acquisition in the '
            'category.')
    if changed_points:
        body.append(section_open("What changed"))
        body.append("<p>" + " ".join(changed_points) + "</p>")

        if pc:
            labels_pc = {
                "_coverage": "Matched coverage records", "launch": "Product launches",
                "partnership": "Partnerships", "customer": "Customer announcements",
                "funding": "Funding announcements", "acquisition": "Acquisitions",
                "hiring": "Executive-change posts", "_jobs": "Open roles observed",
            }
            order_pc = ("_coverage", "launch", "partnership", "customer",
                       "funding", "acquisition", "hiring", "_jobs")
            rows_pc = []
            for key in order_pc:
                cur, prev = pc["current"].get(key, 0), pc["previous"].get(key, 0)
                if cur == 0 and prev == 0:
                    continue
                if prev == 0:
                    change = "no comparable prior-period reading"
                else:
                    d = cur - prev
                    change = f'{"+" if d > 0 else ""}{d} vs previous period'
                rows_pc.append(
                    f'<tr><td>{esc(labels_pc[key])}</td>'
                    f'<td class="mm-num">{cur}</td>'
                    f'<td class="mm-num">{prev}</td>'
                    f'<td class="mm-src">{esc(change)}</td></tr>')
            if rows_pc:
                body.append(f'<h3>Compared with the previous {days} days</h3>')
                body.append(f'<p class="mm-src">Current period '
                           f'{esc(_fmt_range(*pc["current_range"]))} vs previous '
                           f'{esc(_fmt_range(*pc["previous_range"]))}. A metric '
                           'that could not exist before this market started '
                           'tracking is marked rather than shown as a jump from '
                           'zero.</p>')
                body.append('<table class="mm-table"><thead><tr><th>Metric</th>'
                           '<th class="mm-num">Current</th>'
                           '<th class="mm-num">Previous</th><th>Change</th>'
                           "</tr></thead><tbody>" + "".join(rows_pc)
                           + "</tbody></table>")
        body.append("</section>")

    # ================================================================
    # Market snapshot — facts about the market itself
    # ================================================================
    cov, fund = overview["coverage"], overview["funding"]
    corpus = overview.get("corpus") or {}
    body.append(section_open("Market snapshot"))
    body.append('<div class="mm-stats">')
    body.append(_stat("Vendors identified",
                      str(cov["registry"] - cov["excluded"]),
                      f'{cov["watching"]} currently monitored'))
    body.append(_stat("Cumulative disclosed funding",
                      _money(fund["total_musd"]),
                      f'Across {fund["disclosed"]} of '
                      f'{fund["disclosed"] + fund["undisclosed"]} vendors'))
    if formation and formation.get("vendors_in_scope"):
        body.append(_stat("Founded since 2023",
                          str(formation["founded_since_2023"]),
                          f'Of {formation["vendors_in_scope"]} vendors with a '
                          'known founding year'))
    body.append(_stat("Matched coverage records",
                      str(corpus.get("total", 0)),
                      f'During this {days}-day reporting period'))
    body.append("</div></section>")

    # ================================================================
    # Material vendor moves — deduplicated, grouped by kind, before raw coverage
    # ================================================================
    body.append(section_open("Material vendor moves"))
    if not material_rows:
        body.append('<p class="mm-src">No development this period matched a '
                    'launch, partnership, customer, funding, acquisition or '
                    'executive-change pattern.</p>')
    else:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for a, k in material_rows:
            groups.setdefault(k, []).append(a)
        group_order = [
            ("acquisition", "Acquisitions"), ("funding", "Funding"),
            ("launch", "Product launches"), ("customer", "Customers"),
            ("partnership", "Partnerships"), ("hiring", "Executive changes"),
        ]
        for kind, label in group_order:
            rows = groups.get(kind)
            if not rows:
                continue
            rows = _merge_same_story(rows)
            body.append(f"<h3>{esc(label)}</h3>")
            row_html = []
            for a in rows[:10]:
                cluster = a.get("cluster")
                sources = cluster["size"] if cluster else 1
                corrob = _corroboration(a)
                headline = (a.get("review_reason")
                           if kind == "hiring" and a.get("review_reason")
                           else a.get("title")) or a["uri"]
                row_html.append(
                    f'<tr><td><a href="{esc(a["uri"])}">{esc(headline)}</a>'
                    f'<div class="mm-src">{esc(a.get("news_source") or "")}'
                    f' · {esc((a.get("published") or "")[:10])}'
                    f' · {sources} source{"" if sources == 1 else "s"}'
                    f' · {esc(corrob)}</div></td></tr>')
            body.append('<table class="mm-table"><tbody>'
                       + "".join(row_html) + "</tbody></table>")
    body.append("</section>")

    # ================================================================
    # Competitive signals — sentiment, headcount, hiring, Crunchbase
    # ================================================================
    body.append(section_open("Competitive signals"))
    any_signal = False

    sentiment_trend = corpus.get("sentiment_trend") or []
    if any(r.get("net_all") is not None for r in sentiment_trend):
        any_signal = True
        body.append("<h3>Sentiment</h3>")
        latest_sentiment = next(
            (r["net_all"] for r in reversed(sentiment_trend) if r.get("net_all") is not None),
            None)
        body.append(_reading(latest_sentiment))
        body.append('<p class="mm-src">Net-positive-minus-negative share of '
                    "classified coverage, weekly. Not an average — sentiment "
                    "has no numeric scale in this system, only a "
                    "classification. A week is left blank rather than "
                    "plotted at zero when too few articles were classified "
                    "that week to call a direction.</p>")
        vendor_points = sum(1 for r in sentiment_trend if r.get("net_vendor") is not None)
        series = [("net_broad", "#475569", "The market broadly")]
        if vendor_points >= 3:
            series.append(("net_vendor", "#30a46c", "Tracked vendors' own coverage"))
        body.append(_line_chart(sentiment_trend, x_key="week", series=series))
        if vendor_points < 3:
            body.append(f'<p class="mm-src">Vendor-attributed sentiment is not '
                        f'shown: only {vendor_points} week'
                        f'{"" if vendor_points == 1 else "s"} of tracked-vendor '
                        'coverage cleared the confidence floor, too few to '
                        'read as a line.</p>')

    # The window is clipped to how long this market has existed (see
    # market_publish.headcount_trend) — a vendor snapshot cannot predate the
    # market's own registry — so points can genuinely be a short list on a
    # young market, not a sign of missing collection.
    hc_trend = mp.headcount_trend(conn, market, weeks=26)
    hc_with_data = [p for p in hc_trend["points"] if p.get("avg_pct_vs_baseline") is not None]
    if hc_with_data:
        any_signal = True
        body.append("<h3>Headcount change</h3>")
        body.append('<p class="mm-src">Average percentage change from each '
                    "vendor's own imported baseline. Using percentage change "
                    "prevents the market line from rising simply because "
                    "additional vendors were added. Each vendor uses its own "
                    "first recorded observation as baseline — there is no "
                    "single common baseline date across the market. Weeks "
                    f'covering fewer than half of the {hc_trend["watching"]} '
                    'actively monitored vendors should be treated as '
                    'lower-confidence.</p>')
        if len(hc_with_data) == 1:
            only = hc_with_data[0]
            pct = only["avg_pct_vs_baseline"]
            body.append(f'<p>Only one weekly reading exists so far: '
                        f'{"+" if pct > 0 else ""}{pct}% vs baseline, week of '
                        f'{esc(only["week"])}. A trend line needs at least two.</p>')
        else:
            body.append(_line_chart(
                hc_trend["points"], x_key="week",
                series=[("avg_pct_vs_baseline", "#475569", "Avg % vs baseline")]))

    if hiring and hiring["openings"]:
        any_signal = True
        body.append("<h3>Observed hiring</h3>")
        body.append(f'<p>{hiring["openings"]} open roles were observed across '
                    f'{len(hiring["by_vendor"])} vendors.</p>')
        body.append('<p class="mm-src">The mix of engineering, product, sales '
                    'and other roles can indicate where vendors are '
                    'investing, but should not be treated as a direct measure '
                    'of product maturity or commercial traction.</p>')
        if hire_lead:
            body.append(f'<p>Hiring is concentrated: {hire_lead}</p>')
        body.append(_coverage(hiring.get("coverage")))
        body.append(_bar_chart(hiring["by_function"], label_key="function",
                               value_key="openings"))

    if funding:
        any_signal = True
        body.append("<h3>Crunchbase signals</h3>")
        body.append(_coverage(funding.get("coverage")))
        body.append("<h4>Funding stage across the market</h4>")
        body.append(_bar_chart(funding["stages"], label_key="stage",
                               value_key="vendors"))
        body.append('<p class="mm-src">Growth and attention scores are '
                    "Crunchbase's own proprietary indicators, 0 to 100. "
                    "Treat them as supporting signals, not measures of "
                    "market performance.</p>")
        if funding.get("momentum"):
            body.append("<h4>Growth vs. attention</h4>")
            body.append(_scatter(funding["momentum"], x_key="growth_score",
                                 y_key="heat_score", label_key="vendor",
                                 x_label="growth", y_label="attention"))
        if funding.get("shared_investors"):
            body.append("<h4>Investors backing more than one vendor</h4>")
            body.append('<table class="mm-table"><tbody>' + "".join(
                f'<tr><td>{esc(i["investor"])}</td>'
                f'<td class="mm-src">{esc(", ".join(i["backing"]))}</td></tr>'
                for i in funding["shared_investors"]) + "</tbody></table>")
        fm_with_data = [r for r in funding.get("by_month") or []
                       if r.get("avg_heat_score") is not None]
        if fm_with_data:
            body.append("<h4>Growth and attention, as of each month</h4>")
            body.append('<p class="mm-src">Crunchbase reads these scores at '
                        "most weekly, and only writes a new value when it "
                        "changes — most months repeat the prior reading, so "
                        "this is a level, not a live trend. PitchBook and "
                        "ZoomInfo readings are not included. The window is "
                        "clipped to how long this market has existed, since "
                        "a reading cannot predate it.</p>")
            if len(fm_with_data) == 1:
                only = fm_with_data[0]
                body.append(f'<p>Only one month of readings exists so far: '
                            f'attention {only["avg_heat_score"]}, growth '
                            f'{only["avg_growth_score"]}, {esc(only["month"])}. '
                            'A trend line needs at least two.</p>')
            else:
                body.append(_line_chart(
                    funding["by_month"], x_key="month",
                    series=[("avg_heat_score", "#475569", "Attention (heat)"),
                            ("avg_growth_score", "#30a46c", "Growth")]))
        if funding.get("momentum_events"):
            body.append("<h4>Score changes during the reporting period</h4>")
            body.append('<table class="mm-table"><thead><tr><th>Vendor</th>'
                        '<th class="mm-num">Attention Δ</th>'
                        '<th class="mm-num">Growth Δ</th><th>Last observed</th>'
                        "</tr></thead><tbody>" + "".join(
                f'<tr><td>{esc(e["vendor"])}</td>'
                f'<td class="mm-num">{_signed(e.get("heat_delta"))}</td>'
                f'<td class="mm-num">{_signed(e.get("growth_delta"))}</td>'
                f'<td class="mm-src">{esc((e.get("observed_at") or "")[:10])}</td>'
                "</tr>" for e in funding["momentum_events"][:15])
                + "</tbody></table>")

    if not any_signal:
        body.append('<p class="mm-src">No competitive signal cleared its '
                    'reporting floor this period.</p>')
    body.append("</section>")

    # ================================================================
    # Audience and voice — activity, share of voice, and who is talking
    # ================================================================
    body.append(section_open("Audience and voice"))
    most_active = [v for v in overview.get("most_active") or [] if v.get("signals")]
    if most_active:
        body.append("<h3>Most active vendors</h3>")
        body.append(f'<p class="mm-src">LinkedIn posts in the last {days} days '
                    'plus open job listings and matched articles. Activity, '
                    'not performance.</p>')
        body.append(_bar_chart(most_active, label_key="vendor", value_key="signals"))

    if sov and not sov.get("error") and sov.get("vendors"):
        earned_rows = sorted(
            [v for v in sov["vendors"] if v.get("earned")],
            key=lambda v: v.get("earned_share") or 0, reverse=True)
        if earned_rows:
            body.append("<h3>Share of voice</h3>")
            body.append(f'<p class="mm-src">Of {sov["earned_total"]} mentions by '
                        'somebody other than the vendor. A vendor\'s own posts '
                        'are volume, not voice, and are counted separately '
                        'below.</p>')
            body.append(_bar_chart(
                [{"vendor": v["vendor"], "pct": round((v["earned_share"] or 0) * 100)}
                 for v in earned_rows],
                label_key="vendor", value_key="pct", colour="#30a46c"))

        loud_rows = [v for v in sov.get("vendors") or []
                    if v.get("reactions_per_post") is not None]
        if loud_rows:
            body.append("<h3>Who shouts loudest, and who is heard</h3>")
            body.append('<p class="mm-src">Posts published vs. reactions per '
                        'post — the two are not the same thing. Vendors with '
                        'fewer than five measured posts are absent.</p>')
            loud_rows = sorted(loud_rows, key=lambda v: v["own_posts"], reverse=True)
            body.append('<table class="mm-table"><thead><tr><th>Vendor</th>'
                        '<th class="mm-num">Posts</th>'
                        '<th class="mm-num">Reactions/post</th>'
                        '<th class="mm-num">Mentions by others</th>'
                        "</tr></thead><tbody>" + "".join(
                f'<tr><td>{esc(v["vendor"])}</td>'
                f'<td class="mm-num">{v["own_posts"]}</td>'
                f'<td class="mm-num">{v["reactions_per_post"]}</td>'
                f'<td class="mm-num">{v["earned"]}</td></tr>'
                for v in loud_rows[:20]) + "</tbody></table>")

    if voices and voices.get("voices"):
        body.append("<h3>Top voices</h3>")
        body.append('<p class="mm-src">Accounts posting about the market. '
                    "Vendors' own company posts are excluded — they are "
                    'counted as owned above.</p>')
        body.append('<table class="mm-table"><thead><tr><th>Account</th>'
                    '<th>Platform</th><th class="mm-num">Posts</th>'
                    '<th class="mm-num">Reactions</th><th>Last seen</th>'
                    "</tr></thead><tbody>" + "".join(
            f'<tr><td>@{esc(v["author"])}</td><td>{esc(v["platform"])}</td>'
            f'<td class="mm-num">{v["posts"]}</td>'
            f'<td class="mm-num">{v["engagement"]}</td>'
            f'<td class="mm-src">{esc((v.get("last_seen") or "")[:10])}</td></tr>'
            for v in voices["voices"][:20]) + "</tbody></table>")
    body.append("</section>")

    # ================================================================
    # What vendors are announcing — the aggregate claim mix
    # ================================================================
    if sn and sn.get("vendors"):
        totals = sn["totals"]
        body.append(section_open("What vendors are announcing"))
        body.append(f'<p>{totals["signal"]} of '
                    f'{sum(totals.values())} collected vendor posts contained '
                    'a concrete company claim or announcement. The rest were '
                    'commentary, event promotion or other non-company '
                    'updates. A concrete claim is not independently verified '
                    'by being concrete — see Material vendor moves above for '
                    'which of these have independent corroboration.</p>')
        body.append(_coverage(sn.get("coverage")))
        body.append(_stacked_chart(
            sn["vendors"][:20], label_key="vendor",
            series=[("signal", "#30a46c", "Concrete claim"),
                    ("commentary", "#8b93a1", "Commentary"),
                    ("noise", "#d4d8de", "No content")]))
        if sn.get("signal_kinds"):
            body.append("<p>" + " ".join(
                f'<span class="mm-kind">{esc(k["kind"])} {k["n"]}</span>'
                for k in sn["signal_kinds"]) + "</p>")
        body.append("</section>")

    # ---- A young vendor cohort — kept near the announcement mix, not implying causation
    if formation:
        body.append(section_open("A young vendor cohort"))
        body.append(f'<p>{formation["founded_since_2023"]} of '
                    f'{formation["vendors_in_scope"]} vendors in the registry '
                    'were founded in 2023 or later.</p>')
        body.append(_coverage(formation.get("coverage")))
        body.append(_bar_chart(formation["founded_by_year"],
                               label_key="year", value_key="vendors"))
        body.append("<h3>Announcements per month</h3>")
        body.append(_coverage(formation.get("announcement_coverage")))
        body.append(_bar_chart(formation["announcements_by_month"],
                               label_key="month", value_key="signal",
                               colour="#30a46c"))
        body.append("</section>")

    # ================================================================
    # Market discussion — practitioner and analyst chatter, not vendor moves
    # ================================================================
    _spam_re = re.compile(
        r"\bfor hire\b|\blooking for work\b|\bjob[- ]seeking\b|\bmy resume\b"
        r"|\bhire me\b", re.I)
    discussion_rows = [
        a for a, k in classified
        if not k and a.get("article_class") in ("discussion", "research")
        and not _spam_re.search(f"{a.get('title') or ''} {a.get('summary') or ''}")
    ]
    if discussion_rows:
        body.append(section_open("Market discussion"))
        body.append('<p class="mm-src">Practitioner and analyst commentary '
                    "matched to the market's phrases — debate, scepticism "
                    'and emerging terminology, not vendor-specific '
                    'developments. A keyword filter removes obvious spam '
                    '("for hire", job-seeking posts); it is a heuristic, '
                    'not a verified relevance judgment.</p>')
        body.append('<table class="mm-table"><tbody>'
                   + "".join(_coverage_row(a) for a in discussion_rows[:20])
                   + "</tbody></table>")
        body.append("</section>")

    # ================================================================
    # The registry — sorted by most recent material signal
    # ================================================================
    registry_rows = [r for r in dataset if r.get("role") != "excluded"]
    registry_rows.sort(key=lambda r: last_material.get(r["vendor"], ""), reverse=True)
    body.append(section_open("Vendor registry"))
    body.append('<p class="mm-src">Sorted by most recent material signal '
               'this period, then by name.</p>')
    body.append('<table class="mm-table"><thead><tr>'
                "<th>Vendor</th><th>Country</th><th>Founded</th>"
                '<th class="mm-num">LinkedIn headcount</th>'
                '<th class="mm-num">Disclosed funding</th>'
                '<th class="mm-num">30d announcements</th>'
                '<th class="mm-num">Open roles</th>'
                "<th>Last material signal</th></tr></thead><tbody>")
    for row in registry_rows:
        raised = row.get("total_funding_musd")
        watched = bool(row.get("collecting"))
        jobs_cell = str(row.get("open_jobs") or 0) if watched else "—"
        announced = announced_30d.get(row["vendor"], 0)
        last_sig = last_material.get(row["vendor"], "")
        body.append(
            f'<tr><td>{esc(row["vendor"])}</td>'
            f'<td>{esc(row.get("country") or "—")}</td>'
            f'<td>{esc(str(row.get("founded_year") or "—"))}</td>'
            f'<td class="mm-num">{esc(str(row.get("headcount_linkedin") or row.get("headcount_workbook") or "—"))}</td>'
            f'<td class="mm-num">{_money(raised) if raised else esc(row.get("funding_status") or "—")}</td>'
            f'<td class="mm-num">{announced if watched else "—"}</td>'
            f'<td class="mm-num">{esc(jobs_cell)}</td>'
            f'<td class="mm-src">{esc(last_sig[:10]) if last_sig else "—"}</td></tr>')
    body.append("</tbody></table>"
               '<p class="mm-src">A dash means monitoring is paused for that '
               'vendor (announcements, open roles) or no material signal was '
               'observed this period (last material signal) — not a '
               'confirmed zero.</p>'
               "</section>")

    # ================================================================
    # Monitoring coverage — how much of the market we have actually looked at
    # ================================================================
    body.append(section_open("Monitoring coverage"))
    registry_total = cov["registry"] - cov["excluded"]
    body.append('<table class="mm-table"><thead><tr><th>Coverage</th>'
               '<th class="mm-num">Vendors</th><th class="mm-num">%</th>'
               "</tr></thead><tbody>")
    body.append(_pct_row("Actively monitored", cov["watching"], registry_total))
    body.append(_pct_row("Paused", cov["paused"], registry_total))
    body.append(_pct_row("Any recorded observation", cov["observed"], registry_total))
    if formation and formation.get("announcement_coverage"):
        ac = formation["announcement_coverage"]
        body.append(_pct_row("LinkedIn posts collected", ac["measured"], ac["total"]))
    if funding and funding.get("coverage"):
        fc = funding["coverage"]
        body.append(_pct_row("Crunchbase profile read", fc["measured"], fc["total"]))
    if hiring and hiring.get("coverage"):
        hc = hiring["coverage"]
        body.append(_pct_row("Job listings observed", hc["measured"], hc["total"]))
    body.append("</tbody></table>"
               '<p class="mm-src">No observed activity — '
               f'{overview["quiet_vendors"]} of {registry_total} monitored '
               'vendors — means no vendor posts, open roles or matched '
               'coverage were observed from monitored sources this period. '
               'It does not mean the vendor did nothing.</p>'
               "</section>")

    # ================================================================
    # About this report
    # ================================================================
    body.append(section_open("About this report"))
    body.append(
        "<p>Aunoo keeps a registry of vendors in this market and matches its "
        "wider article collection against the market's own phrases, so "
        "coverage can include material first collected for a different "
        "tracked topic. Vendor announcements are classified by event type. "
        "Company and funding data currently draw on sources including "
        "LinkedIn and Crunchbase. Coverage varies by vendor and source; "
        "where a panel above rests on part of the registry rather than all "
        "of it, it states how many vendors are represented.</p>"
        "<p><strong>Absence of an observed signal should not be "
        "interpreted as evidence that no activity occurred</strong> — it "
        "means monitored sources did not carry it. Where a count could mean "
        "either \"checked, found none\" or \"not checked yet,\" this report "
        "shows a dash for the second case, not a zero.</p>")
    body.append("</section>")

    # ================================================================
    # Raw coverage — collapsed, everything, for auditability
    # ================================================================
    if clustered:
        body.append(section_open("Raw coverage"))
        body.append(f'<details><summary>{len(articles)} matched records — '
                    'includes market discussion and coverage below the '
                    'material-development threshold</summary>')
        body.append('<table class="mm-table"><tbody>'
                    + "".join(_coverage_row(a) for a in clustered)
                    + "</tbody></table></details>")
        body.append("</section>")

    return html_document(f'{market["name"]} — Market Monitor',
                         "".join(body)).encode("utf-8")
