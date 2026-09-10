"""Server-side emerging-topics detection jobs.

A detection used to run inside the browser's request: the route pulled
updates from the service generator and wrote them to the SSE stream, so when
the page was reloaded the connection dropped, the generator was cancelled, and
the run in progress was marked failed. A batch over eleven topics is 45
minutes on one request, which made that a common way to lose work.

A job here runs the same generator as an ``asyncio`` task owned by the
process, keeps every update it has produced, and lets any number of clients
subscribe: a subscriber gets the backlog from the index it asks for, then
waits for new updates until the job reaches a terminal state. A client going
away detaches nothing but itself.

Jobs live in memory. A service restart ends them the same way it always did
(the generator's cancellation path marks the run failed); the run rows in
``detection_runs`` remain the durable record.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_KEPT_JOBS = 20
TERMINAL_EVENTS = ("complete", "error")


class DetectionJob:
    def __init__(self, kind: str, scope: str, request: Dict[str, Any]):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind              # "single" | "batch"
        self.scope = scope            # topic name or "<all>"
        self.request = request
        self.status = "running"       # running | completed | partial | failed
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.updates: List[Dict[str, Any]] = []
        self.latest: Optional[Dict[str, Any]] = None
        self._changed = asyncio.Condition()
        self._task: Optional[asyncio.Task] = None

    # -- state -------------------------------------------------------------

    @property
    def done(self) -> bool:
        return self.status != "running"

    def summary(self) -> Dict[str, Any]:
        latest = dict(self.latest or {})
        latest.pop("emerging_topics", None)   # can be large; fetch via the events stream
        return {
            "job_id": self.id,
            "kind": self.kind,
            "scope": self.scope,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": round((self.finished_at or time.time()) - self.started_at, 1),
            "update_count": len(self.updates),
            "latest": latest,
        }

    async def _publish(self, update: Dict[str, Any]) -> None:
        update = dict(update)
        update["job_id"] = self.id
        update["seq"] = len(self.updates)
        update["elapsed_seconds"] = round(time.time() - self.started_at, 1)
        self.updates.append(update)
        self.latest = update
        async with self._changed:
            self._changed.notify_all()

    async def _finish(self, status: str) -> None:
        self.status = status
        self.finished_at = time.time()
        async with self._changed:
            self._changed.notify_all()

    # -- running -----------------------------------------------------------

    async def run(self, generator: AsyncIterator[Dict[str, Any]]) -> None:
        final = "completed"
        saw_error = False
        try:
            async for update in generator:
                event = update.get("event")
                if event == "error":
                    saw_error = True
                await self._publish(update)
                if event == "complete":
                    final = update.get("status") or ("partial" if saw_error else "completed")
            if self.latest is None or self.latest.get("event") not in TERMINAL_EVENTS:
                # The generator ended without a terminal frame; say so.
                await self._publish({
                    "event": "error" if saw_error else "complete",
                    "status": "failed" if saw_error else "completed",
                    "progress": 100,
                    "message": "Detection ended" + (" with errors" if saw_error else ""),
                })
                final = "failed" if saw_error else "completed"
            elif self.latest.get("event") == "error":
                final = "failed"
        except asyncio.CancelledError:
            await self._publish({"event": "error", "status": "failed", "code": "cancelled",
                                 "message": "Detection cancelled (service shutting down)"})
            final = "failed"
            raise
        except Exception as exc:
            logger.exception("Detection job %s crashed", self.id)
            await self._publish({"event": "error", "status": "failed", "code": "detection_failed",
                                 "message": f"{exc.__class__.__name__}: {exc}"})
            final = "failed"
        finally:
            await self._finish(final)

    # -- subscribing -------------------------------------------------------

    async def subscribe(self, after: int = 0) -> AsyncIterator[Dict[str, Any]]:
        """Yield updates from index ``after`` onward until the job is done.

        Emits a heartbeat every 15 s while nothing new has happened so the
        client can show elapsed time and proxies do not time the stream out.
        """
        index = max(0, after)
        while True:
            while index < len(self.updates):
                yield self.updates[index]
                index += 1
            if self.done:
                return
            async with self._changed:
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=15)
                except asyncio.TimeoutError:
                    yield {
                        "event": "heartbeat",
                        "job_id": self.id,
                        "elapsed_seconds": round(time.time() - self.started_at, 1),
                        "status": self.status,
                    }


class DetectionJobRegistry:
    def __init__(self):
        self._jobs: "OrderedDict[str, DetectionJob]" = OrderedDict()

    def start(self, kind: str, scope: str, request: Dict[str, Any],
              generator: AsyncIterator[Dict[str, Any]]) -> DetectionJob:
        job = DetectionJob(kind, scope, request)
        job._task = asyncio.create_task(job.run(generator), name=f"emerging-topics-job-{job.id}")
        self._jobs[job.id] = job
        self._prune()
        logger.info("Detection job %s started (%s, scope=%s)", job.id, kind, scope)
        return job

    def get(self, job_id: str) -> Optional[DetectionJob]:
        return self._jobs.get(job_id)

    def active(self) -> List[DetectionJob]:
        return [j for j in self._jobs.values() if not j.done]

    def _prune(self) -> None:
        finished = [jid for jid, j in self._jobs.items() if j.done]
        while len(self._jobs) > MAX_KEPT_JOBS and finished:
            self._jobs.pop(finished.pop(0), None)


registry = DetectionJobRegistry()
