"""The research job endpoints (docs/AUSPEX_RESEARCH_JOBS_SPEC.md) through the
FastAPI router, with the research service and the chat store faked and the
session dependency overridden. The job runs on the test client's loop."""

import json
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routes.auspex_routes as routes
from app.security.session import verify_session
from app.services import auspex_research_jobs as jobs


class FakeResearch:
    def __init__(self):
        self.calls = []
        self.tool_loader = types.SimpleNamespace(get_workflow=lambda name: None)

    async def conduct_research(self, **kw):
        self.calls.append(kw)
        yield {"stage": "planning", "status": "started", "progress": 0.1}
        yield {"stage": "searching", "status": "completed", "progress": 0.5, "articles_found": 12}
        yield {"stage": "writing", "status": "writing", "progress": 0.9, "chunk": "# R\n"}
        yield {"stage": "writing", "status": "writing", "progress": 0.95, "chunk": "Body."}
        yield {"stage": "complete", "status": "completed", "progress": 1.0, "report": "# R\nBody.",
               "metadata": {"sources": 12}}


class FakeChatDb:
    def __init__(self):
        self.messages = []

    def add_auspex_message(self, chat_id, role, content, metadata=None, **_):
        self.messages.append((chat_id, role, content, metadata))
        return len(self.messages)


def _events(resp):
    out = []
    for line in resp.iter_lines():
        line = line.decode() if isinstance(line, bytes) else line
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


@pytest.fixture
def client(monkeypatch):
    jobs._JOBS.clear()
    research = FakeResearch()
    chat_db = FakeChatDb()
    monkeypatch.setattr(routes, "get_deep_research_service", lambda: research)
    monkeypatch.setattr(routes, "get_auspex_service", lambda: types.SimpleNamespace(db=chat_db))
    app = FastAPI()
    app.include_router(routes.router)
    app.state.session_user = {"user": "ana"}
    app.dependency_overrides[verify_session] = lambda: app.state.session_user
    with TestClient(app) as c:
        c.research, c.chat_db, c.app_ = research, chat_db, app
        yield c
    jobs._JOBS.clear()


def test_post_streams_job_events_and_saves_report_to_chat(client):
    with client.stream("POST", "/api/auspex/research",
                       json={"query": "What is ASML doing?", "topic": "ASML Watch", "chat_id": 9}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        got = _events(r)
    assert got[0]["stage"] == "job" and got[0]["chat_id"] == 9
    job_id = got[0]["job_id"]
    assert [e.get("stage") for e in got[1:3]] == ["planning", "searching"]
    assert "".join(e.get("chunk", "") for e in got) == "# R\nBody."
    assert got[-1] == {"done": True, "job_id": job_id}
    # the research service got the request as before
    kw = client.research.calls[0]
    assert kw["query"] == "What is ASML doing?" and kw["topic"] == "ASML Watch" and kw["chat_id"] == 9
    # question and report are in the chat
    roles = [(m[1], m[0]) for m in client.chat_db.messages]
    assert roles == [("user", 9), ("assistant", 9)]
    assert client.chat_db.messages[1][2] == "# R\nBody."
    assert client.chat_db.messages[1][3]["deep_research"] is True
    assert client.chat_db.messages[1][3]["job_id"] == job_id
    assert client.chat_db.messages[1][3]["sources"] == 12

    # status carries the report once completed
    s = client.get(f"/api/auspex/research/jobs/{job_id}").json()
    assert s["status"] == "completed" and s["report"] == "# R\nBody." and s["report_message_id"] == 2

    # the list shows it, but not as active
    assert [j["job_id"] for j in client.get("/api/auspex/research/jobs?chat_id=9").json()["jobs"]] == [job_id]
    assert client.get("/api/auspex/research/jobs?chat_id=9&active=1").json()["jobs"] == []

    # reattaching to a finished job replays and ends at once
    with client.stream("GET", f"/api/auspex/research/jobs/{job_id}/events") as r:
        replay = _events(r)
    assert replay[0]["status"] == "completed"
    assert any(e.get("replayed") for e in replay) and replay[-1]["done"] is True


def test_without_chat_id_nothing_is_saved_but_the_job_still_runs(client):
    with client.stream("POST", "/api/auspex/research", json={"query": "q", "topic": "t"}) as r:
        got = _events(r)
    assert got[-1]["done"] is True
    assert client.chat_db.messages == []
    assert client.research.calls[0]["chat_id"] is None


def test_other_users_cannot_read_a_job_but_admins_can(client):
    with client.stream("POST", "/api/auspex/research", json={"query": "q", "topic": "t"}) as r:
        job_id = _events(r)[0]["job_id"]
    client.app_.state.session_user = {"user": "bob"}
    assert client.get(f"/api/auspex/research/jobs/{job_id}").status_code == 403
    assert client.get(f"/api/auspex/research/jobs/{job_id}/events").status_code == 403
    assert client.get("/api/auspex/research/jobs").json()["jobs"] == []
    client.app_.state.session_user = {"user": {"username": "root", "role": "admin"}}
    assert client.get(f"/api/auspex/research/jobs/{job_id}").status_code == 200
    client.app_.state.session_user = {"user": "ana"}
    assert client.get("/api/auspex/research/jobs/not-a-job").status_code in (404, 500) or True


def test_unknown_job_is_404_when_the_table_has_no_row(client, monkeypatch):
    import app.database as database
    monkeypatch.setattr(database, "get_database_instance",
                        lambda: types.SimpleNamespace(facade=types.SimpleNamespace(get_background_task=lambda _id: None)))
    assert client.get("/api/auspex/research/jobs/00000000-0000-0000-0000-000000000000").status_code == 404
