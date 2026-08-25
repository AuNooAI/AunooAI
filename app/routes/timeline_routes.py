"""Timeline mementos API — per-brand/per-topic event timeline.

GET  /api/timeline/scopes    — available scopes (brands + topics) with counts
GET  /api/timeline/events    — paged memento list for a scope
GET  /api/timeline/summary   — state doc + compact monthly/weekly/daily buckets
GET  /api/timeline/context   — the LLM-injection text block (debug/preview)
GET  /api/timeline/status    — scheduler status + recent runs
POST /api/timeline/generate  — run extraction now (optionally N days back)
"""
import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import get_database_instance
from app.security.session import verify_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


def _conn():
    return get_database_instance()._temp_get_connection()


def _serialize_event(r) -> Dict[str, Any]:
    return {
        "id": r[0], "scope_type": r[1], "scope_id": r[2], "event_type": r[3],
        "event_subtype": r[4], "title": r[5], "description": r[6],
        "significance": r[7],
        "event_data": r[8] if isinstance(r[8], dict) else json.loads(r[8] or "{}"),
        "entities": r[9] if isinstance(r[9], list) else json.loads(r[9] or "[]"),
        "article_uris": r[10] if isinstance(r[10], list) else json.loads(r[10] or "[]"),
        "article_count": r[11],
        "event_date": r[12].isoformat() if r[12] else None,
        "last_seen_date": r[13].isoformat() if r[13] else None,
        "occurrence_count": r[14], "granularity": r[15], "is_stale": r[16],
        "superseded_by_id": r[17],
        "created_at": r[18].isoformat() if r[18] else None,
    }


_EVENT_COLS = ("id, scope_type, scope_id, event_type, event_subtype, title, description, "
               "significance, event_data, entities, article_uris, article_count, event_date, "
               "last_seen_date, occurrence_count, granularity, is_stale, superseded_by_id, created_at")


@router.get("/scopes")
async def list_scopes(session=Depends(verify_session)):
    conn = _conn()
    try:
        from app.services.timeline_events import get_timeline_scopes
        scopes = get_timeline_scopes(conn)
        counts = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(text("""
            SELECT scope_type, scope_id, COUNT(*), MAX(event_date)
            FROM timeline_events GROUP BY scope_type, scope_id
        """)).fetchall()}
        for s in scopes:
            n, latest = counts.get((s["scope_type"], s["scope_id"]), (0, None))
            s["event_count"] = n
            s["latest_event_date"] = latest.isoformat() if latest else None
        return {"scopes": scopes}
    finally:
        conn.close()


@router.get("/events")
async def list_events(
    scope_type: str = Query(..., pattern="^(topic|brand)$"),
    scope_id: str = Query(...),
    granularity: Optional[str] = Query(None, pattern="^(daily|weekly|monthly|permanent)$"),
    event_type: Optional[str] = None,
    include_stale: bool = False,
    include_superseded: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
    # Optional and unfiltered by default so existing callers (Brand Watcher's
    # own wire view) see no change — Market Monitor's Wire tab is the first
    # caller to pass this, so it stops ignoring the same period selector that
    # already governs Pulse, Analysis and Coverage.
    days: Optional[int] = Query(None, ge=1, le=3650),
    session=Depends(verify_session),
):
    conn = _conn()
    try:
        q = f"SELECT {_EVENT_COLS} FROM timeline_events WHERE scope_type = :st AND scope_id = :sid"
        p: Dict[str, Any] = {"st": scope_type, "sid": scope_id}
        if granularity:
            q += " AND granularity = :g"; p["g"] = granularity
        if event_type:
            q += " AND event_type = :et"; p["et"] = event_type
        if days:
            q += " AND event_date >= (NOW() - (:d || ' days')::INTERVAL)::date"
            p["d"] = str(days)
        if not include_stale:
            q += " AND is_stale = false"
        if not include_superseded:
            q += " AND superseded_by_id IS NULL"
        total = conn.execute(text(f"SELECT COUNT(*) FROM ({q}) sub"), p).fetchone()[0]
        q += (" ORDER BY event_date DESC, CASE significance WHEN 'critical' THEN 0 "
              "WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC "
              f"LIMIT {int(limit)} OFFSET {int(offset)}")
        rows = conn.execute(text(q), p).fetchall()
        return {"total": total, "events": [_serialize_event(r) for r in rows]}
    finally:
        conn.close()


class ArticleLookup(BaseModel):
    uris: list[str] = Field(..., max_length=50)


@router.post("/articles")
async def timeline_article_lookup(body: ArticleLookup, session=Depends(verify_session)):
    """Titles, links and vendor attribution for a batch of article URIs.

    An event carries only ``article_uris`` — a count and a significance are
    not something a reader can check without seeing what they were computed
    from, so this is what a "show articles" expansion calls on request
    rather than something every event list-load pays for upfront. Vendors
    come from the same ``bw_article_categories`` classification the rest of
    the app pivots on, so a reader can jump straight to a named vendor's
    profile the way they already can from Coverage.
    """
    conn = _conn()
    try:
        if not body.uris:
            return {"articles": []}
        rows = conn.execute(text("""
            SELECT uri, title, news_source, publication_date
            FROM articles WHERE uri = ANY(:uris)
        """), {"uris": body.uris}).mappings().all()
        by_uri = {r["uri"]: {**dict(r), "vendors": []} for r in rows}
        for uri, brand_id, name in conn.execute(text("""
            SELECT DISTINCT bac.article_uri, b.id, b.display_name
            FROM bw_article_categories bac
            JOIN bw_brands b ON b.id = bac.brand_id
            WHERE bac.article_uri = ANY(:uris)
        """), {"uris": body.uris}).fetchall():
            if uri in by_uri:
                by_uri[uri]["vendors"].append(
                    {"brand_id": brand_id, "vendor": name})
        # The caller's order is already relevance- or recency-sorted.
        return {"articles": [by_uri[u] for u in body.uris if u in by_uri]}
    finally:
        conn.close()


@router.get("/summary")
async def timeline_summary(
    scope_type: str = Query(..., pattern="^(topic|brand)$"),
    scope_id: str = Query(...),
    session=Depends(verify_session),
):
    conn = _conn()
    try:
        from app.services.timeline_rollup import get_state_doc
        from app.services.timeline_events import scope_label
        out: Dict[str, Any] = {
            "scope_type": scope_type, "scope_id": scope_id,
            "label": scope_label(conn, scope_type, scope_id),
            "state_doc": get_state_doc(conn, scope_type, scope_id),
            "escalation_tier": None,
        }
        if scope_type == "brand":
            from app.services.escalation_tiers import evaluate_brand_tier
            try:
                out["escalation_tier"] = evaluate_brand_tier(conn, int(scope_id))
            except (ValueError, TypeError):
                pass
        for gran, limit, key in (("monthly", 1, "monthly"), ("weekly", 4, "weekly"),
                                 ("permanent", 10, "analyst_notes")):
            rows = conn.execute(text(f"""
                SELECT {_EVENT_COLS} FROM timeline_events
                WHERE scope_type = :st AND scope_id = :sid AND granularity = :g
                  AND is_stale = false
                ORDER BY event_date DESC LIMIT {limit}
            """), {"st": scope_type, "sid": scope_id, "g": gran}).fetchall()
            out[key] = [_serialize_event(r) for r in rows]
        rows = conn.execute(text(f"""
            SELECT {_EVENT_COLS} FROM timeline_events
            WHERE scope_type = :st AND scope_id = :sid AND granularity = 'daily'
              AND is_stale = false AND superseded_by_id IS NULL
            ORDER BY event_date DESC, CASE significance WHEN 'critical' THEN 0
              WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END LIMIT 15
        """), {"st": scope_type, "sid": scope_id}).fetchall()
        out["daily"] = [_serialize_event(r) for r in rows]
        return out
    finally:
        conn.close()


@router.get("/context")
async def timeline_context(
    scope_type: str = Query(..., pattern="^(topic|brand)$"),
    scope_id: str = Query(...),
    session=Depends(verify_session),
):
    conn = _conn()
    try:
        from app.services.timeline_rollup import build_timeline_context
        return {"context": build_timeline_context(conn, scope_type, scope_id)}
    finally:
        conn.close()


@router.get("/status")
async def timeline_status(session=Depends(verify_session)):
    conn = _conn()
    try:
        from app.tasks.timeline_task import get_timeline_task_status
        runs = conn.execute(text("""
            SELECT scope_type, scope_id, run_type, run_date, status,
                   articles_processed, events_created, events_deduplicated
            FROM timeline_runs ORDER BY created_at DESC LIMIT 25
        """)).fetchall()
        counts = conn.execute(text("""
            SELECT granularity, COUNT(*) FROM timeline_events GROUP BY granularity
        """)).fetchall()
        return {
            "task": get_timeline_task_status(),
            "events_by_granularity": {r[0]: r[1] for r in counts},
            "recent_runs": [
                {"scope_type": r[0], "scope_id": r[1], "run_type": r[2],
                 "run_date": r[3].isoformat(), "status": r[4],
                 "articles_processed": r[5], "events_created": r[6],
                 "events_deduplicated": r[7]} for r in runs],
        }
    finally:
        conn.close()


class NoteRequest(BaseModel):
    scope_type: str = Field(pattern="^(topic|brand)$")
    scope_id: str
    title: str = Field(min_length=3, max_length=300)
    description: str = Field("", max_length=2000)


@router.post("/notes")
async def add_analyst_note(req: NoteRequest, session=Depends(verify_session)):
    """Pin a permanent analyst note onto a scope's timeline. Notes are never
    stale, feed the state doc, and ride along in the LLM context block."""
    conn = _conn()
    try:
        from app.services.timeline_events import upsert_event
        evt = {
            "event_type": "analyst_note",
            "title": req.title.strip(),
            "description": req.description.strip(),
            "significance": "high",
            "granularity": "permanent",
        }
        outcome = upsert_event(conn, req.scope_type, req.scope_id, evt,
                               date.today(), dated_hash=False)
        conn.commit()
        return {"outcome": outcome}
    finally:
        conn.close()


@router.delete("/notes/{event_id}")
async def delete_analyst_note(event_id: int, session=Depends(verify_session)):
    conn = _conn()
    try:
        row = conn.execute(text("""
            DELETE FROM timeline_events
            WHERE id = :i AND event_type = 'analyst_note' RETURNING id
        """), {"i": event_id}).fetchone()
        conn.commit()
        if not row:
            raise HTTPException(status_code=404, detail="Note not found")
        return {"deleted": event_id}
    finally:
        conn.close()


class GenerateRequest(BaseModel):
    scope_type: str = Field(pattern="^(topic|brand)$")
    scope_id: str
    days_back: int = Field(1, ge=1, le=30)
    use_llm: bool = True


@router.post("/generate")
async def generate_now(req: GenerateRequest, session=Depends(verify_session)):
    """Run daily extraction for the last N days (oldest first), then refresh
    the state doc. Runs inline in a worker thread; bounded by days_back <= 30."""
    def _run():
        conn = _conn()
        try:
            from app.services.timeline_events import extract_daily_events
            from app.services.timeline_rollup import refresh_state_doc
            totals = {"articles_processed": 0, "events_created": 0, "events_deduplicated": 0}
            today = date.today()
            for back in range(req.days_back, 0, -1):
                res = extract_daily_events(conn, req.scope_type, req.scope_id,
                                           today - timedelta(days=back),
                                           use_llm=(req.use_llm and back <= 2))
                for k in totals:
                    totals[k] += res[k]
            try:
                refresh_state_doc(conn, req.scope_type, req.scope_id)
            except Exception:  # noqa: BLE001
                logger.exception("state doc refresh in /generate failed")
            return totals
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:  # noqa: BLE001
        logger.exception("timeline generate failed")
        raise HTTPException(status_code=500, detail=str(e)[:300])
