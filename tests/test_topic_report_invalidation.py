"""Regenerating a topic report must clear everything derived from the old one.

``POST /api/topic-reports/{period_label}/regenerate`` deleted exactly one file:
the cached PPTX. The supervisor synthesis row, the review verdict and the state
sidecar all survived. ``ensure_bundle_synthesis`` returns early when a payload
already exists, so the Markdown and executive-DOCX exports went on serving the
previous executive letter against a freshly generated deck — indefinitely. The
stale sidecar also still held the OLD pinned run ids, so the next build's HTML
and full DOCX could resolve to runs the new deck had not used.

The quarterly-bundle path already did all three steps; only the topic-report
route was incomplete.

These tests use a temporary cache directory and a stubbed facade; nothing here
touches the real database or the tenant's render cache.
"""

import os
from unittest.mock import Mock

import pytest

PERIOD = "Q3_2026__abc12345"


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point the render cache at a temp dir — it is keyed on DB_NAME."""
    monkeypatch.setenv("DB_NAME", f"test_invalidation_{tmp_path.name}")
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    from app.services import topic_report_service as svc

    d = svc._render_cache_dir()
    return d


def _seed_artifacts(svc, period_label):
    """Write a cached deck and a state sidecar as a real build would."""
    svc._write_render_cache(period_label, b"old-deck-bytes")
    svc._write_state_sidecar(
        period_label, ["Quantum Advantage"], "Q3 2026",
        run_ids={"Quantum Advantage": "run-old"},
    )


def _install_facade(monkeypatch, removed=None, fail=False):
    import app.database as appdb

    facade = Mock()
    if fail:
        facade.delete_forecast_bundle_state.side_effect = RuntimeError("db down")
    else:
        facade.delete_forecast_bundle_state.return_value = (
            removed if removed is not None else {"synthesis": 1, "review": 1}
        )
    db = Mock()
    db.facade = facade
    monkeypatch.setattr(appdb, "get_database_instance", lambda: db)
    return facade


def test_regenerate_clears_deck_sidecar_synthesis_and_review(cache_dir, monkeypatch):
    """All four pieces of derived state go, not just the deck."""
    from app.services import topic_report_service as svc

    facade = _install_facade(monkeypatch)
    _seed_artifacts(svc, PERIOD)
    assert svc._read_render_cache(PERIOD) is not None
    assert svc._read_state_sidecar(PERIOD) is not None

    cleared = svc.invalidate_report_state(PERIOD)

    assert svc._read_render_cache(PERIOD) is None, "cached deck survived"
    assert svc._read_state_sidecar(PERIOD) is None, "state sidecar survived"
    facade.delete_forecast_bundle_state.assert_called_once_with("topic_report", PERIOD)
    assert cleared["pptx"] is True
    assert cleared["state_sidecar"] is True
    assert cleared["synthesis_rows"] == 1
    assert cleared["review_rows"] == 1


def test_the_stale_pinned_runs_do_not_survive(cache_dir, monkeypatch):
    """The sidecar holds the old run pins; leaving it would let the next
    build's HTML and DOCX resolve runs the new deck never used."""
    from app.services import topic_report_service as svc

    _install_facade(monkeypatch)
    _seed_artifacts(svc, PERIOD)
    assert (svc._read_state_sidecar(PERIOD) or {}).get("run_ids") == {
        "Quantum Advantage": "run-old"
    }

    svc.invalidate_report_state(PERIOD)

    assert svc._read_state_sidecar(PERIOD) is None


def test_artifacts_are_kept_when_the_database_cannot_be_cleared(cache_dir, monkeypatch):
    """Deleting the deck while the old executive letter survives would leave
    the period serving a mixture. Fail instead, with everything intact."""
    from app.services import topic_report_service as svc

    _install_facade(monkeypatch, fail=True)
    _seed_artifacts(svc, PERIOD)

    with pytest.raises(RuntimeError):
        svc.invalidate_report_state(PERIOD)

    assert svc._read_render_cache(PERIOD) is not None, (
        "the deck was deleted even though the synthesis could not be cleared"
    )
    assert svc._read_state_sidecar(PERIOD) is not None


def test_invalidating_a_period_with_nothing_cached_is_not_an_error(cache_dir, monkeypatch):
    from app.services import topic_report_service as svc

    _install_facade(monkeypatch, removed={"synthesis": 0, "review": 0})

    cleared = svc.invalidate_report_state("never-generated")

    assert cleared["pptx"] is False
    assert cleared["state_sidecar"] is False


def test_regenerate_route_reports_failure_instead_of_claiming_success(monkeypatch):
    """A regenerate that could not clear state must not return ok."""
    import asyncio

    from fastapi import HTTPException

    from app.routes.topic_report_routes import regenerate_topic_report
    from app.services import topic_report_service as svc

    monkeypatch.setattr(
        svc, "invalidate_report_state",
        Mock(side_effect=RuntimeError("db down")),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(regenerate_topic_report(PERIOD))

    assert exc.value.status_code == 500
    assert "nothing was regenerated" in exc.value.detail


def test_regenerate_route_returns_what_it_cleared(monkeypatch):
    import asyncio

    from app.routes.topic_report_routes import regenerate_topic_report
    from app.services import topic_report_service as svc

    monkeypatch.setattr(
        svc, "invalidate_report_state",
        Mock(return_value={"pptx": True, "state_sidecar": True,
                           "synthesis_rows": 1, "review_rows": 1}),
    )

    resp = asyncio.run(regenerate_topic_report(PERIOD))

    assert resp["ok"] is True
    assert resp["cleared"]["synthesis_rows"] == 1
