"""Deep research runs as server-side jobs (docs/AUSPEX_RESEARCH_JOBS_SPEC.md).

A research run used to live inside one HTTP response: the browser read a
Server-Sent Events stream for ten to twenty minutes and, when that connection
closed for any reason, Starlette cancelled the generator and the run died with
no log line. Here the run is an ``asyncio`` task owned by the process. The
stream is a window onto it: any number of readers can attach, leave and
reattach, and the report is saved to the chat whether or not anyone watches.

The registry keeps every job in this process in memory and mirrors its state
into a ``background_tasks`` row named ``deep_research`` so the restart gate
sees it and the startup reconciliation closes it as interrupted after a
restart. Writer ``chunk`` events are folded into one growing string; the other
events are kept (capped) for replay.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TASK_NAME = "deep_research"
HISTORY_LIMIT = 400
KEEP_FINISHED_SECONDS = 2 * 3600
PERSIST_EVERY_SECONDS = 5.0
TERMINAL = ("completed", "failed", "cancelled")

SaveMessage = Callable[[str, str, Dict[str, Any]], Optional[int]]
Persist = Callable[["ResearchJob"], None]


def user_name(user: Any) -> str:
    """The plain username behind a session's ``user`` value, which is a string
    for password logins and a dict for OAuth logins."""
    if isinstance(user, dict):
        return str(user.get("username") or user.get("email") or user.get("name") or "")
    return str(user or "")


@dataclass
class ResearchJob:
    id: str
    username: str
    query: str
    topic: str
    chat_id: Optional[int]
    status: str = "pending"
    stage: Optional[str] = None
    message: Optional[str] = None
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    report_text: str = ""
    report: Optional[str] = None
    report_message_id: Optional[int] = None
    error: Optional[str] = None
    subscribers: List[asyncio.Queue] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    last_persist: float = 0.0

    @property
    def done(self) -> bool:
        return self.status in TERMINAL

    def final_event(self) -> Dict[str, Any]:
        if self.status == "completed":
            return {"done": True, "job_id": self.id}
        return {"error": self.error or self.status, "stage": "error", "job_id": self.id}

    def status_dict(self, with_report: bool = True) -> Dict[str, Any]:
        d = {
            "job_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "query": self.query,
            "topic": self.topic,
            "chat_id": self.chat_id,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "report_message_id": self.report_message_id,
            "report_chars": len(self.report or self.report_text or ""),
        }
        if with_report and self.status == "completed":
            d["report"] = self.report or self.report_text or ""
        return d


_JOBS: Dict[str, ResearchJob] = {}


# ---------------------------------------------------------------------------
# Persistence (background_tasks row)
# ---------------------------------------------------------------------------

def _persist_row(job: ResearchJob) -> None:
    """Mirror the job into ``background_tasks``. Same shape the task manager
    writes, so the restart gate and the startup reconciliation treat it like
    any other task."""
    from app.database import get_database_instance

    result = None
    if job.done:
        result = json.dumps({
            "report_chars": len(job.report or ""),
            "report_message_id": job.report_message_id,
            "chat_id": job.chat_id,
        })
    current = f"{job.stage or job.status}: {job.message}" if job.message else (job.stage or job.status)
    get_database_instance().facade.save_background_task(
        task_id=job.id,
        name=TASK_NAME,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.finished_at,
        progress=round(float(job.progress or 0.0) * 100, 1),
        total_items=0,
        processed_items=0,
        current_item=(current or "")[:200],
        result=result,
        error=job.error,
        metadata=json.dumps({
            "query": job.query,
            "topic": job.topic,
            "chat_id": job.chat_id,
            "username": job.username,
        }),
    )


def _persist(job: ResearchJob, persist: Optional[Persist], force: bool = False) -> None:
    now = time.monotonic()
    if not force and now - job.last_persist < PERSIST_EVERY_SECONDS:
        return
    job.last_persist = now
    try:
        (persist or _persist_row)(job)
    except Exception as exc:  # noqa: BLE001 - a ledger failure must not stop the run
        logger.warning("deep research job %s: could not persist state: %s", job.id, exc)


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------

def _publish(job: ResearchJob, event: Any) -> None:
    for q in list(job.subscribers):
        try:
            q.put_nowait(event)
        except Exception:  # noqa: BLE001
            pass


def _record(job: ResearchJob, update: Any, save_message: Optional[SaveMessage],
            persist: Optional[Persist]) -> None:
    if not isinstance(update, dict):
        return
    stage = update.get("stage")
    chunk = update.get("chunk")
    if isinstance(chunk, str):
        # Writer text: fold into one string, never into the history.
        job.report_text += chunk
        if isinstance(stage, str):
            job.stage = stage
        _publish(job, update)
        return

    if isinstance(stage, str):
        stage_changed = stage != job.stage
        job.stage = stage
    else:
        stage_changed = False
    msg = update.get("message") or update.get("status")
    if isinstance(msg, str) and msg:
        job.message = msg
    prog = update.get("progress")
    if isinstance(prog, (int, float)):
        job.progress = max(job.progress, float(prog)) if prog <= 1.0 else job.progress

    if stage == "complete" and isinstance(update.get("report"), str) and update["report"]:
        job.report = update["report"]
        if save_message:
            try:
                meta = {"deep_research": True, "job_id": job.id}
                extra = update.get("metadata")
                if isinstance(extra, dict):
                    meta.update(extra)
                job.report_message_id = save_message("assistant", job.report, meta)
            except Exception as exc:  # noqa: BLE001
                logger.warning("deep research job %s: could not save report to chat %s: %s",
                               job.id, job.chat_id, exc)

    if len(job.history) < HISTORY_LIMIT:
        job.history.append(update)
    _publish(job, update)
    _persist(job, persist, force=stage_changed)


async def _run(job: ResearchJob, run: Callable[[], AsyncGenerator[Any, None]],
               save_message: Optional[SaveMessage], persist: Optional[Persist]) -> None:
    job.status = "running"
    job.started_at = datetime.now()
    _persist(job, persist, force=True)
    if save_message:
        try:
            save_message("user", job.query, {"deep_research": True, "job_id": job.id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("deep research job %s: could not save question to chat %s: %s",
                           job.id, job.chat_id, exc)
    try:
        async for update in run():
            _record(job, update, save_message, persist)
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.error = job.error or "The run was cancelled before it finished."
        _finish(job, persist)
        raise
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = str(exc) or exc.__class__.__name__
        logger.error("deep research job %s failed: %s", job.id, exc, exc_info=True)
        _finish(job, persist)
        return
    job.status = "completed"
    job.progress = 1.0
    if job.report is None and job.report_text:
        job.report = job.report_text
    _finish(job, persist)


def _finish(job: ResearchJob, persist: Optional[Persist]) -> None:
    job.finished_at = datetime.now()
    _persist(job, persist, force=True)
    _publish(job, job.final_event())
    _publish(job, None)  # end marker for live readers
    try:
        asyncio.get_running_loop().call_later(KEEP_FINISHED_SECONDS, _JOBS.pop, job.id, None)
    except RuntimeError:
        pass
    logger.info("deep research job %s %s: stage=%s report_chars=%d chat=%s user=%s",
                job.id, job.status, job.stage, len(job.report or ""), job.chat_id, job.username)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(*, user: Any, query: str, topic: str, chat_id: Optional[int],
          run: Callable[[], AsyncGenerator[Any, None]],
          save_message: Optional[SaveMessage] = None,
          persist: Optional[Persist] = None) -> ResearchJob:
    """Start a research job on the running loop and return it at once.

    ``run`` builds the research generator (so the registry never imports the
    research service); ``save_message(role, content, metadata)`` writes a chat
    message and returns its id; ``persist`` replaces the ``background_tasks``
    writer in tests.
    """
    job = ResearchJob(id=str(uuid.uuid4()), username=user_name(user), query=query,
                      topic=topic, chat_id=chat_id)
    _JOBS[job.id] = job
    job.task = asyncio.get_running_loop().create_task(
        _run(job, run, save_message, persist), name=f"deep-research-{job.id[:8]}")
    logger.info("deep research job %s started: topic=%r chat=%s user=%s query=%r",
                job.id, topic, chat_id, job.username, (query or "")[:80])
    return job


def get(job_id: str) -> Optional[ResearchJob]:
    return _JOBS.get(job_id)


def list_for(username: str, chat_id: Optional[int] = None, active_only: bool = False) -> List[ResearchJob]:
    out = []
    for job in _JOBS.values():
        if job.username != username:
            continue
        if chat_id is not None and job.chat_id != chat_id:
            continue
        if active_only and job.done:
            continue
        out.append(job)
    return sorted(out, key=lambda j: j.created_at)


def status_from_row(row: Any) -> Optional[Dict[str, Any]]:
    """A status dict from a ``background_tasks`` row, for a job this process
    no longer holds (after a restart). Column order as ``get_background_task``
    selects it."""
    if not row or row[1] != TASK_NAME:
        return None
    meta = row[12] or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    result = row[10] or {}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            result = {}
    status = row[2]
    current = row[9] or ""
    stage, _, message = current.partition(": ")
    return {
        "job_id": row[0],
        "status": status,
        "stage": stage or None,
        "message": message or None,
        "progress": (row[6] or 0.0) / 100.0,
        "query": meta.get("query"),
        "topic": meta.get("topic"),
        "chat_id": meta.get("chat_id"),
        "username": meta.get("username"),
        "created_at": row[3].isoformat() if row[3] else None,
        "started_at": row[4].isoformat() if row[4] else None,
        "finished_at": row[5].isoformat() if row[5] else None,
        "error": row[11],
        "report_message_id": result.get("report_message_id"),
        "report_chars": result.get("report_chars", 0),
        "from_db": True,
    }


async def events(job: ResearchJob, replay: bool = True) -> AsyncGenerator[Dict[str, Any], None]:
    """Follow a job: the stage events so far, the report text so far, then
    live events until the job ends. A reader leaving stops only itself."""
    # Snapshot and subscribe with no await in between, so nothing is missed
    # or repeated between the replay and the live tail.
    history = list(job.history) if replay else []
    text = job.report_text if replay else ""
    done = job.done
    q: asyncio.Queue = asyncio.Queue()
    if not done:
        job.subscribers.append(q)
    try:
        yield {"stage": "job", "job_id": job.id, "status": job.status, "chat_id": job.chat_id}
        for e in history:
            yield e
        if text:
            yield {"stage": "writing", "status": "writing", "chunk": text, "replayed": True}
        if done:
            yield job.final_event()
            return
        while True:
            item = await q.get()
            if item is None:
                return
            yield item
    finally:
        if q in job.subscribers:
            job.subscribers.remove(q)
