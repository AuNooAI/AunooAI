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

def _estimate_font_scale(text, w_in, h_in, font_size, line_spacing) -> float:
    """Estimate the font-scale (0.55–1.0) needed for ``text`` to fit a box of
    ``w_in`` × ``h_in`` inches at ``font_size`` pt.

    PowerPoint's "shrink text on overflow" only recomputes its scale lazily
    (on open/edit) and stores none by default, so other renderers — PDF
    export, previews, some viewers — show the text at full size and it
    overruns the box. We therefore compute an explicit scale here and bake it
    into the ``normAutofit`` element (see ``_set_autofit_scale``) so the file
    itself carries the shrink. Approximate but conservative: glyph advance for
    the brand sans ≈ 0.50× the point size; ~10% of each wrapped line is slack.
    """
    if not text or w_in <= 0 or h_in <= 0 or font_size <= 0:
        return 1.0
    ls = line_spacing or 1.2
    char_w_in = (font_size * 0.50) / 72.0
    line_h_in = (font_size * ls) / 72.0
    if char_w_in <= 0 or line_h_in <= 0:
        return 1.0
    chars_per_line = max(1.0, w_in / char_w_in)
    n_lines = max(1.0, h_in / line_h_in)
    capacity = chars_per_line * n_lines * 0.90
    # Each hard newline starts a fresh line that's usually only half-full.
    n = len(text) + text.count("\n") * int(chars_per_line * 0.5)
    if n <= capacity:
        return 1.0
    import math
    return max(0.55, min(1.0, math.sqrt(capacity / float(n))))


def _set_autofit_scale(tf, scale: float):
    """Bake an explicit ``fontScale`` (+ modest line-spacing reduction) into
    the text frame's ``normAutofit`` so the shrink renders everywhere, not
    only where PowerPoint recomputes it."""
    if scale >= 0.999:
        return
    try:
        from pptx.oxml.ns import qn
        bodyPr = tf._txBody.find(qn('a:bodyPr'))
        if bodyPr is None:
            return
        na = bodyPr.find(qn('a:normAutofit'))
        if na is None:
            na = bodyPr.makeelement(qn('a:normAutofit'), {})
            bodyPr.insert(0, na)
        na.set('fontScale', str(int(round(scale * 100000))))
        if scale < 0.85:
            na.set('lnSpcReduction', str(int(round(min(0.20, 1.0 - scale) * 100000))))
    except Exception:
        pass


def _text(slide, *, x, y, w, h, text, font_size=10.0, bold=False, italic=False,
          color=TITLE_DARK, align=PP_ALIGN.LEFT, font_name=BODY_FONT,
          line_spacing: Optional[float] = None,
          anchor=MSO_ANCHOR.TOP,
          shrink_to_fit: bool = True):
    """Add a text box. ``text`` may contain newlines — each becomes a paragraph
    so paragraph-level alignment/spacing applies uniformly.

    ``shrink_to_fit`` enables PowerPoint's "Shrink text on overflow" autofit
    (``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE``) on the resulting text frame. With it on,
    long content stays fully visible at a slightly smaller font instead of
    being chopped by the caller's ``_truncate``. Default is on because the
    deck's biggest legibility complaint historically was mid-sentence
    ellipsis on every signal/imperative/description. Disable explicitly for
    fixed-size titles where a smaller fallback font would look broken.
    """
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    if shrink_to_fit:
        try:
            from pptx.enum.text import MSO_AUTO_SIZE
            # "Shrink text on overflow" — the member is TEXT_TO_FIT_SHAPE.
            # (A previous TEXT_TO_SHAPE typo raised AttributeError here and
            # was silently swallowed, so autofit never actually applied and
            # long content overran the box.)
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except Exception:
            # If the python-pptx build doesn't expose TEXT_TO_SHAPE for some
            # reason, fall back silently. word_wrap=True is still applied so
            # text wraps within the box, and the caller's _truncate cap
            # (when used) still provides a last-resort safety net.
            pass
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
    # Bake an explicit shrink scale into the autofit so overflowing text is
    # actually smaller in the saved file (not reliant on the viewer
    # recomputing PowerPoint's autofit).
    if shrink_to_fit and (text or "").strip():
        _set_autofit_scale(tf, _estimate_font_scale(text, w, h, font_size, line_spacing))
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


def _add_left_rail(slide, *, horizon: str, consensus_pct: Optional[float],
                   topic: Optional[str] = None):
    """Dark-navy rail with H-code, label, consensus chip, and AunooAI mark.

    ``topic``, when supplied, renders below the system label so the reader
    keeps the topic context on every per-scenario slide — without it, a deck
    full of "H1 / DECLINING SYSTEM" rails reads identically across topics and
    the reader loses track of which topic they're inside.
    """
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

    # Topic anchor — keeps the reader oriented when paging through ~25
    # scenario slides across 5 topics in a bundle.
    if topic:
        _text(slide, x=0.1, y=3.2, w=1.4, h=0.2, text="TOPIC",
              font_size=7, bold=True, color=accent, align=PP_ALIGN.CENTER)
        _text(slide, x=0.1, y=3.4, w=1.4, h=1.05, text=topic,
              font_size=9, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
              line_spacing=1.15)

    # NOTE: the "consensus %" chip that used to sit here was removed. It
    # stamped an article-framing ratio on every scenario slide as if it
    # were a forecast-confidence score — exactly the overclaim the customer
    # rejected. The horizon code + system label above carry the legitimate
    # Three Horizons positioning. (consensus_pct param kept for signature
    # stability; intentionally unused.)

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


def _calibration_read(basis_pct, n_confirm: int, n_counter: int):
    """Classify a trend on the consensus×evidence matrix → (text, category).

    The product's value is the DIVERGENCE between what sources expected
    (the basis consensus) and what the evidence (named events) shows:
    a high-consensus claim with no confirming evidence is the crowd being
    confidently wrong; a low-consensus outlier with confirming evidence is
    a signal the crowd missed. Both are the high-value cells.
    """
    hi, lo = 60.0, 40.0
    b = basis_pct if isinstance(basis_pct, (int, float)) else None

    if n_confirm == 0 and n_counter == 0:
        return ("Too early — no confirming or countering events yet this cycle.",
                "early")

    confirming_net = n_confirm - n_counter

    if b is not None and b >= hi:
        if n_confirm > 0 and n_counter == 0:
            return ("Consensus holding — sources expected this and the evidence "
                    "is bearing it out.", "holding")
        if confirming_net <= 0:
            return ("Consensus unconfirmed — sources expected this, but the "
                    "evidence isn't showing up. The crowd may be wrong here "
                    "(watch).", "crowd_wrong")
        return ("Consensus largely holding, with some counter-evidence — "
                "watch the dissent.", "holding")

    if b is not None and b <= lo:
        if n_confirm > n_counter:
            return ("Outlier confirming — few sources expected this, but the "
                    "evidence is accumulating. An early signal the consensus "
                    "missed.", "outlier_confirming")
        return ("Outlier not bearing out — neither widely expected nor "
                "materialising.", "noise")

    # Mid-consensus or unknown basis.
    if confirming_net > 0:
        return ("Evidence leaning toward this trend.", "leaning")
    if confirming_net < 0:
        return ("Counter-evidence outweighs confirming — trend in doubt.",
                "doubt")
    return ("Contested — evidence is split.", "contested")


_READ_COLOR = {
    "crowd_wrong": AMBER_DEEP,
    "outlier_confirming": GREEN_DEEP,
    "doubt": CORAL,
    "holding": SLATE_MID,
    "leaning": SLATE_MID,
    "noise": SLATE_LIGHT,
    "contested": SLATE_MID,
    "early": SLATE_LIGHT,
}


def _fmt_event_line(e: dict) -> str:
    actor = (e.get("actor") or "").strip()
    action = (e.get("action") or "").strip()
    subject = (e.get("subject") or "").strip()
    if subject and subject.lower() == actor.lower():
        subject = ""
    mag = ""
    if e.get("magnitude_value") is not None:
        unit = e.get("magnitude_unit") or ""
        mag = f" ({e['magnitude_value']:g} {unit})".replace("  ", " ").replace(" )", ")")
    date = e.get("event_date") or ""
    date = f" — {str(date)[:10]}" if date else ""
    return (" ".join(p for p in (actor, action, subject) if p) + mag + date).strip()


def _add_scenario_slide(prs, verdict: dict, baseline: Optional[dict],
                        confirming_events: Optional[list] = None,
                        countering_events: Optional[list] = None,
                        topic: Optional[str] = None):
    """Per-trend evidence ledger: the scenario is a CLAIM; the consensus is
    the forecast basis (what sources expected); named events are the test of
    whether it's bearing out.

        TREND (claim) + horizon
        Forecast basis: X% of sources framed this as likely at forecast time
        Outlier watch: <contrarian alternative>
        NEW EVIDENCE SINCE FORECAST (confirming): • event — date
        COUNTER-EVIDENCE: • event — date
        READ: <consensus×evidence calibration>

    No drift deltas, no Cooling/Strengthening verdict, no current_consensus_pct
    — the basis % is point-in-time, the test is events.
    """
    confirming_events = confirming_events or []
    countering_events = countering_events or []
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}

    horizon = (verdict.get("horizon_type") or "h1")
    basis = deck_info.get("consensus_pct")
    scenario_name = (deck_info.get("deck_scenario_name")
                     or verdict.get("scenario_title") or "—")

    _add_left_rail(slide, horizon=horizon, consensus_pct=None, topic=topic)

    # ── Title block ───────────────────────────────────────────────────
    title_lines = _split_title(scenario_name, max_chars=38)
    _text(slide, x=1.9, y=0.12, w=7.9, h=0.42, text=title_lines[0],
          font_size=17, bold=True, color=SLATE_DARK)
    if len(title_lines) > 1:
        _text(slide, x=1.9, y=0.5, w=7.9, h=0.42, text=title_lines[1],
              font_size=17, bold=True, color=SLATE_DARK)
    _text(slide, x=1.9, y=0.93, w=7.9, h=0.2, text=_horizon_full_label(horizon),
          font_size=8.5, bold=True, color=SLATE_LIGHT)

    # ── Forecast basis (the hypothesis — point-in-time, not a drift) ──
    y = 1.2
    if isinstance(basis, (int, float)):
        _text(slide, x=1.9, y=y, w=7.9, h=0.24,
              text=f"FORECAST BASIS  ·  {int(basis)}% of sources framed this as likely at forecast time",
              font_size=9, bold=True, color=TEAL)
        y += 0.3
    # Outlier watch — the contrarian alternative the basis might be missing.
    primary = (deck_info.get("primary_signal") or "").strip()
    if primary:
        _text(slide, x=1.9, y=y, w=7.9, h=0.4,
              text=f"Outlier watch: {_truncate(primary, 150)}",
              font_size=8.5, italic=True, color=SLATE_MID, line_spacing=1.2)
        y += 0.46

    # ── New evidence since forecast (confirming) ──────────────────────
    _text(slide, x=1.9, y=y, w=7.9, h=0.22,
          text="NEW EVIDENCE SINCE FORECAST  ·  confirming",
          font_size=8.5, bold=True, color=GREEN_DEEP)
    y += 0.26
    if confirming_events:
        for e in confirming_events[:4]:
            _rect(slide, x=1.9, y=y+0.03, w=0.06, h=0.18, fill=GREEN_DEEP)
            _text(slide, x=2.05, y=y, w=sw-2.55, h=0.36,
                  text=_truncate(_fmt_event_line(e), 130), font_size=9,
                  color=SLATE_BLACK, line_spacing=1.15)
            y += 0.4
    else:
        _text(slide, x=2.05, y=y, w=sw-2.55, h=0.24,
              text="No confirming events attributed this cycle.",
              font_size=8.5, italic=True, color=SLATE_LIGHT)
        y += 0.3

    # ── Counter-evidence ──────────────────────────────────────────────
    _text(slide, x=1.9, y=y, w=7.9, h=0.22,
          text="COUNTER-EVIDENCE", font_size=8.5, bold=True, color=CORAL)
    y += 0.26
    if countering_events:
        for e in countering_events[:3]:
            _rect(slide, x=1.9, y=y+0.03, w=0.06, h=0.18, fill=CORAL)
            _text(slide, x=2.05, y=y, w=sw-2.55, h=0.36,
                  text=_truncate(_fmt_event_line(e), 130), font_size=9,
                  color=SLATE_BLACK, line_spacing=1.15)
            y += 0.4
    else:
        _text(slide, x=2.05, y=y, w=sw-2.55, h=0.24,
              text="None this cycle.", font_size=8.5, italic=True,
              color=SLATE_LIGHT)
        y += 0.3

    # ── READ — the calibration call (pinned near the bottom) ──────────
    read_text, category = _calibration_read(
        basis, len(confirming_events), len(countering_events))
    read_color = _READ_COLOR.get(category, SLATE_MID)
    ry = 5.0
    _rect(slide, x=1.9, y=ry, w=7.9, h=0.012, fill=RULE_GRAY)
    _text(slide, x=1.9, y=ry+0.05, w=0.7, h=0.22, text="READ",
          font_size=8.5, bold=True, color=read_color)
    _text(slide, x=2.55, y=ry+0.05, w=sw-3.05, h=0.5,
          text=read_text, font_size=9.5, bold=True, color=read_color,
          line_spacing=1.15)


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
            _add_scenario_slide(prs, v, baseline, topic=assessment.get("topic"))

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
    # Truncate long scenario names so they don't wrap into the chips below.
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.85,
          text=_truncate(name, 110),
          font_size=18, bold=True, color=WILEY_BODY)

    # Big "Was → Now" panel — render customer-facing labels with internal colors.
    # Kept inside the left ~6.1" of the slide so the Confirmation Δ block on the
    # right has clear width.
    _verdict_chip(slide, x=0.5, y=1.85, w=2.4, h=0.55,
                  label=_customer_label(prior_label),
                  color=_baseline_color(prior_label))
    _text(slide, x=3.0, y=1.93, w=0.6, h=0.4, text="→",
          font_size=22, bold=True, color=SLATE_DARK, align=PP_ALIGN.CENTER)
    _verdict_chip(slide, x=3.7, y=1.85, w=2.4, h=0.55,
                  label=_customer_label(current_label),
                  color=_baseline_color(current_label))

    # Confirmation-strength change on the right — explicit width cap so the
    # ±NN.NN% number never bleeds past the slide edge at large negative deltas.
    was_net = (prior_baseline or {}).get("net_rate")
    now_net = (baseline or {}).get("net_rate")
    if was_net is not None or now_net is not None:
        delta = (now_net or 0) - (was_net or 0)
        sign = "+" if delta > 0 else ""
        _text(slide, x=6.3, y=1.85, w=3.2, h=0.22,
              text="CONFIRMATION Δ", font_size=8.5, bold=True,
              color=PINK_DEEP, align=PP_ALIGN.LEFT)
        was_s = f"{(was_net or 0)*100:.2f}%" if was_net is not None else "—"
        now_s = f"{(now_net or 0)*100:.2f}%" if now_net is not None else "—"
        _text(slide, x=6.3, y=2.05, w=3.2, h=0.2,
              text=f"{was_s} → {now_s}", font_size=10, color=SLATE_MID,
              align=PP_ALIGN.LEFT)
        delta_color = GREEN_DEEP if delta > 0 else (RED_DEEP if delta < 0 else SLATE_LIGHT)
        _text(slide, x=6.3, y=2.25, w=3.2, h=0.35,
              text=f"{sign}{delta*100:.2f}%",
              font_size=20, bold=True, color=delta_color, align=PP_ALIGN.LEFT)

    # The 5.625" slide already gives us roughly 3" of vertical space below
    # the chips (y=2.65 onward). Budget: narrative gets the larger half,
    # evidence the smaller. If narrative is present, it's truncated to fit
    # in 1.5" — previously h=2.0 + evidence underneath would run past the
    # slide bottom on every flip with a cached summary_md narrative.
    narrative = (verdict.get("summary_md") or "").strip()
    sup = ((verdict.get("top_articles") or {}).get("supports") or [])[:2]
    con = ((verdict.get("top_articles") or {}).get("contradicts") or [])[:1]
    n_evidence_lines = len(sup) + len(con)
    evidence_block_h = (0.25 + 0.05 + 0.32 * n_evidence_lines) if n_evidence_lines else 0.0
    # Slide bottom is 5.625"; leave 0.25" for the brand footer.
    slide_bottom_limit = 5.4
    y = 2.65
    if narrative:
        narrative_top = y + 0.4
        narrative_h = max(0.6, slide_bottom_limit - evidence_block_h - narrative_top - 0.15)
        # 11pt-ish text in a 0.6"-2.0" tall, 9.0"-wide box holds roughly
        # 90 chars/line × N lines. Truncate so wrap doesn't overrun.
        approx_chars_per_line = 100
        max_chars = int(narrative_h / 0.18) * approx_chars_per_line
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=0.04, fill=RULE_GRAY)
        _text(slide, x=0.5, y=y+0.1, w=sw-1.0, h=0.25,
              text="WHAT HAPPENED", font_size=8.5, bold=True, color=PINK_DEEP)
        _text(slide, x=0.5, y=narrative_top, w=sw-1.0, h=narrative_h,
              text=_truncate(narrative, max_chars),
              font_size=10.5, color=SLATE_BLACK, line_spacing=1.3)
        y = narrative_top + narrative_h + 0.1

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


def _add_briefing_synthesis_slide(prs, assessment: dict, *, topic_idx: Optional[int] = None):
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

    # Title row (no header bar — title sits directly on the bg, Wiley-style).
    # "Topic N" prefix ties the section back to the numbered ToC.
    title = (f"Topic {topic_idx} · Briefing Synthesis"
             if topic_idx is not None else "Briefing Synthesis")
    _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4, text=title,
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.35,
          text=briefing.get("headline") or (assessment.get("topic") or "—"),
          font_size=12, italic=True, color=WILEY_MUTED)

    # The "Original consensus X% → current Y%" drift strip was removed —
    # that re-counted framing ratio over time was the rejected scorecard.
    # The forecast-basis % now lives (point-in-time) on each per-scenario
    # evidence-ledger slide instead.

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

    # Insights 1-3 (STRONGEST CONFIRMATION / STRONGEST COOLING / BIGGEST
    # STATUS CHANGE) were removed: they reported "confirmation Δ %" and
    # verdict flips ("Cooling → On-track between snapshots"), scoring the
    # futures-cone scenarios as a back-test the customer rejected. The
    # emerging-theme and evidence-gap insights below are the legitimate,
    # non-scorecard observations.

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

    # Card body spans y=1.05 → 5.05 (4.0" tall). Footer is at y=5.18.
    # Findings need to fit within that band — header is at y=1.18 + label at
    # y=1.55, so usable text space is ~5.05 - 1.55 = 3.50". With dynamic
    # spacing the slide can comfortably show 4 errors at 2 lines each plus
    # the warnings footnote, or fewer errors with longer bodies.
    y = 1.55
    card_bottom = 5.05
    # Each finding body is truncated to a length that fits the available
    # width at font_size=9.5 (~110 chars/line) on at most 2 wrapped lines.
    # Past the truncation length the box would otherwise spill into the
    # next finding's header — the bug visible on the screenshot.
    body_max_chars = 220
    body_w = sw - 1.55
    chars_per_line = 110

    for f in errors[:5]:
        sev = (f.get("severity") or "").upper()
        artefact = f.get("artefact_key") or ""
        raw_finding = f.get("finding") or ""
        finding = _truncate(raw_finding, body_max_chars)

        # Estimate wrapped lines so the slot per finding adapts to the
        # length. Two lines = ~0.42" at 9.5pt with line_spacing=1.3.
        approx_lines = max(1, min(3, (len(finding) + chars_per_line - 1) // chars_per_line))
        body_h = 0.22 * approx_lines + 0.04
        # Header row above the body
        next_y = y + 0.22 + body_h + 0.18  # +0.18 gap between findings
        # If we'd overflow the card, stop and roll the rest into the
        # warnings-style footnote so nothing collides with the footer.
        if next_y > card_bottom:
            break

        _text(slide, x=0.85, y=y, w=0.8, h=0.2,
              text=sev, font_size=8, bold=True, color=RED_DEEP)
        _text(slide, x=1.7, y=y, w=sw-2.4, h=0.2,
              text=artefact, font_size=8, color=WILEY_TEAL)
        _text(slide, x=0.85, y=y+0.22, w=body_w, h=body_h,
              text=finding, font_size=9.5, color=WILEY_BODY, line_spacing=1.3)
        y = next_y

    rendered_errors = min(len(errors), 5)
    overflow_errors = max(0, len(errors) - rendered_errors)
    remaining_warnings = len(warnings)
    footnote_parts = []
    if overflow_errors:
        footnote_parts.append(
            f"{overflow_errors} additional error{'' if overflow_errors == 1 else 's'}"
        )
    if remaining_warnings:
        footnote_parts.append(
            f"{remaining_warnings} warning{'' if remaining_warnings == 1 else 's'}"
        )
    if footnote_parts and y + 0.3 <= card_bottom:
        _text(slide, x=0.85, y=y, w=sw-1.55, h=0.25,
              text=f"Plus {' and '.join(footnote_parts)} — see the Wiley Deliverables panel.",
              font_size=9, italic=True, color=WILEY_MUTED)

    _text(slide, x=0.5, y=5.18, w=sw-1.0, h=0.22,
          text="Resolve in the Wiley Deliverables panel — approve overrides or request fix.",
          font_size=9, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)


def _add_executive_summary_letter_slide(prs, exec_summary: dict, period_label: str):
    """Executive Summary LETTER — sits at slide 2, immediately after the cover.

    v2: multi-paragraph briefing rendered with inline-bold section headers
    (``**The bottom line.**`` → bold run + body). Matches the human-authored
    reference in ``docs/Wiley_Horizons_Executive_Summary_May2026.docx`` —
    each paragraph leads with a bolded section title followed by 80–130
    words of concrete prose with named actors, % numbers, and quoted
    briefing lines.
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
          text="Executive Summary", font_size=24, bold=True, color=WILEY_NAVY,
          shrink_to_fit=False)
    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.3,
          text=period_label, font_size=11, italic=True, color=WILEY_MUTED,
          shrink_to_fit=False)

    # Letter card. The body grew from ~6-sentence single paragraph to a
    # 5-section briefing in the prompt v2 rewrite, so the card needs to
    # be taller and the font slightly smaller. shrink_to_fit on _text
    # also catches anything that still overflows.
    card_top = 1.35
    card_h = 3.75
    _rect(slide, x=0.5, y=card_top, w=sw-1.0, h=card_h, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=card_top, w=0.08, h=card_h, fill=WILEY_TEAL)

    _render_markdown_paragraphs(
        slide,
        x=0.85, y=card_top + 0.15, w=sw-1.55, h=card_h - 0.30,
        body=letter,
        font_size=10.5,
        color=WILEY_BODY,
        line_spacing=1.35,
    )

    # Signoff
    _text(slide, x=0.5, y=5.18, w=sw-1.0, h=0.25,
          text="— " + signoff, font_size=10, italic=True, color=WILEY_TEAL,
          align=PP_ALIGN.RIGHT, shrink_to_fit=False)


def _add_expert_commentary_slide(prs, commentary: str, period_label: str):
    """Expert view on the quarter's emerging themes — sits just after the
    Executive Summary letter. Analyst-editable prose generated by the
    expert-commentary agent; renders only when present."""
    if not (commentary or "").strip():
        return
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.4, w=sw-1.0, h=0.45,
          text="Expert View — Emerging Themes", font_size=24, bold=True,
          color=WILEY_NAVY, shrink_to_fit=False)
    _text(slide, x=0.5, y=0.95, w=sw-1.0, h=0.3,
          text=f"{period_label} · analyst interpretation of this quarter's emerging themes",
          font_size=11, italic=True, color=WILEY_MUTED, shrink_to_fit=False)

    card_top = 1.35
    card_h = 3.75
    _rect(slide, x=0.5, y=card_top, w=sw-1.0, h=card_h, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=card_top, w=0.08, h=card_h, fill=WILEY_TEAL)
    _render_markdown_paragraphs(
        slide, x=0.85, y=card_top + 0.2, w=sw-1.55, h=card_h - 0.4,
        body=commentary, font_size=12, color=WILEY_BODY, line_spacing=1.45,
    )


def _render_markdown_paragraphs(slide, *, x, y, w, h, body, font_size=10.5,
                                color=None, line_spacing=1.35):
    """Render a body of text with **inline bold** markers and double-newline
    paragraph breaks into a single text frame.

    Inputs like ``**Section.** Body sentence.`` become a paragraph whose
    leading "Section." is bold and the rest is regular weight. Used by
    the executive summary letter slide where the agent emits a
    multi-paragraph briefing with bolded section headers.
    """
    import re as _re
    from pptx.util import Inches, Pt, Emu
    from pptx.enum.text import MSO_ANCHOR

    if color is None:
        color = WILEY_BODY

    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    try:
        from pptx.enum.text import MSO_AUTO_SIZE
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)

    # Split on blank lines to identify paragraphs. Within each paragraph,
    # we still honour single newlines as soft line breaks via separate
    # paragraphs (the renderer doesn't expose <w:br/> easily) but the
    # agent prompt instructs the model to use \n\n between sections, so
    # a paragraph here is one section of the letter.
    paragraphs = [p.strip() for p in _re.split(r"\n\s*\n", body or "") if p.strip()]
    bold_re = _re.compile(r"\*\*(.+?)\*\*")

    for pi, para_text in enumerate(paragraphs):
        p = tf.paragraphs[0] if pi == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = line_spacing
        if pi > 0:
            # Visual gap between paragraphs.
            p.space_before = Pt(font_size * 0.55)

        cursor = 0
        for m in bold_re.finditer(para_text):
            if m.start() > cursor:
                _add_run(p, para_text[cursor:m.start()], font_size, color, bold=False)
            _add_run(p, m.group(1), font_size, color, bold=True)
            cursor = m.end()
        if cursor < len(para_text):
            _add_run(p, para_text[cursor:], font_size, color, bold=False)

    # Bake an explicit shrink scale in — paragraph gaps cost vertical room, so
    # add the inter-paragraph spacing to the effective length estimate.
    eff = (body or "") + "\n" * max(0, len(paragraphs) - 1) * 2
    _set_autofit_scale(tf, _estimate_font_scale(eff, w, h, font_size, line_spacing))


def _add_run(paragraph, text, font_size, color, *, bold=False, italic=False,
             font_name=BODY_FONT):
    """Add a styled run to an existing paragraph. Used by the markdown
    paragraph renderer to mix bold and regular weight inline."""
    from pptx.util import Pt
    r = paragraph.add_run()
    r.text = text
    r.font.name = font_name
    r.font.size = Pt(font_size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = color


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
          text="Key signals and the strategic imperative for each topic in this bundle",
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

        # White card with teal header bar
        _rect(slide, x=cx, y=cy, w=card_w, h=card_h, fill=WILEY_CARD_BG)
        _rect(slide, x=cx, y=cy, w=card_w, h=0.42, fill=WILEY_TEAL)
        _text(slide, x=cx+0.15, y=cy+0.07, w=card_w-0.3, h=0.3,
              text=_truncate(topic, 50), font_size=11.5, bold=True, color=WHITE)

        # The "Original consensus X% → Current Y%" drift line was removed:
        # it reported article-framing ratios as forecast accuracy. The card
        # now leads straight into the key signals + strategic imperative,
        # which are the qualitative foresight content.
        y_signals = cy + 0.55

        # Signal/imperative truncation lengths scale with card width: a
        # 3-up row with narrower cards needs harsher trims to avoid overrun.
        sig_max = max(50, int(card_w * 22))
        imp_max = max(80, int(card_w * 32))

        # Reserve the bottom of the card for the strategic imperative
        # (rule-line + label + one wrapped line at 8.5pt italic ≈ 0.55").
        # The signals block has to fit above that reservation, so cap how
        # many signals we render based on remaining vertical space. Before
        # the fix, two signals would render through the imperative band.
        imp_block_h = 0.55 if imperative else 0.0
        signals_top = y_signals + 0.22  # below the "KEY SIGNALS" label
        signals_bottom_limit = cy + card_h - imp_block_h - 0.05  # 0.05 safety
        per_signal_h = 0.36
        max_signals = max(1, int((signals_bottom_limit - signals_top) // per_signal_h))

        if signals:
            _text(slide, x=cx+0.18, y=y_signals, w=card_w-0.3, h=0.22,
                  text="KEY SIGNALS", font_size=8, bold=True, color=WILEY_NAVY)
            sy = signals_top
            for sig in signals[:max_signals]:
                _rect(slide, x=cx+0.2, y=sy+0.07, w=0.05, h=0.18, fill=WILEY_TEAL)
                _text(slide, x=cx+0.32, y=sy, w=card_w-0.45, h=per_signal_h-0.02,
                      text=_truncate(sig, sig_max), font_size=9, color=WILEY_BODY,
                      line_spacing=1.3)
                sy += per_signal_h

        # Strategic imperative pinned to the card bottom.
        if imperative:
            iy = cy + card_h - imp_block_h
            _rect(slide, x=cx+0.18, y=iy, w=card_w-0.36, h=0.012, fill=RULE_GRAY)
            _text(slide, x=cx+0.18, y=iy+0.04, w=card_w-0.36, h=0.18,
                  text="STRATEGIC IMPERATIVE", font_size=7.5, bold=True, color=WILEY_NAVY)
            _text(slide, x=cx+0.18, y=iy+0.22, w=card_w-0.36, h=0.3,
                  text=_truncate(imperative, imp_max), font_size=8.5, italic=True,
                  color=WILEY_BODY, line_spacing=1.3)


def _add_black_swans_slide(prs, eos_per_topic: dict):
    """Cross-topic Black Swans & Wild Card Scenarios.

    Two scenarios per slide, each in a full-height card, so the complete
    trajectory/mechanism narrative is readable rather than crammed into a
    2×2 grid (where the ~1,000-char descriptions had to shrink to ~5pt or
    overran the card). Paginates across slides for the top scenarios.
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
    top = aggregated[:4]

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

    sw = 10.0
    card_w = 4.55
    gap_x = 0.1
    start_x = 0.5
    card_top = 1.15
    card_h = 4.30

    # Two full-height cards per slide; paginate for the rest.
    for page_start in range(0, len(top), 2):
        page = top[page_start:page_start + 2]
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _add_bg_image(slide, WILEY_BG_SOFT)

        title = "Black Swans & Wild Card Scenarios"
        if page_start > 0:
            title += " (continued)"
        _text(slide, x=0.5, y=0.2, w=sw-1.0, h=0.4, text=title,
              font_size=22, bold=True, color=WILEY_NAVY, shrink_to_fit=False)
        _text(slide, x=0.5, y=0.7, w=sw-1.0, h=0.3,
              text="High-impact, low-probability scenarios that could reshape the landscape",
              font_size=10.5, italic=True, color=WILEY_MUTED)

        for j, (_score, topic, s) in enumerate(page):
            cx = start_x + j * (card_w + gap_x)
            cy = card_top
            cat = (s.get("category") or "wild_card").lower()
            cat_color = CATEGORY_COLOR.get(cat, WILEY_TEAL)
            cat_label = CATEGORY_DISPLAY.get(cat, cat.upper())

            _rect(slide, x=cx, y=cy, w=card_w, h=card_h, fill=WILEY_CARD_BG, line=WILEY_TEAL_LT)
            _rect(slide, x=cx, y=cy, w=card_w, h=0.34, fill=cat_color)
            _text(slide, x=cx+0.15, y=cy+0.06, w=2.0, h=0.22,
                  text=cat_label, font_size=8.5, bold=True, color=WHITE)
            _text(slide, x=cx+2.2, y=cy+0.06, w=card_w-2.4, h=0.22,
                  text=topic, font_size=8, italic=True, color=WILEY_TEAL_LT,
                  align=PP_ALIGN.RIGHT)

            # Scenario title.
            _text(slide, x=cx+0.18, y=cy+0.42, w=card_w-0.36, h=0.66,
                  text=(s.get("title") or "(untitled)"), font_size=12, bold=True,
                  color=WILEY_BODY, line_spacing=1.15)

            # Full description fills the card down to the footer — no truncation;
            # the baked fontScale shrinks only if it genuinely overflows.
            desc = (s.get("description") or s.get("subtitle") or "")
            desc_top = cy + 1.18
            # End the description well clear of the footer band (rule sits at
            # cy+card_h-0.30) so the last line never collides with the
            # impact/horizon line.
            desc_h = card_h - 1.18 - 0.58
            _text(slide, x=cx+0.18, y=desc_top, w=card_w-0.36, h=desc_h,
                  text=desc, font_size=9, color=WILEY_MUTED, line_spacing=1.32)

            # Footer line: impact / probability / horizon — anchored at the bottom.
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
                _rect(slide, x=cx+0.18, y=cy+card_h-0.30, w=card_w-0.36, h=0.01, fill=WILEY_TEAL_LT)
                _text(slide, x=cx+0.18, y=cy+card_h-0.24, w=card_w-0.36, h=0.2,
                      text="   ·   ".join(parts), font_size=8, color=WILEY_TEAL,
                      bold=True, shrink_to_fit=False)


def _add_whats_changed_section_slide(prs, whats_changed: dict, *,
                                     period_label: str,
                                     prior_period_label: str = None):
    """The honest "What's Changed" section — four signals in priority order:

        1. Named events this quarter (factual ground-truth from extraction)
        2. Scenarios that moved in our framing (Three Horizons drift)
        3. New on the watch (emerging themes from discovery)
        4. Where press attention shifted (labelled AS press attention)

    Events are the priority and always shown; the three qualitative signals
    share the right column and drop from the bottom if absent. This replaces
    the retired Tracker scorecard as the deck's "what changed" view — facts
    and labelled discourse, never "the forecast is playing out".
    """
    wc = whats_changed or {}
    events = [e for e in (wc.get("events") or []) if str(e).strip()]
    drift = [e for e in (wc.get("scenario_drift") or []) if str(e).strip()]
    emerging = [e for e in (wc.get("emerging") or []) if str(e).strip()]
    coverage = [e for e in (wc.get("coverage_shifts") or []) if str(e).strip()]

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    since = f" Since {prior_period_label}" if prior_period_label else ""
    _text(slide, x=0.5, y=0.2, w=sw - 1.0, h=0.4,
          text=f"What's Changed{since}",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw - 1.0, h=0.3,
          text="Named events, scenario drift, and where coverage moved — "
               "facts and attention, not forecast scoring.",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    # Empty-state — honest, never a blank slide.
    if not (events or drift or emerging or coverage):
        _rect(slide, x=0.5, y=1.2, w=sw - 1.0, h=2.0, fill=WILEY_CARD_BG)
        _rect(slide, x=0.5, y=1.2, w=0.08, h=2.0, fill=WILEY_TEAL)
        _text(slide, x=0.85, y=1.5, w=sw - 1.7, h=1.4,
              text="No new headline events confirmed across the portfolio this "
                   "quarter. See the per-topic sections for scenario detail and "
                   "emerging themes.",
              font_size=12, color=WILEY_BODY, line_spacing=1.4)
        return

    # Adaptive layout that FILLS the slide regardless of which signals have
    # data. Events are usually the bulk; drift/emerging/coverage are often
    # sparse or empty — so events get a full-width, two-column card and only
    # the populated qualitative signals appear as a bottom strip. No reserved
    # empty regions.
    qual_blocks = [
        ("SCENARIOS THAT MOVED IN OUR FRAMING", drift),
        ("NEW ON THE WATCH", emerging),
        ("WHERE PRESS ATTENTION SHIFTED", coverage),
    ]
    active_qual = [(t, items) for (t, items) in qual_blocks if items]

    full_w = sw - 1.0
    left_x = 0.5
    top_y = 1.2
    total_h = 4.15
    strip_h = 1.15 if active_qual else 0.0
    events_h = total_h - (strip_h + 0.15 if active_qual else 0.0)

    # ── Named events — full width, two columns, fills the card ────────
    if events:
        _rect(slide, x=left_x, y=top_y, w=full_w, h=events_h, fill=WILEY_CARD_BG)
        _rect(slide, x=left_x, y=top_y, w=0.08, h=events_h, fill=WILEY_TEAL)
        _text(slide, x=left_x + 0.2, y=top_y + 0.1, w=full_w - 0.35, h=0.25,
              text="NAMED EVENTS THIS QUARTER", font_size=9, bold=True,
              color=WILEY_TEAL)
        body_top = top_y + 0.42
        body_h = events_h - 0.5
        col_gap = 0.3
        col_w = (full_w - 0.5 - col_gap) / 2
        col_x = [left_x + 0.2, left_x + 0.2 + col_w + col_gap]
        # Show as many as fit: ~7 rows/column at a comfortable row height.
        per_col = max(6, int(body_h // 0.56))
        cap = per_col * 2
        shown = events[:cap]
        # Split down the columns (first half left, second half right).
        half = (len(shown) + 1) // 2
        cols = [shown[:half], shown[half:]]
        row_h = min(0.56, body_h / max(half, 1))
        for ci, colitems in enumerate(cols):
            ey = body_top
            for ev in colitems:
                _rect(slide, x=col_x[ci], y=ey + 0.03, w=0.05, h=0.15, fill=WILEY_TEAL)
                _text(slide, x=col_x[ci] + 0.13, y=ey, w=col_w - 0.18, h=row_h - 0.02,
                      text=_truncate(ev, 95), font_size=8.8, color=WILEY_BODY,
                      line_spacing=1.1)
                ey += row_h
        if len(events) > len(shown):
            _text(slide, x=left_x + 0.2, y=top_y + events_h - 0.24,
                  w=full_w - 0.4, h=0.2,
                  text=f"+ {len(events) - len(shown)} further named events this quarter",
                  font_size=7.5, italic=True, color=WILEY_MUTED, align=PP_ALIGN.RIGHT)

    # ── Bottom strip: only the qualitative signals that have data ─────
    if active_qual:
        sy = top_y + events_h + 0.15
        n = len(active_qual)
        gap = 0.2
        cw = (full_w - (n - 1) * gap) / n
        for i, (title, items) in enumerate(active_qual):
            cx = left_x + i * (cw + gap)
            _rect(slide, x=cx, y=sy, w=cw, h=strip_h, fill=WILEY_CARD_BG)
            _rect(slide, x=cx, y=sy, w=0.08, h=strip_h, fill=WILEY_NAVY)
            _text(slide, x=cx + 0.16, y=sy + 0.08, w=cw - 0.28, h=0.22,
                  text=title, font_size=7.5, bold=True, color=WILEY_NAVY)
            iy = sy + 0.32
            for it in items[:3]:
                _rect(slide, x=cx + 0.16, y=iy + 0.03, w=0.04, h=0.13, fill=WILEY_NAVY)
                _text(slide, x=cx + 0.27, y=iy, w=cw - 0.4, h=0.24,
                      text=_truncate(it, 70), font_size=8, color=WILEY_BODY,
                      line_spacing=1.05)
                iy += 0.26


def _add_methodology_appendix_slide(prs, *, data_quality_note: str = None):
    """Back-of-deck methodology appendix — documents how the brief is made so
    the reader can trust (and challenge) it. Covers the consensus-as-basis /
    events-as-test calibration model and any data-quality caveat."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.2, w=sw - 1.0, h=0.4, text="Methodology",
          font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.7, w=sw - 1.0, h=0.3,
          text="How this brief is produced — so you can trust it and challenge it",
          font_size=10.5, italic=True, color=WILEY_MUTED)

    _rect(slide, x=0.5, y=1.15, w=sw - 1.0, h=3.55, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.15, w=0.08, h=3.55, fill=WILEY_TEAL)

    blocks = [
        ("Consensus is the forecast basis, events are the test",
         "Each tracked trend is a claim. At forecast time we measure the share "
         "of sources framing it as likely — the prevailing expectation (what the "
         "crowd expects, not proof). Named real-world events afterward either "
         "bear the claim out or don't. We report point-in-time basis, never a "
         "moving “accuracy” score."),
        ("The value is the divergence",
         "We lead with where consensus and evidence disagree: high-consensus "
         "claims the evidence isn't bearing out (the crowd may be wrong) and "
         "low-consensus outliers the evidence is confirming (signals the crowd "
         "missed)."),
        ("Sourcing & relevance",
         "Articles are filtered to a topic by a per-article relevance score, "
         "then events are extracted with an actor / action / magnitude / date, "
         "de-duplicated, and tagged as confirming or countering each trend. "
         "Low-confidence events are held for analyst review, not auto-published."),
    ]
    y = 1.35
    for head, body in blocks:
        _text(slide, x=0.85, y=y, w=sw - 1.7, h=0.24,
              text=head, font_size=11, bold=True, color=WILEY_NAVY)
        _text(slide, x=0.85, y=y + 0.26, w=sw - 1.7, h=0.7,
              text=body, font_size=9.5, color=WILEY_BODY, line_spacing=1.3)
        y += 1.12

    if data_quality_note:
        _rect(slide, x=0.5, y=4.85, w=sw - 1.0, h=0.6, fill=PALE_AMBER)
        _text(slide, x=0.7, y=4.92, w=sw - 1.4, h=0.5,
              text=data_quality_note, font_size=9, italic=True,
              color=SLATE_MID, line_spacing=1.25)


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
        # Card with a bullet marker on left, category + action on right.
        # (Was a large "01/02/03" numeral — dropped because the leading number
        # read as a cross-reference to the numbered topics in the ToC.)
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=1.15, fill=WILEY_CARD_BG)
        _rect(slide, x=0.5, y=y, w=1.05, h=1.15, fill=WILEY_TEAL)
        _text(slide, x=0.5, y=y+0.12, w=1.05, h=0.9,
              text="•", font_size=44, bold=True, color=WHITE,
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
    """Last-resort safety net for catastrophically long input.

    With ``MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`` now enabled on every ``_text`` call,
    long content shrinks to fit the text box rather than being chopped.
    The per-call ``n`` (typically 50-250 chars in the old codebase) is
    multiplied by 4 here so the chop only fires on pathological input
    that would even at minimum font size still overflow the box. A
    deliberate over-cap so authors still see *most* of their content.

    Try to chop on a word boundary so the trailing ellipsis sits after a
    full word, not mid-token.
    """
    s = (s or "").strip()
    # Generous safety net only — we do NOT want to chop readable content. The
    # text instead shrinks to fit via the baked-in fontScale
    # (_set_autofit_scale), so the reader sees the WHOLE sentence at a smaller
    # size rather than an ellipsis. This only fires on pathological input.
    cap = max(n * 4, 600)
    if len(s) <= cap:
        return s
    # Cut at the last whitespace before the cap so we don't leave a
    # truncated half-word stuck to the ellipsis.
    cut = s.rfind(" ", 0, cap - 1)
    if cut < cap * 0.6:  # if no good word break is reasonably close, hard cut
        cut = cap - 1
    return s[:cut].rstrip(",.;:— ") + "…"


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
