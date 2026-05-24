"""Multi-topic bundle PPTX builder for the recurring Wiley delivery pipeline.

Wraps the single-topic builder in :mod:`app.services.forecast_pptx_export` and
glues together a cover slide + a table of contents + per-topic sections
(divider slide + the per-topic deck) into one deliverable.

Used by:
* the on-demand "Generate monthly/quarterly bundle" buttons in the Forecast
  Tracker UI (via ``GET /api/forecast/deliverables/bundle.pptx``)
* the scheduled monthly/quarterly email push from
  :mod:`app.services.wiley_delivery_service`
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional

from pptx import Presentation
from pptx.util import Inches
from pptx.enum.text import PP_ALIGN

from app.services.forecast_pptx_export import (
    PINK, PINK_DEEP, WHITE, NAVY, SLATE_DARK, SLATE_MID, SLATE_LIGHT,
    SLATE_BLACK, RULE_GRAY, PALE_PINK_1, GREEN_DEEP, RED_DEEP, AMBER_DEEP,
    PALE_GREEN, PALE_RED, BASELINE_COLORS,
    WILEY_TEAL, WILEY_TEAL_LT, WILEY_NAVY, WILEY_BLUE,
    WILEY_CARD_BG, WILEY_BODY, WILEY_MUTED,
    WILEY_BG_COVER, WILEY_BG_SOFT, WILEY_BG_BOKEH, WILEY_BG_SECTION,
    _rect, _text, _add_brand_mark, _add_brand_footer, _add_bg_image,
    _add_exec_summary_slide, _add_whats_changed_slide,
    _add_scenario_slide, _add_surprises_divider, _add_surprise_cluster_slide,
    _diff_assessments, _headline_finding, _short_date, _truncate,
    _add_gap_analysis_matrix_slide, _add_flip_detail_slide,
    _add_briefing_synthesis_slide, _add_key_insights_slide,
    _add_strategic_recommendations_slide, _add_consensus_outlier_slide,
    _add_strategic_overview_slide, _add_five_domains_summary_slide,
    _add_black_swans_slide, _add_cross_cutting_themes_slide,
    _add_executive_decision_framework_slide, _add_next_steps_slide,
    _add_executive_summary_letter_slide, _add_review_pending_banner_slide,
    _prior_baseline_for, _verdict_chip, _baseline_color, _customer_label,
)


def build_bundle_pptx(
    items: list,
    *,
    period_label: str,
    cadence: str,
    updates_only: bool = False,
    bundle_synthesis: Optional[dict] = None,
    eos_per_topic: Optional[dict] = None,
    review_findings: Optional[list] = None,
    review_verdict: Optional[str] = None,
) -> bytes:
    """Build one PPTX deck spanning multiple topics.

    Front-matter order mirrors the Feb 2026 Wiley Horizons deck:

        Cover → Executive Summary → Strategic Overview → Five Strategic Domains
        → Three Horizons Overview → Black Swans → Cross-Cutting Themes → ToC.

    Per topic: Topic divider → Briefing Synthesis → Key Insights →
    Strategic Recommendations → Next Steps → Consensus & Outlier → Gap
    Analysis matrix → Status-changed detail slides (if any flips) →
    Emerging-theme clusters (if new ones since prior).

    Parameters
    ----------
    items
        List of ``(assessment, forecast_run, prior_assessment_or_None)``.
    bundle_synthesis
        Cross-topic LLM artefacts (``strategic_overview``,
        ``cross_cutting_themes``, ``executive_decision_framework``) produced
        by :func:`forecast_narrative.ensure_bundle_synthesis`. Cached per
        ``(cadence, period_label)``.
    eos_per_topic
        ``{topic: [scenario_dict]}`` from a recent ExtremeOutlierService
        scan per topic, produced by :func:`wiley_delivery_service._ensure_eos_for_bundle`.
    """
    prs = Presentation()
    prs.slide_width = Inches(10.0)
    prs.slide_height = Inches(5.625)

    topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    synth = bundle_synthesis or {}

    # ── Front matter (cross-topic), in Wiley deck order ───────────────────
    _add_bundle_cover(prs, period_label, cadence, topics, updates_only=updates_only)
    # When the LLM-as-judge flagged errors but the user downloaded the
    # draft anyway, prepend a banner slide listing the findings so the
    # reader knows the deck is not yet ready to ship.
    if review_verdict == "revision_requested" and review_findings:
        _add_review_pending_banner_slide(prs, review_findings, period_label)
    # NEW: prose Executive Summary letter (slide 2) — addressed-to-the-reader.
    # The stats-style slide below renders as "Headline Findings" so the two
    # don't compete for the "Executive Summary" name.
    _add_executive_summary_letter_slide(prs, synth.get("exec_summary") or {}, period_label)
    _add_cross_topic_exec_summary(prs, items, period_label, cadence,
                                  updates_only=updates_only)
    _add_strategic_overview_slide(prs, period_label, synth.get("strategic_overview") or "")
    _add_five_domains_summary_slide(prs, items)
    _add_three_horizons_overview(prs, items, updates_only=updates_only)
    _add_black_swans_slide(prs, eos_per_topic or {})
    _add_cross_cutting_themes_slide(prs, synth.get("cross_cutting_themes") or [])
    _add_executive_decision_framework_slide(prs, synth.get("executive_decision_framework") or [])
    _add_bundle_toc(prs, items, updates_only=updates_only)

    # ── Per-topic sections ────────────────────────────────────────────────
    for assessment, forecast_run, prior in items:
        verdicts = [
            v for v in (assessment.get("scenario_verdicts") or [])
            if v.get("verdict_label") != "Done"  # done scenarios suppressed from bundle
        ]
        summary = assessment.get("summary") or {}
        bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})

        _add_topic_divider(prs, assessment, forecast_run or {})

        if updates_only and prior:
            diff = _diff_assessments(assessment, prior)

            # Narrative orientation BEFORE the data — matches original Wiley
            # deck flow (section divider → Briefing Synthesis → data → Key
            # Insights → Recommendations → Consensus & Outlier).
            _add_briefing_synthesis_slide(prs, assessment)

            _add_gap_analysis_matrix_slide(prs, assessment, prior, diff)

            for v in verdicts:
                key = str(v.get("scenario_idx"))
                if key not in diff.get("verdict_flips", {}):
                    continue
                prior_label, current_label = diff["verdict_flips"][key]
                _add_flip_detail_slide(
                    prs, v, prior_label, current_label,
                    baseline=bc_per.get(key),
                    prior_baseline=_prior_baseline_for(prior, key),
                )

            new_surprises = [
                s for s in (assessment.get("surprises") or [])
                if (s.get("label") or "") in diff["new_surprise_labels"]
            ]
            if new_surprises:
                _add_surprises_divider(prs, new_surprises)
                for sur in sorted(new_surprises, key=lambda s: -(s.get("size") or 0)):
                    _add_surprise_cluster_slide(prs, sur)

            # Narrative interpretation AFTER the data.
            _add_key_insights_slide(prs, assessment, prior)
            _add_strategic_recommendations_slide(prs, assessment)
            _add_next_steps_slide(prs, assessment)
            _add_consensus_outlier_slide(prs, assessment)
        elif updates_only and not prior:
            # No prior snapshot for this topic — emit a 1-slide stub instead
            # of dumping the entire full deck. Still include briefing if
            # the LLM synthesised one for the current snapshot.
            _add_no_prior_stub_slide(prs, assessment)
            _add_briefing_synthesis_slide(prs, assessment)
            _add_key_insights_slide(prs, assessment, None)
            _add_strategic_recommendations_slide(prs, assessment)
            _add_next_steps_slide(prs, assessment)
            _add_consensus_outlier_slide(prs, assessment)
        else:
            headline = _headline_finding(verdicts, bc_per)
            _add_exec_summary_slide(prs, assessment, headline)
            if bc_per:
                _add_whats_changed_slide(prs, assessment)
            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _add_scenario_slide(prs, v, bc_per.get(key))
            surprises = assessment.get("surprises") or []
            if surprises:
                _add_surprises_divider(prs, surprises)
                for sur in sorted(surprises, key=lambda s: -(s.get("size") or 0)):
                    _add_surprise_cluster_slide(prs, sur)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


def _add_cross_topic_exec_summary(prs, items: list, period_label: str, cadence: str, *, updates_only: bool):
    """One-slide cross-topic executive summary.

    Mirrors the Feb 2026 Wiley deck slide 9. Aggregates over all topics: total
    scenarios tracked, total flips this period, total new evidence articles,
    total new unanticipated clusters, plus the single most consequential
    movement across the whole portfolio.
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Full-bleed soft teal background (matches Wiley exec summary)
    _add_bg_image(slide, WILEY_BG_SOFT)

    # Title + subtitle. The subtitle clarifies whether this deck is a full
    # 90-day review (default) or an updates-only diff against the prior
    # snapshot — confusion on this point is a recurring user complaint.
    _text(slide, x=2.0, y=1.55, w=6.0, h=0.5, text="HEADLINE FINDINGS",
          font_size=22, bold=True, color=WILEY_NAVY, align=PP_ALIGN.CENTER)
    mode_label = "Updates only — diff vs prior snapshot" if updates_only \
                 else "Full review — current snapshot vs original forecast"
    sub = f"AunooAI  ·  {period_label}  ·  {mode_label}"
    _text(slide, x=2.0, y=2.10, w=6.0, h=0.3, text=sub,
          font_size=11, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)

    # Aggregate stats. The stats shown depend on which question the deck
    # answers:
    #   - Updates only mode → diff vs prior snapshot
    #       Status changes  = # verdict_label flips between snapshots
    #       New articles    = # URIs added since prior
    #       Emerging        = # new unanticipated clusters since prior
    #   - Full review mode → current vs original forecast
    #       Status changes  = # scenarios off-baseline (cooling/strengthening)
    #       Inconclusive    = # scenarios with no attribution
    #       New articles    = # articles analysed in the assessment window
    #       Emerging        = # unanticipated clusters in current snapshot
    n_topics = len(items)
    n_scenarios = 0
    n_flips = 0
    n_off_baseline = 0
    n_inconclusive_full = 0
    n_new_evidence = 0
    n_new_clusters = 0
    n_total_articles = 0
    n_total_surprises = 0
    biggest_mover = None  # (delta, topic, scenario_name, was, now)
    no_prior_topics = []
    for assessment, _run, prior in items:
        active_verdicts = [
            v for v in (assessment.get("scenario_verdicts") or [])
            if v.get("verdict_label") != "Done"
        ]
        n_scenarios += len(active_verdicts)
        n_total_articles += int(assessment.get("evidence_count") or 0)
        n_total_surprises += len(assessment.get("surprises") or [])

        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        # Per-scenario baseline-corrected labels are the canonical "current
        # status vs forecast" signal. "At baseline" = forecast on-track,
        # everything else = movement worth surfacing.
        for v in active_verdicts:
            key = str(v.get("scenario_idx"))
            bc_label = (bc_per.get(key) or {}).get("label")
            if bc_label in ("Above baseline", "Below baseline"):
                n_off_baseline += 1
            elif bc_label in (None, "Inconclusive"):
                # Distinguish attribution gaps from genuine on-baseline
                # results. Inconclusive when the scenario has no
                # supports/contradicts in the window.
                if (v.get("supports") or 0) + (v.get("contradicts") or 0) == 0:
                    n_inconclusive_full += 1

        if not prior:
            no_prior_topics.append(assessment.get("topic") or "—")
            continue
        diff = _diff_assessments(assessment, prior)
        n_flips += len(diff.get("verdict_flips", {}))
        n_new_evidence += len(diff.get("new_uris", []) or [])
        n_new_clusters += len(diff.get("new_surprise_labels", []) or [])

        prior_bc = ((prior.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        for v in active_verdicts:
            key = str(v.get("scenario_idx"))
            now_net = (bc_per.get(key) or {}).get("net_rate")
            was_net = (prior_bc.get(key) or {}).get("net_rate")
            if now_net is None or was_net is None:
                continue
            delta = now_net - was_net
            if biggest_mover is None or abs(delta) > abs(biggest_mover[0]):
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                biggest_mover = (
                    delta,
                    assessment.get("topic"),
                    deck_info.get("deck_scenario_name") or v.get("scenario_title"),
                    (prior_bc.get(key) or {}).get("label"),
                    (bc_per.get(key) or {}).get("label"),
                )

    # Pick the headline finding when there's no prior snapshot — the
    # scenario with the largest absolute baseline-corrected net_rate
    # across the bundle. Skips zero-attribution scenarios so the headline
    # isn't a "Current 0%" measurement gap.
    full_mode_headline = None
    if not biggest_mover:
        best_abs = -1.0
        for assessment, _run, _prior in items:
            bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
            for v in (assessment.get("scenario_verdicts") or []):
                if v.get("verdict_label") == "Done":
                    continue
                if (v.get("supports") or 0) + (v.get("contradicts") or 0) == 0:
                    continue
                key = str(v.get("scenario_idx"))
                bc = bc_per.get(key) or {}
                net = bc.get("net_rate")
                if net is None:
                    continue
                if abs(net) > best_abs:
                    best_abs = abs(net)
                    deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                    full_mode_headline = (
                        net,
                        assessment.get("topic"),
                        deck_info.get("deck_scenario_name") or v.get("scenario_title"),
                        bc.get("label"),
                        v,
                    )

    # Centred white content card hosting all the synthesis
    _rect(slide, x=0.6, y=2.6, w=8.8, h=2.6, fill=WILEY_CARD_BG)
    _rect(slide, x=0.6, y=2.6, w=0.08, h=2.6, fill=WILEY_TEAL)

    # Stats row inside the card. Pairs differ by mode so the numbers map
    # cleanly onto the deck's actual content (full review = vs-forecast,
    # updates only = vs-prior-snapshot).
    y_stats = 2.78
    if updates_only:
        pairs = [
            ("Topics",         str(n_topics)),
            ("Scenarios",      str(n_scenarios)),
            ("Status changes", str(n_flips)),
            ("New articles",   f"{n_new_evidence:,}"),
            ("Emerging",       str(n_new_clusters)),
        ]
    else:
        pairs = [
            ("Topics",         str(n_topics)),
            ("Scenarios",      str(n_scenarios)),
            ("Off-baseline",   str(n_off_baseline)),
            ("Inconclusive",   str(n_inconclusive_full)),
            ("Articles",       f"{n_total_articles:,}"),
        ]
    inner_w = 8.4
    cell_w = inner_w / len(pairs)
    cx = 0.9
    for label, value in pairs:
        _text(slide, x=cx, y=y_stats, w=cell_w-0.1, h=0.2,
              text=label.upper(), font_size=8, bold=True, color=WILEY_TEAL)
        _text(slide, x=cx, y=y_stats+0.22, w=cell_w-0.1, h=0.45,
              text=value, font_size=24, bold=True, color=WILEY_NAVY)
        cx += cell_w

    # Headline finding inside the card, below the stats
    y_h = 3.6
    if biggest_mover:
        delta, topic, scenario_name, was, now = biggest_mover
        sign = "+" if delta > 0 else ""
        delta_color = GREEN_DEEP if delta > 0 else (RED_DEEP if delta < 0 else SLATE_LIGHT)
        _text(slide, x=0.9, y=y_h, w=inner_w, h=0.22,
              text="HEADLINE FINDING — BIGGEST MOVEMENT THIS PERIOD",
              font_size=8, bold=True, color=WILEY_TEAL)
        _text(slide, x=0.9, y=y_h+0.24, w=inner_w, h=0.32,
              text=f"{topic} — {scenario_name}",
              font_size=14, bold=True, color=WILEY_BODY)
        _text(slide, x=0.9, y=y_h+0.62, w=4.5, h=0.3,
              text=f"{_customer_label(was)}  →  {_customer_label(now)}",
              font_size=12, color=WILEY_MUTED)
        _text(slide, x=5.4, y=y_h+0.58, w=3.9, h=0.4,
              text=f"{sign}{delta*100:.2f}% confirmation Δ",
              font_size=20, bold=True, color=delta_color, align=PP_ALIGN.RIGHT)
    elif full_mode_headline:
        # Full-forecast mode: no prior snapshot to diff against, so the
        # headline is the scenario whose live verdict deviates most from
        # the original forecast's baseline expectation.
        net, topic, scenario_name, bc_label, _v = full_mode_headline
        sign = "+" if net > 0 else ""
        delta_color = GREEN_DEEP if net > 0 else (RED_DEEP if net < 0 else SLATE_LIGHT)
        _text(slide, x=0.9, y=y_h, w=inner_w, h=0.22,
              text="HEADLINE FINDING — LARGEST DEVIATION FROM ORIGINAL FORECAST",
              font_size=8, bold=True, color=WILEY_TEAL)
        _text(slide, x=0.9, y=y_h+0.24, w=inner_w, h=0.32,
              text=f"{topic} — {scenario_name}",
              font_size=14, bold=True, color=WILEY_BODY)
        _text(slide, x=0.9, y=y_h+0.62, w=4.5, h=0.3,
              text=f"Now {_customer_label(bc_label)} vs forecast expectation",
              font_size=12, color=WILEY_MUTED)
        _text(slide, x=5.4, y=y_h+0.58, w=3.9, h=0.4,
              text=f"{sign}{net*100:.2f}% confirmation Δ",
              font_size=20, bold=True, color=delta_color, align=PP_ALIGN.RIGHT)
    else:
        _text(slide, x=0.9, y=y_h+0.2, w=inner_w, h=0.4,
              text="No scenarios with measurable movement vs forecast.",
              font_size=12, italic=True, color=WILEY_MUTED)

    # First-snapshot footnote only applies to updates-only mode — full
    # review mode doesn't compare to a prior snapshot, so listing
    # "first-snapshot topics" is misleading there.
    if updates_only and no_prior_topics:
        msg = (
            f"First snapshot for: "
            + ", ".join(no_prior_topics[:3])
            + ("…" if len(no_prior_topics) > 3 else "")
            + " — these will diff against this period from next bundle onward."
        )
        _text(slide, x=0.6, y=5.3, w=sw-1.2, h=0.3,
              text=msg, font_size=8.5, italic=True, color=WILEY_MUTED,
              align=PP_ALIGN.CENTER)


def _add_three_horizons_overview(prs, items: list, *, updates_only: bool):
    """Cross-topic Three Horizons map — mirrors original deck slide 16.

    Three rows (H1 / H2 / H3), each listing topics' scenarios in that horizon
    with their baseline-corrected verdict + net rate. Lets the reader see at
    a glance which horizons are accelerating vs. cooling across the portfolio.
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Full-bleed bokeh background
    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.3, w=sw-1.0, h=0.5,
          text="Three Horizons Overview", font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.85, w=sw-1.0, h=0.28,
          text="Scenarios grouped by horizon · current status and confirmation strength",
          font_size=11, italic=True, color=WILEY_MUTED)

    horizon_bands = [
        ("h1", "H1 · DECLINING SYSTEM", 1.4),
        ("h2", "H2 · TRANSITION",       2.85),
        ("h3", "H3 · FUTURE VISION",    4.3),
    ]

    for horizon_code, horizon_label, y_top in horizon_bands:
        # Teal label rail on the left
        _rect(slide, x=0.4, y=y_top, w=2.2, h=1.2, fill=WILEY_TEAL)
        _text(slide, x=0.55, y=y_top+0.15, w=2.0, h=0.25,
              text=horizon_label.split("·")[0].strip(), font_size=10, bold=True, color=WHITE)
        _text(slide, x=0.55, y=y_top+0.4, w=2.0, h=0.5,
              text=horizon_label.split("·")[1].strip() if "·" in horizon_label else "",
              font_size=12, bold=True, color=WHITE)

        chips = []  # (name, internal_label, customer_label, sub_text)
        for assessment, _run, _prior in items:
            bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
            for v in (assessment.get("scenario_verdicts") or []):
                if v.get("verdict_label") == "Done":
                    continue
                if (v.get("horizon_type") or "").lower() != horizon_code:
                    continue
                key = str(v.get("scenario_idx"))
                bc = bc_per.get(key) or {}
                internal_label = bc.get("label") or v.get("verdict_label") or "—"
                net = bc.get("net_rate")
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
                topic = (assessment.get("topic") or "")[:18]
                sub = f"{topic} · {(net or 0)*100:+.1f}%" if net is not None else topic
                chips.append((name, internal_label, _customer_label(internal_label), sub))

        # Render chips inline — white cards with colored top bar
        cx = 2.75
        cy = y_top
        for name, internal_label, customer_label, sub in chips[:5]:
            chip_w = 1.42
            color = _baseline_color(internal_label) or WILEY_TEAL
            _rect(slide, x=cx, y=cy, w=chip_w-0.05, h=1.2, fill=WHITE)
            _rect(slide, x=cx, y=cy, w=chip_w-0.05, h=0.22, fill=color)
            _text(slide, x=cx, y=cy+0.03, w=chip_w-0.05, h=0.16,
                  text=customer_label.upper(), font_size=7, bold=True, color=WHITE,
                  align=PP_ALIGN.CENTER)
            _text(slide, x=cx+0.06, y=cy+0.28, w=chip_w-0.15, h=0.55,
                  text=_truncate(name, 38), font_size=8.5, bold=True,
                  color=WILEY_BODY)
            _text(slide, x=cx+0.06, y=cy+0.88, w=chip_w-0.15, h=0.3,
                  text=sub, font_size=7, color=WILEY_MUTED)
            cx += chip_w

        if not chips:
            _text(slide, x=2.85, y=y_top+0.45, w=7.0, h=0.3,
                  text="(no scenarios in this horizon across the bundle)",
                  font_size=10, italic=True, color=WILEY_MUTED)


def _add_no_prior_stub_slide(prs, assessment: dict):
    """Placeholder when no prior snapshot exists yet for a topic.
    Wiley-styled — soft bg, navy band hosting the message."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    topic = assessment.get("topic") or "—"
    _text(slide, x=0.5, y=0.4, w=sw-1.0, h=0.35,
          text="FIRST SNAPSHOT",
          font_size=11, bold=True, color=WILEY_TEAL)
    _text(slide, x=0.5, y=0.8, w=sw-1.0, h=0.6, text=topic,
          font_size=24, bold=True, color=WILEY_NAVY)

    # Card with the message
    _rect(slide, x=0.5, y=1.7, w=sw-1.0, h=2.4, fill=WILEY_CARD_BG)
    _rect(slide, x=0.5, y=1.7, w=0.08, h=2.4, fill=WILEY_TEAL)

    msg = (
        "This topic's first assessment is captured but there's nothing to "
        "compare it against yet.\n\n"
        "The next bundle that follows another assessment for this topic "
        "will include its full gap analysis with confirmation deltas, status "
        "changes, and emerging-theme tracking."
    )
    _text(slide, x=0.8, y=1.85, w=sw-1.6, h=2.1, text=msg,
          font_size=11, color=WILEY_BODY, line_spacing=1.5)

    summary = assessment.get("summary") or {}
    line = (
        f"Forecast generated {_short_date(summary.get('forecast_generated_at') or '')}    ·    "
        f"Assessed {_short_date(summary.get('assessed_at') or assessment.get('assessed_at'))}    ·    "
        f"{assessment.get('evidence_count') or 0} articles analysed"
    )
    _text(slide, x=0.5, y=4.4, w=sw-1.0, h=0.3, text=line,
          font_size=9.5, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)


def _add_bundle_cover(prs, period_label: str, cadence: str, topics: list, *, updates_only: bool):
    """Bundle cover — clean Aunoo black-and-pink layout.

    Full-bleed dark slate (near-black), big pink "WILEY HORIZONS · TRACKER"
    eyebrow, large white period label, white subtitle, Aunoo brandmark
    top-right. No atmospheric image — relies on the brand contrast.
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    # Full-bleed Aunoo black
    _rect(slide, x=0, y=0, w=sw, h=5.625, fill=WILEY_NAVY)
    # Pink top rule + pink bottom rule for brand framing
    _rect(slide, x=0, y=0, w=sw, h=0.08, fill=WILEY_TEAL)
    _rect(slide, x=0, y=5.55, w=sw, h=0.08, fill=WILEY_TEAL)

    suffix = " · UPDATES" if updates_only else ""
    cadence_label = {
        "monthly":   "Monthly intelligence briefing",
        "quarterly": "Quarterly intelligence briefing",
        "all":       "Strategic intelligence briefing",
    }.get(cadence, "Intelligence briefing")

    _text(slide, x=0.6, y=2.0, w=sw-1.2, h=0.4,
          text=f"WILEY HORIZONS · TRACKER{suffix}",
          font_size=12, bold=True, color=WILEY_TEAL)
    _text(slide, x=0.6, y=2.45, w=sw-1.2, h=1.0, text=period_label,
          font_size=44, bold=True, color=WHITE)
    _text(slide, x=0.6, y=3.45, w=sw-1.2, h=0.4,
          text=cadence_label,
          font_size=15, italic=True, color=WILEY_TEAL_LT)

    # Topic count + Aunoo producer credit
    _text(slide, x=0.6, y=4.4, w=sw-1.2, h=0.3,
          text=f"{len(topics)} {'topic' if len(topics) == 1 else 'topics'}    ·    "
               f"Produced by AunooAI",
          font_size=11, bold=True, color=WILEY_TEAL_LT, align=PP_ALIGN.CENTER)

    # Aunoo brandmark top-right corner
    _add_brand_mark(slide, x=8.9, y=0.3, w=0.7, h=0.6)


def _add_bundle_toc(prs, items: list, *, updates_only: bool):
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    _text(slide, x=0.5, y=0.3, w=sw-1.0, h=0.5,
          text="Topics in this bundle", font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.85, w=sw-1.0, h=0.3,
          text="Each topic includes a Briefing Synthesis, gap analysis, "
               "Key Insights, Strategic Recommendations, and Consensus & Outlier review.",
          font_size=10, italic=True, color=WILEY_MUTED)

    y = 1.4
    for i, (assessment, _run, _prior) in enumerate(items, 1):
        topic = assessment.get("topic") or "—"
        n_scenarios = len([
            v for v in (assessment.get("scenario_verdicts") or [])
            if v.get("verdict_label") != "Done"
        ])
        n_surprises = len(assessment.get("surprises") or [])
        evidence = assessment.get("evidence_count") or 0
        assessed = _short_date((assessment.get("summary") or {}).get("assessed_at")
                                or assessment.get("assessed_at"))

        # Each row in a white card with teal number badge
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=0.78, fill=WILEY_CARD_BG)
        _rect(slide, x=0.5, y=y, w=0.7, h=0.78, fill=WILEY_TEAL)
        _text(slide, x=0.5, y=y+0.18, w=0.7, h=0.42,
              text=str(i), font_size=22, bold=True, color=WHITE,
              align=PP_ALIGN.CENTER)
        _text(slide, x=1.35, y=y+0.1, w=sw-1.95, h=0.32,
              text=_truncate(topic, 80), font_size=13, bold=True, color=WILEY_BODY)
        meta = (
            f"{n_scenarios} scenarios  ·  {n_surprises} emerging themes  ·  "
            f"{evidence} articles  ·  assessed {assessed}"
        )
        _text(slide, x=1.35, y=y+0.42, w=sw-1.95, h=0.25, text=meta,
              font_size=9.5, color=WILEY_MUTED)
        y += 0.85
        if y > 5.0:
            break


def _add_topic_divider(prs, assessment: dict, forecast_run: dict):
    """Per-topic section divider — mirrors Wiley deck slide 19. Full-bleed
    soft-teal background with the topic name large and centred, framed by a
    navy band so it reads as a chapter break."""
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_SOFT)

    topic = assessment.get("topic") or "—"

    # Navy band hosting the topic name (Wiley slide 19 style)
    _rect(slide, x=0, y=2.1, w=sw, h=1.5, fill=WILEY_NAVY)
    _rect(slide, x=0, y=2.1, w=sw, h=0.06, fill=WILEY_TEAL)
    _text(slide, x=0.6, y=2.3, w=sw-1.2, h=1.1, text=topic,
          font_size=32, bold=True, color=WHITE, align=PP_ALIGN.CENTER)

    summary = assessment.get("summary") or {}
    forecast_at = summary.get("forecast_generated_at") or forecast_run.get("created_at")
    assessed_at = summary.get("assessed_at") or assessment.get("assessed_at")
    line = (
        f"Original forecast {_short_date(forecast_at)}    ·    "
        f"Latest assessment {_short_date(assessed_at)}"
    )
    _text(slide, x=0.5, y=3.85, w=sw-1.0, h=0.3, text=line,
          font_size=12, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)
