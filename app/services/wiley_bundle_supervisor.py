"""WileyBundleSupervisor — multi-agent pipeline that produces the analytical
content for the recurring Wiley quarterly intelligence deck.

Architecture mirrors JP Morgan's "Ask David" pattern:

    supervisor (plan)
        ↓
    specialised subagents (retrieval, analytics, briefing, recommendations,
                            next_steps, cross_topic, exec_summary)
        ↓
    LLM-as-judge reviewer (gpt-5 with reasoning_effort=high)
        ↓
    gate — errors block, warnings annotate, clean approves
        ↓
    render (PPTX builder, only after gate clears)

This module exposes :func:`run_pipeline` as an async generator that yields
per-stage progress updates, matching the existing pattern used by
:class:`ExtremeOutlierService` and :class:`ExecutiveBriefingService`. The
:mod:`wiley_delivery_service` consumes it and forwards progress to the
``BackgroundTaskManager`` so the UI can poll.

All agent prompts live in ``data/auspex/agents/wiley_*.md`` and are loaded
via the existing ``tool_loader`` registry — same convention as the EOS
and Executive Briefing services.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.ai_models import AIModelFactory
from app.services.tool_loader import get_tool_loader

logger = logging.getLogger(__name__)


# ── Custom exception raised when the reviewer blocks delivery ─────────

class BundleRequiresReviewError(Exception):
    """Raised when the LLM-as-judge reviewer flags ``error`` severity issues.

    The route layer catches this and returns HTTP 202 + the findings to
    the UI so a human can resolve before the deck ships.
    """
    def __init__(self, cadence: str, period_label: str, findings: list):
        self.cadence = cadence
        self.period_label = period_label
        self.findings = findings
        super().__init__(
            f"Bundle {cadence}/{period_label} requires review: "
            f"{sum(1 for f in findings if f.get('severity') == 'error')} errors"
        )


# ── Agent invocation helper ──────────────────────────────────────────

async def _call_agent(agent_name: str, payload: dict, *, reasoning_effort: str = None) -> dict:
    """Load the named agent's system prompt + model_config from the tool_loader
    registry, call the model with the payload as a single user message, and
    parse the response as JSON.

    Returns the parsed dict or {} on failure (the supervisor's gate decides
    how to handle missing artefacts).
    """
    tl = get_tool_loader()
    agent = tl.get_agent(agent_name)
    if not agent:
        logger.error("Agent %s not found in tool_loader registry", agent_name)
        return {}

    model_cfg = (agent.metadata or {}).get("model_config", {}) or {}
    model_name = model_cfg.get("model", "gpt-5")
    temperature = model_cfg.get("temperature", 0.3)
    max_tokens = model_cfg.get("max_tokens", 2000)
    cfg_reasoning = model_cfg.get("reasoning_effort")

    call_kwargs: Dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if cfg_reasoning or reasoning_effort:
        call_kwargs["reasoning_effort"] = reasoning_effort or cfg_reasoning

    system_prompt = agent.content or ""
    user_message = json.dumps(payload, default=str)

    model = AIModelFactory.get_model(model_name)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        raw = await model.agenerate_response(messages, **call_kwargs)
    except Exception as e:
        logger.error("Agent %s LLM call failed: %s", agent_name, e)
        return {}

    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    try:
        return json.loads(s)
    except Exception as e:
        logger.error("Agent %s JSON parse failed: %s | raw=%.400s", agent_name, e, raw or "")
        return {}


# ── Per-stage payload builders ──────────────────────────────────────

def _supervisor_payload(items: list, cadence: str, period_label: str, *,
                        cross_topic_cached: bool, exec_summary_cached: bool,
                        prior_review: Optional[dict] = None) -> dict:
    """Build the inputs the supervisor agent uses to plan the bundle."""
    topics = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        summary = assessment.get("summary") or {}
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        n_with_synth = sum(1 for v in verdicts if (v.get("synthesis") or {}).get("key_signals"))
        topics.append({
            "topic": topic,
            "assessment_id": assessment.get("id"),
            "briefing_cached": bool(summary.get("topic_briefing")),
            "recs_cached": bool(summary.get("strategic_recommendations")),
            "next_steps_cached": bool(summary.get("next_steps")),
            "scenario_synthesis_cached_pct": (
                n_with_synth / max(len(verdicts), 1) if verdicts else 0.0
            ),
        })
    return {
        "cadence": cadence,
        "period_label": period_label,
        "topics": topics,
        "cross_topic_cached": cross_topic_cached,
        "exec_summary_cached": exec_summary_cached,
        "prior_reviewer_outcome": (prior_review or {}).get("status"),
        "prior_reviewer_findings": (prior_review or {}).get("reviewer_findings"),
    }


def _topic_data_payload(assessment: dict) -> dict:
    """Distil one topic's assessment into the shape the per-topic agents expect."""
    summary = assessment.get("summary") or {}
    bc_per = ((summary.get("baseline_correction") or {}).get("per_scenario") or {})
    verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                if v.get("verdict_label") != "Done"]

    # Translate to customer language so the prompts don't have to
    CUSTOMER = {"Above baseline": "Strengthening", "At baseline": "Stable", "Below baseline": "Cooling"}
    def _cust(label):
        return CUSTOMER.get(label, label) if label else "—"

    scenarios = []
    for v in verdicts:
        key = str(v.get("scenario_idx"))
        bc = bc_per.get(key) or {}
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        scenarios.append({
            "scenario_idx": v.get("scenario_idx"),
            "name": deck_info.get("deck_scenario_name") or v.get("scenario_title"),
            "horizon": (v.get("horizon_type") or "h1").upper(),
            "status": _cust(bc.get("label") or v.get("verdict_label")),
            "confirmation_delta_pct": round((bc.get("net_rate") or 0) * 100, 2) if bc.get("net_rate") is not None else None,
            "original_consensus_pct": deck_info.get("consensus_pct"),
            "current_consensus_pct": v.get("current_consensus_pct"),
            "supports": v.get("supports") or 0,
            "contradicts": v.get("contradicts") or 0,
            "top_supports": (v.get("top_articles") or {}).get("supports") or [],
            "top_contras": (v.get("top_articles") or {}).get("contradicts") or [],
        })

    # Status distribution + biggest mover
    labels = [s.get("status") for s in scenarios if s.get("status") and s.get("status") != "—"]
    status_dist = {x: labels.count(x) for x in set(labels)}
    biggest = max(scenarios, key=lambda s: abs(s.get("confirmation_delta_pct") or 0), default=None)

    return {
        "topic": assessment.get("topic"),
        "forecast_published": summary.get("forecast_generated_at"),
        "assessed_at": summary.get("assessed_at"),
        "status_distribution": status_dist,
        "biggest_mover": biggest,
        "scenarios": scenarios,
        "emerging_themes": [
            {"label": s.get("label"), "size": s.get("size"),
             "sample_articles": (s.get("sample_articles") or [])[:3]}
            for s in (assessment.get("surprises") or [])[:5]
        ],
    }


# ── Stage runners ────────────────────────────────────────────────────

async def _run_briefings(items: list, plan: dict) -> dict:
    """Per-topic Briefing Synthesis. Skips topics whose briefing is cached
    unless the plan explicitly targets them."""
    target_topics = _plan_targets(plan, "briefing")
    tasks = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("topic_briefing")
                and (not target_topics or topic not in target_topics)):
            continue
        tasks.append((topic, _call_agent("wiley_briefing_agent",
                                         _topic_data_payload(assessment))))
    results = {}
    for topic, fut in tasks:
        results[topic] = await fut
    return results


async def _run_recommendations(items: list, plan: dict) -> dict:
    target_topics = _plan_targets(plan, "recommendations")
    out = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("strategic_recommendations")
                and (not target_topics or topic not in target_topics)):
            continue
        out[topic] = await _call_agent("wiley_recs_agent", _topic_data_payload(assessment))
    return out


async def _run_next_steps(items: list, plan: dict) -> dict:
    target_topics = _plan_targets(plan, "next_steps")
    out = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("next_steps")
                and (not target_topics or topic not in target_topics)):
            continue
        out[topic] = await _call_agent("wiley_next_steps_agent", _topic_data_payload(assessment))
    return out


def _plan_targets(plan: dict, stage_name: str) -> Optional[set]:
    """Extract the ``targets`` list for a stage from the supervisor's plan.
    Returns None if no targeting (run all eligible topics) or a set of topic
    names if the plan specified them."""
    for s in (plan or {}).get("plan", []) or []:
        if s.get("stage") == stage_name:
            t = s.get("targets")
            return set(t) if t else None
    return None


def _stage_in_plan(plan: dict, stage_name: str) -> bool:
    return any(s.get("stage") == stage_name for s in (plan or {}).get("plan", []) or [])


# ── Cross-topic + exec summary helpers ───────────────────────────────

def _cross_topic_payload(items: list, period_label: str, briefings: dict) -> dict:
    topics = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        CUSTOMER = {"Above baseline": "Strengthening", "At baseline": "Stable", "Below baseline": "Cooling"}
        dist = {}
        for v in verdicts:
            key = str(v.get("scenario_idx"))
            label = (bc_per.get(key) or {}).get("label") or v.get("verdict_label")
            cust = CUSTOMER.get(label, label) if label else "—"
            dist[cust] = dist.get(cust, 0) + 1
        # biggest mover
        best = None
        for v in verdicts:
            key = str(v.get("scenario_idx"))
            net = (bc_per.get(key) or {}).get("net_rate")
            if net is None:
                continue
            if best is None or abs(net) > abs(best[0]):
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                best = (net, deck_info.get("deck_scenario_name") or v.get("scenario_title"))
        emerging = (assessment.get("surprises") or [])
        top_emerging = (emerging[0].get("label") if emerging else "") or "—"
        briefing = briefings.get(topic) or (assessment.get("summary") or {}).get("topic_briefing") or {}
        topics.append({
            "topic": topic,
            "briefing_headline": briefing.get("headline") or "",
            "status_distribution": dist,
            "biggest_mover": {"name": best[1], "delta_pct": round((best[0] or 0)*100, 2)} if best else None,
            "top_emerging_theme": top_emerging,
        })
    return {"period_label": period_label, "topics": topics}


def _exec_summary_payload(items: list, period_label: str,
                          cross_topic: dict, eos_per_topic: dict) -> dict:
    overview = (cross_topic or {}).get("strategic_overview") or ""
    # Status distribution across the whole bundle
    CUSTOMER = {"Above baseline": "Strengthening", "At baseline": "Stable", "Below baseline": "Cooling"}
    dist = {"Strengthening": 0, "Stable": 0, "Cooling": 0, "Inconclusive": 0}
    biggest = None
    for assessment, _run, _prior in items:
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        bc_per = ((assessment.get("summary") or {}).get("baseline_correction") or {}).get("per_scenario") or {}
        for v in verdicts:
            key = str(v.get("scenario_idx"))
            label = (bc_per.get(key) or {}).get("label") or v.get("verdict_label")
            cust = CUSTOMER.get(label, label) if label else None
            if cust and cust in dist:
                dist[cust] += 1
            net = (bc_per.get(key) or {}).get("net_rate")
            if net is not None and (biggest is None or abs(net) > abs(biggest[0])):
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                biggest = (net, assessment.get("topic"),
                           deck_info.get("deck_scenario_name") or v.get("scenario_title"))

    black_swans = []
    for topic, scenarios in (eos_per_topic or {}).items():
        for s in scenarios or []:
            if (s.get("category") or "").lower() == "black_swan":
                black_swans.append({"topic": topic, "title": s.get("title")})

    return {
        "period_label": period_label,
        "strategic_overview": overview,
        "status_distribution": dist,
        "biggest_mover": (
            {"topic": biggest[1], "scenario": biggest[2],
             "delta_pct": round(biggest[0]*100, 2)} if biggest else None
        ),
        "topics": [(a.get("topic") or "—") for (a, _r, _p) in items],
        "black_swan_count": len(black_swans),
        "top_black_swan": black_swans[0] if black_swans else None,
    }


# ── Reviewer payload — combines everything for the judge ─────────────

def _reviewer_payload(period_label: str, items: list, briefings: dict,
                       recommendations: dict, next_steps: dict,
                       cross_topic: dict, exec_summary: dict,
                       eos_per_topic: dict) -> dict:
    per_topic = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        per_topic[topic] = {
            "data": _topic_data_payload(assessment),
            "briefing": briefings.get(topic) or (assessment.get("summary") or {}).get("topic_briefing"),
            "recommendations": recommendations.get(topic) or {
                "recommendations": (assessment.get("summary") or {}).get("strategic_recommendations") or []
            },
            "next_steps": next_steps.get(topic) or {
                "next_steps": (assessment.get("summary") or {}).get("next_steps") or []
            },
        }
    return {
        "period_label": period_label,
        "per_topic": per_topic,
        "cross_topic": cross_topic or {},
        "exec_summary": exec_summary or {},
        "eos_per_topic": eos_per_topic or {},
    }


# ── Public pipeline ─────────────────────────────────────────────────

async def run_pipeline(
    items: list, *, cadence: str, period_label: str,
    eos_per_topic: dict,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the full multi-agent bundle pipeline.

    Yields ``{stage, status, progress, payload?}`` dicts. The caller (wiley
    delivery service) forwards these to the BackgroundTaskManager.

    Final yield is ``{stage: 'complete', status: 'approved'|'revision_requested',
    payload: {...}}`` carrying the synthesised artefacts. On
    ``revision_requested``, the caller raises BundleRequiresReviewError so
    the route returns HTTP 202 + findings.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    # Existing caches
    prior_synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    cross_cached = bool((prior_synth.get("payload") or {}).get("strategic_overview"))
    exec_cached = bool((prior_synth.get("payload") or {}).get("exec_summary"))
    prior_review = db.facade.get_forecast_bundle_review(cadence, period_label) or {}

    # ── Stage 1: supervisor plans ───────────────────────────────────
    yield {"stage": "supervisor", "status": "started", "progress": 0.05}
    plan = await _call_agent("wiley_supervisor_agent", _supervisor_payload(
        items, cadence, period_label,
        cross_topic_cached=cross_cached, exec_summary_cached=exec_cached,
        prior_review=prior_review,
    ))
    yield {"stage": "supervisor", "status": "completed", "progress": 0.1,
           "payload": {"plan_stages": [s.get("stage") for s in plan.get("plan", [])]}}

    # ── Stages 2-3 are pure data; skip in this slim build — the existing
    # narrative agents already have access to the same source data via the
    # topic payloads we hand them. Retrieval/analytics live as helpers
    # inside the topic_data_payload builder.

    # ── Stage 4: per-topic Briefing Synthesis ───────────────────────
    briefings = {}
    if _stage_in_plan(plan, "briefing"):
        yield {"stage": "briefing", "status": "started", "progress": 0.2}
        briefings = await _run_briefings(items, plan)
        # Persist into assessment.summary.topic_briefing so future runs hit cache
        for topic, payload in briefings.items():
            if payload:
                _persist_topic_briefing(db, items, topic, payload)
        yield {"stage": "briefing", "status": "completed", "progress": 0.35,
               "payload": {"topics": list(briefings.keys())}}

    # ── Stage 5: per-topic Strategic Recommendations + Imperatives ──
    recommendations = {}
    if _stage_in_plan(plan, "recommendations"):
        yield {"stage": "recommendations", "status": "started", "progress": 0.4}
        recommendations = await _run_recommendations(items, plan)
        for topic, payload in recommendations.items():
            if payload:
                _persist_recommendations(db, items, topic, payload)
        yield {"stage": "recommendations", "status": "completed", "progress": 0.55,
               "payload": {"topics": list(recommendations.keys())}}

    # ── Stage 6: per-topic Next Steps ───────────────────────────────
    next_steps = {}
    if _stage_in_plan(plan, "next_steps"):
        yield {"stage": "next_steps", "status": "started", "progress": 0.6}
        next_steps = await _run_next_steps(items, plan)
        for topic, payload in next_steps.items():
            if payload:
                _persist_next_steps(db, items, topic, payload)
        yield {"stage": "next_steps", "status": "completed", "progress": 0.7,
               "payload": {"topics": list(next_steps.keys())}}

    # ── Stage 7: cross-topic synthesis ──────────────────────────────
    cross_topic = (prior_synth.get("payload") or {}).get("strategic_overview") and prior_synth.get("payload") or {}
    if _stage_in_plan(plan, "cross_topic") or not cross_cached:
        yield {"stage": "cross_topic", "status": "started", "progress": 0.75}
        cross_topic = await _call_agent("wiley_cross_topic_agent",
                                         _cross_topic_payload(items, period_label, briefings))
        yield {"stage": "cross_topic", "status": "completed", "progress": 0.82}

    # ── Stage 8: Executive Summary letter ────────────────────────────
    exec_summary = (prior_synth.get("payload") or {}).get("exec_summary") or {}
    if _stage_in_plan(plan, "exec_summary") or not exec_summary:
        yield {"stage": "exec_summary", "status": "started", "progress": 0.85}
        exec_summary = await _call_agent("wiley_exec_summary_agent",
                                          _exec_summary_payload(items, period_label,
                                                                cross_topic, eos_per_topic))
        yield {"stage": "exec_summary", "status": "completed", "progress": 0.9}

    # Persist the cross-topic synth payload (overwrites any prior)
    bundle_payload = dict((prior_synth.get("payload") or {}))
    if cross_topic:
        bundle_payload.update({
            "strategic_overview": cross_topic.get("strategic_overview") or bundle_payload.get("strategic_overview"),
            "cross_cutting_themes": cross_topic.get("cross_cutting_themes") or bundle_payload.get("cross_cutting_themes"),
            "executive_decision_framework": cross_topic.get("executive_decision_framework") or bundle_payload.get("executive_decision_framework"),
        })
    if exec_summary:
        bundle_payload["exec_summary"] = exec_summary
    topics_list = [(a.get("topic") or "—") for (a, _r, _p) in items]
    try:
        db.facade.save_forecast_bundle_synthesis(cadence, period_label, bundle_payload, topics_list)
    except Exception as e:
        logger.warning("Failed to persist bundle synthesis: %s", e)

    # ── Stage 9: Reviewer (LLM-as-judge) ─────────────────────────────
    # Skip the reviewer if a human has already approved this period —
    # otherwise every re-export would re-fire the LLM-as-judge and could
    # overwrite the manual approval with fresh findings. The gate state is
    # the source of truth.
    existing_review_state = (prior_review or {}).get("status")
    if existing_review_state in ("approved", "approved_with_warnings"):
        logger.info("Bundle %s/%s already %s — skipping reviewer",
                    cadence, period_label, existing_review_state)
        verdict = existing_review_state
        findings = (prior_review or {}).get("reviewer_findings") or []
        yield {"stage": "reviewer", "status": "skipped_already_approved",
               "progress": 0.97,
               "payload": {"verdict": verdict, "prior_approval": True}}
    else:
        yield {"stage": "reviewer", "status": "started", "progress": 0.92}
        review_payload = _reviewer_payload(period_label, items, briefings,
                                            recommendations, next_steps,
                                            cross_topic, exec_summary, eos_per_topic)
        review_result = await _call_agent("wiley_reviewer_agent", review_payload,
                                           reasoning_effort="high")
        findings = (review_result or {}).get("findings") or []
        summary = (review_result or {}).get("summary") or {}
        verdict = summary.get("verdict") or ("revision_requested" if
                                              any(f.get("severity") == "error" for f in findings)
                                              else "approved")
        yield {"stage": "reviewer", "status": "completed", "progress": 0.97,
               "payload": {"verdict": verdict, "errors": summary.get("errors", 0),
                           "warnings": summary.get("warnings", 0)}}

        # Persist review state. Read the reviewer's actual model from the agent
        # config so the audit row reflects what really ran (not a hard-coded label).
        reviewer_agent_cfg = (get_tool_loader().get_agent("wiley_reviewer_agent") or None)
        reviewer_model = ((reviewer_agent_cfg.metadata or {}).get("model_config", {}).get("model")
                           if reviewer_agent_cfg else None) or "gpt-4.1"
        db.facade.upsert_forecast_bundle_review(
            cadence, period_label,
            status=verdict,
            reviewer_findings=findings,
            reviewer_model=reviewer_model,
        )

    # ── Gate ────────────────────────────────────────────────────────
    if verdict == "revision_requested":
        yield {
            "stage": "complete", "status": "revision_requested", "progress": 1.0,
            "payload": {
                "findings": findings, "cadence": cadence, "period_label": period_label,
                "bundle_payload": bundle_payload,
            },
        }
        return

    # ── Approved (with or without warnings) ─────────────────────────
    yield {
        "stage": "complete", "status": verdict, "progress": 1.0,
        "payload": {
            "findings": findings, "cadence": cadence, "period_label": period_label,
            "bundle_payload": bundle_payload,
        },
    }


# ── Per-assessment persistence helpers ───────────────────────────────

def _find_assessment(items: list, topic: str) -> Optional[dict]:
    for assessment, _run, _prior in items:
        if (assessment.get("topic") or "") == topic:
            return assessment
    return None


def _persist_topic_briefing(db, items: list, topic: str, payload: dict):
    a = _find_assessment(items, topic)
    if not a or not a.get("id"):
        return
    from app.services.forecast_narrative import _persist_summary_key
    summary = a.get("summary") or {}
    summary["topic_briefing"] = payload
    a["summary"] = summary
    try:
        _persist_summary_key(db, a["id"], "topic_briefing", payload)
    except Exception as e:
        logger.warning("Failed to persist briefing for %s: %s", topic, e)


def _persist_recommendations(db, items: list, topic: str, payload: dict):
    a = _find_assessment(items, topic)
    if not a or not a.get("id"):
        return
    from app.services.forecast_narrative import _persist_summary_key, _persist_scenario_synthesis
    summary = a.get("summary") or {}
    recs = payload.get("recommendations") or []
    if recs:
        summary["strategic_recommendations"] = recs
        a["summary"] = summary
        try:
            _persist_summary_key(db, a["id"], "strategic_recommendations", recs)
        except Exception as e:
            logger.warning("Failed to persist recs for %s: %s", topic, e)
    # scenario_imperatives — write back into per-verdict synthesis JSONB
    name_to_idx = {}
    for v in (a.get("scenario_verdicts") or []):
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        nm = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        if nm:
            name_to_idx[nm] = v.get("scenario_idx")
    for entry in (payload.get("scenario_imperatives") or []):
        nm = entry.get("scenario")
        idx = name_to_idx.get(nm)
        if idx is None:
            continue
        synth_payload = {
            "key_signals": entry.get("key_signals") or [],
            "strategic_imperative": entry.get("imperative") or "",
        }
        try:
            _persist_scenario_synthesis(db, a["id"], idx, synth_payload)
        except Exception as e:
            logger.warning("Failed to persist scenario synthesis (%s/%s): %s", topic, nm, e)


def _persist_next_steps(db, items: list, topic: str, payload: dict):
    a = _find_assessment(items, topic)
    if not a or not a.get("id"):
        return
    from app.services.forecast_narrative import _persist_summary_key
    steps = payload.get("next_steps") or []
    if not steps:
        return
    summary = a.get("summary") or {}
    summary["next_steps"] = steps
    a["summary"] = summary
    try:
        _persist_summary_key(db, a["id"], "next_steps", steps)
    except Exception as e:
        logger.warning("Failed to persist next_steps for %s: %s", topic, e)
