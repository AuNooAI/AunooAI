"""The Market Monitor vendor page as one self-contained HTML file.

This is the HTML download on the vendor page. It renders the same panels in
the same order as ``MarketVendorPage.tsx`` and its child components, with the
same labels and hints, so the file reads as a saved copy of the screen. It
needs no JavaScript. The controls (Fetch now, Add PitchBook URL, the Market
Horizon weights) are left out, because a file cannot act on them.

Colours are the Tailwind slate and gray values the app uses. The page
follows the reader's light or dark setting the way the app does.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Any, Dict, Iterable, List, Optional

from app.compliance.ai_disclosure import disclosure_footer_html as _ai_footer
from app.compliance.ai_disclosure import html_meta_tags as _ai_meta

CSS = """
:root{--bg:#fdfcfd;--panel:#fff;--border:#e2e8f0;--text:#0f172a;--strong:#1e293b;
--body:#334155;--muted:#64748b;--faint:#94a3b8;--chip:#f8fafc;--chip2:#f1f5f9;
--track:#f1f5f9;--band:rgba(203,213,225,.6);--median:#475569;--avg:#94a3b8;
--good:#047857;--good-bg:#ecfdf5;--good-bd:#a7f3d0;--warn:#d97706;--alert:#dc2626;
--blue:#1d4ed8;--blue-bg:#eff6ff;--blue-bd:#bfdbfe;--grid:#e2e8f0}
@media (prefers-color-scheme:dark){:root{--bg:#111827;--panel:#1f2937;--border:#374151;
--text:#f3f4f6;--strong:#f3f4f6;--body:#d1d5db;--muted:#9ca3af;--faint:#6b7280;
--chip:#374151;--chip2:#374151;--track:#374151;--band:rgba(75,85,99,.6);--median:#d1d5db;
--avg:#6b7280;--good:#34d399;--good-bg:rgba(6,78,59,.2);--good-bd:#065f46;--warn:#fbbf24;
--alert:#f87171;--blue:#60a5fa;--blue-bg:rgba(30,58,138,.2);--blue-bd:#1e40af;--grid:#374151}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--body);
font:14px/1.45 Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
a{color:var(--strong);text-decoration:none}a:hover{text-decoration:underline}
.page{max-width:1200px;margin:0 auto;padding:16px;display:grid;gap:16px}
.head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-start;gap:12px}
h1{font-size:20px;font-weight:600;color:var(--text);margin:0;display:flex;align-items:center;gap:8px}
.sw{width:10px;height:10px;border-radius:2px;display:inline-block;flex:none}
.sub{font-size:14px;color:var(--muted);margin:2px 0 0}
.stamp{font-size:12px;color:var(--faint);margin:4px 0 0}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;padding:4px 8px;border-radius:4px;border:1px solid var(--border);
background:var(--chip);color:var(--muted)}
.chip.good{background:var(--good-bg);color:var(--good);border-color:var(--good-bd)}
.chip.blue{background:var(--blue-bg);color:var(--blue);border-color:var(--blue-bd)}
.tag{font-size:12px;padding:2px 6px;border-radius:4px;border:1px solid var(--border);
background:var(--chip2);display:inline-block}
.tag.light{background:var(--panel);color:var(--muted)}
.tag.good{background:var(--good-bg);color:var(--good);border-color:var(--good-bd)}
.tags{display:flex;flex-wrap:wrap;gap:4px}
.task{font-size:14px;border:1px solid;border-radius:8px;padding:12px}
.task.high{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
.task.medium{background:#fffbeb;color:#b45309;border-color:#fde68a}
.task.low{background:var(--chip);color:var(--muted);border-color:var(--border)}
.panel{border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--panel);min-width:0}
.pt{font-size:14px;font-weight:500;color:var(--strong)}
.ph{font-size:12px;color:var(--muted);margin:2px 0 0}
.pb{margin-top:12px}
.two{display:grid;gap:16px}
@media (min-width:1024px){.two{grid-template-columns:1fr 1fr}}
.xs{font-size:12px}.muted{color:var(--muted)}.faint{color:var(--faint)}
.strong{color:var(--strong)}.empty{color:var(--muted)}
.big{font-size:20px;font-weight:600;color:var(--strong)}
.huge{font-size:30px;font-weight:600;color:var(--strong)}
dl{margin:0}dl div{display:flex;justify-content:space-between;gap:16px;margin:6px 0}
dt{color:var(--muted)}dd{margin:0;color:var(--strong);text-align:right}
.lbl{font-size:12px;color:var(--muted);margin:12px 0 4px}
.row{border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:8px}
.row:last-child{border-bottom:0;padding-bottom:0;margin-bottom:0}
.line{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
ol.plain,ul.plain{list-style:none;margin:0;padding:0}
ol.plain li,ul.plain li{margin:0 0 8px}
table.prof{width:100%;border-collapse:collapse;font-size:14px}
table.prof td{padding:8px 12px 8px 0;border-top:1px solid var(--border);vertical-align:top}
table.prof tr:first-child td{border-top:0}
table.prof td.k{color:var(--muted);width:160px}table.prof td.v{font-weight:500;color:var(--strong)}
.neutral{color:var(--muted)}.warn{color:var(--warn)}.alert{color:var(--alert)}.good{color:var(--good)}
.ident{display:flex;align-items:center;gap:8px;font-size:14px;margin:6px 0}
.ident .k{color:var(--muted);width:144px;flex:none}
.ident a,.ident span.trunc{flex:1}.ok{color:var(--good);font-size:12px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
@media (min-width:640px){.stats{grid-template-columns:repeat(4,1fr)}}
.bm{border-top:1px solid var(--border);padding:12px 0}.bm:first-child{border-top:0}
.plot{position:relative;height:28px;border-radius:4px;background:var(--track);margin-top:8px}
.plot .band{position:absolute;top:0;bottom:0;background:var(--band)}
.plot .med{position:absolute;top:0;bottom:0;width:1px;background:var(--median)}
.plot .avg{position:absolute;top:4px;bottom:4px;width:1px;background:var(--avg)}
.plot .me{position:absolute;top:-2px;bottom:-2px;width:6px;border-radius:4px}
.cmp{display:grid;gap:4px 16px;font-size:12px;color:var(--muted);margin-top:8px}
@media (min-width:640px){.cmp{grid-template-columns:repeat(2,1fr)}}
@media (min-width:1024px){.cmp{grid-template-columns:repeat(4,1fr)}}
.cmp strong{color:var(--strong)}
details summary{font-size:12px;color:var(--blue);cursor:pointer}
details ol{font-size:12px;color:var(--muted);margin:4px 0 0 16px}
.add{color:var(--good)}.del{color:var(--alert)}
svg text{fill:var(--muted);font-size:11px}
.ai-disclosure,footer{font-size:12px;color:var(--faint)}
"""


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _day(v: Any) -> str:
    """'14 Aug 2026', the way the app's formatDay prints a date."""
    if not v:
        return ""
    if isinstance(v, (datetime, date)):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return str(v)[:10]
    return f"{d.day} {d.strftime('%b %Y')}"


def _iso10(v: Any) -> str:
    return str(v)[:10] if v else ""


def _n(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return _e(v)
    return f"{int(x):,}" if x == int(x) else f"{x:,}"


def _panel(title: str, body: str, hint: str = "") -> str:
    return ('<div class="panel">'
            f'<div class="pt">{_e(title)}</div>'
            + (f'<p class="ph">{_e(hint)}</p>' if hint else "")
            + f'<div class="pb">{body}</div></div>')


def _link(href: Any, label: Any, cls: str = "") -> str:
    href = str(href or "")
    label_html = _e(label)
    if not href.startswith(("http://", "https://")):
        return f'<span class="{cls}">{label_html}</span>'
    return (f'<a class="{cls}" href="{_e(href)}" target="_blank" '
            f'rel="noreferrer">{label_html}</a>')


# --- header ---------------------------------------------------------------

def _header(market: Dict[str, Any], v: Dict[str, Any], stamp: str) -> str:
    base = v.get("baseline") or {}
    tax = base.get("taxonomy") or {}
    sub = " · ".join(str(x) for x in (
        tax.get("sub_category"), base.get("hq_country"),
        f"founded {base['founded_year']}" if base.get("founded_year") else None) if x)
    chips = [f'<span class="chip">{_e(v.get("role"))}</span>']
    chips.append('<span class="chip good">watched</span>' if v.get("collection_enabled")
                 else '<span class="chip">not watched</span>')
    if v.get("is_public"):
        chips.append('<span class="chip blue">published</span>')
    color = v.get("color") or "#d6409f"
    return ('<div class="head"><div>'
            f'<h1><span class="sw" style="background:{_e(color)}"></span>{_e(v.get("display_name"))}</h1>'
            + (f'<p class="sub">{_e(sub)}</p>' if sub else "")
            + f'<p class="stamp">{_e(market.get("name"))} · saved {_e(stamp)} from Market Monitor</p>'
            + f'</div><div class="chips">{"".join(chips)}</div></div>')


def _review_tasks(v: Dict[str, Any]) -> str:
    tasks = v.get("review_tasks") or []
    if not tasks:
        return ""
    return '<div style="display:grid;gap:8px">' + "".join(
        f'<div class="task {_e(t.get("severity") if t.get("severity") in ("high", "medium") else "low")}">'
        f'&#9888; {_e(t.get("message"))}</div>' for t in tasks) + "</div>"


# --- current profile, events, coverage (MarketVendorProvenance) ---------

_FIELD_ORDER = ["employee_count", "funding_total_musd", "funding_status", "last_funding_type",
                "hq_country", "founded_year", "operating_status", "industry", "followers_linkedin"]
_FIELD_LABELS = {
    "employee_count": "Headcount", "funding_total_musd": "Total funding",
    "funding_status": "Funding status", "last_funding_type": "Latest round",
    "hq_country": "Headquarters", "founded_year": "Founded",
    "operating_status": "Operating status", "industry": "Industry",
    "followers_linkedin": "LinkedIn followers",
}
_SOURCE_LABELS = {
    "workbook": "imported workbook", "manual": "entered by an operator",
    "linkedin_company_profile": "LinkedIn company profile", "linkedin_jobs": "LinkedIn jobs",
    "crunchbase_company": "Crunchbase", "pitchbook_company": "PitchBook",
    "zoominfo_company": "ZoomInfo", "vendor_web": "the vendor's own site",
}


# Crunchbase's slugs for "the type of the latest round was not disclosed".
# Rendered as a stage name they read as one: "Series Unknown" looked like a
# round called that on Prophet Security, whose latest round is a February 2026
# strategic investment of undisclosed type and size.
_UNDISCLOSED_STAGES = frozenset({
    "series_unknown", "undisclosed", "unknown", "not_stated", "funding_round",
})


def _stage(raw: str) -> str:
    if not raw or raw == "not stated":
        return "not stated"
    if raw.strip().lower().replace(" ", "_") in _UNDISCLOSED_STAGES:
        return "Undisclosed round"
    return " ".join(w.upper() if len(w) == 1 else w[:1].upper() + w[1:]
                    for w in raw.replace("_", " ").split(" "))


def _field_value(f: Dict[str, Any]) -> str:
    num = f.get("value_number")
    if num is not None:
        x = float(num)
        if f.get("field_key") == "founded_year":
            return str(int(x))
        s = f"{int(x):,}" if x == int(x) else str(x)
        return f"${s}m" if f.get("unit") == "musd" else s
    if f.get("value_text") and f.get("field_key") == "last_funding_type":
        return _stage(f["value_text"])
    return f.get("value_text") or "—"


def _baseline_value(base: Dict[str, Any], key: str) -> Any:
    return {
        "employee_count": (base.get("metrics") or {}).get("employee_count"),
        "funding_total_musd": (base.get("funding_baseline") or {}).get("total_musd"),
        "funding_status": (base.get("funding_baseline") or {}).get("status"),
        "hq_country": base.get("hq_country"),
        "founded_year": base.get("founded_year"),
    }.get(key)


def _differs(a: Any, b: Any, tol: float = 0.02) -> bool:
    if a is None or b is None:
        return False
    try:
        x, y = float(a), float(b)
        scale = max(abs(x), abs(y))
        return bool(scale) and abs(x - y) / scale > tol
    except (TypeError, ValueError):
        return str(a).strip().lower() != str(b).strip().lower()


def _status_note(status: str, stale_after: Any) -> tuple:
    if status == "conflict":
        return "alert", "sources disagree"
    if status == "stale":
        return "warn", (f"not re-read since {_day(stale_after)}" if stale_after
                        else "overdue for a re-read")
    if status == "manual_override":
        return "neutral", "set by an operator"
    return "neutral", "current"


def _profile_panel(profile: Optional[Dict[str, Any]], base: Dict[str, Any]) -> str:
    by = {f["field_key"]: f for f in (profile or {}).get("fields") or []}
    ordered = [k for k in _FIELD_ORDER if k in by]
    missing = [k for k in _FIELD_ORDER if k not in by]
    if not ordered:
        body = '<p class="empty">No resolved fields yet for this vendor.</p>'
    else:
        rows = []
        for k in ordered:
            f = by[k]
            src = _SOURCE_LABELS.get(f.get("source") or "", (f.get("source") or "").replace("_", " "))
            when = _day(f.get("observed_at"))
            note = f"{src}, {when}" if when else src
            if f.get("status") and f["status"] != "current":
                tone, text_ = _status_note(f["status"], f.get("stale_after"))
                note_html = f'{_e(note)}<span class="{tone}" style="margin-left:8px">{_e(text_)}</span>'
            else:
                note_html = _e(note)
            prev = _baseline_value(base, k)
            cur = f.get("value_number") if f.get("value_number") is not None else f.get("value_text")
            if _differs(prev, cur):
                # History, not a dispute: a newer reading from a better source
                # has moved on from the imported figure, which is the system
                # working. Amber made 65 of 116 vendors look contested.
                note_html += f'<span class="muted" style="margin-left:8px">{_e(prev)} at import</span>'
            rows.append(f'<tr><td class="k">{_e(_FIELD_LABELS[k])}</td>'
                        f'<td class="v">{_e(_field_value(f))}</td>'
                        f'<td class="xs muted">{note_html}</td></tr>')
        body = f'<table class="prof"><tbody>{"".join(rows)}</tbody></table>'
    if missing:
        body += ('<p class="xs muted" style="margin-top:12px">No source has answered: '
                 + _e(", ".join(_FIELD_LABELS[k] for k in missing))
                 + ". That is a gap in what we have collected, not a statement about the company.</p>")
    return _panel("Current profile", body, "What we currently believe, and which reading says so.")


def _corroboration(c: str, sources: int) -> tuple:
    return {
        "primary_document": ("good", "from a primary document"),
        "corroborated": ("good", f"{sources} independent sources"),
        "single_source": ("neutral", "one independent source"),
        "vendor_claim": ("neutral", "announced by the vendor, no independent source"),
    }.get(c, ("warn", "no source recorded"))


def _event_date(occurred: Any, precision: str) -> str:
    if not occurred or precision == "unknown":
        return "date not stated by the source"
    if precision == "month":
        d = _day(occurred)
        return d.split(" ", 1)[1] if " " in d else d
    return _day(occurred)


def _events_panel(events: List[Dict[str, Any]]) -> str:
    if not events:
        body = '<p class="empty">No events extracted yet.</p>'
    else:
        good = sum(1 for e in events
                   if _corroboration(e.get("corroboration"), e.get("sources") or 0)[0] == "good")
        items = []
        for e in events[:12]:
            tone, note = _corroboration(e.get("corroboration"), e.get("sources") or 0)
            mark = {"good": '<span class="good">&#10003;</span>',
                    "warn": '<span class="warn">&#9888;</span>'}.get(tone, '<span class="faint">&bull;</span>')
            items.append(
                f'<li style="display:flex;gap:8px"><span style="width:16px;flex:none">{mark}</span>'
                f'<div style="min-width:0"><div class="strong trunc">{_e(e.get("title"))}</div>'
                f'<div class="xs muted">{_e((e.get("event_type") or "").replace("_", " "))} · '
                f'<span class="{tone}">{_e(note)}</span> · '
                f'{_e(_event_date(e.get("occurred_at"), e.get("date_precision") or ""))}</div></div></li>')
        body = (f'<p class="xs muted" style="margin:0 0 8px">{good} of {len(events)} '
                'confirmed by someone other than the vendor.</p>'
                f'<ul class="plain">{"".join(items)}</ul>')
    return _panel("Events", body,
                  "What happened, and how much of it anyone other than the vendor has confirmed.")


def _mentions_panel(summary: List[Dict[str, Any]]) -> str:
    owned_ch = ("owned_web", "owned_social")
    owned = sum(r.get("total") or 0 for r in summary if r.get("channel") in owned_ch)
    ext = [r for r in summary if r.get("channel") not in owned_ch]
    external = sum(r.get("total") or 0 for r in ext)
    unevaluated = sum(r.get("unevaluated") or 0 for r in ext)
    pos = sum(r.get("positive") or 0 for r in ext)
    neg = sum(r.get("negative") or 0 for r in ext)
    evaluated = external - unevaluated
    net = (pos - neg) / evaluated if evaluated > 0 else None

    def stat(label: str, value: str) -> str:
        return f'<div><div class="big">{_e(value)}</div><div class="xs muted">{_e(label)}</div></div>'

    body = ('<div class="stats">' + stat("Own posts", f"{owned:,}")
            + stat("External mentions", f"{external:,}") + stat("Evaluated", f"{evaluated:,}")
            + stat("Net sentiment", "—" if net is None else f"{round(net * 100)}%") + "</div>")
    if net is None:
        note = ("No external mentions have been collected. That is a gap in coverage, "
                "not evidence that nobody discussed this company." if external == 0 else
                f"None of the {external} external mentions have been evaluated yet, "
                "so there is no sentiment figure to show.")
    else:
        note = f"Out of {evaluated} evaluated mentions."
        if unevaluated:
            note += f" {unevaluated} more are found but not yet judged, and are excluded."
    body += f'<p class="xs muted" style="margin-top:12px">{_e(note)}</p>'
    return _panel("Coverage", body,
                  "All time, not the period selected on the market page. The vendor's own posts "
                  "and its own website are counted apart from what other people said.")


# --- benchmark (MarketVendorBenchmark) ------------------------------------

def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    x = float(value)
    if unit == "percent":
        return f"{'+' if x > 0 else ''}{_num(x)}%"
    if unit == "musd":
        return f"${x / 1000:.2f}B" if x >= 1000 else f"${round(x)}M"
    return _num(x)


def _num(x: float) -> str:
    return str(int(x)) if x == int(x) else str(round(x * 10) / 10)


def _ahead_of(unit: str) -> str:
    return {"people": "larger than", "musd": "better funded than", "index": "busier than",
            "percent": "grew faster than"}.get(unit, "ahead of")


def _plot(b: Dict[str, Any], color: str) -> str:
    pts = [p for p in (b.get("vendor_value"), b.get("market_median"), b.get("market_average"),
                       b.get("top_median"), b.get("top_q3")) if p is not None]
    if not pts:
        return ""
    lo, hi = min(0.0, *pts), max(pts)
    span = (hi - lo) or 1

    def at(n: float) -> float:
        return (n - lo) / span * 100

    out = ['<div class="plot">']
    if b.get("top_q1") is not None and b.get("top_q3") is not None:
        out.append(f'<div class="band" style="left:{at(b["top_q1"]):.2f}%;'
                   f'right:{100 - at(b["top_q3"]):.2f}%"></div>')
    if b.get("market_median") is not None:
        out.append(f'<div class="med" style="left:{at(b["market_median"]):.2f}%"></div>')
    if b.get("market_average") is not None:
        out.append(f'<div class="avg" style="left:{at(b["market_average"]):.2f}%"></div>')
    if b.get("vendor_value") is not None:
        out.append(f'<div class="me" style="left:{at(b["vendor_value"]):.2f}%;background:{_e(color)}"></div>')
    return "".join(out) + "</div>"


def _clock(b: Dict[str, Any], days: int) -> str:
    m = b.get("metric") or {}
    if m.get("window") == "period":
        return f"Over the last {days} days"
    s = f"As of {_day(b.get('as_of')) or 'the latest run'}"
    return s + (f" — {m['as_of_note']}" if m.get("as_of_note") else "")


def _bench_row(b: Dict[str, Any], days: int, color: str) -> str:
    m = b.get("metric") or {}
    unit = m.get("unit") or ""
    top = b.get("top_label") or "Top vendors"
    head = (f'<div class="line" style="flex-wrap:wrap"><div><div class="pt">{_e(m.get("label"))}</div>'
            f'<div class="xs muted">{_e(_clock(b, days))}</div></div>')
    if (not b.get("suppressed") and b.get("vendor_value") == 0
            and (b.get("market_median") or 0) == 0 and (b.get("top_median") or 0) == 0):
        return (f'<div class="bm">{head}<div class="big">0</div></div>'
                f'<p class="xs muted" style="margin:4px 0 0">None for this vendor, and none at the market '
                f'median or the {_e(top.lower())} median either — {b.get("measured_count")} of '
                f'{b.get("eligible_count")} vendors measured, most of them at zero. '
                'There is nothing to rank here yet.</p></div>')
    right = f'<div style="text-align:right"><div class="big">{_e(_fmt(b.get("vendor_value"), unit))}</div>'
    if b.get("vendor_percentile") is not None:
        right += (f'<div class="xs muted">{_ahead_of(unit)} {b["vendor_percentile"]}% of the '
                  f'{b.get("measured_count")} vendors measured</div>')
    out = [f'<div class="bm">{head}{right}</div></div>']
    notes = b.get("notes") or []
    if b.get("suppressed"):
        if notes:
            out.append(f'<p class="xs muted" style="margin:8px 0 0">{_e(notes[0])}</p>')
    else:
        out.append(_plot(b, color))
        out.append('<div class="cmp">'
                   f'<span>Market median <strong>{_e(_fmt(b.get("market_median"), unit))}</strong></span>'
                   f'<span>Market average <strong>{_e(_fmt(b.get("market_average"), unit))}</strong></span>'
                   f'<span>{_e(top)} median <strong>{_e(_fmt(b.get("top_median"), unit))}</strong></span>'
                   f'<span>{_e(top)} average <strong>{_e(_fmt(b.get("top_average"), unit))}</strong></span>'
                   '</div>')
        if b.get("vendor_value") is not None:
            def pct(p: Any) -> str:
                return f" ({'+' if p > 0 else ''}{p}%)" if p is not None else ""
            out.append(f'<p class="xs muted" style="margin:6px 0 0">'
                       f'{_e(_fmt(b.get("delta_from_market_median"), unit))} against the market median'
                       f'{pct(b.get("percentage_delta_from_market_median"))}. '
                       f'{_e(_fmt(b.get("delta_from_top_median"), unit))} against the {_e(top.lower())} median'
                       f'{pct(b.get("percentage_delta_from_top_median"))}.</p>')
        tail = f'{b.get("measured_count")} of {b.get("eligible_count")} vendors measured'
        label = (b.get("collection") or {}).get("label")
        if label:
            tail += f" · {label}"
        if b.get("as_of"):
            tail += f" · as of {_day(b['as_of'])}"
        out.append(f'<p class="xs faint" style="margin:4px 0 0">{_e(tail)}</p>')
    for n in (notes[1:] if b.get("suppressed") else notes):
        out.append(f'<p class="xs warn" style="margin:4px 0 0">&#9888; {_e(n)}</p>')
    cohort = b.get("cohort") or []
    if cohort:
        out.append(f'<details style="margin-top:6px"><summary>{_e(top)}</summary><ol>'
                   + "".join(f'<li>{_e(c.get("vendor"))} — {_e(_fmt(c.get("value"), unit))}</li>'
                             for c in cohort) + "</ol></details>")
    return "".join(out) + "</div>"


def _bench_panel(bench: Optional[Dict[str, Any]], color: str) -> str:
    hint = ("This vendor against every other vendor in the market that has a valid value for the "
            "same metric, and against the leading measured vendors on it. The vendor is excluded "
            "from both comparators, so \"above the market median\" is not partly a statement about "
            "itself. Median leads because headcount, funding and attention are all skewed — one "
            "large vendor moves an average and leaves a median alone.")
    if not bench:
        return _panel("Benchmark", '<p class="empty">The benchmark could not be computed.</p>', hint)
    days = bench.get("period_days") or 30
    rows = "".join(_bench_row(b, days, color) for b in bench.get("metrics") or [])
    note = f'<p class="xs faint" style="margin-top:12px">{_e(bench.get("note"))}</p>' if bench.get("note") else ""
    return _panel("Benchmark", f'<div style="margin-top:-4px">{rows}</div>{note}', hint)


# --- headcount and funding ------------------------------------------------

def _headcount_chart(series: List[tuple], baseline: Optional[float], color: str) -> str:
    w, h, l, r, t, b = 560, 220, 44, 70, 10, 26
    ys = [s for _, s in series] + ([baseline] if baseline is not None else [])
    lo, hi = min(ys), max(ys)
    pad = max((hi - lo) * 0.1, 1)
    lo, hi = lo - pad, hi + pad
    n = len(series)

    def x(i: int) -> float:
        return l + (w - l - r) * (i / (n - 1) if n > 1 else 0.5)

    def y(v: float) -> float:
        return t + (h - t - b) * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Headcount over time">']
    for k in range(5):
        val = lo + (hi - lo) * k / 4
        yy = y(val)
        parts.append(f'<line x1="{l}" x2="{w - r}" y1="{yy:.1f}" y2="{yy:.1f}" '
                     'stroke="var(--grid)" stroke-dasharray="3 3"/>'
                     f'<text x="{l - 6}" y="{yy + 4:.1f}" text-anchor="end">{round(val)}</text>')
    step = max(1, n // 6)
    for i in range(0, n, step):
        parts.append(f'<text x="{x(i):.1f}" y="{h - 6}" text-anchor="middle">{_e(series[i][0])}</text>')
    if baseline is not None:
        yb = y(baseline)
        parts.append(f'<line x1="{l}" x2="{w - r}" y1="{yb:.1f}" y2="{yb:.1f}" stroke="var(--faint)" '
                     f'stroke-dasharray="4 4"/><text x="{w - r + 4}" y="{yb + 4:.1f}">registry: '
                     f'{_e(_num(float(baseline)))}</text>')
    pts = " ".join(f"{x(i):.1f},{y(s):.1f}" for i, (_, s) in enumerate(series))
    parts.append(f'<polyline fill="none" stroke="{_e(color)}" stroke-width="2" points="{pts}"/>')
    for i, (d, s) in enumerate(series):
        parts.append(f'<circle cx="{x(i):.1f}" cy="{y(s):.1f}" r="3" fill="var(--panel)" '
                     f'stroke="{_e(color)}" stroke-width="2"><title>{_e(d)}: {s}</title></circle>')
    return "".join(parts) + "</svg>"


def _headcount_panel(v: Dict[str, Any], color: str) -> str:
    base = v.get("baseline") or {}
    baseline = (base.get("metrics") or {}).get("employee_count")
    series = []
    for p in v.get("profile_series") or []:
        if p.get("employee_count") is not None:
            try:
                series.append((_iso10(p.get("observed_at")), int(float(p["employee_count"]))))
            except (TypeError, ValueError):
                pass
    if not series:
        body = '<p class="empty" style="text-align:center;padding:24px 0">No LinkedIn reading yet.</p>'
    elif len(series) == 1:
        d, s = series[0]
        body = (f'<div style="display:flex;align-items:baseline;gap:12px"><span class="huge">{s}</span>'
                f'<span class="muted">on {_e(d)}</span></div>')
        if baseline is not None:
            line = f"Baseline {_num(float(baseline))}"
            if float(baseline) != s:
                delta = s - float(baseline)
                line += f" · delta {'+' if delta > 0 else ''}{_num(delta)}"
            body += f'<p class="muted" style="margin:8px 0 0">{_e(line)}</p>'
        body += '<p class="xs muted" style="margin:8px 0 0">1 reading. Collected weekly.</p>'
    else:
        body = _headcount_chart(series, float(baseline) if baseline is not None else None, color)
    series_raw = v.get("profile_series") or []
    if series_raw and series_raw[-1].get("followers") is not None:
        body += f'<p class="xs muted" style="margin:8px 0 0">Followers: {_n(series_raw[-1]["followers"])}</p>'
    return _panel("Headcount", body, "LinkedIn employee count. Dashed line is the imported baseline.")


def _funding_panel(v: Dict[str, Any]) -> str:
    fund = (v.get("baseline") or {}).get("funding_baseline") or {}
    cb = v.get("funding") or {}

    def row(k: str, val: str) -> str:
        return f"<div><dt>{_e(k)}</dt><dd>{_e(val)}</dd></div>"

    status = fund.get("status") or "—"
    if fund.get("total_musd") is not None:
        status += f" · ${fund['total_musd']}M"
    rows = [row("Registry status", status),
            row("Rounds", str(cb.get("num_funding_rounds") if cb.get("num_funding_rounds") is not None else "—")),
            row("Last round", (cb.get("last_funding_type") or "—").replace("_", " ")),
            row("Status", " · ".join(str(x) for x in (cb.get("operating_status"), cb.get("ipo_status")) if x) or "—")]
    if cb.get("growth_score") is not None or cb.get("cb_rank") is not None:
        bits = []
        if cb.get("growth_score") is not None:
            bits.append(f"growth {cb['growth_score']}")
        if cb.get("heat_score") is not None:
            bits.append(f"heat {cb['heat_score']}")
        if cb.get("cb_rank") is not None:
            bits.append(f"rank {_n(cb['cb_rank'])}")
        rows.append(row("Crunchbase", " · ".join(bits)))
    if isinstance(cb.get("founders"), list) and cb["founders"]:
        rows.append(row("Founders", ", ".join(map(str, cb["founders"]))))
    acq = cb.get("acquired_by")
    if acq:
        rows.append(row("Acquired by", acq if isinstance(acq, str) else (acq or {}).get("acquirer", "")))
    body = f"<dl>{''.join(rows)}</dl>"
    if cb.get("lead_investors"):
        body += ('<div class="lbl">Lead investors</div><div class="tags">'
                 + "".join(f'<span class="tag">{_e(i)}</span>' for i in cb["lead_investors"]) + "</div>")
    if cb.get("investors"):
        body += (f'<div class="lbl">All investors ({len(cb["investors"])})</div><div class="tags">'
                 + "".join(f'<span class="tag light">{_e(i)}</span>' for i in cb["investors"]) + "</div>")
    news = cb.get("recent_news") if isinstance(cb.get("recent_news"), list) else []
    if news:
        items = []
        for n in news[:6]:
            meta = "".join(f" · {x}" for x in (n.get("publisher"), _iso10(n.get("date"))) if x)
            items.append(f'<div class="xs"><span class="strong">{_e(n.get("title"))}</span>'
                         f'<span class="faint">{_e(meta)}</span></div>')
        body += '<div class="lbl">Recent news, per Crunchbase</div>' + "".join(items)
    return _panel("Funding", body, "Source: Crunchbase. Round amounts not available from this dataset.")


# --- identifiers, announcements, pages, jobs, posts, coverage -------------

def _identifiers_panel(v: Dict[str, Any]) -> str:
    ids = v.get("identifiers") or []
    live = [i for i in ids if i.get("live")]
    old = [i for i in ids if not i.get("live")]
    rows = []
    for i in live:
        mark = ('<span class="ok">&#10003; verified</span>' if i.get("verified")
                else '<span class="xs faint">unverified</span>')
        rows.append(f'<div class="ident"><span class="k">{_e((i.get("kind") or "").replace("_", " "))}</span>'
                    f'{_link(i.get("display_value"), i.get("display_value"), "trunc")}{mark}</div>')
    body = "".join(rows) or '<p class="empty">None on file.</p>'
    if old:
        body += (f'<details style="margin-top:8px"><summary>Show {len(old)} corrected</summary>'
                 + "".join(f'<div class="xs muted"><s>{_e(i.get("display_value"))}</s> · '
                           f'{_e((i.get("provenance") or {}).get("superseded_reason") or "corrected")}</div>'
                           for i in old) + "</details>")
    return _panel("Identifiers", body, "Used to match this vendor across sources.")


_VERDICT_WORD = {"signal": "announcements", "commentary": "opinion", "noise": "promotion"}


def _announcements_panel(v: Dict[str, Any]) -> str:
    ann = v.get("announcements") or []
    verdicts = v.get("post_verdicts") or {}
    if not ann:
        body = ('<p class="empty">' + ("No posts have been read yet." if not verdicts
                                       else "Nothing this vendor posted stated a fact.") + "</p>")
    else:
        chips = "".join(f'<span class="tag">{_VERDICT_WORD[k]} {verdicts[k]}</span>'
                        for k in ("signal", "commentary", "noise") if verdicts.get(k))
        rows = []
        for a in ann:
            sub = ""
            if a.get("review_kind"):
                sub += f'<span class="tag good">{_e(a["review_kind"])}</span> '
            if a.get("review_reason"):
                sub += f'<span class="xs muted">{_e(a["review_reason"])}</span>'
            rows.append(f'<div class="row"><div class="line">{_link(a.get("url") or a.get("uri"), a.get("title"))}'
                        f'<span class="xs faint num">{_e(_iso10(a.get("publication_date")) or "—")}</span></div>'
                        + (f'<div style="margin-top:2px">{sub}</div>' if sub else "") + "</div>")
        body = f'<div class="tags" style="margin-bottom:8px">{chips}</div>{"".join(rows)}'
    return _panel("Announcements", body,
                  "Posts naming something that happened — a launch, a raise, a customer, a hire. "
                  "Everything else this vendor posted is below.")


def _pages_panel(v: Dict[str, Any]) -> str:
    pages = v.get("pages") or []
    if not pages:
        body = '<p class="empty">No monitored pages.</p>'
    else:
        rows = []
        for p in pages:
            diff = p.get("diff") or {}
            d = ""
            if diff.get("material"):
                added, removed = diff.get("added") or [], diff.get("removed") or []
                d = (f'<div class="xs" style="margin-top:4px"><div class="muted">'
                     f'{diff.get("added_count", len(added))} lines added, '
                     f'{diff.get("removed_count", len(removed))} removed</div>'
                     + "".join(f'<div class="add trunc">+ {_e(x)}</div>' for x in added[:3])
                     + "".join(f'<div class="del trunc">− {_e(x)}</div>' for x in removed[:2]) + "</div>")
            rows.append(f'<div class="row"><div class="line">'
                        f'{_link(p.get("url"), (p.get("title") or p.get("kind") or "page"), "trunc")}'
                        f'<span class="xs muted num">{_e(_iso10(p.get("observed_at")))}</span></div>{d}</div>')
        body = "".join(rows)
    return _panel("Site changes", body, "Monitored pages and their most recent diff.")


def _jobs_panel(v: Dict[str, Any]) -> str:
    jobs = v.get("jobs") or []
    hint = "Open roles from LinkedIn. Collected twice weekly."
    if len(jobs) > 10:
        hint += f" Showing 10 of {len(jobs)}."
    if not jobs:
        body = '<p class="empty">No postings collected.</p>'
    else:
        body = "".join(
            f'<div class="line" style="margin:6px 0"><span class="strong trunc">{_e(j.get("title"))}</span>'
            f'<span class="xs muted" style="flex:none">'
            f'{_e(" · ".join(str(x) for x in (j.get("seniority"), j.get("location")) if x))}</span></div>'
            for j in jobs[:10])
    return _panel("Job postings", body, hint)


def _posts_panel(v: Dict[str, Any]) -> str:
    posts = v.get("posts") or []
    if not posts:
        body = '<p class="empty">No posts collected.</p>'
    else:
        body = '<ol class="plain">' + "".join(
            f'<li>{_link(p.get("url") or p.get("uri"), p.get("title"))}'
            f'<div class="xs muted">{_e(_iso10(p.get("publication_date")))}</div></li>'
            for p in posts) + "</ol>"
    return _panel("LinkedIn posts", body, "Most recent 10.")


def _coverage_panel(v: Dict[str, Any]) -> str:
    cats = v.get("coverage_by_category") or []
    recent = v.get("recent_coverage") or []
    if not cats:
        body = '<p class="empty">No articles attributed.</p>'
    else:
        body = '<div class="tags">' + "".join(
            f'<span class="tag">{_e(c.get("category"))} · {_e(c.get("n"))}</span>' for c in cats) + "</div>"
    if recent:
        body += '<ol class="plain" style="margin-top:12px">' + "".join(
            f'<li>{_link(a.get("url") or a.get("uri"), a.get("title"))}'
            f'<div class="xs muted">{_e(a.get("news_source"))} · {_e(_iso10(a.get("publication_date")))}</div></li>'
            for a in recent[:5]) + "</ol>"
    return _panel("Coverage", body, "Third-party articles attributed to this vendor.")


def _two(*panels: str) -> str:
    return f'<div class="two">{"".join(panels)}</div>'


def render(market: Dict[str, Any], v: Dict[str, Any], *,
           bench: Optional[Dict[str, Any]] = None,
           profile: Optional[Dict[str, Any]] = None,
           events: Optional[Iterable[Dict[str, Any]]] = None,
           mention_summary: Optional[List[Dict[str, Any]]] = None,
           stamp: str = "") -> str:
    """The vendor page as a standalone HTML document.

    ``profile``, ``events`` and ``mention_summary`` are the entity-layer reads
    behind the Current profile, Events and Coverage panels. Pass ``None`` for
    all three when that layer is switched off, and the panels are left out,
    as they are on screen.
    """
    color = v.get("color") or "#d6409f"
    parts = [_header(market, v, stamp), _review_tasks(v)]
    if profile is not None:
        parts += [_profile_panel(profile, v.get("baseline") or {}),
                  _events_panel(list(events or [])),
                  _mentions_panel(mention_summary or [])]
    parts += [_bench_panel(bench, color),
              _two(_headcount_panel(v, color), _funding_panel(v)),
              _identifiers_panel(v),
              _announcements_panel(v),
              _two(_pages_panel(v), _jobs_panel(v)),
              _two(_posts_panel(v), _coverage_panel(v))]
    title = f"{v.get('display_name')} — vendor dossier"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + _ai_meta() + f"<title>{_e(title)}</title><style>{CSS}</style></head><body>"
            '<div class="page">' + "".join(p for p in parts if p)
            + _ai_footer() + "</div></body></html>")
