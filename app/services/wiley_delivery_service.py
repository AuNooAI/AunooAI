"""Recurring Wiley forecast-tracker delivery service.

Two cadences:

* ``monthly``  — per-topic updates for every topic flagged ``cadence='monthly'``
                 in ``forecast_topic_delivery``. Bundles them into one deck.
* ``quarterly`` — bundle of every topic flagged ``cadence='quarterly'`` (the
                  Wiley core topics, defaulting to the deck-overlay set).

Two entry points:

* :func:`generate_bundle` — builds the PPTX and returns ``(bytes, period_label,
  included_topics)``. Used by the on-demand "Download bundle" button + the
  scheduler.
* :func:`deliver_bundle` — generates + emails to each topic's configured
  recipient + bumps ``last_delivered_at``.

The scheduler call lives in :mod:`app.tasks.forecast_tracker_monitor`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _period_label(cadence: str, when: Optional[datetime] = None) -> str:
    when = when or datetime.now(timezone.utc)
    if cadence == "monthly":
        return when.strftime("%B %Y")
    if cadence == "quarterly":
        q = (when.month - 1) // 3 + 1
        return f"Q{q} {when.year}"
    if cadence == "all":
        return f"All topics · {when.strftime('%Y-%m-%d')}"
    return when.strftime("%Y-%m-%d")


def _resolve_items(cadence: str, *, updates_only: bool) -> list:
    """Return the list of ``(assessment, forecast_run, prior_assessment)`` triples
    for every topic in scope.

    ``cadence`` values:
        * ``monthly`` / ``quarterly`` — topics configured for that cadence in
          ``forecast_topic_delivery``.
        * ``all`` — every distinct topic with at least one stored live
          assessment. Used by the "All topics" view in the UI so the user
          can grab a bundle covering everything without first configuring a
          cadence per topic.
    """
    from app.database import get_database_instance

    db = get_database_instance()

    if cadence == "all":
        # Every distinct topic that has a stored assessment.
        topics = _all_topics_with_assessments(db)
    else:
        configs = db.facade.get_forecast_topic_delivery_configs()
        topics = [c["topic"] for c in configs
                  if (c.get("cadence") or "").lower() == cadence]

    items = []
    for topic in topics:
        assessment = db.facade.get_latest_forecast_assessment_by_topic(topic)
        if not assessment:
            logger.info("Wiley delivery: skipping %s — no assessment yet", topic)
            continue
        forecast_run = db.facade.get_future_horizons_analysis(assessment.get("run_id"))
        prior = None
        if updates_only:
            # Look up the prior by TOPIC, not run_id — every horizons re-run
            # produces a fresh run_id, so a run_id-keyed lookup would treat
            # each new horizons run as a clean slate and surface the "first
            # assessment, nothing to compare" stub for every topic.
            prior = db.facade.get_prior_live_assessment(
                run_id=assessment.get("run_id"),
                before_assessed_at=assessment.get("assessed_at"),
                topic=topic,
            )
        items.append((assessment, forecast_run or {}, prior or None))
    return items


def _apply_overlay_display_names(items: list) -> list:
    """For each bundle item, consult the topic's deck overlay JSON and rewrite
    ``assessment['topic']`` in-place to the overlay's ``display_name`` when one
    is set. The DB row is untouched — this is a presentation-layer relabel
    used by every downstream slide builder (which all read ``assessment.topic``).
    """
    from app.services.forecast_assessment_service import _load_deck_overlay

    out = []
    for assessment, run, prior in items:
        original_topic = assessment.get("topic") or ""
        if not original_topic:
            out.append((assessment, run, prior))
            continue
        overlay = _load_deck_overlay(original_topic)
        display_name = (overlay or {}).get("display_name")
        if display_name and display_name != original_topic:
            # Mutate a shallow copy so the cached assessment object in the
            # caller (if any) isn't polluted.
            a = dict(assessment)
            a["topic"] = display_name
            # Mirror on summary so consensus drift line / exec summary etc.
            # also see the friendly name where they pull from there.
            summary = dict(a.get("summary") or {})
            if summary.get("topic") == original_topic:
                summary["topic"] = display_name
            a["summary"] = summary
            # Mirror on prior assessment too for diff calculations
            if prior:
                p = dict(prior)
                if p.get("topic") == original_topic:
                    p["topic"] = display_name
                prior = p
            assessment = a
        out.append((assessment, run, prior))
    return out


def _all_topics_with_assessments(db) -> list:
    """Distinct topics that have ever produced a live forecast assessment."""
    from app.database_models import t_forecast_assessments
    from sqlalchemy import select, distinct

    stmt = (
        select(distinct(t_forecast_assessments.c.topic))
        .where(t_forecast_assessments.c.mode == "live")
        .where(t_forecast_assessments.c.status == "completed")
        .order_by(t_forecast_assessments.c.topic.asc())
    )
    try:
        rows = db.facade._execute_with_rollback(stmt).fetchall()
        return [r[0] for r in rows if r and r[0]]
    except Exception as e:
        logger.error("Failed to list all assessment topics: %s", e)
        return []


async def _run_synthesis_pipeline(
    cadence: str,
    *,
    updates_only: bool,
    when: Optional[datetime],
    progress_callback,
) -> Tuple[list, str, dict, dict, Optional[str], list]:
    """Resolve items + run the supervisor pipeline once.

    Returns ``(items, period_label, bundle_synth, eos_per_topic, verdict,
    review_findings)``. Both the PPTX and MD export paths consume this output
    so the heavy LLM work isn't duplicated.
    """
    from app.services.wiley_bundle_supervisor import run_pipeline
    from app.database import get_database_instance

    items = _resolve_items(cadence, updates_only=updates_only)
    if not items:
        raise ValueError(
            f"No topics configured for cadence='{cadence}'. "
            "Set per-topic cadence in the Forecast Tracker UI first."
        )

    # If a topic's deck overlay supplies a ``display_name``, override the
    # assessment's topic string in-memory so all downstream renderers see
    # the friendly name. The DB row keeps the long name (article collection
    # depends on it) — purely display-layer.
    items = _apply_overlay_display_names(items)

    period_label = _period_label(cadence, when)
    db = get_database_instance()

    try:
        db.facade.upsert_forecast_bundle_review(cadence, period_label, status="under_review")
    except Exception:
        pass

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as e:
                logger.warning("progress_callback failed: %s", e)

    _emit(2, "Resolving topics and assessments")
    _emit(5, "Generating Black Swan & Wild Card scenarios per topic")
    eos_per_topic = await _ensure_eos_for_bundle(items)
    _emit(20, f"EOS scans complete for {len(eos_per_topic)} topics")

    SUPERVISOR_START = 20
    SUPERVISOR_END = 95
    final_payload = None
    verdict = None

    STAGE_LABELS = {
        "supervisor": "Supervisor planning",
        "briefing": "Drafting per-topic Briefing Synthesis",
        "recommendations": "Drafting Strategic Recommendations",
        "next_steps": "Drafting Next Steps",
        "cross_topic": "Synthesising cross-topic themes",
        "exec_summary": "Writing Executive Summary letter",
        "expert_commentary": "Drafting expert view on emerging themes",
        "humanize": "Stripping AI-slop tells from the prose",
        "reviewer": "LLM-as-judge reviewing all artefacts",
    }
    async for update in run_pipeline(items, cadence=cadence, period_label=period_label,
                                     eos_per_topic=eos_per_topic):
        stage = update.get("stage") or ""
        status = update.get("status") or ""
        sub_progress = float(update.get("progress") or 0)
        mapped_pct = SUPERVISOR_START + int((SUPERVISOR_END - SUPERVISOR_START) * sub_progress)
        label = STAGE_LABELS.get(stage, stage)
        if status == "started":
            _emit(mapped_pct, f"{label}…")
        elif status == "completed":
            _emit(mapped_pct, f"{label} — done")
        elif status == "skipped_already_approved":
            _emit(mapped_pct, "Reviewer skipped (period already approved)")
        if update.get("stage") == "complete":
            verdict = update.get("status")
            final_payload = update.get("payload") or {}
            _emit(95, f"Pipeline finished — verdict: {verdict}")

    bundle_synth = (final_payload or {}).get("bundle_payload") or {}
    review_findings = (final_payload or {}).get("findings") or []
    return items, period_label, bundle_synth, eos_per_topic, verdict, review_findings


def _data_quality_note() -> Optional[str]:
    """Read data/wiley_horizons/collection_gap.json (written by
    detect_collection_gap.py) and render the deck's collection-gap caveat.
    Returns None when there's no detected gap."""
    import json
    import os
    path = os.path.join("data", "wiley_horizons", "collection_gap.json")
    try:
        with open(path) as f:
            g = json.load(f)
    except Exception:
        return None
    if not g.get("detected"):
        return None
    outage = ("a collection-pipeline interruption" if g.get("likely_pipeline_outage")
              else "reduced source coverage")
    return (
        f"Data note: {outage} between {g.get('start')} and {g.get('end')} "
        f"({g.get('days')} days) reduced article volume for this period. "
        "API-based sources (ArXiv, Semantic Scholar, news APIs) are backfilled "
        "where the provider window still allows; RSS-only items from that span "
        "are not recoverable. Findings for that window are correspondingly thinner."
    )


def _events_by_topic(cadence: str, period_label: str) -> dict:
    """Group this period's deck-included extracted events by topic, for the
    per-trend evidence ledger. Returns ``{topic: [event, …]}``."""
    from app.database import get_database_instance
    db = get_database_instance()
    out: dict = {}
    try:
        rows = db.facade.list_extracted_events(
            cadence=cadence, period_label=period_label, include_excluded=False,
        )
        for e in rows:
            out.setdefault(e.get("topic"), []).append(e)
    except Exception as e:
        logger.warning("events_by_topic load failed (%s/%s): %s", cadence, period_label, e)
    return out


async def generate_bundle(
    cadence: str,
    *,
    updates_only: bool = False,
    when: Optional[datetime] = None,
    progress_callback=None,
) -> Tuple[bytes, str, list, str, list]:
    """Build the bundle PPTX via the WileyBundleSupervisor multi-agent pipeline.

    Wraps :func:`_run_synthesis_pipeline` and renders to PPTX. Even when the
    reviewer flags errors, still renders the PPTX (with a banner slide) — the
    user wants to look at the draft. The send path blocks separately.
    """
    from app.services.forecast_bundle_pptx import build_bundle_pptx

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as e:
                logger.warning("progress_callback failed: %s", e)

    items, period_label, bundle_synth, eos_per_topic, verdict, review_findings = \
        await _run_synthesis_pipeline(
            cadence, updates_only=updates_only, when=when,
            progress_callback=progress_callback,
        )

    _emit(96, "Rendering PPTX")
    blob = build_bundle_pptx(
        items,
        period_label=period_label,
        cadence=cadence,
        updates_only=updates_only,
        bundle_synthesis=bundle_synth,
        eos_per_topic=eos_per_topic,
        events_by_topic=_events_by_topic(cadence, period_label),
        data_quality_note=_data_quality_note(),
        review_findings=review_findings if verdict == "revision_requested" else None,
        review_verdict=verdict,
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, verdict, review_findings


async def generate_bundle_docx(
    cadence: str,
    *,
    updates_only: bool = False,
    when: Optional[datetime] = None,
    progress_callback=None,
) -> Tuple[bytes, str, list, str, list]:
    """Build a focused .docx executive briefing.

    Not a slide-by-slide dump — the docx is positioned as the emailable
    standalone briefing. It includes the rewritten exec-summary letter,
    the cross-cutting themes, the executive decision framework, and a
    one-paragraph-per-topic appendix. Source data is identical to the
    PPTX/Markdown paths; only the renderer differs.
    """
    from app.services.forecast_bundle_docx import build_bundle_docx

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as e:
                logger.warning("progress_callback failed: %s", e)

    items, period_label, bundle_synth, eos_per_topic, verdict, review_findings = \
        await _run_synthesis_pipeline(
            cadence, updates_only=updates_only, when=when,
            progress_callback=progress_callback,
        )

    _emit(96, "Rendering Word document")
    blob = build_bundle_docx(
        items,
        period_label=period_label,
        cadence=cadence,
        updates_only=updates_only,
        bundle_synthesis=bundle_synth,
        eos_per_topic=eos_per_topic,
        review_findings=review_findings,
        review_verdict=verdict,
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, verdict, review_findings


async def generate_bundle_markdown(
    cadence: str,
    *,
    updates_only: bool = False,
    when: Optional[datetime] = None,
    progress_callback=None,
) -> Tuple[bytes, str, list, str, list]:
    """Build a Markdown export of the bundle for human review.

    Same pipeline as :func:`generate_bundle` — only the renderer differs.
    Lets reviewers iterate on analytical content faster than the PPTX cycle.
    """
    from app.services.forecast_bundle_markdown import build_bundle_markdown

    def _emit(pct, msg):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception as e:
                logger.warning("progress_callback failed: %s", e)

    items, period_label, bundle_synth, eos_per_topic, verdict, review_findings = \
        await _run_synthesis_pipeline(
            cadence, updates_only=updates_only, when=when,
            progress_callback=progress_callback,
        )

    _emit(96, "Rendering Markdown")
    blob = build_bundle_markdown(
        items,
        period_label=period_label,
        cadence=cadence,
        updates_only=updates_only,
        bundle_synthesis=bundle_synth,
        eos_per_topic=eos_per_topic,
        review_findings=review_findings,
        review_verdict=verdict,
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, verdict, review_findings


async def generate_bundle_html(
    cadence: str,
    *,
    updates_only: bool = False,
    when: Optional[datetime] = None,
    progress_callback=None,
) -> Tuple[bytes, str, list, str, list]:
    """Build the self-contained interactive HTML bundle.

    Unlike the PPTX/DOCX/MD paths, this renders from the ALREADY-GENERATED
    synthesis + events (cached in forecast_bundle_synthesis + extracted_events)
    rather than re-running the multi-agent pipeline. The HTML is a *view* of
    the brief, not a regeneration — so it's fast (no LLM calls) and doesn't
    re-trigger the agent chain. Generate the bundle (PPTX) first to produce
    the synthesis; this then renders it.
    """
    from app.database import get_database_instance
    from app.services.forecast_bundle_html import build_bundle_html

    db = get_database_instance()
    period_label = _period_label(cadence, when)
    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    if not synth.get("payload"):
        raise ValueError(
            f"No generated brief for {cadence}/{period_label} yet — "
            "generate the bundle (PPTX) first, then export HTML."
        )

    # Resolve the same items the deck used, from the cached topic list.
    items = []
    for entry in (synth.get("topics") or []):
        topic = entry.get("topic") if isinstance(entry, dict) else entry
        if not topic:
            continue
        a = db.facade.get_latest_forecast_assessment_by_topic(topic)
        if a:
            items.append((a, None, None))

    eos_per_topic = {}
    for a, _r, _p in items:
        eos = (a.get("summary") or {}).get("extreme_outlier_scenarios") \
            or (a.get("summary") or {}).get("eos") or []
        if eos:
            eos_per_topic[a.get("topic")] = eos

    review = db.facade.get_forecast_bundle_review(cadence, period_label) or {}
    blob = build_bundle_html(
        items,
        period_label=period_label,
        cadence=cadence,
        updates_only=updates_only,
        bundle_synthesis=synth,
        eos_per_topic=eos_per_topic,
        events_by_topic=_events_by_topic(cadence, period_label),
        data_quality_note=_data_quality_note(),
        review_findings=review.get("reviewer_findings"),
        review_verdict=review.get("status"),
    )
    included_topics = [(a.get("topic") or "—") for (a, _r, _p) in items]
    return blob, period_label, included_topics, review.get("status"), review.get("reviewer_findings")


async def _ensure_eos_for_bundle(items: list) -> dict:
    """For every topic in the bundle, return its most recent EOS scenarios.

    If a topic has no scan ≤90d old, trigger a fresh generation via
    :class:`ExtremeOutlierService.run_generation` and persist into
    ``saved_eos``. Returns ``{topic: [scenarios]}``.
    """
    from app.database import get_database_instance
    from app.services.extreme_outlier_service import ExtremeOutlierService

    db = get_database_instance()
    out = {}
    for assessment, _run, _prior in items:
        topic = assessment.get("topic") or ""
        if not topic:
            continue
        cached = db.facade.get_latest_saved_eos_for_topic(topic, max_age_days=90)
        if cached and cached.get("scenarios"):
            out[topic] = cached.get("scenarios") or []
            continue

        logger.info("EOS scan stale or absent for '%s' — triggering fresh generation", topic)
        try:
            service = ExtremeOutlierService()
            scenarios = []
            final = None
            async for update in service.run_generation(
                topic=topic,
                source_analysis={
                    "topic": topic,
                    "scenarios": [
                        {
                            "title": v.get("scenario_title"),
                            "horizon": v.get("horizon_type"),
                        }
                        for v in (assessment.get("scenario_verdicts") or [])
                        if v.get("verdict_label") != "Done"
                    ],
                    "summary": assessment.get("summary") or {},
                },
            ):
                if update.get("stage") == "complete" and update.get("status") == "success":
                    final = update
                    scenarios = update.get("scenarios") or []
            if scenarios:
                try:
                    # saved_eos.username is FK-bound to users.username, so we
                    # need to attribute system-generated scans to a real user.
                    # 'admin' is the canonical system account across all
                    # tenants. If it's missing the EOS cache silently won't
                    # persist; the bundle will still render but next quarter
                    # has to re-run all the scans.
                    db.facade.create_saved_eos(
                        topic=topic,
                        username="admin",
                        name=f"Bundle EOS · {topic} · {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                        scenarios=scenarios,
                        config=(final or {}).get("metadata", {}).get("config") or {},
                        metadata={"source": "wiley_bundle"},
                        articles_used=0,
                        article_uris=[],
                        model_used="eos",
                        time_horizon="5-15 years",
                        scenario_count=len(scenarios),
                        description="Auto-generated for quarterly Wiley bundle",
                    )
                except Exception as e:
                    logger.warning("Failed to persist fresh EOS for %s: %s", topic, e)
            out[topic] = scenarios
        except Exception as e:
            logger.warning("EOS generation failed for '%s': %s — skipping", topic, e)
            out[topic] = []
    return out


async def deliver_bundle(
    cadence: str,
    *,
    updates_only: bool = True,
    when: Optional[datetime] = None,
) -> dict:
    """Generate + email a cadence bundle to each topic's configured recipient.

    Aggregates unique recipient addresses across all topics in the bundle
    so each address gets exactly one email with the full PPTX attached.
    Bumps ``last_delivered_at`` on every topic in the bundle on success.
    """
    from app.database import get_database_instance
    from app.services.email_service import get_email_service

    from app.services.wiley_bundle_supervisor import BundleRequiresReviewError

    db = get_database_instance()
    blob, period_label, topics, verdict, findings = await generate_bundle(
        cadence, updates_only=updates_only, when=when
    )

    # The send path blocks on revision_requested. Download keeps working
    # so the user can preview, but email delivery requires a clean (or
    # approved) review verdict.
    if verdict == "revision_requested":
        raise BundleRequiresReviewError(cadence, period_label, findings)

    # Collect every distinct recipient across the bundle's topics
    configs = db.facade.get_forecast_topic_delivery_configs()
    by_topic = {c["topic"]: c for c in configs}
    recipients: set = set()
    for t in topics:
        addr = (by_topic.get(t) or {}).get("recipient_email") or ""
        for piece in addr.split(","):
            p = piece.strip()
            if p:
                recipients.add(p)

    if not recipients:
        raise ValueError(
            f"No recipient_email configured for any of the {len(topics)} "
            f"topics in the {cadence} bundle. Set one in the UI first."
        )

    email = get_email_service()
    cadence_label = "Monthly" if cadence == "monthly" else "Quarterly"
    subject = f"[Wiley Forecast Tracker] {cadence_label} update — {period_label}"
    intro = (
        f"Attached is the {cadence_label.lower()} Forecast Tracker bundle for "
        f"{period_label}, covering {len(topics)} {'topic' if len(topics) == 1 else 'topics'}."
    )
    body_html = (
        f"<p>{intro}</p>"
        f"<p>Topics in this bundle:</p><ul>"
        + "".join(f"<li>{_html_escape(t)}</li>" for t in topics)
        + "</ul>"
        "<p>— AunooAI</p>"
    )
    body_text = (
        intro
        + "\n\nTopics in this bundle:\n  - "
        + "\n  - ".join(topics)
        + "\n\n— AunooAI\n"
    )

    fname = (
        f"wiley_forecast_{cadence}_{period_label.replace(' ', '_').lower()}.pptx"
    )
    ok = email.send_email(
        to_addresses=sorted(recipients),
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        attachments=[{
            "filename": fname,
            "content": blob,
            "mime_type": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
        }],
    )

    if ok and cadence in ("monthly", "quarterly"):
        # Only bump last_delivered for the scheduled cadences — ad-hoc
        # "all" exports shouldn't reset the recurring schedule guard.
        now = when or datetime.now(timezone.utc)
        for t in topics:
            db.facade.set_forecast_topic_last_delivered(t, now)

    return {
        "ok": ok,
        "cadence": cadence,
        "period_label": period_label,
        "topics": topics,
        "recipients": sorted(recipients),
        "attachment_filename": fname,
        "attachment_bytes": len(blob),
    }


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
