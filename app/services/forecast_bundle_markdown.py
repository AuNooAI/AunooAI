"""Markdown export of the Wiley quarterly intelligence bundle.

Mirrors the structure of :mod:`forecast_bundle_pptx` but renders to plain
markdown. The intent is reviewer-friendly: a human reads the MD to validate
analytical content quickly, then commits to a full PPTX regeneration.

Public surface: :func:`build_bundle_markdown` — same signature shape as
``build_bundle_pptx`` (returns bytes for direct HTTP streaming).
"""

from __future__ import annotations

from typing import Optional


def _topic_of(item):
    a, _r, _p = item
    return a.get("topic") or "—"


def _scenario_name(v: dict) -> str:
    deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
    return deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"


def _verdict_friendly(label: Optional[str]) -> str:
    """Translate raw verdict labels to customer-friendly wording."""
    if not label:
        return "—"
    return {
        "Above baseline": "Strengthening",
        "At baseline": "Stable",
        "Below baseline": "Cooling",
        "Done": "Resolved",
    }.get(label, label)


def _pct(n: Optional[float]) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n) * 100:+.2f}%"
    except Exception:
        return "—"


def _consensus_drift_line(assessment: dict) -> str:
    """Original vs recomputed consensus, averaged across deck scenarios."""
    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = assessment.get("scenario_verdicts") or []
    deck_pcts = []
    live_pcts = []
    for v in verdicts:
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        if deck_info.get("consensus_pct") is not None:
            try:
                deck_pcts.append(float(deck_info["consensus_pct"]))
            except Exception:
                pass
        bc = bc_per.get(str(v.get("scenario_idx"))) or {}
        if bc.get("recomputed_consensus_pct") is not None:
            try:
                live_pcts.append(float(bc["recomputed_consensus_pct"]))
            except Exception:
                pass
    if not deck_pcts or not live_pcts:
        return ""
    deck_avg = sum(deck_pcts) / len(deck_pcts)
    live_avg = sum(live_pcts) / len(live_pcts)
    arrow = "→"
    return f"Consensus drift: {deck_avg:.0f}% (original) {arrow} {live_avg:.0f}% (recomputed)"


def _render_exec_summary(exec_summary: dict, period_label: str) -> str:
    """Front-of-deck Executive Summary letter.

    The wiley_exec_summary_agent emits ``{letter, signoff}`` — single flowing
    paragraph + optional signoff. We accept legacy ``body`` for safety.
    """
    letter = (exec_summary or {}).get("letter") or (exec_summary or {}).get("body") or ""
    signoff = (exec_summary or {}).get("signoff") or f"AunooAI Editorial Team · {period_label}"
    if not letter.strip():
        return ""
    return (
        f"## Executive Summary\n\n"
        f"*{period_label}*\n\n"
        f"{letter.strip()}\n\n"
        f"— {signoff}\n"
    )


def _render_strategic_overview(text: str) -> str:
    if not text:
        return ""
    return f"## Strategic Overview\n\n{text.strip()}\n"


def _render_cross_cutting(themes: list) -> str:
    """Cross-Cutting Themes: agent emits ``{lead, body}`` per item."""
    if not themes:
        return ""
    parts = ["## Cross-Cutting Themes\n"]
    for t in themes:
        lead = (t.get("lead") or t.get("name") or t.get("headline") or "—").strip()
        body = (t.get("body") or t.get("description") or "").strip()
        # lead is a 5-8 word lead phrase ending with a period — use it as the
        # bold opener of each paragraph (matches the slide treatment).
        parts.append(f"**{lead}** {body}\n")
    return "\n".join(parts)


def _render_decision_framework(items: list) -> str:
    """Executive Decision Framework: agent emits ``{headline, body}``, 3 items."""
    if not items:
        return ""
    parts = ["## Executive Decision Framework\n"]
    for i, d in enumerate(items, 1):
        headline = (d.get("headline") or d.get("question") or "").strip()
        body = (d.get("body") or d.get("rationale") or "").strip()
        parts.append(f"{i}. **{headline}** — {body}\n")
    return "\n".join(parts)


def _render_briefing(assessment: dict) -> str:
    briefing = ((assessment.get("summary") or {}).get("topic_briefing")) or {}
    if not briefing or not briefing.get("lede"):
        return ""
    headline = briefing.get("headline") or ""
    lede = (briefing.get("lede") or "").strip()
    iv = (briefing.get("intelligence_view") or "").strip()
    tensions = briefing.get("tensions") or []

    parts = ["### Briefing Synthesis\n"]
    if headline:
        parts.append(f"*{headline}*\n")
    drift = _consensus_drift_line(assessment)
    if drift:
        parts.append(f"_{drift}_\n")

    if tensions:
        parts.append("#### The Ecosystem at a Crossroads\n")
        for t in tensions[:3]:
            name = (t.get("name") or "").strip()
            body = (t.get("body") or "").strip()
            parts.append(f"- **{name}** — {body}")
        parts.append("")

    parts.append("#### The Aunoo Intelligence View\n")
    if lede:
        parts.append(lede + "\n")
    if iv:
        parts.append(iv + "\n")
    return "\n".join(parts)


def _render_recommendations(assessment: dict) -> str:
    recs = ((assessment.get("summary") or {}).get("strategic_recommendations")) or []
    if not recs:
        return ""
    parts = ["### Strategic Recommendations\n"]
    for i, r in enumerate(recs[:3], 1):
        headline = (r.get("headline") or "").strip()
        rationale = (r.get("rationale") or "").strip()
        horizon = (r.get("horizon") or "6-18 months").strip()
        parts.append(f"{i}. **{headline}**  _({horizon})_\n\n   {rationale}\n")
    return "\n".join(parts)


def _render_next_steps(assessment: dict) -> str:
    steps = ((assessment.get("summary") or {}).get("next_steps")) or []
    if not steps:
        return ""
    parts = ["### Next Steps\n"]
    for i, step in enumerate(steps[:3], 1):
        cat = (step.get("category") or "").strip()
        action = (step.get("action") or "").strip()
        parts.append(f"{i}. **{cat}** — {action}")
    parts.append("")
    return "\n".join(parts)


def _render_scenario_table(assessment: dict) -> str:
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    if not verdicts:
        return ""
    bc_per = (((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {})
    parts = ["### Scenario Verdicts\n"]
    parts.append("| # | Scenario | Verdict | Net rate Δ | Supports | Contradicts |")
    parts.append("|---|---|---|---|---|---|")
    for v in verdicts:
        idx = v.get("scenario_idx")
        bc = bc_per.get(str(idx)) or {}
        net = bc.get("net_rate")
        net_s = _pct(net) if net is not None else "—"
        name = _scenario_name(v).replace("|", "\\|")
        verdict = _verdict_friendly(v.get("verdict_label"))
        sup = v.get("supports") or 0
        con = v.get("contradicts") or 0
        parts.append(f"| {idx} | {name} | {verdict} | {net_s} | {sup} | {con} |")
    parts.append("")
    return "\n".join(parts)


def _render_black_swans(eos: list) -> str:
    if not eos:
        return ""
    parts = ["### Black Swans & Wild Cards\n"]
    for s in eos[:6]:
        cat = (s.get("category") or "wild_card").replace("_", " ").title()
        title = (s.get("title") or "(untitled)").strip()
        desc = (s.get("description") or s.get("subtitle") or "").strip()
        impact = s.get("impact_rating")
        prob = s.get("probability")
        horizon = s.get("time_horizon") or ""
        meta = []
        if impact is not None:
            try:
                meta.append(f"Impact {int(round(float(impact)))}/10")
            except Exception:
                pass
        if prob is not None:
            try:
                meta.append(f"Probability {int(round(float(prob) * 100))}%")
            except Exception:
                pass
        if horizon:
            meta.append(horizon)
        meta_s = "  ·  ".join(meta)
        parts.append(f"- **[{cat}] {title}**  _{meta_s}_  \n  {desc}")
    parts.append("")
    return "\n".join(parts)


def _render_review_block(verdict: Optional[str], findings: Optional[list]) -> str:
    if not findings:
        return ""
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warning"]
    if verdict == "approved" and not errors and not warns:
        return ""
    parts = ["## Reviewer Findings\n"]
    parts.append(f"**Verdict:** `{verdict or 'unknown'}`  ·  errors={len(errors)} warnings={len(warns)}\n")
    if errors:
        parts.append("### Errors (blocking)\n")
        for f in errors:
            stage = f.get("stage") or ""
            artefact = f.get("artefact_key") or ""
            finding = (f.get("finding") or "").strip()
            fix = (f.get("suggested_fix") or "").strip()
            parts.append(f"- **{stage} · {artefact}** — {finding}")
            if fix:
                parts.append(f"  - Suggested fix: {fix}")
        parts.append("")
    if warns:
        parts.append("### Warnings\n")
        for f in warns:
            stage = f.get("stage") or ""
            artefact = f.get("artefact_key") or ""
            finding = (f.get("finding") or "").strip()
            parts.append(f"- **{stage} · {artefact}** — {finding}")
        parts.append("")
    return "\n".join(parts)


def build_bundle_markdown(
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
    """Render the bundle to markdown bytes (UTF-8).

    Same arguments as :func:`forecast_bundle_pptx.build_bundle_pptx` — the
    delivery service passes both through identical assessment / synth data.
    """
    synth = bundle_synthesis or {}
    eos_per_topic = eos_per_topic or {}
    topics = [_topic_of(it) for it in items]

    blocks: list[str] = []

    # ── Cover ──
    blocks.append(
        f"# AunooAI · Wiley Horizons Tracker\n\n"
        f"**Period:** {period_label}  ·  **Cadence:** {cadence}"
        f"{'  ·  Updates only' if updates_only else ''}  \n"
        f"**Topics:** {len(topics)}  —  {', '.join(topics)}\n"
    )

    # ── Reviewer summary at top so the reviewer reads it first ──
    review_md = _render_review_block(review_verdict, review_findings)
    if review_md:
        blocks.append(review_md)

    # ── Front matter ──
    blocks.append(_render_exec_summary(synth.get("exec_summary") or {}, period_label))
    blocks.append(_render_strategic_overview(synth.get("strategic_overview") or ""))
    blocks.append(_render_cross_cutting(synth.get("cross_cutting_themes") or []))
    blocks.append(_render_decision_framework(synth.get("executive_decision_framework") or []))

    # ── Per-topic ──
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        summary = assessment.get("summary") or {}
        assessed_at = summary.get("assessed_at") or assessment.get("assessed_at") or ""
        evidence = assessment.get("evidence_count") or 0

        blocks.append(
            f"\n---\n\n## {topic}\n\n"
            f"_Assessed {assessed_at}  ·  {evidence} articles analysed_\n"
        )
        blocks.append(_render_briefing(assessment))
        blocks.append(_render_scenario_table(assessment))
        blocks.append(_render_recommendations(assessment))
        blocks.append(_render_next_steps(assessment))

        # Black Swans per-topic
        topic_eos = eos_per_topic.get(topic) or []
        blocks.append(_render_black_swans(topic_eos))

    full = "\n".join([b for b in blocks if b])
    return full.encode("utf-8")
