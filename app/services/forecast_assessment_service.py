"""Forecast Assessment service.

Given a stored Three Horizons forecast (a row in ``future_horizons_runs``),
score each scenario against articles that arrived AFTER the forecast was
generated, then output per-scenario verdicts (On-track / Accelerating /
Stalled / Off-track / Inconclusive) plus an "unanticipated developments"
panel of evidence clusters no scenario explains.

Pipeline stages (see /root/.claude/plans/see-wiley-horizons-final-eager-boole.md):
  A. pgvector recall per scenario probe (top ~150)
  B. cross-encoder rerank to topical relevance (sigmoid ≥ STAGE_B_MIN_SCORE)
  C. exclusive assignment across all scenarios (margin gate)
  D. per-(scenario, article) LLM classification using the prompt at
     data/prompts/forecast_assessment/current.json
  E. aggregate per-scenario classifications to a verdict label
  F. surprise clustering on the residual (ambiguous + unrelated)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Tuning constants ───────────────────────────────────────────────────────
STAGE_A_TOP_K: int = 150          # per scenario, from pgvector
STAGE_B_MIN_SCORE: float = 0.5    # sigmoid'd reranker score gate
# Margin gate. 0.10 was too tight even for deck-level (5 well-separated
# scenarios): 97% of articles ended up ambiguous because the reranker
# returned tightly bunched scores for in-topic articles. 0.04 lets through
# articles whose top scenario beats the runner-up by ~4 percentage points
# — still requires clear directional signal but doesn't penalise honest
# overlap between, e.g., Public Trust and Peer Review Strain.
STAGE_C_MARGIN: float = 0.04
STAGE_D_CONCURRENCY: int = 8      # parallel LLM calls
DEFAULT_MAX_ARTICLES: int = 2000
DEFAULT_CLASSIFY_MODEL: str = "gpt-5.4-mini"

# Confidence floor below which a verdict counts as inconclusive evidence
MIN_CONF_FOR_VERDICT_PROMOTION: float = 0.5

# Decision-tree thresholds (see plan §5)
DIRECTIONAL_RATE_ONTRACK: float = 0.2
DIRECTIONAL_RATE_OFFTRACK: float = -0.2
# Was 15 — too high for ~3-month assessment windows on small-topic corpora.
# 6 is the smallest sample where a directional rate is interpretable; below
# that we still emit Inconclusive regardless of rate.
INCONCLUSIVE_MIN_ARTICLES: int = 6

DECK_OVERLAY_DIR = Path("data/wiley_horizons")


def build_original_scenarios(run_id, db_scenarios, deck_overlay, *,
                             granularity="auto", topic=None):
    """The run's ORIGINAL scenario list, exactly as an assessment sees it.

    A run has two possible scenario lists. The raw list is what the forecast
    stored; the deck list collapses overlapping raw scenarios into the named
    ones the customer's deck shows, and is what actually gets assessed whenever
    the topic has an overlay (``granularity='auto'`` is the default). Their
    titles, order and length all differ.

    Everything that needs to identify a scenario must build the list the same
    way, or the keys do not match. When ``patch_scenario_status`` derived keys
    from the raw list while ``assess_run`` stamped them from the deck list, the
    two key sets had **zero** overlap, so marking a scenario done returned 409
    for every topic with an overlay — which is all five Wiley Horizons topics.

    Returns ``(scenarios, level)`` where level is ``'deck'`` or ``'db'``, with
    ``scenario_key`` stamped on each entry. Callers must not re-derive keys.
    """
    from app.services.scenario_identity import scenario_key_for

    use_deck = deck_overlay and granularity in ("deck", "auto")
    scenario_level = "db"
    scenarios = list(db_scenarios)

    if use_deck:
        built = _build_deck_scenarios(db_scenarios, deck_overlay)
        if built:
            scenarios = built
            scenario_level = "deck"
        else:
            # The overlay's scenario_title_to_deck_key matched NONE of this
            # run's titles — a stale overlay written against a different run.
            # This used to flow straight through: assign_exclusive([]) → 0
            # assigned → a "completed" assessment with zero verdicts in 0.2s,
            # which the quarterly bundle then read as the topic's status.
            # Fall back to the raw scenarios and say so loudly.
            logger.error(
                "Deck overlay for %r maps 0 of this run's %d scenario titles "
                "(stale overlay — check for a .proposed replacement in the "
                "overlay dir). Falling back to db-level scenarios.",
                topic, len(db_scenarios),
            )

    for i, sc in enumerate(scenarios):
        if isinstance(sc, dict):
            sc["scenario_key"] = scenario_key_for(run_id, sc, i)
    return scenarios, scenario_level


def load_original_scenarios_for_run(db, run_id):
    """``build_original_scenarios`` for a stored run, loading its own inputs.

    For callers outside the assessment pipeline (the status route) that have a
    run id and nothing else.
    """
    forecast = db.facade.get_future_horizons_analysis(run_id)
    if not forecast:
        return [], "db"
    raw = forecast.get("raw_output") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    topic = forecast.get("topic") or (raw or {}).get("topic")
    return build_original_scenarios(
        run_id, (raw or {}).get("scenarios") or [], _load_deck_overlay(topic),
        topic=topic,
    )


# ── Public entry point ─────────────────────────────────────────────────────

async def assess_run(
    run_id: str,
    *,
    mode: str = "live",
    max_articles: int = DEFAULT_MAX_ARTICLES,
    classify_model: str = DEFAULT_CLASSIFY_MODEL,
    margin: float = STAGE_C_MARGIN,
    granularity: str = "auto",
    window_weeks: Optional[int] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """Run a forecast assessment for the given horizons run_id.

    Parameters
    ----------
    run_id : str
        future_horizons_runs.id of the forecast to assess.
    mode : str
        "live" — assess against post-forecast articles (normal case).
        "placebo" — assess against PRE-forecast articles. The temporal placebo
        canary from plan §7.1; verdicts should be Inconclusive.
        "shuffle" — keep article window live but swap scenario titles with
        scenarios from another topic (caller arranges; we just label it).
    max_articles : int
        Cap on the post-forecast article pool. Default 2000.
    classify_model : str
        Model passed to ai_models.get_ai_model() for stage D.
    margin : float
        Stage C margin gate. Below this gap, article goes to ambiguous bucket.
    progress_callback : callable
        Optional (pct, message) callback for background-task progress.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    started = time.time()
    forecast = db.facade.get_future_horizons_analysis(run_id)
    if not forecast:
        raise ValueError(f"No horizons run found: {run_id}")

    raw = forecast.get("raw_output") or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    topic = forecast.get("topic") or raw.get("topic")
    generated_at = forecast.get("created_at") or raw.get("generated_at")
    db_scenarios = raw.get("scenarios") or []
    if not db_scenarios:
        raise ValueError(f"Forecast {run_id} has no scenarios")

    forecast_iso = _to_iso(generated_at)
    forecast_date = _parse_date(forecast_iso)
    deck_overlay = _load_deck_overlay(topic)

    # Resolve which article topics back this (possibly decoupled) tracked topic.
    # The Add-Topic wizard persists source_topics when the deck name differs from
    # the corpus tag (e.g. "Quantum Advantage" → ["Quantum Computing"]); the
    # post-forecast article window is pulled from those. Falls back to the deck
    # name so topics whose name matches the article tag are unaffected.
    _meta = db.facade.get_forecast_topic_metadata(topic) or {}
    _src = _meta.get("source_topics")
    eval_topics = _src if (isinstance(_src, list) and _src) else [topic]
    if eval_topics != [topic]:
        _emit(progress_callback, 1,
              f"Evaluating against source topics: {', '.join(eval_topics)}")

    # Granularity decision: deck-level scenarios collapse overlapping DB
    # scenarios (e.g. five separate H1 peer-review-breakdown scenarios in the
    # raw run all describe the same underlying system) into the 5 named
    # scenarios Wiley sees in the deck. The reranker margin gate then works
    # because the deck scenarios are well-separated.
    scenarios, scenario_level = build_original_scenarios(
        run_id, db_scenarios, deck_overlay, granularity=granularity, topic=topic,
    )

    # Addendum scenarios promoted by the user from prior "unanticipated
    # development" clusters. Appended after the original scenarios so they
    # take higher scenario_idx values and the original ordering is stable.
    user_scenarios = db.facade.get_forecast_user_scenarios(run_id)
    addendum_count = 0
    for us in user_scenarios:
        scenarios.append({
            "title": us.get("title"),
            "description": us.get("description"),
            "type": us.get("horizon_type"),
            "timeframe": us.get("timeframe"),
            "origin": "user_promoted",
            "user_scenario_id": us.get("id"),
            "source_surprise_label": us.get("source_surprise_label"),
            "created_at": us.get("created_at"),
        })
        addendum_count += 1

    # Scenario-status overlay (mark-as-done). We don't drop "done" scenarios
    # from the list — scenario_idx is positional and dropping would shift
    # later scenarios and break historical comparisons. Instead we tag each
    # scenario with _status so the reranker/LLM stages can skip it and Stage
    # E can emit a placeholder verdict row at the same index.
    statuses = db.facade.get_forecast_scenario_statuses(run_id)
    done_count = 0
    for i, sc in enumerate(scenarios):
        if sc.get("origin") == "user_promoted":
            st = statuses["addendums"].get(sc.get("user_scenario_id"))
        else:
            # Key first; fall back to the positional row only when this scenario
            # has no keyed row yet (rows written before fa_012).
            st = (statuses.get("by_key") or {}).get(sc.get("scenario_key"))
            if st is None:
                st = statuses["originals"].get(i)
        if st and st.get("status") == "done":
            sc["_status"] = "done"
            sc["_status_marked_at"] = st.get("marked_done_at")
            sc["_status_note"] = st.get("note")
            done_count += 1

    sibling_digest = _build_sibling_digest(scenarios)

    _emit(progress_callback, 2,
          f"Loaded forecast: {len(scenarios)} {scenario_level}-level scenarios "
          f"(from {len(db_scenarios)} raw, {addendum_count} user-promoted, "
          f"{done_count} marked done) for '{topic}'")

    # ── Stage A: fetch the post-forecast (or pre-forecast, in placebo mode)
    # article window. We use one query bounded by ``max_articles`` rather than
    # per-scenario ANN — when scenarios overlap (e.g., 13 peer-review
    # scenarios about the same system), per-scenario top-k dedupes to a
    # tiny pool. Letting the reranker do exclusive assignment on the full
    # window is both simpler and gives strictly better recall.
    pool = await _fetch_window_articles(
        eval_topics=eval_topics, forecast_iso=forecast_iso, mode=mode,
        limit=max_articles, window_weeks=window_weeks,
    )
    _emit(progress_callback, 18,
          f"Stage A: pulled {len(pool)} articles from "
          f"{'±' + str(window_weeks) + 'wk' if window_weeks else 'full'} window")
    if not pool:
        return await _persist_empty(
            db, run_id, topic, len(scenarios), mode, classify_model,
            started, max_articles, margin, note="No candidate articles found",
        )

    # ── Stage B + C: exclusive assignment via cross-encoder ───────────────
    from app.retrieval.reranker import assign_exclusive, is_enabled
    if not is_enabled():
        logger.warning(
            "Reranker disabled; forecast assessment quality will degrade. "
            "Set RERANK_ENABLED=true in this tenant's .env."
        )

    assignments = await assign_exclusive(
        scenarios=scenarios,
        articles=pool,
        margin=margin,
        scenario_text_fn=lambda s: _scenario_probe(s),
        article_text_fn=lambda a: _article_text(a),
    )
    _emit(progress_callback, 32, "Stage C: exclusive assignment complete")

    scenario_buckets: dict[int, list] = {i: [] for i in range(len(scenarios))}
    ambiguous: list = []
    for art, assign in zip(pool, assignments):
        assigned_idx = assign.get("scenario_idx")
        # If the reranker picked a "done" scenario, route the article to the
        # ambiguous bucket instead so it has a chance to surface as a
        # surprise cluster. Done scenarios get no Stage D classify spend.
        if (
            assigned_idx is not None
            and 0 <= assigned_idx < len(scenarios)
            and scenarios[assigned_idx].get("_status") == "done"
        ):
            ambiguous.append((art, assign))
            continue
        if (
            assigned_idx is not None
            and assign.get("score") is not None
            and assign["score"] >= STAGE_B_MIN_SCORE
        ):
            scenario_buckets[assigned_idx].append((art, assign))
        else:
            ambiguous.append((art, assign))

    assigned_total = sum(len(b) for b in scenario_buckets.values())
    _emit(progress_callback, 35,
          f"Bucketing: {assigned_total} assigned, {len(ambiguous)} ambiguous")

    # ── Stage D: LLM classify each (scenario, article) ────────────────────
    sem = asyncio.Semaphore(STAGE_D_CONCURRENCY)
    processed = {"n": 0}

    async def _classify_one(art, assign, s_idx):
        async with sem:
            scenario = scenarios[s_idx]
            verdict = await _classify_with_llm(
                model_name=classify_model,
                topic=topic,
                forecast_iso=forecast_iso,
                scenario=scenario,
                sibling_digest=sibling_digest,
                article=art,
            )
            processed["n"] += 1
            if processed["n"] % 5 == 0:
                pct = 35 + int(45 * processed["n"] / max(assigned_total, 1))
                _emit(progress_callback, min(pct, 80),
                      f"Stage D: classified {processed['n']}/{assigned_total}")
            return {
                "article_uri": art.get("uri") or art.get("id"),
                "scenario_idx": s_idx,
                "verdict": verdict.get("verdict", "neutral_context"),
                "evidence_type": verdict.get("evidence_type"),
                "confidence": float(verdict.get("confidence") or 0.0),
                "rerank_score": float(assign.get("score") or 0.0),
                "margin": float(assign.get("margin") or 0.0),
                "best_alt_scenario_idx": (
                    verdict.get("best_alt_scenario_idx")
                    if verdict.get("best_alt_scenario_idx") is not None
                    else assign.get("best_alt_scenario_idx")
                ),
                "rationale": verdict.get("rationale"),
                "article_date": (
                    art.get("submission_date")
                    or art.get("publication_date")
                ),
                "_article_title": art.get("title"),
            }

    tasks = []
    for s_idx, bucket in scenario_buckets.items():
        for art, assign in bucket:
            tasks.append(_classify_one(art, assign, s_idx))
    classified: list[dict] = await asyncio.gather(*tasks) if tasks else []

    _emit(progress_callback, 82, "Stage D complete")

    # ── Stage E: aggregate per-scenario verdicts ──────────────────────────
    elapsed_days = _elapsed_days(forecast_date)
    scenario_verdict_rows = []
    for s_idx, scenario in enumerate(scenarios):
        if scenario.get("_status") == "done":
            # Preserve scenario_idx density: emit a placeholder row so later
            # scenarios keep their stable positional index across runs.
            marked_at = scenario.get("_status_marked_at") or ""
            note = scenario.get("_status_note") or ""
            scenario_verdict_rows.append({
                "scenario_idx": s_idx,
                "horizon_type": scenario.get("type", "h1"),
                "scenario_title": scenario.get("title", ""),
                "deck_info": None,
                "verdict_label": "Done",
                "directional_rate": 0.0,
                "velocity": 0.0,
                "milestone_density": 0.0,
                "coverage": 0.0,
                "supports": 0,
                "contradicts": 0,
                "neutral": 0,
                "summary_md": (
                    f"Scenario marked done"
                    + (f" on {marked_at[:10]}" if marked_at else "")
                    + (f" — {note}" if note else "")
                ).strip(),
                "top_articles": {"supports": [], "contradicts": []},
                "user_scenario_id": scenario.get("user_scenario_id"),
                "scenario_key": scenario.get("scenario_key"),
            })
            continue
        verdicts = [c for c in classified if c["scenario_idx"] == s_idx]
        row = _aggregate_scenario(
            scenario=scenario,
            s_idx=s_idx,
            verdicts=verdicts,
            elapsed_days=elapsed_days,
            deck_overlay=deck_overlay,
        )
        # Record WHICH scenario this verdict is for. scenario_idx alone is just
        # a position in the originals+addendums list, so it shifts when a
        # promoted scenario is added or skipped, and the UI used to infer the
        # pairing by arithmetic. Exactly one of these is set.
        row["user_scenario_id"] = scenario.get("user_scenario_id")
        row["scenario_key"] = (
            None if scenario.get("origin") == "user_promoted"
            else scenario.get("scenario_key")
        )
        scenario_verdict_rows.append(row)
    _emit(progress_callback, 88, "Aggregated scenario verdicts")

    # ── Stage F: surprises ────────────────────────────────────────────────
    # _find_surprises runs HDBSCAN's clusterer.fit_predict synchronously —
    # CPU-bound on hundreds of embeddings and easily takes tens of seconds.
    # Pushing it to a worker thread keeps the event loop responsive while
    # the scheduled monitor / API caller waits.
    unrelated = [c for c in classified if c.get("verdict") == "unrelated"]
    surprises = await asyncio.to_thread(
        lambda: _find_surprises(
            pool=pool,
            ambiguous_pairs=ambiguous,
            unrelated_verdicts=unrelated,
            scenarios=scenarios,
        )
    )
    # Replace keyword-salad labels with LLM-generated names AND drop
    # clusters the labeler judges off-topic (e.g. "Ukraine robot force"
    # leaking into a Patent Cliffs assessment). Best-effort: on any
    # failure we keep the original keyword labels rather than blocking.
    surprises = await _label_clusters_with_llm(topic, surprises)
    _emit(progress_callback, 94, f"Found {len(surprises)} surprise clusters")

    # ── Persist ───────────────────────────────────────────────────────────
    assessment_id = str(uuid.uuid4())
    summary = {
        "topic": topic,
        "forecast_generated_at": forecast_iso,
        "assessed_at": datetime.utcnow().isoformat(),
        "elapsed_days": elapsed_days,
        "evidence_pool": len(pool),
        "assigned": assigned_total,
        "classified": len(classified),
        "ambiguous": len(ambiguous),
        "unrelated": len(unrelated),
        "scenario_level": scenario_level,
        "db_scenarios_count": len(db_scenarios),
        "window_weeks": window_weeks,
        "verdict_distribution": _count_labels(
            [r["verdict_label"] for r in scenario_verdict_rows]
        ),
        "deck_overlay_loaded": bool(deck_overlay),
    }

    # Strip helper fields before persisting article verdicts
    article_rows = [
        {k: v for k, v in c.items() if not k.startswith("_")}
        for c in classified
    ]

    db.facade.save_forecast_assessment(
        assessment_id=assessment_id,
        run_id=run_id,
        topic=topic,
        evidence_count=len(pool),
        scenarios_count=len(scenarios),
        ambiguous_count=len(ambiguous),
        unrelated_count=len(unrelated),
        surprises=surprises,
        summary=summary,
        mode=mode,
        model_used=classify_model,
        runtime_seconds=time.time() - started,
        config={
            "max_articles": max_articles,
            "stage_c_margin": margin,
            "stage_b_min_score": STAGE_B_MIN_SCORE,
            "stage_a_top_k": STAGE_A_TOP_K,
            "granularity_requested": granularity,
            "scenario_level_used": scenario_level,
            "window_weeks": window_weeks,
        },
    )
    db.facade.save_forecast_scenario_verdicts(assessment_id, scenario_verdict_rows)
    db.facade.save_forecast_article_verdicts(assessment_id, article_rows)

    _emit(progress_callback, 100, f"Assessment {assessment_id} complete")
    # Return the assessment we just created, not "the latest for the run".
    # get_latest_forecast_assessment prefers mode='live' so in paired mode it
    # would always return the live row even when the placebo just finished —
    # which would set live_id == placebo_id and break baseline correction.
    return _hydrate_assessment_by_id(db, assessment_id)


def _hydrate_assessment_by_id(db, assessment_id: str) -> dict:
    """Same shape as ``get_latest_forecast_assessment`` but keyed by the
    assessment's own id, so the caller never gets a stale 'latest' instead."""
    try:
        from app.database_models import (
            t_forecast_assessments,
            t_forecast_scenario_verdicts,
        )
        from sqlalchemy import select

        a_stmt = (
            select(t_forecast_assessments)
            .where(t_forecast_assessments.c.id == assessment_id)
        )
        row = db.facade._execute_with_rollback(a_stmt).fetchone()
        if not row:
            return {}
        assessment = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        for key in ("surprises", "summary", "config"):
            v = assessment.get(key)
            if isinstance(v, str):
                try:
                    assessment[key] = json.loads(v)
                except Exception:
                    pass
        v_stmt = (
            select(t_forecast_scenario_verdicts)
            .where(t_forecast_scenario_verdicts.c.assessment_id == assessment_id)
            .order_by(t_forecast_scenario_verdicts.c.scenario_idx.asc())
        )
        verdicts = []
        for vr in db.facade._execute_with_rollback(v_stmt).fetchall():
            vd = dict(vr._mapping) if hasattr(vr, "_mapping") else dict(vr)
            ta = vd.get("top_articles")
            if isinstance(ta, str):
                try:
                    vd["top_articles"] = json.loads(ta)
                except Exception:
                    pass
            verdicts.append(vd)
        assessment["scenario_verdicts"] = verdicts
        return assessment
    except Exception as e:
        logger.error(f"Error hydrating assessment {assessment_id}: {e}")
        return {}


# ── Stage A: window fetch ──────────────────────────────────────────────────

async def _fetch_window_articles(
    *,
    eval_topics: list,
    forecast_iso: str,
    mode: str,
    limit: int,
    window_weeks: Optional[int] = None,
) -> list[dict]:
    """Pull embedded articles for the topic in the live or placebo window.

    ``eval_topics`` is the list of article ``topic`` tags to draw from — the
    tracked topic's persisted ``source_topics`` when its deck name is
    decoupled from the corpus, else just ``[deck_name]``.

    When ``window_weeks`` is set, the window is bounded symmetrically:
        live    → [forecast_date, forecast_date + window_weeks weeks]
        placebo → [forecast_date - window_weeks weeks, forecast_date]
    so the two modes cover the same number of weeks. This is what makes the
    placebo a fair baseline — eliminates pool-size asymmetries from
    collection gaps or different elapsed durations.

    Bounded by ``limit`` — most recent first.
    """
    from app.database import get_database_instance
    from sqlalchemy import text
    from datetime import timedelta as _td

    db = get_database_instance()
    params: dict = {"topics": list(eval_topics), "cutoff": forecast_iso, "lim": limit}
    forecast_dt = _parse_date(forecast_iso)

    if mode == "placebo":
        # Pre-forecast: anchor at cutoff, optional lower bound.
        clauses = ["AND submission_date::timestamp < :cutoff"]
        if window_weeks and forecast_dt is not None:
            params["lower"] = (forecast_dt - _td(weeks=window_weeks)).isoformat()
            clauses.append("AND submission_date::timestamp >= :lower")
    else:
        # Live: anchor at cutoff, optional upper bound.
        clauses = ["AND submission_date::timestamp > :cutoff"]
        if window_weeks and forecast_dt is not None:
            params["upper"] = (forecast_dt + _td(weeks=window_weeks)).isoformat()
            clauses.append("AND submission_date::timestamp <= :upper")

    date_clause = "\n          ".join(clauses)
    sql = text(f"""
        SELECT uri, title, summary, submission_date, publication_date,
               news_source, sentiment, future_signal, time_to_impact
        FROM articles
        WHERE topic = ANY(:topics)
          AND embedding IS NOT NULL
          {date_clause}
        ORDER BY submission_date::timestamp DESC
        LIMIT :lim
    """)
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(sql, params).mappings().all()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return [dict(r) for r in rows]


async def _ann_search(
    probe: str,
    *,
    topic: str,
    forecast_iso: str,
    top_k: int,
    mode: str,
    max_articles: int,
) -> list[dict]:
    """Per-scenario ANN over articles in the post-forecast window (live mode)
    or pre-forecast window (placebo mode). Returns enriched article dicts."""
    from app.database import get_database_instance
    from app.vector_store_pgvector import _embed_texts
    from sqlalchemy import text

    db = get_database_instance()
    emb = _embed_texts([probe])[0]
    emb_str = "[" + ",".join(str(x) for x in emb) + "]"

    if mode == "placebo":
        date_clause = "AND submission_date::timestamp < :cutoff"
    else:
        date_clause = "AND submission_date::timestamp > :cutoff"

    sql = text(f"""
        SELECT uri, title, summary, submission_date, publication_date,
               news_source, sentiment, future_signal, time_to_impact,
               (embedding <=> CAST(:qv AS vector)) AS score
        FROM articles
        WHERE topic = :topic
          AND embedding IS NOT NULL
          {date_clause}
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :lim
    """)

    conn = db._temp_get_connection()
    try:
        rows = conn.execute(
            sql,
            {"qv": emb_str, "topic": topic, "cutoff": forecast_iso, "lim": top_k},
        ).mappings().all()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    out = []
    for r in rows:
        out.append({
            "uri": r["uri"],
            "title": r.get("title"),
            "summary": r.get("summary"),
            "submission_date": r.get("submission_date"),
            "publication_date": r.get("publication_date"),
            "news_source": r.get("news_source"),
            "sentiment": r.get("sentiment"),
            "future_signal": r.get("future_signal"),
            "time_to_impact": r.get("time_to_impact"),
            "cosine_distance": float(r.get("score") or 0.0),
        })
    return out


# ── Stage D: LLM classifier ────────────────────────────────────────────────

_PROMPT_CACHE: dict = {}


def _get_prompt() -> dict:
    if "p" not in _PROMPT_CACHE:
        from app.services.prompt_loader import PromptLoader
        _PROMPT_CACHE["p"] = PromptLoader.load_prompt("forecast_assessment", "current")
    return _PROMPT_CACHE["p"]


async def _classify_with_llm(
    *,
    model_name: str,
    topic: str,
    forecast_iso: str,
    scenario: dict,
    sibling_digest: str,
    article: dict,
) -> dict:
    from app.ai_models import get_ai_model
    from app.services.prompt_loader import PromptLoader

    prompt = _get_prompt()
    vars_ = {
        "topic": topic,
        "forecast_generated_at": forecast_iso[:10],
        "scenario_type": scenario.get("type", "h1"),
        "scenario_title": scenario.get("title", ""),
        "scenario_description": scenario.get("description", ""),
        "scenario_timeframe": scenario.get("timeframe", ""),
        "scenario_sentiment": scenario.get("sentiment", ""),
        "sibling_scenarios_digest": sibling_digest,
        "article_title": (article.get("title") or "")[:300],
        "article_date": (
            article.get("submission_date")
            or article.get("publication_date")
            or ""
        )[:10],
        "article_summary": (article.get("summary") or "")[:1500],
    }
    sys_prompt, user_prompt = PromptLoader.get_prompt_template(prompt, vars_)

    model = get_ai_model(model_name)
    if model is None:
        raise RuntimeError(f"AI model {model_name} not available")

    def _call_sync():
        return model.generate_response([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ])

    text_out = await asyncio.to_thread(_call_sync)
    return _parse_classifier_json(text_out)


def _parse_classifier_json(text_out: str) -> dict:
    """Tolerant JSON extraction. The classifier sometimes wraps JSON in ```.
    Falls back to a neutral verdict if parsing fails."""
    if not text_out:
        return _neutral_verdict("Empty model response")
    s = text_out.strip()
    # Strip code fences
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```\s*$", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    # Try direct
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Try first {...} blob
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return _neutral_verdict(f"Unparseable model response: {s[:120]}")


def _neutral_verdict(rationale: str) -> dict:
    return {
        "verdict": "neutral_context",
        "best_alt_scenario_idx": None,
        "evidence_type": "commentary",
        "confidence": 0.0,
        "rationale": rationale,
    }


# ── Stage E: aggregation ───────────────────────────────────────────────────

def _aggregate_scenario(
    *,
    scenario: dict,
    s_idx: int,
    verdicts: list[dict],
    elapsed_days: int,
    deck_overlay: dict,
) -> dict:
    """Produce a single forecast_scenario_verdicts row for one scenario."""
    confident = [
        v for v in verdicts
        if (v.get("confidence") or 0.0) >= MIN_CONF_FOR_VERDICT_PROMOTION
    ]
    n_total = len(confident)

    supports = sum(1 for v in confident if v["verdict"] == "supports_trajectory")
    state_only = sum(1 for v in confident if v["verdict"] == "supports_state_contradicts_trajectory")
    contradicts = sum(1 for v in confident if v["verdict"] == "contradicts")
    better_other = sum(1 for v in confident if v["verdict"] == "better_fits_other_scenario")
    neutral = sum(1 for v in confident if v["verdict"] == "neutral_context")
    unrelated = sum(1 for v in confident if v["verdict"] == "unrelated")

    # Effective contradiction includes "supports_state_contradicts_trajectory"
    eff_contra = contradicts + state_only
    denom = supports + eff_contra
    directional_rate = ((supports - eff_contra) / denom) if denom > 0 else 0.0

    # Milestone density
    milestone_hits = sum(
        1 for v in confident
        if v.get("evidence_type") in ("milestone", "leading_indicator")
        and v["verdict"] in ("supports_trajectory", "contradicts")
    )
    milestone_density = (milestone_hits / n_total) if n_total > 0 else 0.0

    # Velocity: net supports per month over elapsed window
    months_elapsed = max(elapsed_days / 30.0, 0.5)
    velocity = (supports - eff_contra) / months_elapsed

    # Expected-elapsed coverage (rough): we don't have per-scenario priors yet,
    # so anchor to: a healthy on-track scenario should produce ≥ ~3 supporting
    # events per month. coverage = observed_supports / expected_supports.
    expected_supports = 3.0 * months_elapsed
    coverage = (supports / expected_supports) if expected_supports > 0 else 0.0

    # Verdict label
    label = _decide_verdict_label(
        n_confident=n_total,
        directional_rate=directional_rate,
        velocity=velocity,
        milestone_density=milestone_density,
        coverage=coverage,
        state_only=state_only,
        supports=supports,
    )

    # Top supporting + top contradicting article snippets (for UI)
    def _rank_key(v):
        return ((v.get("confidence") or 0) * (v.get("rerank_score") or 0))

    top_supports = sorted(
        [v for v in confident if v["verdict"] == "supports_trajectory"],
        key=_rank_key, reverse=True,
    )[:3]
    top_contras = sorted(
        [v for v in confident if v["verdict"] in ("contradicts", "supports_state_contradicts_trajectory")],
        key=_rank_key, reverse=True,
    )[:2]

    def _snippet(v):
        return {
            "article_uri": v.get("article_uri"),
            "title": v.get("_article_title"),
            "verdict": v.get("verdict"),
            "evidence_type": v.get("evidence_type"),
            "confidence": v.get("confidence"),
            "rationale": v.get("rationale"),
            "article_date": v.get("article_date"),
        }

    top_articles = {
        "supports": [_snippet(v) for v in top_supports],
        "contradicts": [_snippet(v) for v in top_contras],
    }

    # Optional deck-overlay enrichment.
    # In deck-granularity mode the scenario already carries _deck_meta/_deck_key
    # directly. In DB-granularity mode we resolve through the overlay's
    # scenario_title_to_deck_key mapping.
    deck_key = scenario.get("_deck_key") or (
        (deck_overlay or {}).get("scenario_title_to_deck_key", {})
                            .get(scenario.get("title"))
    )
    deck_meta = scenario.get("_deck_meta") or (
        (deck_overlay or {}).get("deck_scenarios", {}).get(deck_key)
        if deck_key else None
    )

    summary_md = _summary_md(
        scenario=scenario,
        label=label,
        n_confident=n_total,
        supports=supports,
        eff_contra=eff_contra,
        milestone_hits=milestone_hits,
        deck_meta=deck_meta,
    )

    # Surface deck info to the UI; include the original DB titles when grouped
    deck_info = None
    if deck_meta:
        deck_info = {
            "deck_key": deck_key,
            "deck_scenario_name": deck_meta.get("deck_scenario_name"),
            "consensus_pct": deck_meta.get("consensus_pct"),
            "primary_signal": deck_meta.get("primary_signal"),
            "minority_view": deck_meta.get("minority_view"),
            "decision_fork": deck_meta.get("decision_fork"),
            "action_windows": deck_meta.get("action_windows"),
            "constituent_db_titles": scenario.get("_db_scenario_titles") or [],
        }

    # Current consensus % among confident verdicts (recomputed each
    # assessment). The Wiley bundle shows this next to the original deck
    # consensus_pct so the reader can see quarter-over-quarter drift.
    current_consensus_pct = (
        round(100.0 * supports / n_total, 1) if n_total > 0 else None
    )

    return {
        "scenario_idx": s_idx,
        "horizon_type": scenario.get("type", "h1"),
        "scenario_title": scenario.get("title", ""),
        "deck_info": deck_info,
        "verdict_label": label,
        "directional_rate": round(directional_rate, 3),
        "velocity": round(velocity, 3),
        "milestone_density": round(milestone_density, 3),
        "coverage": round(coverage, 3),
        "supports": supports,
        "contradicts": contradicts,
        "neutral": neutral + unrelated + better_other,
        "summary_md": summary_md,
        "top_articles": top_articles,
        "current_consensus_pct": current_consensus_pct,
    }


def _decide_verdict_label(
    *,
    n_confident: int,
    directional_rate: float,
    velocity: float,
    milestone_density: float,
    coverage: float,
    state_only: int,
    supports: int,
) -> str:
    if n_confident < INCONCLUSIVE_MIN_ARTICLES:
        return "Inconclusive"

    # Off-track first — strong evidence against the trajectory wins
    if directional_rate < DIRECTIONAL_RATE_OFFTRACK:
        return "Off-track"
    if state_only >= 3 and state_only > supports:
        return "Off-track"

    # Accelerating requires milestones — guards against generic-commentary inflation
    if velocity > 0 and milestone_density > 0.15 and coverage > 1.0:
        return "Accelerating"

    if directional_rate > DIRECTIONAL_RATE_ONTRACK and velocity >= 0:
        return "On-track"

    if abs(directional_rate) <= 0.1 and abs(velocity) <= 1.0:
        return "Stalled"

    return "Inconclusive"


def _summary_md(*, scenario, label, n_confident, supports, eff_contra, milestone_hits, deck_meta) -> str:
    title = scenario.get("title", "")
    h = scenario.get("type", "h1").upper()
    lines = [
        f"**Verdict: {label}** — H{h[-1]}: _{title}_",
        f"Based on {n_confident} confident article verdicts: "
        f"{supports} supporting, {eff_contra} contradicting trajectory, "
        f"{milestone_hits} concrete milestones / leading indicators.",
    ]
    if deck_meta:
        lines.append(
            f"Maps to deck scenario **{deck_meta.get('deck_scenario_name')}** "
            f"({deck_meta.get('consensus_pct')}% original consensus)."
        )
    return "\n\n".join(lines)


# ── Stage F: surprises ─────────────────────────────────────────────────────

def _find_surprises(
    *,
    pool: list[dict],
    ambiguous_pairs: list,
    unrelated_verdicts: list,
    scenarios: list,
) -> list[dict]:
    """Identify clusters of articles that no scenario explains.

    We attempt HDBSCAN clustering on article embeddings if scikit-learn /
    hdbscan are available; otherwise fall back to a simpler "top N most
    ambiguous" grouping with a TF-IDF top-terms label. This keeps the feature
    working in dev environments that don't have the optional deps.
    """
    unrelated_uris = {v["article_uri"] for v in unrelated_verdicts}
    ambiguous_uris = {(a.get("uri") or a.get("id")) for a, _ in ambiguous_pairs}
    residual_uris = unrelated_uris | ambiguous_uris
    if not residual_uris:
        return []

    residual_articles = [a for a in pool if (a.get("uri") or a.get("id")) in residual_uris]
    if len(residual_articles) < 8:
        return []

    # Try HDBSCAN + light keyword labelling
    try:
        return _cluster_with_hdbscan(residual_articles)
    except Exception as e:
        logger.info(f"HDBSCAN not available, using keyword fallback: {e}")
        return _cluster_keyword_fallback(residual_articles)


def _cluster_with_hdbscan(articles: list[dict]) -> list[dict]:
    import numpy as np
    from sqlalchemy import text
    from app.database import get_database_instance

    db = get_database_instance()
    uris = [a.get("uri") or a.get("id") for a in articles]
    placeholders = ",".join([f":u{i}" for i in range(len(uris))])
    params = {f"u{i}": u for i, u in enumerate(uris)}
    sql = text(f"SELECT uri, embedding FROM articles WHERE uri IN ({placeholders}) AND embedding IS NOT NULL")
    conn = db._temp_get_connection()
    try:
        rows = conn.execute(sql, params).mappings().all()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not rows:
        return _cluster_keyword_fallback(articles)

    by_uri = {a.get("uri") or a.get("id"): a for a in articles}
    vectors, kept_uris = [], []
    for r in rows:
        emb = r.get("embedding")
        if emb is None:
            continue
        if isinstance(emb, str):
            # pgvector text format: "[0.1,0.2,...]"
            try:
                emb = [float(x) for x in emb.strip("[]").split(",")]
            except Exception:
                continue
        vectors.append(emb)
        kept_uris.append(r["uri"])

    if len(vectors) < 8:
        return _cluster_keyword_fallback(articles)

    X = np.array(vectors)
    try:
        import hdbscan  # type: ignore
        clusterer = hdbscan.HDBSCAN(min_cluster_size=5, metric="euclidean")
        labels = clusterer.fit_predict(X)
    except ImportError:
        from sklearn.cluster import DBSCAN  # type: ignore
        clusterer = DBSCAN(eps=0.35, min_samples=5, metric="cosine")
        labels = clusterer.fit_predict(X)

    clusters: dict[int, list] = {}
    for uri, lab in zip(kept_uris, labels):
        if lab == -1:
            continue
        clusters.setdefault(int(lab), []).append(uri)

    out = []
    for lab, uri_list in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(uri_list) < 5:
            continue
        cluster_articles = [by_uri[u] for u in uri_list if u in by_uri]
        out.append({
            "size": len(cluster_articles),
            # Rows minus syndicated repeats. A theme whose rows are one story
            # republished by 13 local papers is not a 14-article theme.
            "distinct_stories": _distinct_stories(cluster_articles),
            "label": _keyword_label([a.get("title", "") for a in cluster_articles]),
            "sample_articles": _dedupe_samples(cluster_articles),
        })
    # Rank by distinct stories so a single wire story cannot outrank a theme
    # that genuinely has several independent ones.
    out.sort(key=lambda c: (-(c.get("distinct_stories") or 0), -(c.get("size") or 0)))
    return out


async def _label_clusters_with_llm(topic: str, clusters: list[dict]) -> list[dict]:
    """Replace keyword-salad cluster labels with LLM-named ones and drop
    clusters the labeler judges off-topic.

    Mutates each cluster in-place to set ``label`` to the LLM's name and
    record the original keyword label as ``keyword_label`` for audit.
    Drops clusters where ``topic_relevance`` is false.

    Best-effort: any per-cluster failure leaves that cluster's original
    keyword label intact rather than blocking the assessment.
    """
    if not clusters:
        return clusters

    try:
        from app.services.wiley_bundle_supervisor import _call_agent  # async LLM caller
    except Exception as e:
        logger.warning("Cluster labeler unavailable (%s); keeping keyword labels", e)
        return clusters

    out: list[dict] = []
    for c in clusters:
        original = c.get("label") or ""
        titles = [s.get("title") for s in (c.get("sample_articles") or []) if s.get("title")]
        if not titles:
            out.append(c)
            continue
        try:
            resp = await _call_agent("forecast_cluster_label_agent", {
                "topic": topic,
                "fallback_label": original,
                "article_titles": titles,
            })
        except Exception as e:
            logger.warning("Cluster labeler call failed for '%s': %s — keeping keyword label", original, e)
            out.append(c)
            continue

        if not resp or not resp.get("name"):
            out.append(c)
            continue

        if resp.get("topic_relevance") is False:
            logger.info(
                "Dropping off-topic cluster '%s' (LLM name='%s', size=%d): %s",
                original, resp.get("name"), c.get("size", 0), resp.get("rationale") or "",
            )
            continue

        # Keep the keyword label as audit trail
        c["keyword_label"] = original
        c["label"] = resp["name"]
        if resp.get("rationale"):
            c["label_rationale"] = resp["rationale"]

        # Prune individual off-topic sample articles the LLM flagged inside
        # a kept cluster (e.g. the Ukraine robot-war article in an otherwise
        # pharma cluster). Indices are into the article_titles list we sent.
        off_topic = resp.get("off_topic_article_indices") or []
        if isinstance(off_topic, list) and off_topic:
            try:
                drop = {int(i) for i in off_topic if isinstance(i, (int, float))}
                samples = c.get("sample_articles") or []
                kept_samples = [s for i, s in enumerate(samples) if i not in drop]
                if kept_samples:
                    c["pruned_article_count"] = len(samples) - len(kept_samples)
                    c["sample_articles"] = kept_samples
                    # Reflect the prune in the cluster size so the UI doesn't
                    # claim "N articles" while showing fewer.
                    if isinstance(c.get("size"), int):
                        c["size"] = max(0, c["size"] - c["pruned_article_count"])
            except Exception as e:
                logger.warning("Failed to apply off-topic prune for cluster '%s': %s", original, e)
        out.append(c)
    return out


def _story_key(title: str) -> str:
    """Normalised headline, for collapsing syndicated copies of one story.

    Wire and Conversation pieces get republished verbatim by dozens of local
    outlets under the same headline and different URLs, so they are distinct
    rows but a single story. Counting the rows made a one-article theme look
    like a fourteen-article one and filled the sample list with the same
    headline five times.
    """
    import re as _re
    t = (title or "").strip().lower()
    t = _re.sub(r"[‘’“”'\"]", "", t)
    t = _re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())[:120]


def _dedupe_samples(articles: list[dict], limit: int = 5) -> list[dict]:
    """Up to ``limit`` sample articles, one per distinct story."""
    seen: set = set()
    out: list[dict] = []
    for a in articles:
        key = _story_key(a.get("title") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append({"uri": a.get("uri") or a.get("id"),
                    "title": a.get("title"),
                    "date": a.get("submission_date") or a.get("publication_date")})
        if len(out) >= limit:
            break
    return out


def _distinct_stories(articles: list[dict]) -> int:
    """Distinct headlines in a cluster, ignoring syndicated repeats."""
    return len({_story_key(a.get("title") or "") for a in articles if a.get("title")})


def _cluster_keyword_fallback(articles: list[dict]) -> list[dict]:
    """No-cluster fallback: just label the residual as one bucket."""
    return [{
        "size": len(articles),
        "distinct_stories": _distinct_stories(articles),
        "label": _keyword_label([a.get("title", "") for a in articles]),
        "sample_articles": _dedupe_samples(articles),
        "note": "Unclustered residual — install hdbscan or scikit-learn for clustering",
    }]


def _keyword_label(titles: list[str]) -> str:
    """Cheap top-3 token labelling, stopword-filtered."""
    stop = {
        "the", "and", "for", "with", "from", "into", "amid", "over", "this",
        "that", "after", "before", "about", "their", "what", "have", "been",
        "could", "would", "should", "more", "than", "they", "them", "will",
        "are", "was", "but", "his", "her", "its", "out", "new", "how", "why",
        "who", "you", "your", "our", "all", "any", "can", "not", "one",
        "two", "three", "now", "still", "yet", "say", "says", "said", "may",
        "must", "make", "made", "year", "years", "amid", "without",
    }
    counts: dict[str, int] = {}
    for t in titles:
        if not t:
            continue
        for w in re.findall(r"[A-Za-z][A-Za-z\-]+", t.lower()):
            if len(w) < 4 or w in stop:
                continue
            counts[w] = counts.get(w, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    if not top:
        return "Unlabelled cluster"
    return ", ".join(w for w, _ in top)


# ── Helpers ────────────────────────────────────────────────────────────────

def _scenario_probe(scenario: dict) -> str:
    return (
        f"{scenario.get('title','')}. "
        f"{scenario.get('description','')} "
        f"Timeframe: {scenario.get('timeframe','')}."
    )


def _article_text(article: dict) -> str:
    parts = [article.get("title") or "", article.get("summary") or ""]
    return ". ".join(p for p in parts if p).strip()[:4000]


def _build_sibling_digest(scenarios: list[dict]) -> str:
    lines = []
    for i, s in enumerate(scenarios):
        lines.append(f"{i}: [{s.get('type','?')}] {s.get('title','')}")
    return "\n".join(lines)


def _load_deck_overlay(topic: str) -> dict:
    """Scan the overlay directory for a JSON whose ``topic`` matches.

    Each overlay file declares its own ``topic`` field; we don't rely on
    filenames so adding a new topic only needs dropping the file in place.
    """
    if not DECK_OVERLAY_DIR.exists():
        return {}
    for path in sorted(DECK_OVERLAY_DIR.glob("*_deck_overlay.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("topic") == topic:
            return data
    return {}


def source_topic_for_display_name(display_name: str) -> Optional[str]:
    """Reverse of the deck overlay's ``display_name`` — the real DB topic.

    Exports that stored a post-overlay name ("Scientific Publishing") cannot
    look it up in ``articles`` / ``future_horizons_runs`` / ``forecast_assessments``,
    which hold the source name ("Scientific Publishers - General Monitoring").
    Returns None when the string is not a display name, so callers can tell
    "no mapping" from "maps to itself".
    """
    if not display_name or not DECK_OVERLAY_DIR.exists():
        return None
    for path in sorted(DECK_OVERLAY_DIR.glob("*_deck_overlay.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("display_name") == display_name and data.get("topic"):
            return data["topic"]
    return None


def _build_deck_scenarios(db_scenarios: list[dict], overlay: dict) -> list[dict]:
    """Collapse the N raw DB scenarios into the M named deck scenarios via
    the overlay's ``scenario_title_to_deck_key`` mapping. Each deck scenario
    gets a synthesized description that fuses its primary_signal with the
    descriptions of all DB scenarios mapped to it — so the reranker has the
    full evidence to score against."""
    title_to_key = overlay.get("scenario_title_to_deck_key") or {}
    deck_scenarios = overlay.get("deck_scenarios") or {}

    # Group DB scenarios by their deck key, preserving overlay's order.
    grouped: dict[str, list[dict]] = {k: [] for k in deck_scenarios.keys()}
    for s in db_scenarios:
        key = title_to_key.get(s.get("title"))
        if key and key in grouped:
            grouped[key].append(s)

    result: list[dict] = []
    for key, meta in deck_scenarios.items():
        members = grouped.get(key, [])
        if not members:
            continue

        # Horizon: take the first member's type if overlay's horizon is
        # combined (e.g. "h1_h3"); the overlay's horizon is for display only.
        horizon = members[0].get("type", "h1")
        # Timeframe: widest range across members.
        timeframes = [m.get("timeframe") for m in members if m.get("timeframe")]
        timeframe = timeframes[0] if timeframes else "2025-2040"

        primary_signal = meta.get("primary_signal", "")
        merged_desc_parts = [primary_signal] if primary_signal else []
        for m in members:
            if m.get("description"):
                merged_desc_parts.append(m["description"])

        result.append({
            "type": horizon,
            "title": meta.get("deck_scenario_name", key),
            "description": " ".join(merged_desc_parts)[:4000],
            "timeframe": timeframe,
            "sentiment": members[0].get("sentiment", ""),
            # Provenance — preserved for downstream display + debugging
            "_deck_key": key,
            "_deck_meta": meta,
            "_db_scenario_titles": [m.get("title") for m in members],
        })
    return result


def _to_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_date(iso_str: str) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(iso_str[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _elapsed_days(forecast_date: Optional[datetime]) -> int:
    if forecast_date is None:
        return 90
    today = datetime.utcnow().date()
    fd = forecast_date.date() if hasattr(forecast_date, "date") else forecast_date
    return max((today - fd).days, 1)


def _count_labels(labels: list[str]) -> dict:
    out: dict[str, int] = {}
    for l in labels:
        out[l] = out.get(l, 0) + 1
    return out


def _emit(cb, pct, msg):
    if cb is not None:
        try:
            cb(pct, msg)
        except Exception:
            logger.debug("progress_callback raised", exc_info=True)


def apply_baseline_correction(
    *,
    live_assessment_id: str,
    placebo_assessment_id: str,
) -> dict:
    """Compute per-scenario baseline-corrected support rates and patch the
    live assessment's summary with the result.

    For each scenario:
        live_rate    = supports / pool_size  (post-forecast)
        placebo_rate = supports / pool_size  (pre-forecast, same N weeks)
        net_rate     = live_rate − placebo_rate

    Positive net_rate ⇒ the forecast trajectory accelerated after the
    forecast was made (beyond the baseline rate observed before it).
    Near-zero or negative net_rate ⇒ the article-level signal is no stronger
    than it was before the forecast existed — either the forecast was a
    pure trend extrapolation, or the classifier is responding to topical
    overlap rather than incremental evidence.

    Returns a dict of {scenario_idx: {live_rate, placebo_rate, net_rate, label}}.
    """
    from sqlalchemy import select, update, text
    from app.database import get_database_instance
    from app.database_models import (
        t_forecast_assessments,
        t_forecast_scenario_verdicts,
    )

    db = get_database_instance()
    facade = db.facade

    live = facade.get_latest_forecast_assessment_by_id(live_assessment_id) \
        if hasattr(facade, "get_latest_forecast_assessment_by_id") \
        else _load_assessment_by_id(live_assessment_id)
    placebo = _load_assessment_by_id(placebo_assessment_id)
    if not live or not placebo:
        return {}

    live_pool = max(int(live.get("evidence_count") or 0), 1)
    placebo_pool = max(int(placebo.get("evidence_count") or 0), 1)

    placebo_by_idx = {v["scenario_idx"]: v for v in placebo.get("scenario_verdicts", [])}

    per_scenario: dict = {}
    for lv in live.get("scenario_verdicts", []):
        idx = lv["scenario_idx"]
        pv = placebo_by_idx.get(idx) or {}
        live_rate = (lv.get("supports") or 0) / live_pool
        placebo_rate = (pv.get("supports") or 0) / placebo_pool
        net_rate = live_rate - placebo_rate
        if net_rate > 0.005:
            label = "Above baseline"
        elif net_rate < -0.005:
            label = "Below baseline"
        else:
            label = "At baseline"
        per_scenario[idx] = {
            "live_supports": lv.get("supports") or 0,
            "placebo_supports": pv.get("supports") or 0,
            "live_pool": live_pool,
            "placebo_pool": placebo_pool,
            "live_rate": round(live_rate, 5),
            "placebo_rate": round(placebo_rate, 5),
            "net_rate": round(net_rate, 5),
            "label": label,
        }

    # Patch live assessment summary with the correction block + cross-link.
    correction = {
        "method": "live_rate − placebo_rate (pool-normalised supports)",
        "live_assessment_id": live_assessment_id,
        "placebo_assessment_id": placebo_assessment_id,
        "live_pool": live_pool,
        "placebo_pool": placebo_pool,
        "per_scenario": per_scenario,
    }

    # Read-modify-write the summary JSONB; SQLAlchemy update with json.dumps.
    import json as _json
    conn = db._temp_get_connection()
    try:
        row = conn.execute(
            select(t_forecast_assessments.c.summary).where(
                t_forecast_assessments.c.id == live_assessment_id
            )
        ).fetchone()
        summary = {}
        if row and row[0]:
            v = row[0]
            summary = _json.loads(v) if isinstance(v, str) else dict(v)
        summary["baseline_correction"] = correction
        conn.execute(
            update(t_forecast_assessments)
            .where(t_forecast_assessments.c.id == live_assessment_id)
            .values(summary=_json.dumps(summary))
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return correction


def _load_assessment_by_id(assessment_id: str) -> dict:
    """Direct loader by primary key (the facade's get_latest is keyed on run_id)."""
    import json as _json
    from sqlalchemy import select
    from app.database import get_database_instance
    from app.database_models import (
        t_forecast_assessments,
        t_forecast_scenario_verdicts,
    )

    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        row = conn.execute(
            select(t_forecast_assessments).where(
                t_forecast_assessments.c.id == assessment_id
            )
        ).mappings().fetchone()
        if not row:
            return {}
        out = dict(row)
        for k in ("surprises", "summary", "config"):
            if isinstance(out.get(k), str):
                try:
                    out[k] = _json.loads(out[k])
                except Exception:
                    pass
        v_rows = conn.execute(
            select(t_forecast_scenario_verdicts).where(
                t_forecast_scenario_verdicts.c.assessment_id == assessment_id
            ).order_by(t_forecast_scenario_verdicts.c.scenario_idx.asc())
        ).mappings().all()
        out["scenario_verdicts"] = [dict(r) for r in v_rows]
        return out
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def _persist_empty(
    db, run_id, topic, n_scenarios, mode, classify_model, started,
    max_articles, margin, note,
) -> dict:
    aid = str(uuid.uuid4())
    db.facade.save_forecast_assessment(
        assessment_id=aid,
        run_id=run_id,
        topic=topic,
        evidence_count=0,
        scenarios_count=n_scenarios,
        ambiguous_count=0,
        unrelated_count=0,
        surprises=[],
        summary={"note": note, "topic": topic},
        mode=mode,
        model_used=classify_model,
        runtime_seconds=time.time() - started,
        config={"max_articles": max_articles, "stage_c_margin": margin},
    )
    return db.facade.get_latest_forecast_assessment(run_id)
