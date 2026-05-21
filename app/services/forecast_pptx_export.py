"""PPTX export for forecast assessments.

Mirrors the slide-per-scenario layout of the Wiley Horizons deck (slides
64-68 of the Feb 2026 brief): one cover slide, one slide per deck scenario
showing the verdict + baseline-corrected support rates + top supporting
articles, and a final surprises slide listing emergent themes the forecast
missed. Output is a single .pptx file the client can drop into the same
deck format Wiley already uses.

Public entry point: :func:`build_assessment_pptx(assessment, forecast_run)`
returning the PPTX as bytes.
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN


# ── Palette (matches the deck) ────────────────────────────────────────────

INDIGO = RGBColor(0x4F, 0x46, 0xE5)
SLATE_900 = RGBColor(0x0F, 0x17, 0x2A)
SLATE_700 = RGBColor(0x33, 0x41, 0x55)
SLATE_500 = RGBColor(0x64, 0x74, 0x8B)
SLATE_300 = RGBColor(0xCB, 0xD5, 0xE1)
EMERALD = RGBColor(0x05, 0x96, 0x69)
AMBER = RGBColor(0xD9, 0x77, 0x06)
RED = RGBColor(0xDC, 0x26, 0x26)
GRAY = RGBColor(0x6B, 0x72, 0x80)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG_TINT = RGBColor(0xF8, 0xFA, 0xFC)
BG_ACCENT = RGBColor(0xEE, 0xF2, 0xFF)


# ── Helpers ────────────────────────────────────────────────────────────────

def _text_box(slide, *, left, top, width, height, text, font_size=14,
              bold=False, color=SLATE_900, align=PP_ALIGN.LEFT,
              italic=False, font_name="Calibri"):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text or ""
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = font_name
    run.font.color.rgb = color
    return tb


def _filled_box(slide, *, left, top, width, height, fill_color, line_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.adjustments[0] = 0.05  # subtle rounding
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
    shape.shadow.inherit = False
    return shape


def _verdict_color(label: str):
    label = (label or "").lower()
    if "above" in label or label == "accelerating":
        return EMERALD
    if "below" in label or label == "off-track":
        return RED
    if label == "on-track":
        return INDIGO
    if label == "stalled" or "at baseline" in label:
        return GRAY
    return GRAY


def _horizon_label(h: str) -> str:
    h = (h or "").lower()
    return {"h1": "H1 · Declining System",
            "h2": "H2 · Transition / Innovation",
            "h3": "H3 · Future Vision"}.get(h, h.upper() or "—")


def _fmt_pct(x: Optional[float], digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.{digits}f}%" if x != 0 else f"{x * 100:.{digits}f}%"


def _verdict_explanation(verdict_label: Optional[str], baseline: Optional[dict] = None) -> str:
    """Plain-language interpretation for a verdict. Used on scenario slides so
    readers don't need to know what 'Below baseline' means out of context."""
    if baseline:
        label = (baseline.get("label") or "")
        if "Above" in label:
            return (
                "Genuine new signal. The per-article support rate has accelerated since "
                "the forecast was published — the trajectory is materializing more "
                "strongly than the pre-forecast baseline suggested."
            )
        if "Below" in label:
            return (
                "The deck appears to have called a peak signal. Pre-forecast articles "
                "showed a higher support rate than post-forecast ones, so the story was "
                "hotter at deck-authoring time than it is now. This is not a 'wrong "
                "forecast' — it is a 'trend was already in motion and has since cooled' "
                "framing."
            )
        if "At" in label:
            return (
                "The trend was already visible at deck-authoring time. Per-article signal "
                "density is essentially unchanged in the post-forecast window, so we can "
                "neither confirm nor refute the trajectory from this period alone."
            )
    fallback = {
        "Accelerating": "Velocity is positive and milestones are landing — strong evidence the trajectory is materializing.",
        "On-track": "Directional rate is positive and velocity is non-negative; trend continues.",
        "Stalled": "Roughly equal supports and contradicts; no clear directional signal.",
        "Off-track": "More contradicting than supporting evidence in the window.",
        "Inconclusive": "Too few confident classifications to issue a directional verdict.",
    }
    return fallback.get(verdict_label or "", "")


def _headline_finding(scenario_verdicts: list, baseline_per_scenario: dict) -> dict:
    """Pick the scenario with the most extreme net_rate (positive or negative)
    for the executive-summary spotlight. Returns the verdict dict + its
    baseline block + a direction indicator."""
    best = None
    best_abs = -1.0
    for v in scenario_verdicts:
        b = baseline_per_scenario.get(str(v.get("scenario_idx")))
        if not b:
            continue
        net = abs(b.get("net_rate") or 0)
        if net > best_abs:
            best_abs = net
            best = (v, b)
    return {"verdict": best[0], "baseline": best[1]} if best else {}


# ── Slide builders ─────────────────────────────────────────────────────────

def _add_cover_slide(prs, assessment: dict, forecast_run: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw, sh = prs.slide_width, prs.slide_height

    _filled_box(slide, left=0, top=0, width=sw, height=Inches(2.0), fill_color=INDIGO)
    _text_box(slide, left=Inches(0.5), top=Inches(0.3), width=sw - Inches(1.0),
              height=Inches(0.6), text="Forecast Tracker", font_size=18,
              bold=True, color=WHITE)
    _text_box(slide, left=Inches(0.5), top=Inches(0.85), width=sw - Inches(1.0),
              height=Inches(0.9), text=assessment.get("topic") or "—",
              font_size=32, bold=True, color=WHITE)

    summary = assessment.get("summary") or {}
    forecast_at = summary.get("forecast_generated_at") or forecast_run.get("created_at")
    assessed_at = summary.get("assessed_at") or assessment.get("assessed_at")
    elapsed_days = summary.get("elapsed_days")
    pool = summary.get("evidence_pool") or assessment.get("evidence_count") or "—"
    window_weeks = summary.get("window_weeks")

    bc = summary.get("baseline_correction") or {}
    placebo_pool = bc.get("placebo_pool") if bc else None

    meta_lines = [
        f"Forecast generated: {_short_date(forecast_at)}",
        f"Assessed: {_short_date(assessed_at)}"
        + (f" (elapsed {elapsed_days} days)" if elapsed_days else ""),
        f"Live pool: {pool} articles"
        + (f" · Placebo pool: {placebo_pool}" if placebo_pool is not None else ""),
        f"Window: ±{window_weeks} weeks (symmetric live/placebo)"
        if window_weeks else "Window: full post-forecast pool",
        f"Mode: {assessment.get('mode')} · Classifier: {assessment.get('model_used')}",
    ]
    _text_box(slide, left=Inches(0.5), top=Inches(2.5), width=sw - Inches(1.0),
              height=Inches(2.0), text="\n".join(meta_lines), font_size=14,
              color=SLATE_700)

    verdicts = assessment.get("scenario_verdicts") or []
    n = len(verdicts)
    bc_per = (bc.get("per_scenario") or {}) if bc else {}
    if bc_per:
        labels = [v.get("label") for v in bc_per.values()]
        counts = {x: labels.count(x) for x in set(labels)}
        verdict_summary = "  ·  ".join(f"{k}: {v}" for k, v in counts.items())
        heading = "Baseline-corrected verdicts"
    else:
        labels = [v.get("verdict_label") for v in verdicts]
        counts = {x: labels.count(x) for x in set(labels)}
        verdict_summary = "  ·  ".join(f"{k}: {v}" for k, v in counts.items())
        heading = "Verdict distribution"

    _text_box(slide, left=Inches(0.5), top=Inches(4.8), width=sw - Inches(1.0),
              height=Inches(0.4), text=heading, font_size=12, bold=True,
              color=SLATE_500)
    _text_box(slide, left=Inches(0.5), top=Inches(5.2), width=sw - Inches(1.0),
              height=Inches(0.6), text=f"{n} scenarios  ·  {verdict_summary}",
              font_size=16, color=SLATE_900)


def _add_methodology_slide(prs):
    """Single primer slide so the reader knows what Above/At/Below baseline mean
    without needing external context. Drop this in every export."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = prs.slide_width

    _filled_box(slide, left=0, top=0, width=sw, height=Inches(1.0), fill_color=INDIGO)
    _text_box(slide, left=Inches(0.5), top=Inches(0.2), width=sw - Inches(1.0),
              height=Inches(0.6), text="How to Read This Deck", font_size=22,
              bold=True, color=WHITE)

    intro = (
        "We back-tested each Three Horizons scenario against articles that arrived "
        "after the forecast was published. The headline verdict on every scenario slide "
        "is baseline-corrected: we run the same classifier on a symmetric pre-forecast "
        "window (the 'placebo') and subtract the pre-forecast support rate from the "
        "post-forecast rate. What's left — the 'net rate' — is the incremental signal "
        "attributable to the period after the forecast was made."
    )
    _text_box(slide, left=Inches(0.5), top=Inches(1.3), width=sw - Inches(1.0),
              height=Inches(1.5), text=intro, font_size=14, color=SLATE_700)

    rows = [
        ("Above baseline", "Genuine new signal — trajectory accelerated after the forecast was published.", EMERALD),
        ("At baseline", "Trend was already visible at deck-authoring time; per-article signal density is essentially unchanged.", GRAY),
        ("Below baseline", "Deck appears to have called a peak signal — post-forecast support rate is lower than pre-forecast. NOT 'wrong'; rather 'trend was already cresting'.", RED),
    ]
    y = Inches(3.0)
    for label, body, color in rows:
        _filled_box(slide, left=Inches(0.5), top=y, width=Inches(2.6),
                    height=Inches(0.55), fill_color=color)
        _text_box(slide, left=Inches(0.5), top=y + Inches(0.1), width=Inches(2.6),
                  height=Inches(0.4), text=label, font_size=14, bold=True,
                  color=WHITE, align=PP_ALIGN.CENTER)
        _text_box(slide, left=Inches(3.3), top=y + Inches(0.05),
                  width=sw - Inches(3.8), height=Inches(0.6), text=body,
                  font_size=12, color=SLATE_700)
        y = y + Inches(0.8)

    note = (
        "Surprises (unanticipated developments) at the end of the deck are themes that "
        "no scenario explains — articles topical to the brief but unrelated to any "
        "stored scenario, clustered by embedding similarity."
    )
    _text_box(slide, left=Inches(0.5), top=Inches(6.0), width=sw - Inches(1.0),
              height=Inches(1.0), text=note, font_size=11, color=SLATE_500,
              italic=True)


def _add_exec_summary_slide(prs, assessment: dict, headline: dict):
    """One slide answering: what did the forecast get right / wrong / miss?"""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = prs.slide_width

    _filled_box(slide, left=0, top=0, width=sw, height=Inches(1.0), fill_color=INDIGO)
    _text_box(slide, left=Inches(0.5), top=Inches(0.2), width=sw - Inches(1.0),
              height=Inches(0.6), text="Executive Summary", font_size=22,
              bold=True, color=WHITE)

    summary = assessment.get("summary") or {}
    bc = summary.get("baseline_correction") or {}
    bc_per = bc.get("per_scenario") or {}
    verdicts = assessment.get("scenario_verdicts") or []
    n = len(verdicts)

    # Distribution counts
    if bc_per:
        labels = [v.get("label") for v in bc_per.values()]
    else:
        labels = [v.get("verdict_label") for v in verdicts]
    counts = {x: labels.count(x) for x in set(labels) if x}

    # Distribution chips
    y = Inches(1.3)
    _text_box(slide, left=Inches(0.5), top=y, width=Inches(6.0),
              height=Inches(0.35), text="VERDICT DISTRIBUTION", font_size=10,
              bold=True, color=SLATE_500)
    cy = y + Inches(0.4)
    cx = Inches(0.5)
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        w = Inches(2.5)
        _filled_box(slide, left=cx, top=cy, width=w, height=Inches(0.55),
                    fill_color=_verdict_color(label or ""))
        _text_box(slide, left=cx, top=cy + Inches(0.05), width=w,
                  height=Inches(0.25), text=label or "—", font_size=11,
                  bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text_box(slide, left=cx, top=cy + Inches(0.28), width=w,
                  height=Inches(0.25), text=f"{count} of {n} scenarios",
                  font_size=10, color=WHITE, align=PP_ALIGN.CENTER)
        cx = cx + w + Inches(0.15)

    # Headline finding
    hy = Inches(2.8)
    _text_box(slide, left=Inches(0.5), top=hy, width=sw - Inches(1.0),
              height=Inches(0.35), text="HEADLINE FINDING", font_size=10,
              bold=True, color=SLATE_500)
    if headline:
        v = headline["verdict"]
        b = headline["baseline"]
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        label = b.get("label") or "—"
        net = b.get("net_rate") or 0
        live_rate = b.get("live_rate") or 0
        placebo_rate = b.get("placebo_rate") or 0
        consensus = deck_info.get("consensus_pct")

        body = f"{name}"
        _text_box(slide, left=Inches(0.5), top=hy + Inches(0.35),
                  width=sw - Inches(3.5), height=Inches(0.5), text=body,
                  font_size=18, bold=True, color=SLATE_900)
        chip_w = Inches(2.6)
        chip_x = sw - chip_w - Inches(0.4)
        _filled_box(slide, left=chip_x, top=hy + Inches(0.35), width=chip_w,
                    height=Inches(0.55), fill_color=_verdict_color(label))
        _text_box(slide, left=chip_x, top=hy + Inches(0.45), width=chip_w,
                  height=Inches(0.4), text=label, font_size=14, bold=True,
                  color=WHITE, align=PP_ALIGN.CENTER)

        stats_line = (
            f"Original deck consensus: {consensus}%   "
            f"·   live {live_rate*100:.2f}%   −   placebo {placebo_rate*100:.2f}%   "
            f"=   {net*100:+.2f}% net rate"
        )
        _text_box(slide, left=Inches(0.5), top=hy + Inches(1.0),
                  width=sw - Inches(1.0), height=Inches(0.4), text=stats_line,
                  font_size=12, color=SLATE_700)
        _text_box(slide, left=Inches(0.5), top=hy + Inches(1.45),
                  width=sw - Inches(1.0), height=Inches(1.2),
                  text=_verdict_explanation(v.get("verdict_label"), b),
                  font_size=12, color=SLATE_700, italic=True)
    else:
        _text_box(slide, left=Inches(0.5), top=hy + Inches(0.35),
                  width=sw - Inches(1.0), height=Inches(0.5),
                  text="No baseline-corrected scenario stood out.", font_size=14,
                  color=SLATE_500, italic=True)

    # Surprises spotlight
    surprises = assessment.get("surprises") or []
    sy = Inches(5.5)
    _text_box(slide, left=Inches(0.5), top=sy, width=sw - Inches(1.0),
              height=Inches(0.35), text="DOMINANT EMERGING THEME", font_size=10,
              bold=True, color=SLATE_500)
    if surprises:
        top = max(surprises, key=lambda s: s.get("size") or 0)
        label = top.get("label") or "(unlabelled cluster)"
        size = top.get("size") or 0
        _text_box(slide, left=Inches(0.5), top=sy + Inches(0.35),
                  width=sw - Inches(1.0), height=Inches(0.5),
                  text=f"{size}×  {label}", font_size=16, bold=True,
                  color=AMBER)
        note = top.get("note")
        if note:
            _text_box(slide, left=Inches(0.5), top=sy + Inches(0.95),
                      width=sw - Inches(1.0), height=Inches(0.8),
                      text=_truncate(note, 300), font_size=11, italic=True,
                      color=SLATE_700)
    else:
        _text_box(slide, left=Inches(0.5), top=sy + Inches(0.35),
                  width=sw - Inches(1.0), height=Inches(0.5),
                  text="No surprise clusters of sufficient cohesion.",
                  font_size=12, color=SLATE_500, italic=True)


def _add_whats_changed_slide(prs, assessment: dict):
    """Side-by-side: original deck consensus % vs corrected verdict per scenario."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = prs.slide_width

    _filled_box(slide, left=0, top=0, width=sw, height=Inches(1.0), fill_color=INDIGO)
    _text_box(slide, left=Inches(0.5), top=Inches(0.2), width=sw - Inches(1.0),
              height=Inches(0.6), text="What's Changed: Deck vs Tracker",
              font_size=22, bold=True, color=WHITE)

    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = assessment.get("scenario_verdicts") or []

    # Column headers
    y = Inches(1.4)
    cols = [
        ("SCENARIO", Inches(0.5), Inches(5.5)),
        ("DECK", Inches(6.2), Inches(1.2)),
        ("LIVE RATE", Inches(7.5), Inches(1.2)),
        ("PLACEBO", Inches(8.8), Inches(1.2)),
        ("NET", Inches(10.1), Inches(1.2)),
        ("VERDICT", Inches(11.4), Inches(1.8)),
    ]
    for label, x, w in cols:
        _text_box(slide, left=x, top=y, width=w, height=Inches(0.35),
                  text=label, font_size=9, bold=True, color=SLATE_500)
    y = y + Inches(0.4)

    # Header rule
    _filled_box(slide, left=Inches(0.5), top=y, width=sw - Inches(1.0),
                height=Inches(0.02), fill_color=SLATE_300)
    y = y + Inches(0.1)

    for v in verdicts:
        b = bc_per.get(str(v.get("scenario_idx"))) or {}
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
        consensus = deck_info.get("consensus_pct")
        live = b.get("live_rate")
        placebo = b.get("placebo_rate")
        net = b.get("net_rate")
        label = b.get("label") or v.get("verdict_label") or "—"

        row_y = y
        _text_box(slide, left=Inches(0.5), top=row_y, width=Inches(5.5),
                  height=Inches(0.4), text=_truncate(name, 75), font_size=11,
                  bold=True, color=SLATE_900)
        _text_box(slide, left=Inches(6.2), top=row_y, width=Inches(1.2),
                  height=Inches(0.4),
                  text=f"{consensus}%" if consensus is not None else "—",
                  font_size=12, color=SLATE_700)
        _text_box(slide, left=Inches(7.5), top=row_y, width=Inches(1.2),
                  height=Inches(0.4),
                  text=f"{live*100:.2f}%" if live is not None else "—",
                  font_size=12, color=SLATE_700)
        _text_box(slide, left=Inches(8.8), top=row_y, width=Inches(1.2),
                  height=Inches(0.4),
                  text=f"{placebo*100:.2f}%" if placebo is not None else "—",
                  font_size=12, color=SLATE_700)
        net_color = _verdict_color(label) if net is not None and abs(net) > 0.001 else SLATE_500
        _text_box(slide, left=Inches(10.1), top=row_y, width=Inches(1.2),
                  height=Inches(0.4),
                  text=f"{net*100:+.2f}%" if net is not None else "—",
                  font_size=12, bold=True, color=net_color)
        chip_w = Inches(1.8)
        _filled_box(slide, left=Inches(11.4), top=row_y - Inches(0.05),
                    width=chip_w, height=Inches(0.4),
                    fill_color=_verdict_color(label))
        _text_box(slide, left=Inches(11.4), top=row_y, width=chip_w,
                  height=Inches(0.3), text=label, font_size=10, bold=True,
                  color=WHITE, align=PP_ALIGN.CENTER)
        y = y + Inches(0.55)

    # Footer caveat
    footer = (
        "Net rate = post-forecast support rate − symmetric pre-forecast support rate. "
        "See methodology primer for verdict interpretations."
    )
    _text_box(slide, left=Inches(0.5), top=Inches(7.0), width=sw - Inches(1.0),
              height=Inches(0.4), text=footer, font_size=9, italic=True,
              color=SLATE_500)


def _add_scenario_slide(prs, verdict: dict, baseline: Optional[dict]):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw, sh = prs.slide_width, prs.slide_height
    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}

    horizon = _horizon_label(verdict.get("horizon_type"))
    consensus = deck_info.get("consensus_pct")
    consensus_chip = f"{consensus}% original consensus" if consensus is not None else None
    scenario_name = (deck_info.get("deck_scenario_name")
                     or verdict.get("scenario_title") or "—")

    # Header bar
    _filled_box(slide, left=0, top=0, width=sw, height=Inches(1.4), fill_color=BG_ACCENT)
    _text_box(slide, left=Inches(0.5), top=Inches(0.25), width=Inches(6.0),
              height=Inches(0.4), text=horizon, font_size=12, bold=True,
              color=INDIGO)
    if consensus_chip:
        _text_box(slide, left=Inches(0.5), top=Inches(0.7), width=Inches(6.0),
                  height=Inches(0.4), text=consensus_chip, font_size=11,
                  color=SLATE_700, italic=True)
    _text_box(slide, left=Inches(0.5), top=Inches(1.0), width=Inches(9.0),
              height=Inches(0.45), text=scenario_name, font_size=22, bold=True,
              color=SLATE_900)

    # Verdict chip (top right) — baseline-corrected if available
    if baseline:
        label = baseline.get("label") or verdict.get("verdict_label") or "—"
    else:
        label = verdict.get("verdict_label") or "—"
    chip_w = Inches(2.8)
    chip_x = sw - chip_w - Inches(0.4)
    _filled_box(slide, left=chip_x, top=Inches(0.3), width=chip_w,
                height=Inches(0.6), fill_color=_verdict_color(label))
    _text_box(slide, left=chip_x, top=Inches(0.38), width=chip_w,
              height=Inches(0.4), text=label, font_size=14, bold=True,
              color=WHITE, align=PP_ALIGN.CENTER)
    if baseline:
        raw_label = verdict.get("verdict_label") or "—"
        _text_box(slide, left=chip_x, top=Inches(0.92), width=chip_w,
                  height=Inches(0.3), text=f"raw: {raw_label}", font_size=9,
                  color=SLATE_500, align=PP_ALIGN.CENTER)

    # Primary signal
    primary = deck_info.get("primary_signal")
    y = Inches(1.7)
    if primary:
        _text_box(slide, left=Inches(0.5), top=y, width=sw - Inches(1.0),
                  height=Inches(0.9), text=primary, font_size=13, italic=True,
                  color=SLATE_700)
        y = Inches(2.7)

    # Stats row
    stats_y = y
    cell_w = (sw - Inches(1.0)) / 4
    metrics = [
        ("Supports", str(verdict.get("supports") or 0), EMERALD),
        ("Contradicts", str(verdict.get("contradicts") or 0), RED),
        ("Rate", f"{verdict.get('directional_rate', 0):.2f}", SLATE_700),
        ("Coverage", f"{verdict.get('coverage', 0):.2f}", SLATE_700),
    ]
    for i, (label, value, color) in enumerate(metrics):
        cx = Inches(0.5) + cell_w * i
        _text_box(slide, left=cx, top=stats_y, width=cell_w, height=Inches(0.3),
                  text=label, font_size=10, color=SLATE_500, align=PP_ALIGN.CENTER)
        _text_box(slide, left=cx, top=stats_y + Inches(0.3), width=cell_w,
                  height=Inches(0.5), text=value, font_size=22, bold=True,
                  color=color, align=PP_ALIGN.CENTER)
    y = stats_y + Inches(1.0)

    # Baseline correction block
    if baseline:
        _filled_box(slide, left=Inches(0.5), top=y, width=sw - Inches(1.0),
                    height=Inches(1.0), fill_color=BG_TINT, line_color=SLATE_300)
        _text_box(slide, left=Inches(0.7), top=y + Inches(0.1), width=Inches(3.5),
                  height=Inches(0.3), text="Baseline-corrected", font_size=10,
                  bold=True, color=SLATE_500)
        live = baseline.get("live_rate", 0)
        placebo = baseline.get("placebo_rate", 0)
        net = baseline.get("net_rate", 0)
        body = (
            f"live {live*100:.2f}%   −   placebo {placebo*100:.2f}%   =   "
            f"{net*100:+.2f}%   ({baseline.get('label') or '—'})"
        )
        _text_box(slide, left=Inches(0.7), top=y + Inches(0.4), width=sw - Inches(1.4),
                  height=Inches(0.45), text=body, font_size=14, bold=True,
                  color=_verdict_color(baseline.get("label") or ""))
        pools = (
            f"live {baseline.get('live_supports')}/{baseline.get('live_pool')}   "
            f"·   placebo {baseline.get('placebo_supports')}/{baseline.get('placebo_pool')}"
        )
        _text_box(slide, left=Inches(0.7), top=y + Inches(0.75), width=sw - Inches(1.4),
                  height=Inches(0.3), text=pools, font_size=10, color=SLATE_500)
        y = y + Inches(1.2)

    # Top supporting articles
    supports = (verdict.get("top_articles") or {}).get("supports") or []
    contradicts = (verdict.get("top_articles") or {}).get("contradicts") or []
    if supports:
        _text_box(slide, left=Inches(0.5), top=y, width=Inches(5.0),
                  height=Inches(0.3), text="TOP SUPPORTING", font_size=10,
                  bold=True, color=EMERALD)
        y2 = y + Inches(0.35)
        for art in supports[:2]:
            title = art.get("title") or art.get("article_uri") or "(no title)"
            rationale = art.get("rationale") or ""
            _text_box(slide, left=Inches(0.5), top=y2, width=Inches(5.0),
                      height=Inches(0.35), text=_truncate(title, 110),
                      font_size=11, bold=True, color=SLATE_900)
            if rationale:
                _text_box(slide, left=Inches(0.5), top=y2 + Inches(0.32),
                          width=Inches(5.0), height=Inches(0.5),
                          text=_truncate(rationale, 220), font_size=9,
                          italic=True, color=SLATE_700)
            y2 = y2 + Inches(0.9)

    if contradicts:
        _text_box(slide, left=Inches(5.6), top=y, width=Inches(4.0),
                  height=Inches(0.3), text="STRONGEST CONTRADICTING",
                  font_size=10, bold=True, color=RED)
        y2 = y + Inches(0.35)
        for art in contradicts[:1]:
            title = art.get("title") or art.get("article_uri") or "(no title)"
            rationale = art.get("rationale") or ""
            _text_box(slide, left=Inches(5.6), top=y2, width=Inches(4.0),
                      height=Inches(0.35), text=_truncate(title, 90),
                      font_size=11, bold=True, color=SLATE_900)
            if rationale:
                _text_box(slide, left=Inches(5.6), top=y2 + Inches(0.32),
                          width=Inches(4.0), height=Inches(0.5),
                          text=_truncate(rationale, 200), font_size=9,
                          italic=True, color=SLATE_700)

    # Verdict explanation — a plain-language interpretation of what the chip
    # label means in this context. Sits at the bottom so reviewers don't need
    # external context to understand the verdict.
    explanation = _verdict_explanation(verdict.get("verdict_label"), baseline)
    if explanation:
        _filled_box(slide, left=Inches(0.5), top=Inches(6.55),
                    width=sw - Inches(1.0), height=Inches(0.85),
                    fill_color=BG_TINT, line_color=SLATE_300)
        _text_box(slide, left=Inches(0.7), top=Inches(6.6),
                  width=Inches(2.4), height=Inches(0.3),
                  text="WHAT THIS MEANS", font_size=9, bold=True, color=SLATE_500)
        _text_box(slide, left=Inches(0.7), top=Inches(6.85),
                  width=sw - Inches(1.4), height=Inches(0.5),
                  text=explanation, font_size=10, italic=True, color=SLATE_700)


def _add_surprises_section(prs, surprises: list):
    """One overview slide listing all clusters at a glance, then one slide
    per cluster with sample articles. Front-load the densest cluster."""
    blank = prs.slide_layouts[6]
    sw = prs.slide_width

    # Overview / divider slide
    slide = prs.slides.add_slide(blank)
    _filled_box(slide, left=0, top=0, width=sw, height=Inches(7.5), fill_color=AMBER)
    _text_box(slide, left=Inches(0.5), top=Inches(2.5), width=sw - Inches(1.0),
              height=Inches(1.0), text="Unanticipated Developments",
              font_size=42, bold=True, color=WHITE)
    if surprises:
        subtitle = (
            f"{len(surprises)} cluster" + ("s" if len(surprises) != 1 else "") +
            " of articles topical to this brief but unrelated to any deck scenario."
        )
    else:
        subtitle = "No clusters of sufficient cohesion detected this window."
    _text_box(slide, left=Inches(0.5), top=Inches(3.7), width=sw - Inches(1.0),
              height=Inches(0.6), text=subtitle, font_size=16, color=WHITE,
              italic=True)
    if surprises:
        rank = "  ·  ".join(
            f"{s.get('size') or 0}×  {_truncate(s.get('label') or '(unlabelled)', 60)}"
            for s in sorted(surprises, key=lambda s: -(s.get("size") or 0))[:5]
        )
        _text_box(slide, left=Inches(0.5), top=Inches(4.6),
                  width=sw - Inches(1.0), height=Inches(2.0), text=rank,
                  font_size=11, color=WHITE)

    if not surprises:
        return

    # One cluster per slide, ordered by cluster size (densest first).
    for sur in sorted(surprises, key=lambda s: -(s.get("size") or 0)):
        _add_surprise_cluster_slide(prs, sur)


def _add_surprise_cluster_slide(prs, sur: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = prs.slide_width

    size = sur.get("size") or 0
    label = sur.get("label") or "(unlabelled cluster)"
    note = sur.get("note") or ""
    samples = sur.get("sample_articles") or []

    # Header bar
    _filled_box(slide, left=0, top=0, width=sw, height=Inches(1.4), fill_color=BG_ACCENT)
    _text_box(slide, left=Inches(0.5), top=Inches(0.2), width=Inches(2.5),
              height=Inches(0.45), text="UNANTICIPATED THEME", font_size=10,
              bold=True, color=AMBER)
    _text_box(slide, left=Inches(0.5), top=Inches(0.6), width=Inches(10.5),
              height=Inches(0.7), text=label, font_size=22, bold=True,
              color=SLATE_900)

    chip_w = Inches(1.8)
    chip_x = sw - chip_w - Inches(0.4)
    _filled_box(slide, left=chip_x, top=Inches(0.3), width=chip_w,
                height=Inches(0.7), fill_color=AMBER)
    _text_box(slide, left=chip_x, top=Inches(0.4), width=chip_w,
              height=Inches(0.6), text=f"{size}×", font_size=22, bold=True,
              color=WHITE, align=PP_ALIGN.CENTER)

    y = Inches(1.7)
    if note:
        _text_box(slide, left=Inches(0.5), top=y, width=sw - Inches(1.0),
                  height=Inches(0.45), text="WHY IT MATTERS", font_size=10,
                  bold=True, color=SLATE_500)
        _text_box(slide, left=Inches(0.5), top=y + Inches(0.35),
                  width=sw - Inches(1.0), height=Inches(1.2),
                  text=note, font_size=12, italic=True, color=SLATE_700)
        y = y + Inches(1.7)

    if samples:
        _text_box(slide, left=Inches(0.5), top=y, width=sw - Inches(1.0),
                  height=Inches(0.45),
                  text=f"SAMPLE ARTICLES ({min(len(samples), 5)} of {size})",
                  font_size=10, bold=True, color=SLATE_500)
        y2 = y + Inches(0.4)
        for art in samples[:5]:
            title = art.get("title") or art.get("uri") or "(no title)"
            date = art.get("date")
            line = f"{date}   {_truncate(title, 130)}" if date else _truncate(title, 140)
            _filled_box(slide, left=Inches(0.5), top=y2 + Inches(0.05),
                        width=Inches(0.08), height=Inches(0.35),
                        fill_color=AMBER)
            _text_box(slide, left=Inches(0.75), top=y2,
                      width=sw - Inches(1.25), height=Inches(0.45),
                      text=line, font_size=11, color=SLATE_900)
            y2 = y2 + Inches(0.55)


# ── Public ─────────────────────────────────────────────────────────────────

def build_assessment_pptx(assessment: dict, forecast_run: Optional[dict] = None) -> bytes:
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    verdicts = assessment.get("scenario_verdicts") or []
    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})

    _add_cover_slide(prs, assessment, forecast_run or {})
    _add_methodology_slide(prs)
    headline = _headline_finding(verdicts, bc_per)
    _add_exec_summary_slide(prs, assessment, headline)
    if bc_per:
        _add_whats_changed_slide(prs, assessment)

    for v in verdicts:
        key = str(v.get("scenario_idx"))
        baseline = bc_per.get(key)
        _add_scenario_slide(prs, v, baseline)

    _add_surprises_section(prs, assessment.get("surprises") or [])

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


# ── Internal helpers ───────────────────────────────────────────────────────

def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _short_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(iso)[:10]
