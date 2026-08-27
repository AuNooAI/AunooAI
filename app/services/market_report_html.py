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
# The shared-link treatment: a market news page rather than a report.
#
# Every rule is scoped under `.mm-news`, because `html_document` and `BASE_CSS`
# are shared with the consensus and horizons reports and an unscoped rule here
# would restyle all three.
#
# Self-contained by necessity — this file is emailed, saved and opened offline,
# so there are no icon fonts, no CDN scripts and no web fonts. The sparklines
# are inline SVG built from the same series the page quotes.
NEWS_CSS = """
.mm-news { --n-bg:#f4f6f8; --n-shell:#fff; --n-panel:#fff; --n-text:#111827;
           --n-muted:#596674; --n-line:#d9e0e5; --n-accent:#096b74;
           --n-accent-soft:#dff3f2; --n-blue:#2259a8; --n-green:#21734a;
           --n-orange:#9a5315; --n-purple:#6c48a1;
           margin:0 0 1.6rem; border:1px solid var(--n-line); border-radius:14px;
           overflow:hidden; background:var(--n-bg); color:var(--n-text); }
.mm-news * { box-sizing:border-box; }
.mm-news .n-top { display:flex; align-items:center; gap:20px; padding:14px 18px;
                  background:var(--n-shell); border-bottom:1px solid var(--n-line); }
.mm-news .n-brand { display:flex; align-items:center; gap:9px; font-weight:500;
                    white-space:nowrap; }
.mm-news .n-logo { width:22px; height:22px; border-radius:6px;
                   background:var(--n-accent); color:#fff; display:grid;
                   place-items:center; font-size:11px; }
.mm-news .n-jump { display:flex; gap:4px; flex:1; flex-wrap:wrap; }
.mm-news .n-jump a { border-radius:7px; padding:6px 10px; color:var(--n-muted);
                     text-decoration:none; font-size:.82rem; }
.mm-news .n-jump a:hover { background:var(--n-accent-soft); color:var(--n-accent); }
.mm-news .n-market { color:var(--n-muted); white-space:nowrap; font-size:.85rem; }
.mm-news .n-main { padding:24px; }
.mm-news .n-head { display:flex; align-items:flex-end; justify-content:space-between;
                   gap:20px; margin-bottom:18px; flex-wrap:wrap; }
.mm-news .n-kicker { color:var(--n-accent); font-size:.72rem; text-transform:uppercase;
                     letter-spacing:.08em; margin-bottom:5px; }
.mm-news h1 { font-size:clamp(23px,3vw,34px); font-weight:500;
              letter-spacing:-.025em; margin:0; }
.mm-news .n-sub { color:var(--n-muted); margin:7px 0 0; max-width:680px; }
.mm-news .n-period { color:var(--n-muted); font-size:.82rem; white-space:nowrap; }
.mm-news .n-summary { padding:18px 20px; background:var(--n-panel);
                      border:1px solid var(--n-line); border-radius:10px;
                      margin-bottom:14px; }
.mm-news .n-summary h2 { font-size:17px; font-weight:500; margin:0; }
.mm-news .n-summary p { margin:8px 0 0; color:var(--n-muted); max-width:940px; }
.mm-news .n-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
                      gap:10px; margin-bottom:22px; }
.mm-news .n-metric { min-width:0; padding:15px; background:var(--n-panel);
                     border:1px solid var(--n-line); border-radius:9px; }
.mm-news .n-metric-top { display:flex; justify-content:space-between; gap:8px;
                         color:var(--n-muted); font-size:12px; }
.mm-news .n-metric-value { margin-top:8px; font-size:24px; font-weight:500;
                           letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.mm-news .n-delta { color:var(--n-muted); font-size:12px; margin-top:4px; }
.mm-news .n-spark { width:100%; height:28px; margin-top:9px; display:block; }
.mm-news .n-spark path { fill:none; stroke:var(--n-accent); stroke-width:2; }
.mm-news .n-spark .base { stroke:var(--n-line); stroke-width:1; }
.mm-news .n-nospark { margin-top:9px; font-size:11px; color:var(--n-muted);
                      min-height:28px; display:flex; align-items:center; }
.mm-news .n-grid { display:grid; grid-template-columns:minmax(0,1.75fr) minmax(240px,.72fr);
                   gap:22px; align-items:start; }
.mm-news .n-sec-head { display:flex; align-items:center; justify-content:space-between;
                       gap:12px; padding-bottom:10px; border-bottom:2px solid var(--n-text); }
.mm-news .n-sec-head h2 { font-size:17px; font-weight:500; margin:0; }
.mm-news .n-updated { color:var(--n-muted); font-size:12px; }
.mm-news .n-filters { display:flex; flex-wrap:wrap; gap:4px; padding:10px 0 5px; }
.mm-news .n-filter { font-size:12px; padding:5px 8px; border:0; border-radius:7px;
                     background:transparent; color:var(--n-muted); cursor:pointer;
                     font-family:inherit; }
.mm-news .n-filter[aria-pressed="true"] { background:var(--n-accent-soft);
                                          color:var(--n-accent); }
.mm-news .n-story { padding:16px 0; border-bottom:1px solid var(--n-line); }
.mm-news .n-story:last-child { border-bottom:0; }
.mm-news .n-story-tag { color:var(--story,var(--n-accent)); font-size:11px;
                        text-transform:uppercase; letter-spacing:.07em;
                        margin-bottom:5px; }
.mm-news .n-story h3 { font-size:18px; line-height:1.28; font-weight:500; margin:0; }
.mm-news .n-story-sum { color:var(--n-muted); margin:6px 0 0; line-height:1.45; }
.mm-news .n-byline { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px;
                     color:var(--n-muted); font-size:12px; }
.mm-news .n-why { margin-top:6px; color:var(--n-muted); font-size:11.5px;
                  font-style:italic; }
.mm-news .n-support { margin-top:9px; color:var(--n-muted); font-size:12px;
                      line-height:1.55; }
.mm-news .n-support strong { color:var(--n-text); font-weight:500; }
.mm-news .n-support a { color:var(--n-muted); }
.mm-news .n-support a:hover { color:var(--n-accent); }
.mm-news .n-aside { display:grid; gap:18px; }
.mm-news .n-card { background:var(--n-panel); border:1px solid var(--n-line);
                   border-radius:9px; padding:15px; }
.mm-news .n-card-title { display:flex; align-items:center; justify-content:space-between;
                         border-bottom:1px solid var(--n-line); padding-bottom:9px;
                         margin-bottom:5px; }
.mm-news .n-card-title h2 { font-size:15px; font-weight:500; margin:0; }
.mm-news .n-row { display:grid; grid-template-columns:24px minmax(0,1fr) auto;
                  gap:8px; align-items:center; padding:10px 0;
                  border-bottom:1px solid var(--n-line); }
.mm-news .n-row:last-child { border-bottom:0; }
.mm-news .n-rank { color:var(--n-muted); font-variant-numeric:tabular-nums; }
.mm-news .n-row-val { font-weight:500; white-space:nowrap;
                      font-variant-numeric:tabular-nums; }
.mm-news .n-row-label { font-size:12px; color:var(--n-muted); margin-top:2px; }
.mm-news .n-note { color:var(--n-muted); font-size:11px; margin-top:16px; }
/* Period selector, view switch and the RSS link. */
.mm-news .n-periods { display:flex; gap:4px; align-items:center; }
.mm-news .n-periods a { font-size:12px; padding:4px 8px; border-radius:7px;
                        color:var(--n-muted); text-decoration:none; }
.mm-news .n-periods a[aria-current="page"] { background:var(--n-accent-soft);
                                             color:var(--n-accent); }
.mm-news .n-sec-actions { display:flex; align-items:center; gap:10px;
                          flex-wrap:wrap; }
.mm-news .n-views { display:flex; border:1px solid var(--n-line);
                    border-radius:7px; overflow:hidden; }
.mm-news .n-views button { font-size:12px; padding:5px 9px; border:0;
                           background:transparent; color:var(--n-muted);
                           cursor:pointer; font-family:inherit; }
.mm-news .n-views button[aria-pressed="true"] { background:var(--n-accent-soft);
                                                color:var(--n-accent); }
.mm-news .n-rss { font-size:12px; color:var(--n-muted); text-decoration:none;
                  border:1px solid var(--n-line); border-radius:7px;
                  padding:5px 9px; }
.mm-news .n-rss:hover { color:var(--n-accent); border-color:var(--n-accent); }
/* Headlines and River strip the page back without reordering it, so a reader
   scanning for one item is looking at the same list in the same order. */
.mm-news[data-view="headlines"] .n-story-sum,
.mm-news[data-view="headlines"] .n-support,
.mm-news[data-view="headlines"] .n-why,
.mm-news[data-view="river"] .n-story-sum,
.mm-news[data-view="river"] .n-support,
.mm-news[data-view="river"] .n-why { display:none; }
.mm-news[data-view="headlines"] .n-story { padding:9px 0; }
.mm-news[data-view="headlines"] .n-story h3 { font-size:15px; }
.mm-news[data-view="headlines"] .n-story-tag { margin-bottom:3px; }
.mm-news[data-view="headlines"] .n-byline { margin-top:4px; }
.mm-news[data-view="river"] .n-story { padding:11px 0; }
.mm-news[data-view="river"] .n-story h3 { font-size:15px; }
.mm-news[data-view="river"] .n-story-tag { display:none; }
/* Social highlights: a quote, not a row. */
.mm-news .n-social { padding:11px 0; border-bottom:1px solid var(--n-line); }
.mm-news .n-social:last-of-type { border-bottom:0; }
.mm-news .n-social-meta { color:var(--n-muted); font-size:11.5px; }
.mm-news .n-quote { margin:5px 0 0; line-height:1.45; font-size:13px; }
.mm-news .n-quote a { color:inherit; text-decoration:none; }
.mm-news .n-quote a:hover { text-decoration:underline; }
.mm-news .n-empty { color:var(--n-muted); font-size:13px; padding:14px 0; }
@media (max-width:850px) {
  .mm-news .n-jump { display:none; }
  .mm-news .n-market { margin-left:auto; }
  .mm-news .n-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .mm-news .n-grid { grid-template-columns:1fr; }
}
@media (max-width:560px) {
  .mm-news .n-main { padding:16px; }
  .mm-news .n-metrics { grid-template-columns:1fr; }
  .mm-news .n-story h3 { font-size:16px; }
}
@media print {
  .mm-news .n-filters, .mm-news .n-jump { display:none; }
  .mm-news { border-color:#ccc; }
}
"""


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
        return "Reported by somebody else"
    cluster = article.get("cluster")
    others = (cluster or {}).get("others") or []
    if any((o.get("article_class") not in ("vendor", "social")) for o in others):
        size = cluster["size"]
        return f"Confirmed by {size} separate sources"
    return "Only the vendor has said this"


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

# How many vendors the report names in its activity table. Ten by default, the
# same number the shared-link entitlement allows, so a full report and a shared
# one show a list of the same shape.
ACTIVITY_TOP_N = 10


def _activity_row(vendor: Dict[str, Any]) -> str:
    """One vendor's row in the activity table.

    A withheld index prints an em dash, never a zero. The three raw counts sit
    beside it because the index is a rank and the counts are the measurements
    it was computed from; a reader cannot check the first without the others.
    """
    index = vendor.get("activity_index")
    shown = str(index) if index is not None else "&mdash;"
    return ('<tr><td>' + esc(vendor.get("vendor") or "") + '</td>'
            '<td class="mm-num">' + shown + '</td>'
            '<td class="mm-num">' + str(vendor.get("posts") or 0) + '</td>'
            '<td class="mm-num">' + str(vendor.get("jobs") or 0) + '</td>'
            '<td class="mm-num">' + str(vendor.get("earned") or 0)
            + '</td></tr>')


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

# ---------------------------------------------------------------------------
# The shared-link news page
# ---------------------------------------------------------------------------

#: Theme colours for a finding's tag, keyed on the six themes in
#: ``market_findings.THEMES``. A theme with no colour falls back to the accent
#: rather than being dropped.
_THEME_COLOUR = {
    "Funding and ownership": "var(--n-purple)",
    "Product and launches": "var(--n-blue)",
    "Customers and partnerships": "var(--n-orange)",
    "Hiring and headcount": "var(--n-green)",
    "Leadership and strategy": "var(--n-accent)",
    "Attention and narrative": "var(--n-muted)",
}


def _day(value: Any) -> str:
    """A date the way a person writes one, falling back to what we were given."""
    raw = str(value)[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%-d %b %Y")
    except (ValueError, TypeError):
        return raw


def _clip(text_value: str, limit: int) -> str:
    """Cut at a word, not through one. Slicing raw left "World Wide Technol"."""
    text_value = (text_value or "").strip()
    if len(text_value) <= limit:
        return text_value
    cut = text_value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or text_value[:limit]) + "…"


def _norm_words(text_value: str) -> str:
    """Text reduced to comparable words, for spotting a repeated sentence."""
    return re.sub(r"[^a-z0-9 ]", " ",
                  re.sub(r"\s+", " ", (text_value or "").lower())).strip()


def _spark(values: List[float], *, label: str) -> str:
    """A sparkline, or nothing.

    Refuses to draw fewer than four points. Two readings joined by a line is a
    picture of a trend built from no trend, and this report spent a lot of
    effort today not doing that elsewhere — the headcount series currently has
    two weekly points and its own ``thin_coverage`` flag.
    """
    pts = [v for v in values if isinstance(v, (int, float))]
    if len(pts) < 4:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    step = 180 / (len(pts) - 1)
    coords = " ".join(
        f"{'M' if i == 0 else 'L'}{i * step:.0f} {24 - (v - lo) / span * 20:.0f}"
        for i, v in enumerate(pts))
    return (f'<svg class="n-spark" viewBox="0 0 180 28" role="img" '
            f'aria-label="{esc(label)}">'
            f'<path class="base" d="M0 24H180"/><path d="{coords}"/></svg>')


def _metric_card(label: str, hint: str, value: str, note: str,
                 spark: str = "", nospark: str = "", caption: str = "") -> str:
    body = spark or (f'<div class="n-nospark">{esc(nospark)}</div>'
                     if nospark else "")
    if spark and caption:
        body += f'<div class="n-nospark">{esc(caption)}</div>' 
    return (
        '<article class="n-metric">'
        f'<div class="n-metric-top"><span>{esc(label)}</span>'
        f'<span>{esc(hint)}</span></div>'
        f'<div class="n-metric-value">{esc(value)}</div>'
        f'<div class="n-delta">{esc(note)}</div>{body}</article>')


def _delta(now: float, prev: Optional[float], *, unit: str = "",
           period: str = "the period before") -> str:
    """A change, or why there is not one.

    Percentages off a base of zero are not percentages, and a comparison
    against a period we were not measuring in is not a comparison. Both come
    back as a sentence rather than a number pretending to be one.
    """
    if prev is None:
        return f"Nothing measured in {period}, so no comparison"
    delta = now - prev
    if not delta:
        return f"Unchanged on {period}"
    if not prev:
        return f"Up from none in {period}"
    return (f'{(delta / prev) * 100:+.0f}% on {period} '
            f'({prev:,.0f} → {now:,.0f}{unit})')


def _news_metrics(*, headcount: Optional[Dict[str, Any]],
                  jobs_total: int, jobs_new: int, jobs_state: str,
                  funding: Optional[Dict[str, Any]],
                  earned: int, earned_note: str,
                  earned_prev: Optional[int],
                  movers: Optional[Dict[str, Any]],
                  weekly: List[Dict[str, Any]]) -> str:
    """The four figures at the top, each with its own denominator.

    Every one carries how much of the market it covers, because the number
    alone is the thing this product spent the day learning not to print.
    """
    cards: List[str] = []

    if headcount:
        cohort = headcount.get("cohort") or 0
        total = headcount.get("registry_total") or 0
        # A market total needs one reading per vendor; a market *change* needs
        # two of the same vendor, and 83 of 84 have one. So the delta states
        # what actually moved rather than a market figure it cannot support.
        moved = [m for m in ((movers or {}).get("movers") or [])
                 if m.get("metric") == "Staff"]
        net = sum((m.get("to") or 0) - (m.get("from") or 0) for m in moved)
        head_delta = (
            f'{net:+d} across the {len(moved)} '
            f'vendor{"" if len(moved) == 1 else "s"} measured twice'
            if moved else
            "Nothing to compare yet — almost every vendor has one reading")
        cards.append(_metric_card(
            "Staff", f"counted at {cohort} of {total} vendors",
            f"{headcount.get('observed_market_headcount', 0):,}",
            head_delta,
            # The weekly headcount series has two points and its own
            # thin-coverage flag, so there is nothing honest to draw.
            nospark="Most vendors have one reading so far, so there is no "
                    "trend to show."))

    cards.append(_metric_card(
        "Open roles", "LinkedIn and company job boards",
        f"{jobs_total:,}" if jobs_state != "unmeasured" else "—",
        (f"{jobs_new} of them are new since the last check"
         if jobs_new else "Most vendors have been checked once, so we cannot "
                          "yet say what has changed"),
        nospark="Roles open today, not roles posted this month."))

    if funding:
        cov = funding.get("coverage") or {}
        disclosed = sum(int(r.get("vendors") or 0)
                        for r in (funding.get("stages") or [])
                        if (r.get("stage") or "") != "not stated")
        cards.append(_metric_card(
            "Vendors with a known funding stage", cov.get("label", ""),
            f"{disclosed:,}",
            "Stage and investors come from Crunchbase. The money totals "
            "elsewhere in this report come from the vendor list instead, and "
            "say so.",
            nospark="Crunchbase gives us stages, not individual rounds, so we "
                    "cannot name a largest raise."))

    # Weeks that are still filling are left out of the line rather than drawn
    # as a fall. The newest bar always under-reads — the week is not over, and
    # matching runs days behind publication — so plotting it draws a collapse
    # that is not there.
    settled = [w for w in weekly if not w.get("partial")]
    dropped = len(weekly) - len(settled)
    cards.append(_metric_card(
        "Written about by others", "excludes the vendors' own posts",
        f"{earned:,}",
        _delta(earned, earned_prev, period="the 30 days before")
        + (f". {earned_note}" if earned_note else ""),
        _spark([w.get("n") or 0 for w in settled],
               label="Articles and posts matched each week, completed weeks only")
        or "",
        nospark=("The last week is still filling, so there is nothing "
                 "settled to chart yet." if dropped and not settled
                 else "" if settled else "Not enough weeks to chart."),
        caption=(f"Completed weeks only. The most recent {dropped} "
                 f"{'week is' if dropped == 1 else 'weeks are'} still filling "
                 "and would read as a fall." if dropped else "")))

    return f'<section class="n-metrics">{"".join(cards)}</section>'


_PLATFORM_NAMES = {"linkedin": "LinkedIn", "twitter": "X", "x": "X",
                   "bluesky": "Bluesky", "reddit": "Reddit",
                   "mastodon": "Mastodon"}


def _evidence_label(row: Dict[str, Any], seen: set) -> str:
    """A link somebody would click, not "linkedin" and not "source 2".

    The vendor's own announcement is named as that. A publisher is named by
    its masthead. A repeated label takes the record's title instead, because
    two links both reading "LinkedIn" tell a reader nothing about which to
    open.
    """
    source = (row.get("source") or "").strip()
    title = (row.get("title") or "").strip()
    platform = _PLATFORM_NAMES.get(source.lower(), source)

    if row.get("voice") == "owned":
        label = (f"the company's {platform} post" if platform
                 else "the company's own announcement")
    elif row.get("voice") == "primary":
        label = f"a filing on {platform}" if platform else "a primary document"
    else:
        label = platform or "an outside report"

    if label.lower() in seen and title:
        label = _clip(title, 60)
    seen.add(label.lower())
    return label


def _story_evidence(f: Dict[str, Any]) -> str:
    """Every record behind a finding, split into records and discussion.

    The split is *whose voice*, not whether the item carries social metadata.
    A vendor announcing a product on LinkedIn is the announcement — filing it
    under "Social" beside practitioner chatter said the company's own statement
    was somebody talking about it.
    """
    rows = [r for r in (f.get("supporting") or []) if r.get("uri")]
    if not rows:
        held = int(f.get("evidence_count") or 0)
        if not held:
            return ""
        return ('<div class="n-support"><strong>Evidence:</strong> '
                f'{held} record{"" if held == 1 else "s"} held, none with a '
                'public link</div>')

    seen: set = set()
    records = [r for r in rows if r.get("voice") == "owned" or not r.get("social")]
    discussion = [r for r in rows if r not in records]

    def links(items):
        return ", ".join(f'<a href="{esc(r["uri"])}">'
                         f'{esc(_evidence_label(r, seen))}</a>' for r in items)

    out = ['<div class="n-support">']
    if records:
        # "Evidence" when there is one record and nothing to add to it;
        # "More" when the list actually continues past the byline.
        label = "Evidence" if len(records) == 1 and not discussion else "More"
        out.append(f"<div><strong>{label}:</strong> {links(records)}</div>")
    if discussion:
        out.append(f"<div><strong>Social:</strong> {links(discussion)}</div>")
    out.append("</div>")
    return "".join(out)


def _news_stories(findings: Optional[Dict[str, Any]], *, limit: int = 8) -> str:
    """Findings as stories: a tag, what changed, and what backs it.

    The byline carries the evidence state rather than a source name, because
    that is the fact a reader of a shared report most needs and least has. A
    vendor's own announcement says so in the line under the headline.
    """
    if not findings:
        return ""
    rows = (findings.get("executive") or []) + [
        f for f in (findings.get("data") or [])
        if f not in (findings.get("executive") or [])]
    rows = rows[:limit]
    if not rows:
        state = ((findings.get("meta") or {}).get("synthesis") or {})
        detail = state.get("detail") or "Nothing met the bar for a finding."
        return f'<p class="n-empty">{esc(detail)}</p>'

    themes = sorted({f.get("theme") for f in rows if f.get("theme")})
    out = ['<div class="n-filters" role="group" aria-label="Filter by theme">',
           '<button type="button" class="n-filter" data-theme="all" '
           'aria-pressed="true">All</button>']
    for theme in themes:
        out.append(f'<button type="button" class="n-filter" '
                   f'data-theme="{esc(theme)}" aria-pressed="false">'
                   f'{esc(theme)}</button>')
    out.append("</div>")

    for f in rows:
        theme = f.get("theme") or ""
        colour = _THEME_COLOUR.get(theme, "var(--n-accent)")
        # The event date where one was established, and never the observation
        # date dressed up as one.
        when = f.get("occurred_at")
        when_txt = (_day(when) if when else "date not established")
        sources = f.get("non_vendor_source_count") or 0
        if sources:
            evidence = f"{sources} outside source" + ("s" if sources > 1 else "")
        elif f.get("vendor_voiced") and f.get("self_reportable"):
            # Nobody else can confirm that a company shipped its own product,
            # so "no independent source" here reported a gap that does not
            # exist. The vendor is the record. The byline already names it.
            evidence = "the company's own announcement"
        elif f.get("vendor_voiced"):
            evidence = "the company's claim, nobody else has said it"
        else:
            evidence = "one source"
        out.append(f'<article class="n-story" data-theme="{esc(theme)}" '
                   f'style="--story:{colour}">')
        vendor_names = [v.get("vendor", "") for v in (f.get("vendors") or [])]
        # The extractor prefixes the vendor onto the title, and the byline
        # directly below names it again. "Crogl: Crogl · 20 Aug" reads as a
        # bug, so the prefix comes off when it is one of this finding's own
        # vendors.
        headline = (f.get("headline") or "Untitled").strip()
        for name in vendor_names:
            if name and headline.lower().startswith(f"{name.lower()}:"):
                headline = headline[len(name) + 1:].lstrip() or headline
                break
        out.append(f'<div class="n-story-tag">{esc(theme)}</div>')
        out.append(f'<h3>{esc(headline)}</h3>')
        # A summary that repeats the headline is not a summary. These events
        # are extracted from a post whose first sentence became the title, so
        # the two are frequently the same words.
        summary = (f.get("why_it_matters") or f.get("summary") or "").strip()
        head_key = _norm_words(headline)
        sum_key = _norm_words(summary)
        # `in`, not `startswith`. The title is often the post's *closing* line,
        # so comparing only the openings let the same sentence print twice with
        # three paragraphs between the copies.
        duplicate = bool(head_key) and (
            head_key[:60] in sum_key or sum_key[:60] in head_key)
        if summary and not duplicate:
            out.append(f'<p class="n-story-sum">{esc(_clip(summary, 320))}</p>')
        vendors = ", ".join(vendor_names)
        bits = [b for b in (vendors, when_txt, evidence) if b]
        out.append('<div class="n-byline">'
                   + " · ".join(esc(b) for b in bits) + "</div>")
        # Why it sits where it sits, in the rule's own words. "medium
        # materiality" in the byline was a label with no content; the rule that
        # produced it is a sentence a reader can argue with.
        # Only where it says something. "a change in one vendor's position"
        # printed under every card is furniture, not an explanation.
        why = (f.get("materiality_reason") or "").strip()
        if why in ("no rule ranks this type higher",
                   "a change in one vendor's position",
                   "hiring is a weak signal on its own"):
            why = ""
        if why:
            out.append(f'<div class="n-why">Ranked {esc(f.get("materiality") or "")}'
                       f' — {esc(why)}</div>')
        out.append(_story_evidence(f))
        out.append("</article>")
    return "".join(out)


def _news_aside(*, movers: Optional[Dict[str, Any]],
                highlights: List[Dict[str, Any]],
                notes: List[str], days: int) -> str:
    """Movers and social highlights, with an explicit empty state for each.

    Both are frequently empty in a young market, and an empty panel that says
    nothing reads as a broken page rather than a quiet one. Where a metric
    cannot state a change at all, it is named with the reason — "no movers" and
    "we cannot measure movement" are different answers.
    """
    out = ['<aside class="n-aside">']

    rows = (movers or {}).get("movers") or []
    blocked = (movers or {}).get("unavailable") or []
    out.append('<section class="n-card"><div class="n-card-title">'
               f'<h2>Who moved</h2><span class="n-updated">{days}d</span>'
               '</div>')
    if rows:
        for i, m in enumerate(rows[:6], 1):
            out.append(f'<div class="n-row"><span class="n-rank">{i}</span>'
                       f'<div><strong>{esc(m.get("vendor") or "")}</strong>'
                       f'<div class="n-row-label">{esc(m.get("metric") or "")}'
                       + (f' · {esc(m["detail"])}' if m.get("detail") else "")
                       + '</div></div>'
                       f'<span class="n-row-val">{esc(m.get("value") or "")}'
                       '</span></div>')
    else:
        out.append('<p class="n-empty">Nothing moved enough to report across '
                   'staff, coverage or open roles.</p>')
    for b in blocked:
        out.append(f'<p class="n-note">{esc(b.get("metric") or "")}: '
                   f'{esc(b.get("reason") or "")}.</p>')
    out.append("</section>")

    out.append('<section class="n-card"><div class="n-card-title">'
               '<h2>Social highlights</h2>'
               '<span class="n-updated">outside voices</span></div>')
    if highlights:
        for h in highlights[:3]:
            meta = " · ".join(x for x in (
                f'@{h.get("author")}' if h.get("author") else "",
                h.get("platform") or "",
                (f'{h["engagement"]:,} reactions, comments and reposts'
                 if h.get("engagement") else "no measured response")) if x)
            quote = _clip(h.get("quote") or "", 190)
            body = (f'<a href="{esc(h["uri"])}">&ldquo;{esc(quote)}&rdquo;</a>'
                    if h.get("uri") else f'&ldquo;{esc(quote)}&rdquo;')
            out.append('<div class="n-social">'
                       f'<div class="n-social-meta">{esc(meta)}</div>'
                       f'<p class="n-quote">{body}</p></div>')
    else:
        out.append('<p class="n-empty">Nobody outside the vendors posted about '
                   'this market during the period.</p>')
    out.append("</section>")

    if notes:
        out.append('<section class="n-card"><div class="n-card-title">'
                   '<h2>Worth knowing</h2></div>')
        for n in notes[:3]:
            out.append(f'<p class="n-empty">{esc(n)}</p>')
        out.append("</section>")

    out.append("</aside>")
    return "".join(out)


#: Client-side theme filter. Inline because the report is opened from a saved
#: file as often as from a URL, and anything fetched would not survive that.
_NEWS_JS = """
(function(){var r=document.querySelector('.mm-news');if(!r)return;
var f=[].slice.call(r.querySelectorAll('[data-theme].n-filter'));
var s=[].slice.call(r.querySelectorAll('article.n-story'));
f.forEach(function(b){b.addEventListener('click',function(){
var t=b.getAttribute('data-theme');
f.forEach(function(o){o.setAttribute('aria-pressed',String(o===b));});
s.forEach(function(a){a.hidden=(t!=='all'&&a.getAttribute('data-theme')!==t);});
});});
var v=[].slice.call(r.querySelectorAll('.n-views button'));
v.forEach(function(b){b.addEventListener('click',function(){
r.setAttribute('data-view',b.getAttribute('data-view'));
v.forEach(function(o){o.setAttribute('aria-pressed',String(o===b));});
});});})();
"""


def _relink(params: Dict[str, Any], **overrides: Any) -> str:
    """The current query string with some values replaced.

    The period links have to carry the signed token through, or a shared
    reader switching from 30 days to 7 lands on a 404. `days` is not part of
    what the token signs, so only the window changes.
    """
    from urllib.parse import urlencode

    merged = {k: v for k, v in {**params, **overrides}.items() if v is not None}
    return esc(urlencode(merged))


def build_market_report(conn, market: Dict[str, Any], *, days: int = 30,
                        allowed_brand_ids: Optional[List[int]] = None,
                        link_params: Optional[Dict[str, Any]] = None
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
    from app.services import market_metrics as mmet
    from app.services import market_publish as mp

    from app.services import market_entitlements as ent

    overview = mp.build_overview(conn, market, days=days)
    analyses = {}
    for name in man.ANALYSES:
        try:
            analyses[name] = man.run(conn, market["id"], name)
        except Exception as exc:  # noqa: BLE001 — a missing panel is not a
            logger.warning("report analysis %s failed: %s", name, exc)

    # A restricted viewer gets a report assembled from only the vendors it may
    # see. Filtered here, at the top, rather than section by section further
    # down: thirteen sections name a vendor, and remembering all thirteen is
    # the kind of thing that holds until somebody adds a fourteenth.
    #
    # The rendered bytes are checked again at the end, because a name also
    # reaches the page through an event headline or an article title, which no
    # row filter can catch.
    allowed_names = None
    withheld = ent.withheld_names(conn, market["id"], allowed_brand_ids)
    if allowed_brand_ids is not None:
        allowed_names = set(
            ent.vendor_names(conn, market["id"], allowed_brand_ids).values())

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

    # The sidebar's three panels, each its own failure. A market with no social
    # corpus should lose the quotes panel and keep the movers, not the page.
    try:
        highlights = man.social_highlights(conn, market["id"], days=days,
                                           limit=3)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("social highlights failed: %s", exc)
        highlights = []
    try:
        movers = mp.market_movers(conn, market, days=days)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("market movers failed: %s", exc)
        movers = None
    # The same window, one period back, for the metric strip's delta.
    try:
        earned_prev = int(man.share_of_voice(
            conn, market["id"], days=days * 2,
            until_days_ago=days).get("earned_total") or 0)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("previous-period share of voice failed: %s", exc)
        earned_prev = None

    # Carried through every period link so a shared reader switching windows
    # keeps the signed token. Empty for an operator opening it with a session.
    link_params = dict(link_params or {})

    # Fetched once, up front — "What changed", "Material vendor moves",
    # "Market discussion", the registry sort and "Raw coverage" all read the
    # same deduplicated, classified list rather than re-querying per section.
    dataset = mp.build_dataset(conn, market["id"])
    articles = mcorp.articles(conn, market["id"], limit=60, days=days)

    # The shared-link lead: findings rather than a feed, and the job figures
    # the metric strip quotes.
    try:
        from app.services import market_findings as mfind
        findings = mfind.findings(conn, market["id"], days=days, page_size=20)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report findings failed: %s", exc)
        findings = None
    try:
        from app.services import market_lists as mlists
        joblist = mlists.jobs(conn, market["id"], page_size=1)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report jobs failed: %s", exc)
        joblist = None
    # Fetched with the rest rather than beside the methodology appendix that
    # used to be its only reader: the news strip and the appendix must quote
    # the same object or they will disagree about the market's headcount.
    try:
        headcount = mp.headcount_market(conn, market)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report headcount failed: %s", exc)
        headcount = None

    # ── The entitlement gate ────────────────────────────────────────────
    #
    # Applied here, after every fetch and before anything is rendered, so
    # there is one place to look rather than thirteen. Filtering only the
    # overview and the analyses left 74 of 84 vendors named, because the
    # registry, the voices, the period comparison and the article corpus are
    # separate payloads.
    #
    # Articles are filtered by *text*, not only by attribution: a story about
    # two companies is attributed to one of them, and dropping it on
    # attribution alone would still print the other's name in the headline.
    if allowed_brand_ids is not None:
        overview = ent.filter_rows(overview, allowed_brand_ids, allowed_names)
        analyses = ent.filter_rows(analyses, allowed_brand_ids, allowed_names)
        formation = analyses.get("formation")
        sn = analyses.get("signal_noise")
        funding = analyses.get("funding")
        hiring = analyses.get("hiring")
        sov = analyses.get("share_of_voice")
        pc = ent.filter_rows(pc, allowed_brand_ids, allowed_names)
        voices = ent.filter_rows(voices, allowed_brand_ids, allowed_names)
        dataset = ent.filter_rows(dataset, allowed_brand_ids, allowed_names)
        articles = ent.drop_text_mentioning(articles, withheld)
        # Findings name vendors in their headline as well as in their vendor
        # list, so both filters apply: the row filter for attribution, the text
        # filter for a partner named in the headline of somebody else's news.
        if findings:
            for key in ("data", "executive", "watch_items"):
                rows = ent.filter_rows(findings.get(key) or [],
                                       allowed_brand_ids, allowed_names)
                findings[key] = ent.drop_text_mentioning(rows, withheld)
        if joblist:
            joblist["data"] = ent.filter_rows(joblist.get("data") or [],
                                              allowed_brand_ids, allowed_names)

    vendor_names = [d["vendor"] for d in dataset]
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
    body: List[str] = [f"<style>{EXTRA_CSS}{NEWS_CSS}</style>"]

    # ================================================================
    # The lead: a market news page
    # ================================================================
    #
    # What a shared link opens on. The detailed sections below are unchanged
    # and still carry the methodology appendix the specification requires —
    # this is the scannable front, not a replacement for the evidence.
    period_range = _fmt_range(*pc["current_range"]) if pc else None
    period_txt = (period_range or f"last {days} days")

    # Fetched with the period, because the strip is labelled with one.
    # `analyses` is built by `man.run(...)` without `days`, so its share of
    # voice is all-time — correct for the sections below, which do not claim a
    # window, and wrong under a heading that says "last 30 days".
    try:
        sov_block = man.share_of_voice(conn, market["id"], days=days) or {}
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("report windowed share of voice failed: %s", exc)
        sov_block = analyses.get("share_of_voice") or {}
    if allowed_brand_ids is not None:
        sov_block = ent.filter_rows(sov_block, allowed_brand_ids, allowed_names)
    earned = int(sov_block.get("earned_total") or 0)
    own_posts = int(sov_block.get("own_total") or 0)
    earned_note = (
        f"The vendors published {own_posts:,} posts themselves over the same "
        "period" if own_posts else "Nothing from the vendors' own channels")

    jobs_total = int(((joblist or {}).get("meta") or {})
                     .get("pagination", {}).get("total") or 0)
    jobs_meta = ((joblist or {}).get("meta") or {}).get("metric") or {}
    jobs_new = 0
    jobs_notes = ((joblist or {}).get("meta") or {}).get("notes") or []

    # Computed here rather than at the "What changed" section below, because
    # the news page's summary is these same sentences. They are counted facts
    # with their denominators, not generated commentary — which is the only
    # kind of summary this page can carry, since everything else on it traces
    # to a record.
    changed_points: List[str] = []
    if formation and formation.get("vendors_in_scope"):
        changed_points.append(
            f'{formation["founded_since_2023"]} of the '
            f'{formation["vendors_in_scope"]} vendors here were founded in '
            '2023 or later, so this is a young market.')
    kind_n: Dict[str, int] = {}
    if sn and sn.get("signal_kinds"):
        kind_n = {k["kind"]: k["n"] for k in sn["signal_kinds"]}
        launch_n = kind_n.get("launch", 0)
        commercial_n = sum(kind_n.get(k, 0) for k in
                           ("partnership", "customer", "funding", "acquisition"))
        if launch_n or commercial_n:
            changed_points.append(
                f'They talk about product far more than about business. We '
                f'counted {launch_n} launch announcements against '
                f'{commercial_n} covering partnerships, customers, funding and '
                'acquisitions put together.')
    if hire_lead:
        changed_points.append(f'Hiring is concentrated. {hire_lead}')
    if kind_n.get("acquisition") or any(k == "acquisition" for _, k in material_rows):
        changed_points.append(
            'At least one company in this market was acquired during the '
            'period.')

    body.append('<div class="mm-news" data-view="top">')
    body.append('<div class="n-top">'
                '<span class="n-brand"><span class="n-logo">A</span>'
                '<span>Aunoo AI</span></span>'
                '<nav class="n-jump" aria-label="Jump to section">'
                '<a href="#mm-overview">Overview</a>'
                '<a href="#mm-changed">Findings</a>'
                '<a href="#mm-news">News</a>'
                '<a href="#mm-registry">Vendors</a></nav>'
                f'<span class="n-market">{esc(market["name"])}</span></div>')

    body.append('<main class="n-main"><span id="mm-overview"></span>')
    # The reporting period as links, not a control. `days` is a query parameter
    # and the signed token covers (market, expiry) only, so the same link works
    # at any window — which is what makes three anchors possible in a file that
    # has no server behind it.
    periods = "".join(
        f'<a href="?{_relink(link_params, days=d)}"'
        + (' aria-current="page"' if d == days else "")
        + f'>{d} days</a>' for d in (7, 30, 90))
    body.append('<div class="n-head"><div>'
                f'<div class="n-kicker">Market monitor · {esc(period_txt)}</div>'
                f'<h1>{esc(market["name"])} briefing</h1>'
                '<p class="n-sub">What the vendors in this market did over the '
                'period, and where each of those came from.</p></div>'
                f'<div><nav class="n-periods" aria-label="Reporting period">'
                f'{periods}</nav>'
                f'<div class="n-period">Generated '
                f'{generated.strftime("%d %B %Y, %H:%M UTC")}</div></div></div>')

    # The summary is the counted facts from "What changed", not prose about
    # them. Everything else on this page traces to a record, and a synthesised
    # paragraph would be the one thing that does not.
    question = (market.get("question") or "").strip()
    if changed_points or question:
        body.append('<section class="n-summary"><h2>In summary</h2>')
        if changed_points:
            body.append("<p>" + " ".join(changed_points) + "</p>")
        if question:
            body.append('<p class="n-note">What we are tracking: '
                        f'{esc(question[:700])}</p>')
        body.append("</section>")

    body.append(_news_metrics(
        headcount=headcount, jobs_total=jobs_total, jobs_new=jobs_new,
        jobs_state=(jobs_meta.get("data_state") or "healthy"),
        funding=funding, earned=earned, earned_note=earned_note,
        earned_prev=earned_prev, movers=movers,
        weekly=((overview.get("corpus") or {}).get("by_week") or [])))

    body.append('<div class="n-grid"><section><span id="mm-news"></span>')
    # Three densities of the same list in the same order. Nothing is reordered
    # or dropped between them — a reader scanning for one item finds it in the
    # same place — so the switch is CSS and needs no second copy of the feed.
    views = "".join(
        f'<button type="button" data-view="{k}" '
        f'aria-pressed="{"true" if k == "top" else "false"}">{label}</button>'
        for k, label in (("top", "Top News"), ("headlines", "Headlines"),
                         ("river", "River")))
    rss = ""
    if market.get("is_public"):
        # A feed reader carries no session, so the RSS link is only real on a
        # market that serves anonymously. Offering it otherwise hands a shared
        # reader a link that 404s.
        rss = (f'<a class="n-rss" href="feed.xml?days={days}" '
               'title="Subscribe in a feed reader">RSS</a>')
    body.append('<div class="n-sec-head"><h2>Market news</h2>'
                f'<div class="n-sec-actions"><div class="n-views" '
                f'role="group" aria-label="News density">{views}</div>{rss}'
                f'<span class="n-updated">{esc(period_txt)}</span>'
                '</div></div>')
    body.append(_news_stories(findings))
    body.append("</section>")

    notes = list(jobs_notes)
    if findings:
        notes = ((findings.get("meta") or {}).get("notes") or []) + notes
    body.append(_news_aside(movers=movers, highlights=highlights,
                            notes=notes, days=days))
    body.append("</div></main></div>")
    body.append(f"<script>{_NEWS_JS}</script>")

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
                    'this market, so what counts as being in it has never '
                    'been written down. Some of what follows may be about '
                    'companies or stories that do not belong here. Writing a '
                    'scope description fixes that.</p>')
    body.append("</section>")

    if changed_points:
        body.append('<span id="mm-changed"></span>')
        body.append(section_open("What changed"))
        body.append("<p>" + " ".join(changed_points) + "</p>")

        if pc:
            labels_pc = {
                "_coverage": "Articles and posts", "launch": "Product launches",
                "partnership": "Partnerships", "customer": "Customer announcements",
                "funding": "Funding announcements", "acquisition": "Acquisitions",
                "hiring": "Posts about people joining", "_jobs": "Open roles",
            }
            order_pc = ("_coverage", "launch", "partnership", "customer",
                       "funding", "acquisition", "hiring", "_jobs")
            rows_pc = []
            for key in order_pc:
                cur, prev = pc["current"].get(key, 0), pc["previous"].get(key, 0)
                if cur == 0 and prev == 0:
                    continue
                if prev == 0:
                    change = "nothing to compare against"
                else:
                    d = cur - prev
                    change = f'{"+" if d > 0 else ""}{d}'
                rows_pc.append(
                    f'<tr><td>{esc(labels_pc[key])}</td>'
                    f'<td class="mm-num">{cur}</td>'
                    f'<td class="mm-num">{prev}</td>'
                    f'<td class="mm-src">{esc(change)}</td></tr>')
            if rows_pc:
                body.append(f'<h3>Compared with the previous {days} days</h3>')
                body.append(f'<p class="mm-src">'
                           f'{esc(_fmt_range(*pc["current_range"]))} against '
                           f'{esc(_fmt_range(*pc["previous_range"]))}. Where we '
                           'were not measuring something yet in the earlier '
                           'period, we say so rather than show it as a rise '
                           'from zero.</p>')
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
    body.append(_stat("Vendors in this market",
                      str(cov["registry"] - cov["excluded"]),
                      f'{cov["watching"]} currently monitored'))
    body.append(_stat("Money raised, where disclosed",
                      _money(fund["total_musd"]),
                      f'{fund["disclosed"]} of '
                      f'{fund["disclosed"] + fund["undisclosed"]} vendors have '
                      'published a figure'))
    if formation and formation.get("vendors_in_scope"):
        body.append(_stat("Founded since 2023",
                          str(formation["founded_since_2023"]),
                          f'of the {formation["vendors_in_scope"]} whose '
                          'founding year we know'))
    body.append(_stat("Articles and posts collected",
                      str(corpus.get("total", 0)),
                      f'over the {days} days covered here'))
    body.append("</div></section>")

    # ================================================================
    # Material vendor moves — deduplicated, grouped by kind, before raw coverage
    # ================================================================
    body.append(section_open("What the vendors did"))
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
                # "3 sources · Only the vendor has said this" reads as a
                # contradiction. It is not — those are three posts from the
                # vendor about one thing — so the count says which it is.
                vendor_only = corrob == "Only the vendor has said this"
                noun = "vendor post" if vendor_only else "source"
                count = (f'{sources} {noun}{"" if sources == 1 else "s"}'
                         if not vendor_only or sources > 1 else "")
                row_html.append(
                    f'<tr><td><a href="{esc(a["uri"])}">{esc(headline)}</a>'
                    f'<div class="mm-src">{esc(a.get("news_source") or "")}'
                    f' · {esc((a.get("published") or "")[:10])}'
                    + (f' · {count}' if count else "")
                    + f' · {esc(corrob)}</div></td></tr>')
            body.append('<table class="mm-table"><tbody>'
                       + "".join(row_html) + "</tbody></table>")
    body.append("</section>")

    # ================================================================
    # Competitive signals — sentiment, headcount, hiring, Crunchbase
    # ================================================================
    body.append(section_open("How the market is moving"))
    any_signal = False

    sentiment_trend = corpus.get("sentiment_trend") or []
    if any(r.get("net_all") is not None for r in sentiment_trend):
        any_signal = True
        body.append("<h3>Sentiment</h3>")
        latest_sentiment = next(
            (r["net_all"] for r in reversed(sentiment_trend) if r.get("net_all") is not None),
            None)
        body.append(_reading(latest_sentiment))
        body.append('<p class="mm-src">Each article is classed positive, '
                    "negative or neutral. The line is the share that came out "
                    "positive minus the share that came out negative, week by "
                    "week. Where too few articles were classified in a week to "
                    "call it either way, we leave the week blank instead of "
                    "drawing a zero.</p>")
        vendor_points = sum(1 for r in sentiment_trend if r.get("net_vendor") is not None)
        series = [("net_broad", "#475569", "The market as a whole")]
        if vendor_points >= 3:
            series.append(("net_vendor", "#30a46c", "Coverage of these vendors"))
        body.append(_line_chart(sentiment_trend, x_key="week", series=series))
        if vendor_points < 3:
            body.append(f'<p class="mm-src">We are not showing a separate '
                        'line for the tracked vendors. Only '
                        f'{vendor_points} week'
                        f'{"" if vendor_points == 1 else "s"} had enough '
                        'coverage about them to classify with confidence, '
                        'which is not enough to draw.</p>')

    # The window is clipped to how long this market has existed (see
    # market_publish.headcount_trend) — a vendor snapshot cannot predate the
    # market's own registry — so points can genuinely be a short list on a
    # young market, not a sign of missing collection.
    hc_trend = mp.headcount_trend(conn, market, weeks=26)
    hc_with_data = [p for p in hc_trend["points"] if p.get("avg_pct_vs_baseline") is not None]
    if hc_with_data:
        any_signal = True
        body.append("<h3>Headcount change</h3>")
        body.append('<p class="mm-src">How far each vendor has moved from '
                    "its own first reading, averaged across the market. We use "
                    "percentages so the line does not jump every time a vendor "
                    "is added. Each vendor starts from the day we first read "
                    "it, so there is no single start date. Trust a week less "
                    "when it covers fewer than half of the "
                    f'{hc_trend["watching"]} vendors we watch.</p>')
        if len(hc_with_data) == 1:
            only = hc_with_data[0]
            pct = only["avg_pct_vs_baseline"]
            body.append(f'<p>We have one week of readings so far, the week '
                        f'of {esc(only["week"])}, at '
                        f'{"+" if pct > 0 else ""}{pct}% against where these '
                        'vendors started. Two weeks makes a line.</p>')
        else:
            body.append(_line_chart(
                hc_trend["points"], x_key="week",
                series=[("avg_pct_vs_baseline", "#475569",
                         "Average change since first reading")]))

    if hiring and hiring["openings"]:
        any_signal = True
        body.append("<h3>Hiring</h3>")
        body.append(f'<p>We found {hiring["openings"]} open roles across '
                    f'{len(hiring["by_vendor"])} vendors.</p>')
        body.append('<p class="mm-src">What a company hires for says something '
                    'about where it is spending. It does not say whether the '
                    'product is good or whether anyone is buying it.</p>')
        if hire_lead:
            body.append(f'<p>Hiring is concentrated. {hire_lead}</p>')
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
    body.append(section_open("Who is being heard"))
    # Filtered on `activity_index`, not on the old `signals` key. That key was
    # removed from the overview payload when the posts+jobs sum was dropped, and
    # this filter kept reading it — so the list was empty on every report and
    # the section silently stopped rendering. The live page still showed the
    # table, which is exactly the export/UI divergence spec 6 forbids.
    active = overview.get("most_active") or []
    scored = [v for v in active if v.get("activity_index") is not None]
    top = (scored or active)[:ACTIVITY_TOP_N]
    if top:
        body.append("<h3>Most active vendors</h3>")
        body.append(
            f'<p class="mm-src">The {len(top)} busiest vendors. We rank each '
            'one against the others on three things: LinkedIn posts in the '
            f'last {days} days, roles open today, and articles about them by '
            f'somebody else in the last {days} days. The score averages those '
            'three ranks. It says how visible a vendor is, not how well it is '
            'doing. A vendor only gets a score if we managed to measure all '
            'three.</p>')
        if scored:
            body.append(_bar_chart(top, label_key="vendor",
                                   value_key="activity_index"))
        body.append(
            '<table class="mm-table"><thead><tr><th>Vendor</th>'
            '<th class="mm-num">Score</th>'
            '<th class="mm-num">Own posts</th>'
            '<th class="mm-num">Open roles</th>'
            '<th class="mm-num">Written about</th></tr></thead><tbody>'
            + "".join(_activity_row(v) for v in top)
            + "</tbody></table>")
        # Named for what it counts. As `withheld` it shadowed the list of
        # vendor names the entitlement backstop checks the finished page
        # against — so by the time that check ran it held an integer, and its
        # "nothing to check" guard fired on a count of 0. The last line of
        # defence against naming a withheld vendor was silently disabled on
        # every shared report where this table rendered.
        unscored = sum(1 for v in active if v.get("activity_index") is None)
        if unscored:
            body.append(
                f'<p class="mm-src">{unscored} vendors have no score, '
                'because we could not measure at least one of the three '
                'things. Scoring them anyway would put a vendor we failed to '
                'read below one we read and found quiet.</p>')

    if sov and not sov.get("error") and sov.get("vendors"):
        earned_rows = sorted(
            [v for v in sov["vendors"] if v.get("earned")],
            key=lambda v: v.get("earned_share") or 0, reverse=True)
        if earned_rows:
            body.append("<h3>Share of voice</h3>")
            body.append(f'<p class="mm-src">How {sov["earned_total"]} '
                        'mentions by people outside these companies were '
                        "split between them. The vendors' own posts are "
                        'counted separately, further down.</p>')
            body.append(_bar_chart(
                [{"vendor": v["vendor"], "pct": round((v["earned_share"] or 0) * 100)}
                 for v in earned_rows],
                label_key="vendor", value_key="pct", colour="#30a46c"))

        loud_rows = [v for v in sov.get("vendors") or []
                    if v.get("reactions_per_post") is not None]
        if loud_rows:
            body.append("<h3>Posting a lot is not the same as landing</h3>")
            body.append('<p class="mm-src">How much each vendor posts, next to '
                        'how much response those posts get. A vendor we have '
                        'seen fewer than five posts from is left out.</p>')
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
        body.append(section_open("What people are saying"))
        body.append('<p class="mm-src">Practitioners and analysts arguing '
                    'about where this market is going, rather than news about '
                    'any one vendor. We strip out the obvious noise, like '
                    'job-hunting posts, with a keyword filter. It is a rough '
                    'filter and some noise gets through.</p>')
        body.append('<table class="mm-table"><tbody>'
                   + "".join(_coverage_row(a) for a in discussion_rows[:20])
                   + "</tbody></table>")
        body.append("</section>")

    # ================================================================
    # The registry — sorted by most recent material signal
    # ================================================================
    registry_rows = [r for r in dataset if r.get("role") != "excluded"]
    registry_rows.sort(key=lambda r: last_material.get(r["vendor"], ""), reverse=True)
    body.append('<span id="mm-registry"></span>')
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
    body.append(section_open("How much of the market we checked"))
    registry_total = cov["registry"] - cov["excluded"]
    body.append('<table class="mm-table"><thead><tr><th>Coverage</th>'
               '<th class="mm-num">Vendors</th><th class="mm-num">%</th>'
               "</tr></thead><tbody>")
    body.append(_pct_row("Being watched", cov["watching"], registry_total))
    body.append(_pct_row("Paused", cov["paused"], registry_total))
    body.append(_pct_row("We have seen something from", cov["observed"], registry_total))
    if formation and formation.get("announcement_coverage"):
        ac = formation["announcement_coverage"]
        body.append(_pct_row("LinkedIn posts read", ac["measured"], ac["total"]))
    if funding and funding.get("coverage"):
        fc = funding["coverage"]
        body.append(_pct_row("Crunchbase profile read", fc["measured"], fc["total"]))
    if hiring and hiring.get("coverage"):
        hc = hiring["coverage"]
        body.append(_pct_row("Job boards read", hc["measured"], hc["total"]))
    body.append("</tbody></table>"
               f'<p class="mm-src">{overview["quiet_vendors"]} of the '
               f'{registry_total} vendors we watch showed nothing this period '
               '— no posts, no open roles, nothing written about them in what '
               'we collect. That means we saw nothing, not that they did '
               'nothing.</p>'
               "</section>")

    # ================================================================
    # About this report
    # ================================================================
    body.append(section_open("About this report"))
    body.append(
        "<p>Aunoo keeps a list of the vendors in this market and matches "
        "everything it collects against the phrases that define the market. "
        "Some of what you see here was first collected for a different topic "
        "and matched into this one. Company and funding details come from "
        "LinkedIn and Crunchbase. How much we cover varies by vendor and by "
        "source, so any panel above that rests on part of the list says how "
        "many vendors it covers.</p>"
        "<p><strong>Seeing nothing is not the same as nothing having "
        "happened.</strong> It means the sources we watch did not carry it. "
        "Where a count could mean either &ldquo;we looked and found "
        "none&rdquo; or &ldquo;we have not looked yet&rdquo;, this report "
        "shows a dash for the second, never a zero.</p>")
    body.append("</section>")

    # ================================================================
    # Raw coverage — collapsed, everything, for auditability
    # ================================================================
    if clustered:
        body.append(section_open("Everything we collected"))
        body.append(f'<details><summary>Everything we matched: '
                    f'{len(articles)} articles and posts, including general '
                    'discussion and anything too small to report above'
                    '</summary>')
        body.append('<table class="mm-table"><tbody>'
                    + "".join(_coverage_row(a) for a in clustered)
                    + "</tbody></table></details>")
        body.append("</section>")

    # ================================================================
    # Methodology — definitions, sources, and what we did not measure
    # ================================================================
    #
    # The spec's rule is that no metric may look more definitive in the
    # downloadable file than on the live page. The figures above already come
    # from the same payload the UI renders, so the gap was never the numbers —
    # it was that the file carried none of the definitions, none of the source
    # labels and none of the collection state, so a reader who opened it a month
    # later had no way to tell what any of it had been measured against.
    body.append('<span id="mm-method"></span>')
    body.append(section_open("Where the numbers come from"))

    body.append("<h3>Which sources we use</h3>")
    body.append(
        "<p>Where something was published and who we bought it from are two "
        "different things. LinkedIn is a place things get published. Bright "
        "Data and Xpoz are companies we buy the data through, and items from "
        "Xpoz name the place they were published themselves.</p>")
    body.append('<table class="mm-table"><thead><tr>'
                "<th>What</th><th>Published on</th>"
                "<th>We get it from</th><th>Whose words</th>"
                "</tr></thead><tbody>")
    for row in mmet.SOURCE_LEGEND:
        body.append(f'<tr><td>{esc(row["content"])}</td>'
                    f'<td>{esc(row["platform"])}</td>'
                    f'<td>{esc(row["provider"])}</td>'
                    f'<td>{esc(row["ownership"])}</td></tr>')
    body.append("</tbody></table>")

    body.append("<h3>How much of the market each source covers</h3>")
    body.append(
        "<p>&ldquo;Checked&rdquo; counts the vendors we successfully read "
        "from a source, out of the ones we <em>can</em> read from it. Those "
        "are different numbers: a source needs something to look the company "
        "up by, and not every vendor has one. Where we have nothing to look up "
        "at all, we say the source is not set up rather than showing you a "
        "zero.</p>")
    body.append('<table class="mm-table"><thead><tr>'
                "<th>Source</th><th>State</th><th>Checked</th><th>Notes</th>"
                "</tr></thead><tbody>")
    for src in mmet.tracked_sources():
        try:
            st = mmet.collection_state(conn, market["id"], src)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("report collection state %s failed: %s", src, exc)
            continue
        cov = st["coverage"]
        reached = (f'{cov["successful"]}/{cov["eligible"]}'
                   if cov["eligible"] else "&mdash;")
        # The reader-facing half of the state. The operator note behind it
        # names internal fields and API quirks nobody outside can act on.
        note = st.get("state_detail_public") or st.get("state_detail") or ""
        body.append(
            f'<tr><td>{esc(src)}</td>'
            f'<td>{esc(mmet.STATE_LABELS.get(st["state"], st["state"]))}</td>'
            f'<td>{reached}</td>'
            f'<td>{esc(note)}</td></tr>')
    body.append("</tbody></table>")

    body.append("<h3>What each figure counts</h3>")
    # Definitions are pulled from the metric blocks the aggregates already
    # carry, so the report cannot define a metric differently from the API.
    seen_metrics = set()
    for meta in _metric_blocks(overview, analyses, headcount):
        if not meta or meta.get("metric_id") in seen_metrics:
            continue
        seen_metrics.add(meta["metric_id"])
        body.append(f'<h4>{esc(meta["label"])}</h4>')
        body.append(f'<p>{esc(meta["definition"])}</p>')
        bits = [f'Counts {esc(meta["numerator"])}']
        if meta.get("denominator"):
            bits.append(f'out of {esc(meta["denominator"])}')
        if (meta.get("window") or {}).get("days"):
            bits.append(f'over the last {meta["window"]["days"]} days')
        # The reader-facing note, and only one of the two: the label and the
        # detail said the same thing twice ("some vendors checked — 82 of 83
        # vendors collected").
        note = meta.get("state_detail_public") or meta.get("state_detail")
        body.append(f'<p class="mm-src">{", ".join(bits)}. '
                    + esc(note or meta["data_state_label"])
                    + ".</p>")
        if meta.get("limitations"):
            body.append("<ul>" + "".join(
                f"<li>{esc(l)}</li>" for l in meta["limitations"]) + "</ul>")

    body.append("<h3>Post classification</h3>")
    body.append(
        "<p>Vendor posts are sorted into four kinds. "
        "<strong>Announcement or factual update</strong> is a substantive "
        "company event or a verifiable update. <strong>Commentary or "
        "opinion</strong> is interpretation or educational material. "
        "<strong>Promotion</strong> is marketing with no new event in it. "
        "<strong>Unreviewed</strong> means nothing has classified it yet, and "
        "is not a judgement about the post.</p>")
    body.append("</section>")

    # What this view covers, said on the page rather than left to be inferred
    # from a short table.
    if allowed_brand_ids is not None:
        from sqlalchemy import text as _sql

        total = conn.execute(_sql("""
            SELECT COUNT(*) FROM bw_market_brands
             WHERE market_id = :m AND role <> 'excluded'
        """), {"m": market["id"]}).scalar() or 0
        body.append(
            '<p class="mm-src">This is a shared view. It covers the '
            f'{len(allowed_brand_ids)} most active of the {total} vendors we '
            'watch, and leaves the rest out. Figures that cover the whole '
            'market say so.</p>')

    rendered = html_document(f'{market["name"]} — Market Monitor',
                             "".join(body))

    # Fail closed. Serving a page that names a vendor the viewer is not
    # entitled to see cannot be undone, and a refusal can.
    ent.assert_no_withheld(rendered, withheld,
                           context=f'market {market["id"]} report')

    return rendered.encode("utf-8")


def _metric_blocks(overview: Dict[str, Any], analyses: Dict[str, Any],
                   headcount: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every metric block carried by the payloads this report already renders.

    Collected by walking what is there rather than naming each one, so a metric
    added to an aggregate shows up in the methodology appendix without anyone
    having to remember to list it here.
    """
    out: List[Dict[str, Any]] = []
    for payload in [overview, headcount] + list((analyses or {}).values()):
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key == "metric" and isinstance(value, dict):
                out.append(value)
            elif key.endswith("_metric") and isinstance(value, dict):
                out.append(value)
    return out
