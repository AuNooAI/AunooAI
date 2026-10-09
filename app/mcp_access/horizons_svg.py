"""The Three-Horizons S-curve chart as a self-contained SVG.

Copied from saas (``app/sharing/renderers/horizons_image.py``,
``render_horizons_svg`` and its helpers) so the monolith draws the same chart
saas returns from its ``render_horizons_chart`` tool: three smoothstep curves
(Current declining, Transition cresting, Future rising) with every scenario
plotted as a dot on its band's curve at the midpoint of its years. Keep the
curve constants in sync with the saas file. The PNG path is left out; it needs
Pillow and the SVG is what assistants paste into reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Band colours — mirror HORIZON_COLORS in horizons.py (h1/h2/h3).
_CURRENT = "#d6409f"     # H1 — current developments (pink-9)
_TRANSITION = "#8e4ec6"  # H2 — transition (purple)
_FUTURE = "#0090ff"      # H3 — future (blue-9)
_GRID = "#dbd8e0"        # mauve-6
_AXIS_TEXT = "#65636d"   # mauve-11
_TITLE_TEXT = "#211f26"  # mauve-12
_BG = (253, 252, 253, 255)  # mauve-1

_AXIS_PHASES = ["Now", "Near", "Mid", "Far", "Horizon"]


def _year(value: Any) -> int | None:
    try:
        y = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return y if 1900 < y < 2200 else None


def _timeline_span(scenarios: list[dict]) -> tuple[int, int] | None:
    years: list[int] = []
    for s in scenarios:
        if not isinstance(s, dict):
            continue
        for key in ("timeline_start", "timeline_end"):
            y = _year(s.get(key))
            if y is not None:
                years.append(y)
    if not years:
        return None
    lo, hi = min(years), max(years)
    return (lo, hi if hi > lo else lo + 1)


def render_horizons_svg(payload: dict[str, Any]) -> str:
    """Compact, self-contained SVG of the Three-Horizons chart.

    Same three S-curves as the PNG, with each scenario plotted as a dot on its
    band's curve plus a de-collided text label. Returned as plain SVG markup
    (~6-9 KB, no external CSS/fonts) so an assistant can paste it into an
    artifact reliably — unlike a base64 PNG, which is too long to reproduce
    verbatim without corruption.
    """
    import html as _html

    def ss(x: float) -> float:
        x = max(0.0, min(1.0, x))
        return x * x * (3 - 2 * x)

    f_cur = lambda t: 0.06 + 0.74 * (1 - ss((t - 0.05) / 0.75))
    f_tra = lambda t: (
        (0.42 + 0.20 * ss(t / 0.38)) if t < 0.38
        else (0.62 - 0.48 * ss((t - 0.38) / 0.62))
    )
    f_fut = lambda t: 0.05 + 0.81 * ss((t - 0.28) / 0.78)

    W, H = 1000, 470
    L, RR = 24, 976
    TOP, BOT = 96, 366
    N = 40
    span, hgt = RR - L, BOT - TOP
    X = lambda t: round(L + t * span, 1)
    Y = lambda v: round(BOT - v * hgt, 1)

    bands = {"h1": (f_cur, _CURRENT, "Current"),
             "h2": (f_tra, _TRANSITION, "Transition"),
             "h3": (f_fut, _FUTURE, "Future")}

    scenarios = [s for s in (payload.get("scenarios") or []) if isinstance(s, dict)]
    span_yrs = _timeline_span(scenarios)
    now_year = datetime.now(timezone.utc).year
    lo, hi = span_yrs if span_yrs else (now_year, now_year + 15)

    def area(f) -> str:
        pts = [f"{X(0)},{BOT}"] + [f"{X(i/N)},{Y(f(i/N))}" for i in range(N + 1)] + [f"{X(1)},{BOT}"]
        return " ".join(pts)

    def line(f) -> str:
        return " ".join(f"{X(i/N)},{Y(f(i/N))}" for i in range(N + 1))

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="Inter,system-ui,Arial,sans-serif" width="100%">',
        f'<rect width="{W}" height="{H}" fill="#fdfcfd"/>',
        f'<text x="{L}" y="48" font-size="26" font-weight="700" fill="{_TITLE_TEXT}">Future Horizons</text>',
        f'<text x="{L}" y="72" font-size="15" fill="{_AXIS_TEXT}">'
        f'{_html.escape(str(payload.get("topic_label") or ""))}</text>',
    ]
    for i in range(5):
        x = X(i / 4)
        parts.append(f'<line x1="{x}" y1="{TOP}" x2="{x}" y2="{BOT}" stroke="{_GRID}" stroke-width="1"/>')
    for key in ("h3", "h2", "h1"):
        f, color, _ = bands[key]
        parts.append(f'<polygon points="{area(f)}" fill="{color}" fill-opacity="0.42"/>')
    for key in ("h3", "h2", "h1"):
        f, color, _ = bands[key]
        parts.append(f'<polyline points="{line(f)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    for key in ("h1", "h2", "h3"):
        f, color, label = bands[key]
        parts.append(f'<text x="{X(0)+8}" y="{Y(f(0.0))-6}" font-size="14" font-weight="700" '
                     f'fill="{color}">{label}</text>')
    for i in range(5):
        x = X(i / 4)
        year = int(round(lo + (hi - lo) * i / 4))
        anc = "start" if i == 0 else ("end" if i == 4 else "middle")
        parts.append(f'<text x="{x}" y="{BOT+20}" font-size="13" fill="{_AXIS_TEXT}" '
                     f'text-anchor="{anc}">{year}</text>')
        parts.append(f'<text x="{x}" y="{BOT+38}" font-size="11" fill="{_AXIS_TEXT}" '
                     f'text-anchor="{anc}">{_AXIS_PHASES[i]}</text>')

    # Scenario dots + labels. Each label sits beside its dot — dots in the left
    # ~58% get labels to the RIGHT, the rest to the LEFT, so both gutters are
    # used. Labels are de-collided in 2D (pushed vertically only against labels
    # they actually overlap in x), so a crowd of nearby dots no longer collapses
    # into one tall vertical stack with long leader lines.
    pts = []
    for s in scenarios:
        key = str(s.get("type") or "").lower()
        if key not in bands:
            continue
        f, color, _ = bands[key]
        a, b = _year(s.get("timeline_start")), _year(s.get("timeline_end"))
        mid = ((a or lo) + (b or hi)) / 2
        t = 0.0 if hi == lo else max(0.0, min(1.0, (mid - lo) / (hi - lo)))
        pts.append({"x": X(t), "y": Y(f(t)), "color": color,
                    "title": (str(s.get("title") or "")[:30]).strip()})

    LH, CH = 14.0, 6.4  # line height; approx char width at 11px
    placed: list[tuple[float, float, float, float]] = []  # x0, x1, y0, y1

    def _hit(x0: float, x1: float, y0: float, y1: float) -> bool:
        return any(not (x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1)
                   for bx0, bx1, by0, by1 in placed)

    for p in sorted(pts, key=lambda q: (q["y"], q["x"])):
        w = len(p["title"]) * CH + 6
        right = p["x"] < 0.58 * W
        if right:
            tx0, tx1, anchor, tx, leader_x = p["x"] + 12, p["x"] + 12 + w, "start", p["x"] + 12, p["x"] + 12
        else:
            tx0, tx1, anchor, tx, leader_x = p["x"] - 12 - w, p["x"] - 12, "end", p["x"] - 12, p["x"] - 12
        ly = p["y"]
        for _ in range(80):
            if not _hit(tx0, tx1, ly - 7, ly + 7):
                break
            ly += LH
        ly = max(TOP + 8, min(BOT - 4, round(ly, 1)))
        placed.append((tx0, tx1, ly - 7, ly + 7))
        parts.append(f'<circle cx="{p["x"]}" cy="{p["y"]}" r="3.5" fill="{p["color"]}"/>')
        if abs(ly - p["y"]) > 1.5:
            parts.append(f'<line x1="{p["x"]}" y1="{p["y"]}" x2="{leader_x}" y2="{ly}" '
                         f'stroke="{p["color"]}" stroke-width="0.8" opacity="0.45"/>')
        parts.append(f'<text x="{tx}" y="{round(ly+3,1)}" font-size="11" '
                     f'text-anchor="{anchor}" fill="#211f26">{_html.escape(p["title"])}</text>')
    parts.append("</svg>")
    return "".join(parts)
