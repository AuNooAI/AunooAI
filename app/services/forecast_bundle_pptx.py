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
    _add_whats_changed_section_slide, _add_methodology_appendix_slide,
    _prior_baseline_for, _verdict_chip, _baseline_color, _customer_label,
)

import re as _re


def _looks_like_keyword_salad(label: str) -> bool:
    """True for un-relabelled cluster labels like 'ukraine, drug, generic'
    (comma-separated lowercase tokens) that should not surface on a slide."""
    s = (label or "").strip()
    if not s:
        return True
    return bool(_re.fullmatch(r"[a-z0-9][a-z0-9\-]*(?:,\s*[a-z0-9][a-z0-9\-]*){1,5}", s))


def build_bundle_pptx(
    items: list,
    *,
    period_label: str,
    cadence: str,
    updates_only: bool = False,
    bundle_synthesis: Optional[dict] = None,
    eos_per_topic: Optional[dict] = None,
    events_by_topic: Optional[dict] = None,
    data_quality_note: Optional[str] = None,
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
                                  updates_only=updates_only,
                                  events_by_topic=events_by_topic)
    _add_strategic_overview_slide(prs, period_label, synth.get("strategic_overview") or "")
    # "What's Changed" — the honest replacement for the Tracker scorecard.
    # Named events + scenario drift + emerging themes + press-attention
    # shifts, drawn from the synthesis payload's whats_changed block (events
    # populated by the extraction stage; the other three analyst-editable).
    from app.services.wiley_bundle_supervisor import _prior_period_label
    wc = dict(synth.get("whats_changed") or {})
    # Auto-fill "new on the watch" from the existing surprise clusters when
    # the analyst hasn't entered emerging themes — the data is already
    # computed per topic, so the slide isn't sparse by default. Analyst
    # edits in the editor take precedence (this only fires when empty).
    if not wc.get("emerging"):
        emerging = []
        for a, _r, _p in items:
            top = sorted((a.get("surprises") or []),
                         key=lambda s: -(s.get("size") or 0))[:1]
            for s in top:
                lab = (s.get("label") or "").strip()
                if lab and not _looks_like_keyword_salad(lab):
                    emerging.append(f"{a.get('topic')}: {lab}")
        wc["emerging"] = emerging[:5]
    _add_whats_changed_section_slide(
        prs, wc,
        period_label=period_label,
        prior_period_label=_prior_period_label(period_label),
    )
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

        # Events for this topic this cycle — the evidence that tests each
        # scenario's claim. Split per scenario (confirming/countering) at the
        # call site via events_for_scenario.
        topic_events = (events_by_topic or {}).get(assessment.get("topic")) or []

        def _scenario_ev(v):
            from app.services.wiley_event_extraction import events_for_scenario
            name = ((v.get("top_articles") or {}).get("deck_info") or {}).get("deck_scenario_name") \
                or v.get("scenario_title") or ""
            return events_for_scenario(topic_events, name)

        _add_topic_divider(prs, assessment, forecast_run or {})

        if updates_only and prior:
            diff = _diff_assessments(assessment, prior)

            # The Tracker-era "gap analysis matrix" and per-scenario
            # "status changed" (flip-detail) slides are intentionally NOT
            # rendered — they back-tested the futures-cone scenarios against
            # article framing (rejected). The per-trend evidence ledger
            # (consensus basis + confirming/counter events + READ) is the
            # canonical per-scenario view now, in every mode.
            _add_briefing_synthesis_slide(prs, assessment)

            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr)

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
        elif updates_only and not prior:
            # No prior snapshot for this topic — previously emitted a
            # "first assessment captured, nothing to compare against"
            # stub. Users found that worse than useless because the
            # topic still has actual content (current verdicts, surprises,
            # briefing) the deck should surface. Fall through to the
            # full-review branch so a single-assessment topic ships the
            # same slides as the full-mode bundle, just without the
            # gap-analysis matrix (which requires a prior to diff
            # against).
            # The per-topic "Executive Summary" status-distribution slide
            # ("WHAT THE BACK-TEST FOUND" + Strengthening/Cooling chips) is
            # retired — the Briefing Synthesis opens each topic with the
            # qualitative read instead.
            _add_briefing_synthesis_slide(prs, assessment)
            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr)
            surprises = assessment.get("surprises") or []
            if surprises:
                _add_surprises_divider(prs, surprises)
                for sur in sorted(surprises, key=lambda s: -(s.get("size") or 0)):
                    _add_surprise_cluster_slide(prs, sur)
            _add_key_insights_slide(prs, assessment, None)
            _add_strategic_recommendations_slide(prs, assessment)
            _add_next_steps_slide(prs, assessment)
        else:
            # Retired: per-topic status-distribution exec slide + the
            # consensus-drift "what's changed" slide (both back-test
            # framings). Briefing Synthesis opens the topic.
            _add_briefing_synthesis_slide(prs, assessment)
            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr)
            surprises = assessment.get("surprises") or []
            if surprises:
                _add_surprises_divider(prs, surprises)
                for sur in sorted(surprises, key=lambda s: -(s.get("size") or 0)):
                    _add_surprise_cluster_slide(prs, sur)

    # ── Back-of-deck methodology appendix (documents the calibration model
    # + any collection data-quality caveat). Always present so the reader can
    # trust and challenge the brief.
    _add_methodology_appendix_slide(prs, data_quality_note=data_quality_note)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()


def _add_cross_topic_exec_summary(prs, items: list, period_label: str, cadence: str, *, updates_only: bool, events_by_topic: Optional[dict] = None):
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
    # Neutral portfolio facts only. The Tracker-era "Status changes",
    # "Off-baseline", "Inconclusive" counts and the "biggest movement /
    # confirmation Δ / now Strengthening vs forecast" headline were
    # removed — they scored the futures-cone scenarios as a back-test,
    # which the customer rejected. The Executive Summary letter (slide 2)
    # carries the narrative read of the quarter.
    y_stats = 2.78
    pairs = [
        ("Topics",          str(n_topics)),
        ("Scenarios",       str(n_scenarios)),
        ("Articles analysed", f"{n_total_articles:,}"),
        ("Emerging themes", str(n_total_surprises)),
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

    # ── Calibration: where consensus and evidence DIVERGE ─────────────
    # The product's value is the divergence, not confirmation. Compute each
    # trend's READ and surface the two high-value cells: high-consensus
    # claims the evidence is NOT bearing out (the crowd may be wrong), and
    # low-consensus outliers the evidence IS bearing out (signals missed).
    from app.services.forecast_pptx_export import _calibration_read
    from app.services.wiley_event_extraction import events_for_scenario

    crowd_wrong, outliers_confirming = [], []
    for assessment, _r, _p in items:
        topic = assessment.get("topic") or "—"
        t_events = (events_by_topic or {}).get(topic) or []
        for v in (assessment.get("scenario_verdicts") or []):
            if v.get("verdict_label") == "Done":
                continue
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
            basis = deck_info.get("consensus_pct")
            conf, ctr = events_for_scenario(t_events, name)
            _, category = _calibration_read(basis, len(conf), len(ctr))
            if category == "crowd_wrong":
                crowd_wrong.append(f"{name} ({topic})")
            elif category == "outlier_confirming":
                outliers_confirming.append(f"{name} ({topic})")

    col_y = 3.55
    _text(slide, x=0.9, y=col_y, w=inner_w, h=0.22,
          text="WHERE CONSENSUS & EVIDENCE DIVERGE  ·  the watch-list",
          font_size=8, bold=True, color=WILEY_TEAL)

    half = inner_w / 2
    # Left: high consensus the evidence isn't bearing out.
    _text(slide, x=0.9, y=col_y+0.26, w=half-0.2, h=0.22,
          text="CONSENSUS NOT YET BEARING OUT", font_size=8, bold=True, color=AMBER_DEEP)
    lw = crowd_wrong or ["— none this cycle"]
    _text(slide, x=0.9, y=col_y+0.5, w=half-0.2, h=1.0,
          text="\n".join(f"• {x}" for x in lw[:4]),
          font_size=9.5, color=WILEY_BODY, line_spacing=1.3)
    # Right: low-consensus outliers the evidence IS bearing out.
    _text(slide, x=0.9+half, y=col_y+0.26, w=half-0.2, h=0.22,
          text="OUTLIERS THE EVIDENCE CONFIRMS", font_size=8, bold=True, color=GREEN_DEEP)
    rw = outliers_confirming or ["— none this cycle"]
    _text(slide, x=0.9+half, y=col_y+0.5, w=half-0.2, h=1.0,
          text="\n".join(f"• {x}" for x in rw[:4]),
          font_size=9.5, color=WILEY_BODY, line_spacing=1.3)


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
          text="The scenario set across the three horizons",
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
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
                topic = (assessment.get("topic") or "")[:22]
                # The verdict color-bar + customer label + net-rate % were
                # removed — they scored each scenario. The chip now just
                # places the scenario in its horizon and names its topic.
                chips.append((name, topic))

        # Render chips inline — white cards with a neutral brand top bar
        cx = 2.75
        cy = y_top
        for name, sub in chips[:5]:
            chip_w = 1.42
            _rect(slide, x=cx, y=cy, w=chip_w-0.05, h=1.2, fill=WHITE)
            _rect(slide, x=cx, y=cy, w=chip_w-0.05, h=0.22, fill=WILEY_TEAL)
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

    suffix = " · WHAT'S CHANGED" if updates_only else ""
    cadence_label = {
        "monthly":   "Monthly foresight update",
        "quarterly": "Quarterly foresight update",
        "all":       "Strategic foresight update",
    }.get(cadence, "Foresight update")

    _text(slide, x=0.6, y=2.0, w=sw-1.2, h=0.4,
          text=f"WILEY HORIZONS · FORESIGHT{suffix}",
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
          text="Each topic includes a Briefing Synthesis, per-trend evidence "
               "ledgers, emerging themes, Key Insights, Strategic Recommendations, "
               "and Next Steps.",
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
