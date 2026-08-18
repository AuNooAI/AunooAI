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
from app.services.report_style import CLINICAL_STYLE

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
    """Per-tenant render-cache dir.

    The old path was ``$TMPDIR/topic_report_render_cache`` — shared by every
    tenant on the box, keyed only by period_label. Two tenants generating the
    same topic set for the same period would silently serve each other's
    decks and sidecars. Scope by DB name (unique per tenant). Files from the
    shared dir are migrated on first touch so pinned-run sidecars survive.
    """
    import tempfile
    tenant = os.getenv("DB_NAME") or "default"
    d = os.path.join(tempfile.gettempdir(), f"topic_report_render_cache_{tenant}")
    os.makedirs(d, exist_ok=True)
    # No automatic migration from the old shared dir — its files carry no
    # tenant marker, so copying them in bulk would recreate the leak.
    # Existing sidecars are placed into the right tenant dir by hand.
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


def _write_state_sidecar(period_label: str, topics: list[str], period: Optional[str],
                         run_ids: Optional[dict] = None) -> None:
    """Persist the period's build state.

    ``run_ids`` maps SOURCE topic name → the future_horizons_runs id the
    PPTX build used. Every other export resolves through this mapping, so
    a horizons re-run between exports cannot silently swap the analysis
    under an artifact — the failure where the deck and the HTML carried
    different scenarios under the same cover.
    """
    try:
        with open(_state_sidecar_path(period_label), "w", encoding="utf-8") as f:
            json.dump({"topics": list(topics or []), "period": period or "",
                       "run_ids": dict(run_ids or {})}, f)
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

    # Horizon years are anchored to TODAY, not baked into the prompt. The
    # hard-coded "2025-2040" produced a Q3 2026 report whose H1 window had
    # already started and whose chart labelled 2025 as "Present".
    from datetime import date as _date
    _y0 = _date.today().year
    _yq = f"Q{(_date.today().month - 1) // 3 + 1} {_y0}"

    return f"""You are a strategic foresight expert producing a forward-looking
report on "{topic}" for a scientific-publisher executive audience.

TODAY IS {_date.today().isoformat()} ({_yq}). Everything you write is read as
a forecast made now. Never propose a deadline, decision point or action window
that has already passed; the earliest date you may name is {_y0}.

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
      "timeframe": "<year-year, within {_y0}-{_y0 + 15}>",
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
  H1 timeframes {_y0}-{_y0 + 7} · H2 timeframes {_y0 + 2}-{_y0 + 12} · H3 timeframes {_y0 + 8}-{_y0 + 15}
- strategic_recommendations: EXACTLY 3 (one per horizon: 0-6 / 6-18 / 18+ months)
- key_insights: 4-5 distinct observations grounded in the article set
- next_steps: EXACTLY 3 prioritised actions
- executive_decision_framework.principles: EXACTLY 3 leadership principles

Citation rules:
- Use [1], [2], [3] etc. to reference the numbered article list below
- Every scenario description should cite 2-4 articles
- Every recommendation rationale should cite 1-3 articles
- Every key_insight should cite at least 1 article
- One bracket per article. Write "[44][52]", never "[44, 52]".

Rules for figures (a wrong number here goes to the customer as fact):
- Only state a figure that appears in one of the numbered articles below, and
  put its citation in the same sentence.
- Copy the unit exactly as the source wrote it. "1.4L" and "1.5 lakh" mean
  140,000 and 150,000, not 1.4 million. "crore" is 10 million. If a source
  uses a unit you are not certain of, leave the figure out.
- Never restate a figure in a unit the source did not use, and never convert
  a count into a rate ("one in forty") unless the source states that rate.
- When the articles disagree on a figure, say so and name both, or use the
  peer-reviewed source and drop the aggregator. Do not present a contested
  number as settled.

Writing rules (this text goes on a slide in front of a publishing executive —
these are not style preferences, they are requirements):
- Lead with the finding, then explain it. Never build up to the point.
- Use the plain word. "AI-generated citations that do not exist" beats
  "phantom citations infiltrating the research record at industrial scale".
- Give every number a meaning in the same sentence: "AUC 0.478, no better than
  a coin toss" beats "AUC 0.478 — the signal is weak". Use a figure from THIS
  article set for the meaning, never one carried over from an example.
- Do NOT use: unprecedented, crisis point, at scale, weaponize, dual/twin
  (assault, threat, challenge), core value proposition, the window is
  narrowing, existential, seismic, transformative, paradigm.
- Do NOT open a sentence with Critically, Notably, Importantly, or Crucially.
  If it matters, the sentence itself must show why.
- No "not X, but Y" antithesis more than once in the whole response.
- No three-item lists where the third item exists only for rhythm. Two real
  items beat three padded ones.
- Em dashes: at most one per paragraph. Prefer a comma, colon or full stop.
- No closing sentence that restates what was just said in grander words.
{CLINICAL_STYLE}

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
            # Without this the model has no idea what quarter it is, and
            # writes decision forks with deadlines already in the past.
            "today": _dt.now().date().isoformat(),
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

    # Offset-aware local time. utcnow() produced a naive UTC string, so a
    # deck built at 12:16 local stamped itself 10:16 while the dates on the
    # neighbouring divider slide were local — two clocks, two slides apart.
    summary_data["generated_at"] = _dt.now().astimezone().isoformat()
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


# Slide prose is short, so a passage can read as slop while sitting at or
# under the global threshold of 3. The briefing lede that prompted this had
# exactly 3 tells and sailed through.
_REPORT_TELL_THRESHOLD = int(os.getenv("REPORT_TELL_THRESHOLD", "1"))


async def _humanize_report_prose(raw_output: dict) -> None:
    """Strip AI tells from the narrative fields of a topic-report run, in place.

    Until now the humanizer was only wired into the Wiley bundle supervisor,
    so topic-report prose went from the model straight onto a slide with no
    check at all. Only genuinely narrative fields are rewritten: headlines,
    scenario titles and imperative phrases are left alone, since rewriting
    them for rhythm would fight the schema's length limits.

    Best-effort — never blocks report generation.
    """
    try:
        from app.services.wiley_humanizer import humanize_text, humanize_enabled
    except Exception as e:
        logger.warning("humanize unavailable for topic report: %s", e)
        return
    if not humanize_enabled():
        return

    brief = raw_output.get("topic_briefing") or {}
    targets = [
        (brief, "lede"),
        (brief, "intelligence_view"),
    ]
    for t in (brief.get("tensions") or []):
        if isinstance(t, dict):
            targets.append((t, "body"))
    for r in (raw_output.get("strategic_recommendations") or []):
        if isinstance(r, dict):
            targets.append((r, "rationale"))

    rewritten = 0
    for holder, key in targets:
        cur = holder.get(key)
        if not isinstance(cur, str) or not cur.strip():
            continue
        try:
            res = await humanize_text(cur, threshold=_REPORT_TELL_THRESHOLD)
        except Exception as e:
            logger.warning("humanize failed on %s: %s", key, e)
            continue
        if res.get("changed"):
            holder[key] = res["text"]
            rewritten += 1
    if rewritten:
        logger.info("humanize: rewrote %d/%d topic-report prose fields",
                    rewritten, len(targets))


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

    # A tracked topic's deck name is decoupled from the article `topic` tag: the
    # Add-Topic wizard lets an analyst name "Quantum Advantage" while the seed
    # articles stay tagged "Quantum Computing". Querying the deck name alone
    # returned zero rows and failed the rerun outright. The forecast assessment
    # path already honours source_topics; this one did not.
    eval_topics = [topic]
    try:
        meta = db.facade.get_forecast_topic_metadata(topic) or {}
        src = meta.get("source_topics")
        if isinstance(src, list) and [t for t in src if (t or "").strip()]:
            eval_topics = [t.strip() for t in src if (t or "").strip()]
    except Exception as e:
        logger.warning(
            "rerun horizons: could not read source_topics for %r (%s) — "
            "falling back to the tracked topic name", topic, e,
        )
    if eval_topics != [topic]:
        logger.info(
            "rerun horizons: tracked topic %r is backed by source topics %s",
            topic, eval_topics,
        )

    from sqlalchemy import text as sa_text
    article_rows: list = []
    try:
        # Ordering is fully deterministic — alignment, then date, then uri as
        # the tie-break. Articles from different source topics interleave, so
        # without the final key the numbered citations could differ between two
        # runs over identical data.
        sql = sa_text(f"""
            SELECT uri, title, summary, publication_date, sentiment, category,
                   future_signal, driver_type, time_to_impact, quality_score,
                   news_source, topic_alignment_score, topic
            FROM articles
            WHERE topic = ANY(:topics)
              AND analyzed = TRUE
              AND topic_alignment_score IS NOT NULL
              AND topic_alignment_score > 0.7
            ORDER BY topic_alignment_score DESC, publication_date DESC, uri ASC
            LIMIT {int(sample_size)}
        """)
        rows = db.facade._execute_with_rollback(sql, {"topics": eval_topics}).fetchall()
        seen_uris = set()
        for r in rows:
            rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
            # The same article can be tagged under two source topics; keep the
            # first occurrence so numbering stays stable.
            if rd.get("uri") in seen_uris:
                continue
            seen_uris.add(rd.get("uri"))
            article_rows.append(rd)
    except Exception as e:
        logger.warning(
            "rerun horizons: article fetch failed for %r (source topics %s): %s",
            topic, eval_topics, e,
        )
    # Corpus hygiene BEFORE numbering — the numbered list the model sees is
    # the list we persist and the list every export cites, so it has to
    # happen here, not at render time. Three steps:
    #   1. drop blocked publishers (misinformation sites are not evidence)
    #   2. drop syndicated duplicates (one story counted five times)
    #   3. cheap LLM yes/no screen — ``topic_alignment_score`` saturates at
    #      the top of its range (43 articles at exactly 1.00 on this topic,
    #      including plain AI business news), so a threshold cannot help.
    #      The screen fails open: on any error the corpus passes unchanged.
    from app.services.report_corpus import filter_report_corpus, screen_corpus_relevance
    article_rows = filter_report_corpus(article_rows, topic=topic)
    article_rows = await screen_corpus_relevance(article_rows, topic)
    if not article_rows:
        raise RuntimeError(
            f"No on-topic articles for '{topic}' (searched source topics "
            f"{eval_topics}) — can't run Three Horizons."
        )
    logger.info(
        "rerun horizons: pulled %d articles for %r from source topics %s",
        len(article_rows), topic, eval_topics,
    )

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
            "generated_at": _dt.now().astimezone().isoformat(),
            "analysis_type": "topic_report_rerun",
            # Provenance: which corpus topics this run was actually built from.
            # The run's own `topic` stays the tracked/deck name, so without this
            # there is no record that "Quantum Advantage" was sourced from
            # "Quantum Computing".
            "source_topics": list(eval_topics),
            "evidence_alignment_min": 0.7,
            "evidence_sample_size": int(sample_size),
        },
        "articles_analyzed":      len(article_rows),
        "total_articles_found":   len(article_rows),
        "model_used":             model,
        "generated_at":           _dt.now().astimezone().isoformat(),
        "persona":                "executive",
        "timeframe_days":         180,
    }
    await _humanize_report_prose(raw_output)

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
    # Write the SOURCE topic names, not ``included_topics`` — the latter have
    # been through ``_apply_overlay_display_names``, so a topic with a deck
    # overlay is stored under its display name ("Scientific Publishing")
    # while future_horizons_runs holds the real one ("Scientific Publishers -
    # General Monitoring"). resolve_items looks up by the real name, so every
    # export silently dropped that topic, logging only
    # "skipping <display name> — no forecast run".
    #
    # run_ids pin every later export to THE RUNS THIS DECK USED. Without
    # the pin, each export resolved "latest run per topic" at its own
    # moment, so a re-run between exports produced a deck and an HTML
    # report with different scenarios under the same cover.
    run_ids = {a.get("_source_topic"): a.get("run_id")
               for (a, _r, _p) in items
               if a.get("_source_topic") and a.get("run_id")}
    _write_state_sidecar(period_label, list(topics), period, run_ids=run_ids)

    # Release lint — the machine version of the Q3 review. Findings are
    # logged and stored on the sidecar; they never block the render.
    try:
        from app.services.report_lint import lint_topic_report, deck_text_from_blob
        lint = lint_topic_report(items, deck_text=deck_text_from_blob(blob))
        if lint:
            _emit(99, f"⚠ Release lint: {len(lint)} finding(s) — see logs")
            state = _read_state_sidecar(period_label) or {}
            state["lint"] = lint
            with open(_state_sidecar_path(period_label), "w", encoding="utf-8") as f:
                json.dump(state, f)
    except Exception as e:
        logger.warning("release lint failed (non-fatal): %s", e)

    # Reference check — probes every cited URL for dead links and paywalls.
    # Network-bound (about a minute for a full corpus), advisory like the
    # lint, and skippable with REPORT_REFERENCE_CHECK=0.
    if os.getenv("REPORT_REFERENCE_CHECK", "1").lower() not in ("0", "false", "no"):
        try:
            from app.services.reference_check import check_urls, summarize
            ref_urls: list = []
            _seen_urls: set = set()
            for (a, _r, _p) in items:
                for art in a.get("_articles_corpus") or []:
                    u = ((art or {}).get("uri") or "").strip()
                    if (u.lower().startswith(("http://", "https://"))
                            and u not in _seen_urls):
                        _seen_urls.add(u)
                        ref_urls.append(u)
            if ref_urls:
                _emit(99, f"Checking {len(ref_urls)} reference link(s)")
                ref_results = await check_urls(ref_urls, concurrency=12,
                                               timeout=10.0)
                ref_counts = summarize(ref_results)
                state = _read_state_sidecar(period_label) or {}
                state["reference_check"] = {
                    "counts": ref_counts,
                    "problems": [r for r in ref_results
                                 if r["verdict"] != "ok"],
                }
                with open(_state_sidecar_path(period_label), "w",
                          encoding="utf-8") as f:
                    json.dump(state, f)
                logger.info("reference check: %s", ref_counts)
                if ref_counts.get("dead") or ref_counts.get("redirect"):
                    _emit(99, f"⚠ References: {ref_counts['dead']} dead, "
                              f"{ref_counts['redirect']} redirected — "
                              f"see sidecar")
        except Exception as e:
            logger.warning("reference check failed (non-fatal): %s", e)
    _emit(100, "Done")
    return blob, period_label, included_topics, None, []


async def ensure_bundle_synthesis(period_label: str, *, progress_callback=None) -> bool:
    """Make sure a ``topic_report`` synthesis row exists for this period.

    The synthesis is what the executive-summary exports render: the
    five-section letter, what changed, cross-cutting themes and the decision
    framework. The deck path deliberately skips the supervisor (it reads
    ``future_horizons_runs`` directly), so nothing else writes this row —
    which is why the DOCX and Markdown exports had nothing to render for any
    period generated after 2026-06-03.

    Returns True if it ran the pipeline, False if the row already existed.
    The supervisor persists the payload itself, so a request that dies at the
    proxy before this returns still leaves the row behind and the next call
    is instant.
    """
    from app.database import get_database_instance

    db = get_database_instance()
    existing = db.facade.get_forecast_bundle_synthesis("topic_report", period_label) or {}
    if existing.get("payload"):
        return False

    state = _read_state_sidecar(period_label) or {}
    topics = state.get("topics") or []
    if not topics:
        raise ValueError(
            f"No state sidecar for period_label={period_label}. "
            "Generate the report first so the export can resolve the topic set."
        )

    from app.services.topic_report_pptx import resolve_items
    from app.services.wiley_bundle_supervisor import run_pipeline

    # Pin the synthesis to the same runs the deck used, so the letter and
    # the deck describe one analysis.
    items = resolve_items(topics, run_ids=state.get("run_ids") or {})
    if not items:
        raise ValueError(
            f"None of the topics for {period_label} have a stored forecast run."
        )

    # EOS must come from the same source the DECK renders — resolve_items
    # loads ``_eos_scenarios`` from saved_eos per topic. Reading only the
    # assessment summary (empty on the topic-report path) told the letter
    # agent black_swan_count=0, and it wrote "No new tail-risk scenarios
    # surfaced this quarter" under a deck showing 24 cards — the exact
    # contradiction the Q3 review flagged.
    eos_per_topic: dict = {}
    for a, _r, _p in items:
        summary = a.get("summary") or {}
        eos = (a.get("_eos_scenarios")
               or summary.get("extreme_outlier_scenarios")
               or summary.get("eos") or [])
        if eos:
            eos_per_topic[a.get("topic")] = eos

    logger.info("topic report %s: no synthesis row — running the supervisor pipeline "
                "over %d topics", period_label, len(items))
    final_status = None
    async for ev in run_pipeline(items, cadence="topic_report",
                                 period_label=period_label,
                                 eos_per_topic=eos_per_topic):
        if not isinstance(ev, dict):
            continue
        if ev.get("stage") == "complete":
            final_status = ev.get("status")
        if progress_callback:
            try:
                progress_callback(ev.get("progress"), f"{ev.get('stage')} {ev.get('status')}")
            except Exception:
                pass
    # A reviewer verdict of revision_requested still leaves a usable payload;
    # the exports surface the findings rather than refusing to render.
    logger.info("topic report %s: synthesis complete (reviewer: %s)",
                period_label, final_status or "n/a")
    return True


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

    # Prefer the sidecar's topic list: it records the SOURCE names, while the
    # synthesis row's ``topics`` were captured after
    # ``_apply_overlay_display_names`` ran, so a topic with a deck overlay is
    # stored there under its display name and cannot be looked up.
    sidecar_topics = (_read_state_sidecar(period_label) or {}).get("topics") or []
    topic_names = sidecar_topics or [
        (e.get("topic") if isinstance(e, dict) else e) for e in (synth.get("topics") or [])
    ]

    from app.services.forecast_assessment_service import source_topic_for_display_name

    items: list = []
    for topic in topic_names:
        if not topic:
            continue
        a = db.facade.get_latest_forecast_assessment_by_topic(topic)
        if not a:
            # Rows and sidecars written before 2026-08-03 hold display names.
            source = source_topic_for_display_name(topic)
            if source:
                a = db.facade.get_latest_forecast_assessment_by_topic(source)
        if a:
            items.append((a, None, None))
        else:
            logger.info("topic report %s: no assessment for %r — omitted from the export",
                        period_label, topic)
    items = _apply_overlay_display_names(items)

    # Same saved_eos source the deck uses (see ensure_bundle_synthesis) —
    # the assessment summary is empty on the topic-report path.
    eos_per_topic: dict = {}
    for a, _r, _p in items:
        eos = (a.get("summary") or {}).get("extreme_outlier_scenarios") \
            or (a.get("summary") or {}).get("eos") or []
        if not eos:
            try:
                row = db.facade.get_latest_saved_eos_for_topic(
                    a.get("topic"), max_age_days=180) or {}
                eos = row.get("scenarios") or []
            except Exception:
                eos = []
        if eos:
            eos_per_topic[a.get("topic")] = eos

    review = db.facade.get_forecast_bundle_review("topic_report", period_label) or {}
    return items, synth, eos_per_topic, review


async def generate_topic_report_markdown(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the topic-report synthesis as Markdown — the same executive
    summary the DOCX carries, in plain text.

    Generates the synthesis on first request when the period has none, same as
    the DOCX path. Without it this raised "No generated topic report for
    period_label=…" for every period created after 2026-06-03, since nothing
    writes that row any more.
    """
    from app.services.forecast_bundle_markdown import build_bundle_markdown
    from app.services.wiley_delivery_service import _events_by_topic

    await ensure_bundle_synthesis(period_label)
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
    # Pin to the exact runs the PPTX build used (sidecars written before
    # 2026-08-03 have no run_ids and fall back to latest-run resolution).
    items = resolve_items(topics, run_ids=state.get("run_ids") or {})
    blob = build_topic_report_html(items, period_label=period_label, period=period)
    try:
        from app.services.report_lint import lint_topic_report
        lint_topic_report(items, html_text=blob.decode("utf-8", "replace"))
    except Exception as e:
        logger.warning("release lint failed (non-fatal): %s", e)
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, None, []


async def generate_topic_report_docx(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the topic-report synthesis as an executive-summary Word document.

    This is the emailable briefing — the five-section letter, what changed,
    cross-cutting themes, decision framework and a one-paragraph status per
    topic — not a transcript of the deck. Same renderer and same
    ``updates_only=True`` mode that produced the Q2 2026 document.

    Between 2026-06-18 (``451bed56``) and today this pointed at
    ``topic_report_docx.build_topic_report_docx``, which walks the deck and
    emits every slide's content in Word: 5,316 words per topic, including
    slide furniture like "CARD 3 OF 6" and "YOUR WINDOW". That renderer is
    still available on the ``download-full.docx`` route for anyone who wants
    the whole thing.

    The synthesis is generated on first request if the period does not have
    one yet, which is slow — it is the multi-agent pipeline. The supervisor
    persists as it goes, so a proxy timeout on that first call is not fatal:
    the next request renders from the row.
    """
    from app.services.forecast_bundle_docx import build_bundle_docx

    await ensure_bundle_synthesis(period_label)
    items, synth, eos_per_topic, review = _load_cached_state(period_label)
    # The header and signoff show this verbatim, so use the human period
    # ("Q3 2026") rather than the internal topics-hash label
    # ("Q3_2026__2cec74a7") that keys the cache.
    display_period = (_read_state_sidecar(period_label) or {}).get("period") or period_label
    blob = build_bundle_docx(
        items,
        period_label=display_period,
        cadence="topic_report",
        updates_only=True,
        bundle_synthesis=synth.get("payload") or synth,
        eos_per_topic=eos_per_topic,
        review_findings=review.get("reviewer_findings"),
        review_verdict=review.get("status"),
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, review.get("status"), review.get("reviewer_findings")


async def generate_topic_report_docx_full(period_label: str) -> Tuple[bytes, str, list, str, list]:
    """Render the full deck content as a Word document — every slide, in order.

    Kept for anyone who wants the whole report in Word rather than the
    executive summary. Long by design: one topic runs to roughly 5,000 words.
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
    # Same run pinning as the HTML export — render the runs the deck used.
    items = resolve_items(topics, run_ids=state.get("run_ids") or {})
    blob = build_topic_report_docx(items, period_label=period_label, period=period)
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, None, []
