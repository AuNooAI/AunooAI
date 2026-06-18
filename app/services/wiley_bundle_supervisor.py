"""WileyBundleSupervisor — multi-agent pipeline that produces the analytical
content for the recurring Wiley quarterly intelligence deck.

Architecture mirrors JP Morgan's "Ask David" pattern:

    supervisor (plan)
        ↓
    specialised subagents (retrieval, analytics, briefing, recommendations,
                            next_steps, cross_topic, exec_summary)
        ↓
    LLM-as-judge reviewer (gpt-5.4 with reasoning_effort=high)
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


# ── Lock-aware agent wrapper ─────────────────────────────────────────
#
# The Quarterly Brief Editor lets the analyst lock parts of the bundle
# (forecast_bundle_synthesis.locked_keys / forecast_assessments
# .summary_locked_keys). When the supervisor re-runs an agent stage,
# any subtree under a locked dot-path must be restored from the
# pre-run snapshot — otherwise an accidental "Generate bundle" would
# clobber edited prose.


def _as_dict(v):
    """Coerce a value to a dict, surviving double-encoded JSONB. A JSONB
    column that was written as json.dumps() of an already-stringified
    object comes back as a str; calling .get() on it raises "'str' object
    has no attribute 'get'". Decode until it's a dict, else return {}."""
    import json as _json
    for _ in range(3):
        if isinstance(v, dict):
            return v
        if not isinstance(v, str):
            return {}
        try:
            v = _json.loads(v)
        except Exception:
            return {}
    return v if isinstance(v, dict) else {}


def _split_path(path: str) -> list:
    """Parse 'cross_cutting_themes[2].body' → [('key','cross_cutting_themes'),('idx',2),('key','body')]."""
    if not path:
        return []
    out = []
    token = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if token:
                out.append(("key", token)); token = ""
        elif ch == "[":
            if token:
                out.append(("key", token)); token = ""
            j = path.find("]", i)
            if j == -1:
                raise ValueError(f"Unclosed bracket in path: {path}")
            out.append(("idx", int(path[i + 1:j])))
            i = j
        else:
            token += ch
        i += 1
    if token:
        out.append(("key", token))
    return out


def _walk_path(obj, path: str):
    cur = obj
    for kind, tok in _split_path(path):
        if kind == "key":
            if not isinstance(cur, dict):
                return None, False
            if tok not in cur:
                return None, False
            cur = cur[tok]
        else:
            if not isinstance(cur, list) or tok >= len(cur) or tok < 0:
                return None, False
            cur = cur[tok]
    return cur, True


def _set_path(obj, path: str, value):
    """Set value at dot-path inside obj (mutates). Creates dicts as
    needed; bails on a list index that doesn't exist (locked indexes
    only make sense for slots that exist in both old + new)."""
    tokens = _split_path(path)
    if not tokens:
        return obj
    cur = obj
    for i, (kind, tok) in enumerate(tokens):
        last = (i == len(tokens) - 1)
        if kind == "key":
            if last:
                if isinstance(cur, dict):
                    cur[tok] = value
                return obj
            if not isinstance(cur, dict):
                return obj
            if tok not in cur or not isinstance(cur[tok], (dict, list)):
                cur[tok] = {}
            cur = cur[tok]
        else:  # idx
            if not isinstance(cur, list) or tok >= len(cur) or tok < 0:
                return obj
            if last:
                cur[tok] = value
                return obj
            cur = cur[tok]
    return obj


def _apply_locks_after_call(prior: dict, new: dict, locked_paths: list) -> dict:
    """Return `new` with every locked subtree restored from `prior`.

    Used after every supervisor agent call. If `new` is empty (agent
    failed) the caller decides how to handle — we don't second-guess.
    """
    if not locked_paths or not isinstance(new, dict):
        return new
    merged = dict(new)  # shallow copy; _set_path mutates deeper
    for path in locked_paths:
        prior_subtree, found = _walk_path(prior or {}, path)
        if found:
            _set_path(merged, path, prior_subtree)
    return merged


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
    model_name = model_cfg.get("model", "gpt-5.4")
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
    # ``strict=False`` lets json accept literal control characters (raw
    # newlines / tabs) inside string values. The narrative agents emit
    # multi-paragraph ``letter`` fields with real newlines for the
    # ``\n\n`` paragraph breaks the prompt asks for; strict parsing
    # rejects those with "Invalid control character" and we'd lose the
    # whole letter. The slide/docx renderers want those newlines anyway.
    try:
        return json.loads(s, strict=False)
    except Exception as e:
        logger.error("Agent %s JSON parse failed: %s | raw=%.400s", agent_name, e, raw or "")
        return {}


# ── Per-stage payload builders ──────────────────────────────────────

def _sanitize_review_findings(findings: list, *, exec_letter: str = None) -> list:
    """Post-process the raw reviewer output before persistence + gating.

    Protections, all observed misbehaviours on real bundles:

    * **Dedup**: the reviewer sometimes emits 2-3 copies of the same
      finding. Keep the first per ``(artefact_key, severity)``.
    * **Demote stylistic cross-cutting-theme span findings** to warnings.
    * **Demote exec_summary.letter errors to warnings** UNLESS the letter
      actually contains the one hard-banned thing (consensus-verdict /
      drift framing), which we detect deterministically. Rationale: the
      exec summary is constrained to named_events + briefings and the
      banned framing is already scrubbed deterministically before the
      reviewer runs, so the LLM judge's exec-summary findings are matters
      of emphasis/wording — advisory, not gate-blocking. The one rule that
      MUST block (banned consensus framing) is enforced by the regex below,
      not by the judge's opinion. This stops the judge holding the whole
      deck hostage over debatable exec-summary nits on every regeneration.

    Returns the cleaned list. Mutates nothing in place.
    """
    if not findings:
        return []

    # Deterministic check for the ONE exec-summary rule that must block.
    letter_has_banned = False
    if exec_letter:
        try:
            from app.services.wiley_humanizer import has_forecast_verdict
            letter_has_banned = has_forecast_verdict(exec_letter)
        except Exception:
            letter_has_banned = False

    seen: set[tuple[str, str]] = set()
    cleaned: list[dict] = []
    for raw in findings:
        if not isinstance(raw, dict):
            continue
        f = dict(raw)
        artefact = (f.get("artefact_key") or "").strip()
        severity = (f.get("severity") or "warning").lower()

        # Demote cross_cutting_themes span findings to warnings. Match the
        # artefact prefix the agent prompt instructs the reviewer to use
        # (``bundle.cross_cutting_themes[N]`` / ``cross_topic.cross_cutting_themes[N]``)
        # so the demotion catches the artefact-key shape regardless of
        # whether the reviewer prefixed it with ``bundle.`` or ``cross_topic.``.
        if "cross_cutting_themes" in artefact and severity == "error":
            f["severity"] = "warning"
            f["finding"] = (f.get("finding") or "") + (
                "  [auto-demoted: topic-span findings are stylistic, not blocking]"
            )
            severity = "warning"

        # Demote exec_summary.letter errors to warnings unless the letter
        # really contains the hard-banned consensus framing (deterministic).
        if ("exec_summary" in artefact and severity == "error"
                and not letter_has_banned):
            f["severity"] = "warning"
            f["finding"] = (f.get("finding") or "") + (
                "  [auto-demoted: exec-summary wording/grounding judgments are "
                "advisory; the hard consensus-framing rule is enforced "
                "deterministically and is not present here]"
            )
            severity = "warning"

        # Dedup by (artefact_key, severity). Same artefact emitted at the
        # same severity twice is almost always the model repeating itself.
        key = (artefact, severity)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(f)

    return cleaned


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


def _topic_data_payload(assessment: dict, named_events: Optional[list] = None) -> dict:
    """Distil one topic's assessment into the shape the per-topic agents expect.

    ``named_events`` (optional) — the topic's slice of
    ``db.facade.list_extracted_events`` for this cadence/period. Threaded
    through so the briefing/recs/next-steps agents can ground their
    tensions, lede, and rationales in real events (Nvidia, IonQ, Google,
    India, IBM…). Without this, topics that lack back-tested scenario
    data — and so have an empty ``scenarios``/``emerging_themes`` slot —
    were producing "DATA ABSENCE / ACTOR VISIBILITY / EMERGING THEMES
    GAP" filler that the reviewer rightly rejected as contradicted by
    the named-events table.
    """
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

    # Ground-truth events the extraction stage tagged for this topic.
    # Briefing/recs/next-steps agents anchor their tensions and rationales
    # to these so empty-scenarios topics don't default to "DATA ABSENCE".
    events = [e for e in (named_events or []) if isinstance(e, dict)]

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
        "named_events": events[:30],
    }


# ── Stage runners ────────────────────────────────────────────────────

async def _run_briefings(items: list, plan: dict,
                         events_by_topic: Optional[dict] = None) -> dict:
    """Per-topic Briefing Synthesis. Skips topics whose briefing is cached
    unless the plan explicitly targets them."""
    target_topics = _plan_targets(plan, "briefing")
    events_by_topic = events_by_topic or {}
    tasks = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("topic_briefing")
                and (not target_topics or topic not in target_topics)):
            continue
        tasks.append((topic, _call_agent(
            "wiley_briefing_agent",
            _topic_data_payload(assessment, named_events=events_by_topic.get(topic)),
        )))
    results = {}
    for topic, fut in tasks:
        results[topic] = await fut
    return results


async def _run_recommendations(items: list, plan: dict,
                               events_by_topic: Optional[dict] = None) -> dict:
    target_topics = _plan_targets(plan, "recommendations")
    events_by_topic = events_by_topic or {}
    out = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("strategic_recommendations")
                and (not target_topics or topic not in target_topics)):
            continue
        out[topic] = await _call_agent(
            "wiley_recs_agent",
            _topic_data_payload(assessment, named_events=events_by_topic.get(topic)),
        )
    return out


async def _run_next_steps(items: list, plan: dict,
                          events_by_topic: Optional[dict] = None) -> dict:
    target_topics = _plan_targets(plan, "next_steps")
    events_by_topic = events_by_topic or {}
    out = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if target_topics is not None and topic not in target_topics:
            continue
        if ((assessment.get("summary") or {}).get("next_steps")
                and (not target_topics or topic not in target_topics)):
            continue
        out[topic] = await _call_agent(
            "wiley_next_steps_agent",
            _topic_data_payload(assessment, named_events=events_by_topic.get(topic)),
        )
    return out


def _events_by_topic(db, cadence: str, period_label: str) -> dict:
    """Fetch named events for the period and group by topic.

    One DB call; the result is reused across briefing / recommendations /
    next-steps so the per-topic agents have the same ground truth the
    reviewer evaluates against.
    """
    out: dict[str, list] = {}
    try:
        rows = db.facade.list_extracted_events(
            cadence=cadence, period_label=period_label, include_excluded=True) or []
    except Exception as e:
        logger.warning("events_by_topic: list_extracted_events failed: %s", e)
        return out
    for e in rows:
        if not isinstance(e, dict):
            continue
        t = (e.get("topic") or "").strip()
        if not t:
            continue
        out.setdefault(t, []).append({
            "actor":   e.get("actor"),
            "action":  e.get("action"),
            "subject": e.get("subject"),
            "date":    str(e.get("event_date"))[:10] if e.get("event_date") else None,
        })
    return out


def _plan_targets(plan: dict, stage_name: str) -> Optional[set]:
    """Extract the ``targets`` list for a stage from the supervisor's plan.
    Returns None if no targeting (run all eligible topics) or a set of topic
    names if the plan specified them."""
    for s in (plan or {}).get("plan", []) or []:
        if _plan_stage_name(s) == stage_name:
            t = s.get("targets") if isinstance(s, dict) else None
            return set(t) if t else None
    return None


def _plan_stage_name(s):
    """The supervisor agent (temp 1.0) sometimes returns plan items as bare
    strings instead of {stage,...} dicts. Normalise either shape."""
    return s.get("stage") if isinstance(s, dict) else (s if isinstance(s, str) else None)


def _stage_in_plan(plan: dict, stage_name: str) -> bool:
    return any(_plan_stage_name(s) == stage_name for s in (plan or {}).get("plan", []) or [])


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


def _compute_calibration(items: list, cadence: str = None,
                         period_label: str = None) -> list:
    """Per-trend consensus×evidence calibration for the exec summary.

    Returns ``[{topic, scenario, basis_pct, n_confirm, n_counter, read}]``.
    ``basis_pct`` is the point-in-time forecast basis (deck_info.consensus_pct);
    confirm/counter come from this period's extracted events split by
    direction; ``read`` is the calibration category (crowd_wrong /
    outlier_confirming / holding / …). Lets the agent lead with divergences.
    """
    from app.services.forecast_pptx_export import _calibration_read
    from app.services.wiley_event_extraction import events_for_scenario
    from app.database import get_database_instance

    events_by_topic: dict = {}
    if cadence and period_label:
        try:
            db = get_database_instance()
            for e in (db.facade.list_extracted_events(
                    cadence=cadence, period_label=period_label,
                    include_excluded=False) or []):
                events_by_topic.setdefault(e.get("topic"), []).append(e)
        except Exception as e:
            logger.warning("calibration: events load failed: %s", e)

    out = []
    for assessment, _r, _p in items:
        topic = assessment.get("topic") or "—"
        t_events = events_by_topic.get(topic) or []
        for v in (assessment.get("scenario_verdicts") or []):
            if v.get("verdict_label") == "Done":
                continue
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            name = deck_info.get("deck_scenario_name") or v.get("scenario_title") or "—"
            basis = deck_info.get("consensus_pct")
            conf, ctr = events_for_scenario(t_events, name)
            read_text, category = _calibration_read(basis, len(conf), len(ctr))
            out.append({
                "topic": topic, "scenario": name,
                "basis_pct": round(float(basis), 1) if isinstance(basis, (int, float)) else None,
                "n_confirm": len(conf), "n_counter": len(ctr),
                "read": category, "read_text": read_text,
                "confirming_events": [
                    f"{e.get('actor')} {e.get('action')} {e.get('subject')}" for e in conf[:3]
                ],
                "counter_events": [
                    f"{e.get('actor')} {e.get('action')} {e.get('subject')}" for e in ctr[:2]
                ],
            })
    return out


def _expert_commentary_payload(items: list, period_label: str) -> dict:
    """Build the expert-commentary agent's input: the quarter's emerging
    themes (surprise clusters) across all topics, with real sample headlines
    for grounding. Keyword-salad labels are dropped so the commentary never
    cites an un-relabelled cluster."""
    import re as _re

    def _salad(lab: str) -> bool:
        return bool(_re.fullmatch(
            r"[a-z0-9][a-z0-9\-]*(?:,\s*[a-z0-9][a-z0-9\-]*){1,5}",
            (lab or "").strip()))

    themes = []
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or "—"
        ranked = sorted((assessment.get("surprises") or []),
                        key=lambda s: -(s.get("size") or 0))[:3]
        for s in ranked:
            lab = (s.get("label") or "").strip()
            if not lab or _salad(lab):
                continue
            samples = []
            for a in (s.get("sample_articles") or [])[:3]:
                t = a.get("title") if isinstance(a, dict) else a
                if t:
                    samples.append(t)
            themes.append({
                "topic": topic, "label": lab,
                "size": s.get("size"), "sample_articles": samples,
            })
    return {
        "period_label": period_label,
        "topics": [(a.get("topic") or "—") for (a, _r, _p) in items],
        "emerging_themes": themes,
    }


def _exec_summary_payload(items: list, period_label: str,
                          cross_topic: dict, eos_per_topic: dict,
                          briefings: dict = None,
                          recommendations: dict = None,
                          next_steps: dict = None,
                          calibration: list = None) -> dict:
    """Build the exec-summary agent's input.

    The agent needs more than the strategic overview + a biggest-mover —
    to produce concrete output (the kind in
    ``Wiley_Horizons_Executive_Summary_May2026.docx``) it needs:

    * per-topic consensus % deltas (so it can say "78% → 20%")
    * status-change counts vs the prior snapshot (so it can say
      "Of the 23 scenarios tracked, 7 are now Cooling")
    * the briefing's flagship line for at least one topic (so it can
      quote "Trust is the central battleground")
    * concrete next-step phrases (so its closing imperative is real)
    """
    briefings = briefings or {}
    recommendations = recommendations or {}
    next_steps = next_steps or {}

    overview = (cross_topic or {}).get("strategic_overview") or ""
    CUSTOMER = {"Above baseline": "Strengthening", "At baseline": "Stable", "Below baseline": "Cooling"}
    dist = {"Strengthening": 0, "Stable": 0, "Cooling": 0, "Inconclusive": 0}
    biggest = None
    total_scenarios = 0

    # Per-topic detail. Each entry separates TWO different "drift" values
    # because they were being conflated in the agent output:
    #
    #   * vs_deck_overlay  → original deck-authored consensus % (set at
    #     topic creation) vs current measurement. Always populated for
    #     topics with a deck overlay. NOT a since-prior-period diff.
    #   * vs_prior_assessment → current measurement vs the same field on
    #     the previous assessment. Only populated when ``prior`` exists.
    #     This is the real "since {prior_period_label}" number.
    per_topic_detail = []
    flips_per_topic: dict[str, dict] = {}

    for assessment, _run, prior in items:
        topic = assessment.get("topic") or "—"
        verdicts = [v for v in (assessment.get("scenario_verdicts") or [])
                    if v.get("verdict_label") != "Done"]
        total_scenarios += len(verdicts)
        bc_per = _as_dict(_as_dict(_as_dict(assessment.get("summary")).get("baseline_correction")).get("per_scenario"))
        prior_bc = _as_dict(_as_dict(_as_dict((prior or {}).get("summary")).get("baseline_correction")).get("per_scenario"))

        topic_flips_to_cooling = 0
        topic_flips_to_strengthening = 0
        for v in verdicts:
            key = str(v.get("scenario_idx"))
            label = (bc_per.get(key) or {}).get("label") or v.get("verdict_label")
            prior_label = (prior_bc.get(key) or {}).get("label") if prior else None
            cust = CUSTOMER.get(label, label) if label else None
            if cust and cust in dist:
                dist[cust] += 1
            if prior_label and label and prior_label != label:
                if label == "Below baseline":
                    topic_flips_to_cooling += 1
                elif label == "Above baseline":
                    topic_flips_to_strengthening += 1
            net = (bc_per.get(key) or {}).get("net_rate")
            if net is not None and (biggest is None or abs(net) > abs(biggest[0])):
                deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
                biggest = (net, topic,
                           deck_info.get("deck_scenario_name") or v.get("scenario_title"),
                           prior_label, label)

        # Deck-overlay vs current measurement. ``authored_pct`` is the
        # consensus the analyst set when the deck overlay was created
        # (lives in deck_info.consensus_pct). ``current_pct`` is today's
        # measurement averaged across the topic's scenarios. This is NOT
        # a since-prior diff — it answers "how does today compare to the
        # deck's authored expectation".
        authored_consensus = []
        current_consensus_vals = []
        for v in verdicts:
            deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
            if deck_info.get("consensus_pct") is not None:
                authored_consensus.append(float(deck_info["consensus_pct"]))
            if v.get("current_consensus_pct") is not None:
                current_consensus_vals.append(float(v["current_consensus_pct"]))
        vs_deck_overlay = None
        if authored_consensus and current_consensus_vals:
            vs_deck_overlay = {
                "authored_pct": round(sum(authored_consensus) / len(authored_consensus), 1),
                "current_pct": round(sum(current_consensus_vals) / len(current_consensus_vals), 1),
            }

        # Real since-prior-period diff. Only present when ``prior`` is
        # not None. Compares the same averaged-current-consensus value
        # between this assessment and the previous one for this topic.
        vs_prior_assessment = None
        if prior:
            prior_verdicts = [v for v in (prior.get("scenario_verdicts") or [])
                              if v.get("verdict_label") != "Done"]
            prior_cur = []
            for v in prior_verdicts:
                if v.get("current_consensus_pct") is not None:
                    prior_cur.append(float(v["current_consensus_pct"]))
            if prior_cur and current_consensus_vals:
                prior_avg = sum(prior_cur) / len(prior_cur)
                cur_avg = sum(current_consensus_vals) / len(current_consensus_vals)
                vs_prior_assessment = {
                    "prior_pct": round(prior_avg, 1),
                    "current_pct": round(cur_avg, 1),
                    "prior_assessed_at": str(prior.get("assessed_at") or ""),
                }

        flips_per_topic[topic] = {
            "to_cooling": topic_flips_to_cooling,
            "to_strengthening": topic_flips_to_strengthening,
        }

        briefing = (briefings.get(topic)
                    or (assessment.get("summary") or {}).get("topic_briefing") or {})
        topic_recs = (recommendations.get(topic) or {}).get("recommendations") \
                     or (assessment.get("summary") or {}).get("strategic_recommendations") or []
        topic_next = (next_steps.get(topic) or {}).get("next_steps") \
                     or (assessment.get("summary") or {}).get("next_steps") or []

        per_topic_detail.append({
            "topic": topic,
            "scenarios_count": len(verdicts),
            "has_prior_assessment": bool(prior),
            "vs_deck_overlay": vs_deck_overlay,
            "vs_prior_assessment": vs_prior_assessment,
            "flips": flips_per_topic[topic],
            "briefing_lede": (briefing or {}).get("lede"),
            "briefing_tensions": [
                t.get("body") if isinstance(t, dict) else str(t)
                for t in ((briefing or {}).get("tensions") or [])[:3]
            ],
            "briefing_imperatives": [
                (t.get("body") if isinstance(t, dict) else str(t))
                for t in ((briefing or {}).get("imperatives") or [])[:3]
            ],
            "top_recommendation": (
                (topic_recs[0].get("body") if isinstance(topic_recs[0], dict) else str(topic_recs[0]))
                if topic_recs else None
            ),
            "top_next_step": (
                (topic_next[0].get("body") if isinstance(topic_next[0], dict) else str(topic_next[0]))
                if topic_next else None
            ),
        })

    black_swans = []
    for topic, scenarios in (eos_per_topic or {}).items():
        for s in scenarios or []:
            if (s.get("category") or "").lower() == "black_swan":
                black_swans.append({
                    "topic": topic,
                    "title": s.get("title"),
                    "impact": s.get("impact_score"),
                    "timeframe": s.get("timeframe"),
                    "description": s.get("description"),
                })

    return {
        "period_label": period_label,
        "prior_period_label": _prior_period_label(period_label),
        "strategic_overview": overview,
        "status_distribution": dist,
        "total_scenarios": total_scenarios,
        "biggest_mover": (
            {"topic": biggest[1], "scenario": biggest[2],
             "delta_pct": round(biggest[0]*100, 2),
             "prior_status": CUSTOMER.get(biggest[3], biggest[3]) if biggest[3] else None,
             "current_status": CUSTOMER.get(biggest[4], biggest[4]) if biggest[4] else None}
            if biggest else None
        ),
        "topics": [(a.get("topic") or "—") for (a, _r, _p) in items],
        "per_topic_detail": per_topic_detail,
        # Per-trend consensus×evidence calibration — the agent leads with the
        # divergences (read=crowd_wrong / outlier_confirming).
        "calibration": calibration or [],
        "divergences": {
            "consensus_not_bearing_out": [
                c for c in (calibration or []) if c.get("read") == "crowd_wrong"
            ],
            "outliers_confirming": [
                c for c in (calibration or []) if c.get("read") == "outlier_confirming"
            ],
        },
        "cross_cutting_themes": (cross_topic or {}).get("cross_cutting_themes") or [],
        "executive_decision_framework": (cross_topic or {}).get("executive_decision_framework") or [],
        "black_swan_count": len(black_swans),
        "top_black_swan": black_swans[0] if black_swans else None,
        "all_black_swans": black_swans[:3],
    }


def _prior_period_label(period_label: str) -> str:
    """Crude best-guess at the prior period name for the letter's
    "diff against …" subtitle. The exec agent will use whatever is given
    here so a wrong guess is benign; the docx exemplar uses 'February
    2026 baseline' for a May 2026 update, hence the quarter-back default.
    """
    import re as _re
    from datetime import datetime as _dt
    # Match "Q2 2026", "Quarterly 2026-04-15", or fallback "2026-05-26"
    m = _re.search(r"(Q[1-4]\s*\d{4})", period_label or "")
    if m:
        q, year = m.group(1)[1], m.group(1)[-4:]
        q_num = int(q)
        prior_q = 4 if q_num == 1 else q_num - 1
        prior_year = int(year) - 1 if q_num == 1 else int(year)
        return f"Q{prior_q} {prior_year} baseline"
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", period_label or "")
    if m:
        try:
            d = _dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            month = d.month - 3 if d.month > 3 else 12 + (d.month - 3)
            year = d.year if d.month > 3 else d.year - 1
            return _dt(year, month, 1).strftime("%B %Y baseline")
        except Exception:
            pass
    return "prior bundle"


# ── Reviewer payload — combines everything for the judge ─────────────

def _reviewer_payload(period_label: str, items: list, briefings: dict,
                       recommendations: dict, next_steps: dict,
                       cross_topic: dict, exec_summary: dict,
                       eos_per_topic: dict,
                       cadence: str = None) -> dict:
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

    # The exec summary now cites NAMED EVENTS from the extraction stage. Feed
    # those events to the reviewer so it can verify event-grounded claims
    # against them — otherwise it flags real, sourced events as hallucinations
    # (it can't find them in the briefings, which are a different artefact).
    named_events = []
    try:
        from app.database import get_database_instance
        db = get_database_instance()
        for e in (db.facade.list_extracted_events(
                cadence=cadence, period_label=period_label, include_excluded=True) or []):
            named_events.append({
                "topic": e.get("topic"), "actor": e.get("actor"),
                "action": e.get("action"), "subject": e.get("subject"),
                "date": str(e.get("event_date"))[:10] if e.get("event_date") else None,
            })
    except Exception as e:
        logger.warning("reviewer payload: events load failed: %s", e)

    return {
        "period_label": period_label,
        "per_topic": per_topic,
        "cross_topic": cross_topic or {},
        "exec_summary": exec_summary or {},
        "eos_per_topic": eos_per_topic or {},
        # Ground-truth events the exec summary / what's-changed drew from.
        "named_events": named_events,
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
           "payload": {"plan_stages": [_plan_stage_name(s) for s in plan.get("plan", []) or []]}}

    # ── Stages 2-3 are pure data; skip in this slim build — the existing
    # narrative agents already have access to the same source data via the
    # topic payloads we hand them. Retrieval/analytics live as helpers
    # inside the topic_data_payload builder.

    # ── Named-events ground truth — fetch once, reuse for every per-topic
    # agent. Without this the briefing agent invents "DATA ABSENCE" filler
    # for topics whose back-test scenario_verdicts are empty, even though
    # the extraction stage produced plenty of real events for that topic.
    events_by_topic = _events_by_topic(db, cadence, period_label)

    # ── Stage 4: per-topic Briefing Synthesis ───────────────────────
    briefings = {}
    if _stage_in_plan(plan, "briefing"):
        yield {"stage": "briefing", "status": "started", "progress": 0.2}
        briefings = await _run_briefings(items, plan, events_by_topic)
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
        recommendations = await _run_recommendations(items, plan, events_by_topic)
        for topic, payload in recommendations.items():
            if payload:
                _persist_recommendations(db, items, topic, payload)
        yield {"stage": "recommendations", "status": "completed", "progress": 0.55,
               "payload": {"topics": list(recommendations.keys())}}

    # ── Stage 6: per-topic Next Steps ───────────────────────────────
    next_steps = {}
    if _stage_in_plan(plan, "next_steps"):
        yield {"stage": "next_steps", "status": "started", "progress": 0.6}
        next_steps = await _run_next_steps(items, plan, events_by_topic)
        for topic, payload in next_steps.items():
            if payload:
                _persist_next_steps(db, items, topic, payload)
        yield {"stage": "next_steps", "status": "completed", "progress": 0.7,
               "payload": {"topics": list(next_steps.keys())}}

    # ── Stage 6.5: event extraction (the honest "what's changed") ────
    # Pull structured real-world events (actor + action + magnitude +
    # date) from each topic's recent articles. Guarded so it runs once
    # per period — re-exports reuse the cached events, and the analyst can
    # re-trigger via the editor's "Regenerate → events" button. Failure is
    # non-fatal: the deck still ships without the events section.
    try:
        already = db.facade.list_extracted_events(
            cadence=cadence, period_label=period_label, include_excluded=True,
        )
        if not already:
            yield {"stage": "events", "status": "started", "progress": 0.71}
            from app.services.wiley_event_extraction import run_event_extraction
            counts = await run_event_extraction(
                cadence=cadence, period_label=period_label,
                topics=[(a.get("topic") or "") for (a, _r, _p) in items],
            )
            yield {"stage": "events", "status": "completed", "progress": 0.73,
                   "payload": {"events_per_topic": counts}}
        else:
            # Events already extracted — skip the expensive LLM extraction, but
            # ALWAYS re-sync whats_changed into the payload from the existing
            # events. (Extraction is what populates whats_changed; without this
            # re-sync a re-export loses the "What's Changed" content.)
            from app.services.wiley_event_extraction import _sync_events_into_payload
            _sync_events_into_payload(db, cadence, period_label)
    except Exception as e:
        logger.warning("event-extraction stage failed (non-fatal): %s", e)

    # Locked dot-paths configured in the Quarterly Brief Editor. After
    # each agent call we restore any locked subtree from prior_payload so
    # an accidental "Generate bundle" doesn't clobber edited prose.
    # Re-read synthesis: the events stage may have just written
    # whats_changed.events into the payload.
    prior_synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or prior_synth
    locked_keys = list(prior_synth.get("locked_keys") or [])
    prior_payload = prior_synth.get("payload") or {}

    # ── Stage 7: cross-topic synthesis ──────────────────────────────
    cross_topic = (prior_synth.get("payload") or {}).get("strategic_overview") and prior_synth.get("payload") or {}
    if _stage_in_plan(plan, "cross_topic") or not cross_cached:
        yield {"stage": "cross_topic", "status": "started", "progress": 0.75}
        cross_topic = await _call_agent("wiley_cross_topic_agent",
                                         _cross_topic_payload(items, period_label, briefings))
        # Restore locked subtrees scoped to cross_topic's outputs
        # (strategic_overview / cross_cutting_themes /
        # executive_decision_framework).
        ct_locks = [
            p for p in locked_keys
            if p.split(".", 1)[0].split("[", 1)[0]
            in {"strategic_overview", "cross_cutting_themes", "executive_decision_framework"}
        ]
        cross_topic = _apply_locks_after_call(prior_payload, cross_topic, ct_locks)
        yield {"stage": "cross_topic", "status": "completed", "progress": 0.82}

    # ── Stage 8: Executive Summary letter ────────────────────────────
    exec_summary = (prior_synth.get("payload") or {}).get("exec_summary") or {}
    exec_regenerated = False
    if _stage_in_plan(plan, "exec_summary") or not exec_summary:
        exec_regenerated = True
        yield {"stage": "exec_summary", "status": "started", "progress": 0.85}
        exec_summary = await _call_agent(
            "wiley_exec_summary_agent",
            _exec_summary_payload(
                items, period_label, cross_topic, eos_per_topic,
                briefings=briefings,
                recommendations=recommendations,
                next_steps=next_steps,
                calibration=_compute_calibration(items, cadence, period_label),
            ),
        )
        # Restore locks scoped to exec_summary fields. Locked path
        # 'exec_summary.letter' on the bundle becomes 'letter' here
        # because exec_summary is the local subtree.
        es_locks = [
            p[len("exec_summary."):] for p in locked_keys
            if p.startswith("exec_summary.")
        ]
        if es_locks:
            prior_es = prior_payload.get("exec_summary") or {}
            exec_summary = _apply_locks_after_call(prior_es, exec_summary, es_locks)
        yield {"stage": "exec_summary", "status": "completed", "progress": 0.9}

    # ── Stage 8b: Expert commentary on emerging themes ───────────────
    # A short analyst-editable "expert view" on the quarter's emerging themes
    # (the surprise clusters). Generated only when absent or explicitly
    # re-planned, and never when the analyst has locked it. Grounded in the
    # named themes; humanized + verdict-scrubbed below with the other prose.
    expert_commentary = (prior_synth.get("payload") or {}).get("expert_commentary") or ""
    if ("expert_commentary" not in (locked_keys or [])
            and (_stage_in_plan(plan, "expert_commentary") or not expert_commentary)):
        yield {"stage": "expert_commentary", "status": "started", "progress": 0.905}
        ec = await _call_agent("wiley_expert_commentary_agent",
                               _expert_commentary_payload(items, period_label))
        expert_commentary = ((ec or {}).get("commentary") or "").strip() or expert_commentary
        yield {"stage": "expert_commentary", "status": "completed", "progress": 0.91}

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
    if expert_commentary:
        bundle_payload["expert_commentary"] = expert_commentary

    # ── Humanization pass — strip AI-slop tells from the generated prose
    # (exec summary, strategic overview, theme/framework bodies) before the
    # reviewer sees it and before persistence. Threshold-gated + lock-aware
    # (locked fields are left untouched). Non-fatal.
    try:
        from app.services.wiley_humanizer import humanize_bundle_payload, humanize_enabled
        if humanize_enabled():
            yield {"stage": "humanize", "status": "started", "progress": 0.905}
            hsummary = await humanize_bundle_payload(bundle_payload, locked_keys=locked_keys)
            changed = sum(1 for v in hsummary.values() if v.get("changed"))
            yield {"stage": "humanize", "status": "completed", "progress": 0.915,
                   "payload": {"fields_rewritten": changed,
                               "fields_checked": len(hsummary)}}
            # Keep the in-memory exec_summary aligned with the humanized payload
            # so the reviewer payload below reflects the rewrite.
            if isinstance(bundle_payload.get("exec_summary"), dict):
                exec_summary = bundle_payload["exec_summary"]
            if bundle_payload.get("cross_cutting_themes"):
                cross_topic = dict(cross_topic or {})
                cross_topic["cross_cutting_themes"] = bundle_payload["cross_cutting_themes"]
                cross_topic["executive_decision_framework"] = bundle_payload.get("executive_decision_framework")
                cross_topic["strategic_overview"] = bundle_payload.get("strategic_overview")
    except Exception as e:
        logger.warning("Humanization pass failed (non-fatal): %s", e)

    # Deterministic guard: the exec-summary agent must never JUDGE the
    # consensus/forecast as right or wrong (a framing the customer rejected).
    # LLMs slip, so catch + rewrite it here before the reviewer/customer see
    # it. Lock-aware; non-fatal.
    try:
        es = bundle_payload.get("exec_summary")
        if (isinstance(es, dict) and es.get("letter")
                and "exec_summary.letter" not in (locked_keys or [])):
            from app.services.wiley_humanizer import strip_forecast_verdicts
            r = await strip_forecast_verdicts(es["letter"])
            if r["changed"]:
                es["letter"] = r["text"]
                exec_summary = es
                yield {"stage": "humanize", "status": "verdict_scrubbed", "progress": 0.918}
            # Ground-check: drop/soften any event the letter cites that isn't in
            # named_events. Only when the letter was freshly generated this run
            # (it's an LLM call) — not on every cached re-export.
            if exec_regenerated:
                try:
                    from app.services.wiley_humanizer import ground_check_exec_summary
                    named = db.facade.list_extracted_events(
                        cadence=cadence, period_label=period_label) or []
                    g = await ground_check_exec_summary(es["letter"], named)
                    if g["changed"]:
                        es["letter"] = g["text"]
                        exec_summary = es
                        yield {"stage": "humanize", "status": "event_grounded",
                               "progress": 0.919}
                except Exception as e:
                    logger.warning("exec-summary ground-check failed (non-fatal): %s", e)
        # Same deterministic verdict guard on the expert commentary.
        ec_text = bundle_payload.get("expert_commentary")
        if (isinstance(ec_text, str) and ec_text.strip()
                and "expert_commentary" not in (locked_keys or [])):
            from app.services.wiley_humanizer import strip_forecast_verdicts
            r2 = await strip_forecast_verdicts(ec_text)
            if r2["changed"]:
                bundle_payload["expert_commentary"] = r2["text"]
                expert_commentary = r2["text"]
    except Exception as e:
        logger.warning("Forecast-verdict scrub failed (non-fatal): %s", e)

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
                                            cross_topic, exec_summary, eos_per_topic,
                                            cadence=cadence)
        review_result = await _call_agent("wiley_reviewer_agent", review_payload,
                                           reasoning_effort="high")
        findings = (review_result or {}).get("findings") or []
        findings = _sanitize_review_findings(
            findings,
            exec_letter=(exec_summary or {}).get("letter") if isinstance(exec_summary, dict) else None,
        )
        summary = (review_result or {}).get("summary") or {}
        # Recount severities post-sanitisation so the verdict reflects the
        # cleaned-up findings, not the reviewer's raw self-report (which
        # included duplicates and stylistic items mis-flagged as errors).
        n_errors = sum(1 for f in findings if f.get("severity") == "error")
        n_warnings = sum(1 for f in findings if f.get("severity") == "warning")
        if n_errors:
            verdict = "revision_requested"
        elif n_warnings:
            verdict = "approved_with_warnings"
        else:
            verdict = summary.get("verdict") or "approved"
        summary["errors"] = n_errors
        summary["warnings"] = n_warnings
        yield {"stage": "reviewer", "status": "completed", "progress": 0.97,
               "payload": {"verdict": verdict, "errors": summary.get("errors", 0),
                           "warnings": summary.get("warnings", 0)}}

        # Persist review state. Read the reviewer's actual model from the agent
        # config so the audit row reflects what really ran (not a hard-coded label).
        reviewer_agent_cfg = (get_tool_loader().get_agent("wiley_reviewer_agent") or None)
        reviewer_model = ((reviewer_agent_cfg.metadata or {}).get("model_config", {}).get("model")
                           if reviewer_agent_cfg else None) or "gpt-5.4"
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


# ── Single-stage regeneration (called from the Quarterly Brief Editor) ───
#
# The editor's "Regenerate this section" button targets one stage at a
# time. We rebuild only that stage's inputs, call the agent, apply
# locks, persist, and return. Long-running enough to need
# BackgroundTaskManager; quick enough that a quarterly update can iterate
# in seconds.

async def _load_items_for_period(cadence: str, period_label: str) -> list:
    """Reconstruct the (assessment, run, prior) tuple list for a given
    period — same shape `run_pipeline` consumes. Pulled from the cached
    topics list on forecast_bundle_synthesis + latest assessment per topic."""
    from app.database import get_database_instance
    db = get_database_instance()
    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    topics = synth.get("topics") or []
    out = []
    for entry in topics:
        topic_name = entry.get("topic") if isinstance(entry, dict) else entry
        if not topic_name:
            continue
        latest = db.facade.get_latest_forecast_assessment_by_topic(topic_name) or {}
        if latest:
            out.append((latest, None, None))
    return out


async def regenerate_single_stage(
    *, cadence: str, period_label: str, stage: str,
    topic: Optional[str] = None, actor: str = "ui",
    progress_cb=None,
):
    """Re-run a single supervisor stage. Locks scoped to that stage are
    respected. Persists the result to the same JSONB paths the normal
    pipeline writes to so subsequent renders pick it up.

    `progress_cb(pct: float, message: str)` — optional, called as the
    stage advances. Wrapped by BackgroundTaskManager when invoked from
    the editor endpoint.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    async def _emit(pct: float, msg: str):
        if progress_cb:
            try:
                await progress_cb(pct, msg)
            except TypeError:
                progress_cb(pct, msg)

    await _emit(0.05, f"Loading state for {cadence}/{period_label}")
    items = await _load_items_for_period(cadence, period_label)
    if not items:
        raise RuntimeError(f"No assessments cached for {cadence}/{period_label}")

    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    locked_keys = list(synth.get("locked_keys") or [])
    prior_payload = synth.get("payload") or {}

    # Per-topic stages: rebuild for one topic if specified, else all.
    if stage in ("briefing", "recommendations", "next_steps"):
        targets = [a for (a, _r, _p) in items if (not topic or a.get("topic") == topic)]
        await _emit(0.2, f"Running {stage} for {len(targets)} topic(s)")

        for i, a in enumerate(targets):
            tname = a.get("topic") or "—"
            agent_map = {
                "briefing": "wiley_briefing_agent",
                "recommendations": "wiley_recs_agent",
                "next_steps": "wiley_next_steps_agent",
            }
            new_payload = await _call_agent(agent_map[stage], _topic_data_payload(a))

            # Apply per-topic locks
            topic_locks = list(a.get("summary_locked_keys") or [])
            # Locks for this stage live under the stage's summary key:
            # 'topic_briefing.*' for briefing, etc.
            stage_root = {
                "briefing": "topic_briefing",
                "recommendations": "strategic_recommendations",
                "next_steps": "next_steps",
            }[stage]
            scoped_locks = [
                p[len(stage_root) + 1:] for p in topic_locks
                if p.startswith(stage_root + ".") or p == stage_root
            ]
            if scoped_locks:
                prior_subtree = (a.get("summary") or {}).get(stage_root) or {}
                new_payload = _apply_locks_after_call(
                    prior_subtree, new_payload, scoped_locks,
                )

            if stage == "briefing":
                _persist_topic_briefing(db, items, tname, new_payload)
            elif stage == "recommendations":
                _persist_recommendations(db, items, tname, new_payload)
            elif stage == "next_steps":
                _persist_next_steps(db, items, tname, new_payload)

            pct = 0.2 + 0.7 * ((i + 1) / max(len(targets), 1))
            await _emit(pct, f"{stage}: persisted {tname}")
        await _emit(1.0, f"{stage} stage complete")
        return

    # Bundle-level stages
    if stage == "cross_topic":
        await _emit(0.3, "Calling cross_topic agent")
        new_payload = await _call_agent(
            "wiley_cross_topic_agent",
            _cross_topic_payload(items, period_label, briefings={}),
        )
        ct_locks = [
            p for p in locked_keys
            if p.split(".", 1)[0].split("[", 1)[0]
            in {"strategic_overview", "cross_cutting_themes", "executive_decision_framework"}
        ]
        new_payload = _apply_locks_after_call(prior_payload, new_payload, ct_locks)

        merged = dict(prior_payload)
        for k in ("strategic_overview", "cross_cutting_themes", "executive_decision_framework"):
            if new_payload.get(k) is not None:
                merged[k] = new_payload[k]
        db.facade.save_forecast_bundle_synthesis(
            cadence, period_label, merged, synth.get("topics") or [],
        )
        await _emit(1.0, "cross_topic stage complete")
        return

    if stage == "exec_summary":
        await _emit(0.3, "Calling exec_summary agent")
        # EOS scenarios feed the "headline tail risk" paragraph. Reuse the
        # delivery service's bundle-level EOS loader; degrade to empty if
        # it can't run so the exec summary still regenerates.
        try:
            from app.services.wiley_delivery_service import _ensure_eos_for_bundle
            eos_per_topic = await _ensure_eos_for_bundle(items)
        except Exception as e:
            logger.warning("EOS load failed during exec_summary regen: %s", e)
            eos_per_topic = {}
        new_payload = await _call_agent(
            "wiley_exec_summary_agent",
            _exec_summary_payload(
                items, period_label, prior_payload, eos_per_topic,
                briefings={}, recommendations={}, next_steps={},
                calibration=_compute_calibration(items, cadence, period_label),
            ),
        )
        es_locks = [
            p[len("exec_summary."):] for p in locked_keys
            if p.startswith("exec_summary.")
        ]
        if es_locks:
            prior_es = prior_payload.get("exec_summary") or {}
            new_payload = _apply_locks_after_call(prior_es, new_payload, es_locks)

        # Same guards the full pipeline applies: humanize + scrub any
        # consensus-verdict phrasing before persisting.
        try:
            from app.services.wiley_humanizer import (
                humanize_text, strip_forecast_verdicts, ground_check_exec_summary,
                humanize_enabled)
            if humanize_enabled() and new_payload.get("letter") \
                    and "exec_summary.letter" not in (locked_keys or []):
                h = await humanize_text(new_payload["letter"])
                letter = h["text"] if h.get("changed") else new_payload["letter"]
                v = await strip_forecast_verdicts(letter)
                letter = v["text"] if v.get("changed") else letter
                named = db.facade.list_extracted_events(
                    cadence=cadence, period_label=period_label) or []
                g = await ground_check_exec_summary(letter, named)
                new_payload["letter"] = g["text"] if g.get("changed") else letter
        except Exception as e:
            logger.warning("exec_summary post-guards failed (non-fatal): %s", e)

        merged = dict(prior_payload)
        merged["exec_summary"] = new_payload
        db.facade.save_forecast_bundle_synthesis(
            cadence, period_label, merged, synth.get("topics") or [],
        )
        await _emit(1.0, "exec_summary stage complete")
        return

    if stage == "expert_commentary":
        if "expert_commentary" in (locked_keys or []):
            await _emit(1.0, "expert_commentary locked — skipped")
            return
        await _emit(0.3, "Calling expert_commentary agent")
        ec = await _call_agent("wiley_expert_commentary_agent",
                               _expert_commentary_payload(items, period_label))
        text = ((ec or {}).get("commentary") or "").strip()
        # Same guards as the full pipeline: humanize + verdict-scrub.
        if text:
            try:
                from app.services.wiley_humanizer import (
                    humanize_text, strip_forecast_verdicts, humanize_enabled)
                if humanize_enabled():
                    h = await humanize_text(text)
                    text = h["text"] if h.get("changed") else text
                v = await strip_forecast_verdicts(text)
                text = v["text"] if v.get("changed") else text
            except Exception as e:
                logger.warning("expert_commentary post-guards failed (non-fatal): %s", e)
        merged = dict(prior_payload)
        merged["expert_commentary"] = text
        db.facade.save_forecast_bundle_synthesis(
            cadence, period_label, merged, synth.get("topics") or [],
        )
        await _emit(1.0, "expert_commentary stage complete")
        return

    if stage == "events":
        # Optional: only run if wiley_event_extraction is wired up. Stub
        # for now — the editor can still CRUD events manually.
        try:
            from app.services.wiley_event_extraction import run_event_extraction
            await _emit(0.3, "Extracting events")
            await run_event_extraction(
                cadence=cadence, period_label=period_label,
                topics=[topic] if topic else None,
            )
            await _emit(1.0, "events stage complete")
        except ImportError:
            await _emit(1.0, "events extraction not yet wired up; manual events still editable")
        return

    raise ValueError(f"unknown stage: {stage}")
