"""A Forecast Tracker response must never mix one run with another run's state.

The tracker assesses a specific stored Three Horizons run. Before 2026-08-18 the
assessment endpoint fell back to "latest assessment for this topic" whenever the
requested run had not been assessed yet, and put that row straight into
``assessment``. The scenarios in the same response came from the *requested*
run, so the UI paired one run's scenario list with another run's verdicts. The
``scenario_idx`` values do not line up between runs, so a verdict could be shown
against, and a "mark done" could be written against, an unrelated scenario.

These tests drive the real route handlers with a stubbed facade. There is no
test database in this repo and .env points at the live tenant, so nothing here
may construct Database() — see tests/conftest.py. pytest-asyncio is not
installed either, so async handlers are driven with asyncio.run() from ordinary
sync test functions.
"""

import asyncio

import pytest
from fastapi import HTTPException

RUN_A = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_B = "bbbbbbbb-0000-0000-0000-000000000002"
TOPIC = "Quantum Advantage"

ASSESSMENT_A = {
    "id": "assess-a",
    "run_id": RUN_A,
    "topic": TOPIC,
    "scenario_verdicts": [
        {"scenario_idx": 0, "scenario_title": "Run A scenario one"},
        {"scenario_idx": 1, "scenario_title": "Run A scenario two"},
    ],
    "surprises": [{"label": "a surprise from run A"}],
}


class _Facade:
    """Only the handful of facade calls these routes make."""

    def __init__(self, assessments_by_run, runs, by_topic=None, user_scenarios=None):
        self._by_run = assessments_by_run
        self._runs = runs
        self._by_topic = by_topic or {}
        self._user_scenarios = user_scenarios or {}
        self.saved_status = []

    def get_latest_forecast_assessment(self, run_id):
        return self._by_run.get(run_id) or {}

    def get_latest_forecast_assessment_by_topic(self, topic):
        return self._by_topic.get(topic) or {}

    def get_future_horizons_analysis(self, run_id):
        return self._runs.get(run_id)

    def get_forecast_user_scenarios(self, run_id):
        return self._user_scenarios.get(run_id, [])

    def save_forecast_scenario_status(self, **kw):
        self.saved_status.append(kw)
        return dict(kw)


class _DB:
    def __init__(self, facade):
        self.facade = facade


def _install(monkeypatch, facade):
    import app.database

    monkeypatch.setattr(app.database, "get_database_instance", lambda: _DB(facade))


def _two_runs():
    """Run A assessed; run B newer, same topic, never assessed."""
    runs = {
        RUN_A: {"id": RUN_A, "topic": TOPIC, "raw_output": {"scenarios": [{}, {}]},
                "created_at": "2026-07-01T00:00:00Z"},
        RUN_B: {"id": RUN_B, "topic": TOPIC, "raw_output": {"scenarios": [{}, {}]},
                "created_at": "2026-08-01T00:00:00Z"},
    }
    return _Facade(
        assessments_by_run={RUN_A: ASSESSMENT_A},
        runs=runs,
        by_topic={TOPIC: ASSESSMENT_A},
    )


def test_unassessed_run_does_not_serve_another_runs_assessment(monkeypatch):
    """Requesting run B must not present run A's assessment as run B's."""
    from app.routes.forecast_assessment_routes import get_latest_assessment

    facade = _two_runs()
    _install(monkeypatch, facade)

    resp = asyncio.run(get_latest_assessment(RUN_B))

    assert resp["run_id"] == RUN_B
    assert resp["assessment"] is None, (
        "run B has no assessment of its own, so `assessment` must be null"
    )


def test_other_runs_assessment_is_offered_separately_and_read_only(monkeypatch):
    """The older run's assessment stays available for display, but labelled."""
    from app.routes.forecast_assessment_routes import get_latest_assessment

    facade = _two_runs()
    _install(monkeypatch, facade)

    resp = asyncio.run(get_latest_assessment(RUN_B))

    assert resp["historical_assessment"] is not None
    assert resp["historical_assessment_run_id"] == RUN_A
    assert resp["historical_read_only"] is True


def test_assessed_run_returns_its_own_assessment(monkeypatch):
    """The normal case still works: run A gets run A's assessment, no historical."""
    from app.routes.forecast_assessment_routes import get_latest_assessment

    facade = _two_runs()
    _install(monkeypatch, facade)

    resp = asyncio.run(get_latest_assessment(RUN_A))

    assert resp["assessment"] is not None
    assert resp["assessment"]["run_id"] == RUN_A
    assert resp["historical_assessment"] is None
    assert resp["historical_read_only"] is False


def test_status_write_rejects_scenario_idx_outside_the_run(monkeypatch):
    """An index carried over from another run must not mark a scenario done."""
    from app.routes.forecast_assessment_routes import (
        _ScenarioStatusRequest, patch_scenario_status,
    )

    facade = _two_runs()  # run B has 2 scenarios, 0 addendums
    _install(monkeypatch, facade)

    payload = _ScenarioStatusRequest(scenario_idx=7, status="done")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_scenario_status(RUN_B, payload))

    assert exc.value.status_code == 422
    assert not facade.saved_status, "nothing may be written when the index is invalid"


def test_status_write_rejects_promoted_scenario_from_another_run(monkeypatch):
    """Promoted scenarios stay with their own run; run B cannot mark run A's."""
    from app.routes.forecast_assessment_routes import (
        _ScenarioStatusRequest, patch_scenario_status,
    )

    facade = _two_runs()
    facade._user_scenarios = {RUN_A: [{"id": "user-scenario-from-a"}], RUN_B: []}
    _install(monkeypatch, facade)

    payload = _ScenarioStatusRequest(user_scenario_id="user-scenario-from-a", status="done")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(patch_scenario_status(RUN_B, payload))

    assert exc.value.status_code == 409
    assert not facade.saved_status


def test_status_write_accepts_a_scenario_the_run_actually_has(monkeypatch):
    """The guard must not block legitimate writes."""
    from app.routes.forecast_assessment_routes import (
        _ScenarioStatusRequest, patch_scenario_status,
    )

    facade = _two_runs()
    _install(monkeypatch, facade)

    asyncio.run(patch_scenario_status(RUN_B, _ScenarioStatusRequest(scenario_idx=1, status="done")))

    assert len(facade.saved_status) == 1
    assert facade.saved_status[0]["run_id"] == RUN_B
    assert facade.saved_status[0]["scenario_idx"] == 1


def test_article_detail_rejects_assessment_from_another_run(monkeypatch):
    """Run-scoped URLs must not serve another run's article verdicts."""
    import app.services.forecast_assessment_service as svc
    from app.routes.forecast_assessment_routes import get_assessment_articles

    facade = _two_runs()
    _install(monkeypatch, facade)
    monkeypatch.setattr(svc, "_hydrate_assessment_by_id", lambda db, aid: ASSESSMENT_A)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_assessment_articles(RUN_B, "assess-a"))

    assert exc.value.status_code == 409
    assert RUN_A in exc.value.detail


def test_scenario_draft_rejects_surprise_from_another_runs_assessment(monkeypatch):
    """A promoted scenario is an addendum to this run, so its source surprise
    has to come from this run's own assessment."""
    import app.services.forecast_assessment_service as svc
    from app.routes.forecast_assessment_routes import (
        _DraftScenarioRequest, draft_scenario_from_surprise,
    )

    facade = _two_runs()
    _install(monkeypatch, facade)
    monkeypatch.setattr(svc, "_hydrate_assessment_by_id", lambda db, aid: ASSESSMENT_A)

    payload = _DraftScenarioRequest(assessment_id="assess-a", surprise_index=0)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(draft_scenario_from_surprise(RUN_B, payload))

    assert exc.value.status_code == 409
