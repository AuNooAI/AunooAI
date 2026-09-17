"""Swiss election disinformation monitor: API routes.

Every read endpoint runs the sync service in a worker thread so a slow
query cannot stall the event loop. Processing runs as a FastAPI
background task with a module-level status dict, on the GeoHotspots
pattern. Auth: verify_session_api (401 on missing session).
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import get_database_instance
from app.security.session import verify_session_api
from app.services.swiss_disinfo_service import (
    ATTRIBUTIONS, BRIEF_MODEL, DEFAULT_MODEL, DEFAULT_TOPIC, LANGUAGES, SCOPES,
    STANCES, TECHNIQUES, TIERS, get_swiss_disinfo_service, list_scopes, scope,
)
from app.tasks.swiss_disinfo_monitor import calculate_next_run, get_task_status, run_schedule_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/swiss-disinfo", tags=["swiss-disinfo"])

_processing: Dict[str, Any] = {
    "running": False, "total": 0, "processed": 0, "on_topic": 0,
    "narratives_created": 0, "errors": 0, "started_at": None, "finished_at": None, "error": None,
}


class ProcessRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500)
    model: str = DEFAULT_MODEL
    process_all: bool = False
    topic: Optional[str] = None


class ScheduleIn(BaseModel):
    name: str
    batch_size: int = 50
    model: str = DEFAULT_MODEL
    process_all: bool = False
    schedule_enabled: bool = True
    schedule_type: str = "interval"
    schedule_interval: Optional[int] = 2
    schedule_unit: str = "hours"
    schedule_time: Optional[str] = None
    notify_on_complete: bool = True


class BriefRequest(BaseModel):
    days_back: int = Field(7, ge=1, le=90)
    model: str = BRIEF_MODEL
    topic: Optional[str] = None


def _svc(topic: Optional[str] = None):
    return get_swiss_disinfo_service(topic or DEFAULT_TOPIC)


ScopeParam = Query(None, description="Scope topic; defaults to the Swiss watch")


# ------------------------------------------------------------------ reads
@router.get("/overview")
async def overview(days_back: int = Query(7, ge=1, le=365), topic: Optional[str] = ScopeParam,
                   session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).overview, days_back)


@router.get("/narratives")
async def narratives(days_back: int = Query(30, ge=1, le=365), language: Optional[str] = None,
                     stance: Optional[str] = None, limit: int = Query(100, ge=1, le=500),
                     topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    if language and language not in LANGUAGES:
        raise HTTPException(400, "language must be one of de, fr, it, en")
    if stance and stance not in STANCES:
        raise HTTPException(400, "stance must be promotes, reports or debunks")
    return await asyncio.to_thread(_svc(topic).narratives, days_back, language, stance, limit)


@router.get("/narratives/{narrative_id}")
async def narrative_detail(narrative_id: int, topic: Optional[str] = ScopeParam,
                           session=Depends(verify_session_api)):
    res = await asyncio.to_thread(_svc(topic).narrative_detail, narrative_id)
    if not res:
        raise HTTPException(404, "narrative not found")
    return res


@router.get("/sources")
async def sources(days_back: int = Query(30, ge=1, le=365), topic: Optional[str] = ScopeParam,
                  session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).sources, days_back)


@router.get("/cooccurrence")
async def cooccurrence(days_back: int = Query(30, ge=1, le=365), topic: Optional[str] = ScopeParam,
                       session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).cooccurrence, days_back)


@router.get("/targets")
async def targets(days_back: int = Query(30, ge=1, le=365), topic: Optional[str] = ScopeParam,
                  session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).targets, days_back)


@router.get("/techniques")
async def techniques(days_back: int = Query(30, ge=1, le=365), topic: Optional[str] = ScopeParam,
                     session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).techniques, days_back)


@router.get("/languages")
async def languages(days_back: int = Query(30, ge=1, le=365), topic: Optional[str] = ScopeParam,
                    session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).languages, days_back)


@router.get("/calendar")
async def calendar(days_back: int = Query(60, ge=1, le=365), days_ahead: int = Query(420, ge=1, le=800),
                   topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).calendar, days_back, days_ahead)


@router.get("/responses")
async def responses(days_back: int = Query(90, ge=1, le=365), topic: Optional[str] = ScopeParam,
                    session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).responses, days_back)


@router.get("/articles")
async def articles(days_back: int = Query(30, ge=1, le=365), language: Optional[str] = None,
                   tier: Optional[str] = None, attribution: Optional[str] = None,
                   technique: Optional[str] = None, page: int = Query(1, ge=1),
                   per_page: int = Query(25, ge=1, le=100), topic: Optional[str] = ScopeParam,
                   session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).articles, days_back, language, tier, attribution, technique, page, per_page)


@router.get("/how-it-works")
async def how_it_works(topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    """Live inventory of what this watch collects from, and the settings each
    pipeline stage runs on."""
    return await asyncio.to_thread(_svc(topic).how_it_works)


@router.get("/scopes")
async def scopes(session=Depends(verify_session_api)):
    return {"scopes": list_scopes(), "default": DEFAULT_TOPIC}


@router.get("/vocab")
async def vocab(topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    t = topic if topic in SCOPES else DEFAULT_TOPIC
    sc = scope(t)
    return {"topic": t, "label": sc["label"], "blurb": sc["blurb"],
            "languages": LANGUAGES, "stances": STANCES,
            "attributions": ATTRIBUTIONS, "techniques": TECHNIQUES, "tiers": TIERS,
            "calendar": [{"date": d.isoformat(), "label": l} for d, l in sc["calendar"]]}


# ---------------------------------------------------------------- briefs
@router.get("/brief")
async def latest_brief(topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    return await asyncio.to_thread(_svc(topic).latest_brief)


@router.post("/brief")
async def generate_brief(req: BriefRequest, session=Depends(verify_session_api)):
    try:
        return await _svc(req.topic).generate_brief(req.days_back, req.model)
    except Exception as e:
        logger.error("Swiss disinfo brief failed: %s", e, exc_info=True)
        raise HTTPException(500, f"brief generation failed: {e}")


# ------------------------------------------------------------ processing
async def _process_background(batch_size: int, model: str, process_all: bool,
                              topic: Optional[str] = None) -> None:
    global _processing
    _processing.update({"running": True, "processed": 0, "on_topic": 0, "narratives_created": 0,
                        "errors": 0, "started_at": datetime.now().isoformat(), "finished_at": None, "error": None})
    try:
        def progress(i, total):
            _processing["processed"] = i
            _processing["total"] = total
        stats = await _svc(topic).process_batch(limit=batch_size, model_name=model,
                                                process_all=process_all, progress=progress)
        _processing.update({k: stats[k] for k in ("processed", "on_topic", "narratives_created", "errors", "total")})
        try:
            await asyncio.to_thread(_svc(topic).evaluate_alerts)
        except Exception as e:
            logger.warning("Swiss disinfo alerts after manual run failed: %s", e)
    except Exception as e:
        logger.error("Swiss disinfo background processing failed: %s", e, exc_info=True)
        _processing["error"] = str(e)
    finally:
        _processing["running"] = False
        _processing["finished_at"] = datetime.now().isoformat()


@router.get("/process-articles/status")
async def process_status(session=Depends(verify_session_api)):
    return _processing


@router.post("/process-articles")
async def process_articles(req: ProcessRequest, background_tasks: BackgroundTasks,
                           session=Depends(verify_session_api)):
    if _processing["running"]:
        return {"status": "running", **_processing}
    pending = await asyncio.to_thread(_svc(req.topic).get_unprocessed_articles,
                                      req.batch_size, req.process_all)
    if not pending:
        return {"status": "complete", "message": "No articles to process", "total": 0}
    background_tasks.add_task(_process_background, req.batch_size, req.model,
                              req.process_all, req.topic)
    return {"status": "started", "total": len(pending),
            "message": f"Processing {len(pending)} articles in the background"}


@router.get("/unprocessed-count")
async def unprocessed_count(topic: Optional[str] = ScopeParam, session=Depends(verify_session_api)):
    rows = await asyncio.to_thread(_svc(topic).get_unprocessed_articles, 1000, False)
    return {"count": len(rows)}


# -------------------------------------------------------------- schedules
def _schedule_rows():
    conn = get_database_instance()._temp_get_connection()
    try:
        rows = conn.execute(text("SELECT * FROM sd_schedules ORDER BY id")).fetchall()
        out = []
        for r in rows:
            m = dict(r._mapping)
            for k in ("last_run_at", "next_run_at", "created_at", "updated_at"):
                if m.get(k):
                    m[k] = m[k].isoformat()
            if m.get("schedule_time"):
                m["schedule_time"] = m["schedule_time"].strftime("%H:%M")
            out.append(m)
        return out
    finally:
        conn.close()


@router.get("/schedules")
async def list_schedules(session=Depends(verify_session_api)):
    return {"schedules": await asyncio.to_thread(_schedule_rows), "monitor": get_task_status()}


@router.post("/schedules")
async def create_schedule(s: ScheduleIn, session=Depends(verify_session_api)):
    def _create():
        conn = get_database_instance()._temp_get_connection()
        try:
            next_run = calculate_next_run(s.schedule_type, s.schedule_interval, s.schedule_unit, s.schedule_time)
            sid = conn.execute(text("""
                INSERT INTO sd_schedules (name, batch_size, model, process_all, schedule_enabled, schedule_type,
                    schedule_interval, schedule_unit, schedule_time, notify_on_complete, next_run_at)
                VALUES (:name, :bs, :model, :pa, :en, :st, :si, :su, CAST(:tm AS time), :notify, :nr)
                RETURNING id
            """), {"name": s.name, "bs": s.batch_size, "model": s.model, "pa": s.process_all,
                   "en": s.schedule_enabled, "st": s.schedule_type, "si": s.schedule_interval,
                   "su": s.schedule_unit, "tm": s.schedule_time, "notify": s.notify_on_complete,
                   "nr": next_run}).fetchone()[0]
            conn.commit()
            return int(sid)
        finally:
            conn.close()
    return {"id": await asyncio.to_thread(_create)}


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, s: ScheduleIn, session=Depends(verify_session_api)):
    def _update():
        conn = get_database_instance()._temp_get_connection()
        try:
            next_run = calculate_next_run(s.schedule_type, s.schedule_interval, s.schedule_unit, s.schedule_time)
            n = conn.execute(text("""
                UPDATE sd_schedules SET name=:name, batch_size=:bs, model=:model, process_all=:pa,
                    schedule_enabled=:en, schedule_type=:st, schedule_interval=:si, schedule_unit=:su,
                    schedule_time=CAST(:tm AS time), notify_on_complete=:notify, next_run_at=:nr, updated_at=NOW()
                WHERE id=:id
            """), {"id": schedule_id, "name": s.name, "bs": s.batch_size, "model": s.model, "pa": s.process_all,
                   "en": s.schedule_enabled, "st": s.schedule_type, "si": s.schedule_interval,
                   "su": s.schedule_unit, "tm": s.schedule_time, "notify": s.notify_on_complete,
                   "nr": next_run}).rowcount
            conn.commit()
            return n
        finally:
            conn.close()
    if not await asyncio.to_thread(_update):
        raise HTTPException(404, "schedule not found")
    return {"ok": True}


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, session=Depends(verify_session_api)):
    def _delete():
        conn = get_database_instance()._temp_get_connection()
        try:
            n = conn.execute(text("DELETE FROM sd_schedules WHERE id=:id"), {"id": schedule_id}).rowcount
            conn.commit()
            return n
        finally:
            conn.close()
    if not await asyncio.to_thread(_delete):
        raise HTTPException(404, "schedule not found")
    return {"ok": True}


@router.post("/schedules/{schedule_id}/run")
async def run_schedule(schedule_id: int, session=Depends(verify_session_api)):
    return await run_schedule_now(get_database_instance(), schedule_id)
