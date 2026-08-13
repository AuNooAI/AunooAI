"""Timeline rollups + state doc + LLM context block (monolith port of saas rollup.py).

Weekly (Mondays, prior week) and monthly (1st, prior month) LLM rollups absorb
daily mementos: absorbed events get superseded_by_id, old dailies/weeklies get
is_stale, so the timeline compacts instead of growing without bound. The state
doc is one living "state of the scope" paragraph, refreshed after each weekly
rollup and topped up by the scheduler when missing/stale. build_timeline_context
emits the compact text block for report/Auspex prompt injection.

Sync + raw-connection style, matching timeline_events.py. v1 omits saas's
rolling_weekly/rolling_monthly rows and entity wiki pages.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.timeline_events import (
    _parse_json_lenient, _record_run, run_already_completed, scope_label,
    LLM_MODEL,
)
from app.services.report_style import CLINICAL_STYLE

logger = logging.getLogger(__name__)

MIN_EVENTS_FOR_ROLLUP = 3
STATE_DOC_STALE_DAYS = 8


# ---------------------------------------------------------------------------
# LLM synthesis
# ---------------------------------------------------------------------------

def _format_events_for_llm(events: List[Dict[str, Any]]) -> str:
    lines = []
    for evt in events:
        ents = ", ".join((evt.get("entities") or [])[:5]) or "none"
        occ = f", seen {evt['occurrence_count']}×" if evt.get("occurrence_count", 1) > 1 else ""
        lines.append(
            f"- [{evt['event_date']}] {evt['event_type']}: {evt['title']} "
            f"(significance: {evt['significance']}, entities: {ents}{occ})\n"
            f"  {(evt.get('description') or '')[:300]}")
    return "\n".join(lines)


def _llm_json(prompt: str, max_chars: int = 12000) -> Optional[dict]:
    try:
        from app.ai_models import LiteLLMModel
        model = LiteLLMModel.get_instance(LLM_MODEL)
        raw = model.generate_response(
            [{"role": "user", "content": prompt[:max_chars]}], temperature=0.2)
        parsed = _parse_json_lenient(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception as e:  # noqa: BLE001
        logger.warning(f"timeline rollup LLM call failed: {e}")
        return None


def _llm_rollup(scope_name: str, period_label: str, events_text: str,
                event_count: int) -> Optional[dict]:
    prompt = (
        f"You are summarizing developments for \"{scope_name}\" over {period_label} "
        f"({event_count} recorded events):\n\n{events_text}\n\n"
        "Write a factual period summary. Plain statements of what happened — no "
        "editorializing, nothing not present in the events."
        + CLINICAL_STYLE + "\n"
        "Output a pure JSON object (no markdown) with fields:\n"
        f"- \"title\": concise headline about {scope_name} (max 100 chars)\n"
        f"- \"description\": 2-4 sentence narrative of the period, all about {scope_name}\n"
        "- \"key_developments\": 3-5 most important developments (strings)\n"
        "- \"entities_in_focus\": most prominent entity names (strings)\n"
        "- \"overall_trend\": one of \"escalating\", \"stable\", \"de-escalating\", \"mixed\" — "
        "this is the direction of event/article volume versus the prior period, "
        "not a judgment of how bad things are"
    )
    return _llm_json(prompt)


# ---------------------------------------------------------------------------
# Event fetch helpers
# ---------------------------------------------------------------------------

def _fetch_events(conn, scope_type, scope_id, granularity, start=None, end=None,
                  limit=None, exclude_stale=True, exclude_superseded=False) -> List[Dict]:
    q = ("SELECT id, event_type, title, description, significance, entities, "
         "article_uris, article_count, event_date, occurrence_count, event_data "
         "FROM timeline_events WHERE scope_type = :st AND scope_id = :sid "
         "AND granularity = :g")
    p: Dict[str, Any] = {"st": scope_type, "sid": scope_id, "g": granularity}
    if start is not None:
        q += " AND event_date >= :start"; p["start"] = start
    if end is not None:
        q += " AND event_date < :end"; p["end"] = end
    if exclude_stale:
        q += " AND is_stale = false"
    if exclude_superseded:
        q += " AND superseded_by_id IS NULL"
    q += " ORDER BY event_date DESC, CASE significance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(text(q), p).fetchall()
    out = []
    for r in rows:
        out.append({"id": r[0], "event_type": r[1], "title": r[2], "description": r[3],
                    "significance": r[4],
                    "entities": r[5] if isinstance(r[5], list) else json.loads(r[5] or "[]"),
                    "article_uris": r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                    "article_count": r[7], "event_date": r[8],
                    "occurrence_count": r[9],
                    "event_data": r[10] if isinstance(r[10], dict) else json.loads(r[10] or "{}")})
    return out


def _insert_rollup(conn, scope_type, scope_id, subtype, title, description,
                   significance, event_data, entities, uris, n_articles,
                   chash, event_date, granularity) -> Optional[int]:
    row = conn.execute(text("""
        INSERT INTO timeline_events
            (scope_type, scope_id, event_type, event_subtype, title, description,
             significance, event_data, entities, article_uris, article_count,
             content_hash, event_date, last_seen_date, granularity)
        VALUES (:st, :sid, 'new_development', :sub, :title, :descr, :sig, :edata,
                :ents, :uris, :n, :h, :d, :d, :gran)
        ON CONFLICT ON CONSTRAINT uq_timeline_event_hash DO NOTHING
        RETURNING id
    """), {"st": scope_type, "sid": scope_id, "sub": subtype, "title": title[:500],
           "descr": description, "sig": significance,
           "edata": json.dumps(event_data), "ents": json.dumps(entities[:50]),
           "uris": json.dumps(uris[:100]), "n": n_articles, "h": chash,
           "d": event_date, "gran": granularity}).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Weekly / monthly rollups
# ---------------------------------------------------------------------------

def generate_weekly_rollup(conn, scope_type: str, scope_id: str, week_start: date) -> Optional[dict]:
    """Absorb the week's dailies into one weekly memento; supersede them."""
    t0 = time.monotonic()
    if run_already_completed(conn, scope_type, scope_id, "weekly_rollup", week_start):
        return None
    week_end = week_start + timedelta(days=7)
    dailies = _fetch_events(conn, scope_type, scope_id, "daily", week_start, week_end)
    if len(dailies) < MIN_EVENTS_FOR_ROLLUP:
        _record_run(conn, scope_type, scope_id, "weekly_rollup", week_start, "skipped",
                    0, 0, 0, time.monotonic() - t0)
        return None

    label = scope_label(conn, scope_type, scope_id)
    summary = _llm_rollup(label, f"{week_start.isoformat()} to {week_end.isoformat()}",
                          _format_events_for_llm(dailies), len(dailies))
    if not summary:
        _record_run(conn, scope_type, scope_id, "weekly_rollup", week_start, "failed",
                    0, 0, 0, time.monotonic() - t0, "LLM returned empty/invalid")
        return None

    entities = sorted({e for evt in dailies for e in (evt.get("entities") or [])})
    uris = sorted({u for evt in dailies for u in (evt.get("article_uris") or [])})
    chash = hashlib.sha256(
        f"weekly_rollup|{scope_type}|{scope_id}|{week_start.isoformat()}".encode()).hexdigest()
    rollup_id = _insert_rollup(
        conn, scope_type, scope_id, "weekly_rollup",
        summary.get("title", f"Week of {week_start.isoformat()}"),
        summary.get("description", ""),
        "medium",
        {"key_developments": summary.get("key_developments", []),
         "overall_trend": summary.get("overall_trend", "stable"),
         "entities_in_focus": summary.get("entities_in_focus", []),
         "events_absorbed": len(dailies)},
        entities, uris, len(uris), chash, week_start, "weekly")

    if rollup_id:
        conn.execute(text("UPDATE timeline_events SET superseded_by_id = :rid WHERE id = ANY(:ids)"),
                     {"rid": rollup_id, "ids": [e["id"] for e in dailies]})
    # Stale out dailies older than ~30 days
    conn.execute(text("""
        UPDATE timeline_events SET is_stale = true
        WHERE scope_type = :st AND scope_id = :sid AND granularity = 'daily'
          AND event_date < :cutoff AND is_stale = false
    """), {"st": scope_type, "sid": scope_id, "cutoff": week_start - timedelta(days=23)})
    conn.commit()
    _record_run(conn, scope_type, scope_id, "weekly_rollup", week_start, "completed",
                0, 1, 0, time.monotonic() - t0)
    logger.info("Timeline weekly rollup: %s/%s week=%s absorbed %d",
                scope_type, label, week_start, len(dailies))

    try:
        refresh_state_doc(conn, scope_type, scope_id)
    except Exception:  # noqa: BLE001
        logger.exception("state doc refresh after weekly rollup failed")
    return summary


def generate_monthly_rollup(conn, scope_type: str, scope_id: str, month_start: date) -> Optional[dict]:
    """Absorb the month's weeklies into one monthly memento."""
    t0 = time.monotonic()
    if run_already_completed(conn, scope_type, scope_id, "monthly_rollup", month_start):
        return None
    month_end = (month_start.replace(year=month_start.year + 1, month=1)
                 if month_start.month == 12
                 else month_start.replace(month=month_start.month + 1))
    weeklies = _fetch_events(conn, scope_type, scope_id, "weekly", month_start, month_end)
    if len(weeklies) < 2:
        _record_run(conn, scope_type, scope_id, "monthly_rollup", month_start, "skipped",
                    0, 0, 0, time.monotonic() - t0)
        return None

    label = scope_label(conn, scope_type, scope_id)
    summary = _llm_rollup(label, month_start.strftime("%B %Y"),
                          _format_events_for_llm(weeklies), len(weeklies))
    if not summary:
        _record_run(conn, scope_type, scope_id, "monthly_rollup", month_start, "failed",
                    0, 0, 0, time.monotonic() - t0, "LLM returned empty/invalid")
        return None

    entities = sorted({e for evt in weeklies for e in (evt.get("entities") or [])})
    uris = sorted({u for evt in weeklies for u in (evt.get("article_uris") or [])})
    chash = hashlib.sha256(
        f"monthly_rollup|{scope_type}|{scope_id}|{month_start.isoformat()}".encode()).hexdigest()
    rollup_id = _insert_rollup(
        conn, scope_type, scope_id, "monthly_rollup",
        summary.get("title", f"{month_start.strftime('%B %Y')} summary"),
        summary.get("description", ""),
        "medium",
        {"key_developments": summary.get("key_developments", []),
         "overall_trend": summary.get("overall_trend", "stable"),
         "entities_in_focus": summary.get("entities_in_focus", []),
         "weeks_absorbed": len(weeklies)},
        entities, uris, len(uris), chash, month_start, "monthly")

    if rollup_id:
        conn.execute(text("UPDATE timeline_events SET superseded_by_id = :rid WHERE id = ANY(:ids)"),
                     {"rid": rollup_id, "ids": [e["id"] for e in weeklies]})
    conn.execute(text("""
        UPDATE timeline_events SET is_stale = true
        WHERE scope_type = :st AND scope_id = :sid AND granularity = 'weekly'
          AND event_date < :cutoff AND is_stale = false
    """), {"st": scope_type, "sid": scope_id, "cutoff": month_start - timedelta(days=60)})
    conn.commit()
    _record_run(conn, scope_type, scope_id, "monthly_rollup", month_start, "completed",
                0, 1, 0, time.monotonic() - t0)
    logger.info("Timeline monthly rollup: %s/%s month=%s absorbed %d weeks",
                scope_type, label, month_start, len(weeklies))

    try:
        refresh_state_doc(conn, scope_type, scope_id)
    except Exception:  # noqa: BLE001
        logger.exception("state doc refresh after monthly rollup failed")
    return summary


# ---------------------------------------------------------------------------
# State doc
# ---------------------------------------------------------------------------

def refresh_state_doc(conn, scope_type: str, scope_id: str) -> Optional[dict]:
    """Regenerate the living 'state of the scope' paragraph from recent rollups."""
    label = scope_label(conn, scope_type, scope_id)
    monthly = _fetch_events(conn, scope_type, scope_id, "monthly", limit=3, exclude_stale=False)
    weekly = _fetch_events(conn, scope_type, scope_id, "weekly", limit=4)
    notes = _fetch_events(conn, scope_type, scope_id, "permanent", limit=10, exclude_stale=False)
    daily = [] if (monthly or weekly) else _fetch_events(
        conn, scope_type, scope_id, "daily", limit=15, exclude_superseded=True)
    if not monthly and not weekly and not notes and not daily:
        return None

    parts = []
    if notes:
        parts.append("Analyst notes:\n" + "\n".join(
            f"- {n['title']}: {(n['description'] or '')[:300]}" for n in notes))
    if monthly:
        parts.append("Monthly rollups:\n" + "\n".join(
            f"- {m['event_date']}: {m['title']} — {(m['description'] or '')[:400]}" for m in monthly))
    if weekly:
        parts.append("Weekly rollups:\n" + "\n".join(
            f"- W/E {w['event_date']}: {w['title']} — {(w['description'] or '')[:250]}" for w in weekly))
    if daily:
        parts.append("Recent events:\n" + _format_events_for_llm(daily))

    prompt = (
        f"Scope: \"{label}\"\n\nRecent timeline material:\n" + "\n\n".join(parts) +
        "\n\nWrite one plain paragraph (150-250 words) describing the current "
        "state of this scope for an analyst seeing it for the first time: "
        "dominant storyline, key actors, trajectory, open questions. Factual "
        "statements only — no hedging filler, no generic intro."
        + CLINICAL_STYLE + "\n"
        "Output a pure JSON object (no markdown) with fields:\n"
        "- \"summary\": the paragraph\n"
        "- \"key_entities\": 5-10 most prominent entity names\n"
        "- \"current_trend\": one of \"escalating\", \"stable\", \"de-escalating\", \"emerging\", \"mixed\" — "
        "this is the direction of coverage volume versus the prior period, "
        "not a judgment of how bad things are"
    )
    summary = _llm_json(prompt)
    if not summary or not summary.get("summary"):
        return None

    n_events = conn.execute(text(
        "SELECT COUNT(*) FROM timeline_events WHERE scope_type = :st AND scope_id = :sid"),
        {"st": scope_type, "sid": scope_id}).fetchone()[0]
    conn.execute(text("""
        INSERT INTO timeline_state_docs (scope_type, scope_id, summary, key_entities,
                                         current_trend, event_count_at_refresh)
        VALUES (:st, :sid, :summ, :ents, :trend, :n)
        ON CONFLICT ON CONSTRAINT uq_timeline_state_doc DO UPDATE
        SET summary = EXCLUDED.summary, key_entities = EXCLUDED.key_entities,
            current_trend = EXCLUDED.current_trend,
            event_count_at_refresh = EXCLUDED.event_count_at_refresh,
            generated_at = NOW()
    """), {"st": scope_type, "sid": scope_id, "summ": summary["summary"],
           "ents": json.dumps(summary.get("key_entities") or []),
           "trend": summary.get("current_trend"), "n": n_events})
    conn.commit()
    logger.info("Timeline state doc refreshed: %s/%s", scope_type, label)
    return summary


def get_state_doc(conn, scope_type: str, scope_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT summary, key_entities, current_trend, generated_at
        FROM timeline_state_docs WHERE scope_type = :st AND scope_id = :sid
    """), {"st": scope_type, "sid": scope_id}).fetchone()
    if not row:
        return None
    return {"summary": row[0],
            "key_entities": row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]"),
            "current_trend": row[2], "generated_at": row[3].isoformat() if row[3] else None}


def state_doc_stale_scopes(conn, max_age_days: int = STATE_DOC_STALE_DAYS) -> List[Dict[str, str]]:
    """Scopes with timeline events whose state doc is missing or older than max_age."""
    rows = conn.execute(text("""
        SELECT DISTINCT e.scope_type, e.scope_id
        FROM timeline_events e
        LEFT JOIN timeline_state_docs d
               ON d.scope_type = e.scope_type AND d.scope_id = e.scope_id
        WHERE d.id IS NULL OR d.generated_at < now() - (:age || ' days')::interval
    """), {"age": str(max_age_days)}).fetchall()
    return [{"scope_type": r[0], "scope_id": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Context block for LLM prompt injection
# ---------------------------------------------------------------------------

def resolve_scope_for_topic(conn, topic: str):
    """Map an articles.topic value to a timeline scope.

    'Brand Monitoring <name>' lanes belong to the brand scope (its timeline
    also carries risk/alert/story mementos); everything else is a topic scope.
    """
    if topic and topic.startswith("Brand Monitoring "):
        name = topic[len("Brand Monitoring "):].strip()
        row = conn.execute(text(
            "SELECT id FROM bw_brands WHERE display_name = :n AND enabled = true"),
            {"n": name}).fetchone()
        if row:
            return "brand", str(row[0])
    return "topic", topic


def build_timeline_context(conn, scope_type: str, scope_id: str,
                           char_budget: int = 3200) -> str:
    """Compact text block (~800 tokens): state doc + analyst notes + 1 monthly
    + 4 weekly + 7 daily."""
    label = scope_label(conn, scope_type, scope_id)
    blocks: List[str] = []

    sd = get_state_doc(conn, scope_type, scope_id)
    if sd:
        trend = f" (trend: {sd['current_trend']})" if sd.get("current_trend") else ""
        blocks.append(f"[STATE: {label}]{trend}\n{sd['summary']}\n[END STATE]")

    lines: List[str] = [f"[TIMELINE: {label}]"]
    notes = _fetch_events(conn, scope_type, scope_id, "permanent", limit=10,
                          exclude_stale=False)
    if notes:
        lines.append("Analyst notes:")
        for n in notes:
            lines.append(f"- {n['title']}" + (f": {(n['description'] or '')[:200]}"
                                              if n.get("description") else ""))
    for gran, limit, prefix in (("monthly", 1, "Month"), ("weekly", 4, "Week"),):
        for e in _fetch_events(conn, scope_type, scope_id, gran, limit=limit):
            lines.append(f"- [{prefix} {e['event_date']}] {e['title']}: {(e['description'] or '')[:220]}")
    for e in _fetch_events(conn, scope_type, scope_id, "daily", limit=7,
                           exclude_superseded=True):
        occ = f" (seen {e['occurrence_count']}×)" if e.get("occurrence_count", 1) > 1 else ""
        lines.append(f"- [{e['event_date']}] {e['title']}{occ}")
    if len(lines) > 1:
        lines.append("[END TIMELINE]")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)[:char_budget]
