"""The deep research job registry (docs/AUSPEX_RESEARCH_JOBS_SPEC.md).

A fake research generator stands in for DeepResearchService.conduct_research.
No database: the persist hook records rows in a list.
"""

import asyncio
from datetime import datetime

import pytest

from app.services import auspex_research_jobs as jobs


async def _collect(agen, limit=1000):
    out = []
    async for e in agen:
        out.append(e)
        if len(out) >= limit:
            break
    return out


def _make_run(gate: asyncio.Event = None, fail_after: int = None):
    """A research run: planning, searching, three writer chunks, complete."""
    async def run():
        yield {"stage": "planning", "status": "started", "progress": 0.1}
        yield {"stage": "planning", "status": "completed", "progress": 0.2, "objectives_count": 3}
        if gate is not None:
            await gate.wait()
        yield {"stage": "searching", "status": "started", "progress": 0.3}
        if fail_after == 3:
            raise RuntimeError("Bedrock said no")
        for word in ("# Report\n", "First. ", "Second."):
            yield {"stage": "writing", "status": "writing", "progress": 0.9, "chunk": word}
        yield {"stage": "complete", "status": "completed", "progress": 1.0,
               "report": "# Report\nFirst. Second.", "metadata": {"sources": 9}}
    return run


def _recorder():
    rows, messages = [], []

    def persist(job):
        rows.append((job.status, job.stage, job.progress))

    def save_message(role, content, metadata):
        messages.append((role, content, metadata))
        return len(messages)

    return rows, messages, persist, save_message


@pytest.fixture(autouse=True)
def _clear_registry():
    jobs._JOBS.clear()
    yield
    jobs._JOBS.clear()


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_job_runs_to_completion_and_saves_both_chat_messages():
    async def scenario():
        rows, messages, persist, save = _recorder()
        job = jobs.start(user={"username": "ana", "role": "analyst"}, query="ASML?", topic="ASML Watch",
                         chat_id=7, run=_make_run(), save_message=save, persist=persist)
        assert job.username == "ana"
        await job.task
        return job, rows, messages

    job, rows, messages = run_async(scenario())
    assert job.status == "completed"
    assert job.report == "# Report\nFirst. Second."
    assert job.report_text == "# Report\nFirst. Second."
    assert job.report_message_id == 2
    assert [m[0] for m in messages] == ["user", "assistant"]
    assert messages[0][1] == "ASML?" and messages[0][2]["job_id"] == job.id
    assert messages[1][2]["deep_research"] is True and messages[1][2]["sources"] == 9
    # history keeps stage events only, never writer chunks
    assert all("chunk" not in e for e in job.history)
    assert rows[0][0] == "running" and rows[-1][0] == "completed"
    d = job.status_dict()
    assert d["report"] == job.report and d["report_message_id"] == 2 and d["status"] == "completed"


def test_live_reader_sees_job_event_then_everything_then_done():
    async def scenario():
        gate = asyncio.Event()
        rows, messages, persist, save = _recorder()
        job = jobs.start(user="bob", query="q", topic="t", chat_id=None,
                         run=_make_run(gate=gate), save_message=None, persist=persist)
        reader = asyncio.ensure_future(_collect(jobs.events(job)))
        await asyncio.sleep(0.01)
        gate.set()
        got = await asyncio.wait_for(reader, 5)
        await job.task
        return got

    got = run_async(scenario())
    assert got[0]["stage"] == "job" and got[0]["status"] in ("pending", "running")
    stages = [e.get("stage") for e in got]
    assert stages[1:3] == ["planning", "planning"]
    assert "".join(e["chunk"] for e in got if "chunk" in e) == "# Report\nFirst. Second."
    assert got[-1] == {"done": True, "job_id": got[0]["job_id"]}


def test_reader_that_attaches_late_gets_replay_then_live_tail():
    async def scenario():
        gate = asyncio.Event()
        rows, messages, persist, save = _recorder()
        job = jobs.start(user="bob", query="q", topic="t", chat_id=None,
                         run=_make_run(gate=gate), persist=persist)
        await asyncio.sleep(0.01)          # planning events happen, run blocks on the gate
        assert len(job.history) == 2
        reader = asyncio.ensure_future(_collect(jobs.events(job)))
        await asyncio.sleep(0.01)
        gate.set()
        got = await asyncio.wait_for(reader, 5)
        await job.task
        return got

    got = run_async(scenario())
    stages = [e.get("stage") for e in got]
    assert stages[:3] == ["job", "planning", "planning"]        # replayed
    assert "searching" in stages and stages[-1] is None            # live tail, then done
    assert got[-1]["done"] is True
    # no event twice
    assert stages.count("searching") == 1


def test_reader_leaving_does_not_stop_the_job():
    async def scenario():
        gate = asyncio.Event()
        rows, messages, persist, save = _recorder()
        job = jobs.start(user="bob", query="q", topic="t", chat_id=3,
                         run=_make_run(gate=gate), save_message=save, persist=persist)
        agen = jobs.events(job)
        first = await agen.__anext__()
        assert first["stage"] == "job"
        await agen.aclose()                 # the browser went away
        assert job.subscribers == []
        gate.set()
        await asyncio.wait_for(job.task, 5)
        return job, messages

    job, messages = run_async(scenario())
    assert job.status == "completed"
    assert messages[-1][0] == "assistant" and messages[-1][1].startswith("# Report")


def test_failure_is_recorded_and_streamed():
    async def scenario():
        rows, messages, persist, save = _recorder()
        job = jobs.start(user="bob", query="q", topic="t", chat_id=None,
                         run=_make_run(fail_after=3), persist=persist)
        got = await asyncio.wait_for(_collect(jobs.events(job)), 5)
        await job.task
        return job, got, rows

    job, got, rows = run_async(scenario())
    assert job.status == "failed" and "Bedrock said no" in job.error
    assert got[-1]["stage"] == "error" and "Bedrock said no" in got[-1]["error"]
    assert rows[-1][0] == "failed"
    assert "report" not in job.status_dict()


def test_finished_job_replays_and_ends_at_once():
    async def scenario():
        rows, messages, persist, save = _recorder()
        job = jobs.start(user="bob", query="q", topic="t", chat_id=None, run=_make_run(), persist=persist)
        await job.task
        return job, await _collect(jobs.events(job))

    job, got = run_async(scenario())
    assert got[0]["status"] == "completed"
    assert any(e.get("replayed") for e in got)
    assert got[-1]["done"] is True
    assert job.subscribers == []


def test_list_for_and_user_name():
    async def scenario():
        gate = asyncio.Event()
        rows, messages, persist, save = _recorder()
        a = jobs.start(user="ana", query="1", topic="t", chat_id=1, run=_make_run(gate=gate), persist=persist)
        b = jobs.start(user={"email": "bob@x"}, query="2", topic="t", chat_id=2, run=_make_run(), persist=persist)
        await b.task
        active = jobs.list_for("ana", chat_id=1, active_only=True)
        others = jobs.list_for("bob@x", active_only=True)
        gate.set()
        await a.task
        return a, b, active, others

    a, b, active, others = run_async(scenario())
    assert [j.id for j in active] == [a.id]
    assert others == []
    assert jobs.user_name({"username": "x"}) == "x" and jobs.user_name(None) == ""


def test_status_from_row_after_restart():
    row = ("abc", "deep_research", "failed", datetime(2026, 10, 16, 14, 40), datetime(2026, 10, 16, 14, 40),
           datetime(2026, 10, 16, 14, 52), 45.0, 0, 0, "searching: started", None,
           "Interrupted: the process running this task stopped before it finished.",
           {"query": "q", "topic": "t", "chat_id": 5, "username": "ana"})
    d = jobs.status_from_row(row)
    assert d["status"] == "failed" and d["stage"] == "searching" and d["message"] == "started"
    assert d["progress"] == 0.45 and d["chat_id"] == 5 and d["from_db"] is True
    assert jobs.status_from_row(("x", "bulk_analysis") + row[2:]) is None
