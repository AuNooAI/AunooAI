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


async def _call_llm(prompt: str) -> str:
    """Call the narrative model via AIModelFactory (which returns LiteLLMModel
    with proper content extraction). The bare ``get_ai_model()`` returns the
    base AIModel whose ``generate_sync`` yields a raw Choice object — not what
    we want."""
    from app.ai_models import AIModelFactory
    model = AIModelFactory.get_model(NARRATIVE_MODEL)
    messages = [{"role": "user", "content": prompt}]
    result = await model.agenerate_response(messages)
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
        label = (baseline or {}).get("label") or verdict.get("verdict_label") or "—"
        return (
            f"No supporting or contradicting articles attributable to this scenario "
            f"in the assessed window. The reranker either found no topical fits or all "
            f"candidates fell below the assignment-margin gate, so we can't narrate "
            f"concrete developments here. Verdict: {label} — derived from the "
            f"baseline-rate comparison alone."
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

    return assessment


_STUB_MARKERS = ("**Verdict:", "Based on ", "Maps to deck scenario")


def _is_stub_narrative(s: str) -> bool:
    """The pre-narrative aggregator emitted a templated verdict stub keyed on
    these markers. Detect so we overwrite rather than preserve."""
    head = s.lstrip()[:80]
    return any(m in head or m in s for m in _STUB_MARKERS)


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
