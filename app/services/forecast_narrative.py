"""LLM synthesis of forecast-assessment narratives.

The raw assessment data has counts and verdict labels but not much in the way
of "here's what actually happened" prose. This module synthesizes that prose:

- :func:`synthesize_scenario_narrative` — 3-4 sentence per-scenario narrative
  that names concrete events from the supporting articles (dates, actors,
  what changed). Stored in ``forecast_scenario_verdicts.summary_md``.

- :func:`synthesize_exec_narrative` — 4-6 sentence overall narrative for
  the deck's exec summary, drawing on the most extreme scenario movements
  and the dominant emerging theme. Stored in
  ``forecast_assessments.summary.exec_narrative``.

Both are lazy: the PPTX exporter calls
:func:`ensure_narratives_for_assessment` which only fires LLM calls for
narratives that aren't already cached on the row.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

NARRATIVE_MODEL = "gpt-4.1-mini"


# Customer-facing label translation (mirrors forecast_pptx_export.CUSTOMER_LABEL).
# Used to feed the LLM the same plain-English terms that show up on slides.
CUSTOMER_LABEL = {
    "Above baseline": "Strengthening",
    "At baseline":    "Stable",
    "Below baseline": "Cooling",
}


def _customer_label(label):
    if not label:
        return "—"
    return CUSTOMER_LABEL.get(label, label)


async def _call_llm(prompt: str, *, model_name: Optional[str] = None, **call_kwargs) -> str:
    """Call the narrative model via AIModelFactory (which returns LiteLLMModel
    with proper content extraction). The bare ``get_ai_model()`` returns the
    base AIModel whose ``generate_sync`` yields a raw Choice object — not what
    we want.

    ``call_kwargs`` forwards to the underlying ``router.completion(...)`` —
    use ``reasoning_effort='high'`` for the GPT-5 reviewer agent, etc."""
    from app.ai_models import AIModelFactory
    model = AIModelFactory.get_model(model_name or NARRATIVE_MODEL)
    messages = [{"role": "user", "content": prompt}]
    result = await model.agenerate_response(messages, **call_kwargs)
    return (result or "").strip()

_SCENARIO_PROMPT = """You are writing a 3-4 sentence narrative for an executive briefing.

CONTEXT
Scenario: {scenario_name}
Original deck forecast: {primary_signal}
Verdict from back-test: {verdict_label}
Baseline-corrected support rate: live {live_rate} vs placebo {placebo_rate} = {net_rate} ({baseline_label})

RECENT SUPPORTING ARTICLES (post-forecast)
{supporting_block}

RECENT CONTRADICTING ARTICLES (post-forecast)
{contradicting_block}

WRITE
3-4 sentences narrating what has ACTUALLY HAPPENED in this scenario's space since the forecast was published. Name concrete events, actors, organisations, and dates from the articles above. Do not use phrases like "the data shows", "the assessment indicates", "evidence suggests" — narrate the events directly as a journalist would.

If "{baseline_label}" is "Below baseline", explicitly note that the trend was already in motion at deck-authoring time and signal has since cooled — but still narrate the concrete recent developments. If it is "Above baseline", note that this is genuine new signal beyond the pre-forecast baseline. If "At baseline", note that signal density is unchanged.

Output ONLY the 3-4 sentence narrative as plain prose. No headers, no bullets, no preamble."""

_EXEC_PROMPT = """You are writing the executive-summary opening for a back-test of a strategic forecast.

CONTEXT
Topic: {topic}
Forecast published: {forecast_date}
Assessed: {assessed_date} (over {window_weeks}-week window)
{verdict_distribution}

PER-SCENARIO NARRATIVES
{scenario_narratives}

DOMINANT EMERGING THEME (unanticipated)
{surprise_block}

WRITE
4-6 sentences answering: what did this back-test reveal? Lead with the most consequential finding (largest absolute net rate). Mention by name the scenarios that moved most and which way. End with a sentence on the dominant emerging theme if any. Do not use phrases like "the assessment indicates", "results show", "evidence suggests" — narrate the findings directly.

Output ONLY the 4-6 sentence narrative as plain prose. No headers, no bullets, no preamble."""


def _format_article_block(articles: list[dict], max_items: int = 6) -> str:
    if not articles:
        return "(none)"
    lines = []
    for a in articles[:max_items]:
        date = a.get("article_date") or ""
        title = a.get("title") or a.get("article_uri") or ""
        rationale = (a.get("rationale") or "").strip()
        prefix = f"{date[:10]} · " if date else "· "
        lines.append(f"{prefix}{title}\n    {rationale}")
    return "\n".join(lines)


async def synthesize_scenario_narrative(verdict: dict, baseline: Optional[dict] = None) -> str:
    """Produce a 3-4 sentence narrative for one scenario. Returns empty string
    if no supporting articles are available (the LLM has nothing to ground in
    so refusing to invent is the right call)."""
    from app.ai_models import get_ai_model

    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}
    supports = (verdict.get("top_articles") or {}).get("supports") or []
    contras = (verdict.get("top_articles") or {}).get("contradicts") or []

    if not supports and not contras:
        # Honest fallback so the slide isn't blank (and so the old stub gets
        # overwritten by something readable).
        label = _customer_label((baseline or {}).get("label") or verdict.get("verdict_label"))
        return (
            f"No confirming or contradicting articles attributed to this scenario "
            f"in the tracking window — fresh coverage either lacks topical fit or "
            f"falls below the confidence threshold for direct attribution. "
            f"Status: {label}, based on the pre-forecast trend comparison alone."
        )

    if baseline:
        live = baseline.get("live_rate", 0) or 0
        placebo = baseline.get("placebo_rate", 0) or 0
        net = baseline.get("net_rate", 0) or 0
        label = baseline.get("label") or "—"
        live_s = f"{live*100:.2f}%"
        placebo_s = f"{placebo*100:.2f}%"
        net_s = f"{net*100:+.2f}%"
    else:
        live_s = placebo_s = net_s = "—"
        label = verdict.get("verdict_label") or "—"

    prompt = _SCENARIO_PROMPT.format(
        scenario_name=(deck_info.get("deck_scenario_name") or verdict.get("scenario_title") or "—"),
        primary_signal=deck_info.get("primary_signal") or "(none in deck)",
        verdict_label=verdict.get("verdict_label") or "—",
        live_rate=live_s, placebo_rate=placebo_s, net_rate=net_s,
        baseline_label=label,
        supporting_block=_format_article_block(supports),
        contradicting_block=_format_article_block(contras),
    )

    try:
        text = await _call_llm(prompt)
        return text
    except Exception as e:
        logger.error("Scenario narrative synthesis failed: %s", e)
        return ""


async def synthesize_exec_narrative(assessment: dict) -> str:
    """Produce a 4-6 sentence overall narrative for the assessment."""
    from app.ai_models import get_ai_model

    summary = assessment.get("summary") or {}
    bc = summary.get("baseline_correction") or {}
    bc_per = bc.get("per_scenario") or {}
    verdicts = assessment.get("scenario_verdicts") or []
    surprises = assessment.get("surprises") or []

    if bc_per:
        labels = [v.get("label") for v in bc_per.values()]
    else:
        labels = [v.get("verdict_label") for v in verdicts]
    counts = {x: labels.count(x) for x in set(labels) if x}
    dist = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    dist_line = f"Verdict distribution — {dist}" if dist else ""

    # Build per-scenario lines pairing name + narrative
    scenario_lines = []
    for v in verdicts:
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
        b = bc_per.get(str(v.get("scenario_idx"))) or {}
        net = b.get("net_rate")
        label = b.get("label") or v.get("verdict_label") or "—"
        narrative = (v.get("summary_md") or "").strip()
        net_str = f"{(net or 0)*100:+.2f}%" if net is not None else "—"
        if narrative:
            scenario_lines.append(f"- {name}  [{label}, net {net_str}]\n  {narrative}")
        else:
            scenario_lines.append(f"- {name}  [{label}, net {net_str}]  (no narrative available)")

    if surprises:
        top = max(surprises, key=lambda s: s.get("size") or 0)
        surprise_block = (
            f"{top.get('size') or 0}× {top.get('label') or '(unlabelled)'} — "
            f"{(top.get('note') or '').strip()}"
        )
    else:
        surprise_block = "(no clusters of sufficient cohesion)"

    prompt = _EXEC_PROMPT.format(
        topic=assessment.get("topic") or "—",
        forecast_date=summary.get("forecast_generated_at") or "—",
        assessed_date=summary.get("assessed_at") or "—",
        window_weeks=summary.get("window_weeks") or "full",
        verdict_distribution=dist_line,
        scenario_narratives="\n".join(scenario_lines),
        surprise_block=surprise_block,
    )

    try:
        return await _call_llm(prompt)
    except Exception as e:
        logger.error("Exec narrative synthesis failed: %s", e)
        return ""


_PROMOTE_PROMPT = """You draft a new tracked scenario from a cluster of articles that the existing Three Horizons forecast did not anticipate.

CONTEXT
Topic: {topic}
Cluster label (HDBSCAN-derived from the article titles): {cluster_label}
Cluster size: {cluster_size} articles

SAMPLE ARTICLES FROM THE CLUSTER
{sample_block}

TASK
Draft a tracked scenario describing what this emerging development is and where it could go over the next 3-7 years. Output STRICT JSON only — no markdown, no preamble:

{{
  "title": "short scenario name, max 8 words, no quotes",
  "description": "2-3 sentence scenario describing the current development and a credible 3-7 year trajectory. Name the concrete actors/technologies/institutions from the cluster. Do not hedge with 'the data shows' or 'evidence suggests'.",
  "horizon_type": "h1" | "h2" | "h3",
  "timeframe": "YYYY-YYYY"
}}

HORIZON SELECTION
- "h1" = present-day system already declining or in active disruption
- "h2" = transitional development gaining traction, partial adoption, 2-5 year horizon
- "h3" = future-vision pattern, structural shift, 5+ year horizon

Pick the horizon that best fits the developmental stage of what the cluster articles describe. Timeframe should be plausible given the horizon."""


async def synthesize_scenario_from_surprise(
    cluster: dict,
    topic: str,
) -> dict:
    """Draft a tracked scenario from an unanticipated-development cluster.

    Input is one entry from ``forecast_assessments.surprises`` (label, size,
    sample_articles). Returns a dict ``{title, description, horizon_type,
    timeframe}`` for the UI to present in an editable modal before saving
    via :func:`facade.save_forecast_user_scenario`.
    """
    label = cluster.get("label") or "(unlabelled cluster)"
    size = cluster.get("size") or 0
    samples = cluster.get("sample_articles") or []

    sample_lines = []
    for a in samples[:8]:
        date = (a.get("date") or "")[:10]
        title = a.get("title") or a.get("uri") or ""
        prefix = f"{date} · " if date else "· "
        sample_lines.append(f"{prefix}{title}")
    sample_block = "\n".join(sample_lines) if sample_lines else "(no samples available)"

    prompt = _PROMOTE_PROMPT.format(
        topic=topic or "—",
        cluster_label=label,
        cluster_size=size,
        sample_block=sample_block,
    )

    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Promote-scenario LLM call failed: %s", e)
        raise

    # Strip code-fence wrappers if the model added them.
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.error("Promote-scenario JSON parse failed: %s | raw=%s", e, raw[:400])
        raise ValueError("Scenario draft from LLM was not valid JSON")

    horizon = (parsed.get("horizon_type") or "h2").lower()
    if horizon not in ("h1", "h2", "h3"):
        horizon = "h2"

    return {
        "title": (parsed.get("title") or label)[:200],
        "description": (parsed.get("description") or "").strip(),
        "horizon_type": horizon,
        "timeframe": (parsed.get("timeframe") or "").strip()[:32],
    }


_BRIEFING_PROMPT = """You are writing a "Briefing Synthesis" page for a strategic intelligence document covering one topic. The reader is a senior business stakeholder, not a researcher — use plain business language, no methodology jargon.

CONTEXT
Topic: {topic}
Forecast published: {forecast_date}
Assessed: {assessed_date}
Status distribution across scenarios: {verdict_distribution}
Biggest movement this period: {biggest_mover}

PER-SCENARIO STATE (status: Strengthening / Stable / Cooling)
{scenario_block}

EMERGING THEMES (top 3 by cluster size — story lines none of the original scenarios anticipated)
{surprise_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "headline": "8-12 word strategic headline capturing where this topic stands now, no quotes",
  "lede": "2-3 sentence paragraph synthesising the current state — name concrete actors/events from the per-scenario data, not abstractions like 'the data shows'",
  "tensions": [
    {{ "name": "SHORT NAME IN CAPS", "body": "1-2 sentence description of the tension" }},
    {{ "name": "...", "body": "..." }},
    {{ "name": "...", "body": "..." }}
  ],
  "intelligence_view": "2-3 sentence Aunoo Intelligence View — a synthesis call: is the trajectory the original forecast predicted materialising, cooling, or being replaced by a different story?"
}}

LANGUAGE
- Use "Strengthening" / "Stable" / "Cooling" for status (never "Above/At/Below baseline").
- Refer to surprises as "emerging themes" (never "unanticipated clusters").
- Refer to confirmation Δ as "confirmation strength" or "confirmation change" (never "net rate").
- Exactly 3 tensions. Each must reference concrete dynamics in the per-scenario data."""


_RECOMMENDATIONS_PROMPT = """You are writing the "Strategic Recommendations" slide for a strategic intelligence document covering one topic. The reader is a senior business stakeholder — use plain business language, never methodology jargon like "baseline", "placebo", "net rate", or "unanticipated cluster".

CONTEXT
Topic: {topic}
Status distribution across scenarios: {verdict_distribution}
Period delta: {period_delta}

PER-SCENARIO STATE (status: Strengthening / Stable / Cooling)
{scenario_block}

EMERGING THEMES (top 3)
{surprise_block}

ORG CONTEXT (optional)
{org_context}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "recommendations": [
    {{ "headline": "10-15 word imperative — start with a verb", "rationale": "2 sentences citing the evidence above", "horizon": "0-6 months" | "6-18 months" | "18+ months" }},
    {{ "headline": "...", "rationale": "...", "horizon": "..." }},
    {{ "headline": "...", "rationale": "...", "horizon": "..." }}
  ]
}}

Exactly 3 recommendations. Each must be directly supported by an observation in the per-scenario or emerging-themes data. Do not hedge with 'consider' or 'explore' — write imperative actions ("Pilot…", "Establish…", "Wind down…"). If org context is given, tailor the recommendations to that organisation; otherwise default to actions that any rights-holder in this space could take."""


def _scenario_block_text(verdicts: list, bc_per: dict, limit: int = 6) -> str:
    """Format up to ``limit`` scenarios into a digest for the LLM prompts.
    Labels are translated to customer-facing terms so the LLM's own output
    uses Strengthening/Stable/Cooling rather than the internal baseline jargon."""
    lines = []
    # Order by absolute net rate first so the biggest movers go to the model
    def _key(v):
        b = bc_per.get(str(v.get("scenario_idx"))) or {}
        return -abs(b.get("net_rate") or 0)
    for v in sorted(verdicts, key=_key)[:limit]:
        if v.get("verdict_label") == "Done":
            continue
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
        bc = bc_per.get(str(v.get("scenario_idx"))) or {}
        label = _customer_label(bc.get("label") or v.get("verdict_label"))
        net = bc.get("net_rate")
        net_s = f"{(net or 0)*100:+.2f}%" if net is not None else "—"
        sup = v.get("supports") or 0
        con = v.get("contradicts") or 0
        narrative = (v.get("summary_md") or "").strip()
        narrative_one_line = narrative.replace("\n", " ")[:300]
        lines.append(
            f"- {name} · status: {label} · confirmation Δ {net_s} · {sup} confirming / {con} contradicting\n"
            f"    {narrative_one_line}"
        )
    return "\n".join(lines) if lines else "(no scenarios)"


def _surprise_block_text(surprises: list, limit: int = 3) -> str:
    if not surprises:
        return "(none)"
    items = sorted(surprises, key=lambda s: -(s.get("size") or 0))[:limit]
    lines = []
    for s in items:
        label = s.get("label") or "(unlabelled)"
        size = s.get("size") or 0
        samples = s.get("sample_articles") or []
        sample_titles = "; ".join(
            (a.get("title") or "")[:60] for a in samples[:3] if a.get("title")
        ) or "—"
        lines.append(f"- {label} · {size} articles · {sample_titles}")
    return "\n".join(lines)


def _verdict_distribution_text(verdicts: list, bc_per: dict) -> str:
    if bc_per:
        labels = [_customer_label((bc_per.get(str(v.get("scenario_idx"))) or {}).get("label")
                                   or v.get("verdict_label")) for v in verdicts]
    else:
        labels = [v.get("verdict_label") for v in verdicts]
    counts = {}
    for lbl in labels:
        if not lbl:
            continue
        counts[lbl] = counts.get(lbl, 0) + 1
    return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) or "(none)"


def _biggest_mover_text(verdicts: list, bc_per: dict) -> str:
    best = None
    for v in verdicts:
        if v.get("verdict_label") == "Done":
            continue
        b = bc_per.get(str(v.get("scenario_idx"))) or {}
        net = b.get("net_rate")
        if net is None:
            continue
        if best is None or abs(net) > abs((bc_per.get(str(best.get("scenario_idx"))) or {}).get("net_rate") or 0):
            best = v
    if not best:
        return "(no comparable snapshots yet)"
    deck_info = (best.get("top_articles") or {}).get("deck_info") or {}
    name = deck_info.get("deck_scenario_name") or best.get("scenario_title")
    b = bc_per.get(str(best.get("scenario_idx"))) or {}
    return f"{name} ({_customer_label(b.get('label'))}, confirmation Δ {(b.get('net_rate') or 0)*100:+.2f}%)"


async def synthesize_topic_briefing(assessment: dict) -> dict:
    """LLM-synthesise a Briefing Synthesis page (headline + lede + 3 tensions
    + an Aunoo Intelligence View paragraph). Returns the dict, or {} on
    failure. Caches into ``assessment.summary['topic_briefing']`` upstream."""
    summary = assessment.get("summary") or {}
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    surprises = assessment.get("surprises") or []

    prompt = _BRIEFING_PROMPT.format(
        topic=assessment.get("topic") or "—",
        forecast_date=summary.get("forecast_generated_at") or "—",
        assessed_date=summary.get("assessed_at") or "—",
        verdict_distribution=_verdict_distribution_text(verdicts, bc_per),
        biggest_mover=_biggest_mover_text(verdicts, bc_per),
        scenario_block=_scenario_block_text(verdicts, bc_per),
        surprise_block=_surprise_block_text(surprises),
    )
    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Topic briefing synthesis failed: %s", e)
        return {}

    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.error("Topic briefing JSON parse failed: %s | raw=%s", e, raw[:400])
        return {}

    tensions = parsed.get("tensions") or []
    if not isinstance(tensions, list):
        tensions = []
    return {
        "headline": (parsed.get("headline") or "")[:200].strip(),
        "lede": (parsed.get("lede") or "").strip(),
        "tensions": [
            {"name": (t.get("name") or "")[:40], "body": (t.get("body") or "").strip()}
            for t in tensions[:3] if isinstance(t, dict)
        ],
        "intelligence_view": (parsed.get("intelligence_view") or "").strip(),
    }


async def synthesize_strategic_recommendations(
    assessment: dict, *, prior: Optional[dict] = None, org_context: Optional[str] = None,
) -> list:
    """LLM-synthesise 3 strategic recommendations for the topic. Returns a
    list of ``{headline, rationale, horizon}`` dicts."""
    summary = assessment.get("summary") or {}
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    surprises = assessment.get("surprises") or []

    # Period-delta digest for the prompt
    if prior:
        prior_bc = ((prior.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        movers = []
        for v in verdicts:
            key = str(v.get("scenario_idx"))
            was = (prior_bc.get(key) or {}).get("net_rate")
            now = (bc_per.get(key) or {}).get("net_rate")
            if was is None or now is None:
                continue
            d = now - was
            if abs(d) > 0.005:
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                nm = deck_info.get("deck_scenario_name") or v.get("scenario_title")
                movers.append((d, nm))
        movers.sort(key=lambda m: -abs(m[0]))
        period_delta = "; ".join(f"{nm} {(d*100):+.2f}%" for d, nm in movers[:5]) or "(no material moves)"
    else:
        period_delta = "(first snapshot — no prior delta available)"

    prompt = _RECOMMENDATIONS_PROMPT.format(
        topic=assessment.get("topic") or "—",
        verdict_distribution=_verdict_distribution_text(verdicts, bc_per),
        period_delta=period_delta,
        scenario_block=_scenario_block_text(verdicts, bc_per),
        surprise_block=_surprise_block_text(surprises),
        org_context=org_context or "(no organisational context supplied — write for a generic rights-holder)",
    )

    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Recommendations synthesis failed: %s", e)
        return []

    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.error("Recommendations JSON parse failed: %s | raw=%s", e, raw[:400])
        return []

    recs = parsed.get("recommendations") or []
    valid_horizons = ("0-6 months", "6-18 months", "18+ months")
    out = []
    for r in recs[:3]:
        if not isinstance(r, dict):
            continue
        horizon = (r.get("horizon") or "").strip()
        if horizon not in valid_horizons:
            horizon = "6-18 months"
        out.append({
            "headline": (r.get("headline") or "").strip()[:200],
            "rationale": (r.get("rationale") or "").strip(),
            "horizon": horizon,
        })
    return out


# ── Per-scenario LLM artefacts: key signals + strategic imperative ──────

_SCENARIO_SIGNALS_PROMPT = """You produce structured strategic-intelligence content for one scenario inside a quarterly executive deck. The reader is a senior business stakeholder. Plain language, no methodology jargon (no "baseline", "placebo", "net rate", "reranker", etc.).

CONTEXT
Topic: {topic}
Scenario: {scenario_name}
Horizon: {horizon}
Current status: {status} (confirmation Δ {net_pct})
Original deck consensus: {original_consensus_pct}%
Current consensus (recomputed): {current_consensus_pct}%

TOP CONFIRMING ARTICLES (post-forecast)
{supporting_block}

TOP CONTRADICTING ARTICLES (post-forecast)
{contradicting_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "key_signals": [
    "5-12 word phrase naming a concrete observable signal in this scenario's space",
    "5-12 word phrase naming a second concrete signal",
    "5-12 word phrase naming a third"
  ],
  "strategic_imperative": "ONE imperative sentence (starts with a verb) telling a rights-holder what to do given this scenario's status. Concrete actor / action / metric, not 'consider' or 'explore'."
}}

Exactly 3 key_signals. Each must reference a concrete dynamic visible in the articles above — name actors / technologies / events. The strategic_imperative must match the current status: if Strengthening lean into; if Cooling re-price urgency; if Stable hold position with monitoring."""


async def synthesize_scenario_signals(
    verdict: dict, *, topic: str, original_consensus_pct: Optional[float] = None,
) -> dict:
    """Synthesise key_signals + strategic_imperative for one scenario.

    Returns ``{key_signals: [...], strategic_imperative: "..."}`` or {} on
    failure. Cached by the caller into ``forecast_scenario_verdicts.synthesis``.
    """
    deck_info = (verdict.get("top_articles") or {}).get("deck_info") or {}
    name = deck_info.get("deck_scenario_name") or verdict.get("scenario_title") or "—"
    horizon = verdict.get("horizon_type") or "h1"
    supports = (verdict.get("top_articles") or {}).get("supports") or []
    contras = (verdict.get("top_articles") or {}).get("contradicts") or []

    # Status + Δ for prompt — use baseline-corrected if available
    baseline = (verdict.get("top_articles") or {}).get("baseline") or {}
    label = baseline.get("label") or verdict.get("verdict_label") or "—"
    net = baseline.get("net_rate")
    net_pct = f"{(net or 0)*100:+.2f}%" if net is not None else "—"

    prompt = _SCENARIO_SIGNALS_PROMPT.format(
        topic=topic or "—",
        scenario_name=name,
        horizon=horizon.upper(),
        status=_customer_label(label),
        net_pct=net_pct,
        original_consensus_pct=(
            f"{original_consensus_pct:.0f}" if original_consensus_pct is not None else "—"
        ),
        current_consensus_pct=(
            f"{verdict.get('current_consensus_pct'):.0f}"
            if verdict.get("current_consensus_pct") is not None else "—"
        ),
        supporting_block=_format_article_block(supports),
        contradicting_block=_format_article_block(contras),
    )

    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Scenario signals synthesis failed: %s", e)
        return {}

    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.error("Scenario signals JSON parse failed: %s | raw=%s", e, raw[:300])
        return {}

    signals = parsed.get("key_signals") or []
    return {
        "key_signals": [(str(x) or "").strip() for x in signals[:3] if x][:3],
        "strategic_imperative": (parsed.get("strategic_imperative") or "").strip(),
    }


# ── Per-topic Next Steps slide (Wiley slide 24 format) ──────────────────

_NEXT_STEPS_PROMPT = """You write the "Next Steps" slide for ONE topic in a quarterly executive deck — Wiley slide 24 format: 3 numbered immediate-priority actions. Plain business language, no methodology jargon.

CONTEXT
Topic: {topic}
Status distribution: {verdict_distribution}
Biggest mover this period: {biggest_mover}

PER-SCENARIO STATE
{scenario_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "next_steps": [
    {{ "category": "SHORT UPPERCASE TAG (1-3 words)", "action": "ONE sentence describing the concrete action — start with a verb" }},
    {{ "category": "...", "action": "..." }},
    {{ "category": "...", "action": "..." }}
  ]
}}

Exactly 3 entries. The category tag should name the domain (e.g. OPEN ACCESS, AI INTEGRATION, REGULATORY, PARTNERSHIPS, SUSTAINABILITY). The action sentence must be specific and actionable in the next 6 months — no "consider" or "explore"."""


async def synthesize_next_steps(assessment: dict) -> list:
    """3 numbered actions per topic (Wiley slide 24 layout). Cached upstream
    on ``assessment.summary['next_steps']``."""
    summary = assessment.get("summary") or {}
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})

    prompt = _NEXT_STEPS_PROMPT.format(
        topic=assessment.get("topic") or "—",
        verdict_distribution=_verdict_distribution_text(verdicts, bc_per),
        biggest_mover=_biggest_mover_text(verdicts, bc_per),
        scenario_block=_scenario_block_text(verdicts, bc_per),
    )

    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Next-steps synthesis failed: %s", e)
        return []

    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        parsed = json.loads(s)
    except Exception as e:
        logger.error("Next-steps JSON parse failed: %s | raw=%s", e, raw[:300])
        return []

    return [
        {
            "category": (s.get("category") or "").strip().upper()[:24],
            "action": (s.get("action") or "").strip(),
        }
        for s in (parsed.get("next_steps") or [])[:3]
        if isinstance(s, dict)
    ]


# ── Cross-topic synthesis for a whole bundle ────────────────────────────

_BUNDLE_OVERVIEW_PROMPT = """You write the "Strategic Overview" page for a quarterly executive briefing covering MULTIPLE topics. The reader is a senior business stakeholder. Plain language, no methodology jargon.

CONTEXT
Period: {period_label}
Topics in this bundle:
{topics_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "overview": "4-6 sentence paragraph synthesising the state of all the topics together. Name concrete actors / events / institutions from the per-topic data. Lead with the most consequential cross-topic finding. Do not list topics one-by-one — pull out the throughlines."
}}

Tone: this is the document a senior executive will read first. Punchy, substantive, no hedging."""


_BUNDLE_THEMES_PROMPT = """You write the "Cross-Cutting Strategic Themes" page for a quarterly executive briefing. The reader is a senior business stakeholder.

CONTEXT
Period: {period_label}
Topics in this bundle:
{topics_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "themes": [
    {{ "lead": "5-8 word lead phrase ending with a period — the theme headline", "body": "1-2 sentences describing how this theme spans at least 2 topics — name them by topic name" }},
    {{ "lead": "...", "body": "..." }},
    {{ "lead": "...", "body": "..." }},
    {{ "lead": "...", "body": "..." }}
  ]
}}

Exactly 4 themes. Each theme MUST span ≥2 of the topics above (name them explicitly in the body). Mirror the Wiley reference: "Trust is the central battleground.", "Federal pullback creates private opportunity.", "Asia is the growth frontier.", "AI is both accelerator and risk." — that level of crispness."""


_BUNDLE_FRAMEWORK_PROMPT = """You write the "Executive Decision Framework" slide for a quarterly executive briefing — three strategic priorities for LEADERSHIP across the whole portfolio of topics.

CONTEXT
Period: {period_label}
Topics in this bundle:
{topics_block}

WRITE
Produce strict JSON, no markdown, no preamble:

{{
  "priorities": [
    {{ "headline": "3-5 word priority title in title case", "body": "2-3 sentences explaining what leadership should do across the portfolio to act on this priority — name topics by name when relevant" }},
    {{ "headline": "...", "body": "..." }},
    {{ "headline": "...", "body": "..." }}
  ]
}}

Exactly 3 priorities. These are LEADERSHIP imperatives that span topics — different from per-topic Strategic Recommendations. Mirror the Wiley reference: "Embrace Technological Advancements" / "Foster Collaborative Partnerships" / "Prioritize Ethical Standards" — direction-setting for the executive."""


def _topics_block_text(items: list, max_topics: int = 10) -> str:
    """Format the bundle's per-topic state into a digest for cross-topic prompts."""
    lines = []
    for assessment, _run, _prior in items[:max_topics]:
        topic = assessment.get("topic") or "—"
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        n_scenarios = len(verdicts)
        # Status distribution
        dist = _verdict_distribution_text(verdicts, bc_per)
        # Briefing headline if cached
        briefing = (assessment.get("summary") or {}).get("topic_briefing") or {}
        headline = briefing.get("headline") or ""
        # Strongest single mover
        mover = _biggest_mover_text(verdicts, bc_per)
        # Top emerging theme
        surprises = sorted(assessment.get("surprises") or [],
                           key=lambda s: -(s.get("size") or 0))
        emerging = (surprises[0].get("label") if surprises else "") or "—"

        lines.append(
            f"• {topic}\n"
            f"  Headline: {headline}\n"
            f"  Scenarios ({n_scenarios}): {dist}\n"
            f"  Biggest mover: {mover}\n"
            f"  Top emerging theme: {emerging}"
        )
    return "\n\n".join(lines) if lines else "(no topics)"


async def _bundle_synth(prompt_template: str, period_label: str, items: list, key: str) -> dict:
    """Generic helper to call a bundle-level LLM synth prompt and return the parsed JSON."""
    prompt = prompt_template.format(
        period_label=period_label,
        topics_block=_topics_block_text(items),
    )
    try:
        raw = await _call_llm(prompt)
    except Exception as e:
        logger.error("Bundle synth %s failed: %s", key, e)
        return {}
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        return json.loads(s)
    except Exception as e:
        logger.error("Bundle synth %s JSON parse failed: %s | raw=%s", key, e, raw[:400])
        return {}


async def synthesize_bundle_strategic_overview(period_label: str, items: list) -> str:
    parsed = await _bundle_synth(_BUNDLE_OVERVIEW_PROMPT, period_label, items, "overview")
    return (parsed.get("overview") or "").strip()


async def synthesize_bundle_cross_cutting_themes(period_label: str, items: list) -> list:
    parsed = await _bundle_synth(_BUNDLE_THEMES_PROMPT, period_label, items, "themes")
    themes = parsed.get("themes") or []
    return [
        {"lead": (t.get("lead") or "").strip(), "body": (t.get("body") or "").strip()}
        for t in themes[:5]
        if isinstance(t, dict)
    ]


async def synthesize_bundle_decision_framework(period_label: str, items: list) -> list:
    parsed = await _bundle_synth(_BUNDLE_FRAMEWORK_PROMPT, period_label, items, "framework")
    priorities = parsed.get("priorities") or []
    return [
        {"headline": (p.get("headline") or "").strip(), "body": (p.get("body") or "").strip()}
        for p in priorities[:3]
        if isinstance(p, dict)
    ]


async def ensure_bundle_synthesis(period_label: str, cadence: str, items: list) -> dict:
    """Populate (or return cached) cross-topic synthesis for a bundle run.

    Cached by ``(cadence, period_label)`` in ``forecast_bundle_synthesis``.
    The same quarter's bundle returns instantly on re-export.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    cached = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    payload = cached.get("payload") or {}

    if not payload.get("strategic_overview"):
        logger.info("Bundle synth: strategic_overview for %s/%s", cadence, period_label)
        payload["strategic_overview"] = await synthesize_bundle_strategic_overview(period_label, items)
    if not payload.get("cross_cutting_themes"):
        logger.info("Bundle synth: cross_cutting_themes for %s/%s", cadence, period_label)
        payload["cross_cutting_themes"] = await synthesize_bundle_cross_cutting_themes(period_label, items)
    if not payload.get("executive_decision_framework"):
        logger.info("Bundle synth: executive_decision_framework for %s/%s", cadence, period_label)
        payload["executive_decision_framework"] = await synthesize_bundle_decision_framework(period_label, items)

    topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    db.facade.save_forecast_bundle_synthesis(cadence, period_label, payload, topics)
    return payload


async def ensure_narratives_for_assessment(assessment_id: str) -> dict:
    """Synthesize and persist any missing narratives for an assessment.

    Returns the updated assessment dict (hydrated with the new
    ``summary_md`` per scenario and ``summary.exec_narrative``)."""
    from app.database import get_database_instance
    db = get_database_instance()

    # Pull the full assessment (preferring this exact id, not the latest).
    from app.services.forecast_assessment_service import _hydrate_assessment_by_id
    assessment = _hydrate_assessment_by_id(db, assessment_id)
    if not assessment:
        return {}

    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = assessment.get("scenario_verdicts") or []

    # Per-scenario narratives in parallel
    pending = []
    for v in verdicts:
        existing = (v.get("summary_md") or "").strip()
        # The old aggregator wrote a verdict stub like "**Verdict: Inconclusive**
        # — H1: ..." that's clearly not a narrative. Detect it and regenerate.
        # Real narratives start with prose, not markdown emphasis or "Based on".
        if existing and not _is_stub_narrative(existing):
            continue
        baseline = bc_per.get(str(v.get("scenario_idx")))
        pending.append((v, baseline))

    if pending:
        logger.info("Synthesizing %d scenario narratives for assessment %s",
                    len(pending), assessment_id)
        results = await asyncio.gather(
            *[synthesize_scenario_narrative(v, b) for v, b in pending],
            return_exceptions=True,
        )
        for (v, _b), narrative in zip(pending, results):
            if isinstance(narrative, Exception):
                logger.warning("Narrative failed for scenario %s: %s",
                               v.get("scenario_idx"), narrative)
                continue
            if narrative:
                v["summary_md"] = narrative
                _persist_scenario_narrative(db, assessment_id, v.get("scenario_idx"), narrative)

    # Exec narrative
    if not (summary.get("exec_narrative") or "").strip():
        logger.info("Synthesizing exec narrative for assessment %s", assessment_id)
        exec_n = await synthesize_exec_narrative(assessment)
        if exec_n:
            summary["exec_narrative"] = exec_n
            assessment["summary"] = summary
            _persist_exec_narrative(db, assessment_id, exec_n)

    # Topic-level briefing synthesis (used by the bundle's per-topic
    # narrative slides). Cached in summary so repeated bundle generations
    # don't re-pay the LLM cost.
    if not summary.get("topic_briefing"):
        logger.info("Synthesizing topic briefing for assessment %s", assessment_id)
        briefing = await synthesize_topic_briefing(assessment)
        if briefing:
            summary["topic_briefing"] = briefing
            assessment["summary"] = summary
            _persist_summary_key(db, assessment_id, "topic_briefing", briefing)

    # Strategic recommendations (also cached on summary). Prior is fetched
    # lazily if available so the recommendations reflect the period delta.
    if not summary.get("strategic_recommendations"):
        logger.info("Synthesizing strategic recommendations for assessment %s", assessment_id)
        prior = None
        try:
            prior = db.facade.get_prior_live_assessment(
                run_id=assessment.get("run_id"),
                before_assessed_at=assessment.get("assessed_at"),
            ) or None
        except Exception as e:
            logger.warning("Could not fetch prior for recommendations: %s", e)
        recs = await synthesize_strategic_recommendations(assessment, prior=prior)
        if recs:
            summary["strategic_recommendations"] = recs
            assessment["summary"] = summary
            _persist_summary_key(db, assessment_id, "strategic_recommendations", recs)

    # Per-topic Next Steps (Wiley slide 24 format) — 3 numbered actions.
    if not summary.get("next_steps"):
        logger.info("Synthesizing next steps for assessment %s", assessment_id)
        steps = await synthesize_next_steps(assessment)
        if steps:
            summary["next_steps"] = steps
            assessment["summary"] = summary
            _persist_summary_key(db, assessment_id, "next_steps", steps)

    # Per-scenario key_signals + strategic_imperative — cached on each verdict
    # row's ``synthesis`` JSONB column. Done in parallel across scenarios.
    topic = assessment.get("topic") or ""
    pending_synth = []
    for v in verdicts:
        if v.get("verdict_label") == "Done":
            continue
        existing = v.get("synthesis") or {}
        if existing.get("key_signals") and existing.get("strategic_imperative"):
            continue
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        original_consensus = deck_info.get("consensus_pct")
        # Surface baseline correction for this verdict so the prompt sees it
        v_aug = dict(v)
        v_aug["top_articles"] = dict(v.get("top_articles") or {})
        v_aug["top_articles"]["baseline"] = bc_per.get(str(v.get("scenario_idx"))) or {}
        pending_synth.append((v, v_aug, original_consensus))

    if pending_synth:
        logger.info("Synthesizing per-scenario signals for %d scenarios on assessment %s",
                    len(pending_synth), assessment_id)
        results = await asyncio.gather(
            *[synthesize_scenario_signals(v_aug, topic=topic,
                                          original_consensus_pct=orig)
              for (_v, v_aug, orig) in pending_synth],
            return_exceptions=True,
        )
        for (v, _v_aug, _orig), out in zip(pending_synth, results):
            if isinstance(out, Exception):
                logger.warning("Scenario signals failed for scenario %s: %s",
                               v.get("scenario_idx"), out)
                continue
            if out:
                v["synthesis"] = out
                _persist_scenario_synthesis(db, assessment_id, v.get("scenario_idx"), out)

    return assessment


_STUB_MARKERS = ("**Verdict:", "Based on ", "Maps to deck scenario")


def _is_stub_narrative(s: str) -> bool:
    """The pre-narrative aggregator emitted a templated verdict stub keyed on
    these markers. Detect so we overwrite rather than preserve."""
    head = s.lstrip()[:80]
    return any(m in head or m in s for m in _STUB_MARKERS)


def _persist_scenario_synthesis(db, assessment_id: str, scenario_idx: int, payload: dict):
    """Persist per-scenario synthesis (key_signals + strategic_imperative)
    into ``forecast_scenario_verdicts.synthesis`` JSONB."""
    conn = db._temp_get_connection()
    try:
        conn.execute(
            text(
                "UPDATE forecast_scenario_verdicts "
                "SET synthesis = CAST(:p AS jsonb) "
                "WHERE assessment_id = :aid AND scenario_idx = :idx"
            ),
            {"p": json.dumps(payload), "aid": assessment_id, "idx": scenario_idx},
        )
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        try: conn.close()
        except Exception: pass


def _persist_scenario_narrative(db, assessment_id: str, scenario_idx: int, narrative: str):
    conn = db._temp_get_connection()
    try:
        conn.execute(
            text(
                "UPDATE forecast_scenario_verdicts "
                "SET summary_md = :n "
                "WHERE assessment_id = :aid AND scenario_idx = :idx"
            ),
            {"n": narrative, "aid": assessment_id, "idx": scenario_idx},
        )
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        try: conn.close()
        except Exception: pass


def _persist_summary_key(db, assessment_id: str, key: str, value) -> None:
    """Generic read-modify-write to set a key inside the assessment row's
    ``summary`` JSONB. Mirrors :func:`_persist_exec_narrative` but for any
    serialisable value (dict, list, str).

    Read-modify-write because the summary column was historically saved via
    ``json.dumps()`` into jsonb — which double-encodes it as a jsonb string,
    breaking the ``||`` merge operator. So we unwrap, merge, write back."""
    conn = db._temp_get_connection()
    try:
        row = conn.execute(
            text("SELECT summary FROM forecast_assessments WHERE id = :aid"),
            {"aid": assessment_id},
        ).fetchone()
        if not row:
            return
        current = row[0]
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except Exception:
                current = {}
        if isinstance(current, list):
            current = next((x for x in current if isinstance(x, dict)),
                           current[0] if current and isinstance(current[0], str) else {})
            if isinstance(current, str):
                try: current = json.loads(current)
                except Exception: current = {}
        if not isinstance(current, dict):
            current = {}
        current[key] = value

        conn.execute(
            text("UPDATE forecast_assessments SET summary = CAST(:s AS jsonb) WHERE id = :aid"),
            {"s": json.dumps(current), "aid": assessment_id},
        )
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        try: conn.close()
        except Exception: pass


def _persist_exec_narrative(db, assessment_id: str, narrative: str):
    """Patch ``summary->'exec_narrative'`` in the assessments table.

    Read-modify-write in Python because the summary column was historically
    saved via ``json.dumps()`` into a jsonb column, which double-encodes it
    as a jsonb string. ``string_jsonb || object_jsonb`` promotes both to an
    array — wrong. So we unwrap, merge, and write back as a fresh object.
    """
    conn = db._temp_get_connection()
    try:
        row = conn.execute(
            text("SELECT summary FROM forecast_assessments WHERE id = :aid"),
            {"aid": assessment_id},
        ).fetchone()
        if not row:
            return
        current = row[0]
        # Drivers may return summary as dict, str, or list depending on how it
        # was originally inserted. Coerce to a dict-shaped object.
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except Exception:
                current = {}
        if isinstance(current, list):
            # Earlier broken-||-merge produced an array; salvage the first
            # element that's a dict and discard the rest.
            current = next((x for x in current if isinstance(x, dict)),
                           current[0] if current and isinstance(current[0], str) else {})
            if isinstance(current, str):
                try: current = json.loads(current)
                except Exception: current = {}
        if not isinstance(current, dict):
            current = {}
        current["exec_narrative"] = narrative

        conn.execute(
            text("UPDATE forecast_assessments SET summary = CAST(:s AS jsonb) WHERE id = :aid"),
            {"s": json.dumps(current), "aid": assessment_id},
        )
        try:
            conn.commit()
        except Exception:
            pass
    finally:
        try: conn.close()
        except Exception: pass
