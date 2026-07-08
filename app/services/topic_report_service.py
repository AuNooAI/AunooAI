"""On-demand Topic Report service.

Builds a long-form Wiley-style topic report PPTX (modeled on the
"Wiley Horizons Final" 135-slide deck) for an arbitrary, user-selected
list of topics. Sister service to :mod:`wiley_delivery_service`, which
ships the cadence-locked quarterly/monthly bundle.

Differences from ``generate_bundle``:

* No cadence / no delivery-config dependency — the topic set is supplied
  by the caller.
* Prepends an 8-slide static intro pack (team profiles, methodology,
  "What We Monitor") from ``app/static_assets/topic_report_intro.pptx``.
* Uses a stable, content-derived cache key so re-running with the same
  topic set + period returns the cached PPTX instantly.

Reuses the WileyBundleSupervisor pipeline (so all synthesis is shared
with the quarterly bundle) by registering a synthetic
``cadence="topic_report"`` row in ``forecast_bundle_synthesis``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.ai_models import resolve_litellm_call_params

logger = logging.getLogger(__name__)

INTRO_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static_assets", "topic_report_intro.pptx",
)


def _topics_period_label(period: str, topics: list[str]) -> str:
    """Stable period label for ``(cadence='topic_report', period_label=…)``.

    The supervisor pipeline keys its synthesis cache on (cadence,
    period_label). We want different topic selections in the same period
    to NOT collide, so we fold a topics hash into the label.
    """
    sorted_topics = sorted([(t or "").strip() for t in topics if t])
    h = hashlib.sha1("|".join(sorted_topics).encode("utf-8")).hexdigest()[:8]
    safe = (period or "").strip().replace(" ", "_") or "ondemand"
    return f"{safe}__{h}"


def _synthesize_verdicts_from_forecast(forecast_run: dict) -> list:
    """When the assessment ran with 0 evidence (e.g. the forecast is too
    fresh for any post-forecast articles), the verdicts table is empty —
    but the forecast itself has scenarios we still want to render in the
    deck as a forward-looking view.

    Pulls scenarios from ``raw_output.scenarios`` (parsing the double-
    encoded JSON the supervisor sometimes stores) and emits placeholder
    verdicts with ``verdict_label='Pending evidence'`` so the deck's
    per-scenario builder fires and produces H1/H2/H3 slides.
    """
    import json as _json
    raw = forecast_run.get("raw_output") or {}
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:
            raw = {}
    if isinstance(raw, str):  # doubly-encoded
        try:
            raw = _json.loads(raw)
        except Exception:
            raw = {}
    scenarios = (raw or {}).get("scenarios") or []
    out: list = []
    for idx, s in enumerate(scenarios):
        if not isinstance(s, dict):
            continue
        h = (s.get("type") or "h1").lower()
        out.append({
            "scenario_idx": idx,
            "scenario_title": s.get("title") or s.get("name") or f"Scenario {idx+1}",
            "scenario_description": s.get("description") or "",
            # Deck builder reads ``horizon_type`` (see forecast_pptx_export.py
            # _add_scenario_slide line ~862) — keeping both fields for safety.
            "horizon_type": h,
            "horizon": h,
            "timeframe": s.get("timeframe") or "",
            "sentiment": s.get("sentiment") or "",
            "verdict_label": "Pending evidence",
            "confirming_articles": [],
            "countering_articles": [],
            "top_articles": {},
        })
    return out


def _resolve_items_for_topics(topics: list[str]) -> list:
    """Resolve ``(assessment, forecast_run, prior_assessment)`` triples for
    an explicit topic list.

    If a topic has a forecast run but the latest assessment has no scenario
    verdicts (because the assessment found 0 evidence — common when the
    forecast was just generated and no post-forecast articles exist yet),
    synthesize placeholder verdicts from ``forecast_run.raw_output`` so the
    deck still surfaces the forward-looking scenarios.
    """
    from app.database import get_database_instance
    from app.services.wiley_delivery_service import _apply_overlay_display_names

    db = get_database_instance()
    items: list = []
    for topic in topics:
        topic = (topic or "").strip()
        if not topic:
            continue
        assessment = db.facade.get_latest_forecast_assessment_by_topic(topic)
        forecast_run = None
        if assessment:
            forecast_run = db.facade.get_future_horizons_analysis(assessment.get("run_id"))
        else:
            # No assessment at all — try to find the latest forecast run for
            # this topic so we can still produce a forward-looking deck.
            from sqlalchemy import text as sa_text
            row = db.facade._execute_with_rollback(sa_text("""
                SELECT id FROM future_horizons_runs
                WHERE topic = :topic ORDER BY created_at DESC LIMIT 1
            """), {"topic": topic}).fetchone()
            if not row:
                logger.info("Topic report: skipping %s — no forecast or assessment", topic)
                continue
            run_id = (row._mapping["id"] if hasattr(row, "_mapping") else row[0])
            forecast_run = db.facade.get_future_horizons_analysis(run_id)
            # Stub assessment so the per-topic loop has something to read
            assessment = {
                "topic": topic, "run_id": run_id, "scenario_verdicts": [],
                "summary": {}, "surprises": [], "evidence_count": 0,
            }

        # If the assessment has no verdicts, synthesize them from the
        # forecast's raw_output so the H1/H2/H3 slides render anyway.
        verdicts = assessment.get("scenario_verdicts") or []
        if not verdicts and forecast_run:
            synth = _synthesize_verdicts_from_forecast(forecast_run)
            if synth:
                # Shallow copy + inject so we don't pollute the cached
                # assessment dict in the facade.
                a = dict(assessment)
                a["scenario_verdicts"] = synth
                assessment = a
                logger.info("Topic report: synthesized %d verdicts for %s from forecast raw_output",
                            len(synth), topic)

        items.append((assessment, forecast_run or {}, None))
    return _apply_overlay_display_names(items)


def _render_cache_dir() -> str:
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "topic_report_render_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _render_cache_key(period_label: str) -> str:
    return f"topic_report_{period_label}.pptx"


def invalidate_render_cache(period_label: str) -> None:
    path = os.path.join(_render_cache_dir(), _render_cache_key(period_label))
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.warning("render-cache invalidate failed (%s): %s", path, e)


def _read_render_cache(period_label: str) -> Optional[bytes]:
    path = os.path.join(_render_cache_dir(), _render_cache_key(period_label))
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.warning("render-cache read failed (%s): %s", path, e)
    return None


def _write_render_cache(period_label: str, blob: bytes) -> None:
    path = os.path.join(_render_cache_dir(), _render_cache_key(period_label))
    try:
        with open(path, "wb") as f:
            f.write(blob)
    except Exception as e:
        logger.warning("render-cache write failed (%s): %s", path, e)


def _state_sidecar_path(period_label: str) -> str:
    """Path to the JSON sidecar that stores the (topics, period) inputs
    used to render this period_label's PPTX. The post-hoc renderers
    (HTML / MD / DOCX) read it so they can call ``resolve_items`` on
    the same topic set the PPTX builder used — period_label is hashed
    over the inputs, so without this we'd have no way to go backwards.
    """
    return os.path.join(_render_cache_dir(), f"topic_report_{period_label}.state.json")


def _write_state_sidecar(period_label: str, topics: list[str], period: Optional[str]) -> None:
    try:
        with open(_state_sidecar_path(period_label), "w", encoding="utf-8") as f:
            json.dump({"topics": list(topics or []), "period": period or ""}, f)
    except Exception as e:
        logger.warning("state-sidecar write failed (%s): %s", period_label, e)


def _read_state_sidecar(period_label: str) -> Optional[dict]:
    path = _state_sidecar_path(period_label)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("state-sidecar read failed (%s): %s", period_label, e)
        return None


def _build_topic_report_prompt(topic: str, article_rows: list) -> str:
    """Custom prompt for the Topic Reports rerun.

    Asks for the FULL deck content in one LLM call — not just scenarios.
    The stock ``generate_future_horizons_prompt`` only produces the
    Three Horizons ``scenarios`` field; the deck has slots for strategic
    recommendations, key insights, next steps, and the executive decision
    framework that need to come from the same forecast for consistency.

    Output is a single JSON object. Per-slide layout-friendly shapes:
      - strategic_recommendations: list of 3 ``{headline, rationale, horizon}``
        where horizon is one of "0-6 months" / "6-18 months" / "18+ months"
      - key_insights: list of 4-5 strings
      - next_steps: list of 3 ``{category, action}`` (category = uppercase
        short tag; action = one-sentence imperative)
      - executive_decision_framework: ``{principles: [{headline, body}]}``
        (3 leadership principles)
      - scenarios: same H1/H2/H3 shape the existing builder consumes
    """
    article_refs = "\n".join([
        f"[{i+1}] {a.get('title') or 'Untitled'} — "
        f"{a.get('news_source') or 'Unknown'} — "
        f"{str(a.get('publication_date') or '')[:10]}"
        for i, a in enumerate(article_rows)
    ])
    article_summary_lines = []
    for i, a in enumerate(article_rows, 1):
        bits = [f"[{i}]", (a.get("title") or "")[:140]]
        if a.get("sentiment"):
            bits.append(f"sent={a['sentiment']}")
        if a.get("future_signal"):
            bits.append(f"signal={a['future_signal']}")
        if a.get("time_to_impact"):
            bits.append(f"impact={a['time_to_impact']}")
        article_summary_lines.append(" · ".join(bits))
    article_summary = "\n".join(article_summary_lines)

    return f"""You are a strategic foresight expert producing a forward-looking
report on "{topic}" for a scientific-publisher executive audience.

AUDIENCE CONSTRAINT: every strategic_recommendation, next_step, and executive_decision_framework principle must be an action a scientific publisher can actually take within its own remit (editorial, commissioning, portfolio, licensing, research-integrity, partnership, or communication decisions). Never recommend actions for governments, regulators, funders, health authorities, or other third parties the publisher does not control; if the topic involves a crisis the publisher cannot act on directly, frame the action as how the publisher should respond within its remit, not how the crisis itself should be managed.

Analyse {len(article_rows)} articles and return a SINGLE JSON object with
EVERY field below populated. No prose outside the JSON. No code fences.

Output schema (strict):
{{
  "topic_briefing": {{
    "headline": "<one-sentence framing of the topic at this moment, ≤16 words>",
    "lede": "<2-3 sentence narrative paragraph setting the strategic stakes for a scientific-publisher executive>",
    "tensions": [
      {{
        "name": "<UPPERCASE TENSION NAME, 2-4 words>",
        "body": "<one-sentence elaboration of the tension or trade-off>"
      }}
    ],
    "intelligence_view": "<2-3 sentence Aunoo analytical synthesis of what the article evidence really shows>"
  }},
  "scenarios": [
    {{
      "type": "h1" | "h2" | "h3",
      "title": "<short scenario name, max 12 words>",
      "description": "<2-3 sentences with [n] citations to the article references>",
      "timeframe": "<year-year, within 2025-2040>",
      "sentiment": "Positive" | "Negative" | "Mixed" | "Neutral" | "Mixed/Positive" | "Critical/Neutral" | "Negative/Disruptive" | "Trend/Evolution" | "Breakthrough" | "Disruption/Warning" | "Warning/Disruption"
    }}
  ],
  "strategic_recommendations": [
    {{
      "headline": "<short imperative phrase, ≤8 words>",
      "rationale": "<1-3 sentences explaining what to do and why, with [n] citations>",
      "horizon": "0-6 months" | "6-18 months" | "18+ months"
    }}
  ],
  "key_insights": [
    "<1-2 sentence insight with [n] citations>"
  ],
  "next_steps": [
    {{
      "category": "<UPPERCASE 1-3 WORD TAG>",
      "action": "<one imperative sentence>"
    }}
  ],
  "executive_decision_framework": {{
    "principles": [
      {{
        "headline": "<short principle name, ≤6 words>",
        "body": "<2-3 sentences on how leaders should apply this principle>"
      }}
    ]
  }}
}}

Required quantities and structure:
- topic_briefing.tensions: EXACTLY 3-4 defining tensions
- scenarios: 12-14 total → 4-5 H1 (declining), 4-5 H2 (transition), 3-4 H3 (future vision)
  H1 timeframes 2025-2032 · H2 timeframes 2027-2037 · H3 timeframes 2033-2040
- strategic_recommendations: EXACTLY 3 (one per horizon: 0-6 / 6-18 / 18+ months)
- key_insights: 4-5 distinct observations grounded in the article set
- next_steps: EXACTLY 3 prioritised actions
- executive_decision_framework.principles: EXACTLY 3 leadership principles

Citation rules:
- Use [1], [2], [3] etc. to reference the numbered article list below
- Every scenario description should cite 2-4 articles
- Every recommendation rationale should cite 1-3 articles
- Every key_insight should cite at least 1 article

Article references (use these citation numbers):
{article_refs}

Article summary (sentiment / future_signal / time_to_impact when present):
{article_summary}

Return ONLY the JSON object. No prose, no markdown, no code fences."""


async def generate_executive_summary_for_run(
    run_id: str, topic: str, scenarios: list, model: str = "gpt-5.4",
) -> Optional[dict]:
    """Generate the Future Horizons "Executive Summary" cards for a stored
    horizons run and cache them in ``analysis_versions_v2`` under the
    canonical ``horizons_exec_summary_{run_id}`` key.

    Reuses the exact prompt + cache convention that
    ``POST /api/trend-convergence/horizons/{analysis_id}/executive-summary``
    uses, so the cards rendered in the Topic Reports PPTX are byte-
    identical to the ones the React Future Horizons tab displays.

    Returns the parsed ``summary_data`` dict (with the ``summaries`` array)
    on success, ``None`` on failure (the caller treats it as "no exec
    summary cards" and skips the slides).
    """
    import time as _time
    import re as _re
    from datetime import datetime as _dt
    from app.database import get_database_instance
    from app.services.prompt_loader import PromptLoader

    if not scenarios:
        logger.info("exec summary: no scenarios for %s — skipping", topic)
        return None

    db = get_database_instance()

    try:
        prompt_data = PromptLoader.load_prompt("future_horizons", "executive_summary")
    except Exception as e:
        logger.warning("exec summary: prompt load failed: %s", e)
        return None

    scenarios_json = json.dumps(scenarios, indent=2)
    system_prompt, user_prompt = PromptLoader.get_prompt_template(
        prompt_data,
        {
            "topic": topic,
            "scenarios_json": scenarios_json,
            "organizational_profile": (
                "Wiley — global academic publisher. Scientific publishing, "
                "research integrity, open science, peer review at scale."
            ),
        },
    )
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    # Same gpt-5.4 reasoning params as the horizons rerun: reasoning_effort
    # minimal + ample max_completion_tokens so the structured JSON has
    # room to land after the model's reasoning step.
    import litellm
    import asyncio as _asyncio
    call_kwargs: dict = {
        **resolve_litellm_call_params(model),
        "messages": [{"role": "user", "content": full_prompt}],
        "caching": False,
    }
    if model.startswith("gpt-5"):
        from app.ai_models import minimal_reasoning_effort
        call_kwargs["reasoning_effort"] = minimal_reasoning_effort(model)
        call_kwargs["max_completion_tokens"] = 16000
    else:
        call_kwargs["max_tokens"] = 8000
        call_kwargs["temperature"] = 0.6

    started = _time.time()
    try:
        response = await _asyncio.to_thread(litellm.completion, **call_kwargs)
        raw = response.choices[0].message.content
    except Exception as e:
        logger.warning("exec summary: %s call failed for %s: %s", model, topic, e)
        return None

    logger.info("exec summary: %s returned %d chars in %.1fs",
                model, len(raw or ""), _time.time() - started)
    if not (raw or "").strip():
        logger.warning("exec summary: empty response — skipping")
        return None

    # Pull JSON out (model may wrap in ```json fences or leading prose).
    summary_data: Optional[dict] = None
    m = _re.search(r"```json\s*(\{.*?\})\s*```", raw, _re.DOTALL)
    if m:
        try:
            summary_data = json.loads(m.group(1))
        except Exception:
            summary_data = None
    if summary_data is None:
        s = (raw or "").strip()
        if "{" in s and "}" in s:
            try:
                summary_data = json.loads(s[s.find("{"): s.rfind("}") + 1])
            except Exception:
                summary_data = None
    if not isinstance(summary_data, dict):
        logger.warning("exec summary: JSON parse failed — skipping")
        return None

    summary_data["generated_at"] = _dt.utcnow().isoformat()
    summary_data["topic"] = topic
    summary_data["analysis_id"] = run_id

    try:
        db.facade.save_horizons_executive_summary(
            analysis_id=run_id, topic=topic, summary_data=summary_data,
        )
        logger.info("exec summary: saved %d cards to cache_key=horizons_exec_summary_%s",
                    len(summary_data.get("summaries") or []), run_id)
    except Exception as e:
        logger.warning("exec summary: facade save failed: %s", e)

    return summary_data


async def _rerun_future_horizons_for_topic(
    topic: str, model: str, progress_callback=None,
) -> str:
    """Run a fresh Three Horizons LLM analysis for a topic and persist it
    into ``future_horizons_runs``. Returns the new run_id.

    Adapted from ``wiley_candidate_pipeline._run_three_horizons``: same
    prompt builder (`generate_future_horizons_prompt`), same persistence
    facade, but seeded from the topic's on-topic article corpus instead
    of a candidate row, and parameterised on the model.

    No HTTP, no auth, no cache layer — direct in-process call so the
    Topic Reports background task can drive it.
    """
    import time as _time
    import uuid as _uuid
    from datetime import datetime as _dt
    from app.database import get_database_instance
    db = get_database_instance()

    # Seed the prompt with the topic's most on-topic articles. Size the
    # sample dynamically based on the model's context window — mirrors
    # what ``/api/trend-convergence/{topic}`` does for the Future Horizons
    # tab, so the deck has comparable coverage to a normal run. Default
    # ``auto`` mode: ≥1M-context models get ~180 articles, smaller-context
    # models (incl. gpt-5.4 at 400k) get ~90.
    from app.routes.trend_convergence_routes import calculate_optimal_sample_size
    sample_size = calculate_optimal_sample_size(model, sample_size_mode="auto")
    logger.info("rerun horizons: %s seeding with up to %d articles", model, sample_size)

    from sqlalchemy import text as sa_text
    article_rows: list = []
    try:
        sql = sa_text(f"""
            SELECT uri, title, summary, publication_date, sentiment, category,
                   future_signal, driver_type, time_to_impact, quality_score,
                   news_source, topic_alignment_score
            FROM articles
            WHERE topic = :topic
              AND analyzed = TRUE
              AND topic_alignment_score IS NOT NULL
              AND topic_alignment_score > 0.7
            ORDER BY topic_alignment_score DESC, publication_date DESC
            LIMIT {int(sample_size)}
        """)
        rows = db.facade._execute_with_rollback(sql, {"topic": topic}).fetchall()
        for r in rows:
            article_rows.append(
                dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
            )
    except Exception as e:
        logger.warning("rerun horizons: article fetch failed for %s: %s", topic, e)
    if not article_rows:
        raise RuntimeError(
            f"No on-topic articles for '{topic}' — can't run Three Horizons."
        )
    logger.info("rerun horizons: pulled %d articles for %s", len(article_rows), topic)

    formatted_prompt = _build_topic_report_prompt(topic, article_rows)

    # Call litellm directly so we can pass the model-specific kwargs that
    # the plain ``AIModel.generate_response`` doesn't forward.
    # GPT-5 is a reasoning model — by default it burns the output token
    # budget on internal reasoning before emitting any user-visible text,
    # so a default ``max_tokens=2000`` returns 0 chars for any non-trivial
    # prompt. Pass ``reasoning_effort='minimal'`` and use
    # ``max_completion_tokens`` (not ``max_tokens``) so JSON output has room.
    import litellm
    import asyncio as _asyncio
    call_kwargs: dict = {
        **resolve_litellm_call_params(model),
        "messages": [{"role": "user", "content": formatted_prompt}],
        "caching": False,
    }
    if model.startswith("gpt-5"):
        from app.ai_models import minimal_reasoning_effort
        call_kwargs["reasoning_effort"] = minimal_reasoning_effort(model)
        call_kwargs["max_completion_tokens"] = 16000
    else:
        call_kwargs["max_tokens"] = 8000
        call_kwargs["temperature"] = 0.7

    started = _time.time()
    try:
        response = await _asyncio.to_thread(litellm.completion, **call_kwargs)
    except Exception as e:
        raise RuntimeError(f"{model} call failed: {type(e).__name__}: {e}")

    try:
        raw_response = response.choices[0].message.content
    except Exception:
        raw_response = str(response)

    logger.info("rerun horizons: %s returned %d chars in %.1fs",
                model, len(raw_response or ""), _time.time() - started)
    if not (raw_response or "").strip():
        raise RuntimeError(
            f"{model} returned an empty response — check that the model is "
            f"available and the OPENAI_API_KEY is valid for it."
        )

    # Strip ```json fences + grab outer braces.
    s = (raw_response or "").strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip()
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    if "{" in s and "}" in s:
        s = s[s.find("{"): s.rfind("}") + 1]
    try:
        parsed = json.loads(s)
    except Exception as e:
        snippet = (raw_response or "")[:300].replace("\n", " | ")
        raise RuntimeError(
            f"Three Horizons response was not valid JSON: {e}. "
            f"First 300 chars: {snippet!r}"
        )

    scenarios = parsed.get("scenarios") or []
    if not scenarios:
        raise RuntimeError("Three Horizons returned no scenarios.")
    for sc in scenarios:
        t = str(sc.get("type") or "").strip().lower()
        if t in ("h1", "h2", "h3"):
            sc["type"] = t

    run_id = str(_uuid.uuid4())
    raw_output = {
        "topic": topic,
        "topic_briefing": parsed.get("topic_briefing", {}),
        "scenarios": scenarios,
        "disruption_scenarios": parsed.get("disruption_scenarios", []),
        "strategic_recommendations": parsed.get("strategic_recommendations", []),
        "executive_decision_framework": parsed.get("executive_decision_framework", {}),
        "next_steps": parsed.get("next_steps", []),
        "key_insights": parsed.get("key_insights", []),
        "convergences": parsed.get("convergences", []),
        "impact_timeline": parsed.get("impact_timeline", []),
        "future_signals": parsed.get("future_signals", []),
        "opportunities": parsed.get("opportunities", []),
        "metadata": {
            "topic_label": topic,
            "articles_analyzed": len(article_rows),
            "model_used": model,
            "generated_at": _dt.utcnow().isoformat(),
            "analysis_type": "topic_report_rerun",
        },
        "articles_analyzed":      len(article_rows),
        "total_articles_found":   len(article_rows),
        "model_used":             model,
        "generated_at":           _dt.utcnow().isoformat(),
        "persona":                "executive",
        "timeframe_days":         180,
    }
    db.facade.save_future_horizons_analysis(
        analysis_id=run_id,
        user_id=None,
        topic=topic,
        model_used=model,
        raw_output=raw_output,
        total_articles_analyzed=len(article_rows),
        analysis_duration_seconds=_time.time() - started,
    )
    logger.info("rerun horizons: saved fresh run %s for %s (model=%s, articles=%d)",
                run_id, topic, model, len(article_rows))

    # Persist the numbered article corpus that the LLM was shown so the
    # ``[1]`` / ``[2]`` citation markers in scenario descriptions resolve
    # to real source URLs on the Future Horizons HTML download. The order
    # MUST match the order the prompt builder used — same SELECT, same
    # ORDER BY — so [N] = the Nth uri in this list.
    try:
        ordered_uris = [r.get("uri") for r in article_rows if r.get("uri")]
        if ordered_uris:
            db.facade.save_future_horizon_articles(run_id, ordered_uris, topic)
            logger.info("rerun horizons: saved %d article refs for run %s",
                        len(ordered_uris), run_id)
    except Exception as e:
        logger.warning("rerun horizons: save_future_horizon_articles failed for %s: %s",
                       run_id, e)

    # Also generate the Future Horizons Executive Summary cards (the
    # consensus % / PRIMARY SIGNAL / DECISION FORK / YOUR WINDOW
    # cards the React UI tab shows). Uses the same prompt + cache key
    # the UI uses, so the PPTX cards we render later are byte-identical.
    # gpt-5.4 reasoning latency on this step is highly variable (~50s on a
    # fast pass, ~10min on a slow one), so emit progress BEFORE the call
    # to unstick the UI from "5%" while the second LLM round runs.
    if progress_callback:
        try:
            progress_callback(
                None,
                f"Generating Executive Summary cards for {topic} · {model}…",
            )
        except Exception as e:
            logger.warning("progress_callback failed (exec summary stage): %s", e)
    try:
        await generate_executive_summary_for_run(
            run_id=run_id, topic=topic, scenarios=scenarios, model=model,
        )
    except Exception as e:
        logger.warning("exec summary generation failed for %s: %s", topic, e)

    return run_id


async def generate_topic_report(
    topics: list[str],
    *,
    period: Optional[str] = None,
    when: Optional[datetime] = None,
    rerun_forecast: bool = False,
    force_model: Optional[str] = None,
    progress_callback=None,
) -> Tuple[bytes, str, list, str, list]:
    """Render the on-demand topic report PPTX directly from each topic's
    Future Horizons forecast.

    No back-test, no supervisor pipeline, no reviewer gate — this reads
    ``future_horizons_runs.raw_output`` for each selected topic and shapes
    it into the Wiley Horizons deck via :func:`topic_report_pptx.build_topic_report_pptx`.

    When ``rerun_forecast=True``, runs a fresh Three Horizons analysis
    per topic via :func:`_rerun_future_horizons_for_topic` (using
    ``force_model`` or "gpt-5.4") BEFORE loading items — so the deck
    reflects the latest model + latest article corpus.

    Returns ``(blob, period_label, included_topics, None, [])`` to keep the
    tuple shape compatible with the route handler that mirrored the
    quarterly bundle pattern.
    """
    from app.services.topic_report_pptx import (
        build_topic_report_pptx, resolve_items,
    )

    def _emit(pct: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as e:
                logger.warning("progress_callback failed: %s", e)

    when = when or datetime.now(timezone.utc)
    period = period or when.strftime("%Y-%m-%d")
    period_label = _topics_period_label(period, topics)

    # When rerunning, drop the PPTX cache so the next render uses the
    # fresh future_horizons_runs row.
    if rerun_forecast:
        invalidate_render_cache(period_label)
    # Fast path — cached PPTX (skipped when rerun was requested).
    cached = _read_render_cache(period_label)
    if cached is not None:
        _emit(100, "Returning cached PPTX")
        return cached, period_label, list(topics), None, []

    # Re-run the upstream Three Horizons analysis per topic if asked.
    if rerun_forecast:
        model = force_model or "gpt-5.4"
        span_lo, span_hi = 5, 65   # share the progress budget across topics
        n = max(1, len(topics))
        for i, topic in enumerate(topics, 1):
            # Split each topic's slot in half: scenarios first, exec summary
            # second. gpt-5.4 reasoning latency on the exec summary can rival
            # the scenario generation, so without a mid-step ping the UI
            # would freeze on the first percentage for ~10 minutes per topic.
            slot = (span_hi - span_lo) / n
            base = span_lo + slot * (i - 1)
            pct_a = int(base)
            pct_b = int(base + slot * 0.5)
            _emit(pct_a, f"Re-running Three Horizons for {topic} ({i}/{n}) · {model}…")

            def _topic_progress(pct, msg):
                # The rerun emits a stage transition mid-call ("Generating
                # Executive Summary cards…"). Anchor the % to ``pct_b`` —
                # roughly half-way through this topic's slot — so the bar
                # moves while gpt-5.4 spins on the second LLM round.
                _emit(pct_b if pct is None else pct, msg)

            try:
                await _rerun_future_horizons_for_topic(
                    topic, model, progress_callback=_topic_progress,
                )
            except Exception as e:
                logger.warning("rerun horizons failed for %s: %s", topic, e)
                _emit(pct_a, f"⚠ {topic} rerun failed: {e}")

    _emit(70, "Loading forecasts")
    items = resolve_items(topics)
    if not items:
        raise ValueError(
            "None of the selected topics have a stored Future Horizons "
            "forecast. Generate one on the Future Horizons tab first."
        )
    _emit(85, f"Loaded {len(items)} forecast(s)")
    _emit(92, "Rendering PPTX")
    blob = build_topic_report_pptx(items, period_label=period)
    _write_render_cache(period_label, blob)
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    # Sidecar so HTML/MD/DOCX endpoints can resolve the same topic set.
    _write_state_sidecar(period_label, included_topics, period)
    _emit(100, "Done")
    return blob, period_label, included_topics, None, []


def _load_cached_state(period_label: str):
    """Load (items, synth, eos_per_topic, review) for a topic-report period
    from the cached supervisor synthesis. Raises ValueError when no PPTX
    has been generated yet for this period.

    The MD / HTML / DOCX exports are *views* of the cached synthesis — they
    never re-run the multi-agent pipeline. The PPTX path is the canonical
    generator.
    """
    from app.database import get_database_instance
    from app.services.wiley_delivery_service import _apply_overlay_display_names

    db = get_database_instance()
    synth = db.facade.get_forecast_bundle_synthesis("topic_report", period_label) or {}
    if not (synth.get("payload") or synth.get("topics")):
        raise ValueError(
            f"No generated topic report for period_label={period_label}. "
            "Generate the PPTX first; the MD/HTML/DOCX exports are views of "
            "the cached synthesis."
        )

    items: list = []
    for entry in (synth.get("topics") or []):
        topic = entry.get("topic") if isinstance(entry, dict) else entry
        if not topic:
            continue
        a = db.facade.get_latest_forecast_assessment_by_topic(topic)
        if a:
            items.append((a, None, None))
    items = _apply_overlay_display_names(items)

    eos_per_topic: dict = {}
    for a, _r, _p in items:
        eos = (a.get("summary") or {}).get("extreme_outlier_scenarios") \
            or (a.get("summary") or {}).get("eos") or []
        if eos:
            eos_per_topic[a.get("topic")] = eos

    review = db.facade.get_forecast_bundle_review("topic_report", period_label) or {}
    return items, synth, eos_per_topic, review


async def generate_topic_report_markdown(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the cached topic-report synthesis as Markdown."""
    from app.services.forecast_bundle_markdown import build_bundle_markdown
    from app.services.wiley_delivery_service import _events_by_topic

    items, synth, eos_per_topic, review = _load_cached_state(period_label)
    blob = build_bundle_markdown(
        items,
        period_label=period_label,
        cadence="topic_report",
        updates_only=True,
        bundle_synthesis=synth.get("payload") or synth,
        eos_per_topic=eos_per_topic,
        review_findings=review.get("reviewer_findings"),
        review_verdict=review.get("status"),
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, review.get("status"), review.get("reviewer_findings")


async def generate_topic_report_html(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the topic-report deck as standalone interactive HTML.

    Uses the SAME ``items`` list the PPTX builder uses (resolved via
    ``topic_report_pptx.resolve_items``) so the HTML carries Briefing
    Synthesis, Executive Summary cards, Key Insights, Strategic Recs,
    Decision Framework, Next Steps, Black Swans, Supporting Articles,
    and the H1/H2/H3 scenario walk. NOT the back-test bundle HTML.
    """
    from app.services.topic_report_pptx import resolve_items
    from app.services.topic_report_html import build_topic_report_html

    state = _read_state_sidecar(period_label) or {}
    topics = state.get("topics") or []
    period = state.get("period") or period_label
    if not topics:
        raise ValueError(
            f"No state sidecar for period_label={period_label}. "
            "Generate the PPTX first so the export can resolve the same topic set."
        )
    items = resolve_items(topics)
    blob = build_topic_report_html(items, period_label=period_label, period=period)
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, None, []


async def generate_topic_report_docx(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the topic-report deck as a Word document.

    Uses the same ``items`` list ``build_topic_report_pptx`` consumes
    (resolved via ``topic_report_pptx.resolve_items``) so the DOCX
    carries Briefing Synthesis, Executive Summary cards, Key Insights,
    Strategic Recs, Decision Framework, Next Steps, Black Swans, the
    H1/H2/H3 scenario walk, and the numbered article references —
    matching the HTML/PPTX. NOT the back-test bundle DOCX.
    """
    from app.services.topic_report_pptx import resolve_items
    from app.services.topic_report_docx import build_topic_report_docx

    state = _read_state_sidecar(period_label) or {}
    topics = state.get("topics") or []
    period = state.get("period") or period_label
    if not topics:
        raise ValueError(
            f"No state sidecar for period_label={period_label}. "
            "Generate the PPTX first so the export can resolve the same topic set."
        )
    items = resolve_items(topics)
    blob = build_topic_report_docx(items, period_label=period_label, period=period)
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, None, []
