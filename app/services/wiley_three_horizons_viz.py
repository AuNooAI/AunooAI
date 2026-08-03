"""Three Horizons curves visual — server-side renderer.

Mirrors the visual the web app's Future Horizons tab renders
(``ui/src/components/FutureHorizons.tsx``):

* H1 / H2 / H3 SVG Bezier curves (paths copied 1:1)
* Same horizontal gradient stops
* Same NOW marker
* Scenario markers plotted ON the curves at the position
  ``calculateHorizonPosition`` computes in the React component (time-derived
  x + intra-type spread + alternating vertical offset for label readability)

Returns a PNG to a writable stream so the bundle PPTX can embed it directly
without round-tripping through a file.
"""
from __future__ import annotations

import re as _re
from io import BytesIO
from typing import Iterable, Optional

import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless — never spawn an X server in the API process
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from matplotlib.colors import to_rgba


# ── SVG paths (copied 1:1 from FutureHorizons.tsx) ────────────────────────
# SVG y-axis runs DOWN; we invert the matplotlib y-axis at render time.
# Smooth-quadratic ``T`` commands are pre-expanded to ``Q`` (control = reflection
# of the previous control about the current point).
H1_CMDS = [
    ("M", 0, 25),
    ("Q", 25, 28, 50, 45),
    ("Q", 75, 62, 100, 75),   # T 100,75
]
H2_CMDS = [
    ("M", 0, 85),
    ("Q", 25, 75, 40, 55),
    ("Q", 55, 35, 70, 40),
    ("Q", 85, 45, 100, 60),
]
H3_CMDS = [
    ("M", 0, 95),
    ("Q", 30, 95, 50, 85),
    ("Q", 70, 75, 85, 55),
    ("Q", 100, 35, 100, 20),  # T 100,20
]

GRADIENTS = {
    "h1": [(0.0, "#3b82f6", 0.7), (0.5, "#ec4899", 0.3), (1.0, "#93c5fd", 0.2)],
    "h2": [(0.0, "#a855f7", 0.3), (0.5, "#ec4899", 0.7), (1.0, "#c084fc", 0.3)],
    "h3": [(0.0, "#22c55e", 0.2), (0.5, "#f472b6", 0.4), (1.0, "#4ade80", 0.7)],
}
STROKES = {"h1": "#2563eb", "h2": "#9333ea", "h3": "#16a34a"}


# ── Bezier helpers — mirror of FutureHorizons.tsx::getYOnCurve ────────────
def _quad(t: float, pts) -> float:
    mt = 1 - t
    return mt * mt * pts[0][1] + 2 * mt * t * pts[1][1] + t * t * pts[2][1]


def y_on_curve(x: float, wave_type: str) -> float:
    """Y for a given x ∈ [0,100] on the H1/H2/H3 curve — matches the React fn."""
    t = x / 100.0
    if wave_type == "h1":
        if t <= 0.5:
            return _quad(t / 0.5, [[0, 25], [25, 28], [50, 45]])
        return _quad((t - 0.5) / 0.5, [[50, 45], [75, 62], [100, 75]])
    if wave_type == "h2":
        if t <= 0.4:
            return _quad(t / 0.4, [[0, 85], [25, 75], [40, 55]])
        if t <= 0.7:
            return _quad((t - 0.4) / 0.3, [[40, 55], [55, 35], [70, 40]])
        return _quad((t - 0.7) / 0.3, [[70, 40], [85, 45], [100, 60]])
    if wave_type == "h3":
        if t <= 0.5:
            return _quad(t / 0.5, [[0, 95], [30, 95], [50, 85]])
        if t <= 0.85:
            return _quad((t - 0.5) / 0.35, [[50, 85], [70, 75], [85, 55]])
        return _quad((t - 0.85) / 0.15, [[85, 55], [92.5, 37.5], [100, 20]])
    return 50.0


# Axis anchored on the render year, not a baked-in 2025 — see the same
# note in ``horizons_html``. Both renderers must agree or the deck chart
# and the HTML chart place the same scenario in different places.
_AXIS_SPAN_YEARS = 15


def _axis_base_year() -> int:
    from datetime import date as _date
    return _date.today().year


def _parse_timeframe(tf: Optional[str]) -> tuple[int, int]:
    years = _re.findall(r"\d{4}", tf or "")
    if len(years) >= 2:
        return int(years[0]), int(years[1])
    base = _axis_base_year()
    return base, base + _AXIS_SPAN_YEARS


def scenario_position(timeframe: Optional[str], wave_type: str,
                      type_index: int, total_in_type: int) -> tuple[float, float]:
    """Mirror of FutureHorizons.tsx::calculateHorizonPosition."""
    start, end = _parse_timeframe(timeframe)
    avg_year = (start + end) / 2
    base_x = 10 + ((avg_year - _axis_base_year()) / _AXIS_SPAN_YEARS) * 75
    if total_in_type > 1:
        spread = (type_index / (total_in_type - 1) - 0.5) * 55
    else:
        spread = 0
    x = min(92, max(8, base_x + spread))
    y = y_on_curve(x, wave_type)
    # alternating vertical offset so labels don't pile up on the curve itself
    y += (type_index % 3 - 1) * 12
    return x, y


def _to_mpath(cmds, close_to_baseline=False) -> MPath:
    verts, codes = [], []
    for c in cmds:
        if c[0] == "M":
            verts.append((c[1], c[2])); codes.append(MPath.MOVETO)
        elif c[0] == "Q":
            verts.append((c[1], c[2])); codes.append(MPath.CURVE3)
            verts.append((c[3], c[4])); codes.append(MPath.CURVE3)
    if close_to_baseline:
        verts.append((100, 100)); codes.append(MPath.LINETO)
        verts.append((0, 100));   codes.append(MPath.LINETO)
        verts.append((0, 0));     codes.append(MPath.CLOSEPOLY)
    return MPath(verts, codes)


def _gradient_image(stops, width=400):
    xs = np.linspace(0, 1, width)
    rgba = np.zeros((1, width, 4), dtype=float)
    for i, x in enumerate(xs):
        for j in range(len(stops) - 1):
            x0, c0, a0 = stops[j]; x1, c1, a1 = stops[j + 1]
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0) if x1 > x0 else 0
                r0, g0, b0, _ = to_rgba(c0); r1, g1, b1, _ = to_rgba(c1)
                rgba[0, i] = (
                    r0 + (r1 - r0) * t, g0 + (g1 - g0) * t,
                    b0 + (b1 - b0) * t, a0 + (a1 - a0) * t,
                )
                break
    return rgba


def collect_scenarios_for_render(items: Iterable[tuple]) -> list[dict]:
    """Flatten the bundle's ``items`` into a list of scenarios with the fields
    we need to place markers. ``items`` is the standard
    ``[(assessment, run, prior), ...]`` triple the bundle pipeline builds.

    Returns one dict per scenario with ``wave_type``, ``title``, ``topic``,
    ``timeframe``, ``type_index``, ``total_in_type``. Done scenarios skipped.
    """
    by_horizon: dict[str, list[dict]] = {"h1": [], "h2": [], "h3": []}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        for v in (assessment.get("scenario_verdicts") or []):
            if v.get("verdict_label") == "Done":
                continue
            ht = (v.get("horizon_type") or "").lower()
            if ht not in by_horizon:
                continue
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            title = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
            timeframe = v.get("timeframe") or deck_info.get("timeframe")
            by_horizon[ht].append({
                "wave_type": ht, "title": title, "topic": topic,
                "timeframe": timeframe,
            })

    flat: list[dict] = []
    for ht, group in by_horizon.items():
        total = len(group)
        for i, s in enumerate(group):
            s["type_index"] = i
            s["total_in_type"] = total
            flat.append(s)
    return flat


# Card backgrounds — Tailwind blue-50 / purple-50 / green-50 (the
# React component uses these as the light bg for each scenario card)
CARD_BG = {"h1": "#eff6ff", "h2": "#faf5ff", "h3": "#f0fdf4"}

# Horizon timeline labels — the bottom strip on the chart, matching the
# React component's "Present / Short-term / …" footer. Computed per call
# so "Present" is always the current year.
def _timeline() -> list:
    b = _axis_base_year()
    return [
        (str(b), "Present"),
        (str(b + 4), "Short-term"),
        (str(b + 8), "Mid-term"),
        (str(b + 12), "Long-term"),
        (str(b + _AXIS_SPAN_YEARS), "Horizon"),
    ]


# Back-compat for importers that read the constant directly.
TIMELINE = _timeline()


def _wrap_title(text: str, max_chars: int = 22) -> str:
    """Soft-wrap a scenario title for the on-chart label box.

    Mirrors the React card's max-width clipping: ~22-char lines so the
    bbox stays compact (the React uses ``max-w-[160px]`` + 9px font).
    """
    import textwrap as _tw
    if not text:
        return ""
    return "\n".join(_tw.wrap(text, max_chars) or [text])


def render_to_png(scenarios: list[dict], out_stream: BytesIO,
                  *, figsize=(18, 8.5), dpi=180, mode: str = "cards") -> None:
    """Render the curves + scenario markers to a PNG into ``out_stream``.

    ``mode='cards'`` (default, matches the React Future Horizons tab): each
    scenario is a small horizon-coloured rounded card containing its full
    title, placed at its curve position. Right choice when scenario counts
    per chart are small (≤ ~8) so the cards don't crowd.

    ``mode='numbered'``: legacy marker style — white dot + ``N`` number at
    each position, with the caller responsible for an external legend.
    Kept for the cross-topic overview slide (23 scenarios — cards would
    overlap into illegibility).
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_xlim(-2, 108); ax.set_ylim(112, -5)
    ax.set_axis_off(); ax.set_aspect("auto")

    # Faint baseline
    ax.plot([0, 100], [100, 100], color="#e5e7eb", lw=0.8, zorder=0)

    for key, cmds in (("h1", H1_CMDS), ("h2", H2_CMDS), ("h3", H3_CMDS)):
        fill_path = _to_mpath(cmds, close_to_baseline=True)
        grad = _gradient_image(GRADIENTS[key])
        im = ax.imshow(grad, extent=(0, 100, 100, 0), aspect="auto",
                       interpolation="bilinear", zorder=1)
        clip = PathPatch(fill_path, transform=ax.transData,
                         facecolor="none", edgecolor="none")
        ax.add_patch(clip)
        im.set_clip_path(clip)
        stroke_path = _to_mpath(cmds, close_to_baseline=False)
        ax.add_patch(PathPatch(stroke_path, edgecolor=STROKES[key],
                               facecolor="none", lw=2.4, zorder=3))

    # NOW marker — copied from the SVG
    ax.scatter([3], [50], s=70, color="#1f2937", zorder=5)
    ax.text(3, 58, "NOW", color="#1f2937", fontsize=9, ha="center",
            fontweight="bold")
    # End-of-curve labels
    for label, key, y in (("H1", "h1", 75), ("H2", "h2", 60), ("H3", "h3", 20)):
        ax.text(102.5, y, label, color=STROKES[key], fontsize=13,
                fontweight="bold", va="center")

    if mode == "cards":
        # Scenario LABEL CARDS — coloured rounded box with the wrapped title
        # printed inside, placed at the scenario's curve position. Same look
        # as the React component's chart.
        for s in scenarios:
            x, y = scenario_position(s.get("timeframe"), s["wave_type"],
                                     s["type_index"], s["total_in_type"])
            border = STROKES[s["wave_type"]]
            bg = CARD_BG[s["wave_type"]]
            title = _wrap_title(s.get("title") or "", max_chars=22)
            ax.text(
                x, y, title,
                ha="center", va="center",
                color="#111827", fontsize=8.0, fontweight="bold",
                zorder=7,
                bbox=dict(
                    boxstyle="round,pad=0.35,rounding_size=0.3",
                    facecolor=bg, edgecolor=border, linewidth=1.4, alpha=0.97,
                ),
            )
    else:
        # Numbered marker style — used by the cross-topic overview where 23
        # cards would overlap. Caller renders an external legend.
        #
        # Readability fix (2026-05-28): the old white-circle + coloured-number
        # marker was too small to read against the gradient fills. Switch to
        # a solid horizon-colour fill with a white bold number — same
        # high-contrast pattern used for status badges elsewhere — and bump
        # the dot size + font weight. A thin white halo behind the dot keeps
        # it crisp when it sits over a darker gradient region.
        for n, s in enumerate(scenarios, 1):
            x, y = scenario_position(s.get("timeframe"), s["wave_type"],
                                     s["type_index"], s["total_in_type"])
            color = STROKES[s["wave_type"]]
            ax.scatter([x], [y], s=460, color="white", zorder=5)         # halo
            ax.scatter([x], [y], s=360, color=color,
                       edgecolors="white", linewidths=1.5, zorder=6)     # disc
            ax.text(x, y, str(n), color="white",
                    fontsize=10.5, fontweight="bold",
                    ha="center", va="center", zorder=7)

    # Timeline strip at the bottom (matches the React component footer)
    ax.plot([0, 100], [108, 108], color="#e5e7eb", lw=1.0, zorder=0)
    timeline = _timeline()
    n_tl = len(timeline)
    for i, (year, _label) in enumerate(timeline):
        xx = i * (100 / (n_tl - 1))
        ax.text(xx, 110.5, year, color="#374151", fontsize=9,
                fontweight="bold", ha="center", va="top")

    fig.savefig(out_stream, format="png", bbox_inches="tight", pad_inches=0.1,
                facecolor="white")
    plt.close(fig)


def build_notes(scenarios: list[dict]) -> str:
    """Build the speaker-notes block listing every numbered scenario grouped by
    horizon — referenced from the markers on the curves."""
    HORIZON_LABEL = {
        "h1": "H1 · DECLINING SYSTEM",
        "h2": "H2 · TRANSITION",
        "h3": "H3 · FUTURE VISION",
    }
    lines: list[str] = [
        "Three Horizons Overview — scenarios mapped onto the curves.",
        f"Numbering on the chart matches the lists below; left→right is "
        f"NOW→{_axis_base_year() + _AXIS_SPAN_YEARS}.",
        "",
    ]
    for ht in ("h1", "h2", "h3"):
        group = [(i + 1, s) for i, s in enumerate(scenarios) if s["wave_type"] == ht]
        lines.append(HORIZON_LABEL[ht])
        if not group:
            lines.append("  (no scenarios in this horizon)")
        for n, s in group:
            lines.append(f"  [{n}] {s['title']} — {s['topic']}")
        lines.append("")
    return "\n".join(lines).rstrip()
