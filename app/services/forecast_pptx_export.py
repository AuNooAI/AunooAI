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
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# Brand asset paths (resolved at slide-build time so the deck embeds the
# actual Aunoo brandmark instead of plain text). Fallback to the older
# wordmark if the new mark isn't present (older tenants).
LOGO_PATH = Path("static/aunoo_logo.png")
LOGO_FALLBACK = Path("static/aunooai.png")

# Wiley brand backgrounds extracted from the Feb 2026 Wiley Horizons deck —
# used as full-bleed underlays on cover / exec summary / per-topic slides so
# the recurring bundle reads as a strategic intelligence briefing rather
# than a tracker dashboard. See ``static/wiley_brand/``.
WILEY_BG_DIR = Path("static/wiley_brand")
WILEY_BG_COVER   = WILEY_BG_DIR / "cover_bg.png"          # candlestick gradient
WILEY_BG_SOFT    = WILEY_BG_DIR / "content_bg_soft.png"   # soft teal gradient
WILEY_BG_BOKEH   = WILEY_BG_DIR / "content_bg_bokeh.png"  # teal bokeh
WILEY_BG_SECTION = WILEY_BG_DIR / "section_bg.png"        # section divider


# ── Aunoo brand palette (sourced from ui/src/styles/globals.css + aunoo-theme.css)

# Primary pink scale
PINK         = RGBColor(0xEC, 0x48, 0x99)  # Primary brand pink (Radix pink-8)
PINK_DARK    = RGBColor(0xE9, 0x3D, 0x82)  # pink-9
PINK_DEEP    = RGBColor(0xD6, 0x34, 0x6C)  # pink-10
PINK_DEEPEST = RGBColor(0x8B, 0x1A, 0x42)  # pink-12

PALE_PINK_1  = RGBColor(0xFE, 0xF6, 0xFB)  # pink-1 (lightest)
PALE_PINK_2  = RGBColor(0xFE, 0xE9, 0xF5)  # pink-2
PALE_PINK_3  = RGBColor(0xFD, 0xD8, 0xED)  # pink-3

# Neutral / slate
SLATE_DARK   = RGBColor(0x11, 0x18, 0x27)  # slate-12, page titles
SLATE_BLACK  = RGBColor(0x21, 0x25, 0x29)  # slate-11, body text dark
SLATE_MID    = RGBColor(0x49, 0x50, 0x57)  # slate-9, body text
SLATE_BODY   = RGBColor(0x34, 0x3A, 0x40)  # slate-10
SLATE_LIGHT  = RGBColor(0x86, 0x8E, 0x96)  # slate-8, labels
SLATE_PALE   = RGBColor(0xAD, 0xB5, 0xBD)  # slate-7
RULE_GRAY    = RGBColor(0xDE, 0xE2, 0xE6)  # slate-5
COL_DIV      = RGBColor(0xE9, 0xEC, 0xEF)  # slate-4
SLATE_BG     = RGBColor(0xF8, 0xF9, 0xFA)  # slate-2
WHITE        = RGBColor(0xFF, 0xFF, 0xFF)

# Semantic colors (green/red still semantic, but Aunoo-flavored hues)
GREEN        = RGBColor(0x10, 0xB9, 0x81)  # green-9, success/above-baseline
GREEN_DEEP   = RGBColor(0x05, 0x96, 0x69)  # green-10
RED          = RGBColor(0xEF, 0x44, 0x44)  # red-5 -> red-7
RED_DEEP     = RGBColor(0xDC, 0x26, 0x26)
AMBER        = RGBColor(0xF5, 0x9E, 0x0B)  # amber-7
AMBER_DEEP   = RGBColor(0xD9, 0x77, 0x06)

# Soft fills (chip backgrounds)
PALE_GREEN   = RGBColor(0xDC, 0xFC, 0xE7)  # green-2
PALE_RED     = RGBColor(0xFE, 0xE2, 0xE2)  # red-2
PALE_AMBER   = RGBColor(0xFE, 0xF3, 0xC7)

NAVY         = SLATE_DARK     # Backwards-compat aliases used below
TITLE_DARK   = SLATE_BLACK
CARD_BG      = WHITE
BODY_FONT    = "Calibri"

# Aunoo brand palette for the recurring bundle.
# The constants below keep their original ``WILEY_*`` names so every slide
# builder stays untouched — only the *values* swap from teal/navy to the
# Aunoo black-and-pink identity. Clean white slides, dark slate near-black,
# pink accents — no atmospheric backgrounds.
WILEY_TEAL    = RGBColor(0xD6, 0x34, 0x6C)  # primary accent — Aunoo pink-deep
WILEY_TEAL_LT = RGBColor(0xFE, 0xE9, 0xF5)  # light pink tint (header subtitles on dark)
WILEY_NAVY    = RGBColor(0x11, 0x18, 0x27)  # near-black slate (Aunoo dark)
WILEY_BLUE    = RGBColor(0x8B, 0x1A, 0x42)  # secondary accent — Aunoo pink-deepest
WILEY_CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)  # clean white card fill
WILEY_BODY    = RGBColor(0x21, 0x25, 0x29)  # dark body text
WILEY_MUTED   = RGBColor(0x49, 0x50, 0x57)  # secondary body text

# Forecast Tracker — semantic colors for baseline labels.
# Internal labels (persisted in DB) are kept in this map for backwards
# compatibility; ``_customer_label()`` translates them to the customer-
# facing terms ("Strengthening", "Stable", "Cooling") at slide-build time.
BASELINE_COLORS = {
    "Above baseline": GREEN_DEEP,
    "At baseline":    SLATE_PALE,
    "Below baseline": RED_DEEP,
    # Customer-facing aliases — same colors, present so a slide rendered
    # off already-translated labels still resolves.
    "Strengthening":  GREEN_DEEP,
    "Stable":         SLATE_PALE,
    "Cooling":        RED_DEEP,
}

# Internal label → customer-friendly label.
# "Above baseline" etc. is methodology jargon (placebo correction). The
# customer wants to know directionally what the trend is doing.
CUSTOMER_LABEL = {
    "Above baseline": "Strengthening",
    "At baseline":    "Stable",
    "Below baseline": "Cooling",
}


def _customer_label(label: Optional[str]) -> str:
    """Translate an internal baseline/verdict label into the customer-facing
    term shown on slides. Unmapped labels pass through unchanged (so raw
    verdict labels like ``Accelerating`` / ``On-track`` still render)."""
    if not label:
        return "—"
    return CUSTOMER_LABEL.get(label, label)

# Per-component
SUPPORT_COLOR = GREEN_DEEP
CONTRA_COLOR  = RED_DEEP
NEUTRAL_COLOR = SLATE_PALE


def _horizon_color(h: Optional[str]) -> RGBColor:
    # All horizons use the brand pink — the H-code itself communicates the
    # horizon, no need to color-code per horizon (and would conflict with the
    # pink brand identity).
    return PINK


# Aliases — the rest of the file still uses these older names. Mapping
# them here keeps slide builders untouched while migrating the palette.
TEAL         = PINK         # primary accent → brand pink
GOLD         = AMBER_DEEP   # secondary accent (surprises, minority view)
ORANGE       = AMBER
CORAL        = RED          # below-baseline / contradicting
EMERALD      = GREEN_DEEP   # above-baseline / favorable
PALE_TEAL    = PALE_PINK_2
PALE_GOLD    = PALE_AMBER
PALE_CORAL   = PALE_RED
MINORITY_TXT = PINK_DEEPEST


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

    # AunooAI brand mark (logo image if available, fallback to wordmark text)
    _add_brand_mark(slide, x=0.15, y=5.15, w=1.3, h=0.4)


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


def _add_bg_image(slide, image_path: Path, *, overlay: Optional[RGBColor] = None, opacity: float = 0.0):
    """Lay down a clean Aunoo-style background.

    Originally this loaded a Wiley-extracted atmospheric image (teal bokeh,
    candlestick gradient) and overlaid panels on top. The Aunoo brand is
    cleaner — solid white with strong black + pink — so this is now a
    no-op for the standard "soft" background and a solid white fill for
    everything else. The slide builders' panels (white cards on top of bg,
    navy and pink header strips) already look right on a white base.
    """
    # Clean white base. Cover + section dividers handle their own dark
    # background explicitly via _rect() with WILEY_NAVY fills.
    name = image_path.name if hasattr(image_path, "name") else ""
    if "cover" in name:
        # Cover gets a solid Aunoo-black backdrop, accent pink rule lives
        # in the cover builder itself.
        _rect(slide, x=0, y=0, w=10.0, h=5.625, fill=WILEY_NAVY)
    else:
        _rect(slide, x=0, y=0, w=10.0, h=5.625, fill=WHITE)
    return True


def _add_brand_mark(slide, *, x, y, w, h):
    """Embed the Aunoo brandmark PNG. Square mark (au letterform with pink
    dot). Falls back to the older wordmark, then to plain text, depending
    on what's available in the tenant's static dir."""
    src = LOGO_PATH if LOGO_PATH.exists() else (LOGO_FALLBACK if LOGO_FALLBACK.exists() else None)
    if src is not None:
        # The new square mark needs a height-locked embed so it doesn't
        # stretch into the older wordmark's letterbox proportions.
        if src == LOGO_PATH:
            slide.shapes.add_picture(str(src), Inches(x), Inches(y),
                                     height=Inches(h))
        else:
            slide.shapes.add_picture(str(src), Inches(x), Inches(y),
                                     width=Inches(w))
    else:
        _text(slide, x=x, y=y+0.1, w=w, h=h-0.1, text="AUNOO",
              font_size=10, bold=True, color=PINK, align=PP_ALIGN.CENTER)


def _add_brand_footer(slide, *, slide_label: str = ""):
    """Faint brand mark + slide label in the footer of non-scenario slides
    (scenario slides have the brand mark in their left rail)."""
    _add_brand_mark(slide, x=0.5, y=5.22, w=0.9, h=0.3)
    _text(slide, x=1.5, y=5.32, w=4.0, h=0.2, text="Forecast Tracker",
          font_size=8, bold=True, color=SLATE_LIGHT)
    if slide_label:
        _text(slide, x=5.5, y=5.32, w=4.0, h=0.2, text=slide_label,
              font_size=8, color=SLATE_LIGHT, align=PP_ALIGN.RIGHT)


# ── Slide builders ────────────────────────────────────────────────────────

def _add_cover_slide(prs, assessment: dict, forecast_run: dict, *, updates_diff: Optional[dict] = None):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Light cover with pink accent — matches the app's pink-on-white aesthetic.
    _rect(slide, x=0, y=0, w=sw, h=5.62, fill=WHITE)
    _rect(slide, x=0, y=0, w=sw, h=0.18, fill=PINK)  # top pink rule

    # Brand logo top-left
    _add_brand_mark(slide, x=0.5, y=0.5, w=1.8, h=0.55)

    # Product label
    label = "FORECAST TRACKER · UPDATES" if updates_diff else "FORECAST TRACKER"
    _text(slide, x=0.5, y=1.15, w=6.0, h=0.3, text=label,
          font_size=11, bold=True, color=PINK_DEEP)

    # Topic
    topic = assessment.get("topic") or "—"
    _text(slide, x=0.5, y=1.85, w=sw-1.0, h=0.9, text=topic, font_size=30,
          bold=True, color=SLATE_DARK)

    summary = assessment.get("summary") or {}
    forecast_at = summary.get("forecast_generated_at") or forecast_run.get("created_at")
    assessed_at = summary.get("assessed_at") or assessment.get("assessed_at")
    window_weeks = summary.get("window_weeks")

    if updates_diff:
        line2 = (
            f"Update since {_short_date(updates_diff.get('prior_assessed_at'))} · "
            f"{len(updates_diff.get('new_uris') or [])} new articles · "
            f"{len(updates_diff.get('verdict_flips') or {})} status changes · "
            f"{len(updates_diff.get('new_surprise_labels') or [])} new themes"
        )
    else:
        line2 = (
            f"Tracking the forecast published "
            f"{_short_date(forecast_at)} against evidence through {_short_date(assessed_at)}"
        )
    _text(slide, x=0.5, y=2.85, w=sw-1.0, h=0.5, text=line2,
          font_size=13, color=SLATE_MID)

    # Headline stats row — customer-friendly, no methodology jargon
    bc = summary.get("baseline_correction") or {}
    articles_in_window = bc.get("live_pool") or summary.get("evidence_pool") or assessment.get("evidence_count")
    n_scenarios = len(assessment.get("scenario_verdicts") or [])
    n_surprises = len(assessment.get("surprises") or [])

    pairs = [
        ("Scenarios tracked", str(n_scenarios)),
        ("Articles analysed", _fmt_int(articles_in_window)),
        ("Tracking window", f"{window_weeks} weeks" if window_weeks else "Full"),
        ("Emerging themes", str(n_surprises)),
    ]
    cx = 0.5
    cell_w = (sw - 1.0) / len(pairs)
    for label, value in pairs:
        _text(slide, x=cx, y=3.8, w=cell_w-0.1, h=0.28, text=label.upper(),
              font_size=8, bold=True, color=PINK_DEEP)
        _text(slide, x=cx, y=4.08, w=cell_w-0.1, h=0.6, text=value,
              font_size=22, bold=True, color=SLATE_DARK)
        cx += cell_w

    _rect(slide, x=0.5, y=5.05, w=sw-1.0, h=0.012, fill=RULE_GRAY)
    _text(slide, x=0.5, y=5.18, w=sw-1.0, h=0.22,
          text="AunooAI · aunoo.ai",
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
        "Each scenario in the original forecast is continuously tracked against "
        "fresh evidence. We score how strongly current developments confirm or "
        "contradict the predicted trajectory, then compare against the picture "
        "that was already visible before the forecast was published — so the "
        "status reflects what's genuinely new, not pre-existing momentum."
    )
    _text(slide, x=0.5, y=1.05, w=sw-1.0, h=1.2, text=intro, font_size=10,
          color=SLATE_MID, line_spacing=1.3)

    rows = [
        ("Strengthening", EMERALD,
         "The trajectory is materialising more strongly than it was before the forecast was published. Genuine new confirmation."),
        ("Stable", SLATE_LIGHT,
         "The trend was already visible when the forecast was made; recent evidence holds it on course but does not amplify it."),
        ("Cooling", CORAL,
         "The trend was hotter when the forecast was made than it is now. The story isn't wrong — it's already crested. Worth re-pricing the urgency."),
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
        "Emerging themes at the end of the deck are clusters of developments that "
        "none of the original scenarios anticipated — story lines worth tracking "
        "alongside the existing ones."
    )
    _text(slide, x=0.5, y=4.6, w=sw-1.0, h=0.7, text=footer, font_size=9,
          italic=True, color=SLATE_LIGHT, line_spacing=1.2)

    _add_brand_footer(slide, slide_label="How to read this")


def _add_exec_summary_slide(prs, assessment: dict, headline: dict, *, updates_diff: Optional[dict] = None):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _rect(slide, x=0, y=0, w=sw, h=0.85, fill=PINK)
    title_text = "What's Changed" if updates_diff else "Executive Summary"
    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.55, text=title_text,
          font_size=20, bold=True, color=WHITE)

    summary = assessment.get("summary") or {}
    bc = summary.get("baseline_correction") or {}
    bc_per = bc.get("per_scenario") or {}
    verdicts = assessment.get("scenario_verdicts") or []
    n = len(verdicts)

    if updates_diff:
        # Updates deck: replace exec narrative with a concrete delta panel
        prior_at = _short_date(updates_diff.get("prior_assessed_at"))
        flips = updates_diff.get("verdict_flips") or {}
        new_uri_count = len(updates_diff.get("new_uris") or [])
        new_clusters = updates_diff.get("new_surprise_labels") or set()

        _rect(slide, x=0.5, y=1.0, w=sw-1.0, h=1.7, fill=PALE_PINK_1)
        _rect(slide, x=0.5, y=1.0, w=0.08, h=1.7, fill=PINK)
        _text(slide, x=0.7, y=1.06, w=sw-1.4, h=0.25,
              text=f"DELTA SINCE {prior_at.upper()}",
              font_size=8.5, bold=True, color=PINK_DEEP)

        lines = [
            f"  •  {new_uri_count} new articles classified",
            f"  •  {len(flips)} scenarios changed verdict label",
            f"  •  {len(new_clusters)} new unanticipated clusters emerged",
        ]
        verdict_idx_to_title = {
            str(v.get("scenario_idx")): (
                (v.get("top_articles") or {}).get("deck_info", {}).get("deck_scenario_name")
                or v.get("scenario_title")
                or "—"
            )
            for v in verdicts
        }
        if flips:
            lines.append("")
            lines.append("  Status changes:")
            for key, (prior_l, current_l) in list(flips.items())[:6]:
                title = verdict_idx_to_title.get(key, key)
                lines.append(f"     {_truncate(title, 50)} : {_customer_label(prior_l)} → {_customer_label(current_l)}")

        _text(slide, x=0.7, y=1.32, w=sw-1.4, h=1.35,
              text="\n".join(lines), font_size=10.5, color=SLATE_BLACK,
              line_spacing=1.25)
        _add_brand_footer(slide, slide_label="What's Changed")
        return

    # LLM-synthesised narrative (if available) — the meatiest content on the
    # slide. Goes right under the heading so readers see it first.
    exec_narrative = (summary.get("exec_narrative") or "").strip()
    if exec_narrative:
        _rect(slide, x=0.5, y=1.0, w=sw-1.0, h=1.55,
              fill=PALE_PINK_1)
        _rect(slide, x=0.5, y=1.0, w=0.08, h=1.55, fill=PINK)
        _text(slide, x=0.7, y=1.06, w=sw-1.4, h=0.25,
              text="WHAT THE BACK-TEST FOUND", font_size=8.5,
              bold=True, color=PINK_DEEP)
        _text(slide, x=0.7, y=1.32, w=sw-1.4, h=1.2,
              text=exec_narrative, font_size=10.5, color=SLATE_BLACK,
              line_spacing=1.3)
        # Distribution chips push down to make room
        y_dist = 2.75
    else:
        y_dist = 1.05

    # Status distribution chips — translates internal labels to customer terms
    if bc_per:
        labels = [_customer_label(v.get("label")) for v in bc_per.values()]
        heading = "SCENARIO STATUS"
    else:
        labels = [v.get("verdict_label") for v in verdicts]
        heading = "SCENARIO STATUS"
    counts = {x: labels.count(x) for x in set(labels) if x}

    _text(slide, x=0.5, y=y_dist, w=sw-1.0, h=0.25, text=heading, font_size=9,
          bold=True, color=PINK_DEEP)
    cx = 0.5
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        color = _baseline_color(label)
        chip_w = 2.0
        _rect(slide, x=cx, y=y_dist+0.28, w=chip_w, h=0.5, fill=color, rounded=True)
        _text(slide, x=cx, y=y_dist+0.32, w=chip_w, h=0.22, text=label or "—",
              font_size=10, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _text(slide, x=cx, y=y_dist+0.54, w=chip_w, h=0.22,
              text=f"{count} of {n} scenarios", font_size=8.5,
              color=WHITE, align=PP_ALIGN.CENTER)
        cx += chip_w + 0.12

    # If the LLM narrative covers it, skip the headline panel (redundant)
    show_headline = not exec_narrative

    # Headline finding panel
    y0 = y_dist + 1.05
    if headline and show_headline:
        v = headline["verdict"]
        b = headline["baseline"]
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        label = _customer_label(b.get("label"))
        net = b.get("net_rate") or 0
        consensus = deck_info.get("consensus_pct")

        _text(slide, x=0.5, y=y0, w=sw-1.0, h=0.28, text="HEADLINE FINDING",
              font_size=9, bold=True, color=TEAL)
        _text(slide, x=0.5, y=y0+0.28, w=sw-2.5, h=0.5, text=name or "—",
              font_size=16, bold=True, color=TITLE_DARK)
        # Status chip on the right (customer-friendly label)
        chip_w = 1.85
        chip_x = sw - chip_w - 0.5
        _rect(slide, x=chip_x, y=y0+0.28, w=chip_w, h=0.5,
              fill=_baseline_color(b.get("label")), rounded=True)
        _text(slide, x=chip_x, y=y0+0.38, w=chip_w, h=0.32, text=label,
              font_size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

        consensus_s = f"{consensus}% original consensus" if consensus is not None else ""
        net_s = f"{net*100:+.2f}% confirmation strength vs. pre-forecast"
        stats = f"{consensus_s}   ·   {net_s}" if consensus_s else net_s
        _text(slide, x=0.5, y=y0+0.95, w=sw-1.0, h=0.3, text=stats,
              font_size=10, color=SLATE_MID)
        expl = _verdict_explanation(v.get("verdict_label"), b)
        _text(slide, x=0.5, y=y0+1.3, w=sw-1.0, h=0.95, text=expl,
              font_size=10, italic=True, color=SLATE_MID, line_spacing=1.25)

    # Dominant emerging theme — skip when narrative is present (it covers it)
    surprises = assessment.get("surprises") or []
    if surprises and not exec_narrative:
        top = max(surprises, key=lambda s: s.get("size") or 0)
        ty = 4.3
        _text(slide, x=0.5, y=ty, w=sw-1.0, h=0.28,
              text="DOMINANT EMERGING THEME", font_size=9, bold=True,
              color=AMBER_DEEP)
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
          text="Original consensus vs. current status", font_size=20,
          bold=True, color=WHITE)

    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.25,
          text="How each scenario from the original forecast is tracking against fresh evidence.",
          font_size=10, italic=True, color=SLATE_LIGHT)

    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = assessment.get("scenario_verdicts") or []

    # Column headers — customer-friendly, no methodology jargon
    y = 1.4
    cols = [
        ("SCENARIO",            0.5,  5.4),
        ("ORIGINAL CONSENSUS",  6.0,  1.5),
        ("CONFIRMATION Δ",      7.55, 1.05),
        ("STATUS",              8.65, 1.1),
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
        net = b.get("net_rate")
        internal_label = b.get("label") or v.get("verdict_label") or "—"
        label = _customer_label(internal_label)

        _text(slide, x=0.5, y=y, w=5.4, h=0.4, text=_truncate(name, 96),
              font_size=10, bold=True, color=TITLE_DARK)
        _text(slide, x=6.0, y=y+0.05, w=1.5, h=0.3,
              text=f"{int(consensus)}%" if consensus is not None else "—",
              font_size=11, color=SLATE_MID, align=PP_ALIGN.CENTER)
        net_color = _baseline_color(internal_label) if (net is not None and abs(net) > 0.001) else SLATE_LIGHT
        _text(slide, x=7.55, y=y+0.05, w=1.05, h=0.3,
              text=f"{net*100:+.2f}%" if net is not None else "—",
              font_size=11, bold=True, color=net_color, align=PP_ALIGN.CENTER)
        chip_w = 1.1
        _rect(slide, x=8.65, y=y, w=chip_w, h=0.36,
              fill=_baseline_color(internal_label), rounded=True)
        _text(slide, x=8.65, y=y+0.07, w=chip_w, h=0.24, text=label,
              font_size=9, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        y += 0.5
        _rect(slide, x=0.5, y=y-0.05, w=sw-1.0, h=0.008, fill=COL_DIV)

    _text(slide, x=0.5, y=5.05, w=sw-1.0, h=0.22,
          text="Confirmation Δ shows how much fresh evidence strengthens (+) or cools (−) the trajectory beyond what was already visible when the forecast was published.",
          font_size=8, italic=True, color=SLATE_LIGHT)
    _add_brand_footer(slide, slide_label="Current status")


def _add_scenario_slide(prs, verdict: dict, baseline: Optional[dict]):
    """One slide per scenario, restructured to put narrative + dated
    developments front-and-center (the deck context — primary signal,
    minority view — compresses to a small strip up top)."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}

    horizon = (verdict.get("horizon_type") or "h1")
    consensus = deck_info.get("consensus_pct")
    scenario_name = (deck_info.get("deck_scenario_name")
                     or verdict.get("scenario_title") or "—")

    _add_left_rail(slide, horizon=horizon, consensus_pct=consensus)

    # ── Title block ───────────────────────────────────────────────────
    title_lines = _split_title(scenario_name, max_chars=38)
    _text(slide, x=1.9, y=0.12, w=7.9, h=0.42, text=title_lines[0],
          font_size=17, bold=True, color=SLATE_DARK)
    if len(title_lines) > 1:
        _text(slide, x=1.9, y=0.5, w=7.9, h=0.42, text=title_lines[1],
              font_size=17, bold=True, color=SLATE_DARK)

    _text(slide, x=1.9, y=0.93, w=7.9, h=0.2, text=_horizon_full_label(horizon),
          font_size=8.5, bold=True, color=SLATE_LIGHT)

    # ── Original forecast (compressed) — single line from deck primary signal
    primary = deck_info.get("primary_signal") or ""
    if primary:
        _text(slide, x=1.9, y=1.15, w=7.9, h=0.45, text=primary,
              font_size=9, italic=True, color=SLATE_MID, line_spacing=1.25)

    # ── Tracking strip (full-width horizontal) ────────────────────────
    track_y = 1.7
    _rect(slide, x=1.9, y=track_y, w=7.9, h=0.6, fill=SLATE_BG)
    _rect(slide, x=1.9, y=track_y, w=0.08, h=0.6, fill=PINK)

    # Status chip (left of strip) — customer-facing label
    if baseline:
        internal_label = baseline.get("label") or verdict.get("verdict_label") or "—"
    else:
        internal_label = verdict.get("verdict_label") or "—"
    label = _customer_label(internal_label)
    chip_color = _baseline_color(internal_label)
    _rect(slide, x=2.05, y=track_y+0.1, w=1.7, h=0.4,
          fill=chip_color, rounded=True)
    _text(slide, x=2.05, y=track_y+0.15, w=1.7, h=0.3, text=label,
          font_size=10, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    # Inline metrics across the strip — drop placebo/net jargon, just show
    # confirmation strength + confirming/contradicting article counts
    metric_x = 4.0
    if baseline and baseline.get("net_rate") is not None:
        net = baseline.get("net_rate") or 0
        cells = [
            ("CONFIRMATION Δ", f"{net*100:+.2f}%", chip_color),
        ]
    else:
        cells = []
    cells += [
        ("CONFIRMING", str(verdict.get("supports") or 0), SUPPORT_COLOR),
        ("CONTRADICTING", str(verdict.get("contradicts") or 0), CONTRA_COLOR),
    ]
    cell_w = (sw - 0.5 - metric_x) / max(len(cells), 1)
    for label_, val, color in cells:
        _text(slide, x=metric_x, y=track_y+0.08, w=cell_w-0.05, h=0.2,
              text=label_, font_size=7, bold=True, color=SLATE_LIGHT)
        _text(slide, x=metric_x, y=track_y+0.25, w=cell_w-0.05, h=0.32,
              text=val, font_size=14, bold=True, color=color)
        metric_x += cell_w

    # ── DEVELOPMENTS narrative ────────────────────────────────────────
    nar_y = 2.45
    _text(slide, x=1.9, y=nar_y, w=7.9, h=0.25,
          text="DEVELOPMENTS SINCE FORECAST", font_size=9, bold=True,
          color=PINK_DEEP)

    narrative = (verdict.get("summary_md") or "").strip()
    supports_count = verdict.get("supports") or 0
    contradicts_count = verdict.get("contradicts") or 0
    if narrative:
        _text(slide, x=1.9, y=nar_y+0.28, w=7.9, h=1.1, text=narrative,
              font_size=10, color=SLATE_BLACK, line_spacing=1.3)
        dev_y = nar_y + 1.45
    elif supports_count == 0 and contradicts_count == 0:
        # No articles to ground a narrative in — be honest about it.
        _text(slide, x=1.9, y=nar_y+0.28, w=7.9, h=0.5,
              text="No confirming or contradicting articles attributed to this scenario "
                   "in the tracking window. Either fresh coverage is sparse or topical "
                   "fit is below our confidence threshold.",
              font_size=9, italic=True, color=SLATE_LIGHT, line_spacing=1.25)
        dev_y = nar_y + 0.85
    else:
        _text(slide, x=1.9, y=nar_y+0.28, w=7.9, h=0.4,
              text="(Narrative will be generated on first PPTX export.)",
              font_size=9, italic=True, color=SLATE_LIGHT)
        dev_y = nar_y + 0.7

    # ── Recent developments — dated articles ──────────────────────────
    supports = (verdict.get("top_articles") or {}).get("supports") or []
    contras = (verdict.get("top_articles") or {}).get("contradicts") or []

    _text(slide, x=1.9, y=dev_y, w=7.9, h=0.22,
          text=f"RECENT ARTICLES (top {min(len(supports)+len(contras), 4)} of {len(supports)} supporting, {len(contras)} contradicting)",
          font_size=8, bold=True, color=SLATE_LIGHT)
    item_y = dev_y + 0.3
    items: List[tuple] = [(a, "support") for a in supports[:3]] + [(a, "contra") for a in contras[:1]]
    for art, kind in items[:4]:
        title = art.get("title") or art.get("article_uri") or "(no title)"
        date = art.get("article_date") or ""
        rationale = art.get("rationale") or ""
        color = SUPPORT_COLOR if kind == "support" else CONTRA_COLOR
        _rect(slide, x=1.9, y=item_y+0.04, w=0.07, h=0.32, fill=color)
        date_str = date[:10] if date else ""
        head = f"{date_str}   {_truncate(title, 90)}" if date_str else _truncate(title, 100)
        _text(slide, x=2.05, y=item_y, w=sw-2.55, h=0.22, text=head,
              font_size=9, bold=True, color=SLATE_BLACK)
        if rationale:
            _text(slide, x=2.05, y=item_y+0.2, w=sw-2.55, h=0.2,
                  text=_truncate(rationale, 150), font_size=8,
                  italic=True, color=SLATE_MID)
        item_y += 0.46

    # ── Verdict explanation strip (footer) ────────────────────────────
    explanation = _verdict_explanation(verdict.get("verdict_label"), baseline)
    if explanation:
        _rect(slide, x=1.9, y=5.32, w=7.9, h=0.012, fill=RULE_GRAY)
        _text(slide, x=1.9, y=5.35, w=7.9, h=0.22,
              text="WHAT THIS MEANS  ·  " + _truncate(explanation, 200),
              font_size=7.5, bold=True, color=SLATE_LIGHT, line_spacing=1.1)


def _add_surprises_divider(prs, surprises: list):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _rect(slide, x=0, y=0, w=sw, h=5.62, fill=WHITE)
    _rect(slide, x=0, y=0, w=sw, h=0.18, fill=PINK)
    _add_brand_mark(slide, x=0.5, y=0.5, w=1.8, h=0.55)
    _text(slide, x=0.5, y=1.15, w=4.0, h=0.3,
          text="EMERGING THEMES", font_size=11,
          bold=True, color=PINK_DEEP)
    _text(slide, x=0.5, y=1.85, w=sw-1.0, h=1.0,
          text="Emerging Themes", font_size=30, bold=True,
          color=SLATE_DARK)
    body = (
        f"{len(surprises)} {'theme' if len(surprises) == 1 else 'themes'} of recent coverage "
        f"that none of the original scenarios anticipated — story lines worth tracking."
        if surprises else
        "No emerging themes of sufficient coherence in this window."
    )
    _text(slide, x=0.5, y=2.85, w=sw-1.0, h=0.5, text=body, font_size=13,
          color=SLATE_MID)
    if surprises:
        rank = "\n".join(
            f"  {s.get('size') or 0} articles   ·   {_truncate(s.get('label') or '(unlabelled)', 80)}"
            for s in sorted(surprises, key=lambda s: -(s.get("size") or 0))[:6]
        )
        _text(slide, x=0.5, y=3.5, w=sw-1.0, h=1.5, text=rank,
              font_size=11, color=SLATE_BLACK, line_spacing=1.35)
    _add_brand_footer(slide, slide_label="Emerging Themes")


def _add_surprise_cluster_slide(prs, sur: dict):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Reuse left rail with no horizon (just brand + size chip)
    _rect(slide, x=0, y=0, w=1.6, h=5.62, fill=NAVY)
    _text(slide, x=0.0, y=0.9, w=1.6, h=0.3, text="EMERGING",
          font_size=10, bold=True, color=GOLD, align=PP_ALIGN.CENTER)
    _rect(slide, x=0.4, y=1.3, w=0.8, h=0.015, fill=GOLD)
    size = sur.get("size") or 0
    _rect(slide, x=0.2, y=2.4, w=1.2, h=0.85, fill=GOLD, rounded=True)
    _text(slide, x=0.2, y=2.5, w=1.2, h=0.42, text=f"{size}",
          font_size=26, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _text(slide, x=0.2, y=2.93, w=1.2, h=0.28, text="ARTICLES",
          font_size=8, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _text(slide, x=0.0, y=5.32, w=1.6, h=0.22, text="AunooAI",
          font_size=8, color=SLATE_LIGHT, align=PP_ALIGN.CENTER)

    # Main area
    label = sur.get("label") or "(unlabelled cluster)"
    note = sur.get("note") or ""

    _text(slide, x=1.9, y=0.3, w=7.9, h=0.3, text="EMERGING THEME",
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

def build_assessment_pptx(
    assessment: dict,
    forecast_run: Optional[dict] = None,
    *,
    updates_only: bool = False,
    prior_assessment: Optional[dict] = None,
) -> bytes:
    """Render a Forecast Tracker assessment as a PPTX deck.

    When ``updates_only=True`` and a ``prior_assessment`` is supplied, the deck
    is filtered to the delta since that prior snapshot:

    * Scenario slides only render if the scenario has new evidence or a
      verdict-label change.
    * Surprise clusters only render if they're new (label not present in the
      prior snapshot).
    * The methodology slide is skipped — the audience for an updates deck
      already understands baseline correction.
    """
    prs = Presentation()
    prs.slide_width = Inches(10.0)
    prs.slide_height = Inches(5.625)  # 16:9 matching the Wiley deck (10×5.62)

    verdicts = assessment.get("scenario_verdicts") or []
    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})

    if updates_only and not prior_assessment:
        _add_no_prior_slide(prs, assessment, forecast_run or {})
    elif updates_only and prior_assessment:
        diff = _diff_assessments(assessment, prior_assessment)
        _add_cover_slide(prs, assessment, forecast_run or {}, updates_diff=diff)
        # Single gap-analysis matrix: every scenario, prior vs current verdict,
        # net-rate delta, evidence delta — readable in 30 seconds.
        _add_gap_analysis_matrix_slide(prs, assessment, prior_assessment, diff)

        # Per-scenario detail slides ONLY for verdict-label flips. Scenarios
        # that picked up new articles but didn't change verdict don't earn a
        # slide — the matrix row says everything that matters.
        for v in verdicts:
            if v.get("verdict_label") == "Done":
                continue
            key = str(v.get("scenario_idx"))
            if key not in diff.get("verdict_flips", {}):
                continue
            prior_label, current_label = diff["verdict_flips"][key]
            _add_flip_detail_slide(
                prs, v, prior_label, current_label,
                baseline=bc_per.get(key),
                prior_baseline=_prior_baseline_for(prior_assessment, key),
            )

        # New surprise clusters only.
        surprises = assessment.get("surprises") or []
        new_surprises = [s for s in surprises if (s.get("label") or "") in diff["new_surprise_labels"]]
        if new_surprises:
            _add_surprises_divider(prs, new_surprises)
            for sur in sorted(new_surprises, key=lambda s: -(s.get("size") or 0)):
                _add_surprise_cluster_slide(prs, sur)
    else:
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


def _prior_baseline_for(prior_assessment: dict, scenario_key: str) -> Optional[dict]:
    """Lookup the prior baseline-correction entry for a scenario."""
    if not prior_assessment:
        return None
    bc = ((prior_assessment.get("summary") or {}).get("baseline_correction") or {})
    return (bc.get("per_scenario") or {}).get(scenario_key)


def _add_gap_analysis_matrix_slide(prs, current: dict, prior: dict, diff: dict):
    """One-slide gap analysis: every scenario × {prior verdict, current verdict,
    net-rate delta, new-evidence count}. The point of an updates-only deck.

    Rows are ordered by size of |net-rate change| so the biggest movers
    surface first. Rows are color-tinted: green for improvements, red for
    regressions, gray for no material change. Done scenarios excluded.
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _add_bg_image(slide, WILEY_BG_BOKEH)
    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Gap analysis since prior snapshot",
          font_size=22, bold=True, color=WILEY_NAVY)
    prior_at = diff.get("prior_assessed_at") or "—"
    current_at = (
        current.get("assessed_at").isoformat()
        if hasattr(current.get("assessed_at"), "isoformat")
        else (current.get("assessed_at") or "—")
    )
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text=f"Comparing {_short_date(prior_at)} → {_short_date(current_at)}",
          font_size=11, italic=True, color=WILEY_MUTED)

    # White content card hosting the matrix
    card_y = 1.1
    _rect(slide, x=0.4, y=card_y, w=sw-0.8, h=4.25, fill=WILEY_CARD_BG)
    _rect(slide, x=0.4, y=card_y, w=sw-0.8, h=0.04, fill=WILEY_TEAL)

    # Column geometry
    cols = [
        ("Scenario",          0.55, 3.0, PP_ALIGN.LEFT),
        ("Status was",        3.6,  1.4, PP_ALIGN.CENTER),
        ("Status now",        5.05, 1.4, PP_ALIGN.CENTER),
        ("Confirmation Δ",    6.5,  1.65, PP_ALIGN.CENTER),
        ("New articles",      8.2,  1.3, PP_ALIGN.CENTER),
    ]
    header_y = card_y + 0.18
    for title, x, w, align in cols:
        _text(slide, x=x, y=header_y, w=w, h=0.25, text=title.upper(),
              font_size=8.5, bold=True, color=WILEY_TEAL, align=align)
    _rect(slide, x=0.55, y=header_y+0.28, w=sw-1.1, h=0.012, fill=RULE_GRAY)

    # Map prior verdicts/baselines for lookup
    prior_verdicts = {
        str(v.get("scenario_idx")): v
        for v in (prior.get("scenario_verdicts") or [])
    }
    prior_uris = set(prior.get("article_uris") or [])

    # Build one row payload per non-done scenario
    rows = []
    for v in (current.get("scenario_verdicts") or []):
        if v.get("verdict_label") == "Done":
            continue
        key = str(v.get("scenario_idx"))
        pv = prior_verdicts.get(key, {})
        cur_label = (v.get("top_articles") or {}).get("deck_info") or {}
        # Headline label = baseline label if we have one, else verdict label
        cur_bc = _prior_baseline_for(current, key) or {}
        prior_bc = _prior_baseline_for(prior, key) or {}
        was_label = (prior_bc.get("label") or pv.get("verdict_label") or "—")
        now_label = (cur_bc.get("label") or v.get("verdict_label") or "—")
        was_net = prior_bc.get("net_rate")
        now_net = cur_bc.get("net_rate")
        delta_net = (
            (now_net or 0) - (was_net or 0)
            if (was_net is not None or now_net is not None)
            else None
        )

        # Count new article uris that landed in this scenario's top_articles
        new_count = 0
        for bucket in ("supports", "contradicts"):
            for art in ((v.get("top_articles") or {}).get(bucket) or []):
                u = art.get("article_uri") or art.get("uri")
                if u and u not in prior_uris:
                    new_count += 1

        scenario_name = (
            ((v.get("top_articles") or {}).get("deck_info") or {}).get("deck_scenario_name")
            or v.get("scenario_title")
            or "—"
        )

        rows.append({
            "name": scenario_name,
            "was": was_label,
            "now": now_label,
            "was_net": was_net,
            "now_net": now_net,
            "delta_net": delta_net,
            "new_count": new_count,
            "flipped": key in diff.get("verdict_flips", {}),
            "direction": _row_direction(was_label, now_label, delta_net),
        })

    # Sort: biggest absolute net-rate delta first (then by flip), so the
    # movers surface at the top.
    rows.sort(key=lambda r: (
        -abs(r["delta_net"] or 0),
        -1 if r["flipped"] else 0,
    ))

    # Render rows — cap at 9 to fit on one slide.
    row_y = header_y + 0.35
    for r in rows[:9]:
        tint = {
            "improved":  PALE_GREEN,
            "worsened":  PALE_RED,
            "stable":    None,
        }.get(r["direction"])
        if tint:
            _rect(slide, x=0.4, y=row_y-0.04, w=sw-0.8, h=0.42, fill=tint)

        # Scenario name + small "STATUS CHANGED" badge
        _text(slide, x=0.55, y=row_y, w=cols[0][2], h=0.35,
              text=_truncate(r["name"], 56),
              font_size=10, bold=True, color=WILEY_BODY)
        if r["flipped"]:
            _text(slide, x=0.55, y=row_y+0.22, w=cols[0][2], h=0.15,
                  text="STATUS CHANGED", font_size=7, bold=True, color=WILEY_TEAL)

        # Was / Now chips — render the customer-facing label, color from internal
        _verdict_chip(slide, x=cols[1][1], y=row_y+0.04, w=cols[1][2]-0.1, h=0.3,
                      label=_customer_label(r["was"]),
                      color=_baseline_color(r["was"]))
        _verdict_chip(slide, x=cols[2][1], y=row_y+0.04, w=cols[2][2]-0.1, h=0.3,
                      label=_customer_label(r["now"]),
                      color=_baseline_color(r["now"]))

        # Net rate delta cell — "1.99% → 0.57% (−1.43%)"
        was_s = f"{(r['was_net'] or 0)*100:.2f}%" if r["was_net"] is not None else "—"
        now_s = f"{(r['now_net'] or 0)*100:.2f}%" if r["now_net"] is not None else "—"
        if r["delta_net"] is None:
            delta_s = "—"
        else:
            sign = "+" if r["delta_net"] > 0 else ""
            delta_s = f"{sign}{r['delta_net']*100:.2f}%"
        delta_color = (
            GREEN_DEEP if (r["delta_net"] or 0) > 0.001
            else (RED_DEEP if (r["delta_net"] or 0) < -0.001 else SLATE_LIGHT)
        )
        _text(slide, x=cols[3][1], y=row_y+0.02, w=cols[3][2], h=0.18,
              text=f"{was_s} → {now_s}", font_size=8, color=WILEY_MUTED,
              align=PP_ALIGN.CENTER)
        _text(slide, x=cols[3][1], y=row_y+0.2, w=cols[3][2], h=0.2,
              text=delta_s, font_size=11, bold=True, color=delta_color,
              align=PP_ALIGN.CENTER)

        # New-article count
        new_s = f"+{r['new_count']}" if r["new_count"] else "—"
        _text(slide, x=cols[4][1], y=row_y+0.06, w=cols[4][2], h=0.3,
              text=new_s, font_size=12, bold=True,
              color=(WILEY_TEAL if r["new_count"] else SLATE_LIGHT),
              align=PP_ALIGN.CENTER)

        row_y += 0.42

    # Footer summary line
    n_flips = len(diff.get("verdict_flips", {}))
    n_new_clusters = len(diff.get("new_surprise_labels", []))
    n_new_evidence = len(diff.get("new_uris", []))
    footer = (
        f"{n_flips} status change{'' if n_flips == 1 else 's'}    ·    "
        f"{n_new_evidence} new article{'' if n_new_evidence == 1 else 's'} across all scenarios    ·    "
        f"{n_new_clusters} new emerging theme{'' if n_new_clusters == 1 else 's'}"
    )
    _text(slide, x=0.5, y=5.45, w=sw-1.0, h=0.22,
          text=footer, font_size=9, italic=True, color=WILEY_MUTED,
          align=PP_ALIGN.CENTER)


def _row_direction(was: str, now: str, delta_net: Optional[float]) -> str:
    """Classify the row as improved / worsened / stable for color tinting."""
    rank = {
        "Below baseline": 0, "At baseline": 1, "Above baseline": 2,
        "Off-track": 0, "Stalled": 1, "Inconclusive": 1,
        "On-track": 2, "Accelerating": 3,
    }
    w = rank.get(was)
    n = rank.get(now)
    if w is not None and n is not None and n != w:
        return "improved" if n > w else "worsened"
    if delta_net is not None:
        if delta_net > 0.005:
            return "improved"
        if delta_net < -0.005:
            return "worsened"
    return "stable"


def _verdict_chip(slide, *, x, y, w, h, label: str, color: Optional[RGBColor] = None):
    """Inline chip for the gap-analysis matrix's Was/Now cells.

    ``label`` is the *display* string (already translated by
    :func:`_customer_label` upstream). ``color`` lets callers pin the chip's
    color when the display label has been translated away from the
    ``BASELINE_COLORS`` keys."""
    if color is None:
        color = (
            BASELINE_COLORS.get(label)
            or {
                "Accelerating": GREEN_DEEP,
                "On-track":     GREEN,
                "Inconclusive": SLATE_PALE,
                "Stalled":      AMBER_DEEP,
                "Off-track":    RED_DEEP,
                "Done":         SLATE_MID,
            }.get(label, SLATE_PALE)
        )
    _rect(slide, x=x, y=y, w=w, h=h, fill=color, rounded=True)
    _text(slide, x=x, y=y+0.05, w=w, h=h-0.08,
          text=label or "—", font_size=8.5, bold=True, color=WHITE,
          align=PP_ALIGN.CENTER)


def _add_flip_detail_slide(
    prs, verdict: dict, prior_label: str, current_label: str,
    *, baseline: Optional[dict] = None, prior_baseline: Optional[dict] = None,
):
    """A single slide focused on one scenario whose verdict flipped between
    snapshots. Lean: headline + flip arrow + 2-3 articles driving the flip
    + the narrative if cached."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _add_bg_image(slide, WILEY_BG_SOFT)
    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Status changed", font_size=22, bold=True, color=WILEY_NAVY)

    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}
    name = deck_info.get("deck_scenario_name") or verdict.get("scenario_title") or "—"
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.5, text=name,
          font_size=18, bold=True, color=WILEY_BODY)

    # Big "Was → Now" panel — render customer-facing labels with internal colors
    _verdict_chip(slide, x=0.5, y=1.85, w=2.4, h=0.55,
                  label=_customer_label(prior_label),
                  color=_baseline_color(prior_label))
    _text(slide, x=3.0, y=1.93, w=0.6, h=0.4, text="→",
          font_size=22, bold=True, color=SLATE_DARK, align=PP_ALIGN.CENTER)
    _verdict_chip(slide, x=3.7, y=1.85, w=2.4, h=0.55,
                  label=_customer_label(current_label),
                  color=_baseline_color(current_label))

    # Confirmation-strength change on the right
    was_net = (prior_baseline or {}).get("net_rate")
    now_net = (baseline or {}).get("net_rate")
    if was_net is not None or now_net is not None:
        delta = (now_net or 0) - (was_net or 0)
        sign = "+" if delta > 0 else ""
        _text(slide, x=6.5, y=1.85, w=3.0, h=0.22,
              text="CONFIRMATION Δ", font_size=8.5, bold=True,
              color=PINK_DEEP, align=PP_ALIGN.LEFT)
        was_s = f"{(was_net or 0)*100:.2f}%" if was_net is not None else "—"
        now_s = f"{(now_net or 0)*100:.2f}%" if now_net is not None else "—"
        _text(slide, x=6.5, y=2.05, w=3.0, h=0.2,
              text=f"{was_s} → {now_s}", font_size=10, color=SLATE_MID,
              align=PP_ALIGN.LEFT)
        delta_color = GREEN_DEEP if delta > 0 else (RED_DEEP if delta < 0 else SLATE_LIGHT)
        _text(slide, x=6.5, y=2.25, w=3.0, h=0.35,
              text=f"{sign}{delta*100:.2f}%",
              font_size=20, bold=True, color=delta_color, align=PP_ALIGN.LEFT)

    # LLM narrative if cached, else fall back to top articles
    narrative = (verdict.get("summary_md") or "").strip()
    y = 2.65
    if narrative:
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=0.04, fill=RULE_GRAY)
        _text(slide, x=0.5, y=y+0.1, w=sw-1.0, h=0.25,
              text="WHAT HAPPENED", font_size=8.5, bold=True, color=PINK_DEEP)
        _text(slide, x=0.5, y=y+0.4, w=sw-1.0, h=2.0,
              text=narrative, font_size=10.5, color=SLATE_BLACK,
              line_spacing=1.3)
        y += 2.4

    # Driving evidence — top 2 supports + top 1 contradict (or the inverse
    # if the flip was negative-direction)
    sup = ((verdict.get("top_articles") or {}).get("supports") or [])[:2]
    con = ((verdict.get("top_articles") or {}).get("contradicts") or [])[:1]
    if sup or con:
        _text(slide, x=0.5, y=y, w=sw-1.0, h=0.25,
              text="EVIDENCE", font_size=8.5, bold=True, color=PINK_DEEP)
        y += 0.3
        for a in sup:
            _evidence_line(slide, y=y, article=a, support=True)
            y += 0.32
        for a in con:
            _evidence_line(slide, y=y, article=a, support=False)
            y += 0.32

    _add_brand_footer(slide, slide_label=f"Flip: {name[:40]}")


def _evidence_line(slide, *, y: float, article: dict, support: bool):
    color = SUPPORT_COLOR if support else CONTRA_COLOR
    title = article.get("title") or article.get("article_uri") or "(no title)"
    date = (article.get("article_date") or "")[:10]
    _rect(slide, x=0.5, y=y+0.04, w=0.08, h=0.22, fill=color)
    prefix = f"{date} · " if date else ""
    _text(slide, x=0.7, y=y, w=9.0, h=0.28,
          text=f"{prefix}{_truncate(title, 110)}",
          font_size=10, color=SLATE_DARK)


def _consensus_drift_text(assessment: dict) -> str:
    """Compute a 'Original 75% → Current 68% consensus' summary across the
    topic's high-consensus deck scenarios. Returns empty string when no
    drift can be reported (no deck consensus_pct, or no current values)."""
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    orig_vals = []
    cur_vals = []
    for v in verdicts:
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        o = deck_info.get("consensus_pct")
        c = v.get("current_consensus_pct")
        if o is not None:
            orig_vals.append(float(o))
        if c is not None:
            cur_vals.append(float(c))
    if not orig_vals and not cur_vals:
        return ""
    parts = []
    if orig_vals:
        parts.append(f"Original consensus {sum(orig_vals)/len(orig_vals):.0f}% (avg)")
    if cur_vals:
        parts.append(f"current {sum(cur_vals)/len(cur_vals):.0f}%")
    return "  →  ".join(parts)


def _add_briefing_synthesis_slide(prs, assessment: dict):
    """Per-topic Briefing Synthesis — direct port of Wiley deck slide 20.

    Two equal-width white panels side-by-side. Left panel has a teal header
    bar ("The Ecosystem at a Crossroads" / Defining tensions). Right panel
    has a navy header bar ("The Aunoo Intelligence View" / Strategic synthesis).
    Reads from ``assessment.summary['topic_briefing']`` populated by the
    narrative service.
    """
    briefing = ((assessment.get("summary") or {}).get("topic_briefing")) or {}
    if not briefing or not briefing.get("lede"):
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _add_bg_image(slide, WILEY_BG_SOFT)

    # Title row (no header bar — title sits directly on the bg, Wiley-style)
    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4, text="Briefing Synthesis",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.35,
          text=briefing.get("headline") or (assessment.get("topic") or "—"),
          font_size=12, italic=True, color=WILEY_MUTED)

    # Consensus drift strip — shows original deck consensus next to
    # the freshly-measured current consensus (averaged across scenarios)
    drift_line = _consensus_drift_text(assessment)
    if drift_line:
        _text(slide, x=0.5, y=1.0, w=sw-1.0, h=0.22, text=drift_line,
              font_size=10, bold=True, color=WILEY_TEAL)

    # ── Left panel: The Ecosystem at a Crossroads ────────────────────
    _rect(slide, x=0.5, y=1.1, w=4.5, h=4.2, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.1, w=4.5, h=0.7, fill=WILEY_TEAL)
    _text(slide, x=0.6, y=1.18, w=4.3, h=0.4,
          text="The Ecosystem at a Crossroads",
          font_size=14, bold=True, color=WHITE)
    _text(slide, x=0.6, y=1.52, w=4.3, h=0.25,
          text="Defining tensions shaping this topic",
          font_size=9, italic=True, color=WILEY_TEAL_LT)

    tensions = briefing.get("tensions") or []
    ty = 1.95
    for t in tensions[:3]:
        name = (t.get("name") or "").upper()
        body = t.get("body") or ""
        _text(slide, x=0.7, y=ty, w=4.2, h=0.25,
              text=name, font_size=10, bold=True, color=WILEY_TEAL)
        _text(slide, x=0.7, y=ty+0.27, w=4.2, h=0.85,
              text=body, font_size=9.5, color=WILEY_BODY, line_spacing=1.3)
        ty += 1.1

    # ── Right panel: The Aunoo Intelligence View ─────────────────────
    _rect(slide, x=5.1, y=1.1, w=4.4, h=4.2, fill=WILEY_CARD_BG)
    _rect(slide, x=5.1, y=1.1, w=4.4, h=0.7, fill=WILEY_NAVY)
    _text(slide, x=5.3, y=1.18, w=4.0, h=0.4,
          text="The Aunoo Intelligence View",
          font_size=14, bold=True, color=WHITE)
    _text(slide, x=5.3, y=1.52, w=4.0, h=0.25,
          text="Strategic synthesis · Key implications",
          font_size=9, italic=True, color=WILEY_TEAL_LT)

    # Lede paragraph + the synthesis view, stacked
    lede = (briefing.get("lede") or "").strip()
    iv = (briefing.get("intelligence_view") or "").strip()
    paragraphs = []
    if lede:
        paragraphs.append(lede)
    if iv:
        paragraphs.append(iv)
    full_text = "\n\n".join(paragraphs)
    _text(slide, x=5.3, y=1.95, w=4.0, h=3.3, text=full_text,
          font_size=10, color=WILEY_BODY, line_spacing=1.4)


def _add_key_insights_slide(prs, assessment: dict, prior: Optional[dict] = None):
    """Per-topic Key Insights slide — data-driven (no LLM call).

    Distils 4-5 bullet observations from the assessment + (if available) the
    prior snapshot diff: the strongest support / contradict findings, the
    largest verdict-flip, the biggest unanticipated cluster.
    """
    summary = assessment.get("summary") or {}
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    surprises = sorted(assessment.get("surprises") or [],
                       key=lambda s: -(s.get("size") or 0))

    insights = []  # list of {kind, body}

    # 1. Strongest positive mover
    pos = [(((bc_per.get(str(v.get("scenario_idx"))) or {}).get("net_rate") or 0), v)
           for v in verdicts]
    pos.sort(key=lambda kv: -kv[0])
    if pos and pos[0][0] > 0.005:
        net, v = pos[0]
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        insights.append({
            "kind": "STRONGEST CONFIRMATION",
            "body": f"{name} is strengthening — confirmation Δ {net*100:+.2f}% with "
                    f"{v.get('supports') or 0} confirming events since the forecast "
                    f"was published, beyond what the pre-forecast trend predicted."
        })

    # 2. Strongest negative mover
    if pos and pos[-1][0] < -0.005:
        net, v = pos[-1]
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        insights.append({
            "kind": "STRONGEST COOLING",
            "body": f"{name} is cooling — confirmation Δ {net*100:+.2f}%. The trend "
                    f"was hotter at forecast-authoring time than it is now; not wrong, "
                    f"just already crested."
        })

    # 3. Largest verdict-flip vs prior
    if prior:
        diff = _diff_assessments(assessment, prior)
        flips = list(diff.get("verdict_flips", {}).items())
        if flips:
            biggest = max(
                flips,
                key=lambda kv: abs(
                    ((bc_per.get(kv[0]) or {}).get("net_rate") or 0)
                    - ((_prior_baseline_for(prior, kv[0]) or {}).get("net_rate") or 0)
                ),
            )
            key, (was, now) = biggest
            v = next((x for x in verdicts if str(x.get("scenario_idx")) == key), None)
            if v:
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
                insights.append({
                    "kind": "BIGGEST STATUS CHANGE",
                    "body": f"{name}: {_customer_label(was)} → {_customer_label(now)} between snapshots."
                })

    # 4. Dominant emerging theme
    if surprises:
        top = surprises[0]
        insights.append({
            "kind": "EMERGING THEME",
            "body": f"{(top.get('label') or '(unlabelled)').strip()} surfaced as the "
                    f"largest emerging theme ({top.get('size') or 0} articles) — "
                    f"none of the original scenarios anticipated it."
        })

    # 5. Stable overhang — scenarios stuck at the pre-forecast baseline
    n_inc = sum(
        1 for v in verdicts
        if v.get("verdict_label") == "Inconclusive"
        and (bc_per.get(str(v.get("scenario_idx"))) or {}).get("label") in (None, "At baseline")
    )
    if n_inc >= 2:
        insights.append({
            "kind": "INSUFFICIENT EVIDENCE",
            "body": f"{n_inc} scenarios remain in 'stable / pre-existing trend' territory — "
                    f"fresh coverage isn't yet producing enough confident matches to call a direction."
        })

    if not insights:
        return  # Nothing worth a slide

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Key Insights from Evidence Synthesis",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text=assessment.get("topic") or "—",
          font_size=11, italic=True, color=WILEY_MUTED)

    # White content card hosting the insights
    _rect(slide, x=0.5, y=1.15, w=sw-1.0, h=4.2, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.15, w=0.08, h=4.2, fill=WILEY_TEAL)

    y = 1.35
    for ins in insights[:5]:
        _text(slide, x=0.85, y=y, w=sw-1.7, h=0.22,
              text=ins["kind"], font_size=9, bold=True, color=WILEY_TEAL)
        _text(slide, x=0.85, y=y+0.25, w=sw-1.7, h=0.55,
              text=ins["body"], font_size=11, color=WILEY_BODY,
              line_spacing=1.4)
        y += 0.78


def _add_strategic_recommendations_slide(prs, assessment: dict):
    """Per-topic Strategic Recommendations — direct port of Wiley deck slide 23.

    Three white vertical cards. Each card has a coloured header bar (alternating
    teal / navy / teal across the row, matching the Wiley pattern), a headline
    title, and a body paragraph. Horizon shown as a small chip at the bottom
    of each card.
    """
    recs = ((assessment.get("summary") or {}).get("strategic_recommendations")) or []
    if not recs:
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    # Title
    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Strategic Recommendations",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text=f"{assessment.get('topic') or '—'} — three strategic priorities for leadership",
          font_size=11, italic=True, color=WILEY_MUTED)

    HORIZON_COLOR = {
        "0-6 months":  GREEN_DEEP,
        "6-18 months": AMBER_DEEP,
        "18+ months":  WILEY_BLUE,
    }

    # 3 vertical cards across the slide
    card_palette = [WILEY_TEAL, WILEY_NAVY, WILEY_TEAL]
    card_w = 2.95
    gap = 0.1
    start_x = (sw - (3 * card_w + 2 * gap)) / 2
    card_y = 1.2
    card_h = 4.0

    for i, r in enumerate(recs[:3]):
        cx = start_x + i * (card_w + gap)
        bar_color = card_palette[i % 3]

        # White card with coloured top bar
        _rect(slide, x=cx, y=card_y, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=cx, y=card_y, w=card_w, h=0.55, fill=bar_color)

        # Card header — recommendation headline (short, capitalised treatment)
        headline = (r.get("headline") or "").strip()
        # Wiley headers are a single short phrase. Trim to fit two lines max
        _text(slide, x=cx+0.15, y=card_y+0.07, w=card_w-0.3, h=0.4,
              text=headline, font_size=12, bold=True, color=WHITE,
              line_spacing=1.15)

        # Card body — rationale paragraph
        rationale = (r.get("rationale") or "").strip()
        _text(slide, x=cx+0.2, y=card_y+0.75, w=card_w-0.4, h=card_h-1.3,
              text=rationale, font_size=10, color=WILEY_BODY, line_spacing=1.4)

        # Horizon chip at the bottom of each card
        horizon = r.get("horizon") or "6-18 months"
        chip_color = HORIZON_COLOR.get(horizon, WILEY_BLUE)
        _rect(slide, x=cx+0.2, y=card_y+card_h-0.45, w=card_w-0.4, h=0.32,
              fill=chip_color, rounded=True)
        _text(slide, x=cx+0.2, y=card_y+card_h-0.4, w=card_w-0.4, h=0.22,
              text=horizon.upper(), font_size=8.5, bold=True, color=WHITE,
              align=PP_ALIGN.CENTER)


def _add_consensus_outlier_slide(prs, assessment: dict):
    """Per-topic Consensus & Outlier Analysis — data-driven.

    Two columns: HIGH-CONSENSUS (deck scenarios with ≥75% original consensus)
    and OUTLIERS (scenarios whose baseline-corrected net rate diverges most
    from the deck's predicted direction). Reuses the existing deck_info
    consensus_pct field.
    """
    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]

    high_consensus = []
    outliers = []
    for v in verdicts:
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        consensus = deck_info.get("consensus_pct")
        current_consensus = v.get("current_consensus_pct")
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        bc = bc_per.get(str(v.get("scenario_idx"))) or {}
        net = bc.get("net_rate")
        label = bc.get("label") or v.get("verdict_label") or "—"
        if consensus is not None and consensus >= 75:
            high_consensus.append({"name": name, "consensus": consensus,
                                   "current_consensus": current_consensus,
                                   "label": label, "net": net})
        # Outlier = a scenario the original forecast rated high-consensus that's now cooling
        if consensus is not None and consensus >= 75 and label == "Below baseline":
            outliers.append({"name": name, "consensus": consensus,
                             "current_consensus": current_consensus,
                             "label": label, "net": net,
                             "reason": "Forecast had high consensus, but the trend is now cooling"})
        # Also flag low-consensus scenarios that are now strengthening (forecast under-rated them)
        if consensus is not None and consensus < 70 and label == "Above baseline":
            outliers.append({"name": name, "consensus": consensus,
                             "current_consensus": current_consensus,
                             "label": label, "net": net,
                             "reason": "Forecast had low consensus, but the trend is now strengthening"})
        # NEW outlier rule: significant consensus drift from original to current
        if (consensus is not None and current_consensus is not None
                and abs(consensus - current_consensus) >= 20
                and not any(o["name"] == name for o in outliers)):
            direction = "fallen" if current_consensus < consensus else "risen"
            outliers.append({"name": name, "consensus": consensus,
                             "current_consensus": current_consensus,
                             "label": label, "net": net,
                             "reason": f"Consensus has {direction} sharply since the original forecast"})

    # Sort by absolute net rate inside each list
    high_consensus.sort(key=lambda x: -abs(x.get("net") or 0))
    outliers.sort(key=lambda x: -abs(x.get("net") or 0))

    if not high_consensus and not outliers:
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Consensus & Outlier Analysis",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text=assessment.get("topic") or "—",
          font_size=11, italic=True, color=WILEY_MUTED)

    # Two white panels side-by-side
    _rect(slide, x=0.5, y=1.15, w=4.4, h=4.2, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.15, w=4.4, h=0.55, fill=WILEY_TEAL)
    _text(slide, x=0.65, y=1.25, w=4.2, h=0.32,
          text="HIGH-CONSENSUS SCENARIOS",
          font_size=11, bold=True, color=WHITE)
    _text(slide, x=0.65, y=1.55, w=4.2, h=0.18,
          text="≥75% in the original forecast",
          font_size=8.5, italic=True, color=WILEY_TEAL_LT)

    y = 1.9
    for h in high_consensus[:5]:
        net_s = f"{(h.get('net') or 0)*100:+.2f}%" if h.get("net") is not None else "—"
        cur = h.get("current_consensus")
        cur_s = f"{cur:.0f}%" if cur is not None else "—"
        _verdict_chip(slide, x=0.65, y=y+0.06, w=1.2, h=0.3,
                      label=_customer_label(h.get("label")),
                      color=_baseline_color(h.get("label")))
        _text(slide, x=1.95, y=y, w=2.9, h=0.22,
              text=_truncate(h["name"], 42),
              font_size=10, bold=True, color=WILEY_BODY)
        _text(slide, x=1.95, y=y+0.24, w=2.9, h=0.2,
              text=f"{int(h.get('consensus'))}% original  →  {cur_s} current  ·  Δ {net_s}",
              font_size=8.5, color=WILEY_MUTED)
        y += 0.55

    # Right panel — outliers
    _rect(slide, x=5.1, y=1.15, w=4.4, h=4.2, fill=WILEY_CARD_BG)
    _rect(slide, x=5.1, y=1.15, w=4.4, h=0.55, fill=WILEY_NAVY)
    _text(slide, x=5.25, y=1.25, w=4.2, h=0.32,
          text="OUTLIERS",
          font_size=11, bold=True, color=WHITE)
    _text(slide, x=5.25, y=1.55, w=4.2, h=0.18,
          text="Where original consensus and current tracking disagree",
          font_size=8.5, italic=True, color=WILEY_TEAL_LT)

    y = 1.9
    if outliers:
        for o in outliers[:5]:
            net_s = f"{(o.get('net') or 0)*100:+.2f}%" if o.get("net") is not None else "—"
            _verdict_chip(slide, x=5.25, y=y+0.06, w=1.2, h=0.3,
                          label=_customer_label(o.get("label")),
                          color=_baseline_color(o.get("label")))
            _text(slide, x=6.55, y=y, w=2.9, h=0.22,
                  text=_truncate(o["name"], 42),
                  font_size=10, bold=True, color=WILEY_BODY)
            _text(slide, x=6.55, y=y+0.24, w=2.9, h=0.5,
                  text=f"{o.get('reason') or ''} ({net_s})",
                  font_size=8.5, color=WILEY_MUTED, line_spacing=1.3)
            y += 0.75
    else:
        _text(slide, x=5.25, y=y, w=4.2, h=0.55,
              text="No outliers — current evidence corroborates the original "
                   "high-consensus calls.",
              font_size=11, italic=True, color=WILEY_MUTED, line_spacing=1.4)


# ── New cross-topic Wiley-style front-matter slides ────────────────────

def _add_review_pending_banner_slide(prs, findings: list, period_label: str):
    """Prepended right after the cover when the LLM-as-judge reviewer flagged
    error-severity issues but the user downloaded the draft anyway. Lists
    the findings so the reader knows the deck is a preview, not for shipping.
    """
    if not findings:
        return
    errors = [f for f in findings if f.get("severity") == "error"]
    warnings = [f for f in findings if f.get("severity") == "warning"]
    if not errors and not warnings:
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Soft bg + alert red header band
    _add_bg_image(slide, WILEY_BG_SOFT)
    _rect(slide, x=0, y=0, w=sw, h=0.85, fill=RED_DEEP)

    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.32,
          text="REVIEW PENDING — DO NOT SHIP",
          font_size=18, bold=True, color=WHITE)
    _text(slide, x=0.5, y=0.52, w=sw-1.0, h=0.25,
          text=f"AunooAI's LLM-as-judge reviewer flagged {len(errors)} error"
               f"{'' if len(errors) == 1 else 's'} and {len(warnings)} warning"
               f"{'' if len(warnings) == 1 else 's'} on the {period_label} bundle.",
          font_size=10, color=WHITE)

    # Body card with findings list
    _rect(slide, x=0.5, y=1.05, w=sw-1.0, h=4.0, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.05, w=0.08, h=4.0, fill=RED_DEEP)

    _text(slide, x=0.7, y=1.18, w=sw-1.4, h=0.28,
          text="Findings to resolve before shipping",
          font_size=12, bold=True, color=WILEY_NAVY)

    y = 1.55
    # Errors first
    for f in errors[:5]:
        sev = (f.get("severity") or "").upper()
        artefact = f.get("artefact_key") or ""
        finding = f.get("finding") or ""
        _text(slide, x=0.85, y=y, w=0.8, h=0.2,
              text=sev, font_size=8, bold=True, color=RED_DEEP)
        _text(slide, x=1.7, y=y, w=sw-2.4, h=0.2,
              text=artefact, font_size=8, color=WILEY_TEAL)
        _text(slide, x=0.85, y=y+0.22, w=sw-1.55, h=0.42,
              text=finding, font_size=9.5, color=WILEY_BODY, line_spacing=1.3)
        y += 0.72
    remaining_warnings = len(warnings)
    if remaining_warnings:
        _text(slide, x=0.7, y=y+0.05, w=sw-1.4, h=0.25,
              text=f"Plus {remaining_warnings} warning{'' if remaining_warnings == 1 else 's'} — see the Wiley Deliverables panel.",
              font_size=9, italic=True, color=WILEY_MUTED)

    _text(slide, x=0.5, y=5.18, w=sw-1.0, h=0.22,
          text="Resolve in the Wiley Deliverables panel — approve overrides or request fix.",
          font_size=9, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)


def _add_executive_summary_letter_slide(prs, exec_summary: dict, period_label: str):
    """Executive Summary LETTER — sits at slide 2, immediately after the cover.

    Distinct from the stats-style Executive Summary (which becomes "Headline
    Findings"). This is an addressed-to-the-reader prose paragraph (6-8
    sentences) produced by the wiley_exec_summary_agent. Soft full-bleed bg
    with a centred white card hosting the letter.
    """
    letter = (exec_summary or {}).get("letter") or ""
    if not letter.strip():
        return
    signoff = (exec_summary or {}).get("signoff") or f"AunooAI Editorial Team · {period_label}"

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    # Title row
    _text(slide, x=0.5, y=0.4, w=sw-1.0, h=0.45,
          text="Executive Summary", font_size=24, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.3,
          text=period_label, font_size=11, italic=True, color=WILEY_MUTED)

    # Letter card
    _rect(slide, x=0.5, y=1.4, w=sw-1.0, h=3.65, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.4, w=0.08, h=3.65, fill=WILEY_TEAL)
    _text(slide, x=0.85, y=1.55, w=sw-1.55, h=3.4, text=letter,
          font_size=12.5, color=WILEY_BODY, line_spacing=1.55)

    # Signoff
    _text(slide, x=0.5, y=5.18, w=sw-1.0, h=0.25,
          text="— " + signoff, font_size=10, italic=True, color=WILEY_TEAL,
          align=PP_ALIGN.RIGHT)


def _add_strategic_overview_slide(prs, period_label: str, overview_text: str):
    """Cross-topic Strategic Overview — mirrors Wiley deck slide 10.

    Single rich paragraph (4-6 sentences) on soft-teal full-bleed background.
    """
    if not (overview_text or "").strip():
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.4, w=sw-1.0, h=0.5,
          text="Strategic Overview", font_size=24, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.3,
          text=period_label, font_size=11, italic=True, color=WILEY_MUTED)

    # White paragraph card, generous typography
    _rect(slide, x=0.5, y=1.4, w=sw-1.0, h=3.8, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.4, w=0.08, h=3.8, fill=WILEY_TEAL)
    _text(slide, x=0.85, y=1.6, w=sw-1.7, h=3.5,
          text=overview_text, font_size=13, color=WILEY_BODY, line_spacing=1.55)


def _add_five_domains_summary_slide(prs, items: list):
    """Five Strategic Domains overview — mirrors Wiley deck slide 11 condensed.

    One card per topic in a 2×3 grid: topic name + consensus drift line +
    2 key signals + 1 strategic imperative. Pulls from each topic's
    Briefing Synthesis + per-scenario synthesis.
    """
    if not items:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Strategic Domains", font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text="Status, key signals, and strategic imperative for each topic in this bundle",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    # Cards laid out as 2 rows that fit the 5.625" slide height. Top row
    # holds ceil(n/2) cards, bottom row the rest, centred. Card width is
    # computed from the wider of the two rows so columns align visually.
    visible = items[:6]
    n = len(visible)
    top_n = (n + 1) // 2  # ceil(n/2): 5→3+2, 4→2+2, 6→3+3
    bot_n = n - top_n
    gap_x = 0.1
    gap_y = 0.12
    avail_w = 10.0 - 1.0
    cols_per_row = max(top_n, 1)
    card_w = (avail_w - (cols_per_row - 1) * gap_x) / cols_per_row
    card_h = 2.0
    start_y = 1.15

    def _row_start_x(row_count: int) -> float:
        row_w = row_count * card_w + max(0, row_count - 1) * gap_x
        return (10.0 - row_w) / 2.0

    for i, (assessment, _run, _prior) in enumerate(visible):
        if i < top_n:
            col, row, row_count = i, 0, top_n
        else:
            col, row, row_count = i - top_n, 1, bot_n
        cx = _row_start_x(row_count) + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        topic = assessment.get("topic") or "—"
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}

        # Pick the headline scenario.
        # Prefer scenarios with actual attribution (supports+contradicts > 0).
        # When a topic has hundreds of articles in the window but only one
        # scenario picked any up (the rest are Inconclusive with 0 supports),
        # picking a 0-attribution scenario surfaces "Current 0%" which is a
        # measurement gap, not a real signal — so only pick from attributed
        # scenarios first.
        def _attributed(v):
            return (v.get("supports") or 0) + (v.get("contradicts") or 0) > 0
        attributed = [v for v in verdicts if _attributed(v)]
        pool = attributed if attributed else verdicts

        headline_v = None
        best_abs = -1.0
        for v in pool:
            net = abs((bc_per.get(str(v.get("scenario_idx"))) or {}).get("net_rate") or 0)
            if net > best_abs:
                best_abs = net
                headline_v = v
        if headline_v is None and pool:
            headline_v = pool[0]

        synth = (headline_v.get("synthesis") if headline_v else None) or {}
        signals = synth.get("key_signals") or []
        imperative = (synth.get("strategic_imperative") or "").strip()

        deck_info = (headline_v.get("top_articles") or {}).get("deck_info") if headline_v else None
        deck_info = deck_info or {}
        original_consensus = deck_info.get("consensus_pct")
        # Current consensus comes from the headline scenario; if no scenario
        # in the topic has attribution, show "—" instead of misleading 0%.
        current_consensus = (headline_v or {}).get("current_consensus_pct") if attributed else None
        no_attribution = not attributed

        # White card with teal header bar
        _rect(slide, x=cx, y=cy, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=cx, y=cy, w=card_w, h=0.42, fill=WILEY_TEAL)
        _text(slide, x=cx+0.15, y=cy+0.07, w=card_w-0.3, h=0.3,
              text=_truncate(topic, 50), font_size=11.5, bold=True, color=WHITE)

        # Consensus drift line. When the topic has no attributed scenarios
        # at all, label the gap explicitly ("insufficient attribution")
        # rather than showing 0% which the reader misreads as "no signal".
        if original_consensus is not None or current_consensus is not None:
            o_s = f"{int(original_consensus)}%" if original_consensus is not None else "—"
            c_s = f"{current_consensus:.0f}%" if current_consensus is not None else "—"
            drift_text = (
                f"Original consensus {o_s}   →   Current — (insufficient attribution)"
                if no_attribution and original_consensus is not None
                else f"Original consensus {o_s}   →   Current {c_s}"
            )
            _text(slide, x=cx+0.18, y=cy+0.5, w=card_w-0.3, h=0.22,
                  text=drift_text,
                  font_size=9, italic=True, color=WILEY_TEAL)
            y_signals = cy + 0.78
        else:
            y_signals = cy + 0.55

        # Signal/imperative truncation lengths scale with card width: a
        # 3-up row with narrower cards needs harsher trims to avoid overrun.
        sig_max = max(50, int(card_w * 22))
        imp_max = max(100, int(card_w * 40))

        # Key signals (up to 2)
        if signals:
            _text(slide, x=cx+0.18, y=y_signals, w=card_w-0.3, h=0.22,
                  text="KEY SIGNALS", font_size=8, bold=True, color=WILEY_NAVY)
            sy = y_signals + 0.22
            for sig in signals[:2]:
                _rect(slide, x=cx+0.2, y=sy+0.07, w=0.05, h=0.18, fill=WILEY_TEAL)
                _text(slide, x=cx+0.32, y=sy, w=card_w-0.45, h=0.34,
                      text=_truncate(sig, sig_max), font_size=9, color=WILEY_BODY,
                      line_spacing=1.3)
                sy += 0.36

        # Strategic imperative at the bottom of the card
        if imperative:
            iy = cy + card_h - 0.55
            _rect(slide, x=cx+0.18, y=iy, w=card_w-0.36, h=0.012, fill=RULE_GRAY)
            _text(slide, x=cx+0.18, y=iy+0.04, w=card_w-0.36, h=0.18,
                  text="STRATEGIC IMPERATIVE", font_size=7.5, bold=True, color=WILEY_NAVY)
            _text(slide, x=cx+0.18, y=iy+0.22, w=card_w-0.36, h=0.3,
                  text=_truncate(imperative, imp_max), font_size=8.5, italic=True,
                  color=WILEY_BODY, line_spacing=1.3)


def _add_black_swans_slide(prs, eos_per_topic: dict):
    """Cross-topic Black Swans & Wild Card Scenarios — mirrors Wiley deck slide 17.

    Aggregates the highest impact × probability scenarios across all topics'
    EOS scans and surfaces the top 6-7 as cards on a single slide.
    """
    aggregated = []
    for topic, scenarios in (eos_per_topic or {}).items():
        for s in scenarios or []:
            if not isinstance(s, dict):
                continue
            try:
                score = float(s.get("impact_rating") or 5) * float(s.get("probability") or 0.2)
            except Exception:
                score = 0.0
            aggregated.append((score, topic, s))
    if not aggregated:
        return
    aggregated.sort(key=lambda t: -t[0])
    top = aggregated[:6]

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Black Swans & Wild Card Scenarios",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text="High-impact, low-probability scenarios that could reshape the landscape",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    CATEGORY_COLOR = {
        "black_swan": WILEY_NAVY,
        "contrarian": WILEY_BLUE,
        "wild_card":  WILEY_TEAL,
    }
    CATEGORY_DISPLAY = {
        "black_swan": "BLACK SWAN",
        "contrarian": "CONTRARIAN",
        "wild_card":  "WILD CARD",
    }

    # 2×2 grid of the top 4 cards. Cards are tall enough that the
    # description doesn't overlap the footer line (the bug from the prior
    # 3-row layout). Picking only 4 keeps every card readable; the
    # markdown export covers the remainder.
    card_w = 4.55
    card_h = 1.95
    gap_x = 0.1
    gap_y = 0.12
    start_x = 0.5
    start_y = 1.15

    for i, (_score, topic, s) in enumerate(top[:4]):
        col = i % 2
        row = i // 2
        cx = start_x + col * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        cat = (s.get("category") or "wild_card").lower()
        cat_color = CATEGORY_COLOR.get(cat, WILEY_TEAL)
        cat_label = CATEGORY_DISPLAY.get(cat, cat.upper())

        _rect(slide, x=cx, y=cy, w=card_w, h=card_h, fill=WILEY_CARD_BG, line=WILEY_TEAL_LT)
        # Header strip with category badge + source topic
        _rect(slide, x=cx, y=cy, w=card_w, h=0.34, fill=cat_color)
        _text(slide, x=cx+0.15, y=cy+0.06, w=2.0, h=0.22,
              text=cat_label, font_size=8.5, bold=True, color=WHITE)
        _text(slide, x=cx+2.2, y=cy+0.06, w=card_w-2.4, h=0.22,
              text=_truncate(topic, 38), font_size=8, italic=True, color=WILEY_TEAL_LT,
              align=PP_ALIGN.RIGHT)

        # Scenario title — up to 2 lines, generous height
        title = (s.get("title") or "(untitled)")
        _text(slide, x=cx+0.18, y=cy+0.42, w=card_w-0.36, h=0.5,
              text=_truncate(title, 100), font_size=11, bold=True, color=WILEY_BODY,
              line_spacing=1.2)

        # Description — fixed window leaves room for the footer
        desc = (s.get("description") or s.get("subtitle") or "")
        _text(slide, x=cx+0.18, y=cy+0.92, w=card_w-0.36, h=0.75,
              text=_truncate(desc, 250), font_size=8.5, color=WILEY_MUTED, line_spacing=1.35)

        # Footer line: impact / probability / horizon — anchored at the bottom
        impact = s.get("impact_rating")
        prob = s.get("probability")
        horizon = s.get("time_horizon") or ""
        parts = []
        if impact is not None:
            parts.append(f"Impact {int(round(float(impact)))}/10")
        if prob is not None:
            try:
                parts.append(f"Probability {int(round(float(prob)*100))}%")
            except Exception:
                pass
        if horizon:
            parts.append(horizon)
        if parts:
            # Thin rule above the footer to separate it visually from body
            _rect(slide, x=cx+0.18, y=cy+card_h-0.28, w=card_w-0.36, h=0.01, fill=WILEY_TEAL_LT)
            _text(slide, x=cx+0.18, y=cy+card_h-0.22, w=card_w-0.36, h=0.18,
                  text="   ·   ".join(parts), font_size=7.5, color=WILEY_TEAL,
                  bold=True)


def _add_cross_cutting_themes_slide(prs, themes: list):
    """Cross-cutting strategic themes — mirrors Wiley deck slide 18.

    3-5 short themed paragraphs, each with a bold lead phrase and body.
    """
    if not themes:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Cross-Cutting Strategic Themes",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text="Patterns that span more than one topic in this bundle",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    # White content card
    _rect(slide, x=0.5, y=1.2, w=sw-1.0, h=4.0, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.2, w=0.08, h=4.0, fill=WILEY_TEAL)

    y = 1.45
    for t in themes[:4]:
        lead = (t.get("lead") or "").strip()
        body = (t.get("body") or "").strip()
        _text(slide, x=0.85, y=y, w=sw-1.7, h=0.3,
              text=lead, font_size=12, bold=True, color=WILEY_NAVY)
        _text(slide, x=0.85, y=y+0.3, w=sw-1.7, h=0.6,
              text=body, font_size=10, color=WILEY_BODY, line_spacing=1.4)
        y += 0.95


def _add_executive_decision_framework_slide(prs, priorities: list):
    """Cross-topic Executive Decision Framework — mirrors Wiley deck slide 23.

    Three white vertical cards, alternating teal/navy/teal headers, each
    with a priority headline and 2-3 sentence body. Distinct from the per-
    topic Strategic Recommendations.
    """
    if not priorities:
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Executive Decision Framework",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text="Three strategic priorities for leadership across the portfolio",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    card_palette = [WILEY_TEAL, WILEY_NAVY, WILEY_TEAL]
    card_w = 2.95
    gap = 0.1
    start_x = (sw - (3 * card_w + 2 * gap)) / 2
    card_y = 1.25
    card_h = 4.0

    for i, p in enumerate(priorities[:3]):
        cx = start_x + i * (card_w + gap)
        bar_color = card_palette[i % 3]

        _rect(slide, x=cx, y=card_y, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=cx, y=card_y, w=card_w, h=0.65, fill=bar_color)

        headline = (p.get("headline") or "").strip()
        body = (p.get("body") or "").strip()
        _text(slide, x=cx+0.18, y=card_y+0.13, w=card_w-0.36, h=0.45,
              text=headline, font_size=13, bold=True, color=WHITE, line_spacing=1.15)
        _text(slide, x=cx+0.22, y=card_y+0.85, w=card_w-0.44, h=card_h-1.0,
              text=body, font_size=10, color=WILEY_BODY, line_spacing=1.45)


def _add_next_steps_slide(prs, assessment: dict):
    """Per-topic Next Steps — mirrors Wiley deck slide 24.

    3 numbered actions: large numeral + uppercase category tag + 1-sentence
    action. Pulls from ``assessment.summary['next_steps']``.
    """
    steps = ((assessment.get("summary") or {}).get("next_steps")) or []
    if not steps:
        return

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4,
          text="Next Steps", font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
          text=f"{assessment.get('topic') or '—'} — immediate priorities",
          font_size=11, italic=True, color=WILEY_MUTED)

    y = 1.35
    for i, step in enumerate(steps[:3], 1):
        # Card with large number on left, category + action on right
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=1.15, fill=WILEY_CARD_BG)
        _rect(slide, x=0.5, y=y, w=1.05, h=1.15, fill=WILEY_TEAL)
        _text(slide, x=0.5, y=y+0.2, w=1.05, h=0.8,
              text=f"{i:02d}", font_size=42, bold=True, color=WHITE,
              align=PP_ALIGN.CENTER)
        cat = (step.get("category") or "").strip().upper()
        action = (step.get("action") or "").strip()
        _text(slide, x=1.75, y=y+0.18, w=sw-2.3, h=0.32,
              text=cat, font_size=11, bold=True, color=WILEY_TEAL)
        _text(slide, x=1.75, y=y+0.5, w=sw-2.3, h=0.55,
              text=action, font_size=11.5, color=WILEY_BODY, line_spacing=1.4)
        y += 1.27


def _add_no_prior_slide(prs, assessment: dict, forecast_run: dict):
    """Single-slide deck shown when ``updates_only=true`` was requested but no
    prior live snapshot exists yet for the run. Otherwise we'd 422 and the
    browser would save the JSON body as a broken .pptx."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _rect(slide, x=0, y=0, w=sw, h=5.62, fill=WHITE)
    _rect(slide, x=0, y=0, w=sw, h=0.18, fill=PINK)
    _add_brand_mark(slide, x=0.5, y=0.5, w=1.8, h=0.55)
    _text(slide, x=0.5, y=1.15, w=6.0, h=0.3, text="FORECAST TRACKER · UPDATES",
          font_size=11, bold=True, color=PINK_DEEP)

    topic = assessment.get("topic") or "—"
    _text(slide, x=0.5, y=1.85, w=sw-1.0, h=0.9, text=topic, font_size=30,
          bold=True, color=SLATE_DARK)

    msg = (
        "This is the first assessment snapshot for this forecast — there's no "
        "prior snapshot to diff against yet.\n\n"
        "Updates-only reports compare the current snapshot to the previous one "
        "and surface only what's changed: new evidence, verdict-label flips, "
        "and newly-emerged unanticipated clusters.\n\n"
        "Run another assessment in a few weeks (re-run paired mode from the "
        "Forecast Tracker tab) and the next 'Updates only' export will "
        "contain the delta."
    )
    _text(slide, x=0.5, y=2.85, w=sw-1.0, h=2.0, text=msg, font_size=12,
          color=SLATE_MID, line_spacing=1.4)
    _add_brand_footer(slide, slide_label="No prior snapshot")


def _diff_assessments(current: dict, prior: dict) -> dict:
    """Diff a current vs prior assessment to identify what's changed.

    Returns:
        {
            "prior_assessed_at": str,
            "new_uris": set[str],
            "changed_scenario_keys": set[str],
            "verdict_flips": dict[str, (prior_label, current_label)],
            "new_surprise_labels": set[str],
        }
    """
    prior_uris = set(prior.get("article_uris") or [])
    # Current article uris come from per-scenario top_articles summaries.
    # (The full article-verdicts table isn't carried in the assessment dict,
    # so we approximate "new evidence" by inspecting which scenarios have
    # supports/contradicts articles whose URIs aren't in the prior snapshot.)
    current_uris: set[str] = set()
    new_uris: set[str] = set()
    for v in current.get("scenario_verdicts") or []:
        ta = v.get("top_articles") or {}
        for bucket in ("supports", "contradicts", "neutral"):
            for art in ta.get(bucket) or []:
                u = art.get("article_uri") or art.get("uri")
                if u:
                    current_uris.add(u)
                    if u not in prior_uris:
                        new_uris.add(u)

    # Verdict-label flips per scenario. We track the headline label — which
    # in paired-mode is the baseline-corrected label ("Above/At/Below baseline"),
    # falling back to the raw verdict_label only when no baseline correction
    # is available. This matches what the user sees in the UI.
    prior_bc_per = (
        ((prior.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
    )
    current_bc_per = (
        ((current.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
    )
    prior_labels = {}
    for v in (prior.get("scenario_verdicts") or []):
        key = str(v.get("scenario_idx"))
        prior_labels[key] = (
            (prior_bc_per.get(key) or {}).get("label")
            or v.get("verdict_label")
        )
    verdict_flips: dict = {}
    changed_keys: set = set()
    for v in current.get("scenario_verdicts") or []:
        key = str(v.get("scenario_idx"))
        prior_label = prior_labels.get(key)
        current_label = (
            (current_bc_per.get(key) or {}).get("label")
            or v.get("verdict_label")
        )
        if prior_label and prior_label != current_label and current_label != "Done":
            verdict_flips[key] = (prior_label, current_label)
            changed_keys.add(key)
        # Scenario is also "changed" if any of its top_articles URIs are new
        ta = v.get("top_articles") or {}
        for bucket in ("supports", "contradicts"):
            for art in ta.get(bucket) or []:
                u = art.get("article_uri") or art.get("uri")
                if u and u not in prior_uris:
                    changed_keys.add(key)
                    break
            if key in changed_keys:
                break
        # New scenarios (not present in prior at all)
        if key not in prior_labels:
            changed_keys.add(key)

    # New surprise clusters (by label)
    prior_surprise_labels = {
        (s.get("label") or "").strip()
        for s in (prior.get("surprises") or [])
    }
    new_surprise_labels = {
        (s.get("label") or "").strip()
        for s in (current.get("surprises") or [])
        if (s.get("label") or "").strip()
        and (s.get("label") or "").strip() not in prior_surprise_labels
    }

    return {
        "prior_assessed_at": (
            prior.get("assessed_at").isoformat()
            if hasattr(prior.get("assessed_at"), "isoformat")
            else (prior.get("assessed_at") or "—")
        ),
        "new_uris": new_uris,
        "changed_scenario_keys": changed_keys,
        "verdict_flips": verdict_flips,
        "new_surprise_labels": new_surprise_labels,
    }


# ── Helpers — text shaping + interpretation ───────────────────────────────

def _verdict_explanation(verdict_label: Optional[str], baseline: Optional[dict] = None) -> str:
    if baseline:
        label = baseline.get("label") or ""
        if "Above" in label:
            return (
                "Strengthening. Fresh coverage is amplifying this scenario more "
                "than it was before the forecast was published — genuine new "
                "confirmation, not pre-existing momentum."
            )
        if "Below" in label:
            return (
                "Cooling. The story was hotter at forecast-authoring time than "
                "it is now. The trajectory isn't wrong — it's already crested. "
                "Worth re-pricing how urgent it still feels."
            )
        if "At" in label:
            return (
                "Stable. The trend was already visible when the forecast was "
                "made, and recent coverage is holding it on course without "
                "amplifying or weakening it."
            )
    fallback = {
        "Accelerating": "Activity is positive and milestones are landing — strong evidence the trajectory is materialising.",
        "On-track": "More confirming than contradicting evidence; trend continues.",
        "Stalled": "Roughly equal confirming and contradicting evidence; no clear direction.",
        "Off-track": "More contradicting than confirming evidence in the tracking window.",
        "Inconclusive": "Not enough confident matches to issue a directional finding yet.",
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
