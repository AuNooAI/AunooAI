"""Swiss election disinformation monitor: scheduled processing.

Same shape as the GeoHotspots monitor: a DB-driven schedules table
(sd_schedules), a loop that runs due schedules every minute, and a
run-now helper for the routes. Each run extracts the new approved
articles, evaluates the four alert rules and keeps the vote calendar
seeded. calculate_next_run is shared with the GeoHotspots monitor.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.database import Database, get_database_instance
from app.tasks.geopolitical_hotspots_monitor import calculate_next_run  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)

_background_task_status: Dict[str, Any] = {
    "running": False, "is_checking": False, "last_check_time": None,
    "schedules_checked": 0, "schedules_run": 0, "last_error": None,
}


def get_task_status() -> Dict[str, Any]:
    s = dict(_background_task_status)
    if s["last_check_time"]:
        s["last_check_time"] = s["last_check_time"].isoformat()
    return s


class SwissDisinfoMonitor:
    def __init__(self, db: Database):
        self.db = db
        self.running: set = set()

    def get_due_schedules(self) -> List[Dict[str, Any]]:
        try:
            conn = self.db._temp_get_connection()
            rows = conn.execute(text("""
                SELECT id, name, topic, batch_size, model, process_all, schedule_type,
                       schedule_interval, schedule_unit, schedule_time, notify_on_complete, run_count
                FROM sd_schedules
                WHERE schedule_enabled = true AND (next_run_at IS NULL OR next_run_at <= NOW())
                ORDER BY next_run_at ASC NULLS FIRST
            """)).fetchall()
            conn.close()
            return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error("Swiss disinfo: could not read due schedules: %s", e)
            return []

    def update_status(self, schedule_id: int, status: str, error: Optional[str] = None,
                      next_run_at: Optional[datetime] = None, processed: int = 0, created: int = 0) -> None:
        try:
            conn = self.db._temp_get_connection()
            conn.execute(text("""
                UPDATE sd_schedules SET
                    last_run_at = NOW(), last_run_status = :status, last_run_error = :error,
                    next_run_at = COALESCE(:next_run, next_run_at),
                    last_run_articles_processed = :processed, last_run_narratives_created = :created,
                    run_count = run_count + CASE WHEN :status = 'success' THEN 1 ELSE 0 END,
                    updated_at = NOW()
                WHERE id = :id
            """), {"id": schedule_id, "status": status, "error": error, "next_run": next_run_at,
                   "processed": processed, "created": created})
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Swiss disinfo: could not update schedule %s: %s", schedule_id, e)

    async def run_schedule(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.swiss_disinfo_service import DEFAULT_TOPIC, get_swiss_disinfo_service, scope
        sid = schedule["id"]
        result: Dict[str, Any] = {"success": False, "schedule_id": sid, "schedule_name": schedule["name"],
                                  "articles_processed": 0, "narratives_created": 0, "alerts": 0, "error": None}
        if sid in self.running:
            logger.info("Swiss disinfo schedule %s already running", schedule["name"])
            return result
        self.running.add(sid)
        self.update_status(sid, "running")
        try:
            svc = get_swiss_disinfo_service(schedule.get("topic") or DEFAULT_TOPIC)
            await asyncio.to_thread(svc.ensure_calendar)
            stats = await svc.process_batch(limit=int(schedule.get("batch_size") or 50),
                                            model_name=schedule.get("model") or "bedrock-kimi-k2-5",
                                            process_all=bool(schedule.get("process_all")))
            alerts = await asyncio.to_thread(svc.evaluate_alerts)
            result.update({"success": True, "articles_processed": stats["processed"],
                           "narratives_created": stats["narratives_created"], "alerts": len(alerts)})
            next_run = calculate_next_run(schedule.get("schedule_type"), schedule.get("schedule_interval"),
                                          schedule.get("schedule_unit"), schedule.get("schedule_time"))
            self.update_status(sid, "success", next_run_at=next_run,
                               processed=stats["processed"], created=stats["narratives_created"])
            if schedule.get("notify_on_complete") and stats["processed"]:
                try:
                    self.db.facade.create_notification(
                        username=None, type="swiss_disinfo",
                        title=f"{scope(svc.topic)['label']} run",
                        message=(f"Processed {stats['processed']} articles, {stats['on_topic']} on topic, "
                                 f"{stats['narratives_created']} new narratives, {len(alerts)} alerts."),
                        link="/explore?tab=swiss_disinfo")
                except Exception as e:
                    logger.warning("Swiss disinfo notification failed: %s", e)
        except Exception as e:
            logger.error("Swiss disinfo schedule %s failed: %s", schedule["name"], e, exc_info=True)
            result["error"] = str(e)
            next_run = calculate_next_run(schedule.get("schedule_type"), schedule.get("schedule_interval"),
                                          schedule.get("schedule_unit"), schedule.get("schedule_time"))
            self.update_status(sid, "error", error=str(e)[:1000], next_run_at=next_run)
        finally:
            self.running.discard(sid)
        return result


async def run_swiss_disinfo_monitor() -> None:
    global _background_task_status
    db = Database()
    monitor = SwissDisinfoMonitor(db)
    logger.info("Swiss disinfo monitor started")
    _background_task_status["running"] = True
    while True:
        try:
            _background_task_status["is_checking"] = True
            _background_task_status["last_check_time"] = datetime.now()
            due = monitor.get_due_schedules()
            _background_task_status["schedules_checked"] = len(due)
            for schedule in due:
                try:
                    res = await monitor.run_schedule(schedule)
                    if res["success"]:
                        _background_task_status["schedules_run"] += 1
                except Exception as e:
                    logger.error("Swiss disinfo schedule error: %s", e)
            _background_task_status["last_error"] = None
        except Exception as e:
            logger.error("Swiss disinfo monitor loop error: %s", e, exc_info=True)
            _background_task_status["last_error"] = str(e)
        finally:
            _background_task_status["is_checking"] = False
        await asyncio.sleep(60)


async def run_schedule_now(db: Database, schedule_id: int) -> Dict[str, Any]:
    monitor = SwissDisinfoMonitor(db)
    try:
        conn = db._temp_get_connection()
        row = conn.execute(text("""
            SELECT id, name, topic, batch_size, model, process_all, schedule_type,
                   schedule_interval, schedule_unit, schedule_time, notify_on_complete, run_count
            FROM sd_schedules WHERE id = :id
        """), {"id": schedule_id}).mappings().first()
        conn.close()
        if not row:
            return {"success": False, "error": "Schedule not found"}
        return await monitor.run_schedule(dict(row))
    except Exception as e:
        return {"success": False, "error": str(e)}
