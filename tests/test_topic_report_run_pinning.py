"""Every export format of one report must render the same pinned forecast runs.

A report label pins each source topic to the exact ``future_horizons_runs`` id
the deck was built from, so a horizons rerun between exports cannot swap the
analysis under an artifact. Two holes let that happen anyway:

* ``resolve_items`` loaded the assessment with
  ``get_latest_forecast_assessment_by_topic(topic)``, which resolves to whatever
  run was assessed most recently. A report pinned to run A merged run B's
  summary and surprises into A's scenarios.
* Markdown and the executive DOCX did not use the resolver at all. They went
  through ``_load_cached_state``, which looked up the latest assessment per
  topic, so those two formats could describe a different run than the deck they
  are supposed to be views of.

A pin that no longer resolves also used to fall back to the latest run with a
warning, which is the same drift the pin exists to prevent.

The facade is stubbed here; these tests neither hit the database nor render.
"""

from unittest.mock import Mock

import pytest

TOPIC = "Quantum Advantage"
RUN_A = "run-aaaa-pinned"
RUN_B = "run-bbbb-newer"


class _Facade:
    def __init__(self, existing_run_ids, assessments_by_run, latest_by_topic=None):
        self._existing = set(existing_run_ids)
        self._by_run = assessments_by_run
        self._latest_by_topic = latest_by_topic or {}
        self.by_topic_calls = []

    # resolve_items issues raw SQL for run existence and latest-run lookup, and
    # reads results as SQLAlchemy rows (row._mapping["id"]).
    @staticmethod
    def _row(run_id):
        return Mock(_mapping={"id": run_id})

    def _execute_with_rollback(self, sql, params=None):
        text = str(sql)
        params = params or {}
        if "WHERE id = :rid" in text:
            rid = params.get("rid")
            return Mock(fetchone=lambda: (self._row(rid) if rid in self._existing else None))
        if "ORDER BY created_at DESC" in text:
            return Mock(fetchone=lambda: self._row(RUN_B))
        return Mock(fetchone=lambda: None, fetchall=lambda: [])

    def get_future_horizons_analysis(self, run_id):
        return {"id": run_id, "topic": TOPIC, "raw_output": {"scenarios": []}}

    def get_latest_forecast_assessment(self, run_id):
        return self._by_run.get(run_id) or {}

    def get_latest_forecast_assessment_by_topic(self, topic):
        self.by_topic_calls.append(topic)
        return self._latest_by_topic.get(topic) or {}


def _install(monkeypatch, facade):
    import app.database as appdb
    import app.services.topic_report_pptx as pptx
    import app.services.wiley_delivery_service as delivery

    db = Mock()
    db.facade = facade
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    # Overlay renaming and the per-topic context loaders are not what these
    # tests are about; keep them out of the way. resolve_items imports the
    # renamer inside its body, so patch it on the module that defines it.
    monkeypatch.setattr(delivery, "_apply_overlay_display_names", lambda items: items)
    for name in ("_load_eos_scenarios", "_load_consensus_for_topic",
                 "_load_supporting_articles"):
        monkeypatch.setattr(pptx, name, lambda *a, **k: [], raising=False)
    monkeypatch.setattr(pptx, "_load_horizons_executive_summary",
                        lambda *a, **k: [], raising=False)
    monkeypatch.setattr(pptx, "_load_articles_corpus", lambda *a, **k: [], raising=False)


def test_resolver_loads_the_assessment_of_the_pinned_run(monkeypatch):
    """The core fix: assessment comes from the pinned run, not the topic."""
    from app.services.topic_report_pptx import resolve_items

    facade = _Facade(
        existing_run_ids=[RUN_A, RUN_B],
        assessments_by_run={
            RUN_A: {"id": "assess-a", "run_id": RUN_A, "summary": {"headline": "A"}},
            RUN_B: {"id": "assess-b", "run_id": RUN_B, "summary": {"headline": "B"}},
        },
        latest_by_topic={TOPIC: {"id": "assess-b", "run_id": RUN_B,
                                 "summary": {"headline": "B"}}},
    )
    _install(monkeypatch, facade)

    items = resolve_items([TOPIC], run_ids={TOPIC: RUN_A})

    assert len(items) == 1
    assessment = items[0][0]
    assert assessment["_source_run_id"] == RUN_A
    assert assessment["_assessment_id"] == "assess-a"
    assert not facade.by_topic_calls, (
        "the resolver must not fall back to latest-assessment-by-topic"
    )


def test_resolver_keeps_source_topic_and_run_for_provenance(monkeypatch):
    """Overlay display names are applied after these are stamped, so every
    renderer can still print which run it rendered."""
    from app.services.topic_report_pptx import resolve_items

    facade = _Facade([RUN_A], {RUN_A: {"id": "assess-a", "run_id": RUN_A}})
    _install(monkeypatch, facade)

    assessment = resolve_items([TOPIC], run_ids={TOPIC: RUN_A})[0][0]

    assert assessment["_source_topic"] == TOPIC
    assert assessment["_source_run_id"] == RUN_A


def test_a_missing_pin_is_an_error_not_a_silent_switch(monkeypatch):
    """Falling back to the latest run would change the analysis under an
    existing report label — the exact drift pinning prevents."""
    from app.services.topic_report_pptx import MissingPinnedRun, resolve_items

    facade = _Facade(existing_run_ids=[RUN_B], assessments_by_run={})
    _install(monkeypatch, facade)

    with pytest.raises(MissingPinnedRun) as exc:
        resolve_items([TOPIC], run_ids={TOPIC: RUN_A})

    assert RUN_A in str(exc.value)
    assert "regenerate" in str(exc.value).lower()


def test_an_unpinned_topic_still_resolves_to_latest(monkeypatch):
    """First generation, where the pin is being established, must still work."""
    from app.services.topic_report_pptx import resolve_items

    facade = _Facade([RUN_A, RUN_B], {RUN_B: {"id": "assess-b", "run_id": RUN_B}})
    _install(monkeypatch, facade)

    assessment = resolve_items([TOPIC], run_ids={})[0][0]

    assert assessment["_source_run_id"] == RUN_B


def test_an_assessment_claiming_another_run_is_refused(monkeypatch):
    """Defence in depth: if the lookup ever returns a foreign row, drop it
    rather than merging another run's prose into this one's scenarios."""
    from app.services.topic_report_pptx import resolve_items

    facade = _Facade(
        existing_run_ids=[RUN_A],
        assessments_by_run={RUN_A: {"id": "assess-b", "run_id": RUN_B,
                                    "summary": {"headline": "B"},
                                    "surprises": [{"label": "from B"}]}},
    )
    _install(monkeypatch, facade)

    assessment = resolve_items([TOPIC], run_ids={TOPIC: RUN_A})[0][0]

    assert assessment["_assessment_id"] is None
    assert assessment["surprises"] == []


def test_every_format_resolves_through_the_same_pinned_path():
    """Markdown and executive DOCX used to bypass the resolver entirely."""
    import inspect

    from app.services import topic_report_service as svc

    state_src = inspect.getsource(svc._load_cached_state)
    assert "resolve_items(" in state_src, (
        "Markdown and executive DOCX resolve through _load_cached_state; it must "
        "use the shared run-pinned resolver"
    )
    assert "run_ids=" in state_src, "the sidecar's pins must be passed through"

    # And the HTML / full-DOCX entrypoints keep passing their pins.
    for fn in (svc.generate_topic_report_html, svc.generate_topic_report_docx_full):
        assert "run_ids=" in inspect.getsource(fn)


def test_the_dead_third_resolver_is_gone():
    """A second, unused resolver drifts from the real one and misleads readers."""
    from app.services import topic_report_service as svc

    assert not hasattr(svc, "_resolve_items_for_topics")


def test_routes_do_not_import_the_renderer_at_module_scope():
    """topic_report_pptx imports python-pptx, which is not installed on every
    tenant. Importing it from a route at module scope takes the whole app down
    at startup with ModuleNotFoundError — it did exactly that to wiley on
    2026-08-18. Renderer imports in routes must stay inside function bodies;
    the shared error type lives in a dependency-free module for this reason.
    """
    import ast
    import pathlib

    src = pathlib.Path("app/routes/topic_report_routes.py").read_text()
    tree = ast.parse(src)

    heavy = []
    for node in tree.body:          # module scope only, not nested bodies
        if isinstance(node, ast.ImportFrom) and node.module:
            if "topic_report_pptx" in node.module or node.module == "pptx":
                heavy.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "topic_report_pptx" in alias.name or alias.name == "pptx":
                    heavy.append(alias.name)

    assert not heavy, (
        f"module-scope import of {heavy} in topic_report_routes.py will crash "
        f"tenants without python-pptx installed"
    )
