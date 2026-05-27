"""Event-extraction stage for the Wiley quarterly foresight update.

Runs the ``wiley_event_extractor_agent`` over a topic's recent articles and
persists the structured events it finds into ``extracted_events`` (created by
migration ``fa_008``). These events are the factual ground-truth that powers
the honest "What's changed this quarter" section — named actor + action +
magnitude + date, NOT article-framing ratios.

Design (per docs/wiley_quarterly_update_plan.md §2):

* Synchronous — invoked as a supervisor stage between briefings and
  exec_summary, or on demand from the Quarterly Brief Editor's
  "Regenerate → events" button. Quarterly cadence means nightly batching
  would waste compute on articles that won't be cited.
* Dedup happens at persistence time: ``upsert_extracted_event`` is keyed on
  ``(topic, actor_normalized, action, subject_normalized, event_date)`` and
  merges ``source_urls`` rather than inserting duplicates. We additionally
  collapse within a batch before persisting.
* ``magnitude`` is optional; the agent is instructed never to invent one.
* Low-confidence / missing-field events land with ``requires_review=true`` so
  the editor's Events tab surfaces them under a separate header.

Public entrypoint: ``run_event_extraction(cadence, period_label, topics=None)``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta, date as _date
from typing import Optional

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over",
    "after", "more", "than", "about", "their", "have", "has", "was", "were",
    "are", "its", "a", "an", "of", "to", "in", "on", "by", "at",
}


def _tokens(s: Optional[str]) -> set:
    return {
        w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
        if len(w) >= 3 and w not in _STOPWORDS
    }


def _parse_iso(d) -> Optional[_date]:
    try:
        return _date.fromisoformat(str(d)[:10]) if d else None
    except Exception:
        return None


_VALID_DIRECTIONS = {"confirms", "counters", "neutral"}


def _normalize_scenario_relevance(raw) -> list:
    """Coerce scenario_relevance to a list of {scenario, direction}.

    The v2 extractor returns objects; older data / loose model output may be
    bare strings. Bare strings become direction='neutral'. Invalid
    directions fall back to 'neutral'.
    """
    out = []
    for item in (raw or []):
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"scenario": name, "direction": "neutral"})
        elif isinstance(item, dict):
            name = (item.get("scenario") or "").strip()
            if not name:
                continue
            direction = (item.get("direction") or "neutral").strip().lower()
            if direction not in _VALID_DIRECTIONS:
                direction = "neutral"
            out.append({"scenario": name, "direction": direction})
    return out


def events_for_scenario(events: list, scenario_name: str) -> tuple:
    """Split a topic's events into (confirming, countering) lists for a given
    scenario, by reading the {scenario, direction} entries in
    scenario_relevance. Used by the ledger slide. Case-insensitive match."""
    target = (scenario_name or "").strip().lower()
    confirming, countering = [], []
    for e in events:
        for rel in _normalize_scenario_relevance(e.get("scenario_relevance")):
            if rel["scenario"].strip().lower() != target:
                continue
            if rel["direction"] == "confirms":
                confirming.append(e)
            elif rel["direction"] == "counters":
                countering.append(e)
            break
    return confirming, countering


def _collapse_near_dupes(events: list) -> list:
    """Collapse semantic duplicates the exact dedupe key misses — the same
    real event reported with different wording ("arXiv imposed a 1-year ban"
    vs "Arxiv implemented stricter rules … one-year suspensions"; "A study
    revealed ~150,000 fake citations" vs "A recent study indicated ~150,000
    false citations").

    Two events are treated as the same when BOTH carry the same non-null
    magnitude value, fall within a 10-day window, and share actor tokens or
    ≥2 subject tokens. Events with no magnitude collapse only on a stronger
    signal (same date-window + ≥3 shared subject tokens) to avoid
    over-merging distinct qualitative events. Input is assumed rank-ordered;
    the first representative of each group is kept.

    Non-destructive: only affects the deck list. Every row remains in the DB
    and the editor's Events tab, so a rare wrong merge is recoverable.
    """
    kept: list = []
    for e in events:
        e_mag = e.get("magnitude_value")
        e_date = _parse_iso(e.get("event_date"))
        e_atoks = _tokens(e.get("actor"))
        e_stoks = _tokens(e.get("subject"))
        is_dupe = False
        for k in kept:
            kd = _parse_iso(k.get("event_date"))
            within = (e_date is None or kd is None
                      or abs((e_date - kd).days) <= 10)
            if not within:
                continue
            actor_overlap = bool(e_atoks & _tokens(k.get("actor")))
            subj_overlap = len(e_stoks & _tokens(k.get("subject")))
            k_mag = k.get("magnitude_value")
            if e_mag is not None and k_mag is not None and e_mag == k_mag:
                if actor_overlap or subj_overlap >= 2:
                    is_dupe = True
                    break
            elif e_mag is None and k_mag is None:
                # No magnitude to anchor on — require a strong subject match.
                if subj_overlap >= 3 and (e_date and kd and abs((e_date - kd).days) <= 3):
                    is_dupe = True
                    break
        if not is_dupe:
            kept.append(e)
    return kept

# How far back to pull articles for a quarter window. Generous so a late
# bundle still captures the full quarter; dedup + date filtering keep it tidy.
_DEFAULT_DAYS_BACK = {
    "monthly": 45,
    "quarterly": 110,
    "all": 110,
}
_BATCH_SIZE = 18
_ARTICLE_CAP = 200  # per topic — protects token + cost budget
# Minimum topic_alignment_score for an article to enter event extraction.
# Real on-topic articles score 0.9–1.0; off-topic feed noise scores 0.0,
# so a modest floor cleanly separates them.
_MIN_ALIGNMENT = 0.3


def _normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    return "-".join(str(s).lower().strip().split())


def _scenario_names(assessment: dict) -> list:
    """Exact scenario names for a topic, for the agent's scenario_relevance."""
    names = []
    for v in (assessment.get("scenario_verdicts") or []):
        if v.get("verdict_label") == "Done":
            continue
        deck_info = (v.get("top_articles") or {}).get("deck_info") or {}
        nm = deck_info.get("deck_scenario_name") or v.get("scenario_title")
        if nm:
            names.append(nm)
    return names


def _coerce_date(raw) -> Optional[str]:
    """Return an ISO ``YYYY-MM-DD`` string or None."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Accept full ISO or date-only; slice to the date.
    return s[:10] if len(s) >= 10 else None


async def _extract_for_topic(db, topic: str, assessment: dict, *,
                             cadence: str, period_label: str,
                             days_back: int) -> int:
    """Extract + persist events for one topic. Returns the number of
    distinct events persisted."""
    from app.services.wiley_bundle_supervisor import _call_agent

    # Use the relevance-aware fetch — filters on the ingest pipeline's
    # topic_alignment_score so off-topic feed noise (alignment 0.0) never
    # reaches the extractor. (The unfiltered get_articles_for_topic was the
    # source of the "fighter jets / arms deals" events in the first pass.)
    rows = db.facade.get_relevant_articles_for_topic(
        topic, days_back=days_back, min_alignment=_MIN_ALIGNMENT, limit=_ARTICLE_CAP,
    ) or []
    if not rows:
        logger.info("event-extraction: no on-topic articles for %s "
                    "(alignment > %.2f)", topic, _MIN_ALIGNMENT)
        return 0

    scenarios = _scenario_names(assessment)
    assessment_id = assessment.get("id")

    persisted: dict[tuple, int] = {}  # dedupe key → event id
    n = 0

    for start in range(0, len(rows), _BATCH_SIZE):
        batch = rows[start:start + _BATCH_SIZE]
        payload_articles = []
        for i, a in enumerate(batch):
            payload_articles.append({
                "index": i,
                "title": a.get("title") or "",
                "summary": (a.get("summary") or "")[:600],
                "date": _coerce_date(a.get("publication_date")),
                "source": a.get("news_source") or "",
            })
        payload = {
            "topic": topic,
            "scenarios": scenarios,
            "articles": payload_articles,
        }

        result = await _call_agent("wiley_event_extractor_agent", payload)
        events = (result or {}).get("events") or []

        for ev in events:
            if not isinstance(ev, dict):
                continue
            actor = (ev.get("actor") or "").strip()
            action = (ev.get("action") or "").strip()
            subject = (ev.get("subject") or "").strip()
            if not (actor and action and subject):
                continue  # not a usable event

            event_date = _coerce_date(ev.get("event_date"))
            dedupe_key = (
                _normalize(actor), action.lower(), _normalize(subject), event_date,
            )

            # Resolve the source article URL from source_index.
            src_idx = ev.get("source_index")
            source_url = None
            if isinstance(src_idx, int) and 0 <= src_idx < len(batch):
                source_url = batch[src_idx].get("uri")
            source_urls = [source_url] if source_url else []

            confidence = ev.get("confidence")
            requires_review = bool(ev.get("requires_review")) or (
                isinstance(confidence, (int, float)) and confidence < 0.6
            ) or (not event_date)

            event_row = {
                "assessment_id": assessment_id,
                "topic": topic,
                "cadence": cadence,
                "period_label": period_label,
                "actor": actor,
                "actor_normalized": _normalize(actor),
                "action": action,
                "subject": subject,
                "subject_normalized": _normalize(subject),
                "magnitude_value": ev.get("magnitude_value"),
                "magnitude_unit": ev.get("magnitude_unit"),
                "event_date": event_date,
                "source_urls": source_urls,
                "confidence": confidence,
                "requires_review": requires_review,
                "scenario_relevance": _normalize_scenario_relevance(
                    ev.get("scenario_relevance")
                ),
                "origin": "auto",
            }
            try:
                eid = db.facade.upsert_extracted_event(event_row)
                if dedupe_key not in persisted:
                    persisted[dedupe_key] = eid
                    n += 1
            except Exception as e:
                logger.warning("event-extraction: persist failed for %s/%s: %s",
                               topic, actor, e)

    logger.info("event-extraction: %s → %d distinct events", topic, n)
    return n


async def run_event_extraction(
    *, cadence: str, period_label: str, topics: Optional[list] = None,
) -> dict:
    """Extract events for every topic in the period (or a subset).

    Returns ``{topic: n_events}``. Idempotent: re-running merges into the
    same deduped rows rather than duplicating.
    """
    from app.database import get_database_instance
    db = get_database_instance()

    days_back = _DEFAULT_DAYS_BACK.get(cadence, 110)

    # Resolve the topic → assessment map. Prefer the cached bundle's topic
    # list so we extract for exactly what's in the deck; fall back to all
    # topics with assessments.
    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    topic_list = topics or [
        (t.get("topic") if isinstance(t, dict) else t)
        for t in (synth.get("topics") or [])
    ]
    topic_list = [t for t in topic_list if t]

    out: dict[str, int] = {}
    for topic in topic_list:
        assessment = db.facade.get_latest_forecast_assessment_by_topic(topic) or {}
        if not assessment:
            logger.info("event-extraction: no assessment for %s — skipping", topic)
            out[topic] = 0
            continue
        try:
            out[topic] = await _extract_for_topic(
                db, topic, assessment,
                cadence=cadence, period_label=period_label, days_back=days_back,
            )
        except Exception as e:
            logger.exception("event-extraction failed for %s: %s", topic, e)
            out[topic] = 0

    # Mirror a compact "named events" list into the synthesis payload so the
    # What's Changed slide + exec summary can read it without re-querying.
    try:
        _sync_events_into_payload(db, cadence, period_label)
    except Exception as e:
        logger.warning("event-extraction: payload sync failed: %s", e)

    return out


def _compute_coverage_shifts(db, topics, *, window_days: int = 90):
    """Per-topic press-attention shift: on-topic article volume this window
    vs the prior equal-length window. Returns labelled lines for the deck's
    "where press attention shifted" block. Strictly a coverage signal."""
    now = datetime.now()
    cur_start = (now - timedelta(days=window_days)).strftime('%Y-%m-%d')
    cur_end = now.strftime('%Y-%m-%d')
    prior_start = (now - timedelta(days=window_days * 2)).strftime('%Y-%m-%d')
    prior_end = cur_start
    MIN_VOL = 8       # both windows must clear this to be worth reporting
    MIN_PCT = 35.0    # and the change must exceed the gap-artifact band
    rows = []
    for t in (topics or []):
        topic = t.get("topic") if isinstance(t, dict) else t
        if not topic:
            continue
        try:
            cur = db.facade.count_relevant_articles_for_topic_window(
                topic, start=cur_start, end=cur_end)
            prior = db.facade.count_relevant_articles_for_topic_window(
                topic, start=prior_start, end=prior_end)
        except Exception:
            logger.exception("coverage shift count failed for %s", topic)
            continue
        if cur < MIN_VOL or prior < MIN_VOL:
            continue
        pct = (cur - prior) / prior * 100.0
        if abs(pct) < MIN_PCT:
            continue
        # Qualitative descriptor + raw counts, NOT a fake-precise percentage.
        # The counts carry the true magnitude; the phrase stays conservative.
        if pct >= 100:
            phrase = "press coverage more than doubled"
        elif pct > 0:
            phrase = f"press coverage rose ~{pct:.0f}%"
        elif pct <= -50:
            phrase = "press coverage fell by more than half"
        else:
            phrase = f"press coverage fell ~{abs(pct):.0f}%"
        rows.append((abs(pct),
                     f"{topic}: {phrase} ({cur} vs {prior} on-topic articles)"))
    rows.sort(key=lambda r: -r[0])
    return [line for _, line in rows[:5]]


def _sync_events_into_payload(db, cadence: str, period_label: str):
    """Write a deck-ready ``whats_changed.events`` list (deck-included events
    only) into the bundle synthesis payload."""
    synth = db.facade.get_forecast_bundle_synthesis(cadence, period_label) or {}
    payload = synth.get("payload") or {}

    events = db.facade.list_extracted_events(
        cadence=cadence, period_label=period_label, include_excluded=False,
    )

    # Drop stale events: an article in the window can reference an event from
    # months earlier (e.g. a 2025 statistic). A "what's changed this quarter"
    # list must not carry those. Keep events dated within the analysis window
    # (~120 days) or undated (treated as current-ish).
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    events = [
        e for e in events
        if not e.get("event_date") or str(e["event_date"])[:10] >= cutoff
    ]

    # The topic feeds are noisy, so even after the agent's materiality gate
    # there can be more events than belong on a slide. Rank so the deck
    # shows the most decision-relevant handful: events tied to a scenario
    # and/or carrying a hard magnitude, highest confidence first. Skip
    # review-flagged ones (the analyst promotes those from the editor).
    DECK_CAP = 14

    def _rank(e):
        return (
            1 if (e.get("scenario_relevance") or []) else 0,
            1 if e.get("magnitude_value") is not None else 0,
            e.get("confidence") or 0,
        )

    ranked = sorted(
        [e for e in events if not e.get("requires_review")],
        key=_rank, reverse=True,
    )
    # Collapse semantic near-duplicates (same event, different wording)
    # BEFORE the cap so dupes don't consume slide slots. Runs on the
    # rank-ordered list so the highest-ranked phrasing of each event wins.
    ranked = _collapse_near_dupes(ranked)[:DECK_CAP]
    # Within the capped set, present newest-first for reading.
    ranked.sort(key=lambda e: e.get("event_date") or "", reverse=True)

    lines = []
    for e in ranked:
        actor = (e.get("actor") or "").strip()
        action = (e.get("action") or "").strip()
        subject = (e.get("subject") or "").strip()
        # Drop a redundant subject that just restates the actor (extraction
        # artifact: "Largest X trial was retracted largest X trial").
        if subject and _normalize(subject) in (_normalize(actor), ""):
            subject = ""
        elif subject and _normalize(actor) and _normalize(actor) in _normalize(subject):
            # Subject contains the actor verbatim — keep subject, it's the
            # fuller phrasing; the actor prefix will read slightly redundant
            # but stays informative. (No change.)
            pass
        mag = ""
        if e.get("magnitude_value") is not None:
            unit = e.get("magnitude_unit") or ""
            mag = f" ({e['magnitude_value']:g} {unit})".replace("  ", " ").replace(" )", ")")
        date = f" — {e['event_date']}" if e.get("event_date") else ""
        line = " ".join(p for p in (actor, action, subject) if p) + mag + date
        lines.append(line.strip())

    wc = dict(payload.get("whats_changed") or {})
    wc["events"] = lines
    # Persist "new on the watch" (emerging themes) from each topic's top
    # surprise cluster when the analyst hasn't entered any — so the editor
    # and the deck show the same thing (previously this was render-only).
    # scenario_drift has no reliable auto-source (Wiley's scenarios are
    # authored, so the set rarely drifts) — it stays analyst-entered.
    if not wc.get("emerging"):
        emerging = []
        for t in (synth.get("topics") or []):
            topic = t.get("topic") if isinstance(t, dict) else t
            if not topic:
                continue
            a = db.facade.get_latest_forecast_assessment_by_topic(topic) or {}
            top = sorted((a.get("surprises") or []),
                         key=lambda s: -(s.get("size") or 0))[:1]
            for s in top:
                lab = (s.get("label") or "").strip()
                # skip keyword-salad labels (comma-separated lowercase tokens)
                if lab and not re.fullmatch(
                        r"[a-z0-9][a-z0-9\-]*(?:,\s*[a-z0-9][a-z0-9\-]*){1,5}", lab):
                    emerging.append(f"{topic}: {lab}")
        wc["emerging"] = emerging[:5]
    # Auto-fill "where press attention shifted" (coverage_shifts) from the
    # change in on-topic article VOLUME between this period and the prior
    # equal-length window. This is a press-attention / discourse signal —
    # framed strictly as coverage, NEVER as forecast movement (the events,
    # not the article count, are the test of whether a trend bears out).
    # Thresholds (both windows ≥8 articles, |Δ| ≥35%) keep it out of noise
    # and out of reach of the ~2-week collection gap, which dents a 90-day
    # window by <15% and so can't fake a "coverage fell" line.
    if not wc.get("coverage_shifts"):
        wc["coverage_shifts"] = _compute_coverage_shifts(
            db, synth.get("topics") or [], window_days=90,
        )
    payload["whats_changed"] = wc
    db.facade.save_forecast_bundle_synthesis(
        cadence, period_label, payload, synth.get("topics") or [],
    )
