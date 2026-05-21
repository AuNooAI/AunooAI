"""PPTX export for forecast assessments — Wiley Horizons deck style.

Replicates the visual language of the Feb 2026 Wiley Horizons brief
(slides 64-68): 10×5.62-in slides with a dark-navy left rail (horizon code,
consensus chip, AunooAI mark), a 3-column main area (Primary Signal /
Decision Fork / Tracking), and the Wiley palette throughout.

For the Forecast Tracker we replace the deck's "Your Window" action panel
with a "Tracking" panel showing the baseline-corrected verdict and the
supporting-evidence counts. The rest mirrors the deck so the exported
file drops into the same template Wiley already uses.

Public entry point: :func:`build_assessment_pptx(assessment, forecast_run)`
returns the PPTX as bytes.
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional, List
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR


# ── Wiley deck palette (sampled from the source PPTX) ─────────────────────

NAVY        = RGBColor(0x0D, 0x1B, 0x2A)  # left rail bg, titles dark
TITLE_DARK  = RGBColor(0x1A, 0x23, 0x30)  # title text
SLATE_MID   = RGBColor(0x3D, 0x4F, 0x60)  # body text
SLATE_BODY  = RGBColor(0x4A, 0x55, 0x68)  # softer body
SLATE_LIGHT = RGBColor(0x8A, 0x96, 0xA3)  # labels, brand mark, dividers text
RULE_GRAY   = RGBColor(0xD8, 0xDD, 0xE3)  # horizontal rule
COL_DIV     = RGBColor(0xE2, 0xE8, 0xF0)  # column divider

# Accents per horizon
TEAL        = RGBColor(0x0D, 0x94, 0x88)  # H1 + primary signal accent
ORANGE      = RGBColor(0xB8, 0x76, 0x20)  # H3
GOLD        = RGBColor(0xC9, 0x92, 0x2A)  # H2 / minority view bar
CORAL       = RGBColor(0xE0, 0x5A, 0x4E)  # action window accent, contradicts
EMERALD     = RGBColor(0x05, 0x96, 0x69)  # check / favorable

# Soft fills (icon chip backgrounds, banners)
PALE_TEAL   = RGBColor(0xE6, 0xFA, 0xF8)
PALE_GOLD   = RGBColor(0xFE, 0xF3, 0xDC)
PALE_AMBER  = RGBColor(0xFF, 0xFB, 0xEB)
PALE_GREEN  = RGBColor(0xD1, 0xFA, 0xE5)
PALE_RED    = RGBColor(0xFE, 0xE2, 0xE2)
PALE_CORAL  = RGBColor(0xFE, 0xF2, 0xEF)

MINORITY_TXT = RGBColor(0x7C, 0x57, 0x00)  # text on minority view banner

WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
CARD_BG     = WHITE
BODY_FONT   = "Calibri"

# Forecast Tracker additions — semantic colors for baseline labels
BASELINE_COLORS = {
    "Above baseline": EMERALD,
    "At baseline":    SLATE_LIGHT,
    "Below baseline": CORAL,
}

# Verdict label → soft fill on the supports/contradicts chips
SUPPORT_COLOR = EMERALD
CONTRA_COLOR  = CORAL
NEUTRAL_COLOR = SLATE_LIGHT


def _horizon_color(h: Optional[str]) -> RGBColor:
    return {"h1": TEAL, "h2": GOLD, "h3": ORANGE}.get((h or "").lower(), TEAL)


def _horizon_label(h: Optional[str]) -> str:
    return {
        "h1": "DECLINING\nSYSTEM",
        "h2": "TRANSITION /\nINNOVATION",
        "h3": "FUTURE\nVISION",
    }.get((h or "").lower(), "")


def _horizon_full_label(h: Optional[str]) -> str:
    return {
        "h1": "Horizon: H1 — Declining System",
        "h2": "Horizon: H2 — Transition / Innovation",
        "h3": "Horizon: H3 — Future Vision",
    }.get((h or "").lower(), "")


def _baseline_color(label: Optional[str]) -> RGBColor:
    for key, c in BASELINE_COLORS.items():
        if label and key in label:
            return c
    return SLATE_LIGHT


# ── Low-level helpers ─────────────────────────────────────────────────────

def _text(slide, *, x, y, w, h, text, font_size=10.0, bold=False, italic=False,
          color=TITLE_DARK, align=PP_ALIGN.LEFT, font_name=BODY_FONT,
          line_spacing: Optional[float] = None,
          anchor=MSO_ANCHOR.TOP):
    """Add a text box. ``text`` may contain newlines — each becomes a paragraph
    so paragraph-level alignment/spacing applies uniformly."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    lines = (text or "").split("\n") if text is not None else [""]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing:
            p.line_spacing = line_spacing
        r = p.add_run()
        r.text = line
        r.font.name = font_name
        r.font.size = Pt(font_size)
        r.font.bold = bold
        r.font.italic = italic
        r.font.color.rgb = color
    return tb


def _rect(slide, *, x, y, w, h, fill, line=None, rounded=False):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    s = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if rounded:
        s.adjustments[0] = 0.12
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
    s.shadow.inherit = False
    return s


def _add_left_rail(slide, *, horizon: str, consensus_pct: Optional[float]):
    """Dark-navy rail with H-code, label, consensus chip, and AunooAI mark."""
    accent = _horizon_color(horizon)
    h = (horizon or "").upper() if horizon else ""

    # Rail bg
    _rect(slide, x=0, y=0, w=1.6, h=5.62, fill=NAVY)

    # H-code (huge)
    _text(slide, x=0.0, y=0.8, w=1.6, h=1.1, text=h, font_size=64,
          bold=True, color=accent, align=PP_ALIGN.CENTER)

    # "HORIZON" small caps
    _text(slide, x=0.0, y=1.95, w=1.6, h=0.25, text="HORIZON",
          font_size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # Divider line
    _rect(slide, x=0.4, y=2.22, w=0.8, h=0.015, fill=accent)

    # System label (two lines, e.g. "DECLINING / SYSTEM")
    sys_label = _horizon_label(horizon)
    _text(slide, x=0.0, y=2.3, w=1.6, h=0.6, text=sys_label, font_size=8,
          bold=False, color=SLATE_LIGHT, align=PP_ALIGN.CENTER,
          line_spacing=1.1)

    # Consensus chip
    if consensus_pct is not None:
        _rect(slide, x=0.2, y=3.4, w=1.2, h=0.85, fill=accent, rounded=True)
        _text(slide, x=0.2, y=3.45, w=1.2, h=0.4, text=f"{int(consensus_pct)}%",
              font_size=22, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(slide, x=0.2, y=3.88, w=1.2, h=0.3, text="CONSENSUS",
              font_size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # AunooAI brand mark
    _text(slide, x=0.0, y=5.32, w=1.6, h=0.22, text="AunooAI",
          font_size=8, color=SLATE_LIGHT, align=PP_ALIGN.CENTER)


def _add_minority_banner(slide, *, x, y, w, text):
    """Pale-amber banner with gold left accent — used for 'Minority view' lines."""
    _rect(slide, x=x, y=y, w=w, h=0.45, fill=PALE_AMBER)
    _rect(slide, x=x, y=y, w=0.08, h=0.45, fill=GOLD)
    _text(slide, x=x+0.18, y=y+0.06, w=w-0.25, h=0.35, text=text,
          font_size=8.5, bold=True, color=MINORITY_TXT)


def _add_column_card(slide, *, x, y, w, h, accent: RGBColor):
    """Standard white card with thin accent strip at the top."""
    _rect(slide, x=x, y=y, w=w, h=h, fill=CARD_BG)
    _rect(slide, x=x, y=y, w=w, h=0.05, fill=accent)


def _add_brand_footer(slide, *, slide_label: str = ""):
    """Faint AunooAI footer on non-scenario slides (the scenario slides have
    the rail mark; other slides need their own brand mark)."""
    sw = 10.0
    _text(slide, x=0.5, y=5.35, w=4.0, h=0.2, text=f"AunooAI Forecast Tracker",
          font_size=8, bold=True, color=SLATE_LIGHT)
    if slide_label:
        _text(slide, x=5.5, y=5.35, w=4.0, h=0.2, text=slide_label,
              font_size=8, color=SLATE_LIGHT, align=PP_ALIGN.RIGHT)


# ── Slide builders ────────────────────────────────────────────────────────

def _add_cover_slide(prs, assessment: dict, forecast_run: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Full-bleed navy
    _rect(slide, x=0, y=0, w=sw, h=5.62, fill=NAVY)

    # Brand mark + product strap
    _text(slide, x=0.5, y=0.4, w=4.0, h=0.3, text="AunooAI · FORECAST TRACKER",
          font_size=11, bold=True, color=TEAL)

    # Topic
    topic = assessment.get("topic") or "—"
    _text(slide, x=0.5, y=1.4, w=sw-1.0, h=0.9, text=topic, font_size=32,
          bold=True, color=WHITE)

    # Strapline
    summary = assessment.get("summary") or {}
    forecast_at = summary.get("forecast_generated_at") or forecast_run.get("created_at")
    assessed_at = summary.get("assessed_at") or assessment.get("assessed_at")
    window_weeks = summary.get("window_weeks")
    elapsed = summary.get("elapsed_days")

    line2 = (
        f"Back-test of the Three Horizons forecast generated "
        f"{_short_date(forecast_at)}, assessed {_short_date(assessed_at)}"
    )
    _text(slide, x=0.5, y=2.5, w=sw-1.0, h=0.5, text=line2,
          font_size=14, color=RULE_GRAY)

    # Headline stats row
    bc = summary.get("baseline_correction") or {}
    pool_live = bc.get("live_pool") or summary.get("evidence_pool") or assessment.get("evidence_count")
    pool_placebo = bc.get("placebo_pool")
    n_scenarios = len(assessment.get("scenario_verdicts") or [])
    n_surprises = len(assessment.get("surprises") or [])

    pairs = [
        ("Scenarios", str(n_scenarios)),
        ("Live pool", _fmt_int(pool_live)),
        ("Placebo pool", _fmt_int(pool_placebo) if pool_placebo is not None else "—"),
        ("Window", f"±{window_weeks} weeks" if window_weeks else "full"),
        ("Surprises", str(n_surprises)),
    ]
    cx = 0.5
    for label, value in pairs:
        _text(slide, x=cx, y=3.5, w=1.7, h=0.28, text=label.upper(),
              font_size=8, bold=True, color=TEAL)
        _text(slide, x=cx, y=3.78, w=1.7, h=0.6, text=value, font_size=22,
              bold=True, color=WHITE)
        cx += 1.85

    _text(slide, x=0.5, y=5.3, w=sw-1.0, h=0.22,
          text=f"Model: {assessment.get('model_used') or '—'}  ·  Mode: {assessment.get('mode') or '—'}",
          font_size=8, color=SLATE_LIGHT)


def _add_methodology_slide(prs):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Navy header bar
    _rect(slide, x=0, y=0, w=sw, h=0.85, fill=NAVY)
    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.55, text="How to Read This Deck",
          font_size=20, bold=True, color=WHITE)

    intro = (
        "Each scenario was back-tested against articles that arrived after the "
        "forecast was published. The headline verdict on every scenario slide is "
        "baseline-corrected: we re-ran the identical classifier on a symmetric "
        "PRE-forecast window (the 'placebo') and subtracted the pre-forecast "
        "support rate from the post-forecast rate. What's left — the 'net rate' "
        "— is the incremental signal attributable to the period after the "
        "forecast was made."
    )
    _text(slide, x=0.5, y=1.05, w=sw-1.0, h=1.2, text=intro, font_size=10,
          color=SLATE_MID, line_spacing=1.25)

    rows = [
        ("Above baseline", EMERALD,
         "Genuine new signal — trajectory accelerated after the forecast was published."),
        ("At baseline", SLATE_LIGHT,
         "Trend was already visible at deck-authoring time; signal density essentially unchanged."),
        ("Below baseline", CORAL,
         "Deck appears to have called a peak signal. Post-forecast support rate is lower than pre-forecast. NOT 'wrong' — rather 'trend was already cresting'."),
    ]
    y = 2.4
    for label, color, body in rows:
        _rect(slide, x=0.5, y=y, w=2.2, h=0.45, fill=color, rounded=True)
        _text(slide, x=0.5, y=y+0.08, w=2.2, h=0.32, text=label,
              font_size=11, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(slide, x=2.85, y=y+0.02, w=sw-3.4, h=0.55, text=body,
              font_size=10, color=SLATE_MID, line_spacing=1.2)
        y += 0.7

    footer = (
        "Unanticipated Developments at the end of the deck are themes that no "
        "scenario explains — articles topical to the brief but unrelated to any "
        "stored scenario, clustered by embedding similarity."
    )
    _text(slide, x=0.5, y=4.6, w=sw-1.0, h=0.7, text=footer, font_size=9,
          italic=True, color=SLATE_LIGHT, line_spacing=1.2)

    _add_brand_footer(slide, slide_label="Methodology")


def _add_exec_summary_slide(prs, assessment: dict, headline: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _rect(slide, x=0, y=0, w=sw, h=0.85, fill=NAVY)
    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.55, text="Executive Summary",
          font_size=20, bold=True, color=WHITE)

    summary = assessment.get("summary") or {}
    bc = summary.get("baseline_correction") or {}
    bc_per = bc.get("per_scenario") or {}
    verdicts = assessment.get("scenario_verdicts") or []
    n = len(verdicts)

    # Verdict distribution chips
    if bc_per:
        labels = [v.get("label") for v in bc_per.values()]
        heading = "BASELINE-CORRECTED VERDICTS"
    else:
        labels = [v.get("verdict_label") for v in verdicts]
        heading = "VERDICT DISTRIBUTION"
    counts = {x: labels.count(x) for x in set(labels) if x}

    _text(slide, x=0.5, y=1.05, w=sw-1.0, h=0.25, text=heading, font_size=9,
          bold=True, color=TEAL)
    cx = 0.5
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        color = _baseline_color(label)
        chip_w = 2.0
        _rect(slide, x=cx, y=1.32, w=chip_w, h=0.5, fill=color, rounded=True)
        _text(slide, x=cx, y=1.36, w=chip_w, h=0.22, text=label or "—",
              font_size=10, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(slide, x=cx, y=1.58, w=chip_w, h=0.22,
              text=f"{count} of {n} scenarios", font_size=8.5,
              color=WHITE, align=PP_ALIGN.CENTER)
        cx += chip_w + 0.12

    # Headline finding panel
    y0 = 2.05
    if headline:
        v = headline["verdict"]
        b = headline["baseline"]
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        label = b.get("label") or "—"
        net = b.get("net_rate") or 0
        live = b.get("live_rate") or 0
        placebo = b.get("placebo_rate") or 0
        consensus = deck_info.get("consensus_pct")

        _text(slide, x=0.5, y=y0, w=sw-1.0, h=0.28, text="HEADLINE FINDING",
              font_size=9, bold=True, color=TEAL)
        _text(slide, x=0.5, y=y0+0.28, w=sw-2.5, h=0.5, text=name or "—",
              font_size=16, bold=True, color=TITLE_DARK)
        # corrected-verdict chip on the right
        chip_w = 1.85
        chip_x = sw - chip_w - 0.5
        _rect(slide, x=chip_x, y=y0+0.28, w=chip_w, h=0.5,
              fill=_baseline_color(label), rounded=True)
        _text(slide, x=chip_x, y=y0+0.38, w=chip_w, h=0.32, text=label,
              font_size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

        stats = (
            f"Original consensus {consensus}%   ·   "
            f"live {live*100:.2f}%   −   placebo {placebo*100:.2f}%   "
            f"=   {net*100:+.2f}% net rate"
        )
        _text(slide, x=0.5, y=y0+0.95, w=sw-1.0, h=0.3, text=stats,
              font_size=10, color=SLATE_MID)
        expl = _verdict_explanation(v.get("verdict_label"), b)
        _text(slide, x=0.5, y=y0+1.3, w=sw-1.0, h=0.95, text=expl,
              font_size=10, italic=True, color=SLATE_MID, line_spacing=1.25)

    # Dominant emerging theme
    surprises = assessment.get("surprises") or []
    if surprises:
        top = max(surprises, key=lambda s: s.get("size") or 0)
        ty = 4.3
        _text(slide, x=0.5, y=ty, w=sw-1.0, h=0.28,
              text="DOMINANT EMERGING THEME", font_size=9, bold=True,
              color=GOLD)
        _text(slide, x=0.5, y=ty+0.28, w=sw-1.0, h=0.4,
              text=f"{top.get('size') or 0}×  {_truncate(top.get('label') or '(unlabelled)', 100)}",
              font_size=14, bold=True, color=TITLE_DARK)
        note = top.get("note")
        if note:
            _text(slide, x=0.5, y=ty+0.7, w=sw-1.0, h=0.45,
                  text=_truncate(note, 280), font_size=9.5, italic=True,
                  color=SLATE_MID, line_spacing=1.2)

    _add_brand_footer(slide, slide_label="Executive Summary")


def _add_whats_changed_slide(prs, assessment: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _rect(slide, x=0, y=0, w=sw, h=0.85, fill=NAVY)
    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.55,
          text="What's Changed: Deck vs Tracker", font_size=20,
          bold=True, color=WHITE)

    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.25,
          text="Original deck consensus % vs the baseline-corrected verdict from fresh evidence.",
          font_size=10, italic=True, color=SLATE_LIGHT)

    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = assessment.get("scenario_verdicts") or []

    # Column headers
    y = 1.4
    cols = [
        ("SCENARIO",   0.5,  4.4),
        ("DECK",       5.0,  0.7),
        ("LIVE",       5.75, 0.7),
        ("PLACEBO",    6.55, 0.85),
        ("NET",        7.5,  0.7),
        ("VERDICT",    8.25, 1.5),
    ]
    for label, x, w in cols:
        _text(slide, x=x, y=y, w=w, h=0.25, text=label, font_size=8,
              bold=True, color=SLATE_LIGHT)
    y += 0.3
    _rect(slide, x=0.5, y=y, w=sw-1.0, h=0.015, fill=RULE_GRAY)
    y += 0.1

    for v in verdicts:
        b = bc_per.get(str(v.get("scenario_idx"))) or {}
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
        consensus = deck_info.get("consensus_pct")
        live = b.get("live_rate")
        placebo = b.get("placebo_rate")
        net = b.get("net_rate")
        label = b.get("label") or v.get("verdict_label") or "—"

        _text(slide, x=0.5, y=y, w=4.4, h=0.4, text=_truncate(name, 78),
              font_size=10, bold=True, color=TITLE_DARK)
        _text(slide, x=5.0, y=y+0.05, w=0.7, h=0.3,
              text=f"{int(consensus)}%" if consensus is not None else "—",
              font_size=10, color=SLATE_MID)
        _text(slide, x=5.75, y=y+0.05, w=0.7, h=0.3,
              text=f"{live*100:.2f}%" if live is not None else "—",
              font_size=10, color=SLATE_MID)
        _text(slide, x=6.55, y=y+0.05, w=0.85, h=0.3,
              text=f"{placebo*100:.2f}%" if placebo is not None else "—",
              font_size=10, color=SLATE_MID)
        net_color = _baseline_color(label) if (net is not None and abs(net) > 0.001) else SLATE_LIGHT
        _text(slide, x=7.5, y=y+0.05, w=0.7, h=0.3,
              text=f"{net*100:+.2f}%" if net is not None else "—",
              font_size=10, bold=True, color=net_color)
        chip_w = 1.5
        _rect(slide, x=8.25, y=y, w=chip_w, h=0.36,
              fill=_baseline_color(label), rounded=True)
        _text(slide, x=8.25, y=y+0.07, w=chip_w, h=0.24, text=label,
              font_size=9, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        y += 0.5
        _rect(slide, x=0.5, y=y-0.05, w=sw-1.0, h=0.008, fill=COL_DIV)

    _text(slide, x=0.5, y=5.05, w=sw-1.0, h=0.22,
          text="Net rate = post-forecast support rate − symmetric pre-forecast support rate. See How to Read.",
          font_size=8, italic=True, color=SLATE_LIGHT)
    _add_brand_footer(slide, slide_label="What's Changed")


def _add_scenario_slide(prs, verdict: dict, baseline: Optional[dict]):
    """One slide per scenario in the canonical Wiley card layout:
    left-rail (horizon code + consensus + brand) and three right-side
    panels: Primary Signal, Decision Fork, Tracking."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}

    horizon = (verdict.get("horizon_type") or "h1")
    accent = _horizon_color(horizon)
    consensus = deck_info.get("consensus_pct")
    scenario_name = (deck_info.get("deck_scenario_name")
                     or verdict.get("scenario_title") or "—")

    _add_left_rail(slide, horizon=horizon, consensus_pct=consensus)

    # ── Title block ────────────────────────────────────────────────────
    # Split the title into ≤2 lines for the deck's stacked look.
    title_lines = _split_title(scenario_name, max_chars=34)
    _text(slide, x=1.9, y=0.1, w=7.9, h=0.4, text=title_lines[0],
          font_size=18, bold=True, color=TITLE_DARK)
    if len(title_lines) > 1:
        _text(slide, x=1.9, y=0.45, w=7.9, h=0.4, text=title_lines[1],
              font_size=18, bold=True, color=TITLE_DARK)

    _text(slide, x=1.9, y=0.85, w=7.9, h=0.2, text=_horizon_full_label(horizon),
          font_size=8.5, bold=True, color=SLATE_LIGHT)

    # Intro paragraph — short summary of the scenario context
    intro = deck_info.get("primary_signal") or verdict.get("scenario_title") or ""
    _text(slide, x=1.9, y=1.1, w=7.9, h=0.4, text=_truncate(intro, 240),
          font_size=9.5, color=SLATE_MID, line_spacing=1.2)

    # Minority view banner
    minority = deck_info.get("minority_view")
    if minority:
        _add_minority_banner(slide, x=1.9, y=1.5, w=7.9,
                             text=_truncate(minority, 220))
    panel_y = 2.1

    # ── Column 1: PRIMARY SIGNAL ──────────────────────────────────────
    _add_column_card(slide, x=1.9, y=panel_y, w=2.4, h=3.1, accent=TEAL)
    _text(slide, x=2.05, y=panel_y+0.18, w=2.1, h=0.28, text="PRIMARY SIGNAL",
          font_size=8, bold=True, color=TEAL)
    if consensus is not None:
        _rect(slide, x=2.05, y=panel_y+0.5, w=0.85, h=0.28, fill=PALE_TEAL,
              rounded=True)
        _text(slide, x=2.05, y=panel_y+0.53, w=0.85, h=0.22,
              text=f"{int(consensus)}% Consensus", font_size=7,
              bold=True, color=TEAL, align=PP_ALIGN.CENTER)
    primary = deck_info.get("primary_signal") or "—"
    _text(slide, x=2.05, y=panel_y+0.9, w=2.1, h=2.1, text=primary,
          font_size=9.5, bold=True, color=TITLE_DARK, line_spacing=1.25)

    # ── Column 2: DECISION FORK ───────────────────────────────────────
    _add_column_card(slide, x=4.5, y=panel_y, w=2.4, h=3.1, accent=NAVY)
    _text(slide, x=4.65, y=panel_y+0.18, w=2.1, h=0.28, text="DECISION FORK",
          font_size=8, bold=True, color=TITLE_DARK)
    fork = deck_info.get("decision_fork") or {}
    fav = fork.get("favorable")
    adv = fork.get("adverse")

    if fav:
        _rect(slide, x=4.65, y=panel_y+0.6, w=0.28, h=0.28, fill=PALE_GREEN,
              rounded=True)
        _text(slide, x=4.65, y=panel_y+0.6, w=0.28, h=0.28, text="✔",
              font_size=11, bold=True, color=EMERALD, align=PP_ALIGN.CENTER,
              anchor=MSO_ANCHOR.MIDDLE)
        _text(slide, x=5.0, y=panel_y+0.58, w=1.85, h=1.05,
              text=_truncate(fav, 200), font_size=8.5, color=SLATE_MID,
              line_spacing=1.2)
    if adv:
        _rect(slide, x=4.65, y=panel_y+1.85, w=2.1, h=0.012, fill=COL_DIV)
        _rect(slide, x=4.65, y=panel_y+1.95, w=0.28, h=0.28, fill=PALE_RED,
              rounded=True)
        _text(slide, x=4.65, y=panel_y+1.95, w=0.28, h=0.28, text="!",
              font_size=12, bold=True, color=CORAL, align=PP_ALIGN.CENTER,
              anchor=MSO_ANCHOR.MIDDLE)
        _text(slide, x=5.0, y=panel_y+1.93, w=1.85, h=1.05,
              text=_truncate(adv, 200), font_size=8.5, color=SLATE_MID,
              line_spacing=1.2)

    # ── Column 3: TRACKING (replaces deck's "Your Window") ────────────
    _add_column_card(slide, x=7.1, y=panel_y, w=2.65, h=3.1, accent=accent)
    _text(slide, x=7.25, y=panel_y+0.18, w=2.4, h=0.28, text="TRACKING",
          font_size=8, bold=True, color=accent)

    # Verdict chip — baseline-corrected if available, else raw
    if baseline:
        label = baseline.get("label") or verdict.get("verdict_label") or "—"
        chip_color = _baseline_color(label)
        sub_label = f"raw: {verdict.get('verdict_label') or '—'}"
    else:
        label = verdict.get("verdict_label") or "—"
        chip_color = _baseline_color(label)
        sub_label = ""

    _rect(slide, x=7.25, y=panel_y+0.5, w=2.4, h=0.36,
          fill=chip_color, rounded=True)
    _text(slide, x=7.25, y=panel_y+0.56, w=2.4, h=0.26,
          text=label, font_size=10, bold=True, color=WHITE,
          align=PP_ALIGN.CENTER)
    if sub_label:
        _text(slide, x=7.25, y=panel_y+0.88, w=2.4, h=0.2,
              text=sub_label, font_size=7, color=SLATE_LIGHT,
              align=PP_ALIGN.CENTER)

    # Baseline correction lines
    ty = panel_y + 1.15
    if baseline:
        live = baseline.get("live_rate", 0)
        placebo = baseline.get("placebo_rate", 0)
        net = baseline.get("net_rate", 0)
        _text(slide, x=7.25, y=ty, w=2.4, h=0.22,
              text=f"live   {live*100:.2f}%", font_size=9.5, color=SLATE_MID)
        _text(slide, x=7.25, y=ty+0.22, w=2.4, h=0.22,
              text=f"placebo   {placebo*100:.2f}%", font_size=9.5, color=SLATE_MID)
        _text(slide, x=7.25, y=ty+0.46, w=2.4, h=0.3,
              text=f"net   {net*100:+.2f}%", font_size=12, bold=True,
              color=chip_color)
        ty += 0.85

    # Supports / Contradicts / Neutral counts
    counts = [
        (verdict.get("supports") or 0, "supports", SUPPORT_COLOR),
        (verdict.get("contradicts") or 0, "contra", CONTRA_COLOR),
        (verdict.get("neutral") or 0, "neutral", NEUTRAL_COLOR),
    ]
    cx = 7.25
    cw = 0.78
    for value, label, color in counts:
        _text(slide, x=cx, y=ty, w=cw, h=0.3, text=str(value),
              font_size=14, bold=True, color=color, align=PP_ALIGN.CENTER)
        _text(slide, x=cx, y=ty+0.3, w=cw, h=0.2, text=label,
              font_size=7, color=SLATE_LIGHT, align=PP_ALIGN.CENTER)
        cx += cw + 0.04

    # Top supporting article — title only, italic rationale
    supports = (verdict.get("top_articles") or {}).get("supports") or []
    if supports:
        a = supports[0]
        title = a.get("title") or a.get("article_uri") or "(no title)"
        rationale = a.get("rationale") or ""
        ty2 = panel_y + 2.45
        _text(slide, x=7.25, y=ty2, w=2.4, h=0.55,
              text=_truncate(title, 90), font_size=8, bold=True,
              color=TITLE_DARK, line_spacing=1.1)

    # ── Verdict explanation strip (replaces source scenarios line) ────
    explanation = _verdict_explanation(verdict.get("verdict_label"), baseline)
    if explanation:
        _rect(slide, x=1.9, y=5.32, w=7.9, h=0.012, fill=RULE_GRAY)
        _text(slide, x=1.9, y=5.35, w=7.9, h=0.22,
              text="WHAT THIS MEANS  ·  " + _truncate(explanation, 220),
              font_size=7.5, bold=True, color=SLATE_LIGHT, line_spacing=1.1)


def _add_surprises_divider(prs, surprises: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _rect(slide, x=0, y=0, w=sw, h=5.62, fill=NAVY)
    _text(slide, x=0.5, y=0.4, w=4.0, h=0.3,
          text="AunooAI · FORECAST TRACKER", font_size=11,
          bold=True, color=GOLD)
    _text(slide, x=0.5, y=1.5, w=sw-1.0, h=1.0,
          text="Unanticipated Developments", font_size=32, bold=True,
          color=WHITE)
    body = (
        f"{len(surprises)} cluster{'s' if len(surprises) != 1 else ''} of articles "
        f"topical to this brief but unrelated to any deck scenario."
        if surprises else
        "No clusters of sufficient cohesion detected this window."
    )
    _text(slide, x=0.5, y=2.7, w=sw-1.0, h=0.7, text=body, font_size=14,
          italic=True, color=RULE_GRAY)
    if surprises:
        rank = "\n".join(
            f"  {s.get('size') or 0}×   {_truncate(s.get('label') or '(unlabelled)', 80)}"
            for s in sorted(surprises, key=lambda s: -(s.get("size") or 0))[:6]
        )
        _text(slide, x=0.5, y=3.5, w=sw-1.0, h=1.7, text=rank,
              font_size=11, color=WHITE, line_spacing=1.35)


def _add_surprise_cluster_slide(prs, sur: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Reuse left rail with no horizon (just brand + size chip)
    _rect(slide, x=0, y=0, w=1.6, h=5.62, fill=NAVY)
    _text(slide, x=0.0, y=0.9, w=1.6, h=0.3, text="SURPRISE",
          font_size=10, bold=True, color=GOLD, align=PP_ALIGN.CENTER)
    _rect(slide, x=0.4, y=1.3, w=0.8, h=0.015, fill=GOLD)
    size = sur.get("size") or 0
    _rect(slide, x=0.2, y=2.4, w=1.2, h=0.85, fill=GOLD, rounded=True)
    _text(slide, x=0.2, y=2.5, w=1.2, h=0.42, text=f"{size}×",
          font_size=26, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _text(slide, x=0.2, y=2.93, w=1.2, h=0.28, text="ARTICLES",
          font_size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _text(slide, x=0.0, y=5.32, w=1.6, h=0.22, text="AunooAI",
          font_size=8, color=SLATE_LIGHT, align=PP_ALIGN.CENTER)

    # Main area
    label = sur.get("label") or "(unlabelled cluster)"
    note = sur.get("note") or ""

    _text(slide, x=1.9, y=0.3, w=7.9, h=0.3, text="UNANTICIPATED THEME",
          font_size=9, bold=True, color=GOLD)
    _text(slide, x=1.9, y=0.65, w=7.9, h=0.95, text=label, font_size=20,
          bold=True, color=TITLE_DARK, line_spacing=1.1)

    y = 1.85
    if note:
        _text(slide, x=1.9, y=y, w=7.9, h=0.25, text="WHY IT MATTERS",
              font_size=8, bold=True, color=SLATE_LIGHT)
        _text(slide, x=1.9, y=y+0.28, w=7.9, h=1.1, text=note,
              font_size=10, italic=True, color=SLATE_MID, line_spacing=1.25)
        y += 1.55

    samples = sur.get("sample_articles") or []
    if samples:
        _text(slide, x=1.9, y=y, w=7.9, h=0.25,
              text=f"SAMPLE ARTICLES ({min(len(samples), 5)} of {size})",
              font_size=8, bold=True, color=SLATE_LIGHT)
        y2 = y + 0.32
        for art in samples[:5]:
            title = art.get("title") or art.get("uri") or "(no title)"
            date = art.get("date")
            _rect(slide, x=1.9, y=y2+0.04, w=0.08, h=0.3, fill=GOLD)
            line = f"{date}   ·   {_truncate(title, 110)}" if date else _truncate(title, 130)
            _text(slide, x=2.1, y=y2, w=7.7, h=0.35, text=line,
                  font_size=10, color=TITLE_DARK)
            y2 += 0.42


# ── Public ────────────────────────────────────────────────────────────────

def build_assessment_pptx(assessment: dict, forecast_run: Optional[dict] = None) -> bytes:
    prs = Presentation()
    prs.slide_width = Inches(10.0)
    prs.slide_height = Inches(5.625)  # 16:9 matching the Wiley deck (10×5.62)

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

    surprises = assessment.get("surprises") or []
    _add_surprises_divider(prs, surprises)
    for sur in sorted(surprises, key=lambda s: -(s.get("size") or 0)):
        _add_surprise_cluster_slide(prs, sur)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


# ── Helpers — text shaping + interpretation ───────────────────────────────

def _verdict_explanation(verdict_label: Optional[str], baseline: Optional[dict] = None) -> str:
    if baseline:
        label = baseline.get("label") or ""
        if "Above" in label:
            return (
                "Genuine new signal. The per-article support rate has accelerated since "
                "the forecast was published — the trajectory is materializing more "
                "strongly than the pre-forecast baseline suggested."
            )
        if "Below" in label:
            return (
                "The deck appears to have called a peak signal. Pre-forecast articles "
                "showed a higher support rate than post-forecast ones, so the story "
                "was hotter at deck-authoring time than it is now. Not 'wrong' — "
                "rather 'trend was already in motion and has since cooled'."
            )
        if "At" in label:
            return (
                "The trend was already visible at deck-authoring time. Per-article "
                "signal density is essentially unchanged in the post-forecast window."
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


def _split_title(s: str, max_chars: int = 34) -> List[str]:
    """Split a title into ≤2 lines at a word boundary close to max_chars."""
    s = (s or "").strip()
    if len(s) <= max_chars:
        return [s.upper()]
    # Find the rightmost space before max_chars
    cut = s.rfind(" ", 0, max_chars + 1)
    if cut <= 0:
        cut = max_chars
    return [s[:cut].strip().upper(), s[cut:].strip().upper()]


def _truncate(s: Optional[str], n: int) -> str:
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


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n) if n is not None else "—"
