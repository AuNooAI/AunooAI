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
"""


def _stat(label: str, value: str, hint: str = "") -> str:
    return (f'<div class="mm-stat"><div class="l">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div>'
            + (f'<div class="h">{esc(hint)}</div>' if hint else "")
            + "</div>")


def _coverage(coverage: Optional[Dict[str, Any]]) -> str:
    """The denominator, rendered so it cannot be skipped past.

    Amber when partial, green when complete. A chart in this report without one
    of these is a chart whose author forgot to say what it rests on.
    """
    if not coverage:
        return ""
    cls = "mm-cover full" if coverage.get("complete") else "mm-cover"
    return f'<div class="{cls}">Based on {esc(coverage.get("label", ""))}.</div>'


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
    """One market, one file, no external requests."""
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

    generated = datetime.now(timezone.utc)
    body: List[str] = [f"<style>{EXTRA_CSS}</style>"]

    body.append('<header class="report-header">')
    body.append(f'<h1>{esc(market["name"])} — Market Monitor</h1>')
    if market.get("question"):
        body.append(f'<p class="lede">{esc(market["question"])}</p>')
    body.append('<p class="mm-src">Generated '
                f'{generated.strftime("%d %B %Y")} · '
                f'covering the last {days} days · every figure is a count of '
                'stored records</p>')
    body.append("</header>")

    # ---- Standing picture
    cov, fund = overview["coverage"], overview["funding"]
    body.append(section_open("Where the market stands"))
    body.append('<div class="mm-stats">')
    body.append(_stat("Vendors watched",
                      f'{cov["watching"]} of {cov["registry"] - cov["excluded"]}',
                      f'{cov["paused"]} paused · {cov["observed"]} read at least once'))
    body.append(_stat("Disclosed funding",
                      "—" if fund["total_musd"] is None
                      else f'${fund["total_musd"]:,.0f}M',
                      f'{fund["disclosed"]} disclosed, {fund["undisclosed"]} did not'))
    corpus = overview.get("corpus") or {}
    body.append(_stat("Articles about the market", str(corpus.get("total", 0)),
                      f'{corpus.get("corpus", 0)} found in coverage collected '
                      'for other subjects'))
    body.append(_stat("Vendors with no signal", str(overview["quiet_vendors"]),
                      "No posts, no job listings, no coverage"))
    body.append("</div></section>")

    # ---- Formation
    formation = analyses.get("formation")
    if formation:
        body.append(section_open("How the category formed"))
        body.append(f'<p>{formation["founded_since_2023"]} of '
                    f'{formation["vendors_in_scope"]} vendors were founded in '
                    '2023 or later.</p>')
        body.append(_coverage(formation.get("coverage")))
        body.append(_bar_chart(formation["founded_by_year"],
                               label_key="year", value_key="vendors"))
        body.append("<h3>Announcements per month</h3>")
        body.append(_coverage(formation.get("announcement_coverage")))
        body.append(_bar_chart(formation["announcements_by_month"],
                               label_key="month", value_key="signal",
                               colour="#30a46c"))
        body.append("</section>")

    # ---- Signal to noise
    sn = analyses.get("signal_noise")
    if sn and sn.get("vendors"):
        totals = sn["totals"]
        body.append(section_open("What the vendors are saying"))
        body.append(f'<p>{totals["signal"]} of '
                    f'{sum(totals.values())} vendor posts state a fact. The '
                    'rest are commentary or conference notices.</p>')
        body.append(_coverage(sn.get("coverage")))
        body.append(_stacked_chart(
            sn["vendors"][:20], label_key="vendor",
            series=[("signal", "#30a46c", "States a fact"),
                    ("commentary", "#8b93a1", "Commentary"),
                    ("noise", "#d4d8de", "No content")]))
        if sn.get("signal_kinds"):
            body.append("<p>" + " ".join(
                f'<span class="mm-kind">{esc(k["kind"])} {k["n"]}</span>'
                for k in sn["signal_kinds"]) + "</p>")
        body.append("</section>")

    # ---- Funding
    funding = analyses.get("funding")
    if funding:
        body.append(section_open("Funding and momentum"))
        body.append(_coverage(funding.get("coverage")))
        body.append(_bar_chart(funding["stages"], label_key="stage",
                               value_key="vendors"))
        if funding.get("momentum"):
            body.append("<h3>Growth against attention</h3>")
            body.append('<p class="mm-src">Both scores are Crunchbase\'s own, '
                        '0 to 100.</p>')
            body.append(_scatter(funding["momentum"], x_key="growth_score",
                                 y_key="heat_score", label_key="vendor",
                                 x_label="growth", y_label="attention"))
        if funding.get("shared_investors"):
            body.append("<h3>Investors backing more than one vendor</h3>")
            body.append('<table class="mm-table"><tbody>' + "".join(
                f'<tr><td>{esc(i["investor"])}</td>'
                f'<td class="mm-src">{esc(", ".join(i["backing"]))}</td></tr>'
                for i in funding["shared_investors"]) + "</tbody></table>")
        body.append("</section>")

    # ---- Hiring
    hiring = analyses.get("hiring")
    if hiring and hiring["openings"]:
        body.append(section_open("What the market is hiring for"))
        body.append(f'<p>{hiring["openings"]} open listings. Engineering-heavy '
                    'hiring says a vendor is still building; sales-heavy says '
                    'it has started selling.</p>')
        body.append(_coverage(hiring.get("coverage")))
        body.append(_bar_chart(hiring["by_function"], label_key="function",
                               value_key="openings"))
        body.append("</section>")

    # ---- What happened
    articles = mcorp.articles(conn, market["id"], limit=40, days=days)
    if articles:
        body.append(section_open(f"Coverage in the last {days} days"))
        rows = []
        for a in articles:
            kind = a.get("review_kind") or a["article_class"]
            rows.append(
                f'<tr><td><a href="{esc(a["uri"])}">{esc(a["title"] or a["uri"])}</a>'
                f'<div class="mm-src">{esc(a.get("news_source") or "")}'
                f' · {esc((a.get("published") or "")[:10])}'
                f' · {esc(kind)}</div></td></tr>')
        body.append('<table class="mm-table"><tbody>'
                    + "".join(rows) + "</tbody></table>")
        body.append("</section>")

    # ---- The registry
    dataset = mp.build_dataset(conn, market["id"])
    body.append(section_open("The registry"))
    body.append('<table class="mm-table"><thead><tr>'
                "<th>Vendor</th><th>Country</th><th>Founded</th>"
                '<th class="mm-num">Staff</th><th class="mm-num">Raised</th>'
                '<th class="mm-num">Posts 30d</th>'
                '<th class="mm-num">Open roles</th></tr></thead><tbody>')
    for row in dataset:
        if row.get("role") == "excluded":
            continue
        raised = row.get("total_funding_musd")
        body.append(
            f'<tr><td>{esc(row["vendor"])}</td>'
            f'<td>{esc(row.get("country") or "—")}</td>'
            f'<td>{esc(str(row.get("founded_year") or "—"))}</td>'
            f'<td class="mm-num">{esc(str(row.get("headcount_linkedin") or row.get("headcount_workbook") or "—"))}</td>'
            f'<td class="mm-num">{("$%sM" % raised) if raised else esc(row.get("funding_status") or "—")}</td>'
            f'<td class="mm-num">{esc(str(row.get("posts_30d") or 0))}</td>'
            f'<td class="mm-num">{esc(str(row.get("open_jobs") or 0))}</td></tr>')
    body.append("</tbody></table></section>")

    body.append(section_open("How this was put together"))
    body.append(
        "<p>Vendors come from an imported registry. Coverage is matched against "
        "the market's own phrases across everything this system has collected, "
        "not only what was collected for this market. Vendor posts are read "
        "once each and classified by whether they state a fact. Company "
        "measurements come from LinkedIn and Crunchbase.</p>"
        "<p>Every number here is a count of stored records. Where a figure "
        "rests on part of the registry rather than all of it, the panel says "
        "so.</p>")
    body.append("</section>")

    return html_document(f'{market["name"]} — Market Monitor',
                         "".join(body)).encode("utf-8")
