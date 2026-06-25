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
    _add_expert_commentary_slide,
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
    template_path: Optional[str] = None,
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
    template_path
        Optional path to a PPTX file to use as the base presentation. Its
        existing slides are kept at the head of the deck (intro pack), then
        the cover + exec summary + per-topic sections are appended on top.
        The template's ``slide_layouts[6]`` MUST be a BLANK layout — every
        builder helper assumes index 6 is blank. The intro template at
        ``app/static_assets/topic_report_intro.pptx`` has been reordered to
        match.
    """
    if template_path:
        prs = Presentation(template_path)
    else:
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
    # Expert view on emerging themes (analyst-editable; renders only if present).
    _add_expert_commentary_slide(prs, synth.get("expert_commentary") or "", period_label)
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
    _add_black_swans_slide(prs, eos_per_topic or {})
    _add_cross_cutting_themes_slide(prs, synth.get("cross_cutting_themes") or [])
    _add_executive_decision_framework_slide(prs, synth.get("executive_decision_framework") or [])
    _add_bundle_toc(prs, items, updates_only=updates_only)
    # Three Horizons Overview sits immediately before the per-topic dive so the
    # framework is in the reader's head when they enter Topic 1 (and so the
    # cross-topic horizon map serves as the bridge from cross-cutting analysis
    # to per-topic detail). Previously sat earlier in the cross-topic stack,
    # which left readers re-orienting when topic 1 arrived several slides later.
    _add_three_horizons_overview(prs, items, updates_only=updates_only)

    # ── Per-topic sections ────────────────────────────────────────────────
    for topic_idx, (assessment, forecast_run, prior) in enumerate(items, 1):
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

        _add_topic_divider(prs, assessment, forecast_run or {}, topic_idx=topic_idx)
        # Open every topic section with its own Three Horizons chart so the
        # reader sees the H1/H2/H3 layout for THIS topic before diving into
        # the briefing + scenario detail. The cross-topic overview earlier in
        # the deck still gives the portfolio view; this is the topic view.
        _add_topic_three_horizons_chart(prs, assessment, forecast_run or {}, topic_idx=topic_idx)

        if updates_only and prior:
            diff = _diff_assessments(assessment, prior)

            # The Tracker-era "gap analysis matrix" and per-scenario
            # "status changed" (flip-detail) slides are intentionally NOT
            # rendered — they back-tested the futures-cone scenarios against
            # article framing (rejected). The per-trend evidence ledger
            # (consensus basis + confirming/counter events + READ) is the
            # canonical per-scenario view now, in every mode.
            _add_briefing_synthesis_slide(prs, assessment, topic_idx=topic_idx)

            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr,
                                    topic=assessment.get("topic"))

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
            _add_briefing_synthesis_slide(prs, assessment, topic_idx=topic_idx)
            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr,
                                    topic=assessment.get("topic"))
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
            _add_briefing_synthesis_slide(prs, assessment, topic_idx=topic_idx)
            for v in verdicts:
                key = str(v.get("scenario_idx"))
                _conf, _ctr = _scenario_ev(v)
                _add_scenario_slide(prs, v, bc_per.get(key),
                                    confirming_events=_conf, countering_events=_ctr,
                                    topic=assessment.get("topic"))
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
    _text(slide, x=2.0, y=0.5, w=6.0, h=0.5, text="HEADLINE FINDINGS",
          font_size=22, bold=True, color=WILEY_NAVY, align=PP_ALIGN.CENTER)
    sub = f"AunooAI  ·  {period_label} quarterly intelligence briefing"
    _text(slide, x=2.0, y=1.05, w=6.0, h=0.3, text=sub,
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

    # Centred white content card hosting all the synthesis — sized to fill
    # the slide so the headline metrics + watch-list don't float in empty space.
    _rect(slide, x=0.6, y=1.5, w=8.8, h=3.75, fill=WILEY_CARD_BG)
    _rect(slide, x=0.6, y=1.5, w=0.08, h=3.75, fill=WILEY_TEAL)

    # Stats row inside the card. Pairs differ by mode so the numbers map
    # cleanly onto the deck's actual content (full review = vs-forecast,
    # updates only = vs-prior-snapshot).
    # Neutral portfolio facts only. The Tracker-era "Status changes",
    # "Off-baseline", "Inconclusive" counts and the "biggest movement /
    # confirmation Δ / now Strengthening vs forecast" headline were
    # removed — they scored the futures-cone scenarios as a back-test,
    # which the customer rejected. The Executive Summary letter (slide 2)
    # carries the narrative read of the quarter.
    y_stats = 1.78
    pairs = [
        ("Topics",          str(n_topics),
         "strategic themes tracked this quarter"),
        ("Scenarios",       str(n_scenarios),
         "future scenarios under watch across all topics"),
        ("Articles analysed", f"{n_total_articles:,}",
         "news & research items processed since the last update"),
        ("Emerging themes", str(n_total_surprises),
         "new patterns that weren't in the original forecast"),
    ]
    inner_w = 8.4
    cell_w = inner_w / len(pairs)
    cx = 0.9
    for label, value, desc in pairs:
        _text(slide, x=cx, y=y_stats, w=cell_w-0.1, h=0.2,
              text=label.upper(), font_size=8, bold=True, color=WILEY_TEAL)
        _text(slide, x=cx, y=y_stats+0.22, w=cell_w-0.1, h=0.42,
              text=value, font_size=22, bold=True, color=WILEY_NAVY)
        _text(slide, x=cx, y=y_stats+0.66, w=cell_w-0.15, h=0.42,
              text=desc, font_size=7.5, color=WILEY_MUTED, line_spacing=1.15)
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
                crowd_wrong.append(f"{topic} — {name}")
            elif category == "outlier_confirming":
                outliers_confirming.append(f"{topic} — {name}")

    # Divider rule between the headline metrics and the watch-list.
    _rect(slide, x=0.9, y=3.02, w=inner_w, h=0.012, fill=RULE_GRAY)

    col_y = 3.2
    _text(slide, x=0.9, y=col_y, w=inner_w, h=0.22,
          text="WHAT TO WATCH THIS QUARTER",
          font_size=10, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.9, y=col_y+0.24, w=inner_w, h=0.34,
          text="We compare what most expert sources expect with what the news is actually "
               "showing. The two gaps below are where the prevailing view and the real-world "
               "evidence don't yet match — usually the most useful thing to know.",
          font_size=8.5, italic=True, color=WILEY_MUTED, line_spacing=1.2)

    half = inner_w / 2
    body_y = col_y + 0.66
    # Left: widely expected, but events haven't confirmed it.
    _text(slide, x=0.9, y=body_y, w=half-0.2, h=0.44,
          text="Most expect this — but it isn't happening yet",
          font_size=9.5, bold=True, color=AMBER_DEEP, line_spacing=1.05)
    lw = crowd_wrong or ["No clear gap this quarter"]
    _text(slide, x=0.9, y=body_y+0.46, w=half-0.2, h=0.86,
          text="\n".join(f"• {x}" for x in lw[:4]),
          font_size=9, color=WILEY_BODY, line_spacing=1.3)
    # Right: few expected it, but the evidence is starting to back it.
    _text(slide, x=0.9+half, y=body_y, w=half-0.2, h=0.44,
          text="Few expected this — but it's starting to happen",
          font_size=9.5, bold=True, color=GREEN_DEEP, line_spacing=1.05)
    rw = outliers_confirming or ["No clear gap this quarter"]
    _text(slide, x=0.9+half, y=body_y+0.46, w=half-0.2, h=0.86,
          text="\n".join(f"• {x}" for x in rw[:4]),
          font_size=9, color=WILEY_BODY, line_spacing=1.3)


def _add_three_horizons_overview(prs, items: list, *, updates_only: bool):
    """Cross-topic Three Horizons map.

    Three-zone layout on a single slide:
      1. Title + one-line framing.
      2. The canonical curves chart (Bezier paths copied from the web app's
         Future Horizons tab) with this bundle's scenarios plotted as
         numbered dots — numbers run H1 → H2 → H3.
      3. A 3-column legend BELOW the chart pairing each [N] with its
         scenario title and topic, so the slide reads on its own without
         the audience flipping to speaker notes. The full notes are still
         written as a printer-friendly handout.
    """
    from io import BytesIO as _BytesIO
    from pptx.dml.color import RGBColor as _RGB
    from app.services.wiley_three_horizons_viz import (
        collect_scenarios_for_render, render_to_png, build_notes, STROKES,
    )

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0

    _add_bg_image(slide, WILEY_BG_BOKEH)

    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.40,
          text="Three Horizons Overview", font_size=20, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.58, w=sw-1.0, h=0.22,
          text="H1 fades as H3 emerges; H2 carries the transition. "
               "Numbered markers below match the scenarios listed beneath the chart.",
          font_size=9.5, italic=True, color=WILEY_MUTED)

    # Render the curves + numbered scenario markers in-process. The
    # overview lists 23 scenarios across all topics — too dense for the
    # label-card style, so we keep the numbered-circle marker mode here
    # and pair it with the column legend below. (Per-topic charts use
    # ``mode='cards'`` since their counts are small enough to fit.)
    scenarios = collect_scenarios_for_render(items)
    buf = _BytesIO()
    render_to_png(scenarios, buf, mode="numbered")
    buf.seek(0)
    # Chart height 2.6 in — sized so all 11 H1/H2 scenarios fit the legend
    # below without overflowing into a "+more — see notes" placeholder.
    slide.shapes.add_picture(buf, left=Inches(0.3), top=Inches(0.88),
                             width=Inches(9.4), height=Inches(2.6))

    # ── 3-column legend ───────────────────────────────────────────────
    # Numbers in the legend match the numbered dots on the chart 1:1
    # (same source list, same H1→H2→H3 order).
    HORIZON_LABEL = {
        "h1": "H1 · DECLINING SYSTEM",
        "h2": "H2 · TRANSITION",
        "h3": "H3 · FUTURE VISION",
    }
    rgb_for = {
        k: _RGB(int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))
        for k, v in STROKES.items()
    }
    by_h = {"h1": [], "h2": [], "h3": []}
    for n, s in enumerate(scenarios, 1):
        by_h[s["wave_type"]].append((n, s["title"], s["topic"]))

    # Chart bottom is at 0.88 + 2.6 = 3.48; legend starts just below with a
    # small breathing gap. Sized so 11 + header fits comfortably (max_lines
    # ends up at 12, accommodating up to 11 + an optional "+K more" row).
    legend_top = 3.55
    col_w = 3.1
    col_gap = 0.10
    col_x0 = 0.3
    header_h = 0.22
    body_top = legend_top + header_h + 0.04   # ≈ 3.81
    body_bottom = 5.50
    line_h = 0.135
    max_lines = int((body_bottom - body_top) / line_h)  # = 12

    for i, key in enumerate(("h1", "h2", "h3")):
        col_x = col_x0 + i * (col_w + col_gap)
        # Header: colour swatch + horizon label
        _rect(slide, x=col_x, y=legend_top+0.04, w=0.16, h=0.13, fill=rgb_for[key])
        _text(slide, x=col_x+0.22, y=legend_top, w=col_w-0.22, h=header_h,
              text=HORIZON_LABEL[key], font_size=9, bold=True, color=WILEY_BODY)

        rows = by_h[key]
        if not rows:
            _text(slide, x=col_x, y=body_top, w=col_w, h=line_h,
                  text="(no scenarios in this horizon)",
                  font_size=8, italic=True, color=WILEY_MUTED)
            continue

        # If the column overflows max_lines, last visible row is a "+K more"
        # pointer that still references the speaker notes for the spill.
        visible = rows
        spill = 0
        if len(rows) > max_lines:
            visible = rows[: max_lines - 1]
            spill = len(rows) - len(visible)

        y = body_top
        for (n, title, topic) in visible:
            # Compose the line short enough to fit 3.1" wide at 8pt on ONE
            # line: at this width that's ~46 chars max. Cap the whole string
            # (title + " — " + topic) rather than each part separately, so
            # the budget always lines up with the column width.
            short_topic = (topic or "")
            if len(short_topic) > 14:
                short_topic = short_topic[:13] + "…"
            raw = f"[{n}] {title} — {short_topic}" if short_topic else f"[{n}] {title}"
            # ``_truncate`` multiplies its cap by 4 internally (last-resort
            # safety net for autofit), so it won't actually cut at 46 chars.
            # Do the hard cap inline to fit 3.10" × 8pt on one line.
            MAX = 46
            line = raw if len(raw) <= MAX else raw[: MAX - 1].rstrip() + "…"
            tb = _text(slide, x=col_x, y=y, w=col_w, h=line_h,
                       text=line, font_size=8, color=WILEY_BODY,
                       line_spacing=1.05, shrink_to_fit=False)
            # Disable wrap so anything that still pushes past the column
            # edge gets clipped at the box edge instead of flowing to a
            # second line and overlapping the next entry.
            try:
                tb.text_frame.word_wrap = False
            except Exception:
                pass
            y += line_h
        if spill:
            _text(slide, x=col_x, y=y, w=col_w, h=line_h,
                  text=f"+{spill} more — see speaker notes",
                  font_size=8, italic=True, color=WILEY_MUTED, shrink_to_fit=False)

    # Speaker notes still carry the full, untruncated list as a handout.
    try:
        notes_tf = slide.notes_slide.notes_text_frame
        notes_tf.text = build_notes(scenarios)
    except Exception:
        pass


def _add_topic_three_horizons_chart(prs, assessment: dict, forecast_run: dict, *, topic_idx: Optional[int] = None):
    """Per-topic Three Horizons chart — opens each topic section.

    Mirror of the web app's Future Horizons tab: the same Bezier curves
    with this topic's scenarios placed as small colour-coded title cards
    ON the curves (NOT numbered circles + legend). The chart is the slide.
    """
    from io import BytesIO as _BytesIO
    from app.services.wiley_three_horizons_viz import (
        collect_scenarios_for_render, render_to_png, build_notes,
    )

    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    sw = 10.0
    _add_bg_image(slide, WILEY_BG_BOKEH)

    topic = assessment.get("topic") or "—"
    eyebrow = f"TOPIC {topic_idx} · FUTURE HORIZONS" if topic_idx is not None else "FUTURE HORIZONS"
    _text(slide, x=0.5, y=0.18, w=sw-1.0, h=0.28,
          text=eyebrow, font_size=10, bold=True, color=WILEY_TEAL)
    _text(slide, x=0.5, y=0.42, w=sw-1.0, h=0.42,
          text=topic, font_size=20, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.84, w=sw-1.0, h=0.22,
          text="H1 fades as H3 emerges; H2 carries the transition. "
               "Scenario titles are placed on the curves at their expected timeframe.",
          font_size=9.5, italic=True, color=WILEY_MUTED)

    scenarios = collect_scenarios_for_render([(assessment, forecast_run, None)])
    buf = _BytesIO()
    render_to_png(scenarios, buf)
    buf.seek(0)
    # Chart fills the remaining slide height — no legend below.
    slide.shapes.add_picture(buf, left=Inches(0.2), top=Inches(1.12),
                             width=Inches(9.6), height=Inches(4.30))

    # Speaker notes still carry the scenario list as a printer-friendly handout.
    try:
        slide.notes_slide.notes_text_frame.text = build_notes(scenarios)
    except Exception:
        pass


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

    _text(slide, x=0.5, y=0.22, w=sw-1.0, h=0.45,
          text="Topics in this bundle", font_size=22, bold=True, color=WILEY_NAVY)
    _text(slide, x=0.5, y=0.74, w=sw-1.0, h=0.26,
          text="Each topic carries a Briefing Synthesis, per-trend evidence "
               "ledgers, emerging themes, Key Insights, Recommendations and Next Steps.",
          font_size=9.5, italic=True, color=WILEY_MUTED)

    y = 1.18
    row_h = 0.74
    for i, (assessment, _run, _prior) in enumerate(items, 1):
        topic = assessment.get("topic") or "—"
        n_scenarios = len([
            v for v in (assessment.get("scenario_verdicts") or [])
            if v.get("verdict_label") != "Done"
        ])
        n_surprises = len(assessment.get("surprises") or [])
        evidence = assessment.get("evidence_count") or 0
        # Plain-English one-liner so a cold reader grasps the topic's scope —
        # the briefing headline is the writer's own summary of the topic.
        desc = (((assessment.get("summary") or {}).get("topic_briefing") or {})
                .get("headline") or "").strip()

        # Each row in a white card with teal number badge
        _rect(slide, x=0.5, y=y, w=sw-1.0, h=row_h, fill=WILEY_CARD_BG)
        _rect(slide, x=0.5, y=y, w=0.7, h=row_h, fill=WILEY_TEAL)
        _text(slide, x=0.5, y=y+0.22, w=0.7, h=0.42,
              text=str(i), font_size=22, bold=True, color=WHITE,
              align=PP_ALIGN.CENTER)
        _text(slide, x=1.35, y=y+0.05, w=sw-1.95, h=0.28,
              text=_truncate(topic, 80), font_size=12.5, bold=True, color=WILEY_BODY)
        if desc:
            _text(slide, x=1.35, y=y+0.31, w=sw-1.95, h=0.22,
                  text=_truncate(desc, 105), font_size=9, color=WILEY_BODY)
        meta = (
            f"{n_scenarios} scenarios  ·  {n_surprises} emerging themes  ·  "
            f"{evidence} articles"
        )
        _text(slide, x=1.35, y=y+0.52, w=sw-1.95, h=0.2, text=meta,
              font_size=8, color=WILEY_MUTED)
        y += row_h + 0.05
        if y > 5.0:
            break

    # Three Horizons legend — the H1/H2/H3 codes on the per-trend ledger slides
    # are unfamiliar to new readers, so explain them once up front.
    _text(slide, x=0.5, y=5.28, w=sw-1.0, h=0.26,
          text="Horizons:  H1 — today's declining system (near-term)   ·   "
               "H2 — transition & innovation   ·   H3 — long-term future vision",
          font_size=8.5, italic=True, color=WILEY_MUTED, align=PP_ALIGN.CENTER)


def _add_topic_divider(prs, assessment: dict, forecast_run: dict, *, topic_idx: Optional[int] = None):
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
    # "TOPIC N" eyebrow ties this section back to the numbered ToC.
    if topic_idx is not None:
        _text(slide, x=0.6, y=1.72, w=sw-1.2, h=0.3, text=f"TOPIC {topic_idx}",
              font_size=13, bold=True, color=WILEY_TEAL, align=PP_ALIGN.CENTER)
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
