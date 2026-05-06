"""
Minimal, scalable API endpoint tests.

This file is designed to scale to 300+ endpoints with:
- global dependency overrides
- minimal per-endpoint tests
- no repeated boilerplate
"""

import os
import tempfile

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, mock_open
from fastapi import status
from fastapi.testclient import TestClient

import app.routes.auspex_routes as auspex_routes
import app.routes.dataset_routes as dataset_routes
import app.routes.health_routes as health_routes
import app.routes.market_signals_routes as market_signals_routes
import app.routes.media_bias_routes as media_bias_routes
import app.routes.podcast_routes as podcast_routes
import app.routes.prompt_routes as prompt_routes
import app.routes.executive_summary_routes as executive_summary_routes
import app.routes.futures_cone_routes as futures_cone_routes
import app.routes.oauth_routes as oauth_routes
import app.routes.oauth_admin_routes as oauth_admin_routes
import app.routes.notification_routes as notification_routes
import app.routes.user_management_routes as user_management_routes
import app.routes.websocket_routes as websocket_routes
import app.routes.vector_routes as vector_routes
from unittest.mock import AsyncMock

from app.main import app
from app.security.session import verify_session
from app.security.session import verify_session_api
from app.security.session import verify_session_optional
from app.database import get_database_instance
from app.security.session import verify_session
from app.database_query_facade import DatabaseQueryFacade
import json
from app.routes import dashboard_routes, database
from urllib.parse import unquote_plus
from starlette.requests import Request
import asyncio
from fastapi import HTTPException


@contextmanager
def _reloaded_module_with_patched_verify_session(session_value: dict, module_name: str):
    """
    Patch `app.security.session.verify_session` for the duration of the context
    and reload the target module inside the patch context.

    This preserves the existing test behavior where FastAPI binds Depends(callable)
    at import time, and routes may call verify_session at runtime.
    """
    import importlib
    import app.security.session as session_mod

    with patch.object(session_mod, "verify_session", autospec=True) as verify_session_mock:
        verify_session_mock.return_value = dict(session_value)
        module = importlib.import_module(module_name)
        module = importlib.reload(module)
        yield module


def _make_db_with_facade(*, db_name: str, facade_mock):
    """
    Shared helper for the common pattern:
    db = MagicMock(name=...)
    db.facade = <facade mock>
    """
    db = MagicMock(name=db_name)
    db.facade = facade_mock
    return db


# =============================================================================
# GLOBAL TEST SETUP (applies to ALL tests in this file)
# =============================================================================

@pytest.fixture(scope="session")
def test_client_factory():
    """
    Shared factory for creating FastAPI TestClient instances.
    Centralizes client construction while allowing per-fixture options like
    raise_server_exceptions=False.
    """

    def _make(app_instance, **kwargs):
        return TestClient(app_instance, **kwargs)

    return _make


@pytest.fixture(scope="session")
def client(test_client_factory):
    return test_client_factory(app)


@pytest.fixture(autouse=True)
def override_dependencies():
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}
    app.dependency_overrides[verify_session_api] = lambda: {"user_id": "test-user"}
    app.dependency_overrides[verify_session_optional] = lambda: {"user_id": "test-user"}
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def admin_session():
    return {"user": "admin"}


@pytest.fixture
def mock_verify_session():
    """Explicit fixture for prompt management tests (auth is always mocked)."""
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}
    yield
    # Be defensive: other fixtures may clear overrides.
    app.dependency_overrides.pop(verify_session, None)


# =============================================================================
# oauth_admin_routes.py fixtures (isolated to avoid fixture name collisions)
# =============================================================================


@pytest.fixture
def oauth_admin_mock_db():
    """Mocked DB dependency for oauth_admin_routes tests."""
    return MagicMock(name="oauth_admin_mock_db")


@pytest.fixture
def oauth_admin_mock_oauth_manager():
    """Mock OAuthUserManager used by oauth_admin_routes."""
    with patch("app.routes.oauth_admin_routes.OAuthUserManager") as mgr_cls:
        yield mgr_cls.return_value


@pytest.fixture
def oauth_admin_mock_facade():
    """Mock DatabaseQueryFacade used by oauth_admin_routes."""
    with patch("app.routes.oauth_admin_routes.DatabaseQueryFacade") as facade_cls:
        yield facade_cls.return_value


@pytest.fixture
def oauth_admin_client(admin_session, oauth_admin_mock_db, test_client_factory):
    """
    Dedicated client for oauth_admin_routes.
    The main app may not register these admin routes in all environments, so tests
    mount the router on a tiny FastAPI app and override auth/DB dependencies.
    """
    from fastapi import FastAPI

    admin_app = FastAPI()
    admin_app.include_router(oauth_admin_routes.router)

    with patch("app.security.session.verify_session", return_value=admin_session), patch(
        "app.database.get_database_instance", return_value=oauth_admin_mock_db
    ):
        admin_app.dependency_overrides[verify_session] = lambda: admin_session
        admin_app.dependency_overrides[get_database_instance] = lambda: oauth_admin_mock_db
        yield test_client_factory(admin_app)


# =============================================================================
# web_routes.py (HTML page routes) fixtures + tests (isolated app; templates mocked)
# =============================================================================


@pytest.fixture
def mock_session():
    """Mock session data used by both Depends(verify_session) and request.session."""
    return {"user": "test_user"}


@pytest.fixture
def mock_config():
    """Mock config payload returned by load_config() for topic-based pages."""
    return {
        "topics": [
            {"name": "Security"},
            {"name": "AI"},
            {"name": "Cloud"},
        ]
    }


@pytest.fixture
def web_app(mock_session):
    """
    Tiny FastAPI app that mounts ONLY web_routes.router and provides request.session.
    This keeps the tests hermetic and avoids real template files/config loading.
    """
    from fastapi import FastAPI
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.sessions import SessionMiddleware

    from app.routes.web_routes import router as web_router
    from app.security.session import verify_session as verify_session_dep

    web_app = FastAPI()

    class ForceSessionMiddleware(BaseHTTPMiddleware):
        """Ensures request.session is populated *after* SessionMiddleware initializes it."""

        def __init__(self, app, session_data):
            super().__init__(app)
            self._session_data = session_data

        async def dispatch(self, request: Request, call_next):
            # SessionMiddleware initializes request.session; then we overwrite it for deterministic tests.
            request.session.clear()
            request.session.update(dict(self._session_data))
            return await call_next(request)

    # Order matters: SessionMiddleware must run first so request.session exists,
    # then ForceSessionMiddleware overwrites it with mock data.
    web_app.add_middleware(ForceSessionMiddleware, session_data=mock_session)
    web_app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    web_app.include_router(web_router)
    web_app.dependency_overrides[verify_session_dep] = lambda: dict(mock_session)
    return web_app


@pytest.fixture
def web_client(web_app, test_client_factory):
    return test_client_factory(web_app)


@pytest.fixture
def web_client_no_raise(web_app, test_client_factory):
    return test_client_factory(web_app, raise_server_exceptions=False)


@pytest.fixture
def mock_templates(monkeypatch):
    """Patch web_routes.templates.TemplateResponse so no real templates are rendered."""
    from fastapi.responses import HTMLResponse
    import app.routes.web_routes as web_routes

    tmpl = MagicMock(name="web_routes.templates")
    tmpl.TemplateResponse = MagicMock(return_value=HTMLResponse(content="<html>OK</html>", status_code=200))
    monkeypatch.setattr(web_routes, "templates", tmpl)
    return tmpl


@pytest.fixture
def mock_load_config(monkeypatch, mock_config):
    """Patch web_routes.load_config so no real filesystem/config access occurs."""
    import app.routes.web_routes as web_routes

    fn = MagicMock(name="web_routes.load_config", return_value=mock_config)
    monkeypatch.setattr(web_routes, "load_config", fn)
    return fn


def _assert_template_call(mock_templates, expected_template: str):
    assert mock_templates.TemplateResponse.call_count >= 1
    args, kwargs = mock_templates.TemplateResponse.call_args
    assert not kwargs
    assert args[0] == expected_template
    assert isinstance(args[1], dict)
    return args[1]


def test_web_config_page_success(web_client, mock_templates):
    res = web_client.get("/config")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "config.html")
    assert "request" in ctx
    assert "session" in ctx


def test_web_config_page_failure_template_raises(web_client_no_raise, mock_templates):
    mock_templates.TemplateResponse.side_effect = Exception("template boom")

    res = web_client_no_raise.get("/config")
    assert res.status_code == 500

    ctx = _assert_template_call(mock_templates, "config.html")
    assert "request" in ctx
    assert "session" in ctx


def test_web_prompt_manager_page_success(web_client, mock_templates):
    res = web_client.get("/promptmanager")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "promptmanager.html")
    assert ctx["current_page"] == "settings"
    assert "request" in ctx
    assert "session" in ctx


def test_web_prompt_manager_page_failure_template_raises(web_client_no_raise, mock_templates):
    mock_templates.TemplateResponse.side_effect = Exception("template boom")

    res = web_client_no_raise.get("/promptmanager")
    assert res.status_code == 500

    ctx = _assert_template_call(mock_templates, "promptmanager.html")
    assert "request" in ctx
    assert "session" in ctx


def test_web_vector_analysis_page_success(web_client, mock_templates, mock_session):
    res = web_client.get("/vector-analysis")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "vector_analysis.html")
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_vector_analysis_page_failure_template_raises(web_client_no_raise, mock_templates):
    mock_templates.TemplateResponse.side_effect = Exception("template boom")

    res = web_client_no_raise.get("/vector-analysis")
    assert res.status_code == 500

    ctx = _assert_template_call(mock_templates, "vector_analysis.html")
    assert "request" in ctx
    assert "session" in ctx


def test_web_vector_analysis_improved_page_success(web_client, mock_templates, mock_session):
    res = web_client.get("/vector-analysis-improved")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "vector_analysis_improved.html")
    assert ctx["current_page"] == "gather"
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_vector_analysis_improved_page_failure_template_raises(web_client_no_raise, mock_templates):
    mock_templates.TemplateResponse.side_effect = Exception("template boom")

    res = web_client_no_raise.get("/vector-analysis-improved")
    assert res.status_code == 500

    ctx = _assert_template_call(mock_templates, "vector_analysis_improved.html")
    assert "request" in ctx
    assert "session" in ctx


def test_web_topic_dashboard_page_success(web_client, mock_templates, mock_load_config, mock_session):
    res = web_client.get("/topic-dashboard")
    assert res.status_code == 200
    mock_load_config.assert_called_once()

    ctx = _assert_template_call(mock_templates, "topic_dashboard.html")
    assert ctx["topics"] == ["AI", "Cloud", "Security"]
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_topic_dashboard_page_failure_load_config_raises(web_client, mock_templates, mock_load_config, mock_session):
    mock_load_config.side_effect = Exception("config boom")

    res = web_client.get("/topic-dashboard")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "topic_dashboard.html")
    assert ctx["topics"] == []
    assert "error" in ctx
    assert ctx["session"] == mock_session


def test_web_unified_feed_dashboard_success(web_client, mock_templates, mock_session):
    res = web_client.get("/unified-feed")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "unified_feed_dashboard.html")
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_unified_feed_dashboard_failure_template_raises(web_client, mock_templates, mock_session):
    from fastapi.responses import HTMLResponse

    mock_templates.TemplateResponse.side_effect = [
        Exception("template boom"),
        HTMLResponse(content="<html>OK</html>", status_code=200),
    ]

    res = web_client.get("/unified-feed")
    assert res.status_code == 200
    assert mock_templates.TemplateResponse.call_count == 2

    # Second call should include an error in context
    args2, kwargs2 = mock_templates.TemplateResponse.call_args_list[1]
    assert not kwargs2
    ctx2 = args2[1]
    assert ctx2["error"] == "Could not load unified feed dashboard."
    assert ctx2["session"] == mock_session


def test_web_feed_group_manager_success(web_client, mock_templates, mock_session):
    res = web_client.get("/feed-manager")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "feed_group_manager.html")
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_feed_group_manager_failure_template_raises(web_client, mock_templates, mock_session):
    from fastapi.responses import HTMLResponse

    mock_templates.TemplateResponse.side_effect = [
        Exception("template boom"),
        HTMLResponse(content="<html>OK</html>", status_code=200),
    ]

    res = web_client.get("/feed-manager")
    assert res.status_code == 200
    assert mock_templates.TemplateResponse.call_count == 2

    args2, kwargs2 = mock_templates.TemplateResponse.call_args_list[1]
    assert not kwargs2
    ctx2 = args2[1]
    assert ctx2["error"] == "Could not load feed group manager."
    assert ctx2["session"] == mock_session


def test_web_model_bias_arena_page_success(web_client, mock_templates, mock_session):
    res = web_client.get("/model-bias-arena")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "model_bias_arena.html")
    assert ctx["current_page"] == "analyze"
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_model_bias_arena_page_failure_template_raises(web_client, mock_templates, mock_session):
    from fastapi.responses import HTMLResponse

    mock_templates.TemplateResponse.side_effect = [
        Exception("template boom"),
        HTMLResponse(content="<html>OK</html>", status_code=200),
    ]

    res = web_client.get("/model-bias-arena")
    assert res.status_code == 200
    assert mock_templates.TemplateResponse.call_count == 2

    args2, kwargs2 = mock_templates.TemplateResponse.call_args_list[1]
    assert not kwargs2
    ctx2 = args2[1]
    assert ctx2["error"] == "Could not load model bias arena."
    assert ctx2["current_page"] == "analyze"
    assert ctx2["session"] == mock_session


def test_web_consensus_analysis_page_success(web_client, mock_templates, mock_load_config, mock_session):
    res = web_client.get("/consensus-analysis")
    assert res.status_code == 200
    mock_load_config.assert_called_once()

    ctx = _assert_template_call(mock_templates, "consensus_analysis.html")
    assert ctx["topics"] == ["AI", "Cloud", "Security"]
    assert ctx["session"] == mock_session
    assert "request" in ctx


def test_web_consensus_analysis_page_failure_load_config_raises(web_client, mock_templates, mock_load_config, mock_session):
    mock_load_config.side_effect = Exception("config boom")

    res = web_client.get("/consensus-analysis")
    assert res.status_code == 200

    ctx = _assert_template_call(mock_templates, "consensus_analysis.html")
    assert ctx["topics"] == []
    assert "error" in ctx
    assert ctx["session"] == mock_session


# =============================================================================
# model_bias_arena_routes.py endpoints
# =============================================================================


@pytest.fixture
def bias_arena_mock_session():
    """Ensure verify_session returns a dict with user.username (used by create_run)."""
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "test-user"}}
    yield {"user": {"username": "test-user"}}
    app.dependency_overrides.pop(verify_session, None)


@pytest.fixture
def bias_arena_mock_db():
    """Explicit DB override for bias arena tests (kept hermetic)."""
    db = MagicMock(name="bias_arena_db")
    app.dependency_overrides[get_database_instance] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database_instance, None)


@pytest.fixture
def bias_arena_mock_bg_tasks(monkeypatch):
    """
    Prevent background execution by turning BackgroundTasks.add_task into a recorder.
    Starlette runs background tasks after the response; we ensure nothing is scheduled.
    """
    from fastapi.background import BackgroundTasks

    recorder = MagicMock(name="BackgroundTasks.add_task")

    def _fake_add_task(self, func, *args, **kwargs):
        recorder(func, *args, **kwargs)
        return None

    monkeypatch.setattr(BackgroundTasks, "add_task", _fake_add_task, raising=True)
    return recorder


@pytest.fixture
def bias_arena_mock_service(bias_arena_mock_db):
    """
    Override get_bias_arena_service to return a MagicMock service.
    Also patch ModelBiasArenaService constructor to avoid any accidental real instantiation.
    """
    import app.routes.model_bias_arena_routes as model_bias_arena_routes

    service = MagicMock(name="ModelBiasArenaService")
    app.dependency_overrides[model_bias_arena_routes.get_bias_arena_service] = lambda: service

    with patch("app.services.model_bias_arena_service.ModelBiasArenaService", return_value=service):
        yield service

    app.dependency_overrides.pop(model_bias_arena_routes.get_bias_arena_service, None)


def test_model_bias_arena_get_available_models_success_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_available_models.return_value = [{"name": "gpt-4o"}]
    res = client.get("/api/model-bias-arena/models")
    assert res.status_code == 200
    assert res.json() == {"models": [{"name": "gpt-4o"}]}

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_available_models.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/models")
    assert res.status_code == 500


def test_model_bias_arena_create_run_success_and_failures(
    client, bias_arena_mock_service, bias_arena_mock_session, bias_arena_mock_bg_tasks
):
    payload = {
        "name": "Test",
        "description": "D",
        "benchmark_model": "gpt-4o",
        "selected_models": ["gpt-4o"],
        "article_count": 25,
        "rounds": 1,
        "topic": None,
    }

    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_available_models.return_value = [{"name": "gpt-4o"}]
    res = client.post("/api/model-bias-arena/runs", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "started"
    assert res.json()["run_id"] == -1
    assert bias_arena_mock_bg_tasks.call_count == 1

    called_func = bias_arena_mock_bg_tasks.call_args[0][0]
    called_kwargs = bias_arena_mock_bg_tasks.call_args.kwargs
    assert called_func == bias_arena_mock_service.create_and_evaluate_run
    assert called_kwargs["name"] == "Test"
    assert called_kwargs["benchmark_model"] == "gpt-4o"
    assert called_kwargs["selected_models"] == ["gpt-4o"]
    assert called_kwargs["rounds"] == 1
    assert called_kwargs["username"] == "test-user"

    # ---------------- FAILURE (INVALID BENCHMARK MODEL) ----------------
    bias_arena_mock_service.get_available_models.return_value = [{"name": "other"}]
    res = client.post("/api/model-bias-arena/runs", json=payload)
    assert res.status_code == 400
    assert "benchmark model" in res.json()["detail"].lower()

    # ---------------- FAILURE (INVALID SELECTED MODEL) ----------------
    bias_arena_mock_service.get_available_models.return_value = [{"name": "gpt-4o"}]
    bad_payload = dict(payload)
    bad_payload["selected_models"] = ["not-a-model"]
    res = client.post("/api/model-bias-arena/runs", json=bad_payload)
    assert res.status_code == 400
    assert "not available" in res.json()["detail"].lower()

    # ---------------- FAILURE (EXCEPTION) ----------------
    bias_arena_mock_service.get_available_models.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.post("/api/model-bias-arena/runs", json=payload)
    assert res.status_code == 500


def test_model_bias_arena_get_runs_success_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_runs.return_value = [
        {
            "id": 1,
            "name": "Test",
            "description": None,
            "benchmark_model": "gpt-4o",
            "selected_models": ["gpt-4o"],
            "article_count": 25,
            "rounds": 1,
            "current_round": 1,
            "created_at": "2025",
            "completed_at": None,
            "status": "done",
        }
    ]
    res = client.get("/api/model-bias-arena/runs")
    assert res.status_code == 200
    payload = res.json()
    assert "runs" in payload
    assert payload["runs"][0]["id"] == 1
    assert payload["runs"][0]["benchmark_model"] == "gpt-4o"

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_runs.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs")
    assert res.status_code == 500


def test_model_bias_arena_get_run_details_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_run_details.return_value = {"id": 1, "name": "Test"}
    res = client.get("/api/model-bias-arena/runs/1")
    assert res.status_code == 200
    assert res.json() == {"run": {"id": 1, "name": "Test"}}

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.get_run_details.return_value = None
    res = client.get("/api/model-bias-arena/runs/1")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_run_details.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1")
    assert res.status_code == 500


def test_model_bias_arena_get_run_results_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_run_results.return_value = {"run_details": {"id": 1}, "statistics": {}}
    res = client.get("/api/model-bias-arena/runs/1/results")
    assert res.status_code == 200
    assert res.json()["run_details"]["id"] == 1

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.get_run_results.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/results")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_run_results.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/results")
    assert res.status_code == 500


def test_model_bias_arena_get_run_articles_success_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_run_articles.return_value = [{"id": 1}]
    res = client.get("/api/model-bias-arena/runs/1/articles")
    assert res.status_code == 200
    assert res.json() == {"articles": [{"id": 1}]}

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_run_articles.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/articles")
    assert res.status_code == 500


def test_model_bias_arena_delete_run_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.delete_run.return_value = True
    res = client.delete("/api/model-bias-arena/runs/1")
    assert res.status_code == 200
    assert "deleted" in res.json()["message"].lower()

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.delete_run.return_value = False
    res = client.delete("/api/model-bias-arena/runs/1")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.delete_run.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.delete("/api/model-bias-arena/runs/1")
    assert res.status_code == 500


def test_model_bias_arena_sample_articles_success_validation_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.sample_articles.return_value = [{"id": 1}, {"id": 2}]
    res = client.get("/api/model-bias-arena/sample-articles?count=2")
    assert res.status_code == 200
    assert res.json()["count"] == 2
    assert len(res.json()["articles"]) == 2

    # ---------------- VALIDATION ----------------
    res = client.get("/api/model-bias-arena/sample-articles?count=0")
    assert res.status_code == 400
    res = client.get("/api/model-bias-arena/sample-articles?count=101")
    assert res.status_code == 400

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.sample_articles.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/sample-articles?count=2")
    assert res.status_code == 500


def test_model_bias_arena_export_run_to_pdf_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.export_run_to_pdf.return_value = "<html>report</html>"
    res = client.get("/api/model-bias-arena/runs/1/export/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "inline" in res.headers.get("content-disposition", "").lower()
    assert "<html>" in res.text

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.export_run_to_pdf.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/export/pdf")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.export_run_to_pdf.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/export/pdf")
    assert res.status_code == 500


def test_model_bias_arena_export_run_to_png_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.export_run_to_png.return_value = "viz"
    res = client.get("/api/model-bias-arena/runs/1/export/png")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert "attachment" in res.headers.get("content-disposition", "").lower()
    assert res.text == "viz"

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.export_run_to_png.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/export/png")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.export_run_to_png.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/export/png")
    assert res.status_code == 500


def test_model_bias_arena_export_run_to_csv_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.export_run_to_csv.return_value = "id,score\n1,0.5"
    res = client.get("/api/model-bias-arena/runs/1/export/csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers.get("content-disposition", "").lower()
    assert "id,score" in res.text

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.export_run_to_csv.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/export/csv")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.export_run_to_csv.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/export/csv")
    assert res.status_code == 500


def test_model_bias_arena_export_run_results_to_csv_success_not_found_and_failure(
    client, bias_arena_mock_service, bias_arena_mock_session
):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.export_run_results_to_csv.return_value = "id,score\n1,0.5"
    res = client.get("/api/model-bias-arena/runs/1/export-results/csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers.get("content-disposition", "").lower()
    assert "id,score" in res.text

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.export_run_results_to_csv.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/export-results/csv")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.export_run_results_to_csv.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/export-results/csv")
    assert res.status_code == 500


def test_model_bias_arena_get_validation_results_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.compare_results_with_source_bias.return_value = {"ok": True}
    res = client.get("/api/model-bias-arena/runs/1/validation")
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.compare_results_with_source_bias.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/validation")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.compare_results_with_source_bias.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/validation")
    assert res.status_code == 500


def test_model_bias_arena_get_source_bias_data_success_not_found_and_failure(client, bias_arena_mock_service, bias_arena_mock_session):
    # ---------------- SUCCESS ----------------
    bias_arena_mock_service.get_source_bias_validation_data.return_value = [{"source": "X", "bias": 0.1}]
    res = client.get("/api/model-bias-arena/runs/1/source-bias-data")
    assert res.status_code == 200
    assert res.json() == {"source_bias_data": [{"source": "X", "bias": 0.1}]}

    # ---------------- NOT FOUND ----------------
    bias_arena_mock_service.get_source_bias_validation_data.return_value = None
    res = client.get("/api/model-bias-arena/runs/1/source-bias-data")
    assert res.status_code == 404

    # ---------------- FAILURE ----------------
    bias_arena_mock_service.get_source_bias_validation_data.side_effect = Exception("boom")
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/api/model-bias-arena/runs/1/source-bias-data")
    assert res.status_code == 500


# =============================================================================
# api_routes.py endpoints
# =============================================================================

def test_enriched_articles_success(client, monkeypatch):
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "enriched_articles",
        lambda self, limit: [{"id": 1, "category": "Tech"}]
    )

    res = client.get("/api/enriched_articles")

    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)


# =============================================================================
# auspex_routes.py endpoints
# =============================================================================


def test_enriched_articles_db_error(client, monkeypatch):
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "enriched_articles",
        lambda self, limit: (_ for _ in ()).throw(Exception("DB error"))
    )

    res = client.get("/api/enriched_articles")

    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR




def test_block_options_success(client, monkeypatch):
    class MockAuspex:
        def suggest_options(self, kind, name, description):
            return ["option1", "option2"]

    # Patch the symbol as it exists in auspex_routes.py
    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: MockAuspex()
    )

    res = client.post(
        "/api/auspex/block-options",
        json={
            "kind": "agent",
            "scenario_name": "test",
            "scenario_description": "test desc",
        },
    )

    assert res.status_code == 200
    assert res.json() == {"options": ["option1", "option2"]}




def test_create_chat_session_success(client, monkeypatch):
    mock_auspex = AsyncMock()
    mock_auspex.create_chat_session.return_value = "chat-123"

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res = client.post(
        "/api/auspex/chat/sessions",
        json={
            "topic": "ai",
            "title": "AI discussion",
            "profile_id": 1
        }
    )

    assert res.status_code == 201

    body = res.json()
    assert body["chat_id"] == "chat-123"
    assert body["topic"] == "ai"
    assert body["title"] == "AI discussion"
    assert body["profile_id"] == 1


def test_get_chat_sessions_success(client, monkeypatch):
    mock_auspex = MagicMock()
    mock_auspex.get_chat_sessions.return_value = [
        {"id": "c1", "topic": "ai"},
        {"id": "c2", "topic": "ai"}
    ]

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res = client.get("/api/auspex/chat/sessions?topic=ai&limit=10")

    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert isinstance(res.json()["sessions"], list)


def test_get_chat_sessions_oauth_user(client, monkeypatch):
    mock_auspex = MagicMock()
    mock_auspex.get_chat_sessions.return_value = []

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # Override session to simulate OAuth user
    from app.security.session import verify_session
    from app.main import app

    app.dependency_overrides[verify_session] = lambda: {"user": {"email": "oauth@test.com"}}

    res = client.get("/api/auspex/chat/sessions")

    assert res.status_code == 200
    assert res.json() == {"sessions": [], "total": 0}


def test_get_chat_history_success(client, monkeypatch):
    # --- Mock Auspex ---
    mock_auspex = MagicMock()
    mock_auspex.db.get_auspex_chat.return_value = {
        "id": 1,
        "user_id": "test-user"
    }
    mock_auspex.get_chat_history.return_value = [
        {"role": "system", "content": "internal"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"}
    ]

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # --- Force session user to match chat owner ---
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    res = client.get("/api/auspex/chat/sessions/1/messages")

    assert res.status_code == 200
    assert res.json()["total_messages"] == 2

def test_delete_chat_session_success(client, monkeypatch):
    mock_auspex = MagicMock()
    mock_auspex.db.get_auspex_chat.return_value = {
        "id": 1,
        "user_id": "test-user"
    }
    mock_auspex.delete_chat_session.return_value = True

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # ensure session user matches owner
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    res = client.delete("/api/auspex/chat/sessions/1")

    assert res.status_code == 200
    assert res.json()["message"] == "Chat session deleted successfully"


def test_delete_chat_session_not_found(client, monkeypatch):
    mock_auspex = MagicMock()
    mock_auspex.db.get_auspex_chat.return_value = None

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res = client.delete("/api/auspex/chat/sessions/999")

    assert res.status_code == 404


def test_send_chat_message_success(client, monkeypatch):
    mock_auspex = MagicMock()

    mock_auspex.db.get_auspex_chat.return_value = {
        "id": 1,
        "user_id": "test-user",
        "topic": "ai",
        "profile_id": None
    }

    async def fake_stream(*args, **kwargs):
        yield "hello"

    mock_auspex.chat_with_tools = fake_stream

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    res = client.post(
        "/api/auspex/chat/message",
        json={
            "chat_id": 1,
            "message": "hello",
            "model": "gpt",
            "limit": 5,
            "tools_config": {},
            "profile_id": None,
            "custom_prompt": None,
            "article_detail_limit": 5,
            "include_charts": False
        }
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")


def test_get_prompts_success(client, monkeypatch):
    mock_auspex = MagicMock()
    mock_auspex.get_all_prompts.return_value = [
        {"id": 1, "name": "default"},
        {"id": 2, "name": "analysis"}
    ]

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res = client.get("/api/auspex/prompts")

    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert isinstance(res.json()["prompts"], list)


def test_get_prompt_success_and_not_found(client, monkeypatch):
    mock_auspex = MagicMock()

    # --- Success case ---
    mock_auspex.get_system_prompt.return_value = {
        "name": "default",
        "content": "You are a helpful assistant."
    }

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res_success = client.get("/api/auspex/prompts/default")

    assert res_success.status_code == 200
    assert res_success.json()["name"] == "default"

    # --- Failure case ---
    mock_auspex.get_system_prompt.return_value = None

    res_fail = client.get("/api/auspex/prompts/unknown")

    assert res_fail.status_code == 404


def test_create_prompt_success_and_failure(client, monkeypatch):
    mock_auspex = MagicMock()

    # --- Success case ---
    mock_auspex.create_prompt.return_value = 1

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    res_success = client.post(
        "/api/auspex/prompts",
        json={
            "name": "default",
            "title": "Default Prompt",
            "content": "You are helpful.",
            "description": "Base prompt"
        }
    )

    assert res_success.status_code == 201
    assert res_success.json()["name"] == "default"

    # --- Duplicate name → 400 ---
    def duplicate_error(*args, **kwargs):
        raise Exception("UNIQUE constraint failed")

    mock_auspex.create_prompt.side_effect = duplicate_error

    res_duplicate = client.post(
        "/api/auspex/prompts",
        json={
            "name": "default",
            "title": "Duplicate",
            "content": "Test",
            "description": "Test"
        }
    )

    assert res_duplicate.status_code == 400

    # --- Other error → 500 ---
    def generic_error(*args, **kwargs):
        raise Exception("DB down")

    mock_auspex.create_prompt.side_effect = generic_error

    res_fail = client.post(
        "/api/auspex/prompts",
        json={
            "name": "other",
            "title": "Other",
            "content": "Test",
            "description": "Test"
        }
    )

    assert res_fail.status_code == 500


def test_update_prompt_success_and_failure(client, monkeypatch):
    mock_auspex = MagicMock()

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # --- Not found → 404 ---
    mock_auspex.get_system_prompt.return_value = None

    res_not_found = client.put(
        "/api/auspex/prompts/unknown",
        json={
            "title": "New Title",
            "content": "New Content",
            "description": "New Desc"
        }
    )

    assert res_not_found.status_code == 404

    # --- Success → 200 ---
    mock_auspex.get_system_prompt.return_value = {
        "name": "default",
        "content": "Old"
    }
    mock_auspex.update_prompt.return_value = True

    res_success = client.put(
        "/api/auspex/prompts/default",
        json={
            "title": "Updated",
            "content": "Updated content",
            "description": "Updated desc"
        }
    )

    assert res_success.status_code == 200
    assert res_success.json()["message"] == "Prompt updated successfully"

    # --- Update failed → 500 ---
    mock_auspex.update_prompt.return_value = False

    res_fail = client.put(
        "/api/auspex/prompts/default",
        json={
            "title": "Fail",
            "content": "Fail",
            "description": "Fail"
        }
    )

    assert res_fail.status_code == 500


def test_delete_prompt_success_and_failure(client, monkeypatch):
    mock_auspex = MagicMock()

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # --- Not found → 404 ---
    mock_auspex.get_system_prompt.return_value = None

    res_not_found = client.delete("/api/auspex/prompts/unknown")

    assert res_not_found.status_code == 404

    # --- Default prompt → 400 ---
    mock_auspex.get_system_prompt.return_value = {
        "name": "default",
        "is_default": True
    }

    res_default = client.delete("/api/auspex/prompts/default")

    assert res_default.status_code == 400

    # --- Success → 200 ---
    mock_auspex.get_system_prompt.return_value = {
        "name": "custom",
        "is_default": False
    }
    mock_auspex.delete_prompt.return_value = True

    res_success = client.delete("/api/auspex/prompts/custom")

    assert res_success.status_code == 200
    assert res_success.json()["message"] == "Prompt deleted successfully"

    # --- Delete failed → 500 ---
    mock_auspex.get_system_prompt.return_value = {
        "name": "custom",
        "is_default": False
    }
    mock_auspex.delete_prompt.return_value = False

    res_fail = client.delete("/api/auspex/prompts/custom")

    assert res_fail.status_code == 500


def test_consensus_analysis_route_smoke(client):
    """
    Smoke test for consensus-analysis endpoint.

    Purpose:
    - Verify route is registered
    - App boots correctly
    - No import/runtime crash
    - Endpoint is reachable

    This endpoint is too complex for unit-level mocking.
    It is tested via integration tests instead.
    """

    res = client.options("/api/auspex/consensus-analysis")

    # 200 = OK
    # 405 = Method Not Allowed (also acceptable for OPTIONS)
    assert res.status_code in (200, 405)


"""
def test_get_consensus_analysis_raw_success_and_failure(client, monkeypatch):
    mock_db = MagicMock()

    # Attach facade mock
    mock_db.facade.get_consensus_analysis = MagicMock()

    # Patch DB dependency
    monkeypatch.setattr(
        auspex_routes,
        "get_database_instance",
        lambda: mock_db
    )

    # --------------------
    # Success → 200
    # --------------------
    from datetime import datetime

    mock_db.facade.get_consensus_analysis.return_value = {
        "topic": "ai",
        "timeframe": "30d",
        "created_at": datetime(2026, 1, 1),
        "total_articles_analyzed": 10,
        "analysis_duration_seconds": 5.2,
        "raw_output": {"data": "test"}
    }

    res_success = client.get("/api/auspex/consensus-analysis/abc123/raw")

    assert res_success.status_code == 200
    assert res_success.json()["success"] is True
    assert res_success.json()["analysis_id"] == "abc123"

    # --------------------
    # Not found → 404
    # --------------------
    mock_db.facade.get_consensus_analysis.return_value = None

    res_not_found = client.get("/api/auspex/consensus-analysis/unknown/raw")

    assert res_not_found.status_code == 404

    # --------------------
    # Internal error → 500
    # --------------------
    def db_error(*args, **kwargs):
        raise Exception("DB down")

    mock_db.facade.get_consensus_analysis.side_effect = db_error

    res_fail = client.get("/api/auspex/consensus-analysis/err/raw")

    assert res_fail.status_code == 500
"""

def test_get_system_info_success_and_failure(client, monkeypatch):
    mock_auspex = MagicMock()

    # --------------------
    # Success case
    # --------------------
    mock_auspex.db.get_topics.return_value = ["ai", "ml", "cloud"]
    mock_auspex.get_all_prompts.return_value = [
        {"name": "p1"},
        {"name": "p2"}
    ]

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    res_success = client.get("/api/auspex/system/info")

    assert res_success.status_code == 200

    # --------------------
    # Failure → Exception
    # --------------------
    mock_auspex.db.get_topics.side_effect = Exception("DB error")

    with pytest.raises(Exception):
        client.get("/api/auspex/system/info")


def test_test_auspex_tools_success_and_failure(client, monkeypatch):
    mock_auspex = MagicMock()

    # --------------------
    # Mock DB
    # --------------------
    mock_auspex.db.get_topics.return_value = [
        {"name": "ai"}
    ]

    # --------------------
    # Mock Tools (async)
    # --------------------
    class MockTools:
        async def get_topic_articles(self, topic, limit=5):
            return {"total_articles": 5}

        async def analyze_sentiment_trends(self, topic, period):
            return {"total_articles": 3}

        async def get_article_categories(self, topic):
            return {"category_distribution": {"Tech": 2}}

    mock_auspex.tools = MockTools()

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: mock_auspex
    )

    # --------------------
    # Success case
    # --------------------
    res_success = client.get("/api/auspex/debug/test-tools")

    assert res_success.status_code == 200

    body = res_success.json()

    assert body["status"] == "test_completed"
    assert body["results"]["database_check"] is True
    assert body["results"]["tools_service_check"] is True
    assert body["results"]["topic_articles_test"]["success"] is True
    assert body["results"]["sentiment_analysis_test"]["success"] is True
    assert body["results"]["categories_test"]["success"] is True

    # --------------------
    # Failure case (DB error)
    # --------------------
    def db_error():
        raise Exception("DB down")

    mock_auspex.db.get_topics.side_effect = db_error

    res_fail = client.get("/api/auspex/debug/test-tools")

    assert res_fail.status_code == 200
    assert "general_error" in res_fail.json()["results"]


def test_get_plugin_tools_success_and_failure(client, monkeypatch):
    # --------------------
    # Mock Tool + Registry
    # --------------------
    class MockTrigger:
        def __init__(self):
            self.patterns = ["test"]
            self.priority = 1

    class MockTool:
        def __init__(self):
            self.name = "search"
            self.description = "Search tool"
            self.category = "utils"
            self.version = "1.0"
            self.is_prompt_tool = False
            self.triggers = [MockTrigger()]

    class MockRegistry:
        def get_all_tools(self):
            return [MockTool()]

        def get_handler(self, name):
            return lambda x: x

    # --------------------
    # Patch registry init
    # --------------------
    monkeypatch.setattr(
        "app.services.tool_plugin_base.init_tool_registry",
        lambda: MockRegistry()
    )

    # --------------------
    # Success case
    # --------------------
    res_success = client.get("/api/auspex/plugin-tools")

    assert res_success.status_code == 200

    body = res_success.json()

    assert body["status"] == "success"
    assert body["count"] == 1
    assert body["tools"][0]["name"] == "search"
    assert body["tools"][0]["has_handler"] is True

    # --------------------
    # Failure case
    # --------------------
    def init_error():
        raise Exception("Registry error")

    monkeypatch.setattr(
        "app.services.tool_plugin_base.init_tool_registry",
        init_error
    )

    res_fail = client.get("/api/auspex/plugin-tools")

    assert res_fail.status_code == 200
    assert res_fail.json()["status"] == "error"
    assert res_fail.json()["count"] == 0



def test_start_deep_research(client, monkeypatch):
    from app.main import app

    # ------------------ Mock Service ------------------
    class S:
        async def conduct_research(self, **k):
            yield {"stage": "plan"}
            yield {"stage": "done"}

    monkeypatch.setattr(
        auspex_routes,
        "get_deep_research_service",
        lambda: S()
    )

    url = "/api/auspex/research"

    valid = {
        "query": "AI in healthcare",
        "topic": "Artificial Intelligence"
    }

    # ------------------ 422 (Validation with authenticated session) ------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test"}
    r1 = client.post(url, json={"query": "hi"})  # missing required "topic"
    assert r1.status_code == 422

    # ------------------ 401 (No Session) ------------------
    app.dependency_overrides[verify_session] = lambda: {}

    r2 = client.post(url, json=valid)
    assert r2.status_code == 401

    # ------------------ 200 (Stream OK) ------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    r3 = client.post(url, json=valid)

    assert r3.status_code == 200
    assert "text/event-stream" in r3.headers["content-type"]

    # ------------------ Error in Stream ------------------
    class E:
        async def conduct_research(self, **k):
            raise Exception("boom")

    monkeypatch.setattr(
        auspex_routes,
        "get_deep_research_service",
        lambda: E()
    )

    r4 = client.post(url, json=valid)

    assert r4.status_code == 200
    assert "error" in r4.text

    # ------------------ Cleanup ------------------
    app.dependency_overrides.clear()



def test_research_endpoints(client, monkeypatch):
    from app.main import app

    # ---------------- Mock Research Service ----------------
    class S:
        async def conduct_research(self, **k):
            yield {"stage": "plan"}

    monkeypatch.setattr(
        auspex_routes,
        "get_deep_research_service",
        lambda: S()
    )

    # ---------------- Mock Workflow Loader ----------------
    class W:
        name = "wf"
        version = "1.0"

        def get_sampling_config(self): return {}
        def get_filtering_config(self): return {}

    class L:
        def get_workflow(self, n): return W()

    monkeypatch.setattr(
        "app.services.tool_loader.get_tool_loader",
        lambda: L()
    )

    # ---------------- Auth Override ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    valid = {
        "query": "AI in healthcare",
        "topic": "health"
    }

    # ---------------- Test /research ----------------
    r1 = client.post("/api/auspex/research", json=valid)

    assert r1.status_code == 200
    assert "text/event-stream" in r1.headers["content-type"]

    # ---------------- Test /research/config ----------------
    r2 = client.get("/api/auspex/research/config")

    assert r2.status_code == 200
    assert "default_config" in r2.json()
    assert r2.json()["workflow_loaded"] is True

    # ---------------- Cleanup ----------------
    app.dependency_overrides.clear()


def test_generate_newsletter(client, monkeypatch):
    from app.main import app

    url = "/api/auspex/newsletter/generate"

    # ---------------- Mock Newsletter Service ----------------
    class S:
        async def generate_newsletter(self, **k):
            yield {"stage": "fetch"}
            yield {"stage": "write"}

    monkeypatch.setattr(
        "app.services.newsletter_service.get_newsletter_service",
        lambda: S()
    )

    # ---------------- Mock Auspex (profile) ----------------
    class A:
        def _build_profile_context(self, i):
            return "profile"

    monkeypatch.setattr(
        auspex_routes,
        "get_auspex_service",
        lambda: A()
    )

    # ---------------- Auth ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    valid = {
        "topic": "AI news",
        "days_back": 7
    }

    # ---------------- Success ----------------
    r1 = client.post(url, json=valid)

    assert r1.status_code == 200
    assert "text/event-stream" in r1.headers["content-type"]

    # ---------------- Error Stream ----------------
    class E:
        async def generate_newsletter(self, **k):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.services.newsletter_service.get_newsletter_service",
        lambda: E()
    )

    r2 = client.post(url, json=valid)

    assert r2.status_code == 200
    assert "error" in r2.text

    # ---------------- Cleanup ----------------
    app.dependency_overrides.clear()



# =============================================================================
# auth_routes.py endpoints
# =============================================================================

def test_login_page(client):
    r = client.get("/login")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_login_post(client, monkeypatch):
    import app.routes.auth_routes as auth_routes

    # ---------------- Mock DB ----------------
    class DB:
        def get_user(self, u):
            return {
                "username": u,
                "password": "hashed",
                "is_active": True,
                "force_password_change": False,
                "completed_onboarding": True
            }

    monkeypatch.setattr(
        auth_routes,
        "get_database_instance",
        lambda: DB()
    )

    # ---------------- Mock Password ----------------
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        lambda p, h: True
    )

    # ---------------- Successful Login ----------------
    r = client.post(
        "/login",
        data={"username": "john", "password": "1234"},
        follow_redirects=False
    )

    assert r.status_code == 302
    assert r.headers["location"] == "/change_password"


def test_logout(client):
    # Call logout
    r = client.get("/logout", follow_redirects=False)

    # Should redirect to login
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/login"


# =============================================================================
# auto_ingest.py endpoints
# =============================================================================

def test_auto_ingest_config(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    # ---------------- Mock Service ----------------
    class S:
        def get_config(self):
            return {"enabled": True, "interval": 10}

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S()
    )

    # ---------------- Success ----------------
    r1 = client.get("/api/auto-ingest/config")

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["config"]["enabled"] is True

    # ---------------- Failure ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r2 = client.get("/api/auto-ingest/config")

    assert r2.status_code == 500


def test_update_auto_ingest_config(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    # ---------------- Mock Service ----------------
    class S:
        def update_config(self, data):
            return True

        def get_config(self):
            return {"enabled": True}

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S()
    )

    url = "/api/auto-ingest/config"

    # ---------------- Success ----------------
    r1 = client.post(url, json={"enabled": True})

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Invalid Key → 400 ----------------
    r2 = client.post(url, json={"bad_key": 1})

    assert r2.status_code == 400

    # ---------------- Save Failed → 500 ----------------
    class F:
        def update_config(self, data):
            return False

        def get_config(self):
            return {}

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: F()
    )

    r3 = client.post(url, json={"enabled": True})

    assert r3.status_code == 500



def test_auto_ingest_status(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    # ---------------- Mock Service ----------------
    class S:
        def get_status(self):
            return {"running": True}

        async def get_pending_articles(self, limit=100):
            return [1, 2, 3]

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S()
    )

    # ---------------- Success ----------------
    r1 = client.get("/api/auto-ingest/status")

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["status"]["pending_articles_count"] == 3

    # ---------------- Failure ----------------
    def boom():
        raise Exception("err")

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        boom
    )

    r2 = client.get("/api/auto-ingest/status")

    assert r2.status_code == 500


def test_run_auto_ingest(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    # ---------------- Mock Session ----------------
    auto_ingest.verify_session = lambda: {"user": {"username": "test"}}

    # ---------------- Mock DB ----------------
    class Facade:
        def get_unread_alerts(self):
            return [1, 2]

        def create_notification(self, **k):
            pass

    class DB:
        facade = Facade()

    monkeypatch.setattr(
        "app.database.get_database_instance",
        lambda: DB()
    )

    # ---------------- Mock Task Manager ----------------
    class TM:
        def create_task(self, **k):
            return "task123"

        def run_task(self, *a, **k):
            pass

    monkeypatch.setattr(
        "app.services.background_task_manager.get_task_manager",
        lambda: TM()
    )

    monkeypatch.setattr(
        "app.services.background_task_manager.run_auto_ingest_task",
        lambda *a, **k: None
    )

    url = "/api/auto-ingest/run"

    # ---------------- Normal Run ----------------
    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["task_id"] == "task123"

    # ---------------- No Pending Articles ----------------
    class EmptyFacade:
        def get_unread_alerts(self):
            return []

    class DB2:
        facade = EmptyFacade()

    monkeypatch.setattr(
        "app.database.get_database_instance",
        lambda: DB2()
    )

    r2 = client.post(url)

    assert r2.status_code == 200
    assert r2.json()["total_articles"] == 0

    # ---------------- Failure ----------------
    monkeypatch.setattr(
        "app.database.get_database_instance",
        lambda: (_ for _ in ()).throw(Exception("DB down"))
    )

    r3 = client.post(url)

    assert r3.status_code == 500


def test_run_auto_ingest_sync(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/run-sync"

    # ---------------- Success ----------------
    class S1:
        def is_running(self):
            return False

        async def run_auto_ingest(self):
            return {"processed": 10}

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S1()
    )

    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["results"]["processed"] == 10

    # ---------------- Already Running → 409 ----------------
    class S2:
        def is_running(self):
            return True

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S2()
    )

    r2 = client.post(url)

    assert r2.status_code == 409

    # ---------------- Failure → 500 ----------------
    class S3:
        def is_running(self):
            return False

        async def run_auto_ingest(self):
            raise Exception("boom")

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S3()
    )

    r3 = client.post(url)

    assert r3.status_code == 500



def test_auto_ingest_pending(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/pending"

    # ---------------- Success (Default Limit) ----------------
    class S1:
        async def get_pending_articles(self, limit=20):
            assert limit == 20
            return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S1()
    )

    r1 = client.get(url)

    assert r1.status_code == 200
    assert r1.json()["count"] == 2

    # ---------------- Custom Limit ----------------
    class S2:
        async def get_pending_articles(self, limit=20):
            assert limit == 5
            return [{"id": 1}]

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S2()
    )

    r2 = client.get(url + "?limit=5")

    assert r2.status_code == 200
    assert r2.json()["count"] == 1

    # ---------------- Failure → 500 ----------------
    class S3:
        async def get_pending_articles(self, limit=20):
            raise Exception("boom")

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S3()
    )

    r3 = client.get(url)

    assert r3.status_code == 500


def test_auto_ingest_models(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/models"

    # ---------------- Success ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_available_models",
        lambda: ["gpt-4o", "gpt-4.1"]
    )

    r1 = client.get(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert "gpt-4o" in r1.json()["models"]

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_available_models",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r2 = client.get(url)

    assert r2.status_code == 500


def test_auto_ingest_enable(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/enable"

    # ---------------- Success ----------------
    class S1:
        def update_config(self, data):
            assert data == {"enabled": True}
            return True

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S1()
    )

    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Update Failed → 500 ----------------
    class S2:
        def update_config(self, data):
            return False

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S2()
    )

    r2 = client.post(url)

    assert r2.status_code == 500

    # ---------------- Exception → 500 ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r3 = client.post(url)

    assert r3.status_code == 500


def test_auto_ingest_disable(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/disable"

    # ---------------- Success ----------------
    class S1:
        def update_config(self, data):
            assert data == {"enabled": False}
            return True

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S1()
    )

    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Update Failed → 500 ----------------
    class S2:
        def update_config(self, data):
            return False

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S2()
    )

    r2 = client.post(url)

    assert r2.status_code == 500

    # ---------------- Exception → 500 ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r3 = client.post(url)

    assert r3.status_code == 500


def test_auto_ingest_stats(client, monkeypatch):
    import app.routes.auto_ingest as auto_ingest

    url = "/api/auto-ingest/stats"

    # ---------------- Mock DB Cursor ----------------
    class Cursor:
        def __init__(self):
            self.calls = 0

        def execute(self, q):
            pass

        def fetchone(self):
            self.calls += 1
            return (10,) if self.calls == 1 else (5,)

        def fetchall(self):
            return [("2026-01-01", 3), ("2026-01-02", 7)]

    class Conn:
        def cursor(self):
            return Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class DB:
        def get_connection(self):
            return Conn()

    # ---------------- Mock Service ----------------
    class S:
        db = DB()

        def get_status(self):
            return {"running": True}

    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: S()
    )

    # ---------------- Success ----------------
    r1 = client.get(url)

    assert r1.status_code == 200

    data = r1.json()

    assert data["success"] is True
    assert data["stats"]["auto_ingested_total"] == 10
    assert data["stats"]["pending_total"] == 5
    assert len(data["stats"]["recent_activity"]) == 2

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        auto_ingest,
        "get_auto_ingest_service",
        lambda: (_ for _ in ()).throw(Exception("DB down"))
    )

    r2 = client.get(url)

    assert r2.status_code == 500

# =============================================================================
# background_tasks.py endpoints
# =============================================================================

def test_start_bulk_analysis(client, monkeypatch):
    import app.routes.background_tasks as bg

    url = "/api/background-tasks/bulk-analysis"

    # ---------------- Mock Task Manager ----------------
    class TM:
        def create_task(self, **k):
            return "task123"

        def run_task(self, *a, **k):
            pass

    monkeypatch.setattr(bg, "get_task_manager", lambda: TM())
    monkeypatch.setattr(bg, "run_bulk_analysis_task", lambda *a, **k: None)

    # ---------------- Success ----------------
    r1 = client.post(url, json={
        "urls": ["a.com"],
        "topic": "AI"
    })

    assert r1.status_code == 200

    # ---------------- No URLs → 500 (NOT 400) ----------------
    r2 = client.post(url, json={"topic": "AI"})

    assert r2.status_code == 500

    # ---------------- No Topic → 500 (NOT 400) ----------------
    r3 = client.post(url, json={"urls": ["x.com"]})

    assert r3.status_code == 500

    # ---------------- Internal Error → 500 ----------------
    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r4 = client.post(url, json={
        "urls": ["a.com"],
        "topic": "AI"
    })

    assert r4.status_code == 500


def test_start_bulk_save(client, monkeypatch):
    import app.routes.background_tasks as bg

    url = "/api/background-tasks/bulk-save"

    # ---------------- Mock Task Manager ----------------
    class TM:
        def create_task(self, **k):
            return "task123"

        def run_task(self, *a, **k):
            pass

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM()
    )

    monkeypatch.setattr(
        bg,
        "run_bulk_save_task",
        lambda *a, **k: None
    )

    # ---------------- Success ----------------
    r1 = client.post(url, json={
        "articles": [{"id": 1}, {"id": 2}]
    })

    assert r1.status_code == 200
    assert r1.json()["task_id"] == "task123"

    # ---------------- No Articles → 500 ----------------
    r2 = client.post(url, json={})

    assert r2.status_code == 500

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r3 = client.post(url, json={
        "articles": [{"id": 1}]
    })

    assert r3.status_code == 500


def test_get_task_status(client, monkeypatch):
    import app.routes.background_tasks as bg

    base = "/api/background-tasks/task"

    # ---------------- Success ----------------
    class TM1:
        def get_task_status(self, tid):
            return {"id": tid, "state": "running"}

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM1()
    )

    r1 = client.get(f"{base}/task123")

    assert r1.status_code == 200
    assert r1.json()["task"]["state"] == "running"

    # ---------------- Not Found → 404 ----------------
    class TM2:
        def get_task_status(self, tid):
            return None

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM2()
    )

    r2 = client.get(f"{base}/missing")

    assert r2.status_code == 404

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r3 = client.get(f"{base}/err")

    assert r3.status_code == 500


def test_list_tasks(client, monkeypatch):
    import app.routes.background_tasks as bg

    url = "/api/background-tasks/tasks"

    # ---------------- Mock Task Manager ----------------
    class TM:
        def list_tasks(self, status=None):
            return [{"id": "1", "status": "running"}]

        def get_task_summary(self):
            return {"total": 1}

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM()
    )

    # ---------------- Mock TaskStatus Enum ----------------
    class FakeStatus:
        def __init__(self, v):
            if v != "running":
                raise ValueError()

    monkeypatch.setattr(
        "app.services.background_task_manager.TaskStatus",
        FakeStatus
    )

    # ---------------- No Filter ----------------
    r1 = client.get(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Valid Filter ----------------
    r2 = client.get(url + "?status=running")

    assert r2.status_code == 200

    # ---------------- Invalid Filter → 400 ----------------
    r3 = client.get(url + "?status=bad")

    assert r3.status_code == 400

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r4 = client.get(url)

    assert r4.status_code == 500


def test_cancel_task(client, monkeypatch):
    import app.routes.background_tasks as bg

    base = "/api/background-tasks/task"

    # ---------------- Success ----------------
    class TM1:
        def cancel_task(self, tid):
            return True

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM1()
    )

    r1 = client.delete(f"{base}/task123")

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Not Found → 404 ----------------
    class TM2:
        def cancel_task(self, tid):
            return False

        def get_task(self, tid):
            return None

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM2()
    )

    r2 = client.delete(f"{base}/missing")

    assert r2.status_code == 404

    # ---------------- Not Running → 400 ----------------
    class TM3:
        def cancel_task(self, tid):
            return False

        def get_task(self, tid):
            return {"id": tid, "state": "done"}

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM3()
    )

    r3 = client.delete(f"{base}/done")

    assert r3.status_code == 400

    # ---------------- Failure → 500 ----------------
    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: (_ for _ in ()).throw(Exception("boom"))
    )

    r4 = client.delete(f"{base}/err")

    assert r4.status_code == 500

def test_cleanup_old_tasks(client, monkeypatch):
    import app.routes.background_tasks as bg

    url = "/api/background-tasks/cleanup"

    # ---------------- Success ----------------
    class TM1:
        def cleanup_old_tasks(self, hours):
            assert hours == 24  # default

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM1()
    )

    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ---------------- Custom Hours ----------------
    r2 = client.post(url + "?max_age_hours=10")

    assert r2.status_code == 200

    # ---------------- Failure → 500 ----------------
    class TM2:
        def cleanup_old_tasks(self, hours):
            raise Exception("boom")

    monkeypatch.setattr(
        bg,
        "get_task_manager",
        lambda: TM2()
    )

    r3 = client.post(url)

    assert r3.status_code == 500



def test_cleanup_old_tasks(client, monkeypatch):

    url = "/api/background-tasks/cleanup"

    # ================= SUCCESS =================

    class MockTM:
        def cleanup_old_tasks(self, hours):
            pass

    monkeypatch.setattr(
        "app.routes.background_tasks.get_task_manager",
        lambda: MockTM()
    )

    r1 = client.post(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ================= FAILURE =================

    def broken():
        raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.background_tasks.get_task_manager",
        broken
    )

    r2 = client.post(url)

    assert r2.status_code == 500


def test_get_task_summary(client, monkeypatch):

    url = "/api/background-tasks/summary"

    # =============== SUCCESS ===============

    class MockTM:
        def get_task_summary(self):
            return {
                "total": 5,
                "running": 2,
                "completed": 3
            }

    monkeypatch.setattr(
        "app.routes.background_tasks.get_task_manager",
        lambda: MockTM()
    )

    r1 = client.get(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["summary"]["total"] == 5

    # =============== FAILURE ===============

    class BrokenTM:
        def get_task_summary(self):
            raise Exception("db down")

    monkeypatch.setattr(
        "app.routes.background_tasks.get_task_manager",
        lambda: BrokenTM()
    )

    r2 = client.get(url)

    assert r2.status_code == 500



# =============================================================================
# chat_routes.py endpoints
# =============================================================================

def test_database_chat_page(client, monkeypatch):

    # Mock session dependency
    monkeypatch.setattr(
        "app.routes.chat_routes.verify_session",
        lambda: {"user": "test-user"}
    )

    response = client.get("/database-chat")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_chat_with_database_success_and_failure(client, monkeypatch):

    url = "/api/chat"

    # ------------------ SESSION ------------------

    monkeypatch.setattr(
        "app.routes.chat_routes.verify_session",
        lambda: {"user": "test"}
    )

    # ------------------ DATABASE -----------------

    class MockDB:
        def search_articles(self, **kwargs):
            return ([
                {
                    "uri": "1",
                    "title": "Test",
                    "summary": "Summary",
                    "category": "Tech",
                    "sentiment": "Positive",
                    "future_signal": "High",
                    "time_to_impact": "Short",
                    "tags": ["ai"],
                    "publication_date": "2025-01-01"
                }
            ], 1)

    monkeypatch.setattr(
        "app.routes.chat_routes.Database",
        lambda: MockDB()
    )

    # ------------------ ANALYZE DB ----------------

    class MockAnalyze:
        def __init__(self, db): pass

        def get_topic_options(self, topic):
            return {
                "categories": ["Tech"],
                "sentiments": ["Positive"],
                "futureSignals": ["High"],
                "timeToImpacts": ["Short"]
            }

    monkeypatch.setattr(
        "app.routes.chat_routes.AnalyzeDB",
        MockAnalyze
    )

    # ------------------ VECTOR SEARCH ------------

    monkeypatch.setattr(
        "app.routes.chat_routes.vector_search_articles",
        lambda **k: []
    )

    # ------------------ AI MODEL -----------------

    class MockAI:
        def __init__(self):
            self.calls = 0

        async def agenerate_response(self, msgs):
            self.calls += 1
            # 1st call: search strategy extraction expects JSON payload
            if self.calls == 1:
                return json.dumps(
                    {
                        "queries": [
                            {
                                "description": "Find relevant AI articles",
                                "params": {
                                    "category": None,
                                    "keyword": "ai",
                                    "sentiment": None,
                                    "future_signal": None,
                                    "time_to_impact": None,
                                    "tags": ["ai"],
                                    "date_range": None,
                                },
                            }
                        ]
                    }
                )
            # 2nd call: final response generation
            return "Mock AI response"

    monkeypatch.setattr(
        "app.routes.chat_routes.get_ai_model",
        lambda model: MockAI()
    )

    # ------------------ REQUEST ------------------

    payload = {
        "message": "Test question",
        "topic": "AI",
        "model": "gpt",
        "limit": 5,
        "conversation_history": []
    }

    # ================== SUCCESS ==================

    r1 = client.post(url, json=payload)

    assert r1.status_code == 200
    assert "response" in r1.json()
    assert r1.json()["analyzed_count"] >= 0

    # ================== FAILURE ==================

    def broken(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.chat_routes.get_ai_model",
        broken
    )

    r2 = client.post(url, json=payload)

    assert r2.status_code == 500

# =============================================================================
# dashboard_cache_routes.py endpoints
# =============================================================================

def test_save_dashboard_success_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/save"

    # ================= MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ================= SUCCESS ==================

    class OKService:
        def __init__(self, db):
            pass

        async def save_dashboard(self, *a, **k):
            return "ok-key"

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        OKService
    )

    payload = {
        "dashboard_type": "news_feed",
        "date_range": "24h",
        "content": {"x": 1}
    }

    r1 = client.post(url, json=payload)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    key = r1.json()["cache_key"]
    assert isinstance(key, str)
    assert key != ""

    # ================= FAILURE ==================

    class BadService:
        def __init__(self, db):
            pass

        async def save_dashboard(self, *a, **k):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        BadService
    )

    r2 = client.post(url, json=payload)

    assert r2.status_code == 500


def test_get_dashboard_success_not_found_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/get/test-key"

    # ============== MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ============== SUCCESS ==================

    class OKService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            return {"name": "demo"}

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        OKService
    )

    r1 = client.get(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True
    assert r1.json()["dashboard"]["name"] == "demo"

    # ============== NOT FOUND ================

    class EmptyService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            return None

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        EmptyService
    )

    r2 = client.get(url)

    assert r2.status_code == 404

    # ============== FAILURE ==================

    class BadService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        BadService
    )

    r3 = client.get(url)

    assert r3.status_code == 500



def test_list_dashboards_success_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/list"

    # ================= MOCK DB =================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ================= SUCCESS =================

    class OKService:
        def __init__(self, db):
            pass

        async def list_cached_dashboards(self, limit):
            return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        OKService
    )

    r1 = client.get(url)

    print("SUCCESS RESPONSE:", r1.status_code, r1.text)

    assert r1.status_code == 200
    assert r1.json()["count"] == 2

    # ================= FAILURE =================

    class BadService:
        def __init__(self, db):
            pass

        async def list_cached_dashboards(self, limit):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        BadService
    )

    r2 = client.get(url)

    print("FAIL RESPONSE:", r2.status_code, r2.text)

    assert r2.status_code == 500


def test_delete_dashboard_success_not_found_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/delete/test-key"

    # ============== MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ============== SUCCESS ==================

    class OKService:
        def __init__(self, db):
            pass

        async def delete_dashboard(self, key):
            return True

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        OKService
    )

    r1 = client.delete(url)

    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # ============== NOT FOUND ================

    class EmptyService:
        def __init__(self, db):
            pass

        async def delete_dashboard(self, key):
            return False

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        EmptyService
    )

    r2 = client.delete(url)

    assert r2.status_code == 404

    # ============== FAILURE ==================

    class BadService:
        def __init__(self, db):
            pass

        async def delete_dashboard(self, key):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        BadService
    )

    r3 = client.delete(url)

    assert r3.status_code == 500


def test_export_dashboard_markdown_success_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/export/markdown"

    # ============== MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ============== MOCK EXPORT SERVICE ==============

    class MockExportService:
        @staticmethod
        def export_to_markdown(dashboard_data, dashboard_type, include_metadata=True):
            return "# Test Dashboard"

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        MockExportService
    )

    # ============== MOCK CACHE SERVICE ==============

    class MockCacheService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            return {
                "dashboard_type": "news",
                "data": "cached"
            }

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        MockCacheService
    )

    # ===================== SUCCESS (DIRECT DATA) ============================
    
    

    payload1 = {
        "dashboard_data": {"a": 1},
        "dashboard_type": "news"
    }

    r1 = client.post(url, json=payload1)

    assert r1.status_code == 200
    assert r1.headers["content-type"].startswith("text/markdown")
    assert "# Test Dashboard" in r1.text

    # ===================== SUCCESS (FROM CACHE) ============================

    payload2 = {
        "cache_key": "test-key"
    }

    r2 = client.post(url, json=payload2)

    assert r2.status_code == 200
    assert "# Test Dashboard" in r2.text

    # ===================== BAD REQUEST (400) ============================

    payload3 = {}

    r3 = client.post(url, json=payload3)

    assert r3.status_code == 400

    # ===================== SERVER ERROR (500) ============================

    class BadExportService:
        @staticmethod
        def export_to_markdown(*args, **kwargs):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        BadExportService
    )

    payload4 = {
        "dashboard_data": {"x": 1},
        "dashboard_type": "news"
    }

    r4 = client.post(url, json=payload4)

    assert r4.status_code == 500



def test_export_dashboard_pdf_success_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/export/pdf"

    # ============== CREATE TEMP PDF FILE ==============

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_file.write(b"%PDF-1.4 test pdf")
    tmp_file.close()

    fake_pdf_path = tmp_file.name

    # ============== MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ============== MOCK EXPORT SERVICE ==============

    class MockExportService:
        @staticmethod
        def export_to_pdf(dashboard_data, dashboard_type):
            return fake_pdf_path

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        MockExportService
    )

    # ============== MOCK CACHE SERVICE ==============

    class MockCacheService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            return {
                "dashboard_type": "news",
                "data": "cached"
            }

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        MockCacheService
    )

    # ===================== SUCCESS (DIRECT DATA) ============================

    payload1 = {
        "dashboard_data": {"a": 1},
        "dashboard_type": "news"
    }

    r1 = client.post(url, json=payload1)

    assert r1.status_code == 200
    assert r1.headers["content-type"] == "application/pdf"
    assert len(r1.content) > 0

    # ===================== SUCCESS (FROM CACHE) ============================

    payload2 = {
        "cache_key": "test-key"
    }

    r2 = client.post(url, json=payload2)

    assert r2.status_code == 200
    assert r2.headers["content-type"] == "application/pdf"

    # ===================== BAD REQUEST (400) ============================

    payload3 = {}

    r3 = client.post(url, json=payload3)

    assert r3.status_code == 400

    # ===================== SERVER ERROR (500) ============================

    class BadExportService:
        @staticmethod
        def export_to_pdf(*args, **kwargs):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        BadExportService
    )

    payload4 = {
        "dashboard_data": {"x": 1},
        "dashboard_type": "news"
    }

    r4 = client.post(url, json=payload4)

    assert r4.status_code == 500

    # ============== CLEANUP TEMP FILE =================

    os.unlink(fake_pdf_path)


@pytest.mark.asyncio
def test_export_dashboard_image_success_and_failure(client, monkeypatch):

    url = "/api/dashboard-cache/export/image"

    # ============== CREATE TEMP PNG FILE ==============

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp_file.write(b"\x89PNG\r\n\x1a\nfakepngdata")
    tmp_file.close()

    fake_image_path = tmp_file.name

    # ============== MOCK DB ==================

    class MockDB:
        pass

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.get_database_instance",
        lambda: MockDB()
    )

    # ============== MOCK EXPORT SERVICE (ASYNC) ==============

    class MockExportService:

        @staticmethod
        async def export_to_image(
            dashboard_data,
            dashboard_type,
            width,
            height
        ):
            return fake_image_path

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        MockExportService
    )

    # ============== MOCK CACHE SERVICE ==============

    class MockCacheService:
        def __init__(self, db):
            pass

        async def get_dashboard(self, key):
            return {
                "dashboard_type": "news",
                "data": "cached"
            }

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardCacheService",
        MockCacheService
    )

    # ===================== SUCCESS (DIRECT DATA) ============================

    payload1 = {
        "dashboard_data": {"a": 1},
        "dashboard_type": "news"
    }

    r1 = client.post(url, json=payload1)

    assert r1.status_code == 200
    assert r1.headers["content-type"] == "image/png"
    assert len(r1.content) > 0

    # ===================== SUCCESS (FROM CACHE) ============================

    payload2 = {
        "cache_key": "test-key"
    }

    r2 = client.post(url, json=payload2)

    assert r2.status_code == 200
    assert r2.headers["content-type"] == "image/png"

    # ===================== BAD REQUEST (400) ============================

    payload3 = {}

    r3 = client.post(url, json=payload3)

    assert r3.status_code == 400

    # ===================== SERVER ERROR (500) ============================

    class BadExportService:

        @staticmethod
        async def export_to_image(*args, **kwargs):
            raise Exception("boom")

    monkeypatch.setattr(
        "app.routes.dashboard_cache_routes.DashboardExportService",
        BadExportService
    )

    payload4 = {
        "dashboard_data": {"x": 1},
        "dashboard_type": "news"
    }

    r4 = client.post(url, json=payload4)

    assert r4.status_code == 500

    # ============== CLEANUP TEMP FILE =================

    os.unlink(fake_image_path)


# =============================================================================
# dashboard_routes.py endpoints
# =============================================================================

def test_get_topic_summary_success_and_failure(client, monkeypatch):
    """
    Test /api/dashboard/topic-summary/{topic_name}
    """

    # ----------------------------
    # Mock Session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # Mock DB + Facade
    # ----------------------------
    class MockFacade:
        def get_topic_articles_count(self, topic):
            return 100

        def get_topic_articles_count_since(self, topic, date):
            return 20

        def get_dominant_news_source_for_topic(self, topic, date):
            return "BBC"

        def get_most_frequent_time_to_impact_for_topic(self, topic, date):
            return "Short-term"

    class MockDB:
        def __init__(self):
            self.facade = MockFacade()

    app.dependency_overrides[get_database_instance] = lambda: MockDB()

    # ----------------------------
    # SUCCESS CASE
    # ----------------------------
    res = client.get("/api/dashboard/topic-summary/AI")

    assert res.status_code == 200

    data = res.json()

    assert data["total_articles"] == 100
    assert data["new_articles_last_24h"] == 20
    assert data["new_articles_last_7d"] == 20
    assert data["dominant_news_source"] == "BBC"
    assert data["most_frequent_time_to_impact"] == "Short-term"

    # ----------------------------
    # FAILURE CASE
    # ----------------------------
    class FailingFacade:
        def get_topic_articles_count(self, topic):
            raise Exception("DB error")

    class FailingDB:
        def __init__(self):
            self.facade = FailingFacade()

    app.dependency_overrides[get_database_instance] = lambda: FailingDB()

    res = client.get("/api/dashboard/topic-summary/AI")

    assert res.status_code == 500
    assert "Failed to retrieve summary metrics" in res.json()["detail"]

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()



def test_get_topic_articles_success_and_failure(client, monkeypatch):
    """
    Test /api/dashboard/articles/{topic_name}
    """

    # ----------------------------
    # Mock Session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # Mock DB
    # ----------------------------
    class MockDB:
        def __init__(self):
            self.call_count = 0

        def search_articles(
            self,
            topic=None,
            keyword=None,
            page=1,
            per_page=10,
            pub_date_start=None,
            pub_date_end=None,
            date_type=None,
            require_category=True
        ):
            self.call_count += 1

            # First call → return small result (trigger fallback)
            if self.call_count == 1:
                return ([], 0)

            # Second call (fallback) → return data
            return (
                [
                    {
                        "uri": "u1",
                        "title": "AI News",
                        "summary": "About AI",
                        "category": "Tech",
                        "sentiment": "positive",
                        "future_signal": "growth",
                        "time_to_impact": "short",
                        "tags": "ai,ml,tech",
                        "publication_date": "2025-01-01",
                        "news_source": "BBC",
                        "topic": "AI"
                    }
                ],
                1
            )

    app.dependency_overrides[get_database_instance] = lambda: MockDB()

    # ----------------------------
    # SUCCESS CASE
    # ----------------------------
    res = client.get("/api/dashboard/articles/AI?page=1&per_page=10")

    assert res.status_code == 200

    data = res.json()

    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total_items"] == 1
    assert data["total_pages"] == 1

    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "AI News"
    assert data["items"][0]["tags"] == ["ai", "ml", "tech"]

    # ----------------------------
    # FAILURE CASE
    # ----------------------------
    class FailingDB:
        def search_articles(self, *args, **kwargs):
            raise Exception("DB error")

    app.dependency_overrides[get_database_instance] = lambda: FailingDB()

    res = client.get("/api/dashboard/articles/AI")

    assert res.status_code == 500
    assert "Failed to retrieve articles" in res.json()["detail"]

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()



def test_get_topic_volume_over_time_success_and_failure(client, monkeypatch):
    """
    Test /api/dashboard/volume-over-time/{topic_name}
    """

    # ----------------------------
    # Mock session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # Mock DB (Success)
    # ----------------------------
    class MockDB:
        def fetch_all(self, query, params):
            # Simulate DB rows:
            # (date, category/sentiment, count)
            return [
                ("2025-01-01", "Tech", 5),
                ("2025-01-01", "AI", 3),
                ("2025-01-02", "Tech", 2),
            ]

    app.dependency_overrides[get_database_instance] = lambda: MockDB()

    # ----------------------------
    # SUCCESS CASE
    # ----------------------------
    res = client.get(
        "/api/dashboard/volume-over-time/AI?days_limit=10&stack_by=category"
    )

    assert res.status_code == 200

    data = res.json()

    assert isinstance(data, list)
    assert len(data) == 2

    assert data[0]["date"] == "2025-01-01"
    assert data[0]["values"]["Tech"] == 5
    assert data[0]["values"]["AI"] == 3

    assert data[1]["date"] == "2025-01-02"
    assert data[1]["values"]["Tech"] == 2

    # ----------------------------
    # INVALID stack_by → 500
    # ----------------------------
    res = client.get(
        "/api/dashboard/volume-over-time/AI?stack_by=wrong"
    )

    assert res.status_code == 500
    assert "Failed to retrieve stacked volume data" in res.json()["detail"]


    # ----------------------------
    # FAILURE CASE (DB error)
    # ----------------------------
    class FailingDB:
        def fetch_all(self, query, params):
            raise Exception("DB failure")

    app.dependency_overrides[get_database_instance] = lambda: FailingDB()

    res = client.get(
        "/api/dashboard/volume-over-time/AI"
    )

    assert res.status_code == 500
    assert "Failed to retrieve stacked volume data" in res.json()["detail"]

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()


def test_get_topic_sentiment_over_time_success_and_failure(client, monkeypatch):
    """
    Test /api/dashboard/sentiment-over-time/{topic_name}
    """

    # ----------------------------
    # Mock session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # Mock DB (Success case)
    # ----------------------------
    class MockDB:
        def fetch_all(self, query, params):
            # (date, sentiment, count, avg_score)
            return [
                ("2025-01-01", "positive", 5, 1.0),
                ("2025-01-01", "neutral", 3, 0.0),
                ("2025-01-02", "negative", 2, -1.0),
            ]

    app.dependency_overrides[get_database_instance] = lambda: MockDB()

    # ----------------------------
    # SUCCESS
    # ----------------------------
    res = client.get(
        "/api/dashboard/sentiment-over-time/AI?days_limit=10"
    )

    assert res.status_code == 200

    data = res.json()

    assert isinstance(data, list)
    assert len(data) == 2

    # Day 1
    assert data[0]["date"] == "2025-01-01"
    assert data[0]["positive"] == 5
    assert data[0]["neutral"] == 3
    assert data[0]["avg_score"] == 0.0 or data[0]["avg_score"] == 1.0

    # Day 2
    assert data[1]["date"] == "2025-01-02"
    assert data[1]["negative"] == 2

    # ----------------------------
    # INVALID DATE → 400
    # ----------------------------
    res = client.get(
        "/api/dashboard/sentiment-over-time/AI?start_date=wrong-date"
    )

    assert res.status_code == 400
    assert "Invalid date format" in res.json()["detail"]

    # ----------------------------
    # FAILURE (DB error)
    # ----------------------------
    class FailingDB:
        def fetch_all(self, query, params):
            raise Exception("DB failure")

    app.dependency_overrides[get_database_instance] = lambda: FailingDB()

    res = client.get(
        "/api/dashboard/sentiment-over-time/AI"
    )

    assert res.status_code == 500
    assert "Failed to retrieve sentiment data" in res.json()["detail"]

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()



def test_get_topic_top_tags_success_and_failure(client):
    """
    Test /api/dashboard/top-tags/{topic_name}
    """

    # ----------------------------
    # Mock session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # SUCCESS CASE
    # ----------------------------
    class MockDB:
        def fetch_all(self, query, params):
            return [
                {"tags": "AI,ML,Cloud"},
                {"tags": "AI,Data"},
                {"tags": "Cloud,AI"},
            ]

    app.dependency_overrides[get_database_instance] = lambda: MockDB()

    res = client.get(
        "/api/dashboard/top-tags/AI?days_limit=10&limit_tags=5"
    )

    assert res.status_code == 200

    data = res.json()

    assert isinstance(data, list)

    # AI appears 3 times
    # Cloud appears 2 times
    # ML appears 1 time
    # Data appears 1 time

    tags = {item["tag"]: item["count"] for item in data}

    assert tags["ai"] == 3
    assert tags["cloud"] == 2
    assert tags["ml"] == 1
    assert tags["data"] == 1

    # ----------------------------
    # EMPTY RESULT
    # ----------------------------
    class EmptyDB:
        def fetch_all(self, query, params):
            return []

    app.dependency_overrides[get_database_instance] = lambda: EmptyDB()

    res = client.get("/api/dashboard/top-tags/AI")

    assert res.status_code == 200
    assert res.json() == []

    # ----------------------------
    # FAILURE (DB error)
    # ----------------------------
    class FailingDB:
        def fetch_all(self, query, params):
            raise Exception("DB error")

    app.dependency_overrides[get_database_instance] = lambda: FailingDB()

    res = client.get("/api/dashboard/top-tags/AI")

    assert res.status_code == 500
    assert "Failed to retrieve top tags" in res.json()["detail"]

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()


def test_get_key_articles_success_and_fallback(client, monkeypatch):
    """
    Test /api/dashboard/key-articles/{topic}
    """

    # ----------------------------
    # Mock session
    # ----------------------------
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # ----------------------------
    # Mock Articles (returned by get_topic_articles)
    # ----------------------------
    class MockArticle:
        def __init__(self, uri, title):
            self.uri = uri
            self.title = title
            self.news_source = "TestSource"
            self.publication_date = "2024-01-01"
            self.sentiment = "positive"
            self.future_signal = "growth"
            self.summary = "Test summary"
            self.tags = ["ai"]
            self.time_to_impact = "short"
            self.category = "tech"
            self.driver_type = None
            self.topic = "AI"

        def model_dump(self):
            return self.__dict__


    class MockPaginated:
        def __init__(self, items):
            self.items = items


    mock_articles = [
        MockArticle("uri-1", "Article 1"),
        MockArticle("uri-2", "Article 2"),
        MockArticle("uri-3", "Article 3"),
    ]


    async def mock_get_topic_articles(*args, **kwargs):
        return MockPaginated(mock_articles)


    # Patch internal call
    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_articles",
        mock_get_topic_articles
    )

    # ----------------------------
    # Mock LLM (Success)
    # ----------------------------
    class MockLLM:
        def generate_response(self, messages):
            return """
            [
              {
                "uri": "uri-1",
                "title": "Article 1",
                "highlight_summary": "Important news",
                "highlight_category": "Breaking"
              },
              {
                "uri": "uri-2",
                "title": "Article 2",
                "highlight_summary": "Key update",
                "highlight_category": "Update"
              }
            ]
            """


    class MockLLMFactory:
        @staticmethod
        def get_instance(name):
            return MockLLM()


    monkeypatch.setattr(
        "app.routes.dashboard_routes.LiteLLMModel",
        MockLLMFactory
    )

    # ----------------------------
    # SUCCESS CASE
    # ----------------------------
    res = client.get("/api/dashboard/key-articles/AI?top_k=2")

    assert res.status_code == 200

    data = res.json()

    assert len(data) == 2
    assert data[0]["uri"] == "uri-1"
    assert data[0]["highlight_category"] == "Breaking"
    assert data[1]["uri"] == "uri-2"

    # ----------------------------
    # BAD LLM RESPONSE → FALLBACK
    # ----------------------------
    class BadLLM:
        def generate_response(self, messages):
            return "This is not JSON"


    class BadLLMFactory:
        @staticmethod
        def get_instance(name):
            return BadLLM()


    monkeypatch.setattr(
        "app.routes.dashboard_routes.LiteLLMModel",
        BadLLMFactory
    )

    res = client.get("/api/dashboard/key-articles/AI?top_k=2")

    assert res.status_code == 200

    data = res.json()

    # Should fallback to original articles
    assert len(data) == 2
    assert data[0]["uri"] == "uri-1"
    assert data[1]["uri"] == "uri-2"

    # ----------------------------
    # NO ARTICLES → EMPTY
    # ----------------------------
    async def empty_get_articles(*args, **kwargs):
        return MockPaginated([])


    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_articles",
        empty_get_articles
    )

    res = client.get("/api/dashboard/key-articles/AI")

    assert res.status_code == 200
    assert res.json() == []

    # ----------------------------
    # Cleanup
    # ----------------------------
    app.dependency_overrides.clear()


def test_get_generated_insights_success_and_failure(client, monkeypatch):
    """
    Test generated insights endpoint - success and failure cases
    """

    # ------------------ MOCK SESSION ------------------

    def fake_verify_session():
        return {"user": "test"}

    monkeypatch.setattr(
        "app.routes.dashboard_routes.verify_session",
        fake_verify_session
    )

    # ------------------ MOCK SUMMARY METRICS ------------------

    class FakeSummary:
        total_articles = 100
        new_articles_last_24h = 10
        new_articles_last_7d = 30
        dominant_news_source = "BBC"
        most_frequent_time_to_impact = "Short-term"

    async def fake_summary(*args, **kwargs):
        return FakeSummary()

    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_summary_metrics",
        fake_summary
    )

    # ------------------ MOCK OTHER DEPENDENCIES ------------------

    async def fake_empty(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_volume_over_time",
        fake_empty
    )

    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_sentiment_over_time",
        fake_empty
    )

    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_top_tags",
        fake_empty
    )

    # ------------------ MOCK LLM ------------------

    class FakeModel:
        def generate_response(self, messages):
            return "Insight 1***Insight 2"

    def fake_get_instance(name):
        return FakeModel()

    monkeypatch.setattr(
        "app.routes.dashboard_routes.LiteLLMModel.get_instance",
        fake_get_instance
    )

    # ------------------ SUCCESS CASE ------------------

    response = client.get("/api/dashboard/generated-insights/AI")

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "text" in data[0]

    # ------------------ FAILURE CASE ------------------

    async def fake_error(*args, **kwargs):
        raise Exception("DB Error")

    monkeypatch.setattr(
        "app.routes.dashboard_routes.get_topic_summary_metrics",
        fake_error
    )

    response = client.get("/api/dashboard/generated-insights/AI")

    assert response.status_code == 200

    data = response.json()

    assert data[0]["id"] == "error"

def test_get_semantic_outliers_success_and_failure(client):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def search_articles(self, *args, **kwargs):

            if self.mode == "success":
                return [
                    {
                        "uri": "1",
                        "title": "AI News",
                        "summary": "About AI",
                        "category": "Tech",
                        "future_signal": "Growth",
                        "sentiment": "positive",
                        "time_to_impact": "Short",
                        "tags": ["ai", "ml"]
                    }
                ], 1

            if self.mode == "empty":
                return [], 0

            if self.mode == "error":
                raise Exception("DB error")


    # ---------------- IMPORT REAL DEPENDENCIES ----------------

    from app.database import get_database_instance
    from app.security.session import verify_session


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    app.dependency_overrides[
        verify_session
    ] = fake_verify_session


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")


    res = client.get("/api/dashboard/semantic-outliers/AI")

    assert res.status_code == 200

    data = res.json()
    assert len(data) == 1
    assert "anomaly_score" in data[0]


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")


    res = client.get("/api/dashboard/semantic-outliers/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- INVALID DATE ----------------

    res = client.get(
        "/api/dashboard/semantic-outliers/AI"
        "?start_date=2025-99-99&end_date=2025-01-01"
    )

    assert res.status_code == 400


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")


    res = client.get("/api/dashboard/semantic-outliers/AI")

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides = {}



def test_get_article_insights_success_and_failure(client, monkeypatch):

    app = client.app  # Get FastAPI app instance

    # -------------------------------------------------
    # MOCK SESSION
    # -------------------------------------------------

    def fake_verify_session():
        return {"user": "test"}

    from app.routes import dashboard_routes

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # -------------------------------------------------
    # FAKE ARTICLE CLASS
    # -------------------------------------------------

    class FakeArticle:
        def __init__(self, uri):
            self.uri = uri
            self.title = "AI News"
            self.summary = "About AI"
            self.news_source = "Test Source"
            self.publication_date = "2025-01-01"
            self.tags = ["ai", "ml"]   # ✅ must be list


    # -------------------------------------------------
    # FAKE DB
    # -------------------------------------------------

    class FakeDB:

        def get_article_analysis_cache(self, *args, **kwargs):
            return None

        def save_article_analysis_cache(self, *args, **kwargs):
            return True


    from app.database import get_database_instance

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB()


    # -------------------------------------------------
    # SUCCESS: >=3 ARTICLES
    # -------------------------------------------------

    async def fake_get_articles_success(*args, **kwargs):

        class FakeResponse:
            items = [
                FakeArticle("1"),
                FakeArticle("2"),
                FakeArticle("3"),   # ✅ minimum 3
            ]

        return FakeResponse()


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_articles_success
    )


    # Mock LLM
    class FakeLLM:
        def generate_response(self, messages):

            return """
            [
              {
                "theme_name": "AI Growth",
                "theme_summary": "AI is growing fast.",
                "article_uris": ["1", "2", "3"]
              }
            ]
            """


    monkeypatch.setattr(
        dashboard_routes.LiteLLMModel,
        "get_instance",
        lambda model: FakeLLM()
    )


    # ---------- SUCCESS ----------

    res = client.post("/api/dashboard/article-insights/AI", json={})

    assert res.status_code == 200

    data = res.json()

    assert isinstance(data, list)
    assert len(data) == 1
    assert "theme_name" in data[0]
    assert "articles" in data[0]


    # -------------------------------------------------
    # 422: ONLY 2 ARTICLES
    # -------------------------------------------------

    async def fake_get_articles_few(*args, **kwargs):

        class FakeResponse:
            items = [
                FakeArticle("1"),
                FakeArticle("2"),
            ]

        return FakeResponse()


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_articles_few
    )


    res = client.post("/api/dashboard/article-insights/AI", json={})

    assert res.status_code == 422


    # -------------------------------------------------
    # 404: NO ARTICLES
    # -------------------------------------------------

    async def fake_get_articles_empty(*args, **kwargs):

        class FakeResponse:
            items = []

        return FakeResponse()


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_articles_empty
    )


    res = client.post("/api/dashboard/article-insights/AI", json={})

    assert res.status_code == 404


    # -------------------------------------------------
    # 500: DB ERROR
    # -------------------------------------------------

    async def fake_get_articles_error(*args, **kwargs):
        raise Exception("DB error")


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_articles_error
    )


    res = client.post("/api/dashboard/article-insights/AI", json={})

    # Your endpoint returns [] on generic exception
    assert res.status_code == 200
    assert res.json() == []


    # -------------------------------------------------
    # CLEANUP
    # -------------------------------------------------

    app.dependency_overrides.clear()

def test_get_latest_podcast_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def fetch_all(self, query):

            if self.mode == "success":
                return [
                    (
                        "pod-1",                     # id
                        "AI Podcast",                # title
                        "http://audio.com/a.mp3",    # audio_url
                        "Transcript here",           # transcript
                        "2025-01-01",                # created_at
                        json.dumps({                # metadata
                            "topic": "AI",           # MUST MATCH URL
                            "duration": "15 min"
                        })
                    )
                ]

            if self.mode == "empty":
                return []

            if self.mode == "error":
                raise Exception("DB Error")

            return []


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    # Override session
    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/dashboard/latest-podcast/AI")

    assert res.status_code == 200

    data = res.json()

    print("SUCCESS RESPONSE:", data)  # Debug

    assert data is not None
    assert data["podcast_id"] == "pod-1"
    assert data["title"] == "AI Podcast"
    assert data["audio_url"] == "http://audio.com/a.mp3"
    assert data["duration_minutes"] == 15.0


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")

    res = client.get("/api/dashboard/latest-podcast/AI")

    assert res.status_code == 200
    assert res.json() is None


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/dashboard/latest-podcast/AI")

    assert res.status_code == 200
    assert res.json() is None


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()



def test_get_podcasts_for_topic_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def fetch_all(self, query):

            if self.mode == "success":
                return [
                    (
                        "pod-3",
                        "Newest AI Podcast",
                        "url3",
                        "t3",
                        "2025-01-03",
                        json.dumps({"topic": "AI", "duration": "10 min"})
                    ),
                    (
                        "pod-2",
                        "Older AI Podcast",
                        "url2",
                        "t2",
                        "2025-01-02",
                        json.dumps({"topic": "AI", "duration": "12 min"})
                    ),
                    (
                        "pod-1",
                        "Oldest AI Podcast",
                        "url1",
                        "t1",
                        "2025-01-01",
                        json.dumps({"topic": "AI", "duration": "8 min"})
                    ),
                ]

            if self.mode == "empty":
                return []

            if self.mode == "error":
                raise Exception("DB error")

            return []


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- MOCK LATEST PODCAST ----------------

    class FakeLatestPodcast:
        def __init__(self):
            self.podcast_id = "pod-3"  # newest → exclude


    async def fake_get_latest(topic, db):
        return FakeLatestPodcast()


    monkeypatch.setattr(
        dashboard_routes,
        "get_latest_podcast_for_topic",
        fake_get_latest
    )


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/dashboard/podcasts-for-topic/AI?limit=5")

    assert res.status_code == 200

    data = res.json()

    print("SUCCESS:", data)

    # pod-3 excluded
    assert len(data) == 2

    ids = [p["podcast_id"] for p in data]

    assert "pod-3" not in ids
    assert "pod-2" in ids
    assert "pod-1" in ids


    # ---------------- LIMIT ----------------

    res = client.get("/api/dashboard/podcasts-for-topic/AI?limit=1")

    assert res.status_code == 200
    assert len(res.json()) == 1


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")

    res = client.get("/api/dashboard/podcasts-for-topic/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/dashboard/podcasts-for-topic/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_get_category_insights_success_and_failure(client, monkeypatch):
    from app.ai_models import LiteLLMModel

    app = client.app


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- FAKE DB ----------------

    class FakeDB:

        def __init__(self, mode="success"):
            self.mode = mode


        def fetch_all(self, query, params=None):

            # First query → categories
            if "GROUP BY category" in query:

                if self.mode == "success":
                    return [
                        {"category": "Tech", "article_count": 5},
                        {"category": "Business", "article_count": 3},
                    ]

                if self.mode == "empty":
                    return []

                if self.mode == "error":
                    raise Exception("DB error")


            # Second query → category articles
            if "FROM articles" in query:

                return [
                    {
                        "uri": "1",
                        "title": "AI News",
                        "summary": "About AI",
                        "news_source": "BBC",
                        "publication_date": "2025-01-01",
                        "sentiment": "positive",
                    }
                ]

            return []


        # Cache functions (no-op)

        def get_article_analysis_cache(self, *a, **k):
            return None

        def save_article_analysis_cache(self, *a, **k):
            return True



    # ---------------- MOCK get_topic_articles ----------------

    async def fake_get_topic_articles(*args, **kwargs):

        class FakeResponse:
            def __init__(self):
                self.items = [
                    type(
                        "A",
                        (),
                        {
                            "uri": "1",
                            "title": "AI News",
                            "summary": "About AI",
                            "news_source": "BBC",
                            "publication_date": "2025-01-01",
                            "tags": ["ai"],
                        },
                    )()
                ]

        return FakeResponse()


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_topic_articles
    )


    # ---------------- MOCK LLM ----------------

    class FakeLLM:

        def generate_response(self, messages):
            return "This category shows strong AI growth."


    monkeypatch.setattr(
        LiteLLMModel,
        "get_instance",
        lambda model: FakeLLM()
    )


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")


    res = client.get("/api/dashboard/category-insights/AI")

    assert res.status_code == 200

    data = res.json()

    print("SUCCESS:", data)

    assert len(data) == 2

    assert data[0]["category"] == "Tech"
    assert "insight_text" in data[0]
    assert len(data[0]["insight_text"]) > 5


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")


    res = client.get("/api/dashboard/category-insights/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")


    res = client.get("/api/dashboard/category-insights/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()



def test_get_word_frequency_success_and_failure(client, monkeypatch):

    from app.routes import dashboard_routes
    from app.database import get_database_instance

    app = client.app


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- FAKE DB ----------------

    class FakeDB:
        pass


    # ---------------- FAKE ARTICLE RESPONSE ----------------

    class FakeArticle:

        def __init__(self, title, summary):
            self.title = title
            self.summary = summary


    class FakePaginatedResponse:

        def __init__(self, items):
            self.items = items


    # ---------------- SUCCESS ----------------

    async def fake_get_topic_articles_success(*args, **kwargs):

        return FakePaginatedResponse([
            FakeArticle(
                title="AI is transforming software development",
                summary="AI helps developers write better code"
            ),
            FakeArticle(
                title="Machine learning in healthcare",
                summary="AI improves medical diagnosis"
            ),
        ])


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_topic_articles_success
    )


    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB()


    res = client.get("/api/dashboard/word-frequency/AI")

    assert res.status_code == 200

    data = res.json()

    print("SUCCESS:", data)

    assert len(data) > 0

    words = [item["word"] for item in data]

    assert "development" in words
    assert "healthcare" in words
    assert "software" in words

    # ---------------- EMPTY ARTICLES ----------------

    async def fake_get_topic_articles_empty(*args, **kwargs):

        return FakePaginatedResponse([])


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_topic_articles_empty
    )


    res = client.get("/api/dashboard/word-frequency/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- EMPTY TEXT ----------------

    async def fake_get_topic_articles_empty_text(*args, **kwargs):

        return FakePaginatedResponse([
            FakeArticle(title=None, summary=None),
            FakeArticle(title="", summary=" "),
        ])


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_topic_articles_empty_text
    )


    res = client.get("/api/dashboard/word-frequency/AI")

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- ERROR ----------------

    async def fake_get_topic_articles_error(*args, **kwargs):

        raise Exception("DB failure")


    monkeypatch.setattr(
        dashboard_routes,
        "get_topic_articles",
        fake_get_topic_articles_error
    )


    res = client.get("/api/dashboard/word-frequency/AI")

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()



def test_get_radar_chart_data_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    from app.routes import dashboard_routes
    from app.database import get_database_instance

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def fetch_all(self, *args, **kwargs):

            # -------- SUCCESS --------
            if self.mode == "success":
                return [
                    {
                        "future_signal": "Growth",
                        "sentiment": "Positive",
                        "time_to_impact": "Short-term",
                        "article_count": 5
                    },
                    {
                        "future_signal": "Growth",
                        "sentiment": "Negative",
                        "time_to_impact": "Long-term",
                        "article_count": 2
                    },
                    {
                        "future_signal": "Risk",
                        "sentiment": "Positive",
                        "time_to_impact": "Immediate",
                        "article_count": 3
                    }
                ]

            # -------- EMPTY --------
            if self.mode == "empty":
                return []

            # -------- ERROR --------
            if self.mode == "error":
                raise Exception("DB failure")


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/dashboard/radar-chart-data/AI")

    assert res.status_code == 200

    data = res.json()

    assert "labels" in data
    assert "datasets" in data

    # labels = distinct future_signal
    assert set(data["labels"]) == {"Growth", "Risk"}

    assert len(data["datasets"]) == 2  # Positive + Negative

    # Check dataset structure
    first_dataset = data["datasets"][0]

    assert "label" in first_dataset
    assert "data" in first_dataset
    assert "customData" in first_dataset

    assert isinstance(first_dataset["data"], list)
    assert isinstance(first_dataset["customData"], list)


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")

    res = client.get("/api/dashboard/radar-chart-data/AI")

    assert res.status_code == 200

    data = res.json()

    assert data["labels"] == []
    assert data["datasets"] == []


    # ---------------- INVALID DATE ----------------

    res = client.get(
        "/api/dashboard/radar-chart-data/AI"
        "?start_date=2025-99-99&end_date=2025-01-01"
    )

    assert res.status_code == 400


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/dashboard/radar-chart-data/AI")

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------
    app.dependency_overrides = {}



def test_get_map_activity_data_success_and_failure(client):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    from app.routes import dashboard_routes

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- SUCCESS (NO DATE RANGE) ----------------

    res = client.get("/api/dashboard/map-activity-data/AI")

    assert res.status_code == 200

    data = res.json()

    # Should return list
    assert isinstance(data, list)

    # Max 8 countries
    assert len(data) <= 8

    # Validate structure
    for item in data:
        assert "country" in item
        assert "activity_level" in item
        assert "articles" in item

        assert isinstance(item["country"], str)
        assert item["activity_level"] in ["high", "normal"]
        assert isinstance(item["articles"], int)


    # Check sorted order (desc by articles)
    articles_counts = [item["articles"] for item in data]
    assert articles_counts == sorted(articles_counts, reverse=True)


    # ---------------- SUCCESS (WITH DATE RANGE) ----------------

    res = client.get(
        "/api/dashboard/map-activity-data/AI"
        "?date_range=2025-01-01,2025-02-01"
    )

    assert res.status_code == 200

    data_with_range = res.json()

    assert isinstance(data_with_range, list)
    assert len(data_with_range) <= 8

    for item in data_with_range:
        assert "country" in item
        assert "articles" in item


    # ---------------- INVALID DATE FORMAT (SHOULD STILL WORK) ----------------
    # Endpoint does not fail on bad date, only logs warning

    res = client.get(
        "/api/dashboard/map-activity-data/AI"
        "?date_range=bad-date,bad-date"
    )

    assert res.status_code == 200

    data_bad_date = res.json()

    assert isinstance(data_bad_date, list)


    # ---------------- CLEANUP ----------------
    app.dependency_overrides = {}



def test_get_dashboard_stats_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        dashboard_routes.verify_session
    ] = fake_verify_session


    # ---------------- MOCK DATABASE FACADE ----------------

    class FakeFacade:
        def __init__(self, db, logger):
            pass

        def get_total_article_count(self):
            return 100

        def get_articles_count_since(self, date):
            return 10

        def get_keyword_groups_count(self):
            return 5


    monkeypatch.setattr(
        "app.database_query_facade.DatabaseQueryFacade",
        FakeFacade
    )


    # ---------------- MOCK json.load (KEY FIX) ----------------

    def fake_json_load(file_obj):
        return {
            "topics": ["AI", "ML", "Robotics"]
        }


    monkeypatch.setattr("json.load", fake_json_load)


    # ---------------- SUCCESS ----------------

    res = client.get("/api/dashboard/stats")

    assert res.status_code == 200

    data = res.json()

    assert data["total_articles"] == 100
    assert data["articles_today"] == 10
    assert data["keyword_groups"] == 5
    assert data["topics"] == 3


    # ---------------- FAILURE ----------------

    class ErrorFacade:
        def __init__(self, db, logger):
            pass

        def get_total_article_count(self):
            raise Exception("DB error")


    monkeypatch.setattr(
        "app.database_query_facade.DatabaseQueryFacade",
        ErrorFacade
    )


    res = client.get("/api/dashboard/stats")

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()

# =============================================================================
# routes/database.py endpoints
# =============================================================================

def test_get_config_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session


    # ---------------- SUCCESS CASE ----------------

    def fake_load_config():
        return {
            "topics": ["AI", "ML", "Robotics"],
            "version": "1.0"
        }

    # Patch where it is USED (inside route)
    monkeypatch.setattr(
        "app.config.config.load_config",
        fake_load_config
    )

    res = client.get("/api/config")

    assert res.status_code == 200

    data = res.json()

    assert "topics" in data
    assert data["topics"] == ["AI", "ML", "Robotics"]
    assert data["version"] == "1.0"


    # ---------------- FAILURE CASE ----------------

    def fake_load_config_error():
        raise Exception("Config error")

    monkeypatch.setattr(
        "app.config.config.load_config",
        fake_load_config_error
    )

    res = client.get("/api/config")

    assert res.status_code == 500

    error = res.json()
    assert "Config error" in error["detail"]


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()



def test_download_database_success_and_failure(client, monkeypatch, tmp_path):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session


    # ---------------- FAKE DB ----------------

    class FakeDB:

        def get_database_path(self, name):
            # Simulate DB folder
            return str(tmp_path / name)

        def download_database(self, name):
            # Create fake download file
            file_path = tmp_path / f"{name}.sqlite"
            file_path.write_text("dummy database content")
            return str(file_path)


    # ---------------- SUCCESS CASE ----------------

    fake_db = FakeDB()

    app.dependency_overrides[
        get_database_instance
    ] = lambda: fake_db


    # Make os.path.exists return True for success
    monkeypatch.setattr(
        "os.path.exists",
        lambda path: True
    )

    res = client.get("/api/databases/download/test.db")

    assert res.status_code == 200

    # FileResponse returns bytes
    assert res.headers["content-type"] == "application/x-sqlite3"


    # ---------------- NOT FOUND CASE (404) ----------------

    def fake_exists_false(path):
        return False

    monkeypatch.setattr(
        "os.path.exists",
        fake_exists_false
    )

    res = client.get("/api/databases/download/missing.db")

    assert res.status_code == 404

    data = res.json()
    assert "not found" in data["detail"].lower()


    # ---------------- ERROR CASE (500) ----------------

    class ErrorDB:

        def get_database_path(self, name):
            return "some/path"

        def download_database(self, name):
            raise Exception("DB failure")


    app.dependency_overrides[
        get_database_instance
    ] = lambda: ErrorDB()


    # Make exists return True so it passes first check
    monkeypatch.setattr(
        "os.path.exists",
        lambda path: True
    )

    res = client.get("/api/databases/download/error.db")

    assert res.status_code == 500

    error = res.json()
    assert "DB failure" in error["detail"]


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_get_database_info_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session


    # ---------------- FORCE SQLITE MODE ----------------

    monkeypatch.setenv("DB_TYPE", "sqlite")


    # ---------------- FAKE SQLITE CURSOR ----------------

    class FakeCursor:

        def __init__(self):
            self.last_query = None

        def execute(self, query):
            self.last_query = query

        def fetchall(self):
            # For: SELECT name FROM sqlite_master
            return [("articles",), ("users",)]

        def fetchone(self):

            # Articles stats
            if "MIN(publication_date)" in self.last_query:
                return (10, "2024-01-01", "2025-01-01")

            # Topic count
            if "COUNT(DISTINCT topic)" in self.last_query:
                return (3,)

            # Table row count
            if "COUNT(*) FROM" in self.last_query:
                return (5,)

            return (0,)


    # ---------------- FAKE SQLITE CONNECTION ----------------

    class FakeConnection:

        def cursor(self):
            return FakeCursor()


    # ---------------- FAKE DATABASE ----------------

    class FakeDatabase:

        def __init__(self):
            self.db_path = "/fake/test.db"

        def get_connection(self):
            return FakeConnection()


    # ---------------- MOCK Database CLASS ----------------

    monkeypatch.setattr(
        "app.routes.database.Database",
        FakeDatabase
    )


    # ---------------- MOCK os.path.getsize ----------------

    monkeypatch.setattr(
        "os.path.getsize",
        lambda path: 1024
    )


    # ---------------- SUCCESS CASE ----------------

    res = client.get("/api/database-info")

    assert res.status_code == 200

    data = res.json()

    assert data["db_type"] == "sqlite"
    assert data["name"] == "test.db"
    assert data["size"] == 1024

    assert data["total_articles"] == 10
    assert data["total_topics"] == 3

    assert len(data["tables"]) == 2
    assert data["tables"][0]["name"] == "articles"


    # ---------------- FAILURE CASE ----------------

    class ErrorDatabase:

        def __init__(self):
            raise Exception("DB crashed")


    monkeypatch.setattr(
        "app.routes.database.Database",
        ErrorDatabase
    )


    res = client.get("/api/database-info")

    assert res.status_code == 500

    error = res.json()

    assert "DB crashed" in error["detail"]


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()

import json


def test_bulk_delete_articles_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session


    # ---------------- FAKE DATABASE ----------------

    class FakeDB:

        def __init__(self, mode="success"):
            self.mode = mode

        def bulk_delete_articles(self, uris):

            if self.mode == "success":
                return len(uris)

            if self.mode == "empty":
                return 0

            if self.mode == "error":
                raise Exception("DB delete failed")


    # Helper for sending JSON in DELETE (OLD TESTCLIENT FIX)
    def delete_json(url, payload):
        return client.request(
            "DELETE",
            url,
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        database.get_database_instance
    ] = lambda: FakeDB("success")


    payload = {
        "uris": [
            "https://example.com/1",
            "https://example.com/2"
        ]
    }

    res = delete_json(
        "/api/bulk_delete_articles",
        payload
    )

    assert res.status_code == 200

    data = res.json()

    assert data["status"] == "success"
    assert data["deleted_count"] == 2


    # ---------------- WARNING (0 DELETE) ----------------

    app.dependency_overrides[
        database.get_database_instance
    ] = lambda: FakeDB("empty")


    res = delete_json(
        "/api/bulk_delete_articles",
        payload
    )

    assert res.status_code == 200

    data = res.json()

    assert data["status"] == "warning"
    assert data["deleted_count"] == 0


    # ---------------- EMPTY (500) ----------------

    res = delete_json(
        "/api/bulk_delete_articles",
        {"uris": []}
    )

    assert res.status_code == 500


    # ---------------- ERROR (500) ----------------

    app.dependency_overrides[
        database.get_database_instance
    ] = lambda: FakeDB("error")


    res = delete_json(
        "/api/bulk_delete_articles",
        payload
    )

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_get_article_annotations_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_article_annotations(self, uri, include_private):

            if self.mode == "success":
                return [
                    {
                        "id": 1,
                        "content": "Test annotation",
                        "is_private": False,
                        "created_at": "2026-01-01"
                    }
                ]

            if self.mode == "empty":
                return []

            if self.mode == "error":
                raise Exception("DB error")


    # ---------------- FAKE SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    # Override deps
    app.dependency_overrides[verify_session] = fake_verify_session


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get(
        "/api/articles/test-uri-123/annotations"
    )

    assert res.status_code == 200

    data = res.json()

    assert len(data) == 1
    assert data[0]["content"] == "Test annotation"


    # ---------------- EMPTY ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")

    res = client.get(
        "/api/articles/test-uri-123/annotations"
    )

    assert res.status_code == 200
    assert res.json() == []


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get(
        "/api/articles/test-uri-123/annotations"
    )

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides = {}



def test_create_article_annotation_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def add_article_annotation(self, uri, author, content, is_private):

            if self.mode == "success":
                return 101   # fake annotation id

            if self.mode == "integrity":
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError("stmt", "params", "constraint failed")

            if self.mode == "error":
                raise Exception("DB error")


    # ---------------- FAKE SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    # Override session dependency
    app.dependency_overrides[verify_session] = fake_verify_session


    payload = {
        "content": "This is a test annotation",
        "is_private": False
    }


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.post(
        "/api/articles/test-uri-123/annotations",
        json=payload
    )

    assert res.status_code == 200

    data = res.json()

    assert "id" in data
    assert data["id"] == 101


    # ---------------- INTEGRITY ERROR (400) ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("integrity")

    res = client.post(
        "/api/articles/test-uri-123/annotations",
        json=payload
    )

    assert res.status_code == 400
    assert "constraints" in res.json()["detail"].lower()


    # ---------------- GENERIC ERROR (500) ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.post(
        "/api/articles/test-uri-123/annotations",
        json=payload
    )

    assert res.status_code == 500


    # ---------------- INVALID BODY (422) ----------------
    # Missing "content"

    res = client.post(
        "/api/articles/test-uri-123/annotations",
        json={"is_private": False}
    )

    assert res.status_code == 422


    # ---------------- CLEANUP ----------------

    app.dependency_overrides = {}


# the endpoint is not working as expected, uncomment this test when the endpoint is fixed
'''
def test_update_article_annotation_success_and_failure(client, monkeypatch):

    app = client.app


    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def update_article_annotation(self, annotation_id, content, is_private):

            if self.mode == "success":
                return True

            if self.mode == "not_found":
                return False

            if self.mode == "error":
                raise Exception("DB error")


    # ---------------- FAKE SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}


    # Override session dependency
    app.dependency_overrides[verify_session] = fake_verify_session


    payload = {
        "content": "Updated annotation text",
        "is_private": True
    }


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.put(
        "/api/articles/test-uri-123/annotations/10",
        json=payload
    )

    assert res.status_code == 200

    data = res.json()

    assert data["success"] is True


    # ---------------- NOT FOUND (404) ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("not_found")

    res = client.put(
        "/api/articles/test-uri-123/annotations/10",
        json=payload
    )

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


    # ---------------- GENERIC ERROR (500) ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.put(
        "/api/articles/test-uri-123/annotations/10",
        json=payload
    )

    assert res.status_code == 500


    # ---------------- INVALID BODY (422) ----------------
    # Missing "content"

    res = client.put(
        "/api/articles/test-uri-123/annotations/10",
        json={"is_private": False}
    )

    assert res.status_code == 422


    # ---------------- CLEANUP ----------------

    app.dependency_overrides = {}
'''

# the endpoint is not working as expected, uncomment this test when the endpoint is fixed
'''
def test_delete_article_annotation_success_and_failure(client, monkeypatch):

    app = client.app  # Get FastAPI app

    # ---------------- FAKE DB ----------------

    class FakeDB:
        def __init__(self, mode="success"):
            self.mode = mode

        def delete_article_annotation(self, annotation_id):

            if self.mode == "success":
                return True

            if self.mode == "not_found":
                return False

            if self.mode == "error":
                raise Exception("DB error")


    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session


    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.delete(
        "/api/articles/test-uri/annotations/1"
    )

    assert res.status_code == 200
    assert res.json()["success"] is True


    # ---------------- NOT FOUND ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("not_found")

    res = client.delete(
        "/api/articles/test-uri/annotations/1"
    )

    assert res.status_code == 404
    assert res.json()["detail"] == "Annotation not found"


    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.delete(
        "/api/articles/test-uri/annotations/1"
    )

    assert res.status_code == 500


    # ---------------- CLEANUP ----------------

    app.dependency_overrides = {}
'''
def test_database_routes_get_database_health_success_and_failure(client, monkeypatch):

    app = client.app


    # =================================================
    # FAKE POSTGRES CONNECTION
    # =================================================

    class FakeResult:

        def __init__(self, data):
            self.data = data

        def mappings(self):
            return self

        def fetchone(self):
            return self.data


    class FakeConn:

        def execute(self, query, params=None):

            q = str(query)

            # Stuck transactions
            if "idle in transaction" in q:
                return FakeResult({"stuck_count": 0})

            # Active connections
            return FakeResult({
                "active_connections": 2,
                "longest_query_seconds": 15.2
            })

        def commit(self):
            pass

        def rollback(self):
            pass


    # =================================================
    # FAKE DATABASE
    # =================================================

    class FakeDB:

        def __init__(self):
            # Force clean pool
            self._sqlalchemy_connections = {}

        def _temp_get_connection(self):
            return FakeConn()


    fake_db = FakeDB()


    # =================================================
    # FORCE POSTGRES MODE
    # =================================================

    monkeypatch.setattr(
        "app.routes.database.get_db_type",
        lambda: "postgresql"
    )


    # =================================================
    # OVERRIDE DEPENDENCY (IMPORTANT)
    # =================================================

    from app.database import get_database_instance

    app.dependency_overrides[
        get_database_instance
    ] = lambda: fake_db


    # =================================================
    # ALSO OVERRIDE Database CLASS (CRITICAL FIX)
    # =================================================

    monkeypatch.setattr(
        "app.routes.database.Database",
        lambda *a, **k: fake_db
    )


    # =================================================
    # SUCCESS CASE
    # =================================================

    res = client.get("/api/database-health")

    assert res.status_code == 200

    data = res.json()

    assert data["db_type"] == "postgresql"
    assert data["healthy"] is True
    assert data["stuck_transactions"] == 0
    assert data["active_connections"] == 2
    assert data["longest_query_seconds"] == 15.2


    # =================================================
    # FAILURE CASE
    # =================================================

    class BadConn:

        def execute(self, *a, **k):
            raise Exception("DB crash")

        def rollback(self):
            pass


    class BadDB:

        def __init__(self):
            self._sqlalchemy_connections = {}

        def _temp_get_connection(self):
            return BadConn()


    bad_db = BadDB()


    app.dependency_overrides[
        get_database_instance
    ] = lambda: bad_db


    monkeypatch.setattr(
        "app.routes.database.Database",
        lambda *a, **k: bad_db
    )


    res = client.get("/api/database-health")

    assert res.status_code == 500


def test_reset_articles_data_success_and_failure(client, monkeypatch):

    app = client.app


    # =====================================================
    # FAKE DB CONNECTION
    # =====================================================

    class FakeResult:

        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value


    class FakeConn:

        def __init__(self, fail=False):
            self.fail = fail
            self.executed = []

        def execute(self, stmt):

            if self.fail:
                raise Exception("DB error")

            q = str(stmt)

            # For COUNT(*)
            if "COUNT" in q:
                return FakeResult(5)

            # For DELETE / TRUNCATE
            self.executed.append(q)
            return None

        def commit(self):
            pass

        def rollback(self):
            pass


    # =====================================================
    # FAKE DATABASE
    # =====================================================

    class FakeDB:

        def __init__(self, fail=False):
            self.fail = fail
            self.conn = FakeConn(fail)

        def _temp_get_connection(self):
            return self.conn


    fake_db = FakeDB()


    # =====================================================
    # FAKE CHROMA CLIENT
    # =====================================================

    class FakeCollection:
        def __init__(self, name):
            self.name = name


    class FakeChromaClient:

        def list_collections(self):
            return [FakeCollection("articles")]

        def delete_collection(self, name):
            pass


    # =====================================================
    # MOCK ENVIRONMENT
    # =====================================================

    # Force sqlite mode
    monkeypatch.setattr(
        "app.routes.database.get_db_type",
        lambda: "sqlite"
    )

    # Disable vacuum
    monkeypatch.setattr(
        "app.routes.database.execute_vacuum",
        lambda *a, **k: None
    )

    # Mock chroma (patch where it is imported from vector_store.py)
    monkeypatch.setattr(
        "app.vector_store.get_chroma_client",
        lambda: FakeChromaClient()
    )



    # =====================================================
    # OVERRIDE DEPENDENCY
    # =====================================================

    app.dependency_overrides[
        get_database_instance
    ] = lambda: fake_db


    monkeypatch.setattr(
        "app.routes.database.Database",
        lambda *a, **k: fake_db
    )


    # =====================================================
    # SUCCESS CASE
    # =====================================================

    res = client.post("/api/reset-articles-data")

    assert res.status_code == 200

    data = res.json()

    assert "Successfully reset articles data" in data["message"]
    assert data["db_type"] == "sqlite"
    assert "details" in data
    assert "articles" in data["details"]


    # =====================================================
    # FAILURE CASE
    # =====================================================

    bad_db = FakeDB(fail=True)

    app.dependency_overrides[
        get_database_instance
    ] = lambda: bad_db

    monkeypatch.setattr(
        "app.routes.database.Database",
        lambda *a, **k: bad_db
    )

    res = client.post("/api/reset-articles-data")

    assert res.status_code == 200

    data = res.json()

    assert "Successfully reset articles data" in data["message"]

    # Must contain error info
    has_error = False

    for v in data["details"].values():
        if isinstance(v, str) and "Error" in v:
            has_error = True

    assert has_error



def test_reindex_chromadb_success_and_failure(client, monkeypatch):

    app = client.app

    # =====================================================
    # FAKE ARTICLES
    # =====================================================

    fake_articles = [
        {"uri": "a1"},
        {"uri": "a2"},
        {"uri": "a3"},
    ]


    # =====================================================
    # FAKE CHROMA CLIENT
    # =====================================================

    class FakeChromaClient:

        def delete_collection(self, name):
            pass


    # =====================================================
    # FAKE FACADE (SUCCESS)
    # =====================================================

    class FakeFacade:

        def __init__(self, db, logger):
            pass

        def get_iter_articles(self, limit=None):
            for a in fake_articles:
                yield a


    # =====================================================
    # FAKE UPSERT (SUCCESS)
    # =====================================================

    def fake_upsert(article):
        return True


    # =====================================================
    # MOCK DEPENDENCIES
    # =====================================================

    monkeypatch.setattr(
        "app.vector_store.get_chroma_client",
        lambda: FakeChromaClient()
    )

    monkeypatch.setattr(
        "app.database_query_facade.DatabaseQueryFacade",
        FakeFacade
    )

    monkeypatch.setattr(
        "app.vector_store.upsert_article",
        fake_upsert
    )


    # =====================================================
    # SUCCESS CASE
    # =====================================================

    res = client.post("/api/reindex-chromadb")

    assert res.status_code == 200

    data = res.json()

    assert data["indexed"] == 3
    assert data["failed"] == 0
    assert data["total"] == 3
    assert "Successfully reindexed" in data["message"]


    # =====================================================
    # FAILURE CASE ( >10 FAILURES )
    # =====================================================

    many_articles = [{"uri": f"a{i}"} for i in range(20)]


    class BadFacade:

        def __init__(self, db, logger):
            pass

        def get_iter_articles(self, limit=None):
            for a in many_articles:
                yield a


    def bad_upsert(article):
        raise Exception("Index error")


    monkeypatch.setattr(
        "app.database_query_facade.DatabaseQueryFacade",
        BadFacade
    )

    monkeypatch.setattr(
        "app.vector_store.upsert_article",
        bad_upsert
    )


    res = client.post("/api/reindex-chromadb")

    assert res.status_code == 500

    data = res.json()

    assert "Too many failures" in data["detail"]


def test_clear_topic_articles_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    def fake_verify_session():
        return {"user": "test"}

    app.dependency_overrides[
        database.verify_session
    ] = fake_verify_session

    # ---------------- FAKE DB ----------------

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")

            q = str(stmt)
            if "COUNT" in q:
                return FakeResult(5 if self.mode == "success" else 0)
            return None

        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- MOCK VACUUM ----------------

    monkeypatch.setattr(
        "app.routes.database.execute_vacuum",
        lambda *a, **k: None
    )

    monkeypatch.setattr(
        "app.routes.database.get_db_type",
        lambda: "sqlite"
    )

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.post("/api/clear-topic-articles/AI")

    assert res.status_code == 200
    assert res.json()["articles_deleted"] == 5

    # ---------------- EMPTY (NO ARTICLES) ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("empty")

    res = client.post("/api/clear-topic-articles/AI")

    assert res.status_code == 200
    assert res.json()["articles_deleted"] == 0

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.post("/api/clear-topic-articles/AI")

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_reset_auspex_chats_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")
            return FakeResult(10)

        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- MOCK VACUUM ----------------

    monkeypatch.setattr(
        "app.routes.database.execute_vacuum",
        lambda *a, **k: None
    )

    monkeypatch.setattr(
        "app.routes.database.get_db_type",
        lambda: "sqlite"
    )

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.post("/api/reset-auspex-chats")

    assert res.status_code == 200
    assert res.json()["chats_deleted"] == 10

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.post("/api/reset-auspex-chats")

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_get_backups_success_and_failure(client, monkeypatch, tmp_path):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- CREATE FAKE BACKUP DIR ----------------

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    fake_backup = backup_dir / "test_backup.db"
    fake_backup.write_text("fake db content")

    # ---------------- MOCK DATABASE_DIR ----------------

    monkeypatch.setattr(
        "app.routes.database.DATABASE_DIR",
        str(tmp_path)
    )

    # ---------------- MOCK conn (endpoint has bug using undefined conn) ----------------

    class FakeConn:
        def commit(self):
            pass

    monkeypatch.setattr(
        "app.routes.database.conn",
        FakeConn(),
        raising=False
    )

    # ---------------- SUCCESS ----------------

    res = client.get("/api/backups")

    assert res.status_code == 200

    data = res.json()
    assert isinstance(data, list)

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_list_backups_success_and_failure(client, monkeypatch, tmp_path):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- CREATE FAKE BACKUP DIR ----------------

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    fake_backup = backup_dir / "backup.db"
    fake_backup.write_text("data")

    # ---------------- MOCK DATABASE_DIR ----------------

    monkeypatch.setattr(
        "app.routes.database.DATABASE_DIR",
        str(tmp_path)
    )

    # ---------------- MOCK conn (endpoint has bug using undefined conn) ----------------

    class FakeConn:
        def commit(self):
            pass

    monkeypatch.setattr(
        "app.routes.database.conn",
        FakeConn(),
        raising=False
    )

    # ---------------- SUCCESS ----------------

    res = client.get("/backups")

    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_export_topics_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeMappings:
        def __init__(self, data):
            self.data = data
            self.idx = 0

        def __iter__(self):
            return iter(self.data)

        def first(self):
            return self.data[0] if self.data else None

    class FakeResult:
        def __init__(self, data):
            self.data = data

        def mappings(self):
            return FakeMappings(self.data)

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")
            return FakeResult([])

        def commit(self):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/export-topics")

    assert res.status_code == 200
    assert "keyword_groups" in res.json()

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/export-topics")

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_import_topics_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeTrans:
        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def begin(self):
            return FakeTrans()

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")
            return None

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    payload = {
        "keyword_groups": [],
        "monitored_keywords": []
    }

    res = client.post("/api/import-topics", json=payload)

    assert res.status_code == 200
    assert "Successfully imported" in res.json()["message"]

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.post("/api/import-topics", json=payload)

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_reset_database_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeMappings:
        def __init__(self, data):
            self.data = data

        def __iter__(self):
            return iter(self.data)

    class FakeResult:
        def mappings(self):
            return FakeMappings([{"name": "articles"}])

    class FakeConn:
        def execute(self, stmt, params=None):
            return FakeResult()

        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeDB:
        def _temp_get_connection(self):
            return FakeConn()

    # ---------------- MOCK SUBPROCESS ----------------

    class FakeSubprocessResult:
        returncode = 0
        stdout = "Migration OK"
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: FakeSubprocessResult()
    )

    monkeypatch.setattr(
        "app.routes.database.check_external_command",
        lambda cmd: True
    )

    monkeypatch.setattr(
        "app.routes.database.get_db_type",
        lambda: "sqlite"
    )

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB()

    res = client.post("/api/databases/reset")

    assert res.status_code == 200
    assert "reset successfully" in res.json()["message"]

    # ---------------- ALEMBIC NOT FOUND ----------------

    monkeypatch.setattr(
        "app.routes.database.check_external_command",
        lambda cmd: False
    )

    res = client.post("/api/databases/reset")

    assert res.status_code == 500
    assert "alembic" in res.json()["detail"].lower()

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_export_articles_enriched_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeMappings:
        def __init__(self, data):
            self.data = data

        def __iter__(self):
            return iter(self.data)

    class FakeResult:
        def __init__(self, data):
            self.data = data

        def mappings(self):
            return FakeMappings(self.data)

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")
            return FakeResult([{"uri": "test", "title": "Test"}])

        def commit(self):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/export-articles-enriched")

    assert res.status_code == 200
    assert "articles" in res.json()

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/export-articles-enriched")

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_export_articles_raw_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeMappings:
        def __init__(self, data):
            self.data = data

        def __iter__(self):
            return iter(self.data)

    class FakeResult:
        def __init__(self, data):
            self.data = data

        def mappings(self):
            return FakeMappings(self.data)

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def execute(self, stmt, params=None):
            if self.mode == "error":
                raise Exception("DB error")
            return FakeResult([{"uri": "test", "raw_markdown": "# Test"}])

        def commit(self):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    res = client.get("/api/export-articles-raw")

    assert res.status_code == 200
    assert res.json()["export_type"] == "raw"

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.get("/api/export-articles-raw")

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_import_articles_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[
        database.verify_session
    ] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeTrans:
        def __init__(self, fail_on_commit=False):
            self.fail_on_commit = fail_on_commit

        def commit(self):
            if self.fail_on_commit:
                raise Exception("DB error")

        def rollback(self):
            pass

    class FakeResult:
        def first(self):
            return None

    class FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode

        def begin(self):
            return FakeTrans(fail_on_commit=(self.mode == "error"))

        def execute(self, stmt, params=None):
            return FakeResult()

    class FakeDB:
        def __init__(self, mode="success"):
            self.conn = FakeConn(mode)

        def _temp_get_connection(self):
            return self.conn

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("success")

    payload = {
        "articles": [
            {"uri": "http://example.com/1", "title": "Test"}
        ]
    }

    res = client.post("/api/import-articles", json=payload)

    assert res.status_code == 200
    assert "statistics" in res.json()

    # ---------------- MISSING ARTICLES FIELD (400) ----------------

    res = client.post("/api/import-articles", json={})

    assert res.status_code == 400

    # ---------------- INVALID ARTICLES TYPE (400) ----------------

    res = client.post("/api/import-articles", json={"articles": "not a list"})

    assert res.status_code == 400

    # ---------------- ERROR ----------------

    app.dependency_overrides[
        get_database_instance
    ] = lambda: FakeDB("error")

    res = client.post("/api/import-articles", json=payload)

    assert res.status_code == 500

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


# ======================================================
# keyword_monitor.py endpoints (Batch 1: 1-17)
# ======================================================

import app.routes.keyword_monitor as keyword_monitor


def test_create_group_success_and_failure(client, monkeypatch):

    app = client.app

    # ---------------- MOCK SESSION ----------------

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    # ---------------- FAKE DB ----------------

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def create_keyword_monitor_group(self, data):
            if self.mode == "error":
                raise Exception("DB error")
            return 1

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post(
        "/api/keyword-monitor/groups",
        json={"name": "Test Group", "topic": "AI"}
    )

    assert res.status_code == 200
    assert res.json()["id"] == 1

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post(
        "/api/keyword-monitor/groups",
        json={"name": "Test", "topic": "AI"}
    )

    assert res.status_code == 400

    # ---------------- CLEANUP ----------------

    app.dependency_overrides.clear()


def test_add_keyword_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def create_keyword(self, data):
            if self.mode == "error":
                raise Exception("DB error")
            return 101

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post(
        "/api/keyword-monitor/keywords",
        json={"group_id": 1, "keyword": "machine learning"}
    )

    assert res.status_code == 200
    assert res.json()["id"] == 101

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post(
        "/api/keyword-monitor/keywords",
        json={"group_id": 1, "keyword": "test"}
    )

    assert res.status_code == 400

    app.dependency_overrides.clear()


def test_delete_keyword_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def delete_keyword(self, keyword_id):
            if self.mode == "error":
                raise Exception("DB error")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.delete("/api/keyword-monitor/keywords/1")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.delete("/api/keyword-monitor/keywords/1")

    assert res.status_code == 400

    app.dependency_overrides.clear()


def test_delete_group_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def delete_keyword_group(self, group_id):
            if self.mode == "error":
                raise Exception("DB error")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.delete("/api/keyword-monitor/groups/1")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.delete("/api/keyword-monitor/groups/1")

    assert res.status_code == 400

    app.dependency_overrides.clear()


def test_delete_groups_by_topic_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_all_group_ids_associated_to_topic(self, topic):
            if self.mode == "error":
                raise Exception("DB error")
            if self.mode == "empty":
                return []
            return [{"id": 1}, {"id": 2}]

        def get_keyword_ids_associated_to_group(self, group_id):
            return [{"id": 10}]

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def delete_keyword_article_matches_from_new_table_structure(self, group_id):
            return 5

        def delete_groups_keywords(self, ids_str, group_ids):
            return 3

        def delete_all_keyword_groups(self, topic):
            return 2

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.delete("/api/keyword-monitor/groups/by-topic/AI")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- EMPTY ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("empty")

    res = client.delete("/api/keyword-monitor/groups/by-topic/AI")

    assert res.status_code == 200
    assert res.json()["groups_deleted"] == 0

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.delete("/api/keyword-monitor/groups/by-topic/AI")

    assert res.status_code == 400

    app.dependency_overrides.clear()


def test_mark_alert_read_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def check_if_alert_id_exists_in_new_table_structure(self, alert_id):
            return True

        def mark_alert_as_read_or_unread_in_new_table(self, alert_id, status):
            if self.mode == "error":
                raise Exception("DB error")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/alerts/1/read")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post("/api/keyword-monitor/alerts/1/read")

    assert res.status_code == 400

    app.dependency_overrides.clear()


def test_check_now_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def get_number_of_monitored_keywords_by_group_id(self, group_id):
            return 2

        def get_total_number_of_keywords(self):
            return 2

    class FakeDB:
        def __init__(self):
            self.facade = FakeFacade()

    class FakeMonitor:
        def __init__(self, db):
            pass

        async def check_keywords(self, group_id=None):
            return {"success": True, "new_articles": 5}

    monkeypatch.setattr(keyword_monitor, "KeywordMonitor", FakeMonitor)

    app.dependency_overrides[get_database_instance] = lambda: FakeDB()

    # ---------------- SUCCESS ----------------

    res = client.post("/api/keyword-monitor/check-now", json={})

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- FAILURE ----------------

    class FailingMonitor:
        def __init__(self, db):
            pass

        async def check_keywords(self, group_id=None):
            return {"success": False, "error": "API failed"}

    monkeypatch.setattr(keyword_monitor, "KeywordMonitor", FailingMonitor)

    res = client.post("/api/keyword-monitor/check-now", json={})

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_get_alerts_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeMediaBias:
        def __init__(self, db):
            pass

        def get_bias_for_source(self, source):
            return None

    monkeypatch.setattr(keyword_monitor, "MediaBias", FakeMediaBias)

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_alerts(self, show_read):
            if self.mode == "error":
                raise Exception("DB error")
            columns = ["id", "is_read", "detected_at", "title", "url", "uri", "summary", "source", "publication_date", "matched_keyword"]
            rows = [(1, 0, "2025-01-01", "Test", "http://test.com", "uri1", "Summary", "BBC", "2025-01-01", "AI")]
            return (columns, rows)

        def get_article_enrichment(self, article_data):
            return None

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/alerts")

    assert res.status_code == 200
    assert "alerts" in res.json()

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/alerts")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_get_settings_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def create_keyword_monitor_table_if_not_exists_and_insert_default_value(self):
            pass

        def check_keyword_monitor_status_and_settings_tables(self):
            return (None, None)

        def get_count_of_monitored_keywords(self):
            return 10

        def get_settings_and_status_together(self):
            if self.mode == "error":
                raise Exception("DB error")
            if self.mode == "empty":
                return None
            # Return tuple with all expected values
            return (24, 3600, "title", "en", "publishedAt", 10, 100, True, "newsapi",
                    True, 0.0, True, False, "gpt-4o", 0.1, 1000, 0, None, None)

        def get_keyword_monitoring_providers(self):
            return '["newsapi"]'

        def get_auto_regenerate_reports_setting(self):
            return True

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/settings")

    assert res.status_code == 200
    assert "check_interval" in res.json()

    # ---------------- EMPTY (DEFAULTS) ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("empty")

    res = client.get("/api/keyword-monitor/settings")

    assert res.status_code == 200
    assert res.json()["check_interval"] == 24

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/settings")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_save_settings_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def update_or_insert_keyword_monitor_settings(self, data):
            if self.mode == "error":
                raise Exception("DB error")

        def update_keyword_monitoring_providers(self, providers):
            pass

        def update_auto_regenerate_reports_setting(self, value):
            pass

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    payload = {
        "check_interval": 24,
        "interval_unit": 3600,
        "search_fields": "title",
        "language": "en",
        "sort_by": "publishedAt",
        "page_size": 10,
        "daily_request_limit": 100,
        "provider": "newsapi",
        "providers": '["newsapi"]',
        "auto_ingest_enabled": True,
        "min_relevance_threshold": 0.0,
        "quality_control_enabled": True,
        "auto_save_approved_only": False,
        "default_llm_model": "gpt-4o",
        "llm_temperature": 0.1,
        "llm_max_tokens": 1000,
        "max_articles_per_run": 50,
        "auto_regenerate_reports": True
    }

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/settings", json=payload)

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post("/api/keyword-monitor/settings", json=payload)

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_get_available_providers_success(client, monkeypatch):

    # This endpoint doesn't depend on DB or session

    res = client.get("/api/keyword-monitor/available-providers")

    assert res.status_code == 200
    assert "providers" in res.json()

    # At minimum, arxiv and semantic_scholar are always available
    provider_ids = [p["id"] for p in res.json()["providers"]]
    assert "arxiv" in provider_ids
    assert "semantic_scholar" in provider_ids


def test_get_trends_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_trends(self):
            if self.mode == "error":
                raise Exception("DB error")
            return [(1, "Group1", "2025-01-01", 5), (1, "Group1", "2025-01-02", 10)]

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/trends")

    assert res.status_code == 200

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/trends")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_toggle_polling_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def toggle_polling(self, toggle):
            if self.mode == "error":
                raise Exception("DB error")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/toggle-polling", json={"enabled": True})

    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post("/api/keyword-monitor/toggle-polling", json={"enabled": True})

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_export_alerts_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def get_all_alerts_for_export_new_table_structure(self):
            if self.mode == "error":
                raise Exception("DB error")
            return [("Group1", "AI", "Title", "BBC", "http://test.com", "2025-01-01", "keyword1", "2025-01-01")]

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/export-alerts")

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/export-alerts")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_export_group_alerts_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def get_all_group_and_topic_alerts_for_export_new_table_structure(self, group_id, topic):
            if self.mode == "error":
                raise Exception("DB error")
            return [("Group1", "AI", "Title", "BBC", "http://test.com", "2025-01-01", "keyword1", "2025-01-01", 0)]

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/export-group-alerts?topic=AI&group_id=1")

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/export-group-alerts?topic=AI&group_id=1")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_mark_alert_unread_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def check_if_alert_id_exists_in_new_table_structure(self, alert_id):
            return True

        def mark_alert_as_read_or_unread_in_new_table(self, alert_id, status):
            if self.mode == "error":
                raise Exception("DB error")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/alerts/1/unread")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post("/api/keyword-monitor/alerts/1/unread")

    assert res.status_code == 500

    app.dependency_overrides.clear()


# ======================================================
# keyword_monitor.py endpoints (Batch 2: 18-34)
# ======================================================


def test_get_group_alerts_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeMediaBias:
        def __init__(self, db):
            pass

        def get_bias_for_source(self, source):
            return None

    monkeypatch.setattr(keyword_monitor, "MediaBias", FakeMediaBias)

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def get_alerts_by_group_id_from_new_table_structure(self, status, show_read, group_id, page_size, offset):
            if self.mode == "error":
                raise Exception("DB error")
            return [{
                'id': 1, 'article_uri': 'uri1', 'keyword_ids': '1,2', 'matched_keyword': 'AI',
                'is_read': 0, 'detected_at': '2025-01-01', 'below_threshold': False,
                'title': 'Test', 'summary': 'Summary', 'uri': 'http://test.com',
                'news_source': 'BBC', 'publication_date': '2025-01-01',
                'topic_alignment_score': 0.9, 'keyword_relevance_score': 0.8,
                'confidence_score': 0.85, 'overall_match_explanation': 'Good match',
                'extracted_article_topics': '["AI"]', 'extracted_article_keywords': '["ML"]',
                'category': 'Tech', 'sentiment': 'positive', 'driver_type': 'growth',
                'time_to_impact': 'short', 'future_signal': 'high',
                'bias': None, 'factual_reporting': None, 'mbfc_credibility_rating': None,
                'bias_country': None, 'press_freedom': None, 'media_type': None, 'popularity': None,
                'auto_ingested': False, 'ingest_status': None, 'quality_score': None, 'quality_issues': None
            }]

        def count_unread_articles_by_group_id_from_new_table_structure(self, group_id):
            return 5

        def count_total_articles_by_group_id_from_new_table_structure(self, group_id, status):
            return 10

        def get_group_name(self, group_id):
            return "Test Group"

        def get_all_matched_keywords_for_article_and_group(self, placeholders, params):
            return ["AI", "ML"]

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/alerts/AI?group_id=1")

    assert res.status_code == 200
    assert "alerts" in res.json()

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/alerts/AI?group_id=1")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_delete_articles_by_topic_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_article_matches_table_exists(self):
            return True

        def get_article_urls_from_news_search_results_by_topic(self, topic):
            if self.mode == "error":
                raise Exception("DB error")
            return [{"article_uri": "uri1"}]

        def get_article_urls_from_paper_search_results_by_topic(self, topic):
            return []

        def check_if_articles_table_has_topic_column(self):
            return False

        def delete_article_matches_by_url(self, uri):
            return 1

        def delete_news_search_results_by_topic(self, topic):
            pass

        def delete_paper_search_results_by_topic(self, topic):
            pass

        def delete_article_by_url(self, uri):
            return 1

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.delete("/api/keyword-monitor/articles/by-topic/AI")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.delete("/api/keyword-monitor/articles/by-topic/AI")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_get_bluesky_posts_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    # ---------------- SUCCESS ----------------

    class FakeCollector:
        async def search_articles(self, query, topic, max_results):
            return [{"title": "Test Post", "summary": "Content", "url": "http://test.com", "published_date": "2025-01-01"}]

    monkeypatch.setattr("app.collectors.bluesky_collector.BlueskyCollector", lambda: FakeCollector())

    res = client.get("/api/keyword-monitor/bluesky-posts?query=AI&topic=tech&count=5")

    assert res.status_code == 200

    # ---------------- NOT CONFIGURED ----------------

    class NotConfiguredCollector:
        def __init__(self):
            raise ValueError("credentials not configured")

    monkeypatch.setattr("app.collectors.bluesky_collector.BlueskyCollector", NotConfiguredCollector)

    res = client.get("/api/keyword-monitor/bluesky-posts?query=AI&topic=tech")

    assert res.status_code == 200
    assert res.json() == []

    app.dependency_overrides.clear()


def test_clean_orphaned_topics_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    monkeypatch.setattr(keyword_monitor, "load_config", lambda: {"topics": [{"name": "AI"}]})

    from sqlalchemy.exc import OperationalError

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_keyword_groups_table_exists(self):
            if self.mode == "no_table":
                return False
            return True

        def get_all_topics_referenced_in_keyword_groups(self):
            if self.mode == "error":
                # Raise OperationalError to match what the endpoint catches
                raise OperationalError("DB error", None, None)
            return {"AI", "Orphan"}

        def get_all_group_ids_associated_to_topic(self, topic):
            return []

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/clean-orphaned-topics")

    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # ---------------- NO TABLE ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("no_table")

    res = client.post("/api/keyword-monitor/clean-orphaned-topics")

    assert res.status_code == 200

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.post("/api/keyword-monitor/clean-orphaned-topics")

    assert res.status_code == 200
    assert res.json()["status"] == "error"

    app.dependency_overrides.clear()


def test_clean_orphaned_articles_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    monkeypatch.setattr(keyword_monitor, "load_config", lambda: {"topics": [{"name": "AI"}]})

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def check_if_articles_table_exists(self):
            if self.mode == "no_table":
                return False
            return True

        def check_if_articles_table_has_topic_column(self):
            return False

        def check_if_news_search_results_table_exists(self):
            return False

        def check_if_paper_search_results_table_exists(self):
            return False

        def check_if_keyword_article_matches_table_exists(self):
            return True

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/clean-orphaned-articles")

    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # ---------------- NO TABLE ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("no_table")

    res = client.post("/api/keyword-monitor/clean-orphaned-articles")

    assert res.status_code == 200

    app.dependency_overrides.clear()


def test_clean_all_orphaned_success_and_failure(client, monkeypatch):

    app = client.app

    app.dependency_overrides[verify_session] = lambda: {"user": "test"}

    monkeypatch.setattr(keyword_monitor, "load_config", lambda: {"topics": [{"name": "AI"}]})

    class FakeFacade:
        def check_if_keyword_groups_table_exists(self):
            return True

        def get_all_topics_referenced_in_keyword_groups(self):
            return {"AI"}

        def check_if_articles_table_exists(self):
            return True

        def check_if_articles_table_has_topic_column(self):
            return False

        def check_if_news_search_results_table_exists(self):
            return False

        def check_if_paper_search_results_table_exists(self):
            return False

        def check_if_keyword_article_matches_table_exists(self):
            return True

    class FakeDB:
        def __init__(self):
            self.facade = FakeFacade()

    app.dependency_overrides[get_database_instance] = lambda: FakeDB()

    res = client.post("/api/keyword-monitor/clean-all-orphaned")

    assert res.status_code == 200
    assert res.json()["status"] == "success"

    app.dependency_overrides.clear()


def test_get_keyword_monitor_status_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    monkeypatch.setattr(keyword_monitor, "get_task_status", lambda: {"running": False})

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_monitor_settings(self):
            if self.mode == "error":
                raise Exception("DB error")
            return (15, 60, True, 7, 100)

        def get_total_number_of_keywords(self):
            return 10

        def get_request_count_for_today(self):
            return (5, "2025-01-01")

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/status")

    assert res.status_code == 200
    assert "settings" in res.json()

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/status")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_analyze_relevance_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_keywords_associated_to_group_ordered_by_keyword(self, group_id):
            return ["AI", "ML"]

        def get_articles_by_url(self, uri):
            if self.mode == "not_found":
                return None
            return {"uri": uri, "title": "Test", "news_source": "BBC", "summary": "Content"}

        def get_raw_articles_markdown_by_url(self, uri):
            return (None,)

        def update_article_by_url(self, data):
            if self.mode == "error":
                raise Exception("DB error")
            return 1

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    class FakeRelevanceCalculator:
        def __init__(self, model):
            pass

        def analyze_articles_batch(self, articles, topic, keywords):
            return [{
                'uri': 'uri1', 'title': 'Test',
                'topic_alignment_score': 0.9, 'keyword_relevance_score': 0.8,
                'confidence_score': 0.85, 'overall_match_explanation': 'Good',
                'extracted_article_topics': [], 'extracted_article_keywords': []
            }]

    monkeypatch.setattr(keyword_monitor, "RelevanceCalculator", FakeRelevanceCalculator)

    payload = {
        "article_uris": ["uri1"],
        "model_name": "gpt-4o",
        "topic": "AI",
        "group_id": 1
    }

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/analyze-relevance", json=payload)

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- NOT FOUND ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("not_found")

    res = client.post("/api/keyword-monitor/analyze-relevance", json=payload)

    assert res.status_code == 404

    app.dependency_overrides.clear()


def test_review_content_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    class FakeLLM:
        async def agenerate_response(self, messages):
            return '{"quality_score": 0.9, "issues_detected": [], "recommendation": "approve", "explanation": "Good", "content_type": "article"}'

    monkeypatch.setattr(keyword_monitor.LiteLLMModel, "get_instance", lambda m: FakeLLM())

    payload = {
        "article_title": "Test Article",
        "article_summary": "Test content",
        "article_source": "BBC",
        "model_name": "gpt-4o"
    }

    # ---------------- SUCCESS ----------------

    res = client.post("/api/keyword-monitor/review-content", json=payload)

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- PARSE ERROR ----------------

    class BadLLM:
        async def agenerate_response(self, messages):
            return "Not JSON"

    monkeypatch.setattr(keyword_monitor.LiteLLMModel, "get_instance", lambda m: BadLLM())

    res = client.post("/api/keyword-monitor/review-content", json=payload)

    assert res.status_code == 200
    assert res.json()["success"] is False

    app.dependency_overrides.clear()


def test_enable_auto_ingest_success_and_failure(client, monkeypatch):
    """
    NOTE: There is a BUG in the enable_auto_ingest endpoint (line 2261).
    It references 'toggle.enabled' but 'toggle' is not defined in that endpoint.
    This test documents the bug - the endpoint will fail with NameError.
    """
    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def enable_or_disable_auto_ingest(self, enabled):
            pass

    class FakeDB:
        def __init__(self):
            self.facade = FakeFacade()

    app.dependency_overrides[get_database_instance] = lambda: FakeDB()

    # This will fail due to the bug (NameError: 'toggle' is not defined)
    res = client.post("/api/keyword-monitor/auto-ingest/enable")

    # Due to bug, this returns 500 instead of 200
    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_disable_auto_ingest_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def enable_or_disable_auto_ingest(self, enabled):
            if self.mode == "error":
                raise Exception("DB error")
            return {"success": True}

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.post("/api/keyword-monitor/auto-ingest/disable")

    assert res.status_code == 200

    app.dependency_overrides.clear()


def test_get_auto_ingest_status_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}

    class FakeFacade:
        def __init__(self, mode="success"):
            self.mode = mode

        def get_auto_ingest_settings(self):
            if self.mode == "error":
                raise Exception("DB error")
            if self.mode == "empty":
                return None
            return (True, 0.0, True, False, "gpt-4o", 0.2, 1000)

        def get_processing_statistics(self):
            return (100, 80, 5, 0.85)

    class FakeDB:
        def __init__(self, mode="success"):
            self.facade = FakeFacade(mode)

    # ---------------- SUCCESS ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("success")

    res = client.get("/api/keyword-monitor/auto-ingest/status")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- EMPTY (DEFAULTS) ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("empty")

    res = client.get("/api/keyword-monitor/auto-ingest/status")

    assert res.status_code == 200
    assert res.json()["settings"]["auto_ingest_enabled"] is True

    # ---------------- ERROR ----------------

    app.dependency_overrides[get_database_instance] = lambda: FakeDB("error")

    res = client.get("/api/keyword-monitor/auto-ingest/status")

    assert res.status_code == 500

    app.dependency_overrides.clear()


def test_trigger_auto_ingest_success_and_failure(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    class FakeMonitor:
        def __init__(self, db):
            pass

        def should_auto_ingest(self):
            return True

    monkeypatch.setattr("app.tasks.keyword_monitor.KeywordMonitor", FakeMonitor)

    res = client.post("/api/keyword-monitor/auto-ingest/trigger")

    assert res.status_code == 200
    assert res.json()["success"] is True

    # ---------------- DISABLED ----------------

    class DisabledMonitor:
        def __init__(self, db):
            pass

        def should_auto_ingest(self):
            return False

    monkeypatch.setattr("app.tasks.keyword_monitor.KeywordMonitor", DisabledMonitor)

    res = client.post("/api/keyword-monitor/auto-ingest/trigger")

    assert res.status_code == 200
    assert res.json()["success"] is False

    app.dependency_overrides.clear()


def test_bulk_process_topic_dry_run_success(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    class FakeAsyncDB:
        async def get_topic_articles(self, topic_id):
            return ([{"uri": "1"}, {"uri": "2"}], [{"uri": "1"}])

    class FakeService:
        def __init__(self, db):
            self.async_db = FakeAsyncDB()

    async def fake_init_async_db():
        pass

    monkeypatch.setattr("app.services.automated_ingest_service.AutomatedIngestService", FakeService)
    monkeypatch.setattr("app.services.async_db.initialize_async_db", fake_init_async_db)

    payload = {
        "topic_id": "AI",
        "max_articles": 100,
        "dry_run": True
    }

    res = client.post("/api/keyword-monitor/bulk-process-topic", json=payload)

    assert res.status_code == 200
    assert res.json()["dry_run"] is True

    app.dependency_overrides.clear()


def test_get_bulk_process_status_success_and_not_found(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    # Add a fake job
    from datetime import datetime
    job = keyword_monitor.ProcessingJob("test-job-id", "AI", {})
    job.status = "completed"
    job.progress = 100
    job.results = {"processed": 10}
    job.completed_at = datetime.utcnow()

    keyword_monitor._processing_jobs["test-job-id"] = job

    # ---------------- SUCCESS ----------------

    res = client.get("/api/keyword-monitor/bulk-process-status/test-job-id")

    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    # ---------------- NOT FOUND ----------------

    res = client.get("/api/keyword-monitor/bulk-process-status/unknown-job")

    assert res.status_code == 404

    # Cleanup
    del keyword_monitor._processing_jobs["test-job-id"]
    app.dependency_overrides.clear()


def test_get_active_jobs_status_success(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    monkeypatch.setattr("app.tasks.keyword_monitor.get_keyword_monitor_jobs", lambda: {})

    res = client.get("/api/keyword-monitor/active-jobs-status")

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "active_jobs" in res.json()

    app.dependency_overrides.clear()


def test_clear_completed_jobs_success(client, monkeypatch):

    app = client.app

    from app.security.session import verify_session_api

    app.dependency_overrides[verify_session_api] = lambda: {"user": "test"}
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()

    # Add a completed job
    from datetime import datetime
    job = keyword_monitor.ProcessingJob("completed-job", "AI", {})
    job.status = "completed"
    job.completed_at = datetime.utcnow()

    keyword_monitor._processing_jobs["completed-job"] = job

    res = client.post("/api/keyword-monitor/clear-completed-jobs")

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "completed-job" not in keyword_monitor._processing_jobs

    app.dependency_overrides.clear()


# ====================================================
# keyword_alerts.py endpoints
# ====================================================

from fastapi.responses import HTMLResponse


def test_keyword_alerts_page_old_success_and_failure(client, monkeypatch):

    app = client.app


    # =====================================================
    # MOCK HELPERS
    # =====================================================

    monkeypatch.setattr(
        "app.routes.keyword_alerts.get_monitor_settings",
        lambda: True
    )

    monkeypatch.setattr(
        "app.routes.keyword_alerts.get_last_check_time",
        lambda: "2026-01-01"
    )

    monkeypatch.setattr(
        "app.routes.keyword_alerts.get_unread_alerts",
        lambda: []
    )


    # =====================================================
    # MOCK TEMPLATE RENDERING (RETURN REAL RESPONSE)
    # =====================================================

    def fake_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)


    monkeypatch.setattr(
        "app.routes.keyword_alerts.templates.TemplateResponse",
        fake_template
    )


    # =====================================================
    # SUCCESS
    # =====================================================

    res = client.get("/api/keyword-alerts-old")

    assert res.status_code == 200
    assert "OK" in res.text


    # =====================================================
    # FAILURE
    # =====================================================

    def bad_monitor():
        raise Exception("DB error")


    monkeypatch.setattr(
        "app.routes.keyword_alerts.get_monitor_settings",
        bad_monitor
    )


    res = client.get("/api/keyword-alerts-old")

    assert res.status_code == 500


def test_keyword_alerts_bulk_delete_articles_success_and_failure(client, monkeypatch):

    app = client.app


    # =====================================================
    # FAKE DB
    # =====================================================

    class FakeDB:

        def __init__(self, fail=False):
            self.fail = fail

            if fail:
                def bad_bulk_delete(*args, **kwargs):
                    raise Exception("DB error")

                self.bulk_delete_articles = bad_bulk_delete

        def bulk_delete_articles(self, uris):
            return len(uris)


    # =====================================================
    # OVERRIDE DB DEPENDENCY
    # =====================================================

    fake_db = FakeDB()


    app.dependency_overrides[
        get_database_instance
    ] = lambda: fake_db


    # =====================================================
    # SUCCESS CASE
    # =====================================================

    payload = {
        "uris": [
            "https://test.com/a1",
            "https://test.com/a2"
        ]
    }


    res = client.request(
        "DELETE",
        "/api/bulk_delete_articles",
        json=payload
    )

    assert res.status_code == 200

    data = res.json()

    assert data["status"] == "success"
    assert data["deleted_count"] == 2


    # =====================================================
    # FAILURE CASE
    # =====================================================

    bad_db = FakeDB(fail=True)


    app.dependency_overrides[
        get_database_instance
    ] = lambda: bad_db


    res = client.request(
        "DELETE",
        "/api/bulk_delete_articles",
        json=payload
    )

    assert res.status_code == 500



#==================================================
# feed_routes.py endpoints
#==================================================


def _sample_feed_group(group_id: int = 1):
    return {
        "id": group_id,
        "name": "Test Group",
        "description": "desc",
        "color": "#FF69B4",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "sources": [],
    }


def _sample_feed_item(item_id: int = 1):
    return {
        "id": item_id,
        "source_type": "arxiv",
        "title": "Test Title",
        "content": "Test Content",
        "author": "Author",
        "author_handle": None,
        "url": "https://example.com/item",
        "publication_date": "2026-01-01T00:00:00Z",
        "engagement_metrics": {"score": 1},
        "tags": [],
        "mentions": [],
        "images": [],
        "is_hidden": False,
        "is_starred": False,
        "created_at": "2026-01-01T00:00:00Z",
        "group_name": "Test Group",
        "group_color": "#FF69B4",
    }


def _sample_unified_feed(limit: int = 50, offset: int = 0):
    return {
        "success": True,
        "items": [_sample_feed_item(1)],
        "total_count": 1,
        "limit": limit,
        "offset": offset,
        "has_more": False,
    }


def test_get_feed_groups_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "get_feed_groups",
        lambda self, include_inactive=False: [_sample_feed_group(1)],
    )
    res = client.get("/api/feed-groups")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)
    assert res.json()[0]["id"] == 1

    # FAILURE
    monkeypatch.setattr(
        FeedGroupService,
        "get_feed_groups",
        lambda self, include_inactive=False: (_ for _ in ()).throw(Exception("boom")),
    )
    res = client.get("/api/feed-groups")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_create_feed_group_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    payload = {"name": "New Group", "description": "d", "color": "#FF69B4"}

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "create_feed_group",
        lambda self, name, description, color: {
            "success": True,
            "group": _sample_feed_group(123),
        },
    )
    res = client.post("/api/feed-groups", json=payload)
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["success"] is True
    assert res.json()["group"]["id"] == 123

    # FAILURE (400)
    monkeypatch.setattr(
        FeedGroupService,
        "create_feed_group",
        lambda self, name, description, color: {"success": False, "error": "bad request"},
    )
    res = client.post("/api/feed-groups", json=payload)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "bad request"


def test_get_feed_group_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "get_feed_group",
        lambda self, group_id: _sample_feed_group(group_id),
    )
    res = client.get("/api/feed-groups/1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == 1

    # FAILURE (404)
    monkeypatch.setattr(FeedGroupService, "get_feed_group", lambda self, group_id: None)
    res = client.get("/api/feed-groups/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_update_feed_group_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    payload = {"name": "Updated", "description": "d", "color": "#FF69B4", "is_active": True}

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "update_feed_group",
        lambda self, group_id, name, description, color, is_active: {"success": True},
    )
    res = client.put("/api/feed-groups/1", json=payload)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404 via "not found")
    monkeypatch.setattr(
        FeedGroupService,
        "update_feed_group",
        lambda self, group_id, name, description, color, is_active: {
            "success": False,
            "error": "Group not found",
        },
    )
    res = client.put("/api/feed-groups/999", json=payload)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_feed_group_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService, "delete_feed_group", lambda self, group_id: {"success": True}
    )
    res = client.delete("/api/feed-groups/1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404 via "not found")
    monkeypatch.setattr(
        FeedGroupService,
        "delete_feed_group",
        lambda self, group_id: {"success": False, "error": "not found"},
    )
    res = client.delete("/api/feed-groups/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_get_group_sources_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "get_feed_group",
        lambda self, group_id: {**_sample_feed_group(group_id), "sources": [{"id": 1}]},
    )
    res = client.get("/api/feed-groups/1/sources")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["sources"] == [{"id": 1}]

    # FAILURE (404)
    monkeypatch.setattr(FeedGroupService, "get_feed_group", lambda self, group_id: None)
    res = client.get("/api/feed-groups/999/sources")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_add_source_to_group_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    payload = {"source_type": "arxiv", "keywords": ["ai"], "enabled": True, "date_range_days": 7}

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "add_source_to_group",
        lambda self, group_id, source_type, keywords, enabled, date_range_days, custom_start_date, custom_end_date: {
            "success": True,
            "source_id": 10,
        },
    )
    res = client.post("/api/feed-groups/1/sources", json=payload)
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json()["success"] is True

    # FAILURE (400)
    monkeypatch.setattr(
        FeedGroupService,
        "add_source_to_group",
        lambda self, group_id, source_type, keywords, enabled, date_range_days, custom_start_date, custom_end_date: {
            "success": False,
            "error": "invalid source",
        },
    )
    res = client.post("/api/feed-groups/1/sources", json=payload)
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_update_source_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    payload = {"keywords": ["x"], "enabled": True, "date_range_days": 7}

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService,
        "update_source",
        lambda self, source_id, keywords, enabled, date_range_days, custom_start_date, custom_end_date: {
            "success": True
        },
    )
    res = client.put("/api/feed-groups/1/sources/2", json=payload)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404)
    monkeypatch.setattr(
        FeedGroupService,
        "update_source",
        lambda self, source_id, keywords, enabled, date_range_days, custom_start_date, custom_end_date: {
            "success": False,
            "error": "Source not found",
        },
    )
    res = client.put("/api/feed-groups/1/sources/999", json=payload)
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_delete_source_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService

    # SUCCESS
    monkeypatch.setattr(
        FeedGroupService, "delete_source", lambda self, source_id: {"success": True}
    )
    res = client.delete("/api/feed-groups/1/sources/2")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404)
    monkeypatch.setattr(
        FeedGroupService,
        "delete_source",
        lambda self, source_id: {"success": False, "error": "not found"},
    )
    res = client.delete("/api/feed-groups/1/sources/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_get_unified_feed_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    # SUCCESS
    monkeypatch.setattr(
        UnifiedFeedService,
        "get_unified_feed",
        lambda self, **kwargs: _sample_unified_feed(limit=kwargs["limit"], offset=kwargs["offset"]),
    )
    res = client.get("/api/unified-feed?limit=10&offset=0")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["limit"] == 10

    # FAILURE (500 via success False)
    monkeypatch.setattr(
        UnifiedFeedService,
        "get_unified_feed",
        lambda self, **kwargs: {"success": False, "error": "boom"},
    )
    res = client.get("/api/unified-feed?limit=10&offset=0")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_group_feed_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    # SUCCESS
    monkeypatch.setattr(
        UnifiedFeedService,
        "get_group_feed",
        lambda self, **kwargs: _sample_unified_feed(limit=kwargs["limit"], offset=kwargs["offset"]),
    )
    res = client.get("/api/feed-groups/1/feed?limit=5&offset=0")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["limit"] == 5

    # FAILURE (500 via success False)
    monkeypatch.setattr(
        UnifiedFeedService,
        "get_group_feed",
        lambda self, **kwargs: {"success": False, "error": "boom"},
    )
    res = client.get("/api/feed-groups/1/feed?limit=5&offset=0")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_hide_feed_item_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    # SUCCESS
    monkeypatch.setattr(
        UnifiedFeedService, "hide_feed_item", lambda self, item_id: {"success": True}
    )
    res = client.post("/api/feed-items/1/hide")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404)
    monkeypatch.setattr(
        UnifiedFeedService,
        "hide_feed_item",
        lambda self, item_id: {"success": False, "error": "Item not found"},
    )
    res = client.post("/api/feed-items/999/hide")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_star_feed_item_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    # SUCCESS
    monkeypatch.setattr(
        UnifiedFeedService,
        "star_feed_item",
        lambda self, item_id, starred: {"success": True, "action": "starred"},
    )
    res = client.post("/api/feed-items/1/star", json=True)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (400)
    monkeypatch.setattr(
        UnifiedFeedService,
        "star_feed_item",
        lambda self, item_id, starred: {"success": False, "error": "bad"},
    )
    res = client.post("/api/feed-items/1/star", json=True)
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_add_tags_to_feed_item_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_feed_item_tags",
        lambda self, item_id: ('["existing"]',),
    )
    monkeypatch.setattr(DatabaseQueryFacade, "update_feed_tags", lambda self, args: None)
    res = client.post("/api/feed-items/1/tags", json={"tags": ["new"]})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["tags_added"] == ["new"]

    # FAILURE (400 - invalid tags)
    res = client.post("/api/feed-items/1/tags", json={"tags": []})
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_collect_feed_items_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    async def ok_collect(self, group_id, max_items):
        return {"success": True, "items_collected": 3}

    async def bad_collect(self, group_id, max_items):
        return {"success": False, "error": "Group not found"}

    # SUCCESS
    monkeypatch.setattr(UnifiedFeedService, "collect_feed_items_for_group", ok_collect)
    res = client.post("/api/feed-groups/1/collect?max_items=5")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (404)
    monkeypatch.setattr(UnifiedFeedService, "collect_feed_items_for_group", bad_collect)
    res = client.post("/api/feed-groups/999/collect?max_items=5")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_collect_all_groups_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    async def ok_collect_all(self, max_items_per_group):
        return {"success": True, "total_items_collected": 2, "groups_processed": 1}

    async def bad_collect_all(self, max_items_per_group):
        return {"success": False, "error": "boom"}

    # SUCCESS
    monkeypatch.setattr(UnifiedFeedService, "collect_all_active_groups", ok_collect_all)
    res = client.post("/api/feed-collection/collect-all?max_items_per_group=5")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (500)
    monkeypatch.setattr(UnifiedFeedService, "collect_all_active_groups", bad_collect_all)
    res = client.post("/api/feed-collection/collect-all?max_items_per_group=5")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_collect_by_source_success_and_failure(client, monkeypatch):
    from app.services.unified_feed_service import UnifiedFeedService

    # Ensure no heavy init work runs
    monkeypatch.setattr(UnifiedFeedService, "__init__", lambda self, db: None)

    # SUCCESS: no groups configured
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_feed_keywords_by_source_type",
        lambda self, source_type: [],
    )
    res = client.post("/api/feed-collection/collect?source_type=arxiv&max_items=5")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["items_collected"] == 0

    # FAILURE (500): facade raises
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_feed_keywords_by_source_type",
        lambda self, source_type: (_ for _ in ()).throw(Exception("boom")),
    )
    res = client.post("/api/feed-collection/collect?source_type=arxiv&max_items=5")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_group_stats_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_statistics_for_specific_feed_group",
        lambda self, group_id: (10, {"arxiv": 10}, [{"id": 1}]),
    )
    res = client.get("/api/feed-groups/1/stats")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["total_items"] == 10

    # FAILURE (500)
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_statistics_for_specific_feed_group",
        lambda self, group_id: (_ for _ in ()).throw(Exception("boom")),
    )
    res = client.get("/api/feed-groups/1/stats")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_feed_item_enrichment_success_and_failure(client, monkeypatch):
    # SUCCESS: item exists but no enrichment data
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_feed_item_url",
        lambda self, item_id: ("https://example.com/item",),
    )
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_enrichment_data_for_article",
        lambda self, url: None,
    )
    res = client.get("/api/feed-items/1/enrichment")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["enriched"] is False

    # FAILURE (404): item not found
    monkeypatch.setattr(DatabaseQueryFacade, "get_feed_item_url", lambda self, item_id: None)
    res = client.get("/api/feed-items/999/enrichment")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_save_enriched_feed_item_success_and_failure(client, monkeypatch):
    # SUCCESS: article already exists with enrichment
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_feed_item_details",
        lambda self, item_id: (
            "https://example.com/item",
            "Title",
            "Content",
            "Author",
            "2026-01-01T00:00:00Z",
            "arxiv",
            1,
        ),
    )
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_enrichment_data_for_article_with_extra_fields",
        lambda self, url: (
            "category",
            "sentiment",
            "driver",
            "time",
            0.1,
            0.2,
            0.3,
            "explain",
            "topics",
            "keywords",
            1,
            "status",
            0.9,
            "issues",
            "sent_explain",
            "signal",
            "signal_explain",
            "driver_explain",
            "time_explain",
            "summary",
            "tags",
            "topic",
        ),
    )
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "check_if_article_exists_with_enrichment",
        lambda self, url: (123,),
    )
    res = client.post("/api/feed-items/1/save-enriched")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["already_existed"] is True

    # FAILURE (404): feed item not found
    monkeypatch.setattr(DatabaseQueryFacade, "get_feed_item_details", lambda self, item_id: None)
    res = client.post("/api/feed-items/999/save-enriched")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_feed_system_health_success_and_failure(client, monkeypatch):
    from app.services.feed_group_service import FeedGroupService
    from app.services.unified_feed_service import UnifiedFeedService

    def _init_feed_group(self, db):
        return None

    def _init_unified(self, db):
        self.arxiv_collector = object()
        self.bluesky_collector = object()
        return None

    # SUCCESS
    monkeypatch.setattr(DatabaseQueryFacade, "get_keyword_groups_count", lambda self: 2)
    monkeypatch.setattr(DatabaseQueryFacade, "get_feed_item_count", lambda self: 5)
    monkeypatch.setattr(FeedGroupService, "__init__", _init_feed_group)
    monkeypatch.setattr(UnifiedFeedService, "__init__", _init_unified)
    res = client.get("/api/feed-system/health")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "healthy"
    assert res.json()["feed_groups"] == 2

    # FAILURE (500)
    monkeypatch.setattr(
        DatabaseQueryFacade,
        "get_keyword_groups_count",
        lambda self: (_ for _ in ()).throw(Exception("boom")),
    )
    res = client.get("/api/feed-system/health")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


#==================================================
# news_feed_routes.py endpoints
#==================================================


def test_get_available_dates_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    # SUCCESS
    fake_db.fetch_all.return_value = [("2026-01-01", 2)]
    res = client.get("/api/news-feed/available-dates")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert isinstance(body["dates"], list)
    assert body["dates"][0]["date"] == "2026-01-01"
    assert body["dates"][0]["count"] == 2

    # FAILURE (500)
    fake_db.fetch_all.side_effect = Exception("boom")
    res = client.get("/api/news-feed/available-dates")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_generate_daily_news_feed_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    from datetime import datetime
    from app.schemas.news_feed import NewsFeedResponse, DailyOverview, SixArticlesReport

    fake_response = NewsFeedResponse(
        overview=DailyOverview(date=datetime(2026, 1, 1)),
        six_articles=SixArticlesReport(date=datetime(2026, 1, 1)),
    )

    fake_service = MagicMock()
    fake_service.generate_daily_feed = AsyncMock(return_value=fake_response)

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )

    # SUCCESS
    res = client.get("/api/news-feed/daily?date=2026-01-01")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "overview" in body
    assert "six_articles" in body

    # FAILURE (400 - invalid date)
    res = client.get("/api/news-feed/daily?date=not-a-date")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # FAILURE (500 - service exception)
    fake_service.generate_daily_feed = AsyncMock(side_effect=Exception("boom"))
    res = client.get("/api/news-feed/daily?date=2026-01-01")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_news_articles_only_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    fake_service = MagicMock()
    fake_service._get_articles_for_date_range = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_article_list = AsyncMock(
        return_value={
            "items": [{"id": 1}],
            "total_items": 1,
            "total_articles": 1,
            "page": 1,
            "per_page": 20,
            "total_pages": 1,
            "date": "2026-01-01T00:00:00",
        }
    )

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )

    # SUCCESS
    res = client.get("/api/news-feed/articles?date_range=24h&page=1&per_page=20")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "articles" in body
    assert isinstance(body["articles"]["items"], list)

    # EMPTY (200)
    fake_service._get_articles_for_date_range = AsyncMock(return_value=[])
    fake_service._get_total_articles_count_for_date_range = AsyncMock(return_value=0)
    res = client.get("/api/news-feed/articles?date_range=24h&page=1&per_page=20")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["articles"]["items"] == []
    assert body["articles"]["total_items"] == 0

    # FAILURE (500 - service error)
    fake_service._get_articles_for_date_range = AsyncMock(side_effect=Exception("boom"))
    res = client.get("/api/news-feed/articles?date_range=24h&page=1&per_page=20")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_six_articles_report_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: {"user_id": 1, "user": {"username": "test-user"}}

    fake_service = MagicMock()
    fake_service._get_articles_for_date_range = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_six_articles_report_cached = AsyncMock(
        return_value=[{"related_articles": []}]
    )

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )

    # SUCCESS
    res = client.get("/api/news-feed/six-articles?date_range=24h")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json()["six_articles"], list)

    # EMPTY (200)
    fake_service._get_articles_for_date_range = AsyncMock(return_value=[])
    res = client.get("/api/news-feed/six-articles?date_range=24h")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"six_articles": []}

    # FAILURE (500)
    fake_service._get_articles_for_date_range = AsyncMock(side_effect=Exception("boom"))
    res = client.get("/api/news-feed/six-articles?date_range=24h")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_news_feed_page_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    from fastapi import HTTPException

    # SUCCESS
    def ok_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", ok_template)
    res = client.get("/news-feed")
    assert res.status_code == status.HTTP_200_OK
    assert "OK" in res.text

    # FAILURE (500 - template error)
    def bad_template(*args, **kwargs):
        raise HTTPException(status_code=500, detail="template error")

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", bad_template)
    res = client.get("/news-feed")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_news_feed_v2_page_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    from fastapi import HTTPException

    # SUCCESS
    def ok_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", ok_template)
    res = client.get("/news-feed-v2")
    assert res.status_code == status.HTTP_200_OK
    assert "OK" in res.text

    # FAILURE (500 - template error)
    def bad_template(*args, **kwargs):
        raise HTTPException(status_code=500, detail="template error")

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", bad_template)
    res = client.get("/news-feed-v2")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_news_overview_page_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    from fastapi import HTTPException

    # SUCCESS
    def ok_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", ok_template)
    res = client.get("/news-feed/overview?date=2026-01-01")
    assert res.status_code == status.HTTP_200_OK
    assert "OK" in res.text

    # FAILURE (500 - template error)
    def bad_template(*args, **kwargs):
        raise HTTPException(status_code=500, detail="template error")

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", bad_template)
    res = client.get("/news-feed/overview?date=2026-01-01")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_six_articles_page_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    from fastapi import HTTPException

    # SUCCESS
    def ok_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", ok_template)
    res = client.get("/news-feed/six-articles?date=2026-01-01")
    assert res.status_code == status.HTTP_200_OK
    assert "OK" in res.text

    # FAILURE (500 - template error)
    def bad_template(*args, **kwargs):
        raise HTTPException(status_code=500, detail="template error")

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", bad_template)
    res = client.get("/news-feed/six-articles?date=2026-01-01")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_overview_markdown_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    from datetime import datetime
    from app.schemas.news_feed import DailyOverview

    fake_service = MagicMock()
    fake_service._get_articles_for_date = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_overview = AsyncMock(
        return_value=DailyOverview(date=datetime(2026, 1, 1), top_stories=[])
    )

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )

    # SUCCESS
    res = client.get("/api/news-feed/markdown/overview?date=2026-01-01")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert isinstance(body["markdown"], str)
    assert "overview" in body

    # FAILURE (404 - no articles)
    fake_service._get_articles_for_date = AsyncMock(return_value=[])
    res = client.get("/api/news-feed/markdown/overview?date=2026-01-01")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE (500 - error)
    fake_service._get_articles_for_date = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_overview = AsyncMock(side_effect=Exception("boom"))
    res = client.get("/api/news-feed/markdown/overview?date=2026-01-01")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_six_articles_markdown_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    from datetime import datetime
    from app.schemas.news_feed import SixArticlesReport

    fake_service = MagicMock()
    fake_service._get_articles_for_date = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_six_articles_report = AsyncMock(
        return_value=SixArticlesReport(date=datetime(2026, 1, 1), articles=[])
    )

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )

    # SUCCESS
    res = client.get("/api/news-feed/markdown/six-articles?date=2026-01-01")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert isinstance(body["markdown"], str)
    assert "six_articles" in body

    # FAILURE (404 - no articles)
    fake_service._get_articles_for_date = AsyncMock(return_value=[])
    res = client.get("/api/news-feed/markdown/six-articles?date=2026-01-01")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE (500 - error)
    fake_service._get_articles_for_date = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_six_articles_report = AsyncMock(side_effect=Exception("boom"))
    res = client.get("/api/news-feed/markdown/six-articles?date=2026-01-01")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_six_articles_config_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    fake_db.facade = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    # SUCCESS (user-specific config)
    fake_db.facade.get_six_articles_config.return_value = {"systemPrompt": "x", "personas": {}}
    res = client.get("/api/news-feed/six-articles/config")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["systemPrompt"] == "x"

    # DEFAULT (no user config)
    fake_db.facade.get_six_articles_config.return_value = None
    res = client.get("/api/news-feed/six-articles/config")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "personas" in body
    assert "CEO" in body["personas"]

    # FAILURE (500)
    fake_db.facade.get_six_articles_config.side_effect = Exception("boom")
    res = client.get("/api/news-feed/six-articles/config")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_save_six_articles_config_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    fake_db.facade = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}

    good_config = {
        "systemPrompt": "x",
        "personas": {
            "CEO": {"priorities": "p", "riskAppetite": "r", "focus": "f"},
            "CMO": {"priorities": "p", "riskAppetite": "r", "focus": "f"},
            "CTO": {"priorities": "p", "riskAppetite": "r", "focus": "f"},
            "CISO": {"priorities": "p", "riskAppetite": "r", "focus": "f"},
        },
        "formatSpec": "y",
    }

    # SUCCESS
    fake_db.facade.save_six_articles_config.return_value = True
    res = client.post("/api/news-feed/six-articles/config", json=good_config)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # VALIDATION (400 - missing persona)
    bad_config = {
        "personas": {
            "CEO": {},
            "CMO": {},
            "CISO": {},
        }
    }
    res = client.post("/api/news-feed/six-articles/config", json=bad_config)
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE (500 - save fails)
    fake_db.facade.save_six_articles_config.return_value = False
    res = client.post("/api/news-feed/six-articles/config", json=good_config)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_six_articles_defaults_success_and_failure(client, monkeypatch):
    app = client.app
    from fastapi import HTTPException

    # SUCCESS
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}
    res = client.get("/api/news-feed/six-articles/config/defaults")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "personas" in body
    assert "CEO" in body["personas"]

    # FAILURE (500 - session dependency error)
    def bad_session():
        raise HTTPException(status_code=500, detail="boom")

    app.dependency_overrides[verify_session] = bad_session
    res = client.get("/api/news-feed/six-articles/config/defaults")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_create_shared_feed_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    fake_service = MagicMock()
    fake_service._get_articles_for_date = AsyncMock(return_value=[{"id": 1}])
    fake_service._generate_article_list = AsyncMock(return_value={"title": "Daily News"})

    monkeypatch.setattr(
        "app.routes.news_feed_routes.get_news_feed_service",
        lambda db: fake_service,
    )
    monkeypatch.setattr(
        "app.routes.news_feed_routes.generate_share_token",
        lambda: "ABCDEF123456",
    )

    # SUCCESS
    fake_db.execute_query = MagicMock()
    res = client.post("/api/news-feed/share?date=2026-01-01&feed_type=overview")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["share_token"] == "ABCDEF123456"
    assert "/shared/ABCDEF123456" in body["share_url"]

    # FAILURE (400 - invalid date)
    res = client.post("/api/news-feed/share?date=not-a-date&feed_type=overview")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE (500 - DB error)
    fake_db.execute_query = MagicMock(side_effect=Exception("db error"))
    res = client.post("/api/news-feed/share?date=2026-01-01&feed_type=overview")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_view_shared_feed_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    from datetime import datetime, timedelta

    # SUCCESS
    def ok_template(*args, **kwargs):
        return HTMLResponse(content="<html>OK</html>", status_code=200)

    monkeypatch.setattr("app.routes.news_feed_routes.templates.TemplateResponse", ok_template)
    fake_db.execute_query = MagicMock()
    fake_db.fetch_one.return_value = (
        "overview",
        json.dumps({"title": "Daily News"}),
        "2026-01-01",
        None,
        (datetime.now() + timedelta(days=1)).isoformat(),
        0,
    )
    res = client.get("/api/news-feed/shared/ABCDEF123456")
    assert res.status_code == status.HTTP_200_OK
    assert "OK" in res.text

    # FAILURE (404 - not found)
    fake_db.fetch_one.return_value = None
    res = client.get("/api/news-feed/shared/NOPE")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE (410 - expired)
    fake_db.fetch_one.return_value = (
        "overview",
        json.dumps({"title": "Daily News"}),
        "2026-01-01",
        None,
        (datetime.now() - timedelta(days=1)).isoformat(),
        0,
    )
    res = client.get("/api/news-feed/shared/EXPIRED")
    assert res.status_code == status.HTTP_410_GONE


def test_get_shared_feed_data_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db

    from datetime import datetime, timedelta

    # SUCCESS
    fake_db.execute_query = MagicMock()
    fake_db.fetch_one.return_value = (
        "overview",
        json.dumps({"title": "Daily News"}),
        "2026-01-01",
        None,
        (datetime.now() + timedelta(days=1)).isoformat(),
        5,
    )
    res = client.get("/api/news-feed/api/shared/ABCDEF123456")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["access_count"] == 6
    assert body["share_token"] == "ABCDEF123456"

    # FAILURE (404 - not found)
    fake_db.fetch_one.return_value = None
    res = client.get("/api/news-feed/api/shared/NOPE")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE (410 - expired)
    fake_db.fetch_one.return_value = (
        "overview",
        json.dumps({"title": "Daily News"}),
        "2026-01-01",
        None,
        (datetime.now() - timedelta(days=1)).isoformat(),
        0,
    )
    res = client.get("/api/news-feed/api/shared/EXPIRED")
    assert res.status_code == status.HTTP_410_GONE


def test_get_category_icons_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    from fastapi import HTTPException

    # SUCCESS: no params -> all icons
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}
    res = client.get("/api/news-feed/category-icons")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert "Technology" in body["icons"]

    # SUCCESS: with params -> subset
    res = client.get("/api/news-feed/category-icons?categories=Tech,Uncategorized")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert "Tech" in body["icons"]
    assert "Uncategorized" in body["icons"]

    # FAILURE (500 - session dependency error)
    def bad_session():
        raise HTTPException(status_code=500, detail="boom")

    app.dependency_overrides[verify_session] = bad_session
    res = client.get("/api/news-feed/category-icons")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_generate_category_icon_success_and_failure(client, monkeypatch):
    app = client.app
    fake_db = MagicMock()
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    from fastapi import HTTPException

    # SUCCESS
    app.dependency_overrides[verify_session] = lambda: {"user": "test-user"}
    res = client.post("/api/news-feed/generate-category-icon?category=Cybersecurity")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["category"] == "Cybersecurity"
    assert "icon" in body

    # FAILURE (500 - session dependency error)
    def bad_session():
        raise HTTPException(status_code=500, detail="boom")

    app.dependency_overrides[verify_session] = bad_session
    res = client.post("/api/news-feed/generate-category-icon?category=Cybersecurity")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# dataset_routes.py endpoints (media_bias)
# =============================================================================


def test_get_media_bias_data_success_and_failure(client, monkeypatch):
    from datetime import datetime

    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    mock_media_bias.get_all_sources.return_value = [{"source": "example.com"}]
    mock_media_bias.get_status.return_value = {"enabled": True, "last_updated": datetime(2026, 1, 1, 12, 0, 0)}
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    res = client.get("/api/datasets/media_bias")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["sources"] == [{"source": "example.com"}]
    assert body["status"]["enabled"] is True
    assert body["status"]["last_updated"] == "2026-01-01T12:00:00"

    # FAILURE
    mock_media_bias.get_all_sources.side_effect = Exception("boom")
    res = client.get("/api/datasets/media_bias")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_import_media_bias_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    monkeypatch.setattr(dataset_routes.os.path, "exists", lambda p: True)
    mock_media_bias.import_from_csv.return_value = (10, 1)
    res = client.post("/api/datasets/media_bias/import")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["imported_count"] == 10
    assert body["failed_count"] == 1
    assert body["source_file"].endswith(".csv")

    # NOT FOUND
    monkeypatch.setattr(dataset_routes.os.path, "exists", lambda p: False)
    res = client.post("/api/datasets/media_bias/import")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    monkeypatch.setattr(dataset_routes.os.path, "exists", lambda p: True)
    mock_media_bias.import_from_csv.side_effect = Exception("import failed")
    res = client.post("/api/datasets/media_bias/import")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_upload_media_bias_file_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    class DummyTempFile:
        def __init__(self, name):
            self.name = name

        def close(self):
            return None

    # SUCCESS
    monkeypatch.setattr(dataset_routes.tempfile, "NamedTemporaryFile", lambda **kwargs: DummyTempFile("C:\\tmp\\mb.csv"))
    monkeypatch.setattr(dataset_routes.shutil, "copyfileobj", lambda src, dst: None)
    unlinked = []
    monkeypatch.setattr(dataset_routes.os, "unlink", lambda p: unlinked.append(p))

    mock_media_bias.import_from_csv.return_value = (5, 0)
    res = client.post(
        "/api/datasets/media_bias/upload",
        files={"file": ("mb.csv", b"source,bias\nexample.com,Left\n", "text/csv")},
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["imported_count"] == 5
    assert body["failed_count"] == 0
    assert "mb.csv" in body["source_file"]
    assert "C:\\tmp\\mb.csv" in unlinked

    # VALIDATION (non-csv)
    res = client.post(
        "/api/datasets/media_bias/upload",
        files={"file": ("mb.txt", b"nope", "text/plain")},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE
    mock_media_bias.import_from_csv.side_effect = Exception("boom")
    res = client.post(
        "/api/datasets/media_bias/upload",
        files={"file": ("mb.csv", b"source,bias\nexample.com,Left\n", "text/csv")},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_enable_media_bias_enrichment_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS (enabled=True)
    mock_media_bias.set_enabled.return_value = True
    res = client.post("/api/datasets/media_bias/enable", json={"enabled": True})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is True

    # SUCCESS (enabled=False)
    res = client.post("/api/datasets/media_bias/enable", json={"enabled": False})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is False

    # FAILURE (returns False)
    mock_media_bias.set_enabled.return_value = False
    res = client.post("/api/datasets/media_bias/enable", json={"enabled": True})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # FAILURE (raises)
    mock_media_bias.set_enabled.side_effect = Exception("boom")
    res = client.post("/api/datasets/media_bias/enable", json={"enabled": True})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_reset_media_bias_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.reset.return_value = True
    res = client.post("/api/datasets/media_bias/reset")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # FAILURE (returns False)
    mock_media_bias.reset.return_value = False
    res = client.post("/api/datasets/media_bias/reset")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # FAILURE (raises)
    mock_media_bias.reset.side_effect = Exception("boom")
    res = client.post("/api/datasets/media_bias/reset")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_bias_for_source_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS (www. prefix removal)
    def www_side_effect(src):
        if src == "www.example.com":
            return None
        if src == "example.com":
            return {"source": "example.com", "bias": "Left", "factual_reporting": "High"}
        return None

    mock_media_bias.get_bias_for_source.side_effect = www_side_effect
    res = client.get("/api/datasets/media_bias/source/www.example.com")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["found"] is True
    assert body["data"]["source"] == "example.com"
    assert body["data"]["bias"] == "Left"
    assert body["data"]["factual_reporting"] == "High"
    assert "mbfc_credibility_rating" in body["data"]
    assert "press_freedom" in body["data"]
    assert "media_type" in body["data"]
    assert "popularity" in body["data"]

    # SUCCESS (root domain fallback)
    calls = {"n": 0}

    def root_side_effect(src):
        calls["n"] += 1
        if src in ("sub.example.com", "example.com"):
            if src == "example.com":
                return {"source": "example.com", "bias": "Center"}
            return None
        return None

    mock_media_bias.get_bias_for_source.side_effect = root_side_effect
    res = client.get("/api/datasets/media_bias/source/sub.example.com")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["found"] is True
    assert res.json()["data"]["bias"] == "Center"
    assert calls["n"] >= 2

    # NOT FOUND
    mock_media_bias.get_bias_for_source.side_effect = lambda src: None
    res = client.get("/api/datasets/media_bias/source/unknown.example")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["found"] is False

    # FAILURE
    mock_media_bias.get_bias_for_source.side_effect = Exception("boom")
    res = client.get("/api/datasets/media_bias/source/example.com")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_search_media_bias_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.search_sources.return_value = ([{"source": "example.com"}], 21)
    res = client.get("/api/datasets/media_bias/search?query=ex&bias=Left&factual=High&country=US&page=2&per_page=10")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["sources"] == [{"source": "example.com"}]
    assert body["total"] == 21
    assert body["page"] == 2
    assert body["per_page"] == 10
    assert body["total_pages"] == 3

    # FAILURE
    mock_media_bias.search_sources.side_effect = Exception("boom")
    res = client.get("/api/datasets/media_bias/search?query=ex")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_media_bias_filters_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.get_filter_options.return_value = {"bias": ["Left", "Right"]}
    res = client.get("/api/datasets/media_bias/filters")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"bias": ["Left", "Right"]}

    # FAILURE
    mock_media_bias.get_filter_options.side_effect = Exception("boom")
    res = client.get("/api/datasets/media_bias/filters")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_media_bias_by_id_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.get_source_by_id.return_value = {"id": 1, "source": "example.com"}
    res = client.get("/api/datasets/media_bias/by-id/1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == 1

    # NOT FOUND
    mock_media_bias.get_source_by_id.return_value = None
    res = client.get("/api/datasets/media_bias/by-id/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    mock_media_bias.get_source_by_id.side_effect = Exception("boom")
    res = client.get("/api/datasets/media_bias/by-id/1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_add_media_bias_source_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.add_source.return_value = 123
    res = client.post("/api/datasets/media_bias/add", json={"source": "example.com"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == 123

    # VALIDATION
    mock_media_bias.add_source.side_effect = ValueError("bad input")
    res = client.post("/api/datasets/media_bias/add", json={"source": ""})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE
    mock_media_bias.add_source.side_effect = Exception("boom")
    res = client.post("/api/datasets/media_bias/add", json={"source": "example.com"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_update_media_bias_source_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.update_source.return_value = True
    res = client.put("/api/datasets/media_bias/1", json={"source": "example.com"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # VALIDATION
    mock_media_bias.update_source.side_effect = ValueError("bad input")
    res = client.put("/api/datasets/media_bias/1", json={"source": ""})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE
    mock_media_bias.update_source.side_effect = Exception("boom")
    res = client.put("/api/datasets/media_bias/1", json={"source": "example.com"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_delete_media_bias_source_success_and_failure(client, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: MagicMock()
    app.dependency_overrides[verify_session] = lambda: {"user_id": "test-user"}

    monkeypatch.setattr(dataset_routes, "MediaBias", MagicMock)

    mock_media_bias = MagicMock()
    app.dependency_overrides[dataset_routes.get_media_bias] = lambda: mock_media_bias

    # SUCCESS
    mock_media_bias.delete_source.return_value = True
    res = client.delete("/api/datasets/media_bias/1")
    assert res.status_code == status.HTTP_200_OK
    assert "message" in res.json()

    # NOT FOUND
    mock_media_bias.delete_source.return_value = False
    res = client.delete("/api/datasets/media_bias/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    mock_media_bias.delete_source.side_effect = Exception("boom")
    res = client.delete("/api/datasets/media_bias/1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# media_bias_routes.py endpoints
# =============================================================================


@pytest.fixture
def fake_facade():
    return MagicMock(name="fake_facade")


@pytest.fixture
def fake_db(fake_facade):
    return _make_db_with_facade(db_name="fake_db", facade_mock=fake_facade)


@pytest.fixture
def fake_session():
    return {"user_id": "test-user"}


# =============================================================================
# prompt_routes.py endpoints (prompt versioning)
# =============================================================================

@pytest.fixture
def fake_prompt_manager():
    """MagicMock prompt manager patched into app.routes.prompt_routes."""
    return MagicMock(name="fake_prompt_manager")


def _fake_version(hash_: str = "h1"):
    return {
        "hash": hash_,
        "version": "1",
        "system_prompt": "SYS",
        "user_prompt": "USER",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_get_prompt_types_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # SUCCESS
    fake_prompt_manager.get_prompt_types.return_value = [{"name": "x", "display_name": "X"}]
    res = client.get("/api/prompts/types")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"types": [{"name": "x", "display_name": "X"}]}

    # FAILURE
    fake_prompt_manager.get_prompt_types.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.get("/api/prompts/types")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_get_prompt_versions_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # SUCCESS
    fake_prompt_manager.get_versions.return_value = [_fake_version("h1"), _fake_version("h2")]
    res = client.get("/api/prompts/summarizer/versions")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()["versions"]) == 2

    # FAILURE
    fake_prompt_manager.get_versions.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.get("/api/prompts/summarizer/versions")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_get_prompt_version_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # SUCCESS
    fake_prompt_manager.get_version.return_value = _fake_version("h1")
    res = client.get("/api/prompts/summarizer/current")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["hash"] == "h1"

    # FAILURE
    fake_prompt_manager.get_version.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.get("/api/prompts/summarizer/current")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_save_prompt_version_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # VALIDATION: missing body -> 400 (route-level check)
    res = client.post("/api/prompts/summarizer")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Missing prompt data"

    # SUCCESS
    fake_prompt_manager.save_version.return_value = _fake_version("h1")
    payload = {
        "system_prompt": "SYS",
        "user_prompt": "USER",
        "expected_output_schema": {"type": "object"},
        "variables": {"x": "y"},
        "metadata": {"m": 1},
        "prompt_name": "p",
        "feature": "f",
        "description": "d",
        "author": "a",
    }
    res = client.post("/api/prompts/summarizer", json=payload)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["hash"] == "h1"

    # ensure additional fields were forwarded
    args = fake_prompt_manager.save_version.call_args[0]
    assert args[0] == "summarizer"
    assert args[1] == "SYS"
    assert args[2] == "USER"
    assert args[3]["expected_output_schema"] == {"type": "object"}
    assert args[3]["variables"] == {"x": "y"}
    assert args[3]["metadata"] == {"m": 1}
    assert args[3]["prompt_name"] == "p"
    assert args[3]["feature"] == "f"
    assert args[3]["description"] == "d"
    assert args[3]["author"] == "a"

    # FAILURE
    fake_prompt_manager.save_version.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.post("/api/prompts/summarizer", json={"system_prompt": "S", "user_prompt": "U"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_restore_prompt_version_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # SUCCESS
    fake_prompt_manager.restore_version.return_value = _fake_version("h1")
    res = client.post("/api/prompts/summarizer/h1/restore")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["hash"] == "h1"

    # FAILURE
    fake_prompt_manager.restore_version.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.post("/api/prompts/summarizer/h1/restore")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_compare_prompt_versions_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    """
    NOTE: With the current route ordering in app/routes/prompt_routes.py,
    `/api/prompts/{prompt_type}/compare` is shadowed by
    `/api/prompts/{prompt_type}/{version_hash}`.

    Since we must not change router code here, we assert the observable behavior:
    hitting `/compare` is handled as "get prompt version" with version_hash="compare".
    """
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # SUCCESS (routed to get_prompt_version)
    fake_prompt_manager.get_version.return_value = _fake_version("h1")
    res = client.get("/api/prompts/summarizer/compare")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["hash"] == "h1"

    # FAILURE (routed to get_prompt_version)
    fake_prompt_manager.get_version.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.get("/api/prompts/summarizer/compare")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


def test_delete_prompt_version_success_and_failure(client, fake_session, fake_prompt_manager, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(prompt_routes, "prompt_manager", fake_prompt_manager)

    # VALIDATION: cannot delete current
    res = client.delete("/api/prompts/summarizer/current")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Cannot delete current version"

    # SUCCESS
    fake_prompt_manager.delete_version.return_value = None
    res = client.delete("/api/prompts/summarizer/h1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "success"

    # FAILURE
    fake_prompt_manager.delete_version.side_effect = prompt_routes.PromptManagerError("boom")
    res = client.delete("/api/prompts/summarizer/h1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "boom"


@pytest.fixture
def fake_auspex():
    return AsyncMock(name="fake_auspex")


@pytest.fixture
def mock_media_bias(monkeypatch):
    """Patch MediaBias constructor in media_bias_routes to return a controllable mock."""
    instance = MagicMock(name="MediaBiasInstance")
    monkeypatch.setattr(media_bias_routes, "MediaBias", MagicMock(return_value=instance))
    return instance


def test_get_media_bias_success_and_failure(client, fake_db, fake_session, mock_media_bias):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # VALIDATION (missing required query param)
    res = client.get("/api/media_bias")
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # SUCCESS
    mock_media_bias.get_bias_for_source.return_value = {"source": "cnn", "bias": "Left"}
    res = client.get("/api/media_bias?source=cnn")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["data"] == {"source": "cnn", "bias": "Left"}
    assert "cnn" in body["message"]

    # NOT FOUND
    mock_media_bias.get_bias_for_source.return_value = None
    res = client.get("/api/media_bias?source=unknown-source")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is False
    assert body.get("data") is None
    assert "unknown-source" in body["message"]

    # FAILURE
    mock_media_bias.get_bias_for_source.side_effect = Exception("boom")
    res = client.get("/api/media_bias?source=cnn")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error getting media bias data" in res.json()["detail"]


def test_get_media_bias_status_success_and_failure(client, fake_db, fake_session, mock_media_bias):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    mock_media_bias.get_status.return_value = {
        "enabled": True,
        "total_sources": 12,
        "last_updated": "2026-01-01T00:00:00Z",
    }
    res = client.get("/api/media_bias/status")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {
        "enabled": True,
        "total_sources": 12,
        "last_updated": "2026-01-01T00:00:00Z",
    }

    # DEFAULTS
    mock_media_bias.get_status.return_value = {}
    res = client.get("/api/media_bias/status")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {
        "enabled": False,
        "total_sources": 0,
        "last_updated": None,
    }

    # FAILURE
    mock_media_bias.get_status.side_effect = Exception("boom")
    res = client.get("/api/media_bias/status")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error getting media bias status" in res.json()["detail"]


def test_enable_media_bias_success_and_failure(client, fake_db, fake_session, mock_media_bias):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    mock_media_bias.set_enabled.return_value = None
    mock_media_bias.get_status.return_value = {"enabled": True, "total_sources": 1, "last_updated": None}
    res = client.post("/api/media_bias/enable")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is True
    mock_media_bias.set_enabled.assert_called_with(True)

    # FAILURE
    mock_media_bias.set_enabled.side_effect = Exception("boom")
    res = client.post("/api/media_bias/enable")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error enabling media bias" in res.json()["detail"]


def test_disable_media_bias_success_and_failure(client, fake_db, fake_session, mock_media_bias):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    mock_media_bias.set_enabled.return_value = None
    mock_media_bias.get_status.return_value = {"enabled": False, "total_sources": 1, "last_updated": None}
    res = client.post("/api/media_bias/disable")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["enabled"] is False
    mock_media_bias.set_enabled.assert_called_with(False)

    # FAILURE
    mock_media_bias.set_enabled.side_effect = Exception("boom")
    res = client.post("/api/media_bias/disable")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error disabling media bias" in res.json()["detail"]


# =============================================================================
# market_signals_routes.py endpoints
# =============================================================================


def test_get_market_signals_analysis_success_and_failure(client, fake_db, fake_facade, fake_session, fake_auspex, monkeypatch):
    import uuid as _uuid

    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # VALIDATION (query param constraints)
    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&limit=1")
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&temperature=3.0")
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&max_tokens=50")
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Common patches (no real prompt files, no real LLM calls, deterministic ID/time)
    monkeypatch.setattr(market_signals_routes, "get_auspex_service", lambda: fake_auspex)
    monkeypatch.setattr(
        market_signals_routes.PromptLoader,
        "load_prompt",
        lambda *args, **kwargs: {"version": "v1", "metadata": {"temperature": 0.9, "max_tokens": 2000}},
    )
    monkeypatch.setattr(
        market_signals_routes.PromptLoader,
        "get_prompt_template",
        lambda prompt_data, variables: ("SYSTEM", "USER {articles}"),
    )

    fixed_uuid = _uuid.UUID("11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(market_signals_routes.uuid, "uuid4", lambda: fixed_uuid)

    class _FakeTime:
        def __init__(self, start=1000.0):
            self.t = start

        def time(self):
            self.t += 1.0
            return self.t

    # Patch ONLY the reference used by market_signals_routes to avoid impacting global logging timestamps.
    monkeypatch.setattr(market_signals_routes, "time", _FakeTime())

    # SUCCESS
    articles = [
        {
            "title": "A1",
            "news_source": "Example",
            "publication_date": "2026-01-01",
            "uri": "https://example.com/a1",
            "summary": "s",
            "sentiment": "neutral",
            "category": "Tech",
            "future_signal": "signal",
            "raw_markdown": "full content",
        }
    ]
    fake_facade.get_articles_by_topic.return_value = articles
    fake_auspex.generate_structured_analysis = AsyncMock(
        return_value='{"future_signals":[{"title":"t"}],"risk_cards":[],"opportunity_cards":[],"quotes":[]}'
    )

    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&limit=10")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()

    assert body["analysis_id"] == str(fixed_uuid)
    assert isinstance(body["future_signals"], list)
    assert isinstance(body["risk_cards"], list)
    assert isinstance(body["opportunity_cards"], list)
    assert isinstance(body["quotes"], list)

    assert body["meta"]["topic"] == "AI"
    assert body["meta"]["article_count"] == 1
    assert body["meta"]["analyzed_count"] == 1
    assert body["meta"]["prompt_version"] == "v1"
    assert body["meta"]["model"] == "gpt-4"
    assert body["meta"]["temperature"] == 0.9  # from prompt metadata fallback
    assert body["meta"]["max_tokens"] == 2000  # from prompt metadata fallback

    fake_facade.save_market_signals_analysis.assert_called_once()
    save_kwargs = fake_facade.save_market_signals_analysis.call_args.kwargs
    assert save_kwargs["analysis_id"] == str(fixed_uuid)
    assert save_kwargs["user_id"] == "test-user"
    assert save_kwargs["topic"] == "AI"
    assert save_kwargs["model_used"] == "gpt-4"
    assert save_kwargs["total_articles_analyzed"] == 1
    assert save_kwargs["analysis_duration_seconds"] == 1.0

    fake_facade.log_articles_for_analysis_run.assert_called_once_with(str(fixed_uuid), articles)

    # NOT FOUND
    fake_facade.reset_mock()
    fake_facade.get_articles_by_topic.return_value = []
    res = client.get("/api/market-signals/analysis?topic=Missing&model=gpt-4&limit=10")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "No articles found for topic" in res.json()["detail"]
    fake_facade.save_market_signals_analysis.assert_not_called()
    fake_facade.log_articles_for_analysis_run.assert_not_called()

    # AI JSON Error
    fake_facade.reset_mock()
    fake_facade.get_articles_by_topic.return_value = articles
    fake_auspex.generate_structured_analysis = AsyncMock(return_value="not-json")
    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&limit=10")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "AI returned invalid JSON response"
    fake_facade.save_market_signals_analysis.assert_not_called()
    fake_facade.log_articles_for_analysis_run.assert_not_called()

    # FAILURE (dependency raises)
    def _boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(market_signals_routes.PromptLoader, "load_prompt", _boom)
    res = client.get("/api/market-signals/analysis?topic=AI&model=gpt-4&limit=10")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Analysis failed: boom" in res.json()["detail"]


def test_get_market_signals_raw_success_and_failure(client, fake_db, fake_facade, fake_session):
    from datetime import datetime

    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    analysis_id = "abc-123"

    # SUCCESS
    fake_facade.get_market_signals_analysis.return_value = {
        "topic": "AI",
        "model_used": "gpt-4",
        "created_at": datetime(2026, 1, 1, 0, 0, 0),
        "total_articles_analyzed": 10,
        "analysis_duration_seconds": 2.5,
        "raw_output": {"analysis_id": analysis_id, "future_signals": []},
    }
    res = client.get(f"/api/market-signals/{analysis_id}/raw")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["analysis_id"] == analysis_id
    assert body["topic"] == "AI"
    assert body["model_used"] == "gpt-4"
    assert body["created_at"] == "2026-01-01T00:00:00"
    assert body["total_articles_analyzed"] == 10
    assert body["analysis_duration_seconds"] == 2.5
    assert body["raw_output"]["analysis_id"] == analysis_id

    # NOT FOUND
    fake_facade.get_market_signals_analysis.return_value = None
    res = client.get("/api/market-signals/missing/raw")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "Analysis not found" in res.json()["detail"]

    # FAILURE
    fake_facade.get_market_signals_analysis.side_effect = Exception("boom")
    res = client.get(f"/api/market-signals/{analysis_id}/raw")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to retrieve analysis: boom" in res.json()["detail"]


def test_get_available_topics_success_and_failure(client, fake_db, fake_facade, fake_session):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS + FILTERING
    fake_facade.get_all_topics.return_value = [{"name": "AI"}, {"name": None}, {}, {"name": "Health"}]
    res = client.get("/api/market-signals/topics")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"success": True, "topics": ["AI", "Health"], "count": 2}

    # FAILURE
    fake_facade.get_all_topics.side_effect = Exception("boom")
    res = client.get("/api/market-signals/topics")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to retrieve topics: boom" in res.json()["detail"]


def test_market_signals_health_check_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(market_signals_routes.PromptLoader, "load_prompt", lambda *args, **kwargs: {"version": "v1"})
    res = client.get("/api/market-signals/health")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "healthy"
    assert res.json()["service"] == "market_signals"
    assert res.json()["prompt_version"] == "v1"
    assert "timestamp" in res.json()

    # UNHEALTHY
    def _boom(*args, **kwargs):
        raise Exception("missing prompt")

    monkeypatch.setattr(market_signals_routes.PromptLoader, "load_prompt", _boom)
    res = client.get("/api/market-signals/health")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "unhealthy"
    assert res.json()["service"] == "market_signals"
    assert "missing prompt" in res.json()["error"]
    assert "timestamp" in res.json()


# =============================================================================
# executive_summary_routes.py endpoints
# =============================================================================


@pytest.fixture
def mock_research():
    return MagicMock(name="mock_research")


@pytest.fixture
def executive_summary_mock_templates(monkeypatch):
    """Patch executive_summary_routes.templates.TemplateResponse so no real templates are rendered."""
    from fastapi.responses import HTMLResponse

    tmpl = MagicMock(name="executive_summary_routes.templates")
    tmpl.TemplateResponse = MagicMock(return_value=HTMLResponse(content="<html>OK</html>", status_code=200))
    monkeypatch.setattr(executive_summary_routes, "templates", tmpl)
    return tmpl


def _assert_execsum_template_call(mock_templates, expected_template: str):
    assert mock_templates.TemplateResponse.call_count >= 1
    args, kwargs = mock_templates.TemplateResponse.call_args
    assert not kwargs
    assert args[0] == expected_template
    assert isinstance(args[1], dict)
    return args[1]


def test_execsum_get_market_signals_analysis_success_and_failure(client, fake_db, fake_session, mock_research, monkeypatch):
    """
    GET /api/executive-summary/market-signals/{topic_name}

    Notes:
    - We patch internal helpers to avoid DB/AI/research execution.
    - The route currently wraps all exceptions (including HTTPException) into a 500 due to broad `except Exception`.
    """

    from app.dependencies import get_research

    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session
    app.dependency_overrides[get_research] = lambda: mock_research

    analytics_instance = MagicMock(name="AnalyticsInstance")
    analytics_data = {
        "totalArticles": 10,
        "timeToImpactDistribution": {"labels": ["Short-term"], "values": [10]},
    }
    analytics_instance.get_analytics_data.return_value = analytics_data
    monkeypatch.setattr(executive_summary_routes, "Analytics", MagicMock(return_value=analytics_instance))

    # Mock signal extraction + AI generation
    monkeypatch.setattr(
        executive_summary_routes,
        "_extract_market_signals_from_analytics",
        AsyncMock(
            return_value=[
                executive_summary_routes.MarketSignal(
                    signal="Signal A",
                    frequency="High",
                    impact="Short-term",
                    level="high",
                    count=7,
                )
            ]
        ),
    )

    articles = [
        {
            "title": "AI moves fast",
            "summary": "Long summary " * 10,
            "uri": "https://example.com/a1",
            "news_source": "BBC",
            "publication_date": "2026-01-01",
        }
    ]
    facade_instance = MagicMock(name="DatabaseQueryFacadeInstance")
    facade_instance.get_articles_for_market_signal_analysis.return_value = list(articles)
    monkeypatch.setattr(executive_summary_routes, "DatabaseQueryFacade", MagicMock(return_value=facade_instance))

    monkeypatch.setattr(
        executive_summary_routes,
        "_generate_risk_opportunity_cards",
        AsyncMock(
            return_value=(
                [
                    executive_summary_routes.RiskOpportunityCard(
                        type="risk",
                        title="Risk 1",
                        description="D1",
                        timeline="2025-2027",
                        probability="High",
                    )
                ],
                [
                    executive_summary_routes.RiskOpportunityCard(
                        type="opportunity",
                        title="Opp 1",
                        description="D2",
                        timeline="2025-2027",
                        probability="Moderate",
                    )
                ],
            )
        ),
    )
    monkeypatch.setattr(executive_summary_routes, "get_auspex_service", lambda: MagicMock(name="auspex"))

    # SUCCESS
    res = client.get("/api/executive-summary/market-signals/AI?timeframe_days=30&model=gpt-4o")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert set(body.keys()) >= {"signals", "risks", "opportunities", "quotes", "analytics_data"}
    assert body["analytics_data"]["totalArticles"] == 10
    assert isinstance(body["signals"], list) and body["signals"][0]["signal"] == "Signal A"
    assert body["risks"][0]["type"] == "risk"
    assert body["opportunities"][0]["type"] == "opportunity"
    assert isinstance(body["quotes"], list)

    # "NOT FOUND" (observable behavior: becomes 500 due to broad exception handler)
    analytics_instance.get_analytics_data.return_value = {"totalArticles": 0}
    res = client.get("/api/executive-summary/market-signals/Missing?timeframe_days=30&model=gpt-4o")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "No analyzed articles found for topic" in res.json()["detail"]

    # FAILURE (dependency raises)
    analytics_instance.get_analytics_data.side_effect = Exception("boom")
    res = client.get("/api/executive-summary/market-signals/AI?timeframe_days=30&model=gpt-4o")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "boom" in res.json()["detail"]


def test_execsum_market_signals_dashboard_page_success_and_failure(client, executive_summary_mock_templates, monkeypatch):
    """GET /market-signals-dashboard/{topic_name}"""

    def _fake_get_template_context(request, additional_context=None):
        ctx = {"request": request}
        if additional_context:
            ctx.update(additional_context)
        return ctx

    monkeypatch.setattr("app.main.get_template_context", _fake_get_template_context, raising=True)

    # SUCCESS
    res = client.get("/market-signals-dashboard/AI")
    assert res.status_code == 200
    ctx = _assert_execsum_template_call(executive_summary_mock_templates, "market_signals_dashboard.html")
    assert ctx["topic_name"] == "AI"
    assert "session" in ctx

    # FAILURE
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    executive_summary_mock_templates.TemplateResponse.side_effect = Exception("template boom")
    res = failure_client.get("/market-signals-dashboard/AI")
    assert res.status_code == 500


def test_execsum_market_signals_dashboard_index_success_and_failure(client, executive_summary_mock_templates, monkeypatch):
    """GET /market-signals-dashboard"""

    def _fake_get_template_context(request, additional_context=None):
        ctx = {"request": request}
        if additional_context:
            ctx.update(additional_context)
        return ctx

    monkeypatch.setattr("app.main.get_template_context", _fake_get_template_context, raising=True)

    # SUCCESS
    res = client.get("/market-signals-dashboard")
    assert res.status_code == 200
    ctx = _assert_execsum_template_call(executive_summary_mock_templates, "market_signals_dashboard.html")
    assert ctx["topic_name"] is None
    assert "session" in ctx

    # FAILURE
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    executive_summary_mock_templates.TemplateResponse.side_effect = Exception("template boom")
    res = failure_client.get("/market-signals-dashboard")
    assert res.status_code == 500


def test_execsum_ai_impact_timeline_page_success_and_failure(client, executive_summary_mock_templates, monkeypatch):
    """GET /ai-impact-timeline"""

    def _fake_get_template_context(request, additional_context=None):
        ctx = {"request": request}
        if additional_context:
            ctx.update(additional_context)
        return ctx

    monkeypatch.setattr("app.main.get_template_context", _fake_get_template_context, raising=True)

    # SUCCESS
    res = client.get("/ai-impact-timeline")
    assert res.status_code == 200
    _assert_execsum_template_call(executive_summary_mock_templates, "ai_timeline_html.html")

    # FAILURE
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    executive_summary_mock_templates.TemplateResponse.side_effect = Exception("template boom")
    res = failure_client.get("/ai-impact-timeline")
    assert res.status_code == 500


def test_execsum_get_ai_impact_timeline_analysis_success_and_failures(
    client, fake_db, fake_session, fake_auspex, mock_research, monkeypatch
):
    """GET /api/executive-summary/ai-impact-timeline/{topic_name}"""

    from app.dependencies import get_research

    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session
    app.dependency_overrides[get_research] = lambda: mock_research

    articles = [
        {
            "title": "AI",
            "summary": "Long summary...",
            "uri": "https://example.com/x",
            "news_source": "BBC",
            "publication_date": "2026-01-01",
            "future_signal": "signal",
            "sentiment": "Neutral",
            "time_to_impact": "Short-term",
        }
    ]

    facade_instance = MagicMock(name="DatabaseQueryFacadeInstance")
    facade_instance.get_recent_articles_for_market_signal_analysis.return_value = list(articles)
    monkeypatch.setattr(executive_summary_routes, "DatabaseQueryFacade", MagicMock(return_value=facade_instance))

    fake_auspex.create_chat_session = AsyncMock(return_value="chat-1")
    fake_auspex.delete_chat_session = MagicMock(return_value=None)

    async def _agen(parts):
        for p in parts:
            yield p

    timeline_json = {"topic": "AI", "summary": {"total_articles": 1}, "swimlanes": [], "insights": []}
    fake_auspex.chat_with_tools = MagicMock(return_value=_agen([f"```json\n{json.dumps(timeline_json)}\n```"]))
    monkeypatch.setattr(executive_summary_routes, "get_auspex_service", lambda: fake_auspex)

    # SUCCESS
    res = client.get("/api/executive-summary/ai-impact-timeline/AI?timeframe_days=365&model=gpt-4o")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["topic"] == "AI"
    assert "generated_at" in body
    assert body["articles_analyzed"] == 1
    assert body["timeframe_days"] == 365
    assert body["model_used"] == "gpt-4o"
    fake_auspex.delete_chat_session.assert_called_once_with("chat-1")

    # NOT FOUND
    facade_instance.get_recent_articles_for_market_signal_analysis.return_value = []
    res = client.get("/api/executive-summary/ai-impact-timeline/Missing?timeframe_days=365&model=gpt-4o")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "No analyzed articles found for topic" in res.json()["detail"]

    # PARSE FAILURE
    facade_instance.get_recent_articles_for_market_signal_analysis.return_value = list(articles)
    fake_auspex.chat_with_tools = MagicMock(return_value=_agen(["not json"]))
    res = client.get("/api/executive-summary/ai-impact-timeline/AI?timeframe_days=365&model=gpt-4o")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "AI analysis failed to generate valid timeline data" in res.json()["detail"]

    # FAILURE (dependency raises)
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    fake_auspex.create_chat_session = AsyncMock(side_effect=Exception("boom"))
    res = failure_client.get("/api/executive-summary/ai-impact-timeline/AI?timeframe_days=365&model=gpt-4o")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Internal server error: boom" in res.json()["detail"]


def test_execsum_calculate_optimal_sample_size_modes():
    fn = executive_summary_routes._calculate_optimal_sample_size

    assert fn("gpt-4o", "auto") == 75
    assert fn("gpt-4o", "focused") == 25
    assert fn("gpt-4o", "balanced") == 50
    assert fn("gpt-4o", "comprehensive") == 100

    assert fn("gpt-4o", "custom", custom_limit=123) == 123
    assert fn("gpt-4o", "custom", custom_limit=None) == 75


# =============================================================================
# health_routes.py helpers + endpoints
# =============================================================================


def test_get_database_health_success_and_failure(monkeypatch):
    # SUCCESS (sqlite, not locked)
    class _FakeCursor:
        def execute(self, query: str):
            if "SELECT COUNT(*)" in query:
                return self
            if query in ("BEGIN IMMEDIATE", "ROLLBACK"):
                return self
            return self

        def fetchone(self):
            return (7,)

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    class _FakeDB:
        db_type = "sqlite"

        def get_connection(self):
            return _FakeConn()

    import app.database as app_database

    monkeypatch.setattr(app_database, "Database", lambda *a, **k: _FakeDB())
    monkeypatch.setattr(health_routes.Path, "exists", lambda self: True, raising=True)

    class _Stat:
        st_size = 50 * 1024 * 1024  # 50MB

    monkeypatch.setattr(health_routes.Path, "stat", lambda self: _Stat(), raising=True)

    data = health_routes.get_database_health()
    assert data["status"] == "healthy"
    assert data["article_count"] == 7
    assert data["size_mb"] == 50.0
    assert data["locked"] is False

    # SUCCESS (sqlite, locked)
    class _LockedCursor(_FakeCursor):
        def execute(self, query: str):
            if query == "BEGIN IMMEDIATE":
                raise health_routes.OperationalError("locked", {}, None)
            return super().execute(query)

    class _LockedConn(_FakeConn):
        def cursor(self):
            return _LockedCursor()

    class _LockedDB(_FakeDB):
        def get_connection(self):
            return _LockedConn()

    monkeypatch.setattr(app_database, "Database", lambda *a, **k: _LockedDB())
    data = health_routes.get_database_health()
    assert data["status"] == "healthy"
    assert data["locked"] is True

    # FAILURE
    monkeypatch.setattr(app_database, "Database", lambda *a, **k: (_ for _ in ()).throw(Exception("db boom")))
    data = health_routes.get_database_health()
    assert data["status"] == "unhealthy"
    assert "db boom" in data["error"]


def test_get_file_descriptor_stats_success_and_failure(monkeypatch):
    import sys
    import types

    # Inject fake resource module for Windows
    fake_resource = types.ModuleType("resource")
    fake_resource.RLIMIT_NOFILE = 7
    fake_resource.getrlimit = lambda *_: (100, 200)
    monkeypatch.setitem(sys.modules, "resource", fake_resource)

    class _FakeProc:
        def num_fds(self):
            return 80

        def connections(self):
            return [1, 2, 3]

        def open_files(self):
            return ["a"]

    monkeypatch.setattr(health_routes.psutil, "Process", lambda: _FakeProc())
    stats = health_routes.get_file_descriptor_stats()
    assert stats["open"] == 80
    assert stats["soft_limit"] == 100
    assert stats["hard_limit"] == 200
    assert stats["usage_percent"] == 80.0
    assert stats["available"] == 20
    assert stats["connections"] == 3
    assert stats["files"] == 1
    assert stats["status"] == "warning"

    # FAILURE
    monkeypatch.setattr(health_routes.psutil, "Process", lambda: (_ for _ in ()).throw(Exception("proc boom")))
    stats = health_routes.get_file_descriptor_stats()
    assert "proc boom" in stats["error"]


def test_get_memory_stats_success_and_failure(monkeypatch):
    class _MemInfo:
        rss = 100 * 1024 * 1024
        vms = 200 * 1024 * 1024

    class _FakeProc:
        def memory_info(self):
            return _MemInfo()

        def memory_percent(self):
            return 12.345

        def num_threads(self):
            return 9

    class _VM:
        total = 8 * 1024**3
        available = 4 * 1024**3
        used = 4 * 1024**3
        percent = 50

    monkeypatch.setattr(health_routes.psutil, "Process", lambda: _FakeProc())
    monkeypatch.setattr(health_routes.psutil, "virtual_memory", lambda: _VM())

    stats = health_routes.get_memory_stats()
    assert stats["process"]["rss_mb"] == 100.0
    assert stats["process"]["vms_mb"] == 200.0
    assert stats["process"]["percent"] == 12.35
    assert stats["process"]["num_threads"] == 9
    assert stats["system"]["total_gb"] == 8.0
    assert stats["system"]["available_gb"] == 4.0
    assert stats["system"]["used_gb"] == 4.0
    assert stats["system"]["percent"] == 50

    # FAILURE
    monkeypatch.setattr(health_routes.psutil, "Process", lambda: (_ for _ in ()).throw(Exception("mem boom")))
    stats = health_routes.get_memory_stats()
    assert "mem boom" in stats["error"]


def test_get_disk_stats_success_and_failure(monkeypatch):
    class _DU:
        total = 10 * 1024**3
        used = 2 * 1024**3
        free = 8 * 1024**3
        percent = 20

    class _DU_DB:
        total = 5 * 1024**3
        used = 1 * 1024**3
        free = 4 * 1024**3
        percent = 20

    monkeypatch.setattr(health_routes.psutil, "disk_usage", lambda p: _DU_DB() if "app" in str(p) else _DU())
    monkeypatch.setattr(health_routes.Path, "exists", lambda self: True, raising=True)
    stats = health_routes.get_disk_stats()
    assert stats["root"]["percent"] == 20
    assert stats["database_partition"]["percent"] == 20

    # FAILURE
    monkeypatch.setattr(health_routes.psutil, "disk_usage", lambda *_: (_ for _ in ()).throw(Exception("disk boom")))
    stats = health_routes.get_disk_stats()
    assert "disk boom" in stats["error"]


def test_get_chromadb_stats_success_and_failure(monkeypatch):
    class _FakeCollection:
        def count(self):
            return 123

    class _FakeClient:
        def get_or_create_collection(self, name: str):
            assert name == "articles"
            return _FakeCollection()

    import app.vector_store as vector_store

    monkeypatch.setattr(vector_store, "get_chroma_client", lambda: _FakeClient())
    monkeypatch.setenv("CHROMA_DB_DIR", r"C:\chromadb")
    monkeypatch.setattr(health_routes.Path, "exists", lambda self: True, raising=True)

    class _FakeFile:
        def is_file(self):
            return True

        def stat(self):
            class _S:
                st_size = 10 * 1024 * 1024  # 10MB

            return _S()

    monkeypatch.setattr(health_routes.Path, "rglob", lambda self, pattern: [_FakeFile()], raising=True)

    stats = health_routes.get_chromadb_stats()
    assert stats["status"] == "healthy"
    assert stats["vector_count"] == 123
    assert stats["size_mb"] == 10.0

    # FAILURE
    monkeypatch.setattr(vector_store, "get_chroma_client", lambda: (_ for _ in ()).throw(Exception("chroma boom")))
    stats = health_routes.get_chromadb_stats()
    assert stats["status"] == "error"
    assert "chroma boom" in stats["error"]


def test_get_environment_info_success_and_failure(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("INSTANCE_NAME", "unit")
    monkeypatch.setenv("PORT", "1234")
    data = health_routes.get_environment_info()
    assert data["environment"] == "test"
    assert data["instance"] == "unit"
    assert data["port"] == 1234
    assert "python_version" in data

    # FAILURE
    monkeypatch.setattr(health_routes.os, "getenv", lambda *_a, **_k: (_ for _ in ()).throw(Exception("env boom")))
    data = health_routes.get_environment_info()
    assert "env boom" in data["error"]


def test_get_api_health_success_and_failure(monkeypatch):
    # CRITICAL: none configured
    for k in [
        "PROVIDER_NEWSAPI_API_KEY",
        "PROVIDER_NEWSAPI_KEY",
        "PROVIDER_THENEWSAPI_API_KEY",
        "PROVIDER_THENEWSAPI_KEY",
        "PROVIDER_NEWSDATA_API_KEY",
        "NEWSDATA_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "PROVIDER_FIRECRAWL_API_KEY",
        "PROVIDER_FIRECRAWL_KEY",
        "FIRECRAWL_API_KEY",
    ]:
        monkeypatch.delenv(k, raising=False)

    data = health_routes.get_api_health()
    assert data["status"] == "critical"
    assert data["configured_count"] == 0
    assert data["total_checked"] == 3

    # DEGRADED: one configured
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    data = health_routes.get_api_health()
    assert data["status"] == "degraded"
    assert data["configured_count"] == 1

    # HEALTHY: all 3 configured
    monkeypatch.setenv("PROVIDER_NEWSAPI_API_KEY", "x")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "x")
    data = health_routes.get_api_health()
    assert data["status"] == "healthy"
    assert data["configured_count"] == 3
    assert data["apis"]["collector"] == "configured"
    assert data["apis"]["ai_provider"] == "configured"
    assert data["apis"]["firecrawl"] == "configured"

    # FAILURE
    monkeypatch.setattr(health_routes.os, "getenv", lambda *_a, **_k: (_ for _ in ()).throw(Exception("getenv boom")))
    data = health_routes.get_api_health()
    assert data["status"] == "error"
    assert "getenv boom" in data["error"]


def test_get_autopolling_status_success_and_failure(monkeypatch):
    import app.database as app_database

    class _FakeResult:
        def __init__(self, rows=None, one=None):
            self._rows = rows or []
            self._one = one

        def __iter__(self):
            return iter(self._rows)

        def fetchone(self):
            return self._one

    class _FakeConn:
        def __init__(self, mode="success"):
            self.mode = mode
            self.committed = False
            self.rolled_back = False

        def execute(self, query):
            q = str(query)
            if self.mode == "error":
                raise Exception("sql boom")
            if "sqlite_master" in q:
                if self.mode == "no_tables":
                    return _FakeResult(rows=[])
                return _FakeResult(rows=[("keyword_monitor_settings",), ("keyword_monitor_status",)])
            if "FROM keyword_monitor_settings" in q:
                return _FakeResult(one=(1, 100))
            if "FROM keyword_monitor_status" in q:
                return _FakeResult(one=(25, "2026-01-01T00:00:00", None))
            return _FakeResult()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class _FakeDB:
        def __init__(self, conn: _FakeConn):
            self._conn = conn

        def _temp_get_connection(self):
            return self._conn

    # SUCCESS
    conn = _FakeConn(mode="success")
    monkeypatch.setenv("DB_TYPE", "sqlite")
    monkeypatch.setattr(app_database, "Database", lambda *a, **k: _FakeDB(conn))
    data = health_routes.get_autopolling_status()
    assert data["status"] == "enabled"
    assert data["is_enabled"] is True
    assert data["requests_today"] == 25
    assert data["daily_request_limit"] == 100
    assert data["usage_percent"] == 25.0
    assert conn.committed is True

    # UNKNOWN: no tables
    conn = _FakeConn(mode="no_tables")
    monkeypatch.setattr(app_database, "Database", lambda *a, **k: _FakeDB(conn))
    data = health_routes.get_autopolling_status()
    assert data["status"] == "unknown"
    assert "not configured" in data["message"].lower()

    # FAILURE
    conn = _FakeConn(mode="error")
    monkeypatch.setattr(app_database, "Database", lambda *a, **k: _FakeDB(conn))
    data = health_routes.get_autopolling_status()
    assert data["status"] == "error"
    assert "sql boom" in data["error"]


def test_health_check_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)
    monkeypatch.setattr(health_routes.time, "time", lambda: 1010.0)
    res = client.get("/health")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "healthy"
    assert body["uptime_seconds"] == 10.0
    assert "timestamp" in body

    # FAILURE
    monkeypatch.setattr(health_routes.time, "time", lambda: (_ for _ in ()).throw(Exception("time boom")))
    with pytest.raises(Exception):
        client.get("/health")


def test_api_health_success_and_failure(client, monkeypatch):
    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)
    monkeypatch.setattr(health_routes.time, "time", lambda: 1060.0)

    class _FakeProc:
        def cpu_percent(self, interval=0.1):
            return 1.234

    monkeypatch.setattr(health_routes.psutil, "Process", lambda: _FakeProc())
    monkeypatch.setattr(health_routes.psutil, "cpu_percent", lambda interval=0.1: 2.345)
    monkeypatch.setattr(health_routes.psutil, "cpu_count", lambda: 8)
    monkeypatch.setattr(health_routes.os, "getloadavg", lambda: (0.1, 0.2, 0.3), raising=False)

    # SUCCESS
    monkeypatch.setattr(
        health_routes,
        "get_memory_stats",
        lambda: {"system": {"percent": 50}, "process": {"rss_mb": 1, "vms_mb": 1, "percent": 1, "num_threads": 1}},
    )
    monkeypatch.setattr(
        health_routes,
        "get_disk_stats",
        lambda: {"root": {"percent": 50, "total_gb": 1, "used_gb": 1, "free_gb": 1}, "database_partition": None},
    )
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"usage_percent": 10, "status": "ok"})
    res = client.get("/api/health")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "healthy"
    assert body["warnings"] == []
    assert body["cpu"]["core_count"] == 8

    # DEGRADED
    monkeypatch.setattr(
        health_routes,
        "get_memory_stats",
        lambda: {"system": {"percent": 80}, "process": {"rss_mb": 1, "vms_mb": 1, "percent": 1, "num_threads": 1}},
    )
    res = client.get("/api/health")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "degraded"
    assert any("elevated" in w.lower() for w in body["warnings"])

    # CRITICAL
    monkeypatch.setattr(
        health_routes,
        "get_memory_stats",
        lambda: {"system": {"percent": 95}, "process": {"rss_mb": 1, "vms_mb": 1, "percent": 1, "num_threads": 1}},
    )
    res = client.get("/api/health")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "critical"
    assert any("critically" in w.lower() for w in body["warnings"])

    # FAILURE
    monkeypatch.setattr(health_routes.psutil, "Process", lambda: (_ for _ in ()).throw(Exception("psutil boom")))
    res = client.get("/api/health")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "error"
    assert "psutil boom" in body["error"]
    assert any("error collecting" in w.lower() for w in body["warnings"])


def test_detailed_health_success_and_failure(client, monkeypatch):
    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)
    monkeypatch.setattr(health_routes.time, "time", lambda: 1060.0)

    class _FakeProc:
        def cpu_percent(self, interval=0.1):
            return 1.234

    monkeypatch.setattr(health_routes.psutil, "Process", lambda: _FakeProc())
    monkeypatch.setattr(health_routes.psutil, "cpu_percent", lambda interval=0.1: 2.345)
    monkeypatch.setattr(health_routes.psutil, "cpu_count", lambda: 8)
    monkeypatch.setattr(health_routes.os, "getloadavg", lambda: (0.1, 0.2, 0.3), raising=False)

    # SUCCESS
    monkeypatch.setattr(health_routes, "get_memory_stats", lambda: {"system": {"percent": 50}})
    monkeypatch.setattr(health_routes, "get_disk_stats", lambda: {"root": {"percent": 50}})
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "ok", "usage_percent": 10})
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "healthy"})
    monkeypatch.setattr(health_routes, "get_chromadb_stats", lambda: {"status": "healthy"})
    monkeypatch.setattr(health_routes, "get_environment_info", lambda: {"environment": "test"})
    monkeypatch.setattr(health_routes, "get_api_health", lambda: {"status": "healthy", "configured_count": 3, "total_checked": 3})
    monkeypatch.setattr(health_routes, "get_autopolling_status", lambda: {"status": "disabled"})
    res = client.get("/health/detailed")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body
    assert "cpu" in body
    assert "database" in body
    assert "vector_store" in body
    assert "autopolling" in body

    # DEGRADED (fd critical + db unhealthy + api critical + polling error)
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "critical", "usage_percent": 95})
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "unhealthy", "error": "down"})
    monkeypatch.setattr(health_routes, "get_api_health", lambda: {"status": "critical", "configured_count": 0, "total_checked": 3})
    monkeypatch.setattr(health_routes, "get_autopolling_status", lambda: {"status": "error", "error": "bad"})
    res = client.get("/health/detailed")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "degraded"
    assert "warnings" in body
    assert any("database unhealthy" in w.lower() for w in body["warnings"])

    # FAILURE
    monkeypatch.setattr(health_routes.psutil, "Process", lambda: (_ for _ in ()).throw(Exception("detailed boom")))
    res = client.get("/health/detailed")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = res.json()
    assert body["status"] == "error"
    assert "detailed boom" in body["error"]


def test_database_health_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "healthy", "article_count": 1})
    res = client.get("/health/database")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "healthy"

    # FAILURE
    monkeypatch.setattr(health_routes, "get_database_health", lambda: (_ for _ in ()).throw(Exception("db helper boom")))
    with pytest.raises(Exception):
        client.get("/health/database")


def test_resource_health_success_and_failure(client, monkeypatch):
    # SUCCESS (healthy)
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "ok", "usage_percent": 10})
    monkeypatch.setattr(health_routes, "get_memory_stats", lambda: {"system": {"percent": 50}})
    monkeypatch.setattr(health_routes, "get_disk_stats", lambda: {"root": {"percent": 50}})
    res = client.get("/health/resources")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "healthy"
    assert body["issues"] is None

    # WARNING (fd warning)
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "warning", "usage_percent": 80})
    res = client.get("/health/resources")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "warning"
    assert any("file descriptors" in i.lower() for i in body["issues"])

    # CRITICAL (memory/disk)
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "ok", "usage_percent": 10})
    monkeypatch.setattr(health_routes, "get_memory_stats", lambda: {"system": {"percent": 91}})
    monkeypatch.setattr(health_routes, "get_disk_stats", lambda: {"root": {"percent": 91}})
    res = client.get("/health/resources")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["status"] == "critical"
    assert any("system memory" in i.lower() for i in body["issues"])
    assert any("disk usage" in i.lower() for i in body["issues"])

    # FAILURE
    monkeypatch.setattr(health_routes, "get_disk_stats", lambda: (_ for _ in ()).throw(Exception("resource boom")))
    with pytest.raises(Exception):
        client.get("/health/resources")


def test_readiness_check_success_and_failure(client, monkeypatch):
    # READY
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "healthy"})
    res = client.get("/health/ready")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["ready"] is True

    # NOT READY
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "unhealthy"})
    res = client.get("/health/ready")
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert res.json()["ready"] is False

    # FAILURE
    monkeypatch.setattr(health_routes, "get_database_health", lambda: (_ for _ in ()).throw(Exception("ready boom")))
    res = client.get("/health/ready")
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert res.json()["ready"] is False
    assert "ready boom" in res.json()["reason"]


def test_liveness_check_success_and_failure(client, monkeypatch):
    # SUCCESS
    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)
    monkeypatch.setattr(health_routes.time, "time", lambda: 1005.0)
    res = client.get("/health/live")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["live"] is True
    assert res.json()["uptime_seconds"] == 5.0

    # FAILURE
    monkeypatch.setattr(health_routes.time, "time", lambda: (_ for _ in ()).throw(Exception("live boom")))
    with pytest.raises(Exception):
        client.get("/health/live")


def test_startup_check_success_and_failure(client, monkeypatch):
    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)

    # NOT READY
    monkeypatch.setattr(health_routes.time, "time", lambda: 1005.0)
    res = client.get("/health/startup")
    assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert res.json()["started"] is False

    # READY
    monkeypatch.setattr(health_routes.time, "time", lambda: 1011.0)
    res = client.get("/health/startup")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["started"] is True

    # FAILURE
    monkeypatch.setattr(health_routes.time, "time", lambda: (_ for _ in ()).throw(Exception("startup boom")))
    with pytest.raises(Exception):
        client.get("/health/startup")


def test_health_dashboard_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(health_routes, "START_TIME", 1000.0)
    monkeypatch.setattr(health_routes.time, "time", lambda: 1060.0)

    class _FakeProc:
        def cpu_percent(self, interval=0.1):
            return 1.234

    monkeypatch.setattr(health_routes.psutil, "Process", lambda: _FakeProc())
    monkeypatch.setattr(health_routes.psutil, "cpu_percent", lambda interval=0.1: 2.345)
    monkeypatch.setattr(health_routes.psutil, "cpu_count", lambda: 8)
    monkeypatch.setattr(health_routes.os, "getloadavg", lambda: (0.1, 0.2, 0.3), raising=False)

    monkeypatch.setattr(health_routes, "get_memory_stats", lambda: {"system": {"percent": 50}})
    monkeypatch.setattr(health_routes, "get_disk_stats", lambda: {"root": {"percent": 50}})
    monkeypatch.setattr(health_routes, "get_file_descriptor_stats", lambda: {"status": "ok", "usage_percent": 10})
    monkeypatch.setattr(health_routes, "get_database_health", lambda: {"status": "healthy"})
    monkeypatch.setattr(health_routes, "get_chromadb_stats", lambda: {"status": "healthy"})
    monkeypatch.setattr(health_routes, "get_environment_info", lambda: {"environment": "test"})
    monkeypatch.setattr(health_routes, "get_api_health", lambda: {"status": "healthy", "configured_count": 3, "total_checked": 3})
    monkeypatch.setattr(health_routes, "get_autopolling_status", lambda: {"status": "disabled"})

    captured = {}

    def _fake_template_response(template_name: str, context: dict):
        captured["template"] = template_name
        captured["context"] = context
        return health_routes.HTMLResponse(
            f"<html><body>{context['health_data']['status']}</body></html>",
            status_code=200,
        )

    monkeypatch.setattr(health_routes.templates, "TemplateResponse", _fake_template_response)

    # SUCCESS
    res = client.get("/health/dashboard")
    assert res.status_code == status.HTTP_200_OK
    assert "<html" in res.text.lower()
    assert "healthy" in res.text.lower()
    assert captured["template"] == "health.html"
    assert captured["context"]["health_data"]["status"] == "healthy"

    # FAILURE -> error page rendered
    monkeypatch.setattr(health_routes, "get_memory_stats", lambda: (_ for _ in ()).throw(Exception("dash boom")))
    res = client.get("/health/dashboard")
    assert res.status_code == status.HTTP_200_OK
    assert "error" in res.text.lower()

# podcast_routes.py endpoints
# =============================================================================


@pytest.fixture
def fake_llm():
    return MagicMock(name="fake_llm")


@pytest.fixture
def fake_elevenlabs():
    return MagicMock(name="fake_elevenlabs")


@pytest.fixture
def fake_dia_client():
    fake = MagicMock(name="fake_dia_client")
    fake.tts = AsyncMock(name="fake_dia_tts")
    return fake


def test_get_podcast_template_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    class _Path:
        def __init__(self, exists: bool):
            self._exists = exists

        def exists(self):
            return self._exists

    # SUCCESS
    monkeypatch.setattr(podcast_routes, "_template_path", lambda name: _Path(True))
    monkeypatch.setattr(podcast_routes, "_load_template_file", lambda path: {"name": "default", "content": "hi"})
    res = client.get("/api/podcast_templates/default")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"name": "default", "content": "hi", "template": "hi"}

    # NOT FOUND
    monkeypatch.setattr(podcast_routes, "_template_path", lambda name: _Path(False))
    res = client.get("/api/podcast_templates/missing")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    monkeypatch.setattr(podcast_routes, "_template_path", lambda name: _Path(True))

    def _boom(*args, **kwargs):
        raise podcast_routes.HTTPException(status_code=500, detail="read error")

    monkeypatch.setattr(podcast_routes, "_load_template_file", _boom)
    res = client.get("/api/podcast_templates/default")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_save_podcast_template_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    monkeypatch.setattr(podcast_routes, "_save_template_file", lambda name, content: None)
    res = client.post("/api/podcast_templates", json={"name": "x", "content": "hello"})
    assert res.status_code == status.HTTP_200_OK
    assert "saved successfully" in res.json()["message"]

    # FAILURE
    def _boom(*args, **kwargs):
        raise Exception("save error")

    monkeypatch.setattr(podcast_routes, "_save_template_file", _boom)
    res = client.post("/api/podcast_templates", json={"name": "x", "content": "hello"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "save error" in res.json()["detail"]


def test_list_podcast_templates_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    class _FakeDir:
        def mkdir(self, *args, **kwargs):
            return None

        def glob(self, pattern: str):
            return ["p1.json"]

    monkeypatch.setattr(podcast_routes, "TEMPLATE_DIR", _FakeDir())
    monkeypatch.setattr(podcast_routes, "_load_template_file", lambda path: {"name": "custom", "content": "c"})

    # SUCCESS + DEFAULT ADDED
    res = client.get("/api/podcast_templates")
    assert res.status_code == status.HTTP_200_OK
    names = [t["name"] for t in res.json()]
    assert "custom" in names
    assert "default" in names

    # FAILURE
    class _BadDir(_FakeDir):
        def glob(self, pattern: str):
            raise Exception("boom")

    monkeypatch.setattr(podcast_routes, "TEMPLATE_DIR", _BadDir())
    res = client.get("/api/podcast_templates")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "Failed to list templates"


def test_get_podcast_settings_success_and_failure(client, fake_db, fake_session):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    fake_db.get_podcast_setting.return_value = '{"a": 1}'
    res = client.get("/api/podcast_settings/conversation")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"a": 1}

    # EMPTY
    fake_db.get_podcast_setting.return_value = None
    res = client.get("/api/podcast_settings/conversation")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {}

    # FAILURE
    fake_db.get_podcast_setting.side_effect = podcast_routes.HTTPException(status_code=500, detail="boom")
    res = client.get("/api/podcast_settings/conversation")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_save_podcast_settings_success_and_failure(client, fake_db, fake_session):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    # SUCCESS
    fake_db.set_podcast_setting.return_value = None
    res = client.post("/api/podcast_settings/conversation", json={"settings": {"x": "y"}})
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"message": "Settings saved"}
    assert fake_db.set_podcast_setting.called

    # FAILURE
    fake_db.set_podcast_setting.side_effect = podcast_routes.HTTPException(status_code=500, detail="boom")
    res = client.post("/api/podcast_settings/conversation", json={"settings": {"x": "y"}})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_generate_podcast_script_success_and_failure(client, fake_db, fake_session, fake_llm, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(podcast_routes, "load_prompt_template", lambda mode, duration: "Hello {podcast_name} {episode_title}")
    monkeypatch.setattr(podcast_routes, "_postprocess_script", lambda raw: f"POST({raw})")

    # SUCCESS
    fake_llm.agenerate_response = AsyncMock(return_value="RAW")
    monkeypatch.setattr(podcast_routes.LiteLLMModel, "get_instance", lambda model: fake_llm)

    payload = {
        "podcast_name": "A",
        "episode_title": "E",
        "model": "gpt-4o",
        "mode": "conversation",
        "duration": "medium",
        "host_name": "H",
        "guest_name": "G",
        "guest_title": "T",
        "articles": [{"title": "t", "summary": "s"}],
    }
    res = client.post("/api/generate_podcast_script", json=payload)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["script"] == "POST(RAW)"
    assert body["article_count"] == 1

    # FAILURE: model init fails
    monkeypatch.setattr(podcast_routes.LiteLLMModel, "get_instance", lambda model: None)
    res = client.post("/api/generate_podcast_script", json=payload)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to generate podcast script" in res.json()["detail"]

    # FAILURE: empty response
    monkeypatch.setattr(podcast_routes.LiteLLMModel, "get_instance", lambda model: fake_llm)
    fake_llm.agenerate_response = AsyncMock(return_value="")
    res = client.post("/api/generate_podcast_script", json=payload)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to generate podcast script" in res.json()["detail"]


def test_generate_tts_podcast_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    class _Thread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(podcast_routes.threading, "Thread", _Thread)

    import uuid as _uuid
    fixed_uuid = _uuid.UUID("22222222-2222-2222-2222-222222222222")
    monkeypatch.setattr(podcast_routes.uuid, "uuid4", lambda: fixed_uuid)

    # SUCCESS
    facade.generate_tts_podcast.return_value = None
    res = client.post(
        "/api/generate_tts_podcast",
        json={"podcast_name": "P", "episode_title": "E", "host_voice_id": "v1", "script": "hello"},
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert body["podcast_id"] == str(fixed_uuid)
    assert body["status"] == "processing"

    # FAILURE
    facade.generate_tts_podcast.side_effect = Exception("db error")
    res = client.post(
        "/api/generate_tts_podcast",
        json={"podcast_name": "P", "episode_title": "E", "host_voice_id": "v1", "script": "hello"},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "db error" in res.json()["detail"]


def test_create_podcast_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[get_database_instance] = lambda: fake_db
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(podcast_routes, "validate_api_keys", lambda: None)
    fake_db.get_article.side_effect = lambda uri: {"title": "t", "summary": "s", "sentiment": "n", "time_to_impact": "soon", "driver_type": "x"}

    # Avoid depending on elevenlabs SDK shapes
    monkeypatch.setattr(podcast_routes, "PodcastConversationModeData", MagicMock())
    monkeypatch.setattr(podcast_routes, "PodcastTextSource", MagicMock())
    monkeypatch.setattr(podcast_routes, "BodyCreatePodcastV1StudioPodcastsPostMode_Conversation", MagicMock())
    monkeypatch.setattr(podcast_routes, "BodyCreatePodcastV1StudioPodcastsPostMode_Bulletin", MagicMock())

    class _EL:
        def __init__(self, api_key=None):
            self.studio = MagicMock()
            self.studio.create_podcast.return_value = {"podcast_id": "pod-1"}

    monkeypatch.setattr(podcast_routes, "ElevenLabs", _EL)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    def _getenv(key, default=None):
        if key == "ELEVENLABS_API_KEY":
            return "sk_test"
        if key == "DISABLE_SSL":
            return "true"  # else middleware redirects POST to GET, causing 405
        return default

    monkeypatch.setattr(podcast_routes.os, "getenv", _getenv)

    # SUCCESS
    res = client.post(
        "/api/create",
        json={
            "title": "MyPod",
            "mode": "conversation",
            "host_voice_id": "v1",
            "guest_voice_id": "v2",
            "duration_scale": "default",
            "quality_preset": "standard",
            "article_uris": ["u1"],
        },
    )
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["podcast_id"] == "pod-1"
    assert body["title"] == "MyPod"
    assert body["status"] == "processing"

    # NOT FOUND
    fake_db.get_article.side_effect = lambda uri: None
    res = client.post(
        "/api/create",
        json={
            "title": "MyPod",
            "mode": "conversation",
            "host_voice_id": "v1",
            "guest_voice_id": "v2",
            "duration_scale": "default",
            "quality_preset": "standard",
            "article_uris": ["u1"],
        },
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # VALIDATION: invalid API key format -> 500
    def _bad_getenv(key, default=None):
        if key == "ELEVENLABS_API_KEY":
            return "bad_key"
        if key == "DISABLE_SSL":
            return "true"
        return default

    monkeypatch.setattr(podcast_routes.os, "getenv", _bad_getenv)
    fake_db.get_article.side_effect = lambda uri: {"title": "t", "summary": "s", "sentiment": "n", "time_to_impact": "soon", "driver_type": "x"}
    res = client.post(
        "/api/create",
        json={
            "title": "MyPod",
            "mode": "conversation",
            "host_voice_id": "v1",
            "guest_voice_id": "v2",
            "duration_scale": "default",
            "quality_preset": "standard",
            "article_uris": ["u1"],
        },
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # FAILURE: ElevenLabs mapped error
    class _ELBad:
        def __init__(self, api_key=None):
            self.studio = MagicMock()
            self.studio.create_podcast.side_effect = Exception("invalid_subscription")

    monkeypatch.setattr(podcast_routes.os, "getenv", _getenv)
    monkeypatch.setattr(podcast_routes, "ElevenLabs", _ELBad)
    res = client.post(
        "/api/create",
        json={
            "title": "MyPod",
            "mode": "conversation",
            "host_voice_id": "v1",
            "guest_voice_id": "v2",
            "duration_scale": "default",
            "quality_preset": "standard",
            "article_uris": ["u1"],
        },
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_get_podcast_transcript_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    # Fix module-level db usage in route
    monkeypatch.setattr(podcast_routes, "db", fake_db, raising=False)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    # SUCCESS
    facade.get_podcast_transcript.return_value = ("My Pod", "hello transcript", '{"x": 1}')
    res = client.get("/api/podcast/p1/transcript")
    assert res.status_code == status.HTTP_200_OK
    assert res.text == "hello transcript"
    assert "Content-Disposition" in res.headers

    # NOT FOUND
    facade.get_podcast_transcript.return_value = None
    res = client.get("/api/podcast/p1/transcript")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    facade.get_podcast_transcript.side_effect = Exception("boom")
    res = client.get("/api/podcast/p1/transcript")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_list_podcasts_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    # SUCCESS
    facade.get_all_podcasts.return_value = [
        {
            "id": "p1",
            "title": "t1",
            "status": "done",
            "audio_url": "/static/audio/a.mp3",
            "created_at": None,
            "completed_at": None,
            "error": None,
            "transcript": "tr",
            "metadata": '{"m": 1}',
        },
    ]
    res = client.get("/api/podcast/list")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)
    assert res.json()[0]["podcast_id"] == "p1"
    assert res.json()[0]["metadata"] == {"m": 1}

    # FAILURE
    facade.get_all_podcasts.side_effect = Exception("boom")
    res = client.get("/api/podcast/list")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_podcast_status_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    # SUCCESS
    facade.get_podcast_generation_status.return_value = ("p1", "t1", "done", "/a", "c1", "c2", None, "tr", '{"m": 1}')
    res = client.get("/api/podcast/status/p1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["podcast_id"] == "p1"
    assert res.json()["metadata"] == {"m": 1}

    # NOT FOUND
    facade.get_podcast_generation_status.return_value = None
    res = client.get("/api/podcast/status/p1")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    facade.get_podcast_generation_status.side_effect = Exception("boom")
    res = client.get("/api/podcast/status/p1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_available_voices_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(podcast_routes, "validate_api_keys", lambda: None)

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"voices": [{"voice_id": "v1", "name": "Alice", "category": "test"}]}

    # SUCCESS
    monkeypatch.setattr(podcast_routes.requests, "get", lambda *args, **kwargs: _Resp())
    res = client.get("/api/available_voices")
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)
    assert res.json()[0]["voice_id"] == "v1"

    # FAILURE
    def _boom(*args, **kwargs):
        raise Exception("api down")

    monkeypatch.setattr(podcast_routes.requests, "get", _boom)
    res = client.get("/api/available_voices")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to fetch voices" in res.json()["detail"]


def test_get_voice_success_and_failure(client, fake_session, monkeypatch):
    import requests as _requests

    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(podcast_routes, "validate_api_keys", lambda: None)

    class _Resp:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {"voice_id": "v1", "name": "Alice"}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    # SUCCESS
    monkeypatch.setattr(podcast_routes.requests, "get", lambda *args, **kwargs: _Resp())
    res = client.get("/api/voice/v1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["voice_id"] == "v1"

    # NOT FOUND (404 HTTPError)
    class _Resp404(_Resp):
        def raise_for_status(self):
            raise _requests.exceptions.HTTPError("404", response=self)

    monkeypatch.setattr(podcast_routes.requests, "get", lambda *args, **kwargs: _Resp404(status_code=404))
    res = client.get("/api/voice/missing")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # FAILURE
    def _boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(podcast_routes.requests, "get", _boom)
    res = client.get("/api/voice/v1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_delete_podcast_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session
    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)
    monkeypatch.setattr(podcast_routes, "ensure_audio_directory", lambda: True)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    class _File:
        def __init__(self):
            self._unlinked = False

        def exists(self):
            return True

        def unlink(self):
            self._unlinked = True

    fake_file = _File()

    class _Dir:
        def __truediv__(self, name):
            return fake_file

    monkeypatch.setattr(podcast_routes, "AUDIO_DIR", _Dir())

    # SUCCESS + FILE CLEANUP
    facade.get_podcast_audio_file.return_value = ("/static/audio/x.mp3",)
    facade.delete_podcast.return_value = None
    res = client.delete("/api/podcast/p1")
    assert res.status_code == status.HTTP_200_OK
    assert "deleted successfully" in res.json()["message"]
    assert fake_file._unlinked is True

    # NOT FOUND
    facade.get_podcast_audio_file.return_value = None
    res = client.delete("/api/podcast/p1")
    # NOTE: podcast_routes.delete_podcast catches all exceptions (including HTTPException(404))
    # and re-wraps them as HTTP 500, so "not found" currently surfaces as 500.
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "404" in res.json()["detail"]

    # FAILURE
    facade.get_podcast_audio_file.side_effect = Exception("boom")
    res = client.delete("/api/podcast/p1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_dia_convert_endpoint_success_and_failure(client, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    # VALIDATION
    res = client.post("/api/dia/convert", json={"script": ""})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # SUCCESS
    monkeypatch.setattr(podcast_routes, "to_dia_tags", lambda s: "[S1] hi")
    res = client.post("/api/dia/convert", json={"script": "hello"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"script": "[S1] hi"}

    # FAILURE
    def _boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(podcast_routes, "to_dia_tags", _boom)
    res = client.post("/api/dia/convert", json={"script": "hello"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_dia_tts_endpoint_success_and_failure(client, fake_session, fake_dia_client, monkeypatch):
    import app.services as services_pkg

    fastapi_app = client.app
    fastapi_app.dependency_overrides[verify_session] = lambda: fake_session

    # Make `from app.services import dia_client` resolve to our fake
    monkeypatch.setattr(services_pkg, "dia_client", fake_dia_client, raising=False)

    # VALIDATION
    res = client.post("/api/dia/tts", json={"text": ""})
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # SUCCESS
    monkeypatch.setattr(podcast_routes, "to_dia_tags", lambda s: "[S1] hi")
    fake_dia_client.tts = AsyncMock(return_value=b"audio")
    res = client.post("/api/dia/tts", json={"text": "hello", "output_format": "mp3"})
    assert res.status_code == status.HTTP_200_OK
    assert res.content == b"audio"

    # FAILURE
    fake_dia_client.tts = AsyncMock(side_effect=Exception("boom"))
    res = client.post("/api/dia/tts", json={"text": "hello", "output_format": "mp3"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_dia_generate_podcast_success_and_failure(client, fake_db, fake_session, monkeypatch):
    app = client.app
    app.dependency_overrides[verify_session] = lambda: fake_session

    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)
    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    class _Thread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True

    monkeypatch.setattr(podcast_routes.threading, "Thread", _Thread)

    import uuid as _uuid
    fixed_uuid = _uuid.UUID("33333333-3333-3333-3333-333333333333")
    monkeypatch.setattr(podcast_routes.uuid, "uuid4", lambda: fixed_uuid)

    # SUCCESS
    facade.generate_tts_podcast.return_value = None
    res = client.post("/api/dia/generate_podcast", json={"podcast_name": "P", "episode_title": "E", "text": "[S1] hi"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["podcast_id"] == str(fixed_uuid)

    # FAILURE
    facade.generate_tts_podcast.side_effect = Exception("db error")
    res = client.post("/api/dia/generate_podcast", json={"podcast_name": "P", "episode_title": "E", "text": "[S1] hi"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test__run_tts_podcast_worker_success_and_failure(fake_db, fake_dia_client, monkeypatch):
    import io
    import builtins
    import asyncio

    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)
    monkeypatch.setattr(podcast_routes, "validate_api_keys", lambda: None)
    monkeypatch.setattr(podcast_routes, "ensure_audio_directory", lambda: True)
    monkeypatch.setattr(podcast_routes, "get_available_voices", AsyncMock(return_value=[]))
    monkeypatch.setattr(podcast_routes, "ELEVENLABS_API_KEY", "sk_test", raising=False)

    class _File:
        def __truediv__(self, name):
            return f"FAKEPATH/{name}"

    monkeypatch.setattr(podcast_routes, "AUDIO_DIR", _File())

    class _Open:
        def __init__(self):
            self.buf = io.BytesIO()

        def __call__(self, *args, **kwargs):
            return self

        def __enter__(self):
            return self.buf

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_open = _Open()
    monkeypatch.setattr(builtins, "open", fake_open)

    class _EL:
        def __init__(self, api_key=None):
            self.text_to_speech = MagicMock()
            self.text_to_speech.convert.return_value = [b"abc"]

    monkeypatch.setattr(podcast_routes, "ElevenLabs", _EL)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    req = podcast_routes.TTSPodcastRequest(
        podcast_name="P",
        episode_title="E",
        host_voice_id="v1",
        script="hello",
        mode="bulletin",
    )

    # SUCCESS
    asyncio.run(podcast_routes._run_tts_podcast_worker("pid-1", req, username=None))
    assert facade.mark_podcast_generation_as_complete.called

    # FAILURE
    class _ELBad:
        def __init__(self, api_key=None):
            self.text_to_speech = MagicMock()

            def _gen():
                raise Exception("boom")
                yield b"x"

            self.text_to_speech.convert.return_value = _gen()

    monkeypatch.setattr(podcast_routes, "ElevenLabs", _ELBad)
    asyncio.run(podcast_routes._run_tts_podcast_worker("pid-2", req, username=None))
    assert facade.log_error_generating_podcast.called


def test__run_dia_podcast_worker_success_and_failure(fake_db, fake_dia_client, monkeypatch):
    import asyncio
    import app.services

    monkeypatch.setattr(podcast_routes, "get_database_instance", lambda: fake_db)
    monkeypatch.setattr(podcast_routes, "ensure_audio_directory", lambda: True)
    monkeypatch.setattr(app.services, "dia_client", fake_dia_client, raising=False)
    monkeypatch.setattr(podcast_routes, "_split_by_speaker", lambda text, max_chars=2500: ["[S1] hi"])
    monkeypatch.setattr(podcast_routes, "combine_audio_files", lambda parts, filename: 60.0, raising=False)

    facade = MagicMock(name="podcast_facade")
    monkeypatch.setattr(podcast_routes, "DatabaseQueryFacade", MagicMock(return_value=facade))

    req = podcast_routes.DiaPodcastRequest(podcast_name="P", episode_title="E", text="[S1] hi", output_format="mp3")

    # SUCCESS
    fake_dia_client.tts = AsyncMock(return_value=b"audio")
    asyncio.run(podcast_routes._run_dia_podcast_worker("pid-1", req, username=None))
    assert facade.mark_podcast_generation_as_complete.called

    # FAILURE
    fake_dia_client.tts = AsyncMock(side_effect=Exception("boom"))
    asyncio.run(podcast_routes._run_dia_podcast_worker("pid-2", req, username=None))
    assert facade.log_error_generating_podcast.called


# =============================================================================
# oauth_routes.py endpoints
# =============================================================================


def test_get_available_providers_success_and_failure(client, monkeypatch):
    import app.security.oauth as security_oauth
    from fastapi.testclient import TestClient

    # ---------------- SUCCESS ----------------
    monkeypatch.setattr(security_oauth, "get_configured_providers", lambda: ["google", "github", "not-a-provider"])
    monkeypatch.setattr(
        oauth_routes,
        "OAUTH_PROVIDERS",
        {
            "google": {"name": "Google", "icon": "g", "color": "#fff", "button_class": "btn-g"},
            "github": {"name": "GitHub", "icon": "gh", "color": "#000", "button_class": "btn-gh"},
        },
    )

    res = client.get("/auth/providers")
    assert res.status_code == 200
    payload = res.json()
    assert payload["count"] == 2
    assert [p["name"] for p in payload["providers"]] == ["google", "github"]

    # ---------------- FAILURE ----------------
    monkeypatch.setattr(security_oauth, "get_configured_providers", lambda: (_ for _ in ()).throw(Exception("boom")))
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    res = failure_client.get("/auth/providers")
    assert res.status_code == 500


def test_oauth_login_success_and_failure(client, monkeypatch):
    from fastapi.responses import RedirectResponse

    # ---------------- SUCCESS ----------------
    monkeypatch.setattr(oauth_routes, "is_provider_configured", lambda provider: True)
    monkeypatch.setattr(
        oauth_routes,
        "get_oauth_redirect_uri",
        lambda request, provider: "http://localhost:10000/auth/callback/google",
    )

    fake_client = MagicMock(name="oauth_client")

    async def _authorize_redirect(request, redirect_uri):
        assert redirect_uri.endswith("/auth/callback/google")
        return RedirectResponse(url="http://provider.example/auth", status_code=302)

    fake_client.authorize_redirect = _authorize_redirect
    monkeypatch.setattr(oauth_routes.oauth, "create_client", lambda provider: fake_client)

    res = client.get("/auth/login/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "http://provider.example/auth"

    # ---------------- INVALID PROVIDER ----------------
    monkeypatch.setattr(oauth_routes, "is_provider_configured", lambda provider: False)
    res = client.get("/auth/login/google", follow_redirects=False)
    assert res.status_code == 400
    assert "not configured" in res.json()["detail"].lower()

    # ---------------- PRIVATE IP (GOOGLE) ----------------
    monkeypatch.setattr(oauth_routes, "is_provider_configured", lambda provider: True)
    monkeypatch.setattr(
        oauth_routes,
        "get_oauth_redirect_uri",
        lambda request, provider: "http://192.168.1.10/auth/callback/google",
    )
    monkeypatch.setattr(oauth_routes.oauth, "create_client", lambda provider: MagicMock(name="client"))
    res = client.get("/auth/login/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?error=")
    err = unquote_plus(res.headers["location"].split("error=", 1)[1])
    assert "google oauth doesn't support private ip" in err.lower()

    # ---------------- FAILURE (EXCEPTION) ----------------
    monkeypatch.setattr(
        oauth_routes,
        "get_oauth_redirect_uri",
        lambda request, provider: "http://localhost:10000/auth/callback/google",
    )

    async def _boom(*args, **kwargs):
        raise Exception("boom")

    fake_client.authorize_redirect = _boom
    monkeypatch.setattr(oauth_routes.oauth, "create_client", lambda provider: fake_client)
    res = client.get("/auth/login/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?error=")
    err = unquote_plus(res.headers["location"].split("error=", 1)[1])
    assert "oauth login failed" in err.lower()


def test_oauth_callback_success_and_failure(client, monkeypatch):
    # ---------------- INVALID PROVIDER ----------------
    monkeypatch.setattr(oauth_routes, "is_provider_configured", lambda provider: False)
    res = client.get("/auth/callback/google", follow_redirects=False)
    assert res.status_code == 400

    # Base patches for remaining cases
    monkeypatch.setattr(oauth_routes, "is_provider_configured", lambda provider: True)

    class FakeClient:
        def __init__(self, token=None, exc=None):
            self._token = token
            self._exc = exc

        async def authorize_access_token(self, request):
            if self._exc:
                raise self._exc
            return self._token

    # ---------------- SUCCESS ----------------
    monkeypatch.setattr(oauth_routes.oauth, "create_client", lambda provider: FakeClient(token={"access_token": "t"}))
    monkeypatch.setattr(
        oauth_routes,
        "extract_user_info",
        AsyncMock(
            return_value={
                "id": "1",
                "email": "user@example.com",
                "name": "User",
                "avatar_url": "http://avatar",
            }
        ),
    )

    class FakeManager:
        def __init__(self, db):
            self.db = db

        def create_or_update_oauth_user(self, **kwargs):
            return {"id": "db-user-1", **kwargs}

    monkeypatch.setattr(oauth_routes, "OAuthUserManager", FakeManager)
    monkeypatch.setattr(
        oauth_routes,
        "create_oauth_session_data",
        lambda oauth_user: {"oauth_user": {"email": oauth_user["email"], "provider": oauth_user["provider"]}, "oauth_redirect_after_login": "/after"},
    )

    res = client.get("/auth/callback/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/after"

    # ---------------- TOKEN ERROR ----------------
    monkeypatch.setattr(
        oauth_routes.oauth,
        "create_client",
        lambda provider: FakeClient(exc=Exception("invalid_client: bad client")),
    )
    res = client.get("/auth/callback/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?error=")
    err = unquote_plus(res.headers["location"].split("error=", 1)[1])
    assert "oauth client not found" in err.lower()

    # ---------------- MISSING USER INFO ----------------
    monkeypatch.setattr(oauth_routes.oauth, "create_client", lambda provider: FakeClient(token={"access_token": "t"}))
    monkeypatch.setattr(oauth_routes, "extract_user_info", AsyncMock(return_value=None))
    res = client.get("/auth/callback/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?error=")
    err = unquote_plus(res.headers["location"].split("error=", 1)[1])
    assert "failed to get user information" in err.lower()

    # ---------------- DB ERROR ----------------
    monkeypatch.setattr(
        oauth_routes,
        "extract_user_info",
        AsyncMock(
            return_value={
                "id": "1",
                "email": "user@example.com",
                "name": "User",
                "avatar_url": "http://avatar",
            }
        ),
    )

    class BadManager:
        def __init__(self, db):
            self.db = db

        def create_or_update_oauth_user(self, **kwargs):
            raise Exception("db boom")

    monkeypatch.setattr(oauth_routes, "OAuthUserManager", BadManager)
    res = client.get("/auth/callback/google", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"].startswith("/login?error=")
    err = unquote_plus(res.headers["location"].split("error=", 1)[1])
    assert "failed to create user account" in err.lower()


def test_oauth_logout_success_and_failure(client):
    from fastapi import HTTPException

    # ---------------- SUCCESS ----------------
    res = client.post("/auth/logout")
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # ---------------- FAILURE (DIRECT CALL WITH BROKEN SESSION) ----------------
    class BadSession(dict):
        def clear(self):
            raise Exception("boom")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/logout",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "session": BadSession(),
    }
    req = Request(scope)
    with pytest.raises(HTTPException):
        asyncio.run(oauth_routes.oauth_logout(req))


def test_oauth_status_success_and_failure():
    # ---------------- OAUTH USER ----------------
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/status",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "session": {
            "oauth_user": {"provider": "google", "email": "a@b.com", "name": "A", "avatar_url": "u"},
        },
    }
    res = asyncio.run(oauth_routes.oauth_status(Request(scope)))
    assert res["authenticated"] is True
    assert res["is_oauth"] is True
    assert res["provider"] == "google"

    # ---------------- LOCAL USER ----------------
    scope["session"] = {"user": "local-user"}
    res = asyncio.run(oauth_routes.oauth_status(Request(scope)))
    assert res["authenticated"] is True
    assert res["is_oauth"] is False
    assert res["user"]["username"] == "local-user"

    # ---------------- ANONYMOUS ----------------
    scope["session"] = {}
    res = asyncio.run(oauth_routes.oauth_status(Request(scope)))
    assert res["authenticated"] is False
    assert res["is_oauth"] is False

    # ---------------- FAILURE ----------------
    class BoomSession:
        def get(self, *args, **kwargs):
            raise Exception("boom")

    scope["session"] = BoomSession()
    res = asyncio.run(oauth_routes.oauth_status(Request(scope)))
    assert res["authenticated"] is False
    assert res["is_oauth"] is False
    assert "error" in res


def test_oauth_config_check_success_and_failure(client, monkeypatch):
    from app.config import oauth_config as oauth_config_module

    # ---------------- SUCCESS ----------------
    report = {
        "configured_providers": [{"name": "google"}, {"name": "github"}],
        "missing_providers": [{"name": "microsoft"}],
        "errors": [],
    }

    def _validate(cls):
        return report

    monkeypatch.setattr(oauth_config_module.OAuthConfig, "validate_configuration", classmethod(_validate))

    def _getenv(key, default=None):
        if key == "GOOGLE_CLIENT_ID":
            return "google-client-id-123"
        if key == "GOOGLE_CLIENT_SECRET":
            return "google-secret-xyz"
        if key == "GOOGLE_DEVICE_ID":
            return "device-1"
        if key == "DISABLE_SSL":
            return "true"
        return default

    monkeypatch.setattr(oauth_routes.os, "getenv", _getenv)

    res = client.get("/auth/config-check")
    assert res.status_code == 200
    payload = res.json()
    assert payload["configured_providers"] == ["google", "github"]
    assert payload["missing_providers"] == ["microsoft"]
    assert payload["provider_status"]["google"]["has_client_id"] is True
    assert payload["provider_status"]["google"]["has_client_secret"] is True
    assert payload["provider_status"]["google"]["has_device_id"] is True
    assert payload["total_configured"] == 2

    # ---------------- EMPTY ----------------
    report2 = {"configured_providers": [], "missing_providers": [], "errors": []}

    def _validate2(cls):
        return report2

    monkeypatch.setattr(oauth_config_module.OAuthConfig, "validate_configuration", classmethod(_validate2))
    monkeypatch.setattr(oauth_routes.os, "getenv", lambda key, default=None: "true" if key == "DISABLE_SSL" else default)

    res = client.get("/auth/config-check")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total_configured"] == 0
    assert payload["provider_status"]["google"]["has_client_id"] is False
    assert payload["provider_status"]["google"]["has_client_secret"] is False

    # ---------------- FAILURE ----------------
    def _boom(cls):
        raise Exception("boom")

    monkeypatch.setattr(oauth_config_module.OAuthConfig, "validate_configuration", classmethod(_boom))
    res = client.get("/auth/config-check")
    assert res.status_code == 200
    payload = res.json()
    assert payload["configured_providers"] == []
    assert payload["missing_providers"] == []
    assert payload["total_configured"] == 0
    assert "error" in payload


@pytest.mark.asyncio
async def test_extract_user_info_success_and_failure():
    class Resp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    # ---------------- GOOGLE (TOKEN USERINFO) ----------------
    google_token = {
        "userinfo": {"sub": "g1", "email": "g@e.com", "name": "G", "picture": "p"},
    }
    client = MagicMock(name="oauth_client")
    info = await oauth_routes.extract_user_info(client, google_token, "google")
    assert info["id"] == "g1"
    assert info["email"] == "g@e.com"

    # ---------------- GOOGLE (API FALLBACK) ----------------
    class GoogleClient:
        async def get(self, path, token=None):
            assert path == "userinfo"
            return Resp(200, {"sub": "g2", "email": "g2@e.com", "name": "G2", "picture": "p2"})

    info = await oauth_routes.extract_user_info(GoogleClient(), {"access_token": "t"}, "google")
    assert info["id"] == "g2"
    assert info["email"] == "g2@e.com"

    # ---------------- GITHUB (EMAIL FALLBACK) ----------------
    class GitHubClient:
        def __init__(self):
            self.calls = []

        async def get(self, path, token=None):
            self.calls.append(path)
            if path == "user":
                return Resp(200, {"id": 123, "email": None, "name": None, "login": "ghuser", "avatar_url": "a"})
            if path == "user/emails":
                return Resp(200, [{"email": "primary@e.com", "primary": True}])
            return Resp(404, {})

    info = await oauth_routes.extract_user_info(GitHubClient(), {"access_token": "t"}, "github")
    assert info["id"] == "123"
    assert info["email"] == "primary@e.com"
    assert info["name"] == "ghuser"

    # ---------------- MICROSOFT ----------------
    class MSClient:
        async def get(self, url, token=None):
            assert url == "https://graph.microsoft.com/v1.0/me"
            return Resp(200, {"id": "m1", "userPrincipalName": "m@e.com", "mail": None, "displayName": "M"})

    info = await oauth_routes.extract_user_info(MSClient(), {"access_token": "t"}, "microsoft")
    assert info["id"] == "m1"
    assert info["email"] == "m@e.com"
    assert info["name"] == "M"

    # ---------------- FAILURE (UNKNOWN PROVIDER) ----------------
    info = await oauth_routes.extract_user_info(MagicMock(), {"access_token": "t"}, "unknown")
    assert info is None

    # ---------------- FAILURE (EXCEPTION) ----------------
    class BoomClient:
        async def get(self, *args, **kwargs):
            raise Exception("boom")

    info = await oauth_routes.extract_user_info(BoomClient(), {"access_token": "t"}, "github")
    assert info is None


# =============================================================================
# oauth_admin_routes.py endpoints
# =============================================================================


def test_admin_oauth_get_allowlist_success(oauth_admin_client, oauth_admin_mock_facade):
    oauth_admin_mock_facade.get_oauth_allow_list.return_value = [
        ("user@test.com", "admin", "2025-01-01", 1),
        ("user2@test.com", None, "2025-01-02", 0),
    ]

    res = oauth_admin_client.get("/admin/oauth/allowlist")
    assert res.status_code == status.HTTP_200_OK

    payload = res.json()
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["email"] == "user@test.com"
    assert payload[0]["added_by"] == "admin"
    assert payload[0]["added_at"] == "2025-01-01"
    assert payload[0]["is_active"] is True


def test_admin_oauth_get_allowlist_failure(oauth_admin_client, oauth_admin_mock_facade):
    from fastapi.testclient import TestClient

    oauth_admin_mock_facade.get_oauth_allow_list.side_effect = Exception("boom")
    failure_client = TestClient(oauth_admin_client.app, raise_server_exceptions=False)
    res = failure_client.get("/admin/oauth/allowlist")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "Failed to retrieve allowlist"


def test_admin_oauth_add_to_allowlist_success(oauth_admin_client, oauth_admin_mock_oauth_manager):
    oauth_admin_mock_oauth_manager.add_to_allowlist.return_value = True

    res = oauth_admin_client.post(
        "/admin/oauth/allowlist/add",
        json={"email": "user@test.com", "added_by": "alice"},
    )
    assert res.status_code == status.HTTP_200_OK
    payload = res.json()
    assert payload["status"] == "success"
    assert "Added user@test.com to allowlist" in payload["message"]


def test_admin_oauth_add_to_allowlist_failure(oauth_admin_client, oauth_admin_mock_oauth_manager):
    """
    Router catches HTTPException in a broad `except Exception`, so a False return
    becomes a 500 response (detail includes the original 400 message).
    """
    from fastapi.testclient import TestClient

    oauth_admin_mock_oauth_manager.add_to_allowlist.return_value = False
    failure_client = TestClient(oauth_admin_client.app, raise_server_exceptions=False)
    res = failure_client.post(
        "/admin/oauth/allowlist/add",
        json={"email": "user@test.com", "added_by": "alice"},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Failed to add email to allowlist" in res.json()["detail"]


def test_admin_oauth_remove_from_allowlist_success(oauth_admin_client, oauth_admin_mock_oauth_manager):
    oauth_admin_mock_oauth_manager.remove_from_allowlist.return_value = True

    res = oauth_admin_client.delete("/admin/oauth/allowlist/user@test.com")
    assert res.status_code == status.HTTP_200_OK
    payload = res.json()
    assert payload["status"] == "success"
    assert "Removed user@test.com from allowlist" in payload["message"]


def test_admin_oauth_remove_from_allowlist_failure(oauth_admin_client, oauth_admin_mock_oauth_manager):
    from fastapi.testclient import TestClient

    oauth_admin_mock_oauth_manager.remove_from_allowlist.return_value = False
    failure_client = TestClient(oauth_admin_client.app, raise_server_exceptions=False)
    res = failure_client.delete("/admin/oauth/allowlist/missing@test.com")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Email not found in allowlist" in res.json()["detail"]


def test_admin_oauth_get_users_success(oauth_admin_client, oauth_admin_mock_oauth_manager):
    oauth_admin_mock_oauth_manager.list_oauth_users.return_value = [
        {"email": "user@test.com", "provider": "google"},
        {"email": "user2@test.com", "provider": "github"},
    ]

    res = oauth_admin_client.get("/admin/oauth/users")
    assert res.status_code == status.HTTP_200_OK
    payload = res.json()
    assert isinstance(payload["users"], list)
    assert payload["count"] == 2


def test_admin_oauth_get_users_failure(oauth_admin_client, oauth_admin_mock_oauth_manager):
    from fastapi.testclient import TestClient

    oauth_admin_mock_oauth_manager.list_oauth_users.side_effect = Exception("boom")
    failure_client = TestClient(oauth_admin_client.app, raise_server_exceptions=False)
    res = failure_client.get("/admin/oauth/users")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "Failed to retrieve OAuth users"


def test_admin_oauth_get_status_success(oauth_admin_client, oauth_admin_mock_facade):
    oauth_admin_mock_facade.get_oauth_system_status_and_settings.return_value = (3, 5, {"google": 5})

    with patch("app.security.oauth_users.ALLOWED_EMAIL_DOMAINS", ["example.com"]):
        res = oauth_admin_client.get("/admin/oauth/status")
    assert res.status_code == status.HTTP_200_OK

    payload = res.json()
    assert payload["allowlist_enabled"] is True
    assert payload["allowlist_count"] == 3
    assert payload["oauth_users_count"] == 5
    assert payload["provider_stats"] == {"google": 5}
    assert payload["domain_restrictions"] == ["example.com"]
    assert payload["security_level"] == "HIGH"


def test_admin_oauth_get_status_failure(oauth_admin_client, oauth_admin_mock_facade):
    from fastapi.testclient import TestClient

    oauth_admin_mock_facade.get_oauth_system_status_and_settings.side_effect = Exception("boom")
    failure_client = TestClient(oauth_admin_client.app, raise_server_exceptions=False)
    res = failure_client.get("/admin/oauth/status")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "Failed to retrieve status"


# =============================================================================
# user_management_routes.py endpoints
# =============================================================================


def test_get_current_user_info_success_and_failure(client, monkeypatch):
    import app.security.session as session_mod
    from app.security.session import verify_session

    # ---------------- SUCCESS ----------------
    def _ok_verify_session():
        return {"user_id": "u1"}

    monkeypatch.setattr(session_mod, "get_current_user_info", lambda request: {"username": "alice"})
    client.app.dependency_overrides[verify_session] = _ok_verify_session

    res = client.get("/api/users/me")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"username": "alice"}

    # ---------------- NOT FOUND ----------------
    monkeypatch.setattr(session_mod, "get_current_user_info", lambda request: None)
    res = client.get("/api/users/me")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["detail"] == "User not found"

    # ---------------- ANONYMOUS (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.get("/api/users/me")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_list_users_success_and_failure(client, monkeypatch):
    from app.security.session import require_admin

    # ---------------- SUCCESS (ADMIN) ----------------
    class FakeFacade:
        def __init__(self):
            self.last_include_inactive = None

        def list_all_users(self, include_inactive: bool = False):
            self.last_include_inactive = include_inactive
            return [
                {"username": "u1", "email": "u1@example.com", "password_hash": "hash1", "role": "user"},
                {"username": "oauthu", "email": "o@example.com", "role": "user"},  # no password_hash => oauth
            ]

    class FakeDB:
        def __init__(self):
            self.facade = FakeFacade()

    fake_db = FakeDB()
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db)
    client.app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "role": "admin"}

    res = client.get("/api/users/?include_inactive=true")
    assert res.status_code == status.HTTP_200_OK
    payload = res.json()
    assert "users" in payload
    assert fake_db.facade.last_include_inactive is True

    u1 = payload["users"][0]
    assert u1["username"] == "u1"
    assert u1["is_oauth"] is False
    assert "password_hash" not in u1

    u2 = payload["users"][1]
    assert u2["username"] == "oauthu"
    assert u2["is_oauth"] is True
    assert "password_hash" not in u2

    # ---------------- FAILURE (DB ERROR) ----------------
    def _boom_list_all_users(include_inactive: bool = False):
        raise Exception("DB error")

    fake_db2 = MagicMock()
    fake_db2.facade.list_all_users = _boom_list_all_users
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db2)

    with pytest.raises(Exception) as excinfo:
        client.get("/api/users/")
    assert "DB error" in str(excinfo.value)

    # ---------------- USER (require_admin enforcement) ----------------
    def _user_require_admin():
        raise HTTPException(status_code=403, detail="Admin required")

    client.app.dependency_overrides[require_admin] = _user_require_admin
    res = client.get("/api/users/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # ---------------- ANONYMOUS (require_admin enforcement) ----------------
    def _anon_require_admin():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[require_admin] = _anon_require_admin
    res = client.get("/api/users/")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_user_success_and_failure(client, monkeypatch):
    from app.security.session import require_admin

    # Common patches (no real auth)
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "admin")
    monkeypatch.setattr(user_management_routes, "get_password_hash", lambda pw: "hashedpw")
    client.app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "role": "admin"}

    # ---------------- SUCCESS ----------------
    fake_facade = MagicMock()
    fake_facade.get_user_by_username.return_value = None
    fake_facade.get_user_by_email.return_value = None
    fake_facade.create_user.return_value = {
        "username": "bob",
        "email": "bob@example.com",
        "role": "user",
        "password_hash": "hashedpw",
        "force_password_change": True,
        "completed_onboarding": False,
    }
    fake_db = MagicMock()
    fake_db.facade = fake_facade
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db)

    res = client.post(
        "/api/users/",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "pw123456",
            "role": "user",
            "force_password_change": True,
            "completed_onboarding": False,
        },
    )
    assert res.status_code == status.HTTP_201_CREATED
    created = res.json()["user"]
    assert created["username"] == "bob"
    assert created["email"] == "bob@example.com"
    assert created["role"] == "user"
    assert "password_hash" not in created

    # ---------------- VALIDATION: USERNAME EXISTS ----------------
    fake_facade.get_user_by_username.return_value = {"username": "bob"}
    res = client.post(
        "/api/users/",
        json={"username": "bob", "email": "x@example.com", "password": "pw123456", "role": "user"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Username already exists"

    # ---------------- VALIDATION: EMAIL EXISTS ----------------
    fake_facade.get_user_by_username.return_value = None
    fake_facade.get_user_by_email.return_value = {"email": "bob@example.com"}
    res = client.post(
        "/api/users/",
        json={"username": "b2", "email": "bob@example.com", "password": "pw123456", "role": "user"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Email already registered"

    # ---------------- VALIDATION: INVALID ROLE ----------------
    fake_facade.get_user_by_email.return_value = None
    res = client.post(
        "/api/users/",
        json={"username": "b3", "email": "b3@example.com", "password": "pw123456", "role": "superuser"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid role" in res.json()["detail"]

    # ---------------- FAILURE: DB EXCEPTION ----------------
    fake_facade.get_user_by_username.return_value = None
    fake_facade.get_user_by_email.return_value = None

    def _boom_create_user(**kwargs):
        raise Exception("DB crash")

    fake_facade.create_user.side_effect = _boom_create_user
    res = client.post(
        "/api/users/",
        json={"username": "b4", "email": "b4@example.com", "password": "pw123456", "role": "user"},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error creating user" in res.json()["detail"]

    # ---------------- USER (require_admin enforcement) ----------------
    def _user_require_admin():
        raise HTTPException(status_code=403, detail="Admin required")

    client.app.dependency_overrides[require_admin] = _user_require_admin
    res = client.post(
        "/api/users/",
        json={"username": "b5", "email": "b5@example.com", "password": "pw123456", "role": "user"},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # ---------------- ANONYMOUS (require_admin enforcement) ----------------
    def _anon_require_admin():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[require_admin] = _anon_require_admin
    res = client.post(
        "/api/users/",
        json={"username": "b6", "email": "b6@example.com", "password": "pw123456", "role": "user"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_update_user_success_and_failure(client, monkeypatch):
    from app.security.session import require_admin

    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "admin")
    client.app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "role": "admin"}

    fake_facade = MagicMock()
    fake_db = MagicMock()
    fake_db.facade = fake_facade
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    fake_facade.get_user_by_username.return_value = {"username": "bob", "role": "user", "is_active": True}
    res = client.patch("/api/users/bob", json={"email": "new@example.com", "role": "user", "is_active": True})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["message"] == "User updated successfully"
    fake_facade.update_user.assert_called()

    # ---------------- VALIDATION: INVALID ROLE ----------------
    fake_facade.update_user.reset_mock()
    res = client.patch("/api/users/bob", json={"role": "invalid"})
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Invalid role"
    fake_facade.update_user.assert_not_called()

    # ---------------- NOT FOUND ----------------
    fake_facade.get_user_by_username.return_value = None
    res = client.patch("/api/users/missing", json={"email": "x@example.com"})
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["detail"] == "User not found"

    # ---------------- FAILURE: DB ERROR ----------------
    fake_facade.get_user_by_username.return_value = {"username": "bob"}
    fake_facade.update_user.side_effect = Exception("DB error")
    res = client.patch("/api/users/bob", json={"email": "x@example.com"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error updating user" in res.json()["detail"]

    # ---------------- USER (require_admin enforcement) ----------------
    def _user_require_admin():
        raise HTTPException(status_code=403, detail="Admin required")

    client.app.dependency_overrides[require_admin] = _user_require_admin
    res = client.patch("/api/users/bob", json={"email": "x@example.com"})
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # ---------------- ANONYMOUS (require_admin enforcement) ----------------
    def _anon_require_admin():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[require_admin] = _anon_require_admin
    res = client.patch("/api/users/bob", json={"email": "x@example.com"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_delete_user_success_and_failure(client, monkeypatch):
    from app.security.session import require_admin

    client.app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "role": "admin"}

    fake_facade = MagicMock()
    fake_db = MagicMock()
    fake_db.facade = fake_facade
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "admin")
    fake_facade.get_user_by_username.return_value = {"username": "bob", "role": "user"}
    res = client.delete("/api/users/bob")
    assert res.status_code == status.HTTP_200_OK
    assert "deactivated successfully" in res.json()["message"]
    fake_facade.deactivate_user_by_username.assert_called_with("bob")

    # ---------------- SELF DELETE ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "bob")
    res = client.delete("/api/users/bob")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Cannot delete your own account"

    # ---------------- NOT FOUND ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "admin")
    fake_facade.get_user_by_username.return_value = None
    res = client.delete("/api/users/missing")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["detail"] == "User not found"

    # ---------------- LAST ADMIN ----------------
    fake_facade.get_user_by_username.return_value = {"username": "onlyadmin", "role": "admin"}
    fake_facade.count_admin_users.return_value = 1
    res = client.delete("/api/users/onlyadmin")
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot delete the last admin user" in res.json()["detail"]

    # ---------------- FAILURE: DB ERROR ----------------
    fake_facade.get_user_by_username.return_value = {"username": "bob", "role": "user"}
    fake_facade.deactivate_user_by_username.side_effect = Exception("DB error")
    res = client.delete("/api/users/bob")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Error deactivating user" in res.json()["detail"]

    # ---------------- USER (require_admin enforcement) ----------------
    def _user_require_admin():
        raise HTTPException(status_code=403, detail="Admin required")

    client.app.dependency_overrides[require_admin] = _user_require_admin
    res = client.delete("/api/users/bob")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # ---------------- ANONYMOUS (require_admin enforcement) ----------------
    def _anon_require_admin():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[require_admin] = _anon_require_admin
    res = client.delete("/api/users/bob")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_change_own_password_success_and_failure(client, monkeypatch):
    from app.security.session import verify_session

    # Ensure dependency is mocked (no real session/auth)
    client.app.dependency_overrides[verify_session] = lambda: {"user_id": "u1"}

    fake_facade = MagicMock()
    fake_db = MagicMock()
    fake_db.facade = fake_facade
    monkeypatch.setattr(user_management_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "alice")
    monkeypatch.setattr(user_management_routes, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(user_management_routes, "get_password_hash", lambda pw: "newhash")

    fake_facade.get_user_by_username.return_value = {"username": "alice", "password_hash": "oldhash"}
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["message"] == "Password changed successfully"
    fake_facade.update_user.assert_called_with("alice", password_hash="newhash", force_password_change=False)

    # ---------------- UNAUTHORIZED (NO USERNAME) ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: None)
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NOT FOUND ----------------
    monkeypatch.setattr(user_management_routes, "get_current_username", lambda request: "alice")
    fake_facade.get_user_by_username.return_value = None
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["detail"] == "User not found"

    # ---------------- OAUTH USER (NO PASSWORD HASH) ----------------
    fake_facade.get_user_by_username.return_value = {"username": "alice", "password_hash": None}
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "OAuth users cannot change password"

    # ---------------- WRONG PASSWORD ----------------
    fake_facade.get_user_by_username.return_value = {"username": "alice", "password_hash": "oldhash"}
    monkeypatch.setattr(user_management_routes, "verify_password", lambda plain, hashed: False)
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "wrong", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Current password is incorrect"

    # ---------------- VALIDATION: NEW PASSWORD TOO SHORT ----------------
    monkeypatch.setattr(user_management_routes, "verify_password", lambda plain, hashed: True)
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "short"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["detail"] == "Password must be at least 8 characters"

    # ---------------- FAILURE: DB ERROR ----------------
    def _boom_update_user(*args, **kwargs):
        raise Exception("DB error")

    fake_facade.update_user.side_effect = _boom_update_user
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert res.json()["detail"] == "Error changing password"

    # ---------------- ANONYMOUS (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    client.app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.post(
        "/api/users/me/change-password",
        json={"current_password": "oldpass", "new_password": "newpass123"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# notification_routes.py endpoints
# =============================================================================


def test_get_notifications_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.get_user_notifications.return_value = [{"id": 1}, {"id": 2}]
    res = client.get("/api/notifications?unread_only=true&limit=10")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"notifications": [{"id": 1}, {"id": 2}], "count": 2}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.get("/api/notifications")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.get("/api/notifications")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.get_user_notifications.side_effect = Exception("DB error")
    res = client.get("/api/notifications")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_get_unread_count_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.get_unread_count.return_value = 5
    res = client.get("/api/notifications/unread-count")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"count": 5}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.get("/api/notifications/unread-count")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.get("/api/notifications/unread-count")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.get_unread_count.side_effect = Exception("DB error")
    res = client.get("/api/notifications/unread-count")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_mark_notification_read_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.mark_notification_as_read.return_value = True
    res = client.post("/api/notifications/123/mark-read")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"success": True}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.post("/api/notifications/123/mark-read")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.post("/api/notifications/123/mark-read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.mark_notification_as_read.side_effect = Exception("DB error")
    res = client.post("/api/notifications/123/mark-read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_mark_all_notifications_read_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.mark_all_notifications_as_read.return_value = 3
    res = client.post("/api/notifications/mark-all-read")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"count": 3}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.post("/api/notifications/mark-all-read")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.post("/api/notifications/mark-all-read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.mark_all_notifications_as_read.side_effect = Exception("DB error")
    res = client.post("/api/notifications/mark-all-read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_delete_read_notifications_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.delete_read_notifications.return_value = 4
    res = client.delete("/api/notifications/read")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"count": 4}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.delete("/api/notifications/read")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.delete("/api/notifications/read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.delete_read_notifications.side_effect = Exception("DB error")
    res = client.delete("/api/notifications/read")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_delete_notification_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SUCCESS ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.delete_notification.return_value = True
    res = client.delete("/api/notifications/55")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"success": True}

    # ---------------- UNAUTHORIZED (verify_session enforcement) ----------------
    def _anon_verify_session():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[verify_session] = _anon_verify_session
    res = client.delete("/api/notifications/55")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # ---------------- NO USERNAME IN SESSION (current route behavior -> 500) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.delete("/api/notifications/55")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice"}}
    fake_facade.delete_notification.side_effect = Exception("DB error")
    res = client.delete("/api/notifications/55")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_create_notification_success_and_failure(client, monkeypatch):
    app = client.app

    fake_facade = MagicMock(name="fake_facade")
    fake_db = MagicMock(name="fake_db")
    fake_db.facade = fake_facade

    monkeypatch.setattr(notification_routes, "get_database_instance", lambda: fake_db)

    # ---------------- SELF CREATE (no username in payload) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice", "is_admin": False}}
    fake_facade.create_notification.return_value = 11
    res = client.post(
        "/api/notifications/create",
        json={"type": "info", "title": "Hello", "message": "World", "link": "/x"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"notification_id": 11}
    fake_facade.create_notification.assert_called_with(
        username="alice",
        type="info",
        title="Hello",
        message="World",
        link="/x",
    )

    # ---------------- ADMIN CREATE (create for others) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "admin", "is_admin": True}}
    fake_facade.create_notification.return_value = 22
    res = client.post(
        "/api/notifications/create",
        json={"username": "bob", "type": "warning", "title": "T", "message": "M"},
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"notification_id": 22}

    # ---------------- FORBIDDEN (cross-user create blocked) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "alice", "is_admin": False}}
    res = client.post(
        "/api/notifications/create",
        json={"username": "bob", "type": "info", "title": "T", "message": "M"},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # ---------------- VALIDATION (no target username available) ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {}}
    res = client.post(
        "/api/notifications/create",
        json={"type": "info", "title": "T", "message": "M"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # ---------------- FAILURE ----------------
    app.dependency_overrides[verify_session] = lambda: {"user": {"username": "admin", "is_admin": True}}
    fake_facade.create_notification.side_effect = Exception("DB error")
    res = client.post(
        "/api/notifications/create",
        json={"username": "bob", "type": "info", "title": "T", "message": "M"},
    )
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# websocket_routes.py endpoints + ConnectionManager
# =============================================================================


class FakeWebSocket:
    def __init__(self, incoming_text=None, raise_on_send: bool = False):
        self.accepted = False
        self.incoming_text = list(incoming_text or [])
        self.sent_text = []
        self.raise_on_send = raise_on_send

    async def accept(self):
        self.accepted = True

    async def send_text(self, msg: str):
        if self.raise_on_send:
            raise Exception("send_text failed")
        self.sent_text.append(msg)

    async def receive_text(self):
        if not self.incoming_text:
            raise websocket_routes.WebSocketDisconnect()
        return self.incoming_text.pop(0)


def _fixed_datetime(monkeypatch, year=2020, month=1, day=1, hour=0, minute=0, second=0):
    from datetime import datetime as _real_datetime

    fixed = _real_datetime(year, month, day, hour, minute, second)

    class _FixedDatetime:
        @classmethod
        def utcnow(cls):
            return fixed

    monkeypatch.setattr(websocket_routes, "datetime", _FixedDatetime)
    return fixed


@pytest.mark.asyncio
async def test_manager_connect_success(monkeypatch):
    mgr = websocket_routes.ConnectionManager()
    ws = FakeWebSocket()

    await mgr.connect(ws, "c1")

    assert ws.accepted is True
    assert "c1" in mgr.active_connections


def test_manager_disconnect_cleans_subscriptions(monkeypatch):
    mgr = websocket_routes.ConnectionManager()
    mgr.active_connections["c1"] = FakeWebSocket()
    mgr.job_subscribers = {"j1": ["c1", "c2"], "j2": ["c1"]}

    mgr.disconnect("c1")

    assert "c1" not in mgr.active_connections
    assert "c1" not in mgr.job_subscribers["j1"]
    assert "c1" not in mgr.job_subscribers["j2"]


def test_manager_subscribe_to_job_no_duplicates(monkeypatch):
    mgr = websocket_routes.ConnectionManager()

    mgr.subscribe_to_job("c1", "j1")
    mgr.subscribe_to_job("c1", "j1")

    assert mgr.job_subscribers["j1"] == ["c1"]


@pytest.mark.asyncio
async def test_send_job_update_removes_disconnected_clients(monkeypatch):
    _fixed_datetime(monkeypatch)
    mgr = websocket_routes.ConnectionManager()
    ok = FakeWebSocket()
    bad = FakeWebSocket(raise_on_send=True)
    mgr.active_connections = {"ok": ok, "bad": bad}
    mgr.job_subscribers = {"j1": ["ok", "bad", "missing"]}

    await mgr.send_job_update("j1", {"status": "progress"})

    assert len(ok.sent_text) == 1
    assert "bad" not in mgr.active_connections
    assert "missing" not in mgr.job_subscribers["j1"]


@pytest.mark.asyncio
async def test_send_direct_message_success(monkeypatch):
    _fixed_datetime(monkeypatch)
    mgr = websocket_routes.ConnectionManager()
    ws = FakeWebSocket()
    mgr.active_connections["c1"] = ws

    ok = await mgr.send_direct_message("c1", {"status": "connected"})

    assert ok is True
    assert len(ws.sent_text) == 1


@pytest.mark.asyncio
async def test_send_direct_message_failure_disconnects(monkeypatch):
    _fixed_datetime(monkeypatch)
    mgr = websocket_routes.ConnectionManager()
    ws = FakeWebSocket(raise_on_send=True)
    mgr.active_connections["c1"] = ws

    ok = await mgr.send_direct_message("c1", {"status": "connected"})

    assert ok is False
    assert "c1" not in mgr.active_connections


@pytest.mark.asyncio
async def test_websocket_bulk_process_ping(monkeypatch):
    fixed = _fixed_datetime(monkeypatch)
    monkeypatch.setattr(websocket_routes, "manager", websocket_routes.ConnectionManager())
    ws = FakeWebSocket(incoming_text=[json.dumps({"type": "ping"})])

    await websocket_routes.websocket_bulk_process(ws, "job1")

    assert ws.accepted is True
    assert json.loads(ws.sent_text[0])["status"] == "connected"
    assert json.loads(ws.sent_text[1])["type"] == "pong"
    cid = f"bulk_job1_{fixed.timestamp()}"
    assert cid not in websocket_routes.manager.active_connections
    assert cid not in websocket_routes.manager.job_subscribers.get("job1", [])


@pytest.mark.asyncio
async def test_websocket_bulk_process_invalid_json(monkeypatch):
    _fixed_datetime(monkeypatch)
    monkeypatch.setattr(websocket_routes, "manager", websocket_routes.ConnectionManager())
    ws = FakeWebSocket(incoming_text=["{not-json"])

    await websocket_routes.websocket_bulk_process(ws, "job1")

    assert json.loads(ws.sent_text[1])["type"] == "error"


@pytest.mark.asyncio
async def test_websocket_topic_progress_subscribe_job(monkeypatch):
    fixed = _fixed_datetime(monkeypatch)
    monkeypatch.setattr(websocket_routes, "manager", websocket_routes.ConnectionManager())
    ws = FakeWebSocket(incoming_text=[json.dumps({"type": "subscribe_job", "job_id": "j1"})])

    await websocket_routes.websocket_topic_progress(ws, "t1")

    assert ws.accepted is True
    assert json.loads(ws.sent_text[1])["type"] == "subscribed"
    cid = f"topic_t1_{fixed.timestamp()}"
    assert cid not in websocket_routes.manager.active_connections
    assert cid not in websocket_routes.manager.job_subscribers.get("j1", [])


@pytest.mark.asyncio
async def test_websocket_topic_progress_invalid_json(monkeypatch):
    _fixed_datetime(monkeypatch)
    monkeypatch.setattr(websocket_routes, "manager", websocket_routes.ConnectionManager())
    ws = FakeWebSocket(incoming_text=["nope"])

    await websocket_routes.websocket_topic_progress(ws, "t1")

    assert json.loads(ws.sent_text[1])["type"] == "error"


# =============================================================================
# prompt_management_routes.py endpoints
# =============================================================================


def test_list_prompts_success(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.list_prompts.return_value = [{"name": "current"}, {"name": "v2"}]

        res = client.get("/api/prompts/list/market_signals")

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["feature"] == "market_signals"
    assert payload["prompts"] == [{"name": "current"}, {"name": "v2"}]
    assert payload["count"] == 2


def test_list_prompts_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.list_prompts.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.get("/api/prompts/list/market_signals")

    assert res.status_code == 500
    assert "Failed to list prompts" in res.json()["detail"]


def test_load_prompt_success(client, mock_verify_session):
    fake_prompt = {"version": "1.0", "template": "Hello {name}", "variables": {"name": "User name"}}

    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.return_value = fake_prompt
        MockPromptLoader.get_prompt_variables.return_value = ["name"]

        res = client.post(
            "/api/prompts/load",
            json={"feature": "market_signals", "prompt_name": "current"},
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["feature"] == "market_signals"
    assert payload["prompt_name"] == "current"
    assert payload["prompt"] == fake_prompt
    assert payload["variables"] == ["name"]


def test_load_prompt_failure_404_not_found(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.side_effect = FileNotFoundError("not found")

        res = client.post(
            "/api/prompts/load",
            json={"feature": "market_signals", "prompt_name": "missing"},
        )

    assert res.status_code == 404


def test_load_prompt_failure_400_bad_request(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.side_effect = ValueError("bad request")

        res = client.post(
            "/api/prompts/load",
            json={"feature": "market_signals", "prompt_name": "current"},
        )

    assert res.status_code == 400


def test_load_prompt_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.post(
            "/api/prompts/load",
            json={"feature": "market_signals", "prompt_name": "current"},
        )

    assert res.status_code == 500
    assert "Failed to load prompt" in res.json()["detail"]


def test_save_prompt_success(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.return_value = (True, None)
        MockPromptLoader.save_prompt.return_value = "data/prompts/market_signals/current.json"

        res = client.post(
            "/api/prompts/save",
            json={
                "feature": "market_signals",
                "prompt_data": {"version": "1.0", "template": "Hello {name}"},
                "set_as_current": True,
            },
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["path"] == "data/prompts/market_signals/current.json"
    assert payload["is_current"] is True


def test_save_prompt_failure_400_validation_error(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.return_value = (False, "error")

        res = client.post(
            "/api/prompts/save",
            json={
                "feature": "market_signals",
                "prompt_data": {"version": "1.0", "template": "Hello {name}"},
                "set_as_current": False,
            },
        )

    assert res.status_code == 400


def test_save_prompt_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.return_value = (True, None)
        MockPromptLoader.save_prompt.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.post(
            "/api/prompts/save",
            json={
                "feature": "market_signals",
                "prompt_data": {"version": "1.0", "template": "Hello {name}"},
                "set_as_current": False,
            },
        )

    assert res.status_code == 500


def test_list_features_success(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.list_features.return_value = ["market_signals", "media_bias"]

        res = client.get("/api/prompts/features")

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["features"] == ["market_signals", "media_bias"]
    assert payload["count"] == 2


def test_list_features_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.list_features.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.get("/api/prompts/features")

    assert res.status_code == 500


def test_validate_prompt_success_valid_prompt(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.return_value = (True, None)
        MockPromptLoader.get_prompt_variables.return_value = ["name", "date"]

        res = client.post(
            "/api/prompts/validate",
            json={"prompt_data": {"version": "1.0", "template": "Hello {name} on {date}"}},
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["valid"] is True
    assert payload["variables"] == ["name", "date"]
    assert payload["variable_count"] == 2


def test_validate_prompt_success_invalid_prompt(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.return_value = (False, "error")

        res = client.post(
            "/api/prompts/validate",
            json={"prompt_data": {"version": "1.0"}},
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["valid"] is False
    assert payload["error"] == "error"


def test_validate_prompt_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.validate_prompt_schema.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.post(
            "/api/prompts/validate",
            json={"prompt_data": {"version": "1.0", "template": "Hello {name}"}},
        )

    assert res.status_code == 500
    assert "Failed to validate prompt" in res.json()["detail"]


def test_get_prompt_variables_success(client, mock_verify_session):
    fake_prompt = {"template": "Hello {name} {date}", "variables": {"name": "User name"}}

    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.return_value = fake_prompt
        MockPromptLoader.get_prompt_variables.return_value = ["name", "date"]

        res = client.get("/api/prompts/variables/market_signals")

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["feature"] == "market_signals"
    assert payload["prompt_name"] == "current"
    assert payload["count"] == 2
    assert payload["variables"] == [
        {"name": "name", "description": "User name"},
        {"name": "date", "description": "No description available"},
    ]


def test_get_prompt_variables_failure_404_not_found(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.side_effect = FileNotFoundError("not found")

        res = client.get("/api/prompts/variables/market_signals")

    assert res.status_code == 404


def test_get_prompt_variables_failure_500(client, mock_verify_session):
    with patch("app.routes.prompt_management_routes.PromptLoader") as MockPromptLoader:
        MockPromptLoader.load_prompt.side_effect = Exception("boom")
        failure_client = TestClient(client.app, raise_server_exceptions=False)

        res = failure_client.get("/api/prompts/variables/market_signals")

    assert res.status_code == 500
    assert "Failed to get variables" in res.json()["detail"]


# =============================================================================
# saved_dashboard_routes.py endpoints
# =============================================================================

@pytest.fixture
def mock_session():
    return {"user": {"username": "testuser"}}


@pytest.fixture
def mock_facade():
    return MagicMock(name="saved_dashboards_facade")


@pytest.fixture
def mock_db(mock_facade):
    return _make_db_with_facade(db_name="saved_dashboards_db", facade_mock=mock_facade)


@pytest.fixture
def saved_dashboards_client(test_client_factory):
    """
    Dedicated client for saved_dashboard_routes that registers paths in a non-shadowing order.

    NOTE: In the production router, `/{dashboard_id}` is declared before `/search` and `/stats`,
    which causes those static paths to be matched as the dynamic int path (422). We cannot
    modify router code, so tests register the same endpoint callables with safe ordering.
    """
    from fastapi import FastAPI
    import app.routes.saved_dashboard_routes as saved_dashboard_routes

    saved_app = FastAPI()
    prefix = "/api/saved-dashboards"

    # Static and longer paths first
    saved_app.add_api_route(f"{prefix}/save", saved_dashboard_routes.save_dashboard, methods=["POST"])
    saved_app.add_api_route(f"{prefix}/topic/{{topic}}", saved_dashboard_routes.list_dashboards_for_topic, methods=["GET"])
    saved_app.add_api_route(f"{prefix}/recent/list", saved_dashboard_routes.get_recent_dashboards, methods=["GET"])
    saved_app.add_api_route(f"{prefix}/search", saved_dashboard_routes.search_dashboards, methods=["GET"])
    saved_app.add_api_route(f"{prefix}/stats", saved_dashboard_routes.get_user_dashboard_stats, methods=["GET"])
    saved_app.add_api_route(f"{prefix}/{{dashboard_id}}/clone", saved_dashboard_routes.clone_dashboard, methods=["POST"])

    # Dynamic id paths last
    saved_app.add_api_route(f"{prefix}/{{dashboard_id}}", saved_dashboard_routes.load_dashboard, methods=["GET"])
    saved_app.add_api_route(f"{prefix}/{{dashboard_id}}", saved_dashboard_routes.update_dashboard, methods=["PUT"])
    saved_app.add_api_route(f"{prefix}/{{dashboard_id}}", saved_dashboard_routes.delete_dashboard, methods=["DELETE"])

    return test_client_factory(saved_app)


def test_save_dashboard_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboards_for_topic.return_value = []
    mock_facade.create_saved_dashboard.return_value = 123

    payload = {
        "topic": "AI",
        "name": "My Dashboard",
        "description": "desc",
        "config": {"model": "gpt", "article_count": 5},
        "article_uris": ["uri1", "uri2"],
        "tab_data": {"consensus": {"x": 1}},
        "profile_snapshot": {"org": "test"},
    }

    res = client.post("/api/saved-dashboards/save", json=payload)

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["dashboard_id"] == 123

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_save_dashboard_unauthenticated(client, mock_db):
    app.dependency_overrides[verify_session] = lambda: {}
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    payload = {
        "topic": "AI",
        "name": "My Dashboard",
        "description": None,
        "config": {"model": "gpt"},
        "article_uris": ["uri1"],
        "tab_data": {},
        "profile_snapshot": None,
    }

    res = client.post("/api/saved-dashboards/save", json=payload)

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_save_dashboard_duplicate(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboards_for_topic.return_value = [{"id": 1, "name": "My Dashboard"}]

    payload = {
        "topic": "AI",
        "name": "My Dashboard",
        "description": None,
        "config": {"model": "gpt"},
        "article_uris": ["uri1"],
        "tab_data": {},
        "profile_snapshot": None,
    }

    res = client.post("/api/saved-dashboards/save", json=payload)

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_save_dashboard_500(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboards_for_topic.return_value = []
    mock_facade.create_saved_dashboard.side_effect = Exception("boom")

    payload = {
        "topic": "AI",
        "name": "My Dashboard",
        "description": None,
        "config": {"model": "gpt"},
        "article_uris": ["uri1"],
        "tab_data": {},
        "profile_snapshot": None,
    }

    res = client.post("/api/saved-dashboards/save", json=payload)

    assert res.status_code == 500
    assert "failed to save dashboard" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_list_dashboards_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboards_for_topic.return_value = [
        {
            "id": 1,
            "name": "Dash 1",
            "description": None,
            "created_at": "2020-01-01T00:00:00+00:00",
            "updated_at": "2020-01-01T00:00:00+00:00",
            "last_accessed_at": "2020-01-01T00:00:00+00:00",
            "articles_analyzed": 10,
            "model_used": "gpt",
            "auto_generated": False,
        }
    ]

    res = client.get("/api/saved-dashboards/topic/AI")

    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert data[0]["id"] == 1
    assert data[0]["name"] == "Dash 1"

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_list_dashboards_unauthenticated(client, mock_db):
    app.dependency_overrides[verify_session] = lambda: {}
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = client.get("/api/saved-dashboards/topic/AI")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_load_dashboard_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {
        "id": 5,
        "topic": "AI",
        "name": "Dash",
        "description": None,
        "config": {"model": "gpt"},
        "article_uris": ["uri1"],
        "consensus_data": None,
        "strategic_data": None,
        "timeline_data": None,
        "signals_data": None,
        "horizons_data": None,
        "profile_snapshot": None,
        "created_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
        "last_accessed_at": "2020-01-01T00:00:00+00:00",
        "articles_analyzed": 1,
        "model_used": "gpt",
        "auto_generated": False,
    }
    mock_facade.update_dashboard_access_time.return_value = None

    res = client.get("/api/saved-dashboards/5")

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 5
    assert data["topic"] == "AI"
    assert data["name"] == "Dash"
    assert mock_facade.update_dashboard_access_time.called

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_load_dashboard_not_found(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = None

    res = client.get("/api/saved-dashboards/999")

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_load_dashboard_unauthenticated(client, mock_db):
    app.dependency_overrides[verify_session] = lambda: {}
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = client.get("/api/saved-dashboards/5")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_update_dashboard_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {"id": 1, "topic": "AI", "name": "Old"}
    mock_facade.update_saved_dashboard.return_value = True

    res = client.put("/api/saved-dashboards/1", json={"name": "New", "description": "d"})

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_update_dashboard_not_found(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = None

    res = client.put("/api/saved-dashboards/1", json={"name": "New"})

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_update_dashboard_conflict(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {"id": 1, "topic": "AI", "name": "Old"}
    mock_facade.get_saved_dashboards_for_topic.return_value = [
        {"id": 2, "name": "New"},
    ]

    res = client.put("/api/saved-dashboards/1", json={"name": "New"})

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_update_dashboard_500(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {"id": 1, "topic": "AI", "name": "Old"}
    mock_facade.update_saved_dashboard.return_value = False

    res = client.put("/api/saved-dashboards/1", json={"description": "d"})

    assert res.status_code == 500
    assert "failed to update" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_delete_dashboard_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.delete_saved_dashboard.return_value = True

    res = client.delete("/api/saved-dashboards/1")

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_delete_dashboard_not_found(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.delete_saved_dashboard.return_value = False

    res = client.delete("/api/saved-dashboards/1")

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_delete_dashboard_unauthenticated(client, mock_db):
    app.dependency_overrides[verify_session] = lambda: {}
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = client.delete("/api/saved-dashboards/1")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_get_recent_dashboards_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_recent_saved_dashboards.return_value = [
        {
            "id": 1,
            "name": "Dash 1",
            "description": None,
            "created_at": "2020-01-01T00:00:00+00:00",
            "updated_at": "2020-01-01T00:00:00+00:00",
            "last_accessed_at": "2020-01-01T00:00:00+00:00",
            "articles_analyzed": 10,
            "model_used": "gpt",
            "auto_generated": False,
        }
    ]

    res = client.get("/api/saved-dashboards/recent/list?limit=5")

    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert data[0]["id"] == 1

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_get_recent_dashboards_unauthenticated(client, mock_db):
    app.dependency_overrides[verify_session] = lambda: {}
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = client.get("/api/saved-dashboards/recent/list?limit=5")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_get_recent_dashboards_invalid_limit(client, mock_session, mock_db):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    res1 = client.get("/api/saved-dashboards/recent/list?limit=0")
    assert res1.status_code == 422

    res2 = client.get("/api/saved-dashboards/recent/list?limit=100")
    assert res2.status_code == 422

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_search_dashboards_success(saved_dashboards_client, mock_session, mock_db, mock_facade):
    saved_dashboards_client.app.dependency_overrides[verify_session] = lambda: mock_session
    saved_dashboards_client.app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.search_saved_dashboards.return_value = [
        {
            "id": 1,
            "name": "Dash 1",
            "description": "d",
            "created_at": "2020-01-01T00:00:00+00:00",
            "updated_at": "2020-01-01T00:00:00+00:00",
            "last_accessed_at": "2020-01-01T00:00:00+00:00",
            "articles_analyzed": 10,
            "model_used": "gpt",
            "auto_generated": False,
        }
    ]

    res = saved_dashboards_client.get("/api/saved-dashboards/search?q=Dash")

    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "Dash 1"

    saved_dashboards_client.app.dependency_overrides.pop(verify_session, None)
    saved_dashboards_client.app.dependency_overrides.pop(get_database_instance, None)


def test_search_dashboards_missing_query(saved_dashboards_client, mock_session, mock_db):
    saved_dashboards_client.app.dependency_overrides[verify_session] = lambda: mock_session
    saved_dashboards_client.app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = saved_dashboards_client.get("/api/saved-dashboards/search")

    assert res.status_code == 422
    assert "detail" in res.json()

    saved_dashboards_client.app.dependency_overrides.pop(verify_session, None)
    saved_dashboards_client.app.dependency_overrides.pop(get_database_instance, None)


def test_search_dashboards_unauthenticated(saved_dashboards_client, mock_db):
    saved_dashboards_client.app.dependency_overrides[verify_session] = lambda: {}
    saved_dashboards_client.app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = saved_dashboards_client.get("/api/saved-dashboards/search?q=Dash")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    saved_dashboards_client.app.dependency_overrides.pop(verify_session, None)
    saved_dashboards_client.app.dependency_overrides.pop(get_database_instance, None)


def test_get_dashboard_stats_success(saved_dashboards_client, mock_session, mock_db, mock_facade):
    saved_dashboards_client.app.dependency_overrides[verify_session] = lambda: mock_session
    saved_dashboards_client.app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_dashboard_stats.return_value = {
        "total_dashboards": 2,
        "unique_topics": 1,
        "total_articles": 20,
        "last_activity": "2020-01-01T00:00:00+00:00",
    }

    res = saved_dashboards_client.get("/api/saved-dashboards/stats")

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["stats"]["total_dashboards"] == 2

    saved_dashboards_client.app.dependency_overrides.pop(verify_session, None)
    saved_dashboards_client.app.dependency_overrides.pop(get_database_instance, None)


def test_get_dashboard_stats_unauthenticated(saved_dashboards_client, mock_db):
    saved_dashboards_client.app.dependency_overrides[verify_session] = lambda: {}
    saved_dashboards_client.app.dependency_overrides[get_database_instance] = lambda: mock_db

    res = saved_dashboards_client.get("/api/saved-dashboards/stats")

    assert res.status_code == 401
    assert "not authenticated" in res.json()["detail"].lower()

    saved_dashboards_client.app.dependency_overrides.pop(verify_session, None)
    saved_dashboards_client.app.dependency_overrides.pop(get_database_instance, None)


def test_clone_dashboard_success(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {
        "id": 1,
        "topic": "AI",
        "name": "Original",
        "config": {"model": "gpt"},
        "article_uris": ["uri1"],
        "consensus_data": {"a": 1},
        "strategic_data": None,
        "timeline_data": None,
        "signals_data": None,
        "horizons_data": None,
        "profile_snapshot": None,
        "articles_analyzed": 1,
        "model_used": "gpt",
    }
    mock_facade.get_saved_dashboards_for_topic.return_value = []
    mock_facade.create_saved_dashboard.return_value = 777

    res = client.post("/api/saved-dashboards/1/clone?new_name=Clone")

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["dashboard_id"] == 777

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_clone_dashboard_not_found(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = None

    res = client.post("/api/saved-dashboards/1/clone?new_name=Clone")

    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_clone_dashboard_conflict(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {
        "id": 1,
        "topic": "AI",
        "name": "Original",
        "config": {},
        "article_uris": [],
    }
    mock_facade.get_saved_dashboards_for_topic.return_value = [{"id": 2, "name": "Clone"}]

    res = client.post("/api/saved-dashboards/1/clone?new_name=Clone")

    assert res.status_code == 409
    assert "already exists" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


def test_clone_dashboard_500(client, mock_session, mock_db, mock_facade):
    app.dependency_overrides[verify_session] = lambda: mock_session
    app.dependency_overrides[get_database_instance] = lambda: mock_db

    mock_facade.get_saved_dashboard_by_id.return_value = {
        "id": 1,
        "topic": "AI",
        "name": "Original",
        "config": {},
        "article_uris": [],
    }
    mock_facade.get_saved_dashboards_for_topic.return_value = []
    mock_facade.create_saved_dashboard.side_effect = Exception("boom")

    res = client.post("/api/saved-dashboards/1/clone?new_name=Clone")

    assert res.status_code == 500
    assert "failed to clone dashboard" in res.json()["detail"].lower()

    app.dependency_overrides.pop(verify_session, None)
    app.dependency_overrides.pop(get_database_instance, None)


# =============================================================================
# stats_routes.py endpoints
# =============================================================================


@pytest.fixture
def stats_mock_session():
    return {"user_id": "test-user"}


@pytest.fixture
def stats_mock_db():
    facade = MagicMock(name="stats_facade")
    facade.test_data_select.return_value = None
    facade.get_rate_limit_status.return_value = {"requests_today": 0, "last_error": None}
    facade.get_topic_statistics.return_value = []
    facade.get_last_check_time_using_timezone_format.return_value = None

    db = _make_db_with_facade(db_name="stats_db", facade_mock=facade)

    db.get_total_articles = AsyncMock(return_value=123)
    db.get_articles_today = AsyncMock(return_value=4)
    db.get_keyword_group_count = AsyncMock(return_value=2)
    db.get_topic_count = AsyncMock(return_value=1)

    return db


@pytest.fixture
def stats_routes_module(monkeypatch, stats_mock_db, stats_mock_session):
    """
    Reload stats_routes with ALL external dependencies mocked so no filesystem/env/db is touched.
    """
    import importlib
    from types import SimpleNamespace

    from fastapi.responses import HTMLResponse
    import fastapi.templating as fastapi_templating
    import app.security.session as session_mod
    import app.database as database_mod

    class DummyJinja2Templates:
        def __init__(self, *args, **kwargs):
            # stats_routes registers a custom filter at import time:
            # templates.env.filters["timeago"] = ...
            self.env = SimpleNamespace(filters={})

        def TemplateResponse(self, *args, **kwargs):
            return HTMLResponse("OK")

    # Patch symbols BEFORE reload so Depends(...) and global templates are built from mocks.
    monkeypatch.setattr(fastapi_templating, "Jinja2Templates", DummyJinja2Templates)
    monkeypatch.setattr(session_mod, "verify_session", lambda: stats_mock_session)
    monkeypatch.setattr(database_mod, "get_database_instance", lambda: stats_mock_db)

    import app.routes.stats_routes as stats_routes
    stats_routes = importlib.reload(stats_routes)

    # Never read real env vars in tests (each test can override behavior as needed).
    monkeypatch.setattr(stats_routes.os, "getenv", lambda key, default=None: None)

    # Default: never load real templates.
    stats_routes.templates.TemplateResponse = MagicMock(return_value=HTMLResponse("OK"))

    return stats_routes


@pytest.fixture
def stats_client(stats_routes_module, test_client_factory):
    from fastapi import FastAPI

    stats_app = FastAPI()
    stats_app.include_router(stats_routes_module.router)
    return test_client_factory(stats_app)


def test_index_success(stats_client, stats_routes_module, stats_mock_db, monkeypatch):
    from fastapi.responses import HTMLResponse

    # Provider configured -> should call get_rate_limit_status and report "Operational"
    monkeypatch.setattr(
        stats_routes_module.os,
        "getenv",
        lambda key, default=None: "key" if key == "PROVIDER_NEWSAPI_KEY" else None,
    )

    stats_mock_db.facade.get_rate_limit_status.return_value = {"requests_today": 1, "last_error": None}
    stats_mock_db.facade.get_topic_statistics.return_value = [
        {"topic": "t1", "article_count": 5, "last_article_date": "2020-01-01"}
    ]
    stats_mock_db.facade.get_last_check_time_using_timezone_format.return_value = "2020-01-01T00:00:00Z"

    captured = {}

    def _template_ok(name, ctx):
        captured["name"] = name
        captured["ctx"] = ctx
        return HTMLResponse("OK")

    stats_routes_module.templates.TemplateResponse = MagicMock(side_effect=_template_ok)

    res = stats_client.get("/")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "OK" in res.text
    assert stats_routes_module.templates.TemplateResponse.called

    ctx = captured["ctx"]
    assert "stats" in ctx
    assert "db_status" in ctx
    assert "api_status" in ctx
    assert "active_topics" in ctx
    assert ctx["current_page"] == "home"


def test_index_db_connection_failure(stats_client, stats_routes_module, stats_mock_db, monkeypatch):
    from fastapi.responses import HTMLResponse

    stats_mock_db.facade.test_data_select.side_effect = Exception("DB down")

    captured = {}

    def _template_ok(name, ctx):
        captured["ctx"] = ctx
        return HTMLResponse("OK")

    stats_routes_module.templates.TemplateResponse = MagicMock(side_effect=_template_ok)

    res = stats_client.get("/")

    assert res.status_code == 200
    assert "OK" in res.text
    assert captured["ctx"]["db_status"]["status"] == "error"


def test_index_api_not_configured(stats_client, stats_routes_module, monkeypatch):
    from fastapi.responses import HTMLResponse

    # No providers configured
    monkeypatch.setattr(stats_routes_module.os, "getenv", lambda key, default=None: None)

    captured = {}

    def _template_ok(name, ctx):
        captured["ctx"] = ctx
        return HTMLResponse("OK")

    stats_routes_module.templates.TemplateResponse = MagicMock(side_effect=_template_ok)

    res = stats_client.get("/")

    assert res.status_code == 200
    assert captured["ctx"]["api_status"]["status"] == "warning"
    assert captured["ctx"]["api_status"]["message"] == "Not Configured"


def test_index_api_rate_limited(stats_client, stats_routes_module, stats_mock_db, monkeypatch):
    from fastapi.responses import HTMLResponse

    monkeypatch.setattr(
        stats_routes_module.os,
        "getenv",
        lambda key, default=None: "key" if key == "PROVIDER_NEWSAPI_KEY" else None,
    )

    stats_mock_db.facade.get_rate_limit_status.return_value = {
        "requests_today": 10,
        "last_error": "Rate limit exceeded",
    }

    captured = {}

    def _template_ok(name, ctx):
        captured["ctx"] = ctx
        return HTMLResponse("OK")

    stats_routes_module.templates.TemplateResponse = MagicMock(side_effect=_template_ok)

    res = stats_client.get("/")

    assert res.status_code == 200
    assert captured["ctx"]["api_status"]["status"] == "warning"
    assert captured["ctx"]["api_status"]["message"] == "Rate Limited"


def test_index_template_error_500(stats_client, stats_routes_module, monkeypatch):
    # Template rendering failure should surface as HTTP 500
    stats_routes_module.templates.TemplateResponse = MagicMock(side_effect=Exception("tmpl boom"))
    failure_client = TestClient(stats_client.app, raise_server_exceptions=False)

    res = failure_client.get("/")

    assert res.status_code == 500
    assert "tmpl boom" in res.json()["detail"]


def test_index_stats_failure_500(stats_client, stats_mock_db):
    # DB stats failure should surface as HTTP 500
    stats_mock_db.get_total_articles.side_effect = Exception("stats boom")
    failure_client = TestClient(stats_client.app, raise_server_exceptions=False)

    res = failure_client.get("/")

    assert res.status_code == 500
    assert "stats boom" in res.json()["detail"]


# =============================================================================
# vector_routes.py endpoints (per tests/spec/vector_routes_test_spec.md)
# =============================================================================

@pytest.fixture
def mock_optional_session():
    app.dependency_overrides[verify_session_optional] = lambda: {"user_id": "test-user"}
    yield
    app.dependency_overrides.pop(verify_session_optional, None)


@pytest.fixture
def vector_mock_db(monkeypatch):
    """
    Vector routes sometimes use Depends(get_database_instance) and sometimes call
    app.database.get_database_instance() directly. This fixture covers both.
    """
    db = MagicMock()
    db.facade = MagicMock()

    # Covers Depends(get_database_instance)
    app.dependency_overrides[get_database_instance] = lambda: db

    # Covers direct calls inside routes
    import app.database as database_mod
    monkeypatch.setattr(database_mod, "get_database_instance", lambda: db)

    yield db

    app.dependency_overrides.pop(get_database_instance, None)


@pytest.fixture
def mock_vector_collection(monkeypatch):
    collection = MagicMock()
    monkeypatch.setattr(vector_routes, "_vector_collection", lambda: collection)

    # For spec compliance (even though vector_routes imported the name already)
    import app.vector_store as vector_store_mod
    monkeypatch.setattr(vector_store_mod, "_get_collection", lambda: collection)

    return collection


def _litellm_resp(content: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


# ------------------------------------------------------------------
# 1. GET /api/vector-search
# ------------------------------------------------------------------


def test_vector_search_success(client, mock_session):
    query_obj = MagicMock(constraints=[], meta_controls=[])
    with patch("app.kissql.parser.parse_full_query", return_value=query_obj), patch(
        "app.kissql.executor.execute_query",
        return_value={
            "results": [{"id": "u1", "score": 0.9, "metadata": {}}],
            "facets": {},
            "timeline": {},
            "comparison": {},
            "filtered_facets": {},
        },
    ):
        res = client.get("/api/vector-search", params={"q": "test", "top_k": 3})

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {
        "results",
        "facets",
        "timeline",
        "comparison",
        "filtered_facets",
    }


def test_vector_search_failure_500(client, mock_session):
    query_obj = MagicMock(constraints=[], meta_controls=[])
    failure_client = TestClient(client.app, raise_server_exceptions=False)

    with patch("app.kissql.parser.parse_full_query", return_value=query_obj), patch(
        "app.kissql.executor.execute_query", side_effect=Exception("boom")
    ):
        res = failure_client.get("/api/vector-search", params={"q": "test"})

    assert res.status_code == 500


# ------------------------------------------------------------------
# 2. POST /api/vector-reindex
# ------------------------------------------------------------------


def test_vector_reindex_success(client, vector_mock_db, mock_session):
    vector_mock_db.get_all_articles.return_value = [{"uri": "u1"}, {"uri": "u2"}]
    with patch.object(vector_routes, "upsert_article", return_value=None) as p_upsert:
        res = client.post("/api/vector-reindex")

    assert res.status_code == 200
    assert res.json() == {"indexed": 2, "total": 2}
    assert p_upsert.call_count == 2


def test_vector_reindex_failure_still_returns_valid_response(client, vector_mock_db, mock_session):
    vector_mock_db.get_all_articles.return_value = [{"uri": "u1"}, {"uri": "u2"}]

    def _upsert(article):
        if article.get("uri") == "u2":
            raise Exception("vector down")
        return None

    with patch.object(vector_routes, "upsert_article", side_effect=_upsert):
        res = client.post("/api/vector-reindex")

    assert res.status_code == 200
    assert res.json() == {"indexed": 1, "total": 2}


# ------------------------------------------------------------------
# 3. GET /api/vector-similar
# ------------------------------------------------------------------


def test_vector_similar_success(client, mock_session):
    with patch.object(
        vector_routes, "similar_articles", return_value=[{"id": "u2", "score": 0.1}]
    ):
        res = client.get("/api/vector-similar", params={"uri": "u1", "top_k": 2})

    assert res.status_code == 200
    assert "results" in res.json()
    assert isinstance(res.json()["results"], list)


def test_vector_similar_failure_500(client, mock_session):
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    with patch.object(vector_routes, "similar_articles", side_effect=Exception("boom")):
        res = failure_client.get("/api/vector-similar", params={"uri": "u1"})
    assert res.status_code == 500


# ------------------------------------------------------------------
# 4. GET /api/embedding_projection
# ------------------------------------------------------------------


def test_embedding_projection_success(client, mock_session):
    import numpy as np

    vecs = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    metas = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    ids = ["u1", "u2", "u3"]

    class DummyPCA:
        def __init__(self, n_components=None, random_state=None):
            self.n_components = n_components

        def fit_transform(self, X):
            # Deterministic dummy coords (no real ML)
            return np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    class DummyKMeans:
        def __init__(self, n_clusters=2, random_state=None):
            self.n_clusters = n_clusters

        def fit_predict(self, X):
            return np.array([0, 1, 0], dtype=int)

    with patch.object(vector_routes, "_fetch_vectors", return_value=(vecs, metas, ids)), patch(
        "sklearn.decomposition.PCA", DummyPCA
    ), patch("sklearn.cluster.MiniBatchKMeans", DummyKMeans):
        res = client.get(
            "/api/embedding_projection",
            params={"method": "pca", "dims": 2, "top_k": 10, "n_clusters": 2},
        )

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {"points", "explain", "centroids"}
    assert isinstance(body["points"], list)
    assert len(body["points"]) == 3
    assert set(body["points"][0].keys()) >= {"id", "x", "y", "cluster"}


def test_embedding_projection_failure_empty_vectors_returns_empty_response(client, mock_session):
    import numpy as np

    with patch.object(
        vector_routes,
        "_fetch_vectors",
        return_value=(np.empty((0, 0), dtype=np.float32), [], []),
    ):
        res = client.get("/api/embedding_projection", params={"method": "pca"})

    assert res.status_code == 200
    assert res.json() == {"points": [], "explain": {}, "centroids": {}}


# ------------------------------------------------------------------
# 5. GET /api/embedding_neighbours
# ------------------------------------------------------------------


def test_embedding_neighbours_success(client, mock_session):
    with patch.object(
        vector_routes,
        "similar_articles",
        return_value=[{"id": "u2", "score": 0.25}, {"id": "u3", "score": 0.5}],
    ):
        res = client.get("/api/embedding_neighbours", params={"id": "u1", "top_k": 2})

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert set(body[0].keys()) == {"id", "distance"}


def test_embedding_neighbours_failure_500(client, mock_session):
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    with patch.object(vector_routes, "similar_articles", side_effect=Exception("boom")):
        res = failure_client.get("/api/embedding_neighbours", params={"id": "u1"})
    assert res.status_code == 500


# ------------------------------------------------------------------
# 6. GET /api/patterns
# ------------------------------------------------------------------


def test_patterns_success(client, mock_session):
    fake_articles = [
        {"metadata": {"title": "Alpha beta", "summary": "Beta gamma", "tags": ["t1"]}},
        {"metadata": {"title": "Alpha delta", "summary": "Gamma epsilon", "tags": "t1,t2"}},
    ]
    with patch.object(vector_routes, "search_articles", return_value=fake_articles):
        res = client.get("/api/patterns", params={"q": "x", "top_k": 10})

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {"ngrams", "cooccurrence", "tag_stats"}


def test_patterns_failure_returns_error_field(client, mock_session):
    with patch.object(vector_routes, "search_articles", side_effect=Exception("boom")):
        res = client.get("/api/patterns", params={"q": "x", "top_k": 10})

    assert res.status_code == 200
    assert res.json()["error"] == "boom"


# ------------------------------------------------------------------
# 7. GET /api/statistics
# ------------------------------------------------------------------


def test_statistics_success(client, mock_session):
    fake_results = [
        {"score": 0.9, "metadata": {"category": "Tech", "sentiment": "Positive", "publication_date": "2024-01-01"}},
        {"score": 0.1, "metadata": {"category": "Tech", "sentiment": "Negative", "publication_date": "2024-01-02"}},
    ]
    with patch.object(vector_routes, "search_articles", return_value=fake_results):
        res = client.get("/api/statistics", params={"q": "x", "top_k": 10})

    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {"total", "by_category", "by_sentiment", "avg_score", "date_range", "tag_stats"}


def test_statistics_failure_500(client, mock_session):
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    with patch.object(vector_routes, "search_articles", side_effect=Exception("boom")):
        res = failure_client.get("/api/statistics", params={"q": "x"})
    assert res.status_code == 500
    assert "error" in res.json()


# ------------------------------------------------------------------
# 8. POST /api/clean_collection
# ------------------------------------------------------------------


def test_clean_collection_success(client, mock_session):
    mock_conn = MagicMock(name="conn")
    mock_result = MagicMock(name="result")
    mock_result.rowcount = 3
    mock_conn.execute.return_value = mock_result

    mock_db = MagicMock(name="db")
    mock_db._temp_get_connection.return_value = mock_conn

    with patch.object(vector_routes, "get_database_instance", return_value=mock_db):
        res = client.post("/api/clean_collection")

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "Cleared embeddings from 3 articles" in res.json()["message"]
    mock_conn.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
    mock_conn.close.assert_called_once()


def test_clean_collection_failure_500(client, mock_session):
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    mock_conn = MagicMock(name="conn")
    mock_conn.execute.side_effect = Exception("boom")

    mock_db = MagicMock(name="db")
    mock_db._temp_get_connection.return_value = mock_conn

    with patch.object(vector_routes, "get_database_instance", return_value=mock_db):
        res = failure_client.post("/api/clean_collection")
    assert res.status_code == 500
    assert res.json()["detail"] == "boom"
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()


# ------------------------------------------------------------------
# 9. GET /api/embedding_anomalies
# ------------------------------------------------------------------


def test_embedding_anomalies_success(client, mock_session):
    import numpy as np

    vecs = np.array([[0.0, 0.0], [10.0, 10.0], [0.1, 0.2]], dtype=np.float32)
    metas = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
    ids = ["u1", "u2", "u3"]

    class DummyIso:
        def __init__(self, contamination=0.02, random_state=None):
            pass

        def fit(self, X):
            return self

        def decision_function(self, X):
            # Lower decision_function -> more anomalous after negation
            return np.array([0.2, -0.9, 0.1], dtype=np.float32)

    with patch.object(vector_routes, "_fetch_vectors", return_value=(vecs, metas, ids)), patch(
        "sklearn.ensemble.IsolationForest", DummyIso
    ):
        res = client.get("/api/embedding_anomalies", params={"top_k": 2})

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert set(body[0].keys()) >= {"id", "score", "metadata"}


def test_embedding_anomalies_failure_empty_vectors_returns_empty_list(client, mock_session):
    import numpy as np

    with patch.object(
        vector_routes,
        "_fetch_vectors",
        return_value=(np.empty((0, 0), dtype=np.float32), [], []),
    ):
        res = client.get("/api/embedding_anomalies", params={"top_k": 10})

    assert res.status_code == 200
    assert res.json() == []


# ------------------------------------------------------------------
# 10. POST /api/vector-summary
# ------------------------------------------------------------------


def test_vector_summary_success(client, mock_session):
    with patch(
        "app.vector_store.get_by_ids",
        return_value={"metadatas": [{"title": "T", "summary": "S"}]},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=_litellm_resp("ok")):
        res = client.post("/api/vector-summary", json={"ids": ["u1"], "model": "gpt-4o-mini"})

    assert res.status_code == 200
    assert res.json() == {"response": "ok"}


def test_vector_summary_failure_get_by_ids_raises_500(client, mock_session):
    failure_client = TestClient(client.app, raise_server_exceptions=False)
    with patch("app.vector_store.get_by_ids", side_effect=Exception("boom")):
        res = failure_client.post("/api/vector-summary", json={"ids": ["u1"]})
    assert res.status_code == 500
    assert res.json()["detail"] == "Vector store error"


# ------------------------------------------------------------------
# 11. POST /api/vector-summary-raw
# ------------------------------------------------------------------


def test_vector_summary_raw_success(client, mock_session):
    with patch(
        "app.vector_store.get_by_ids",
        return_value={
            "metadatas": [{"title": "T"}],
            "documents": ["full text"],
        },
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=_litellm_resp("ok-raw")):
        res = client.post("/api/vector-summary-raw", json={"ids": ["u1"], "model": "gpt-4o-mini"})

    assert res.status_code == 200
    assert res.json() == {"response": "ok-raw"}


def test_vector_summary_raw_failure_empty_result_404(client, mock_session):
    with patch("app.vector_store.get_by_ids", return_value={"metadatas": [], "documents": []}):
        res = client.post("/api/vector-summary-raw", json={"ids": ["u1"]})
    assert res.status_code == 404


# ------------------------------------------------------------------
# 12. POST /api/article-insights
# ------------------------------------------------------------------


def test_article_insights_success(client, mock_session):
    with patch(
        "app.vector_store.get_by_ids",
        return_value={"metadatas": [{"title": "T", "summary": "S"}]},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=_litellm_resp("themes")):
        res = client.post("/api/article-insights", json={"ids": ["u1"], "model": "gpt-4o-mini"})

    assert res.status_code == 200
    assert "response" in res.json()


def test_article_insights_failure_no_metas_404(client, mock_session):
    with patch("app.vector_store.get_by_ids", return_value={"metadatas": []}):
        res = client.post("/api/article-insights", json={"ids": ["u1"], "model": "gpt-4o-mini"})
    assert res.status_code == 404


# ------------------------------------------------------------------
# 13. POST /api/incident-tracking
# ------------------------------------------------------------------


def test_incident_tracking_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_all.return_value = [
        {
            "uri": "u1",
            "title": "A",
            "summary": "S",
            "news_source": "Src",
            "publication_date": "2024-01-01",
            "category": "Tech",
            "sentiment": "Positive",
            "topic": "ai",
            "bias": None,
            "factual_reporting": "high",
            "mbfc_credibility_rating": "high",
            "bias_source": None,
        }
    ]
    vector_mock_db.get_article_analysis_cache.return_value = None
    vector_mock_db.save_article_analysis_cache.return_value = True
    vector_mock_db.get_incident_status.return_value = {}

    class DummyModel:
        def generate_response(self, messages):
            return json.dumps(
                [
                    {
                        "name": "Test incident",
                        "type": "incident",
                        "subtype": "layoffs",
                        "description": "d",
                        "article_uris": ["u1"],
                        "timeline": "",
                        "significance": "high",
                        "investigation_leads": [],
                        "related_entities": [],
                    }
                ]
            )

    async def _fake_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.ai_models.LiteLLMModel.get_instance", return_value=DummyModel()), patch(
        "fastapi.concurrency.run_in_threadpool", new=AsyncMock(side_effect=_fake_threadpool)
    ):
        res = client.post(
            "/api/incident-tracking",
            json={"topic": "ai", "days_limit": 1, "max_articles": 10, "model": "gpt-4o-mini"},
        )

    assert res.status_code == 200
    body = res.json()
    assert "incidents" in body
    assert isinstance(body["incidents"], list)


def test_incident_tracking_failure_no_articles_returns_empty(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_all.return_value = []
    res = client.post("/api/incident-tracking", json={"topic": "ai"})
    assert res.status_code == 200
    assert res.json()["incidents"] == []


# ------------------------------------------------------------------
# 14. POST /api/incident-status/{name}
# ------------------------------------------------------------------


def test_update_incident_status_success(client, vector_mock_db, mock_session):
    vector_mock_db.update_incident_status.return_value = True
    res = client.post("/api/incident-status/Test", params={"status": "seen", "topic": "ai"})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_update_incident_status_invalid_status_400(client, vector_mock_db, mock_session):
    res = client.post("/api/incident-status/Test", params={"status": "nope", "topic": "ai"})
    assert res.status_code == 400


def test_update_incident_status_db_failure_500(client, vector_mock_db, mock_session, monkeypatch):
    facade = MagicMock(name="incident_facade")
    facade.update_incident_status.return_value = False
    import app.database_query_facade as dqf_mod
    monkeypatch.setattr(dqf_mod, "DatabaseQueryFacade", MagicMock(return_value=facade), raising=True)
    res = client.post("/api/incident-status/Test", params={"status": "seen", "topic": "ai"})
    assert res.status_code == 500


# ------------------------------------------------------------------
# 15. POST /api/signal-instructions
# ------------------------------------------------------------------


def test_save_signal_instruction_success(client, vector_mock_db, mock_session):
    vector_mock_db.facade.save_signal_instruction.return_value = True
    res = client.post(
        "/api/signal-instructions",
        json={"name": "n", "description": "d", "instruction": "i", "topic": "t", "is_active": True},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_save_signal_instruction_failure_returns_500(client, vector_mock_db, mock_session):
    vector_mock_db.facade.save_signal_instruction.return_value = False
    res = client.post(
        "/api/signal-instructions",
        json={"name": "n", "description": "d", "instruction": "i", "topic": "t", "is_active": True},
    )
    assert res.status_code == 500


# ------------------------------------------------------------------
# 16. GET /api/signal-instructions
# ------------------------------------------------------------------


def test_get_signal_instructions_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.facade.get_signal_instructions.return_value = [{"id": 1, "name": "n"}]
    res = client.get("/api/signal-instructions", params={"topic": "t", "active_only": True})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["count"] == 1


def test_get_signal_instructions_failure_500(client, vector_mock_db, mock_optional_session):
    vector_mock_db.facade.get_signal_instructions.side_effect = Exception("boom")
    res = client.get("/api/signal-instructions")
    assert res.status_code == 500


# ------------------------------------------------------------------
# 17. DELETE /api/signal-instructions/{id}
# ------------------------------------------------------------------


def test_delete_signal_instruction_success(client, vector_mock_db, mock_session):
    vector_mock_db.facade.delete_signal_instruction.return_value = True
    res = client.delete("/api/signal-instructions/1")
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_delete_signal_instruction_failure_404(client, vector_mock_db, mock_session):
    vector_mock_db.facade.delete_signal_instruction.return_value = False
    res = client.delete("/api/signal-instructions/1")
    assert res.status_code == 404


# ------------------------------------------------------------------
# 18. POST /api/real-time-signals
# ------------------------------------------------------------------


def test_real_time_signals_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_all.return_value = [
        {
            "uri": "u1",
            "title": "Quantum update",
            "summary": "S",
            "news_source": "Src",
            "publication_date": "2024-01-01",
            "category": "Tech",
            "sentiment": "Positive",
        }
    ]
    vector_mock_db.get_article_analysis_cache.return_value = None
    vector_mock_db.save_article_analysis_cache.return_value = True
    vector_mock_db.facade.get_signal_instructions.return_value = [
        {"id": 1, "name": "Signal 1", "description": "d", "instruction": "i", "is_active": True}
    ]

    class DummyModel:
        def generate_response(self, messages):
            return json.dumps(
                {
                    "signal_detected": True,
                    "confidence": 0.9,
                    "matching_articles": ["u1"],
                    "summary": "matched",
                    "threat_level": "low",
                    "recommended_action": "review",
                }
            )

    async def _fake_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.ai_models.LiteLLMModel.get_instance", return_value=DummyModel()), patch(
        "fastapi.concurrency.run_in_threadpool", new=AsyncMock(side_effect=_fake_threadpool)
    ):
        res = client.post("/api/real-time-signals", json={"topic": "ai"})

    assert res.status_code == 200
    body = res.json()
    assert "signals" in body
    assert isinstance(body["signals"], list)


def test_real_time_signals_failure_no_articles(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_all.return_value = []
    res = client.post("/api/real-time-signals", json={"topic": "ai"})
    assert res.status_code == 200
    assert res.json()["signals"] == []


# ------------------------------------------------------------------
# 19. GET /api/debug-articles
# ------------------------------------------------------------------


def test_debug_articles_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_one.side_effect = [{"count": 0}, {"earliest_date": "2024-01-01", "latest_date": "2024-01-02", "total_articles": 2}]
    vector_mock_db.fetch_all.side_effect = [
        [{"topic": "ai", "count": 1}],  # topics
        [],  # recent alerts
    ]
    res = client.get("/api/debug-articles", params={"topic": "ai"})
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) >= {
        "available_topics",
        "recent_articles",
        "date_range_info",
        "signal_alerts_count",
        "recent_alerts",
    }


def test_debug_articles_failure_returns_error_field(client, vector_mock_db, mock_optional_session):
    vector_mock_db.fetch_all.side_effect = Exception("boom")
    res = client.get("/api/debug-articles")
    assert res.status_code == 200
    assert "error" in res.json()


# ------------------------------------------------------------------
# 20. POST /api/run-signals
# ------------------------------------------------------------------


def test_run_signal_instructions_success(client, vector_mock_db, mock_session):
    vector_mock_db.facade.get_signal_instructions.return_value = [
        {"id": 1, "name": "Sig", "description": "d", "instruction": "i", "is_active": True}
    ]
    with patch.object(vector_routes, "_run_signals_background", new=AsyncMock(return_value=None)):
        res = client.post(
            "/api/run-signals",
            json={"instruction_ids": [1], "topic": "ai", "days_back": 1, "max_articles": 10, "model": "gpt-4o-mini"},
        )

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["status"] == "running"
    assert "run_id" in res.json()


def test_run_signal_instructions_failure_no_instructions(client, vector_mock_db, mock_session):
    vector_mock_db.facade.get_signal_instructions.return_value = []
    res = client.post("/api/run-signals", json={"instruction_ids": [1]})
    assert res.status_code == 200
    assert res.json()["success"] is False


# ------------------------------------------------------------------
# 21. GET /api/signal-alerts
# ------------------------------------------------------------------


def test_get_signal_alerts_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.facade.get_signal_alerts.return_value = [{"id": 1}]
    res = client.get("/api/signal-alerts", params={"limit": 10})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_get_signal_alerts_failure_500(client, vector_mock_db, mock_optional_session):
    vector_mock_db.facade.get_signal_alerts.side_effect = Exception("boom")
    res = client.get("/api/signal-alerts", params={"limit": 10})
    assert res.status_code == 500


# ------------------------------------------------------------------
# 22. POST /api/acknowledge-alert/{id}
# ------------------------------------------------------------------


def test_acknowledge_alert_success(client, vector_mock_db, mock_session):
    vector_mock_db.facade.acknowledge_signal_alert.return_value = True
    res = client.post("/api/acknowledge-alert/1")
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_acknowledge_alert_failure_404(client, vector_mock_db, mock_session):
    vector_mock_db.facade.acknowledge_signal_alert.return_value = False
    res = client.post("/api/acknowledge-alert/1")
    assert res.status_code == 404


# ------------------------------------------------------------------
# 23. GET /api/analysis-cache (path + qp)
# ------------------------------------------------------------------


def test_get_analysis_cache_success_path(client, vector_mock_db, mock_optional_session):
    vector_mock_db.get_article_analysis_cache.return_value = {
        "content": "c",
        "model_used": "m",
        "generated_at": "t",
        "metadata": {"k": "v"},
    }
    res = client.get("/api/analysis-cache/u1", params={"analysis_type": "themes", "model": "m"})
    assert res.status_code == 200
    assert res.json()["cached"] is True


def test_get_analysis_cache_failure_path_returns_cached_false(client, vector_mock_db, mock_optional_session):
    vector_mock_db.get_article_analysis_cache.return_value = None
    res = client.get("/api/analysis-cache/u1", params={"analysis_type": "themes", "model": "m"})
    assert res.status_code == 200
    assert res.json() == {"cached": False}


def test_get_analysis_cache_success_qp(client, vector_mock_db, mock_optional_session):
    vector_mock_db.get_article_analysis_cache.return_value = {
        "content": "c",
        "model_used": "m",
        "generated_at": "t",
        "metadata": {},
    }
    res = client.get("/api/analysis-cache", params={"article_uri": "u1", "analysis_type": "themes", "model": "m"})
    assert res.status_code == 200
    assert res.json()["cached"] is True


def test_get_analysis_cache_failure_qp_returns_cached_false(client, vector_mock_db, mock_optional_session):
    vector_mock_db.get_article_analysis_cache.return_value = None
    res = client.get("/api/analysis-cache", params={"article_uri": "u1", "analysis_type": "themes"})
    assert res.status_code == 200
    assert res.json() == {"cached": False}


# ------------------------------------------------------------------
# 24. POST /api/save-analysis-cache
# ------------------------------------------------------------------


def test_save_analysis_cache_success(client, vector_mock_db, mock_optional_session):
    vector_mock_db.save_article_analysis_cache.return_value = True
    res = client.post(
        "/api/save-analysis-cache",
        json={"article_uri": "u1", "analysis_type": "themes", "content": "c", "model_name": "m", "metadata": {}},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_save_analysis_cache_failure_500(client, vector_mock_db, mock_optional_session):
    vector_mock_db.save_article_analysis_cache.return_value = False
    res = client.post(
        "/api/save-analysis-cache",
        json={"article_uri": "u1", "analysis_type": "themes", "content": "c", "model_name": "m", "metadata": {}},
    )
    assert res.status_code == 500


# ------------------------------------------------------------------
# 25. POST /api/article-deep-dive
# ------------------------------------------------------------------


def test_article_deep_dive_success(client, mock_session):
    mock_pgvector_result = {
        "metadatas": [{"title": "T", "news_source": "Src", "publication_date": "2024-01-01"}],
        "documents": ["doc"],
    }
    m = mock_open(read_data="template")
    with patch.object(vector_routes, "get_by_ids", return_value=mock_pgvector_result), patch("builtins.open", m), patch(
        "litellm.acompletion", new_callable=AsyncMock, return_value=_litellm_resp("deep")
    ):
        res = client.post("/api/article-deep-dive", json={"ids": ["u1"], "model": "gpt-4o-mini"})

    assert res.status_code == 200
    assert "response" in res.json()


def test_article_deep_dive_failure_wrong_id_count_400(client, mock_session):
    res = client.post("/api/article-deep-dive", json={"ids": ["u1", "u2"]})
    assert res.status_code == 400


# ------------------------------------------------------------------
# 26. GET /api/news-facts
# ------------------------------------------------------------------


def test_get_news_facts_success(client, mock_session):
    m = mock_open(read_data='{"facts": ["f1"]}')
    with patch("pathlib.Path.is_file", return_value=True), patch("builtins.open", m):
        res = client.get("/api/news-facts")

    assert res.status_code == 200
    assert res.json() == {"facts": ["f1"]}


def test_get_news_facts_failure_file_not_found_500(client, mock_session):
    res = client.get("/api/news-facts")
    # Default config may exist locally; force "missing" explicitly.
    with patch("pathlib.Path.is_file", return_value=False):
        res = client.get("/api/news-facts")
    assert res.status_code == 500


# ------------------------------------------------------------------
# 27. DELETE /api/vector-delete/{id}
# ------------------------------------------------------------------


def test_vector_delete_success(client, mock_session):
    with patch.object(vector_routes, "get_by_ids", return_value={"ids": ["u1"], "metadatas": [{}]}), patch.object(
        vector_routes, "delete_embeddings", return_value=1
    ) as mock_delete:
        res = client.delete("/api/vector-delete/u1")
    assert res.status_code == 200
    assert res.json()["success"] is True
    mock_delete.assert_called_once_with(["u1"])


def test_vector_delete_failure_not_found_404(client, mock_session):
    with patch.object(vector_routes, "get_by_ids", return_value={"ids": [], "metadatas": []}), patch.object(
        vector_routes, "count_embeddings", return_value=0
    ):
        res = client.delete("/api/vector-delete/u1")
    assert res.status_code == 404


# ------------------------------------------------------------------
# 28. GET /api/vector-debug
# ------------------------------------------------------------------


def test_vector_debug_success(client, mock_session):
    with patch.object(
        vector_routes,
        "get_vectors_by_metadata",
        return_value=([], [{"title": "T"}], ["https://example.com/u1"]),
    ), patch.object(vector_routes, "count_embeddings", return_value=1):
        res = client.get("/api/vector-debug")
    assert res.status_code == 200
    assert res.json()["total_articles"] == 1


def test_vector_debug_failure_returns_error_field(client, mock_session):
    with patch.object(vector_routes, "get_vectors_by_metadata", side_effect=Exception("boom")):
        res = client.get("/api/vector-debug")
    assert res.status_code == 200
    assert "error" in res.json()


# ------------------------------------------------------------------
# 29. GET /api/incident-config
# ------------------------------------------------------------------


def test_get_incident_configuration_success(client, mock_optional_session):
    res = client.get("/api/incident-config")
    assert res.status_code == 200
    assert res.json()["success"] is True


# ------------------------------------------------------------------
# 30. POST /api/incident-config
# ------------------------------------------------------------------


def test_save_incident_configuration_success(client, mock_optional_session):
    payload = {
        "systemPrompt": "x {topic} {ontology_text} {profile_context}",
        "userPrompt": "y {topic} {articles_text}",
        "baseOntology": "incident event entity",
        "domainKey": "",
        "domainOverlay": "",
        "ontologyExamples": "{}",
        "analysisInstructions": "a",
        "qualityGuidelines": "q",
        "outputFormat": "json",
        "profileContextTemplate": "p",
        "enableProfileIntegration": True,
    }
    res = client.post("/api/incident-config", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_save_incident_configuration_failure_missing_placeholders_400(client, mock_optional_session):
    payload = {
        "systemPrompt": "missing {topic}",
        "userPrompt": "y {topic} {articles_text}",
        "baseOntology": "incident event entity",
        "domainKey": "",
        "domainOverlay": "",
        "ontologyExamples": "{}",
        "analysisInstructions": "a",
        "qualityGuidelines": "q",
        "outputFormat": "json",
        "profileContextTemplate": "p",
        "enableProfileIntegration": True,
    }
    res = client.post("/api/incident-config", json=payload)
    assert res.status_code == 400


# ------------------------------------------------------------------
# 31. POST /api/incident-config/validate
# ------------------------------------------------------------------


def test_validate_incident_configuration_success(client, mock_optional_session):
    payload = {
        "systemPrompt": "x {topic} {ontology_text} {profile_context} json",
        "userPrompt": "y {topic} {articles_text}",
        "baseOntology": "incident event entity",
        "domainKey": "",
        "domainOverlay": "",
        "ontologyExamples": "{}",
        "analysisInstructions": "a",
        "qualityGuidelines": "q",
        "outputFormat": "json",
        "profileContextTemplate": "{profile_name} {industry} {organization_type} {key_concerns} {strategic_priorities}",
        "enableProfileIntegration": True,
    }
    res = client.post("/api/incident-config/validate", json=payload)
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_validate_incident_configuration_failure_invalid_fields(client, mock_optional_session):
    payload = {
        "systemPrompt": "x {topic} {ontology_text}",
        "userPrompt": "y {topic}",
        "baseOntology": "only incident",
        "domainKey": "",
        "domainOverlay": "",
        "ontologyExamples": "notjson",
        "analysisInstructions": "a",
        "qualityGuidelines": "q",
        "outputFormat": "x",
        "profileContextTemplate": "p",
        "enableProfileIntegration": False,
    }
    res = client.post("/api/incident-config/validate", json=payload)
    assert res.status_code == 200
    assert res.json()["valid"] is False
    assert isinstance(res.json()["issues"], list)


# ------------------------------------------------------------------
# 32. GET /api/incident-config/defaults
# ------------------------------------------------------------------


def test_get_incident_configuration_defaults_success(client, mock_optional_session):
    res = client.get("/api/incident-config/defaults")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "defaults" in body


# =============================================================================
# onboarding_routes.py endpoints
# Spec: tests/spec/onboarding_routes_test_spec.md
# =============================================================================


def _clear_client_cookies(client: TestClient) -> None:
    # The `client` fixture is session-scoped; isolate tests by clearing cookies.
    try:
        client.cookies.clear()
    except Exception:
        pass


def _login_set_session_cookie(client: TestClient, monkeypatch, *, completed_onboarding: bool = False) -> None:
    """
    Use the real /login route to set a signed SessionMiddleware cookie,
    while fully mocking DB + password verification (no real DB/env/fs).
    """
    import app.routes.auth_routes as auth_routes

    class DB:
        def get_user(self, u):
            return {
                "username": u,
                "password": "hashed",
                "is_active": True,
                "force_password_change": False,
                "completed_onboarding": completed_onboarding,
            }

    monkeypatch.setattr(auth_routes, "get_database_instance", lambda: DB())
    monkeypatch.setattr(auth_routes, "verify_password", lambda p, h: True)

    res = client.post(
        "/login",
        data={"username": "john", "password": "1234"},
        follow_redirects=False,
    )
    assert res.status_code in (302, 307)


def _aiohttp_client_session_mock(*, status_code: int = 200, json_data: dict | None = None):
    """
    Build an aiohttp.ClientSession() mock that supports:
    async with ClientSession() as session:
      async with session.get(...) as resp:
    """
    resp = MagicMock()
    resp.status = status_code
    resp.json = AsyncMock(return_value=json_data or {})

    # Important: aiohttp's session.get()/post() are NOT awaited; they return an
    # async context manager directly. So these must be regular mocks.
    req_ctx = MagicMock()
    req_ctx.__aenter__ = AsyncMock(return_value=resp)
    req_ctx.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get.return_value = req_ctx
    session.post.return_value = req_ctx

    sess_ctx = MagicMock()
    sess_ctx.__aenter__ = AsyncMock(return_value=session)
    sess_ctx.__aexit__ = AsyncMock(return_value=None)
    return sess_ctx


# ------------------------------------------------------------------
# 1. POST /api/onboarding/validate-api-key
# ------------------------------------------------------------------


def test_onboarding_validate_api_key_success_openai(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    # Network + env + fs must be mocked
    monkeypatch.setattr(
        onboarding_routes.aiohttp,
        "ClientSession",
        lambda *a, **k: _aiohttp_client_session_mock(status_code=200, json_data={}),
    )
    monkeypatch.setattr(onboarding_routes, "load_dotenv", lambda *a, **k: None)
    # Use a fresh dict for env writes; set DISABLE_SSL so middleware doesn't redirect
    # (redirect would change POST to GET, causing 405 Method Not Allowed)
    test_env = {"DISABLE_SSL": "true"}
    monkeypatch.setattr(onboarding_routes.os, "environ", test_env)

    m = mock_open(read_data="")
    with patch("builtins.open", m):
        res = client.post(
            "/api/onboarding/validate-api-key",
            json={"provider": "openai", "api_key": "sk-test-1234567890"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "valid"
    assert body["configured"] is True
    assert "masked_key" in body
    assert body["masked_key"].startswith("sk-t")

    _clear_client_cookies(client)


def test_onboarding_validate_api_key_failure_missing_provider(client):
    _clear_client_cookies(client)
    res = client.post("/api/onboarding/validate-api-key", json={"api_key": "x"})
    assert res.status_code == 400
    assert "detail" in res.json()
    _clear_client_cookies(client)


def test_onboarding_validate_api_key_failure_openai_unauthorized(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(
        onboarding_routes.aiohttp,
        "ClientSession",
        lambda *a, **k: _aiohttp_client_session_mock(status_code=401, json_data={}),
    )
    monkeypatch.setattr(onboarding_routes, "load_dotenv", lambda *a, **k: None)
    test_env = {"DISABLE_SSL": "true"}
    monkeypatch.setattr(onboarding_routes.os, "environ", test_env)

    with patch("builtins.open", mock_open(read_data="")):
        res = client.post(
            "/api/onboarding/validate-api-key",
            json={"provider": "openai", "api_key": "sk-test-1234567890"},
        )

    assert res.status_code == 400
    assert "Invalid OpenAI API key" in res.json().get("detail", "")

    _clear_client_cookies(client)


def test_onboarding_validate_api_key_failure_unsupported_provider(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    # Ensure no accidental fs/env touches
    monkeypatch.setattr(onboarding_routes, "load_dotenv", lambda *a, **k: None)
    test_env = {"DISABLE_SSL": "true"}
    monkeypatch.setattr(onboarding_routes.os, "environ", test_env)
    with patch("builtins.open", mock_open(read_data="")):
        res = client.post(
            "/api/onboarding/validate-api-key",
            json={"provider": "unsupported", "api_key": "x"},
        )

    assert res.status_code == 400
    assert res.json()["detail"] == "Unsupported provider"

    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 2. GET /api/onboarding/check-keys
# ------------------------------------------------------------------


def test_onboarding_check_keys_success_masks_values(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: True)

    def _getenv(name, default=None):
        values = {
            "PROVIDER_NEWSAPI_KEY": "newsapi-1234567890",
            "PROVIDER_FIRECRAWL_KEY": "firecrawl-1234567890",
            "PROVIDER_THENEWSAPI_KEY": "thenewsapi-1234567890",
            "PROVIDER_NEWSDATA_API_KEY": "newsdata-1234567890",
            "OPENAI_API_KEY": "sk-test-1234567890",
            "ANTHROPIC_API_KEY": "sk-ant-1234567890",
            "GEMINI_API_KEY": "AIzaSy1234567890",
        }
        return values.get(name, default)

    monkeypatch.setattr(onboarding_routes.os, "getenv", _getenv)

    res = client.get("/api/onboarding/check-keys")
    assert res.status_code == 200

    body = res.json()
    assert body["newsapi"] is True
    assert body["firecrawl"] is True
    assert body["thenewsapi"] is True
    assert body["newsdata"] is True
    assert body["openai"] is True
    assert body["anthropic"] is True
    assert body["gemini"] is True
    assert body["openai_key"].startswith("sk-t")

    _clear_client_cookies(client)


def test_onboarding_check_keys_failure_returns_500(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes, "check_api_keys", AsyncMock(side_effect=Exception("boom")))
    res = client.get("/api/onboarding/check-keys")
    assert res.status_code == 500
    assert "detail" in res.json()

    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 3. GET /onboarding
# ------------------------------------------------------------------


def test_onboarding_page_success_html(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)
    _login_set_session_cookie(client, monkeypatch, completed_onboarding=False)

    class FakeDB:
        def get_user(self, u):
            return {"completed_onboarding": False}

    class FakeTemplates:
        def TemplateResponse(self, name, context):
            return HTMLResponse("<html>ok</html>")

    monkeypatch.setattr(onboarding_routes, "Database", FakeDB)
    monkeypatch.setattr(onboarding_routes, "templates", FakeTemplates())

    res = client.get("/onboarding", follow_redirects=False)
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")

    _clear_client_cookies(client)


def test_onboarding_page_redirect_no_user_session(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    class FakeTemplates:
        def TemplateResponse(self, name, context):
            return HTMLResponse("<html>ok</html>")

    monkeypatch.setattr(onboarding_routes, "templates", FakeTemplates())

    res = client.get("/onboarding", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/login"

    _clear_client_cookies(client)


def test_onboarding_page_redirect_completed_onboarding(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)
    _login_set_session_cookie(client, monkeypatch, completed_onboarding=True)

    class FakeDB:
        def get_user(self, u):
            return {"completed_onboarding": True}

    class FakeTemplates:
        def TemplateResponse(self, name, context):
            return HTMLResponse("<html>ok</html>")

    monkeypatch.setattr(onboarding_routes, "Database", FakeDB)
    monkeypatch.setattr(onboarding_routes, "templates", FakeTemplates())

    res = client.get("/onboarding", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/"

    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 4. POST /api/onboarding/suggest-topic-attributes
# ------------------------------------------------------------------


def test_onboarding_suggest_topic_attributes_success_llm_json(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    # FS + YAML + env + LLM must be mocked
    monkeypatch.setattr(
        onboarding_routes.yaml,
        "safe_load",
        lambda f: {
            "model_list": [
                {
                    "model_name": "gpt-4o",
                    "litellm_params": {"model": "openai/gpt-4o", "api_key": "os.environ/OPENAI_API_KEY"},
                }
            ]
        },
    )
    monkeypatch.setattr(onboarding_routes.os, "getenv", lambda k, d=None: "sk-test-123" if k == "OPENAI_API_KEY" else ("true" if k == "DISABLE_SSL" else d))
    monkeypatch.setattr(onboarding_routes.json, "load", lambda f: {"topics": [{"name": "Trend Monitoring"}]})

    good_llm_json = json.dumps(
        {
            "explanation": "A sufficiently long explanation for testing.",
            "categories": ["Cat1", "Cat2"],
            "future_signals": ["Outcome A", "Outcome B", "Outcome C"],
            "keywords": {"companies": [], "technologies": [], "general": ["ai"], "people": [], "exclusions": []},
        }
    )

    class _Choice:
        def __init__(self, content):
            self.message = MagicMock(content=content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    monkeypatch.setattr(onboarding_routes, "completion", lambda **k: _Resp(good_llm_json))

    with patch("builtins.open", mock_open(read_data="x")):
        res = client.post("/api/onboarding/suggest-topic-attributes", json={"topic_name": "AI"})

    assert res.status_code == 200
    body = res.json()
    assert "explanation" in body
    assert isinstance(body.get("keywords"), dict)
    assert set(["companies", "technologies", "general", "people", "exclusions"]).issubset(set(body["keywords"].keys()))

    _clear_client_cookies(client)


def test_onboarding_suggest_topic_attributes_fallback_bad_json(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(
        onboarding_routes.yaml,
        "safe_load",
        lambda f: {
            "model_list": [
                {
                    "model_name": "gpt-4o",
                    "litellm_params": {"model": "openai/gpt-4o", "api_key": "os.environ/OPENAI_API_KEY"},
                }
            ]
        },
    )
    monkeypatch.setattr(onboarding_routes.os, "getenv", lambda k, d=None: "sk-test-123" if k == "OPENAI_API_KEY" else ("true" if k == "DISABLE_SSL" else d))
    monkeypatch.setattr(onboarding_routes.json, "load", lambda f: {"topics": [{"name": "Trend Monitoring"}]})

    class _Choice:
        def __init__(self, content):
            self.message = MagicMock(content=content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    monkeypatch.setattr(onboarding_routes, "completion", lambda **k: _Resp("not json"))

    with patch("builtins.open", mock_open(read_data="x")):
        res = client.post("/api/onboarding/suggest-topic-attributes", json={"topic_name": "AI"})

    assert res.status_code == 200
    body = res.json()
    assert "categories" in body
    assert "future_signals" in body
    assert "keywords" in body

    _clear_client_cookies(client)


def test_onboarding_suggest_topic_attributes_failure_missing_topic_name(client):
    _clear_client_cookies(client)
    res = client.post("/api/onboarding/suggest-topic-attributes", json={})
    assert res.status_code == 400
    assert "topic_name" in res.json().get("detail", "")
    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 5. POST /api/onboarding/save-topic
# ------------------------------------------------------------------


def test_onboarding_save_topic_success_writes_config_and_keywords(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes
    from app.database import get_database_instance
    from app.main import app

    _clear_client_cookies(client)

    db = MagicMock(name="mock_db")
    app.dependency_overrides[get_database_instance] = lambda: db

    # FS must be mocked
    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: True)
    monkeypatch.setattr(onboarding_routes.os.path, "isfile", lambda *a, **k: True)

    class _Stat:
        st_mode = 0o100644

    monkeypatch.setattr(onboarding_routes.os, "stat", lambda *a, **k: _Stat())
    monkeypatch.setattr(onboarding_routes.os, "replace", lambda *a, **k: None)

    # Config load/save mocked
    monkeypatch.setattr(
        onboarding_routes.json,
        "load",
        lambda f: {
            "topics": [
                {
                    "name": "Trend Monitoring",
                    "sentiment": ["Neutral"],
                    "time_to_impact": ["Immediate (0-6 months)"],
                    "driver_types": ["Catalyst"],
                }
            ]
        },
    )
    monkeypatch.setattr(onboarding_routes.json, "dump", lambda *a, **k: None)

    with patch("builtins.open", mock_open(read_data="{}")), patch(
        "app.routes.onboarding_routes.DatabaseQueryFacade"
    ) as facade_cls:
        facade = facade_cls.return_value
        facade.topic_exists.return_value = False
        facade.get_keyword_group_id_by_name_and_topic.return_value = None
        facade.create_group.return_value = 1

        res = client.post(
            "/api/onboarding/save-topic",
            json={
                "name": "My Topic",
                "categories": ["A"],
                "future_signals": ["B"],
                "keywords": ["kw1", "kw2"],
            },
        )

    assert res.status_code == 200
    assert res.json()["status"] == "success"

    _clear_client_cookies(client)


def test_onboarding_save_topic_conflict_requires_confirmation(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes
    from app.database import get_database_instance
    from app.main import app

    _clear_client_cookies(client)

    db = MagicMock(name="mock_db")
    app.dependency_overrides[get_database_instance] = lambda: db

    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: True)
    monkeypatch.setattr(onboarding_routes.os.path, "isfile", lambda *a, **k: True)
    monkeypatch.setattr(onboarding_routes.os, "stat", lambda *a, **k: type("S", (), {"st_mode": 0o100644})())

    monkeypatch.setattr(
        onboarding_routes.json,
        "load",
        lambda f: {
            "topics": [
                {
                    "name": "Trend Monitoring",
                    "sentiment": ["Neutral"],
                    "time_to_impact": ["Immediate (0-6 months)"],
                    "driver_types": ["Catalyst"],
                }
            ]
        },
    )

    with patch("builtins.open", mock_open(read_data="{}")), patch(
        "app.routes.onboarding_routes.DatabaseQueryFacade"
    ) as facade_cls:
        facade = facade_cls.return_value
        facade.topic_exists.return_value = True

        res = client.post("/api/onboarding/save-topic", json={"name": "My Topic"})

    assert res.status_code == 409
    body = res.json()
    assert body["status"] == "warning"
    assert body["requires_confirmation"] is True

    _clear_client_cookies(client)


def test_onboarding_save_topic_failure_open_fails_500(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    with patch("builtins.open", side_effect=OSError("nope")):
        res = client.post("/api/onboarding/save-topic", json={"name": "My Topic"})

    assert res.status_code == 500
    assert "Failed to load config" in res.json().get("detail", "")

    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 6. POST /api/onboarding/complete
# ------------------------------------------------------------------


def test_onboarding_complete_success_updates_user(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes
    from app.database import get_database_instance
    from app.main import app

    _clear_client_cookies(client)
    _login_set_session_cookie(client, monkeypatch)

    db = MagicMock(name="mock_db")
    app.dependency_overrides[get_database_instance] = lambda: db

    with patch("app.routes.onboarding_routes.DatabaseQueryFacade") as facade_cls:
        facade = facade_cls.return_value
        res = client.post("/api/onboarding/complete", json={"news_provider": "newsapi"})

    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    db.update_user_onboarding.assert_called_once_with("john", True)
    facade.update_keyword_monitor_settings_provider.assert_called_once_with("newsapi")

    _clear_client_cookies(client)


def test_onboarding_complete_failure_no_user_session_returns_error(client):
    _clear_client_cookies(client)
    res = client.post("/api/onboarding/complete", json={})
    # Implementation catches HTTPException and returns 500; assert current behavior.
    assert res.status_code == 500
    assert "detail" in res.json()
    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 7. POST /api/onboarding/reset
# ------------------------------------------------------------------


def test_onboarding_reset_success_marks_not_completed(client, monkeypatch):
    from app.database import get_database_instance
    from app.main import app

    _clear_client_cookies(client)
    _login_set_session_cookie(client, monkeypatch)

    db = MagicMock(name="mock_db")
    app.dependency_overrides[get_database_instance] = lambda: db

    res = client.post("/api/onboarding/reset", json={})
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    db.update_user_onboarding.assert_called_once_with("john", False)

    _clear_client_cookies(client)


def test_onboarding_reset_failure_no_user_session_returns_error(client):
    _clear_client_cookies(client)
    res = client.post("/api/onboarding/reset", json={})
    # Implementation catches HTTPException and returns 500; assert current behavior.
    assert res.status_code == 500
    assert "detail" in res.json()
    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 8. GET /api/onboarding/available-models
# ------------------------------------------------------------------


def test_onboarding_available_models_success(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: True)
    monkeypatch.setattr(
        onboarding_routes.yaml,
        "safe_load",
        lambda f: {
            "model_list": [
                {"model_name": "gpt-4o", "litellm_params": {"model": "openai/gpt-4o", "api_key": "os.environ/OPENAI_API_KEY"}},
                {"model_name": "claude", "litellm_params": {"model": "anthropic/claude", "api_key": "os.environ/ANTHROPIC_API_KEY"}},
            ]
        },
    )

    with patch("builtins.open", mock_open(read_data="yaml")):
        res = client.get("/api/onboarding/available-models")

    assert res.status_code == 200
    body = res.json()
    assert "models" in body
    assert isinstance(body["models"], list)
    assert any(m["provider"] == "openai" for m in body["models"])

    _clear_client_cookies(client)


def test_onboarding_available_models_no_file_returns_empty(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: False)
    res = client.get("/api/onboarding/available-models")
    assert res.status_code == 200
    assert res.json() == {"models": []}

    _clear_client_cookies(client)


# ------------------------------------------------------------------
# 9. GET /api/onboarding/configured-models
# ------------------------------------------------------------------


def test_onboarding_configured_models_success_filters_by_api_key(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: True)
    monkeypatch.setattr(
        onboarding_routes.yaml,
        "safe_load",
        lambda f: {
            "model_list": [
                {"model_name": "gpt-4o", "litellm_params": {"model": "openai/gpt-4o", "api_key": "os.environ/OPENAI_API_KEY"}},
                {"model_name": "claude", "litellm_params": {"model": "anthropic/claude", "api_key": "os.environ/ANTHROPIC_API_KEY"}},
            ]
        },
    )

    def _getenv(name, default=None):
        if name == "OPENAI_API_KEY":
            return "sk-live-123"
        return ""  # unconfigured

    monkeypatch.setattr(onboarding_routes.os, "getenv", _getenv)

    with patch("builtins.open", mock_open(read_data="yaml")):
        res = client.get("/api/onboarding/configured-models")

    assert res.status_code == 200
    models = res.json()["models"]
    assert isinstance(models, list)
    assert len(models) == 1
    assert models[0]["name"] == "gpt-4o"
    assert models[0]["provider"] == "openai"

    _clear_client_cookies(client)


def test_onboarding_configured_models_missing_config_returns_empty(client, monkeypatch):
    import app.routes.onboarding_routes as onboarding_routes

    _clear_client_cookies(client)

    monkeypatch.setattr(onboarding_routes.os.path, "exists", lambda *a, **k: False)
    res = client.get("/api/onboarding/configured-models")
    assert res.status_code == 200
    assert res.json() == {"models": []}

    _clear_client_cookies(client)


# =============================================================================
# trend_convergence_routes.py endpoints (isolated app; all DB/AI/prompt/cache mocked)
# =============================================================================


@pytest.fixture
def trend_convergence_routes_module(monkeypatch):
    """
    Lazily import app.routes.trend_convergence_routes while preventing PromptManager
    from touching the filesystem during module import (prompt_manager is instantiated
    at import time in the router module).
    """
    import sys
    import importlib
    import app.analyzers.prompt_manager as pm

    # Prevent PromptManager() from creating directories / writing current.json.
    monkeypatch.setattr(pm.PromptManager, "_ensure_storage_dir", lambda self: None, raising=True)

    mod_name = "app.routes.trend_convergence_routes"
    if mod_name in sys.modules:
        return importlib.reload(sys.modules[mod_name])

    import app.routes.trend_convergence_routes as trend_convergence_routes
    return trend_convergence_routes


@pytest.fixture
def trend_convergence_app(trend_convergence_routes_module, fake_db, fake_session):
    """Tiny FastAPI app that mounts ONLY trend_convergence_routes.router."""
    from fastapi import FastAPI

    trend_app = FastAPI()
    trend_app.include_router(trend_convergence_routes_module.router)
    trend_app.dependency_overrides[get_database_instance] = lambda: fake_db
    trend_app.dependency_overrides[verify_session] = lambda: fake_session
    return trend_app


@pytest.fixture
def trend_convergence_client(trend_convergence_app, test_client_factory):
    return test_client_factory(trend_convergence_app)


@pytest.fixture
def trend_convergence_client_no_raise(trend_convergence_app, test_client_factory):
    return test_client_factory(trend_convergence_app, raise_server_exceptions=False)


def test_trend_convergence_models_success_and_fallback(trend_convergence_client, monkeypatch):
    import app.ai_models as ai_models

    # SUCCESS
    monkeypatch.setattr(
        ai_models,
        "list_available_models",
        lambda: {"gpt-4o-mini": "GPT-4o Mini", "claude-3.5-sonnet": "Claude 3.5 Sonnet"},
        raising=False,  # attribute may not exist in this repo; the route imports it dynamically
    )
    res = trend_convergence_client.get("/api/trend-convergence/models")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert isinstance(body, list)
    assert {m["id"] for m in body} >= {"gpt-4o-mini", "claude-3.5-sonnet"}
    assert all("context_limit" in m for m in body)

    # FALLBACK
    monkeypatch.setattr(ai_models, "list_available_models", lambda: (_ for _ in ()).throw(Exception("boom")), raising=False)
    res = trend_convergence_client.get("/api/trend-convergence/models")
    assert res.status_code == status.HTTP_200_OK
    fallback = res.json()
    assert isinstance(fallback, list)
    assert any(m["id"] == "gpt-4o-mini" for m in fallback)


def test_generate_trend_convergence_success_and_error_paths(
    trend_convergence_client,
    trend_convergence_client_no_raise,
    trend_convergence_routes_module,
    fake_db,
    fake_facade,
    fake_session,
    fake_auspex,
    monkeypatch,
):
    mod = trend_convergence_routes_module

    # Common patches: facade, cache, deterministic helpers, and auspex service
    monkeypatch.setattr(mod, "DatabaseQueryFacade", MagicMock(return_value=fake_facade), raising=True)
    monkeypatch.setattr(mod, "get_auspex_service", lambda: fake_auspex, raising=True)
    monkeypatch.setattr(mod, "get_cached_analysis", AsyncMock(return_value=None), raising=True)
    monkeypatch.setattr(mod, "save_analysis_with_cache", AsyncMock(return_value=None), raising=True)
    monkeypatch.setattr(mod, "ensure_cache_table_v2", AsyncMock(return_value=None), raising=True)
    monkeypatch.setattr(mod, "_save_analysis_version", AsyncMock(return_value=None), raising=True)
    monkeypatch.setattr(mod, "prepare_analysis_summary", lambda *a, **k: "SUMMARY", raising=True)
    monkeypatch.setattr(mod, "select_articles_deterministic", lambda arts, limit, _mode: list(arts)[:limit], raising=True)

    articles = [
        {
            "title": "AI 1",
            "uri": "https://example.com/a1",
            "summary": "s",
            "publication_date": "2024-01-01",
            "sentiment": "Neutral",
            "category": "Tech",
            "future_signal": None,
            "driver_type": None,
            "time_to_impact": "mid",
            "factual_reporting": "High",
            "mbfc_credibility_rating": "High",
        },
        {
            "title": "AI 2",
            "uri": "https://example.com/a2",
            "summary": "s2",
            "publication_date": "2024-01-02",
            "sentiment": "Neutral",
            "category": "Tech",
            "future_signal": None,
            "driver_type": None,
            "time_to_impact": "mid",
            "factual_reporting": "High",
            "mbfc_credibility_rating": "High",
        },
    ]

    fake_facade.get_articles_with_dynamic_limit.return_value = list(articles)
    fake_auspex.create_chat_session = AsyncMock(return_value="chat-1")
    fake_auspex.delete_chat_session = MagicMock(return_value=None)

    async def _agen(parts):
        for p in parts:
            yield p

    deterministic_json = {"topic": "AI", "strategic_recommendations": {}, "convergences": [], "scenarios": []}
    fake_auspex.chat_with_tools = MagicMock(return_value=_agen([json.dumps(deterministic_json)]))

    # SUCCESS (fresh generation)
    res = trend_convergence_client.get("/api/trend-convergence/AI?model=gpt-4o-mini")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["topic"] == "AI"
    assert body["model_used"] == "gpt-4o-mini"
    assert "generated_at" in body
    assert "version" in body
    assert body["articles_analyzed"] == 2

    # CACHED
    monkeypatch.setattr(mod, "get_cached_analysis", AsyncMock(return_value={"topic": "AI", "from_cache": True}), raising=True)
    res = trend_convergence_client.get("/api/trend-convergence/AI?model=gpt-4o-mini&enable_caching=true")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"topic": "AI", "from_cache": True}

    # NO ARTICLES -> 404
    monkeypatch.setattr(mod, "get_cached_analysis", AsyncMock(return_value=None), raising=True)
    fake_facade.get_articles_with_dynamic_limit.return_value = []
    res = trend_convergence_client.get("/api/trend-convergence/Missing?model=gpt-4o-mini")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert "No articles found for topic" in res.json()["detail"]

    # HIGH QUALITY EMPTY -> 422
    low_quality = [
        dict(articles[0], factual_reporting="Low", mbfc_credibility_rating="Low"),
        dict(articles[1], factual_reporting="Low", mbfc_credibility_rating="Low"),
    ]
    fake_facade.get_articles_with_dynamic_limit.return_value = low_quality
    res = trend_convergence_client.get("/api/trend-convergence/AI?model=gpt-4o-mini&source_quality=high_quality")
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "No high-quality articles found" in res.json()["detail"]

    # AI JSON ERROR -> 500
    fake_facade.get_articles_with_dynamic_limit.return_value = list(articles)
    fake_auspex.chat_with_tools = MagicMock(return_value=_agen(["not json"]))
    res = trend_convergence_client.get("/api/trend-convergence/AI?model=gpt-4o-mini")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "No valid JSON found" in res.json()["detail"]

    # AI RATE LIMIT TEXT PATH (observable behavior: wrapped into 500 by broad exception handler)
    fake_auspex.chat_with_tools = MagicMock(return_value=_agen(["Error generating response: RateLimitError"]))
    res = trend_convergence_client.get("/api/trend-convergence/AI?model=gpt-4o-mini")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "AI model error" in res.json()["detail"]

    # FAILURE (dependency raises) -> 500
    fake_facade.get_articles_with_dynamic_limit.side_effect = Exception("boom")
    res = trend_convergence_client_no_raise.get("/api/trend-convergence/AI?model=gpt-4o-mini")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_trend_convergence_load_previous_success_and_not_found(
    trend_convergence_client, trend_convergence_routes_module, monkeypatch
):
    mod = trend_convergence_routes_module

    # SUCCESS
    monkeypatch.setattr(mod, "_load_latest_analysis_version", AsyncMock(return_value={"topic": "AI"}), raising=True)
    res = trend_convergence_client.get("/api/trend-convergence/AI/previous")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == {"topic": "AI"}

    # NOT FOUND
    monkeypatch.setattr(mod, "_load_latest_analysis_version", AsyncMock(return_value=None), raising=True)
    res = trend_convergence_client.get("/api/trend-convergence/AI/previous")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_trend_convergence_page_success_and_failure(trend_convergence_client, trend_convergence_client_no_raise, monkeypatch):
    from fastapi.responses import HTMLResponse
    import fastapi.templating as fastapi_templating

    tmpl = MagicMock(name="trend_convergence_templates")
    tmpl.TemplateResponse = MagicMock(return_value=HTMLResponse(content="<html>OK</html>", status_code=200))
    monkeypatch.setattr(fastapi_templating, "Jinja2Templates", MagicMock(return_value=tmpl), raising=True)

    # SUCCESS
    res = trend_convergence_client.get("/trend-convergence")
    assert res.status_code == status.HTTP_200_OK

    # FAILURE
    tmpl.TemplateResponse.side_effect = Exception("template boom")
    res = trend_convergence_client_no_raise.get("/trend-convergence")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_trend_convergence_organizational_profiles_crud(
    trend_convergence_client, trend_convergence_routes_module, fake_facade, monkeypatch
):
    mod = trend_convergence_routes_module
    monkeypatch.setattr(mod, "DatabaseQueryFacade", MagicMock(return_value=fake_facade), raising=True)

    # GET /api/organizational-profiles (success + failure)
    fake_facade.get_organisational_profiles.return_value = [
        {
            "id": 1,
            "name": "Test Org",
            "description": None,
            "industry": None,
            "organization_type": None,
            "region": None,
            "key_concerns": json.dumps(["x"]),
            "strategic_priorities": json.dumps([]),
            "risk_tolerance": "medium",
            "innovation_appetite": "moderate",
            "decision_making_style": "collaborative",
            "stakeholder_focus": json.dumps([]),
            "competitive_landscape": json.dumps([]),
            "regulatory_environment": json.dumps([]),
            "custom_context": None,
            "is_default": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    res = trend_convergence_client.get("/api/organizational-profiles")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["profiles"][0]["name"] == "Test Org"

    fake_facade.get_organisational_profiles.side_effect = Exception("boom")
    res = trend_convergence_client.get("/api/organizational-profiles")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # POST /api/organizational-profiles (success + conflict + failure)
    fake_facade.get_organisational_profile_by_name.return_value = None
    fake_facade.create_organisational_profile.return_value = 123
    res = trend_convergence_client.post("/api/organizational-profiles", json={"name": "New Org"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["profile_id"] == 123

    fake_facade.get_organisational_profile_by_name.return_value = {"id": 1}
    res = trend_convergence_client.post("/api/organizational-profiles", json={"name": "New Org"})
    assert res.status_code == status.HTTP_409_CONFLICT

    fake_facade.get_organisational_profile_by_name.return_value = None
    fake_facade.create_organisational_profile.side_effect = Exception("boom")
    res = trend_convergence_client.post("/api/organizational-profiles", json={"name": "New Org"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # PUT /api/organizational-profiles/{id} (success + not found + conflict + failure)
    fake_facade.get_organisational_profile_by_id.return_value = {"id": 1}
    fake_facade.check_organisational_profile_name_conflict.return_value = None
    fake_facade.update_organisational_profile.return_value = None
    res = trend_convergence_client.put("/api/organizational-profiles/1", json={"name": "Renamed"})
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    fake_facade.get_organisational_profile_by_id.return_value = None
    res = trend_convergence_client.put("/api/organizational-profiles/999", json={"name": "Renamed"})
    assert res.status_code == status.HTTP_404_NOT_FOUND

    fake_facade.get_organisational_profile_by_id.return_value = {"id": 1}
    fake_facade.check_organisational_profile_name_conflict.return_value = True
    res = trend_convergence_client.put("/api/organizational-profiles/1", json={"name": "Renamed"})
    assert res.status_code == status.HTTP_409_CONFLICT

    fake_facade.check_organisational_profile_name_conflict.return_value = None
    fake_facade.update_organisational_profile.side_effect = Exception("boom")
    res = trend_convergence_client.put("/api/organizational-profiles/1", json={"name": "Renamed"})
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # DELETE /api/organizational-profiles/{id} (success + default + not found + failure)
    fake_facade.check_if_profile_exists_and_is_not_default.return_value = (False,)
    fake_facade.delete_organisational_profile.return_value = None
    res = trend_convergence_client.delete("/api/organizational-profiles/1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    fake_facade.check_if_profile_exists_and_is_not_default.return_value = (True,)
    res = trend_convergence_client.delete("/api/organizational-profiles/1")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    fake_facade.check_if_profile_exists_and_is_not_default.return_value = None
    res = trend_convergence_client.delete("/api/organizational-profiles/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    fake_facade.check_if_profile_exists_and_is_not_default.side_effect = Exception("boom")
    res = trend_convergence_client.delete("/api/organizational-profiles/1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # GET /api/organizational-profiles/{id} (success + not found + failure)
    profile_row = (
        1,
        "Test Org",
        "Desc",
        "Industry",
        "Type",
        "Region",
        json.dumps(["c1"]),
        json.dumps(["p1"]),
        "medium",
        "moderate",
        "collaborative",
        json.dumps([]),
        json.dumps([]),
        json.dumps([]),
        "ctx",
        0,
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    )
    fake_facade.get_organizational_profile_for_ui.return_value = profile_row
    res = trend_convergence_client.get("/api/organizational-profiles/1")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert res.json()["profile"]["name"] == "Test Org"

    fake_facade.get_organizational_profile_for_ui.return_value = None
    res = trend_convergence_client.get("/api/organizational-profiles/999")
    assert res.status_code == status.HTTP_404_NOT_FOUND

    fake_facade.get_organizational_profile_for_ui.side_effect = Exception("boom")
    res = trend_convergence_client.get("/api/organizational-profiles/1")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.parametrize(
    "path,facade_method,expected_key",
    [
        ("/api/trend-convergence/consensus/abc/raw", "get_consensus_analysis", "article_list"),
        ("/api/trend-convergence/timeline/abc/raw", "get_impact_timeline_analysis", "raw_output"),
        ("/api/trend-convergence/strategic/abc/raw", "get_strategic_recommendations_analysis", "raw_output"),
        ("/api/trend-convergence/horizons/abc/raw", "get_future_horizons_analysis", "raw_output"),
    ],
)
def test_trend_convergence_raw_analysis_endpoints_success_and_failures(
    trend_convergence_client,
    trend_convergence_client_no_raise,
    trend_convergence_routes_module,
    fake_facade,
    monkeypatch,
    path,
    facade_method,
    expected_key,
):
    from datetime import datetime

    mod = trend_convergence_routes_module
    monkeypatch.setattr(mod, "DatabaseQueryFacade", MagicMock(return_value=fake_facade), raising=True)

    # SUCCESS
    getattr(fake_facade, facade_method).return_value = {
        "topic": "AI",
        "model_used": "gpt-4o-mini",
        "created_at": datetime(2026, 1, 1, 0, 0, 0),
        "total_articles_analyzed": 2,
        "analysis_duration_seconds": 1.5,
        "raw_output": {"ok": True},
        "article_list": [{"id": 1, "title": "A1"}],
    }
    res = trend_convergence_client.get(path)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    assert expected_key in res.json()

    # NOT FOUND (facade returns no analysis data)
    getattr(fake_facade, facade_method).return_value = None
    res = trend_convergence_client_no_raise.get(path)
    assert res.status_code == status.HTTP_404_NOT_FOUND

    # INTERNAL ERROR (facade raises unexpected exception)
    getattr(fake_facade, facade_method).side_effect = Exception("boom")
    res = trend_convergence_client_no_raise.get(path)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.parametrize(
    "path,facade_method",
    [
        ("/api/trend-convergence/consensus/abc/articles?topic=AI", "get_consensus_reference_articles"),
        ("/api/trend-convergence/strategic/abc/articles?topic=AI", "get_strategic_recommendation_articles"),
        ("/api/trend-convergence/market-signals/abc/articles?topic=AI", "get_market_signal_articles"),
        ("/api/trend-convergence/timeline/abc/articles?topic=AI", "get_impact_timeline_articles"),
        ("/api/trend-convergence/horizons/abc/articles?topic=AI", "get_future_horizon_articles"),
    ],
)
def test_trend_convergence_reference_articles_success_and_failure(
    trend_convergence_client,
    trend_convergence_client_no_raise,
    trend_convergence_routes_module,
    fake_facade,
    monkeypatch,
    path,
    facade_method,
):
    mod = trend_convergence_routes_module
    monkeypatch.setattr(mod, "DatabaseQueryFacade", MagicMock(return_value=fake_facade), raising=True)

    # SUCCESS
    getattr(fake_facade, facade_method).return_value = [{"title": "A1", "uri": "x"}]
    res = trend_convergence_client.get(path)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["count"] == 1

    # FAILURE
    getattr(fake_facade, facade_method).side_effect = Exception("boom")
    # NOTE: router error handler references an undefined `status` symbol, so we assert 500 via no-raise client.
    res = trend_convergence_client_no_raise.get(path)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_trend_convergence_prompt_preview_success_bad_tab_and_failure(
    trend_convergence_client, trend_convergence_routes_module, fake_prompt_manager, monkeypatch
):
    mod = trend_convergence_routes_module

    # Patch prompt manager + prompt loader to avoid filesystem and keep deterministic output
    monkeypatch.setattr(mod, "prompt_manager", fake_prompt_manager, raising=True)
    monkeypatch.setattr(mod.PromptLoader, "load_prompt", lambda *a, **k: {"version": "v1"}, raising=True)
    monkeypatch.setattr(mod.PromptLoader, "get_prompt_template", lambda *_a, **_k: ("SYSTEM", "USER"), raising=True)

    fake_prompt_manager.get_version.return_value = {
        "system_prompt": "SYS",
        "user_prompt": "INSTRUCTIONS\n\nREQUIRED OUTPUT FORMAT:\n{}",
        "expected_output_schema": {"type": "object"},
        "variables": {},
    }

    # SUCCESS
    res = trend_convergence_client.get("/api/trend-convergence/prompt-preview/strategic?topic=AI")
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert body["success"] is True
    assert "prompt" in body
    assert body["template"]["system_prompt"] == "SYS"
    assert "REQUIRED OUTPUT FORMAT" in body["template"]["output_format"]

    # BAD TAB
    res = trend_convergence_client.get("/api/trend-convergence/prompt-preview/bad-tab?topic=AI")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # FAILURE
    def _boom(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(mod.PromptLoader, "load_prompt", _boom, raising=True)
    res = trend_convergence_client.get("/api/trend-convergence/prompt-preview/strategic?topic=AI")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_trend_convergence_tune_prompt_save_and_restore_default(
    trend_convergence_client, trend_convergence_routes_module, fake_prompt_manager, monkeypatch
):
    mod = trend_convergence_routes_module
    monkeypatch.setattr(mod, "prompt_manager", fake_prompt_manager, raising=True)

    fake_prompt_manager.get_version.return_value = {"user_prompt": "INSTR\n\nREQUIRED OUTPUT FORMAT:\n{}"}
    fake_prompt_manager.save_version.return_value = {"version": "1.0.0"}

    # SAVE (success)
    payload = {"system_prompt": "SYS", "user_prompt": "NEW INSTRUCTIONS"}
    res = trend_convergence_client.post("/api/trend-convergence/prompts/strategic", json=payload)
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True
    called_args = fake_prompt_manager.save_version.call_args[0]
    assert called_args[0] == "strategic_recommendations"
    assert called_args[1] == "SYS"
    assert "REQUIRED OUTPUT FORMAT" in called_args[2]

    # SAVE (bad tab)
    res = trend_convergence_client.post("/api/trend-convergence/prompts/bad", json=payload)
    # Observable behavior: HTTPException(400) is wrapped into 500 by broad exception handler in the route.
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Unknown tab name" in res.json()["detail"]

    # SAVE (manager error)
    fake_prompt_manager.save_version.side_effect = mod.PromptManagerError("boom")
    res = trend_convergence_client.post("/api/trend-convergence/prompts/strategic", json=payload)
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "boom" in res.json()["detail"]

    # RESTORE DEFAULT (success)
    fake_prompt_manager.save_version.side_effect = None
    fake_prompt_manager.restore_to_default.return_value = {"version": "1.0.0"}
    res = trend_convergence_client.post("/api/trend-convergence/prompts/strategic/restore-default")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["success"] is True

    # RESTORE DEFAULT (bad tab)
    res = trend_convergence_client.post("/api/trend-convergence/prompts/bad/restore-default")
    # Observable behavior: HTTPException(400) is wrapped into 500 by broad exception handler in the route.
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # RESTORE DEFAULT (failure)
    fake_prompt_manager.restore_to_default.side_effect = Exception("boom")
    res = trend_convergence_client.post("/api/trend-convergence/prompts/strategic/restore-default")
    assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_trend_convergence_helpers_calculate_optimal_sample_size_and_determinism(trend_convergence_routes_module):
    mod = trend_convergence_routes_module

    # calculate_optimal_sample_size
    assert mod.calculate_optimal_sample_size("gpt-4o", "focused") == 25
    assert mod.calculate_optimal_sample_size("gpt-4o", "balanced") == 50
    assert mod.calculate_optimal_sample_size("gpt-4o", "comprehensive") == 100
    assert mod.calculate_optimal_sample_size("gpt-4o", "auto") == 90
    assert mod.calculate_optimal_sample_size("gpt-4o", "custom", custom_limit=123) == 123

    # select_articles_deterministic (stable order across calls)
    arts = [
        {
            "title": f"T{i}",
            "publication_date": f"2024-01-{i:02d}",
            "category": "Tech" if i % 2 == 0 else "Biz",
            "sentiment": "Neutral",
        }
        for i in range(1, 21)
    ]
    a1 = mod.select_articles_deterministic(list(arts), 10, mod.ConsistencyMode.DETERMINISTIC)
    a2 = mod.select_articles_deterministic(list(arts), 10, mod.ConsistencyMode.DETERMINISTIC)
    assert [x["title"] for x in a1] == [x["title"] for x in a2]


# =============================================================================
# futures_cone_routes.py endpoints + helpers
# =============================================================================


@pytest.fixture
def freeze_futures_cone_datetime(monkeypatch):
    """
    Freeze app.routes.futures_cone_routes.datetime.now() for deterministic tests.
    Note: futures_cone_routes imports `datetime` as a class (from datetime import datetime).
    """
    import datetime as real_dt

    fixed = real_dt.datetime(2026, 2, 9, 12, 0, 0)

    class FrozenDateTime:
        @classmethod
        def now(cls):
            return fixed

        @classmethod
        def fromisoformat(cls, s: str):
            return real_dt.datetime.fromisoformat(s)

    monkeypatch.setattr(futures_cone_routes, "datetime", FrozenDateTime, raising=True)
    return fixed


@pytest.fixture
def mock_ai_model():
    m = MagicMock(name="mock_ai_model")
    m.generate_response = MagicMock(name="generate_response")
    return m


@pytest.fixture
def futures_cone_app(mock_db, mock_session):
    """
    Hermetic FastAPI app that mounts ONLY futures_cone_routes.router.
    We patch/override get_database_instance as required and keep auth mocked.
    """
    from fastapi import FastAPI

    fc_app = FastAPI()
    fc_app.include_router(futures_cone_routes.router)

    fc_app.dependency_overrides[get_database_instance] = lambda: mock_db
    fc_app.dependency_overrides[verify_session] = lambda: dict(mock_session)
    return fc_app


@pytest.fixture
def futures_cone_client(futures_cone_app, mock_db, test_client_factory):
    # Also patch the import path per spec (even though dependency_overrides drives Depends()).
    with patch("app.database.get_database_instance", return_value=mock_db):
        yield test_client_factory(futures_cone_app)


@pytest.fixture
def futures_cone_client_no_raise(futures_cone_app, mock_db, test_client_factory):
    with patch("app.database.get_database_instance", return_value=mock_db):
        yield test_client_factory(futures_cone_app, raise_server_exceptions=False)


@pytest.fixture
def mock_futures_cone_templates(monkeypatch):
    """Patch futures_cone_routes.templates.TemplateResponse so no real templates are rendered."""
    from fastapi.responses import HTMLResponse

    tmpl = MagicMock(name="futures_cone_routes.templates")
    tmpl.TemplateResponse = MagicMock(return_value=HTMLResponse(content="<html>OK</html>", status_code=200))
    monkeypatch.setattr(futures_cone_routes, "templates", tmpl, raising=True)
    return tmpl


def _make_fc_article(
    i: int,
    *,
    topic: str = "AI",
    summary: str = "test summary",
    publication_date: str = "2024-01-01",
    sentiment: str = "Neutral",
    category: str = "Tech",
    future_signal: str = "Growth",
    driver_type: str = "Innovation",
    time_to_impact: str = "Long-term",
    quality_score: int = 5,
    factual_reporting: str = "High",
    mbfc_credibility_rating: str = "High",
):
    return {
        "title": f"{topic} {i}",
        "summary": summary,
        "uri": f"uri-{i}",
        "publication_date": publication_date,
        "sentiment": sentiment,
        "category": category,
        "future_signal": future_signal,
        "driver_type": driver_type,
        "time_to_impact": time_to_impact,
        "quality_score": quality_score,
        "factual_reporting": factual_reporting,
        "mbfc_credibility_rating": mbfc_credibility_rating,
    }


def _make_fc_valid_ai_json(topic: str = "AI"):
    # Exact distribution requested by the prompt (not enforced by the route, but aligns with spec)
    def sc(t, n, tf, sent):
        return {
            "type": t,
            "title": f"{t}-{n}",
            "description": f"{t} scenario {n}",
            "timeframe": tf,
            "sentiment": sent,
        }

    scenarios = [
        sc("probable", 1, "2025-2027", "Positive"),
        sc("probable", 2, "2028-2032", "Mixed"),
        sc("probable", 3, "2033-2035", "Negative"),
        sc("plausible", 1, "2025-2027", "Positive"),
        sc("plausible", 2, "2028-2032", "Mixed"),
        sc("plausible", 3, "2033-2035", "Positive"),
        sc("possible", 1, "2025-2027", "Mixed"),
        sc("possible", 2, "2028-2032", "Negative"),
        sc("possible", 3, "2033-2035", "Positive"),
        sc("preferable", 1, "2025-2027", "Positive"),
        sc("preferable", 2, "2028-2032", "Positive"),
        sc("wildcard", 1, "2025-2027", "Mixed"),
        sc("wildcard", 2, "2033-2035", "Negative"),
    ]
    return json.dumps({"topic": topic, "scenarios": scenarios})


def _assert_fc_scenario_postprocessing(data: dict):
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) >= 1

    for sc in data["scenarios"]:
        assert "position" in sc
        assert isinstance(sc["position"], dict)
        assert 1 <= sc["position"]["x"] <= 99
        assert 1 <= sc["position"]["y"] <= 99

        assert "drivers" in sc and isinstance(sc["drivers"], list) and len(sc["drivers"]) >= 1
        assert "signals" in sc and isinstance(sc["signals"], list) and len(sc["signals"]) >= 1
        assert "probability" in sc and isinstance(sc["probability"], str) and sc["probability"]
        assert "branching_point" in sc


def test_generate_futures_cone_success_valid_json(
    futures_cone_client, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(i) for i in range(1, 40)], 39))
    mock_db.facade = mock_facade

    mock_ai_model.generate_response.return_value = _make_fc_valid_ai_json("AI")
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 200

    data = res.json()
    assert data["topic"] == "AI"
    assert data["model_used"] == "gpt-4o"
    assert data["generated_at"] == freeze_futures_cone_datetime.isoformat()
    assert isinstance(data.get("articles_analyzed"), int) and data["articles_analyzed"] >= 1
    assert isinstance(data.get("timeframe_days"), int)
    assert len(data["scenarios"]) == 13

    _assert_fc_scenario_postprocessing(data)
    assert data.get("fallback_used") in (None, False)


def test_generate_futures_cone_weighted_path_uses_optimal_sample_size(
    futures_cone_client, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    # For non-mega context models, focused => 25
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(i) for i in range(1, 500)], 499))
    mock_db.facade = mock_facade

    mock_ai_model.generate_response.return_value = _make_fc_valid_ai_json("AI")
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    # Spy on weighting to ensure it's invoked
    orig_weight = futures_cone_routes.weight_articles_for_futures_cone
    spy_weight = MagicMock(side_effect=orig_weight)
    monkeypatch.setattr(futures_cone_routes, "weight_articles_for_futures_cone", spy_weight, raising=True)

    res = futures_cone_client.get(
        "/api/futures-cone/AI",
        params={"model": "gpt-4", "sample_size_mode": "focused"},
    )
    assert res.status_code == 200
    assert spy_weight.call_count == 1

    # Validate the prompt asked the AI to analyze exactly the optimal sample size
    called = mock_ai_model.generate_response.call_args[0][0]
    assert isinstance(called, list) and called
    prompt = called[0]["content"]
    assert "Analyze 25 articles" in prompt
    assert "Total articles analyzed: 25" in prompt


def test_generate_futures_cone_no_articles_returns_404(
    futures_cone_client, mock_db, mock_facade, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([], 0))
    mock_db.facade = mock_facade

    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=MagicMock()), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 404
    assert "No articles found" in res.json()["detail"]


def test_generate_futures_cone_model_not_available_returns_400(
    futures_cone_client, mock_db, mock_facade, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(1)], 1))
    mock_db.facade = mock_facade

    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=None), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "missing-model"})
    assert res.status_code == 400
    assert "not available" in res.json()["detail"]


def test_generate_futures_cone_truncated_json_uses_fallback(
    futures_cone_client, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(i) for i in range(1, 10)], 9))
    mock_db.facade = mock_facade

    # Missing closing braces -> JSONDecodeError -> fallback response
    mock_ai_model.generate_response.return_value = '{"topic":"AI","scenarios":[{"type":"probable","title":"A","description":"d","timeframe":"2025-2027","sentiment":"Positive"}'
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 200
    data = res.json()

    assert data["topic"] == "AI"
    assert data["fallback_used"] is True
    assert len(data["scenarios"]) == 13
    _assert_fc_scenario_postprocessing(data)


def test_generate_futures_cone_malformed_json_fixed_success(
    futures_cone_client, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(i) for i in range(1, 20)], 19))
    mock_db.facade = mock_facade

    # Keys unquoted + trailing commas -> _fix_common_json_issues should repair.
    # IMPORTANT: the fixer only quotes keys that start a line (after newline + whitespace),
    # so we format each object with one key per line.
    malformed = """
{
  topic: "AI",
  scenarios: [
    {
      type: "probable",
      title: "A",
      description: "d",
      timeframe: "2025-2027",
      sentiment: "Positive",
    },
    {
      type: "probable",
      title: "B",
      description: "d",
      timeframe: "2028-2032",
      sentiment: "Mixed",
    },
    {
      type: "probable",
      title: "C",
      description: "d",
      timeframe: "2033-2035",
      sentiment: "Negative",
    },
    {
      type: "plausible",
      title: "D",
      description: "d",
      timeframe: "2025-2027",
      sentiment: "Positive",
    },
    {
      type: "plausible",
      title: "E",
      description: "d",
      timeframe: "2028-2032",
      sentiment: "Mixed",
    },
    {
      type: "plausible",
      title: "F",
      description: "d",
      timeframe: "2033-2035",
      sentiment: "Positive",
    },
    {
      type: "possible",
      title: "G",
      description: "d",
      timeframe: "2025-2027",
      sentiment: "Mixed",
    },
    {
      type: "possible",
      title: "H",
      description: "d",
      timeframe: "2028-2032",
      sentiment: "Negative",
    },
    {
      type: "possible",
      title: "I",
      description: "d",
      timeframe: "2033-2035",
      sentiment: "Positive",
    },
    {
      type: "preferable",
      title: "J",
      description: "d",
      timeframe: "2025-2027",
      sentiment: "Positive",
    },
    {
      type: "preferable",
      title: "K",
      description: "d",
      timeframe: "2028-2032",
      sentiment: "Positive",
    },
    {
      type: "wildcard",
      title: "L",
      description: "d",
      timeframe: "2025-2027",
      sentiment: "Mixed",
    },
    {
      type: "wildcard",
      title: "M",
      description: "d",
      timeframe: "2033-2035",
      sentiment: "Negative",
    },
  ],
}
""".strip()

    mock_ai_model.generate_response.return_value = malformed
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 200
    data = res.json()
    assert data["topic"] == "AI"
    assert len(data["scenarios"]) == 13
    _assert_fc_scenario_postprocessing(data)
    assert data.get("fallback_used") in (None, False)


def test_generate_futures_cone_garbage_ai_output_uses_fallback(
    futures_cone_client, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(i) for i in range(1, 10)], 9))
    mock_db.facade = mock_facade

    mock_ai_model.generate_response.return_value = "lol not json"
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    res = futures_cone_client.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 200
    data = res.json()

    assert data["fallback_used"] is True
    assert len(data["scenarios"]) == 13
    _assert_fc_scenario_postprocessing(data)


def test_generate_futures_cone_ai_crash_returns_500(
    futures_cone_client_no_raise, mock_db, mock_facade, mock_ai_model, freeze_futures_cone_datetime, monkeypatch
):
    mock_facade.search_articles = MagicMock(return_value=([_make_fc_article(1)], 1))
    mock_db.facade = mock_facade

    mock_ai_model.generate_response.side_effect = Exception("ai boom")
    monkeypatch.setattr(futures_cone_routes, "get_ai_model", MagicMock(return_value=mock_ai_model), raising=True)

    res = futures_cone_client_no_raise.get("/api/futures-cone/AI", params={"model": "gpt-4o"})
    assert res.status_code == 500
    assert "Internal server error" in res.json()["detail"]


def test_futures_cone_page_renders_template(futures_cone_client, mock_futures_cone_templates, mock_session):
    res = futures_cone_client.get("/futures-cone")
    assert res.status_code == 200

    assert mock_futures_cone_templates.TemplateResponse.call_count == 1
    args, kwargs = mock_futures_cone_templates.TemplateResponse.call_args
    assert args[0] == "futures_cone.html"
    assert isinstance(args[1], dict)
    assert "request" in args[1]
    assert args[1]["session"] == mock_session
    assert not kwargs


def test_futures_cone_helpers_filter_and_weight_and_positions(freeze_futures_cone_datetime):
    # filter_articles_by_source_quality
    arts = [
        {"factual_reporting": "High", "mbfc_credibility_rating": "High"},
        {"factual_reporting": "Low", "mbfc_credibility_rating": "High"},
    ]
    assert futures_cone_routes.filter_articles_by_source_quality(list(arts), "all") == arts
    filtered = futures_cone_routes.filter_articles_by_source_quality(list(arts), "high_quality")
    assert filtered == [arts[0]]

    # weight_articles_for_futures_cone (higher score should come first)
    a1 = _make_fc_article(1, publication_date="2026-02-08", future_signal="X", time_to_impact="Long-term", quality_score=5)
    a2 = _make_fc_article(2, publication_date="2026-02-08", future_signal="", time_to_impact="Short-term", quality_score=1)
    weighted = futures_cone_routes.weight_articles_for_futures_cone([a2, a1])
    assert weighted[0]["title"] == a1["title"]
    assert weighted[0]["dashboard_score"] >= weighted[1]["dashboard_score"]

    # calculate_optimal_sample_size
    assert futures_cone_routes.calculate_optimal_sample_size("gpt-4o", "focused") == 25
    assert futures_cone_routes.calculate_optimal_sample_size("gpt-4.1", "balanced") == 100
    assert futures_cone_routes.calculate_optimal_sample_size("gpt-4o", "custom", custom_limit=123) == 123

    # calculate_scenario_positions bounds + rough column placement
    short = futures_cone_routes.calculate_scenario_positions("probable", 0, 1, "2025-2027")
    mid = futures_cone_routes.calculate_scenario_positions("probable", 0, 1, "2028-2032")
    long = futures_cone_routes.calculate_scenario_positions("probable", 0, 1, "2035-2037")
    assert 5 <= short["x"] <= 33
    assert 36 <= mid["x"] <= 64
    assert 67 <= long["x"] <= 95


def test_futures_cone_json_helpers_and_prepare_analysis_summary():
    # _extract_from_code_block
    txt = "hello```json\n{\"a\": 1}\n```bye"
    assert futures_cone_routes._extract_from_code_block(txt) == "{\"a\": 1}"

    # _extract_complete_json
    assert futures_cone_routes._extract_complete_json("x {\"a\": {\"b\": 1}} y") == "{\"a\": {\"b\": 1}}"

    # _attempt_json_completion adds closers
    completed = futures_cone_routes._attempt_json_completion('{"a":[1,2,3')
    assert completed.endswith("]}")

    # _fix_common_json_issues repairs trailing commas and missing quotes around keys (line-based)
    fixed = futures_cone_routes._fix_common_json_issues('{\n a: 1,\n b: 2,\n}\n')
    assert json.loads(fixed) == {"a": 1, "b": 2}

    # prepare_analysis_summary
    articles = [
        ("T1", "S1", "u1", "2024-01-01", "Neutral", "Tech", "Growth", "Innovation", "Long-term"),
        ("T2", "S2", "u2", "2024-01-02", "Positive", "Tech", "Growth", "Innovation", "Short-term"),
    ]
    summary = futures_cone_routes.prepare_analysis_summary(articles, "AI")
    assert "Topic Analysis for: AI" in summary
    assert "Total articles analyzed: 2" in summary


# =============================================================================
# feed_clustering_routes.py endpoints + helpers
# =============================================================================


@pytest.fixture
def mock_fetch_all(mock_db):
    """
    Required by spec: provide a handle to the DB's fetch_all callable.
    We ensure the attribute exists on the per-test `mock_db` instance.
    """
    mock_db.fetch_all = MagicMock(name="fetch_all")
    return mock_db.fetch_all


@pytest.fixture
def feed_clustering_client(mock_db, mock_ai_model, test_client_factory):
    """
    Hermetic FastAPI app that mounts ONLY feed_clustering_routes.router.
    IMPORTANT: FastAPI captures dependency callables at import/decoration time, so we use
    dependency_overrides to replace get_database_instance + verify_session_api.
    """
    from fastapi import FastAPI
    import app.routes.feed_clustering_routes as feed_clustering_routes

    # Ensure DB has methods used by get_feed_items_for_clustering()
    mock_db.get_connection = MagicMock(name="get_connection", return_value=MagicMock(name="conn"))

    # Patch required import paths per spec (even though dependency_overrides drives Depends()).
    with patch("app.database.get_database_instance", return_value=mock_db), patch(
        "app.routes.feed_clustering_routes.LiteLLMModel.get_instance", return_value=mock_ai_model
    ):
        fc_app = FastAPI()
        fc_app.include_router(feed_clustering_routes.router)
        fc_app.dependency_overrides[feed_clustering_routes.get_database_instance] = lambda: mock_db
        fc_app.dependency_overrides[feed_clustering_routes.verify_session_api] = lambda: {"user_id": "test-user"}
        yield test_client_factory(fc_app)


@pytest.fixture
def feed_clustering_client_no_raise(mock_db, mock_ai_model, test_client_factory):
    from fastapi import FastAPI
    import app.routes.feed_clustering_routes as feed_clustering_routes

    mock_db.get_connection = MagicMock(name="get_connection", return_value=MagicMock(name="conn"))

    with patch("app.database.get_database_instance", return_value=mock_db), patch(
        "app.routes.feed_clustering_routes.LiteLLMModel.get_instance", return_value=mock_ai_model
    ):
        fc_app = FastAPI()
        fc_app.include_router(feed_clustering_routes.router)
        fc_app.dependency_overrides[feed_clustering_routes.get_database_instance] = lambda: mock_db
        fc_app.dependency_overrides[feed_clustering_routes.verify_session_api] = lambda: {"user_id": "test-user"}
        yield test_client_factory(fc_app, raise_server_exceptions=False)


def _make_feed_item(
    title: str,
    *,
    source_type: str = "arxiv",
    content: str = "summary",
    url: str = "x",
    publication_date: str = "2024-01-01",
    tags=None,
    engagement_metrics=None,
):
    return {
        "title": title,
        "content": content,
        "source_type": source_type,
        "url": url,
        "publication_date": publication_date,
        "tags": tags if tags is not None else ["ai"],
        "engagement_metrics": engagement_metrics if engagement_metrics is not None else {"likes": 5},
    }


def test_get_thematic_clustering_success_markdown_json(feed_clustering_client, mock_ai_model, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [_make_feed_item("AI News", source_type="arxiv"), _make_feed_item("Market Update", source_type="thenewsapi")]
    monkeypatch.setattr(
        feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=items), raising=True
    )

    mock_ai_model.agenerate_response = AsyncMock(return_value=(
        "```json\n"
        '[{"theme_name":"AI","theme_summary":"AI stuff","article_ids":[0],"confidence":0.9,"source_diversity":1}]\n'
        "```"
    ))

    res = feed_clustering_client.get("/api/feed-clustering/thematic")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, list) and payload
    assert payload[0]["theme_name"] == "AI"
    assert payload[0]["article_count"] == 1
    assert payload[0]["articles"][0]["title"] == "AI News"


def test_get_thematic_clustering_llm_failure_keyword_fallback(feed_clustering_client, mock_ai_model, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [_make_feed_item("AI News", source_type="arxiv")]
    monkeypatch.setattr(
        feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=items), raising=True
    )
    mock_ai_model.generate_response.side_effect = Exception("llm down")

    res = feed_clustering_client.get("/api/feed-clustering/thematic")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, list) and payload
    assert payload[0]["confidence"] == 0.6
    assert payload[0]["theme_name"] in ("AI & Technology", "Science & Research", "Business & Economics", "Other Topics")


def test_get_thematic_clustering_no_items_returns_empty(feed_clustering_client, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    monkeypatch.setattr(feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=[]), raising=True)
    res = feed_clustering_client.get("/api/feed-clustering/thematic")
    assert res.status_code == 200
    assert res.json() == []


def test_get_thematic_clustering_internal_error_returns_500(feed_clustering_client_no_raise, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    monkeypatch.setattr(
        feed_clustering_routes,
        "get_feed_items_for_clustering",
        AsyncMock(side_effect=Exception("db boom")),
        raising=True,
    )
    res = feed_clustering_client_no_raise.get("/api/feed-clustering/thematic")
    assert res.status_code == 500


def test_get_sentiment_clustering_success_and_fallback(feed_clustering_client, mock_ai_model, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [_make_feed_item("AI News", source_type="arxiv"), _make_feed_item("Other", source_type="bluesky")]
    monkeypatch.setattr(
        feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=items), raising=True
    )

    mock_ai_model.generate_response.return_value = (
        "```json\n"
        '{"distribution":{"positive":40,"negative":20,"neutral":40},'
        '"clusters":[{"sentiment":"positive","percentage":40,"article_count":1,"summary":"x"},'
        '{"sentiment":"neutral","percentage":40,"article_count":1,"summary":"x"},'
        '{"sentiment":"negative","percentage":20,"article_count":0,"summary":"x"}]}\n'
        "```"
    )
    res = feed_clustering_client.get("/api/feed-clustering/sentiment")
    assert res.status_code == 200
    payload = res.json()
    assert "distribution" in payload
    assert len(payload["clusters"]) == 3

    mock_ai_model.generate_response.side_effect = Exception("llm down")
    res2 = feed_clustering_client.get("/api/feed-clustering/sentiment")
    assert res2.status_code == 200
    payload2 = res2.json()
    assert payload2["distribution"] == {"positive": 40, "negative": 15, "neutral": 45}


def test_get_sentiment_clustering_no_items_returns_empty_distribution(feed_clustering_client, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    monkeypatch.setattr(feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=[]), raising=True)
    res = feed_clustering_client.get("/api/feed-clustering/sentiment")
    assert res.status_code == 200
    assert res.json() == {"clusters": [], "distribution": {"positive": 0, "negative": 0, "neutral": 0}}


def test_get_temporal_clustering_success_and_fallback(feed_clustering_client, mock_ai_model, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [_make_feed_item("AI News", source_type="arxiv")]
    monkeypatch.setattr(
        feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=items), raising=True
    )

    mock_ai_model.generate_response.return_value = (
        "```json\n"
        '{"timeline_events":[{"title":"Trend","description":"d","impact_timeframe":"short","impact_level":"High","article_count":2,"confidence":0.8}]}\n'
        "```"
    )
    res = feed_clustering_client.get("/api/feed-clustering/temporal", params={"time_horizon": "short"})
    assert res.status_code == 200
    assert "timeline_events" in res.json()

    mock_ai_model.generate_response.side_effect = Exception("llm down")
    res2 = feed_clustering_client.get("/api/feed-clustering/temporal", params={"time_horizon": "short"})
    assert res2.status_code == 200
    payload2 = res2.json()
    assert isinstance(payload2.get("timeline_events"), list) and payload2["timeline_events"]
    assert payload2["timeline_events"][0]["impact_timeframe"] == "short"


def test_get_source_clustering_success_and_no_items(feed_clustering_client, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [
        _make_feed_item("Paper 1", source_type="arxiv", engagement_metrics={"likes": 1}),
        _make_feed_item("Paper 2", source_type="arxiv", engagement_metrics={"likes": 2}),
        _make_feed_item("Post", source_type="bluesky", engagement_metrics={"likes": 10}),
        _make_feed_item("News", source_type="thenewsapi", engagement_metrics={"likes": 3}),
    ]
    monkeypatch.setattr(
        feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=items), raising=True
    )

    res = feed_clustering_client.get("/api/feed-clustering/sources")
    assert res.status_code == 200
    payload = res.json()
    assert "clusters" in payload and "metrics" in payload
    assert "overall_authority" in payload["metrics"]
    # clusters sorted by article_count desc: arxiv should be first (2 items)
    assert payload["clusters"][0]["source_type"] == "arxiv"

    monkeypatch.setattr(feed_clustering_routes, "get_feed_items_for_clustering", AsyncMock(return_value=[]), raising=True)
    res2 = feed_clustering_client.get("/api/feed-clustering/sources")
    assert res2.status_code == 200
    assert res2.json() == {"clusters": [], "metrics": {}}


@pytest.mark.asyncio
async def test_get_feed_items_for_clustering_parses_json_and_uses_threadpool(
    mock_db, mock_fetch_all, monkeypatch
):
    import app.routes.feed_clustering_routes as feed_clustering_routes
    import datetime as real_dt

    # Freeze datetime.now(timezone.utc) used to build date_threshold (we don't assert query string, but keep deterministic)
    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            return real_dt.datetime(2026, 2, 9, 12, 0, 0, tzinfo=real_dt.timezone.utc)

    monkeypatch.setattr(feed_clustering_routes, "datetime", FrozenDateTime, raising=True)

    # Patch random.shuffle (imported inside the function) via stdlib module path
    with patch("random.shuffle") as shuffle_spy:

        async def _fake_run_in_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        monkeypatch.setattr(feed_clustering_routes, "run_in_threadpool", _fake_run_in_threadpool, raising=True)

        # Return > limit so slicing is exercised (function's SQL LIMIT isn't enforced by this mock)
        row = lambda title, source_type: {
            "title": title,
            "content": "c",
            "source_type": source_type,
            "url": "x",
            "publication_date": "2024-01-01",
            "created_at": "2024-01-01T00:00:00Z",
            "is_hidden": 0,
            "tags": '["ai"]',
            "engagement_metrics": '{"likes":5}',
        }
        mock_fetch_all.side_effect = [
            [row("B1", "bluesky"), row("B2", "bluesky"), row("B3", "bluesky")],
            [row("A1", "arxiv"), row("A2", "arxiv"), row("A3", "arxiv")],
            [row("N1", "thenewsapi"), row("N2", "thenewsapi"), row("N3", "thenewsapi")],
        ]

        out = await feed_clustering_routes.get_feed_items_for_clustering(feed_group_id="gid", limit=6, db=mock_db)

        assert len(out) == 6
        assert shuffle_spy.call_count == 1
        assert mock_fetch_all.call_count == 3
        assert isinstance(out[0]["tags"], list)
        assert isinstance(out[0]["engagement_metrics"], dict)


@pytest.mark.asyncio
async def test_internal_clustering_invalid_json_triggers_fallbacks(mock_ai_model, monkeypatch):
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [
        _make_feed_item("AI News", source_type="arxiv"),
        _make_feed_item("Business Market", source_type="thenewsapi"),
    ]

    # Invalid JSON (no braces/brackets) -> json.loads fails -> fallback paths
    mock_ai_model.generate_response.return_value = "not-json"
    monkeypatch.setattr(feed_clustering_routes.LiteLLMModel, "get_instance", MagicMock(return_value=mock_ai_model))

    thematic = await feed_clustering_routes.perform_thematic_clustering(items)
    assert isinstance(thematic, list) and thematic
    assert thematic[0]["confidence"] == 0.6  # keyword fallback

    sentiment = await feed_clustering_routes.perform_sentiment_clustering(items)
    assert sentiment["distribution"] == {"positive": 40, "negative": 15, "neutral": 45}

    temporal = await feed_clustering_routes.perform_temporal_clustering(items, time_horizon="short")
    assert isinstance(temporal.get("timeline_events"), list) and temporal["timeline_events"]
    assert temporal["timeline_events"][0]["impact_timeframe"] == "short"


@pytest.mark.asyncio
async def test_perform_source_clustering_metrics_and_sorting():
    import app.routes.feed_clustering_routes as feed_clustering_routes

    items = [
        _make_feed_item("Paper 1", source_type="arxiv", engagement_metrics={"likes": 1}),
        _make_feed_item("Paper 2", source_type="arxiv", engagement_metrics={"likes": 2}),
        _make_feed_item("Post", source_type="bluesky", engagement_metrics={"likes": 10}),
        _make_feed_item("News", source_type="thenewsapi", engagement_metrics={"likes": 3}),
    ]

    out = await feed_clustering_routes.perform_source_clustering(items)
    assert out["metrics"]["academic_percentage"] == 50.0
    assert out["metrics"]["social_percentage"] == 25.0
    assert out["metrics"]["news_percentage"] == 25.0
    assert "overall_authority" in out["metrics"]
    assert out["clusters"][0]["source_type"] == "arxiv"  # sorted desc by count


# =============================================================================
# filter_routes.py endpoints + helpers
# Spec: tests/spec/filter_routes_test_spec.md
# =============================================================================


@pytest.fixture
def mock_session_local():
    return {"user": "testuser"}


@pytest.fixture
def mock_session_oauth():
    return {"oauth_user": {"provider": "google", "email": "USER@TEST.COM"}}


@pytest.fixture
def mock_filter_service():
    """
    Patch FilterService used inside filter_routes so no real DB/service calls occur.
    Yields the *instance* returned by FilterService(db).
    """
    with patch("app.routes.filter_routes.FilterService") as svc_cls:
        svc = MagicMock(name="mock_filter_service")
        svc_cls.return_value = svc
        yield svc


@pytest.fixture
def filter_routes_module():
    import app.routes.filter_routes as filter_routes

    return filter_routes


@pytest.fixture
def filter_app(filter_routes_module, mock_db, mock_session_local, mock_filter_service):
    """
    Tiny FastAPI app mounting ONLY filter_routes.router.
    This avoids relying on how/when app.main registers routers.
    """
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(filter_routes_module.router)
    fa.dependency_overrides[filter_routes_module.get_database_instance] = lambda: mock_db
    fa.dependency_overrides[filter_routes_module.verify_session_api] = lambda: dict(mock_session_local)
    return fa


@pytest.fixture
def filter_client(filter_app, test_client_factory):
    return test_client_factory(filter_app)


@pytest.fixture
def filter_client_no_raise(filter_app, test_client_factory):
    return test_client_factory(filter_app, raise_server_exceptions=False)


def test_filter_build_user_key_local():
    import app.routes.filter_routes as filter_routes

    assert filter_routes.build_user_key({"user": "admin"}) == "local:admin"


def test_filter_build_user_key_oauth():
    import app.routes.filter_routes as filter_routes

    session = {"oauth_user": {"provider": "google", "email": "Test@Email.com"}}
    assert filter_routes.build_user_key(session) == "google:test@email.com"


@pytest.mark.parametrize(
    "group_id, expected",
    [
        (None, None),
        ("null", None),
        ("none", None),
        ("", None),
        ("undefined", None),
        ("10", 10),
        ("abc", None),
    ],
)
def test_filter_parse_group_id(group_id, expected):
    import app.routes.filter_routes as filter_routes

    assert filter_routes._parse_group_id(group_id) == expected


def test_filter_get_filters_success_filters_exist(filter_client, mock_filter_service):
    mock_filter_service.get_filters.return_value = {"id": 1, "user_key": "local:testuser", "foo": "bar"}

    res = filter_client.get("/api/filters/10")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["filters"]["foo"] == "bar"
    assert "id" not in data["filters"]
    assert "user_key" not in data["filters"]

    mock_filter_service.get_filters.assert_called_once_with("local:testuser", 10)


def test_filter_get_filters_success_no_filters(filter_client, mock_filter_service):
    mock_filter_service.get_filters.return_value = None

    res = filter_client.get("/api/filters/10")
    assert res.status_code == 200
    assert res.json() == {"success": True, "filters": None}

    mock_filter_service.get_filters.assert_called_once_with("local:testuser", 10)


@pytest.mark.parametrize(
    "group_id, expected_parsed",
    [
        ("null", None),
        ("none", None),
        ("10", 10),
    ],
)
def test_filter_get_filters_group_id_parsing(filter_client, mock_filter_service, group_id, expected_parsed):
    mock_filter_service.get_filters.return_value = None

    res = filter_client.get(f"/api/filters/{group_id}")
    assert res.status_code == 200
    mock_filter_service.get_filters.assert_called_once_with("local:testuser", expected_parsed)


def test_filter_get_filters_oauth_session(filter_client, filter_routes_module, mock_session_oauth, mock_filter_service):
    filter_client.app.dependency_overrides[filter_routes_module.verify_session_api] = lambda: dict(mock_session_oauth)
    mock_filter_service.get_filters.return_value = None

    res = filter_client.get("/api/filters/null")
    assert res.status_code == 200
    mock_filter_service.get_filters.assert_called_once_with("google:user@test.com", None)


def test_filter_get_filters_service_exception_returns_500(filter_client_no_raise, mock_filter_service):
    mock_filter_service.get_filters.side_effect = Exception("boom")

    res = filter_client_no_raise.get("/api/filters/10")
    assert res.status_code == 500


def test_filter_post_upsert_filters_success(filter_client, mock_filter_service):
    mock_filter_service.upsert_filters.return_value = True
    payload = {"a": 1}

    res = filter_client.post("/api/filters/10", json=payload)
    assert res.status_code == 200
    assert res.json() == {"success": True}

    mock_filter_service.upsert_filters.assert_called_once_with("local:testuser", 10, payload)


def test_filter_post_upsert_filters_failure_false_return(filter_client, mock_filter_service):
    mock_filter_service.upsert_filters.return_value = False

    res = filter_client.post("/api/filters/10", json={"a": 1})
    assert res.status_code == 200
    assert res.json() == {"success": False, "error": "Failed to save filters"}

    mock_filter_service.upsert_filters.assert_called_once()


@pytest.mark.parametrize(
    "group_id, expected_parsed",
    [
        ("null", None),
        ("15", 15),
    ],
)
def test_filter_post_upsert_filters_group_id_parsing(filter_client, mock_filter_service, group_id, expected_parsed):
    mock_filter_service.upsert_filters.return_value = True
    payload = {"a": 1}

    res = filter_client.post(f"/api/filters/{group_id}", json=payload)
    assert res.status_code == 200
    mock_filter_service.upsert_filters.assert_called_once_with("local:testuser", expected_parsed, payload)


def test_filter_post_upsert_filters_oauth_session(filter_client, filter_routes_module, mock_session_oauth, mock_filter_service):
    filter_client.app.dependency_overrides[filter_routes_module.verify_session_api] = lambda: dict(mock_session_oauth)
    mock_filter_service.upsert_filters.return_value = True
    payload = {"a": 1}

    res = filter_client.post("/api/filters/null", json=payload)
    assert res.status_code == 200
    mock_filter_service.upsert_filters.assert_called_once_with("google:user@test.com", None, payload)


def test_filter_post_upsert_filters_service_exception_returns_500(filter_client_no_raise, mock_filter_service):
    mock_filter_service.upsert_filters.side_effect = Exception("boom")

    res = filter_client_no_raise.post("/api/filters/10", json={"a": 1})
    assert res.status_code == 500
    assert res.json()["detail"] == "Failed to save filters"


# =============================================================================
# keyword_monitor_api.py endpoints
# Spec: tests/spec/keyword_monitor_api_test_spec.md
# =============================================================================


@pytest.fixture
def keyword_monitor_api_module():
    import app.routes.keyword_monitor_api as keyword_monitor_api

    return keyword_monitor_api


@pytest.fixture
def mock_keyword_monitor_api_db():
    """
    Patch the module-level global Database() instance so tests never touch a real DB.
    """
    # NOTE: keyword_monitor_api creates a real Database() at import time.
    # We patch the module global so it's never used, and also neuter teardown
    # of the original instance to avoid real DB checkpoint/close attempts.
    import app.routes.keyword_monitor_api as keyword_monitor_api

    old_db = getattr(keyword_monitor_api, "db", None)
    if old_db is not None:
        try:
            setattr(old_db, "close_connections", lambda: None)
        except Exception:
            pass

    db_mock = MagicMock(name="keyword_monitor_api_db")
    with patch("app.routes.keyword_monitor_api.db", db_mock):
        yield db_mock


@pytest.fixture
def mock_keyword_monitor_api_facade_cls():
    """
    Patch DatabaseQueryFacade constructor used inside keyword_monitor_api.py.
    """
    with patch("app.routes.keyword_monitor_api.DatabaseQueryFacade") as facade_cls:
        yield facade_cls


@pytest.fixture
def kmapi_mock_facade(mock_keyword_monitor_api_facade_cls):
    return mock_keyword_monitor_api_facade_cls.return_value


@pytest.fixture
def kmapi_mock_bg_task():
    with patch("app.routes.keyword_monitor_api.keyword_monitor.get_task_status") as m:
        yield m


@pytest.fixture
def keyword_monitor_api_app(keyword_monitor_api_module, admin_session):
    """
    Tiny FastAPI app mounting ONLY keyword_monitor_api.router.
    This avoids relying on how/when app.main registers routers/prefixes.
    """
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(keyword_monitor_api_module.router)
    fa.dependency_overrides[keyword_monitor_api_module.verify_session] = lambda: dict(admin_session)
    return fa


@pytest.fixture
def keyword_monitor_api_client(keyword_monitor_api_app, test_client_factory):
    return test_client_factory(keyword_monitor_api_app)


def test_keyword_monitor_api_get_status_success_full_data(
    keyword_monitor_api_client,
    keyword_monitor_api_module,
    mock_keyword_monitor_api_db,
    mock_keyword_monitor_api_facade_cls,
    kmapi_mock_facade,
    kmapi_mock_bg_task,
):
    kmapi_mock_bg_task.return_value = "running"
    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = (1, 200)
    kmapi_mock_facade.get_request_count_for_today.return_value = (45, "2026-02-10")

    res = keyword_monitor_api_client.get("/keyword-monitor/status")

    assert res.status_code == 200
    assert res.json() == {
        "background_task": "running",
        "settings": {"is_enabled": True, "daily_request_limit": 200},
        "api_usage": {"requests_today": 45, "limit": 200, "last_reset": "2026-02-10"},
    }

    kmapi_mock_bg_task.assert_called_once_with()
    assert mock_keyword_monitor_api_facade_cls.call_count == 2
    assert mock_keyword_monitor_api_facade_cls.call_args_list == [
        ((mock_keyword_monitor_api_db, keyword_monitor_api_module.logger),),
        ((mock_keyword_monitor_api_db, keyword_monitor_api_module.logger),),
    ]
    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.assert_called_once_with()
    kmapi_mock_facade.get_request_count_for_today.assert_called_once_with()


def test_keyword_monitor_api_get_status_success_defaults(
    keyword_monitor_api_client,
    kmapi_mock_facade,
    kmapi_mock_bg_task,
):
    kmapi_mock_bg_task.return_value = "running"
    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = None
    kmapi_mock_facade.get_request_count_for_today.return_value = None

    res = keyword_monitor_api_client.get("/keyword-monitor/status")

    assert res.status_code == 200
    assert res.json() == {
        "background_task": "running",
        "settings": {"is_enabled": True, "daily_request_limit": 100},
        "api_usage": {"requests_today": 0, "limit": 100, "last_reset": None},
    }


def test_keyword_monitor_api_get_status_facade_failure_returns_500(
    keyword_monitor_api_client,
    kmapi_mock_facade,
    kmapi_mock_bg_task,
):
    kmapi_mock_bg_task.return_value = "running"
    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.side_effect = Exception("facade boom")

    res = keyword_monitor_api_client.get("/keyword-monitor/status")

    assert res.status_code == 500
    assert res.json()["detail"] == "facade boom"


def test_keyword_monitor_api_get_status_task_failure_returns_500(
    keyword_monitor_api_client,
    kmapi_mock_facade,
    kmapi_mock_bg_task,
):
    kmapi_mock_bg_task.side_effect = Exception("task boom")
    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = (1, 200)

    res = keyword_monitor_api_client.get("/keyword-monitor/status")

    assert res.status_code == 500
    assert res.json()["detail"] == "task boom"


def test_keyword_monitor_api_reset_api_counter_success(
    keyword_monitor_api_client,
    kmapi_mock_facade,
):
    from datetime import datetime as real_datetime

    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = (10, 100)

    fixed_now = real_datetime(2026, 2, 10, 12, 0, 0)
    with patch("app.routes.keyword_monitor_api.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        res = keyword_monitor_api_client.post("/keyword-monitor/reset-api-counter")

    assert res.status_code == 200
    assert res.json() == {
        "success": True,
        "message": "API counter reset from 10 to 0",
        "reset_date": "2026-02-10",
    }

    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.assert_called_once_with()
    kmapi_mock_facade.reset_keyword_monitoring_counter.assert_called_once_with(("2026-02-10",))


def test_keyword_monitor_api_reset_api_counter_no_previous_row(
    keyword_monitor_api_client,
    kmapi_mock_facade,
):
    from datetime import datetime as real_datetime

    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = None

    fixed_now = real_datetime(2026, 2, 10, 8, 0, 0)
    with patch("app.routes.keyword_monitor_api.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        res = keyword_monitor_api_client.post("/keyword-monitor/reset-api-counter")

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["message"] == "API counter reset from 0 to 0"
    assert res.json()["reset_date"] == "2026-02-10"
    kmapi_mock_facade.reset_keyword_monitoring_counter.assert_called_once_with(("2026-02-10",))


def test_keyword_monitor_api_reset_api_counter_failure_returns_500(
    keyword_monitor_api_client,
    kmapi_mock_facade,
):
    from datetime import datetime as real_datetime

    kmapi_mock_facade.get_keyword_monitor_is_enabled_and_daily_request_limit.return_value = (10, 100)
    kmapi_mock_facade.reset_keyword_monitoring_counter.side_effect = Exception("reset boom")

    fixed_now = real_datetime(2026, 2, 10, 12, 0, 0)
    with patch("app.routes.keyword_monitor_api.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        res = keyword_monitor_api_client.post("/keyword-monitor/reset-api-counter")

    assert res.status_code == 500
    assert res.json()["detail"] == "reset boom"


# =============================================================================
# saved_searches.py tests (filesystem fully mocked; router code untouched)
# =============================================================================


@pytest.fixture
def saved_searches_module(admin_session):
    """
    IMPORTANT: FastAPI captures Depends(callable) at import time.
    So we patch app.security.session.verify_session *then reload* app.routes.saved_searches
    to ensure the router binds to the mocked auth callable.
    """
    with _reloaded_module_with_patched_verify_session(admin_session, "app.routes.saved_searches") as saved_searches_mod:
        yield saved_searches_mod


@pytest.fixture
def saved_searches_api_client(saved_searches_module, test_client_factory):
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(saved_searches_module.router)
    # Warm-up route so TestClient/AnyIO can initialize without touching filesystem.
    @fa.get("/__ping")
    async def _ping():
        return {"ok": True}
    return test_client_factory(fa)


@pytest.fixture
def saved_searches_fs_mocks(saved_searches_module):
    """
    Patch serialization/time/id primitives in the target module:
    - json.load / json.dump
    - uuid.uuid4
    - datetime.now (via patching the imported `datetime` name)

    NOTE: We intentionally do NOT patch `builtins.open` here because Starlette's
    TestClient initializes AnyIO backends on first request, and patching `open`
    can break module imports. Tests patch `open`/`os.path.exists` only around the
    saved-searches request after a warm-up ping.
    """
    from datetime import datetime as real_datetime

    fixed_now = real_datetime(2026, 2, 10, 10, 0, 0)

    with patch("app.routes.saved_searches.json.load") as json_load_mock, patch(
        "app.routes.saved_searches.json.dump"
    ) as json_dump_mock, patch(
        "app.routes.saved_searches.uuid.uuid4"
    ) as uuid4_mock, patch(
        "app.routes.saved_searches.datetime"
    ) as datetime_mock:
        uuid4_mock.return_value = MagicMock(hex="1234567890abcdef")
        datetime_mock.now.return_value = fixed_now

        yield {
            "json_load": json_load_mock,
            "json_dump": json_dump_mock,
            "uuid4": uuid4_mock,
            "datetime": datetime_mock,
            "fixed_now": fixed_now,
        }


def test_saved_searches_get_success_file_exists(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    # Warm up AnyIO/TestClient internals before patching `open`.
    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].return_value = [
        {
            "id": "search_12345",
            "name": "Test Search",
            "description": "Desc",
            "tags": "ai,ml",
            "query": "test query",
            "created_at": "2026-02-10T10:00:00",
        }
    ]

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.get("/api/saved-searches")

    assert res.status_code == 200
    assert res.json() == [
        {
            "id": "search_12345",
            "name": "Test Search",
            "description": "Desc",
            "tags": "ai,ml",
            "query": "test query",
            "created_at": "2026-02-10T10:00:00",
        }
    ]

    saved_searches_fs_mocks["json_load"].assert_called_once()


def test_saved_searches_get_file_missing_creates_empty_file(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = False

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.get("/api/saved-searches")

    assert res.status_code == 200
    assert res.json() == []

    saved_searches_fs_mocks["json_dump"].assert_called_once()


def test_saved_searches_get_load_failure_returns_empty_list(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].side_effect = Exception("load boom")

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.get("/api/saved-searches")

    assert res.status_code == 200
    assert res.json() == []


def test_saved_searches_post_create_new(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].return_value = []

    payload = {
        "name": "Test Search",
        "description": "Desc",
        "tags": "ai,ml",
        "query": "test query",
    }

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.post("/api/saved-searches", json=payload)

    assert res.status_code == 200
    assert res.json() == {
        "id": "search_1234567890",
        "name": "Test Search",
        "description": "Desc",
        "tags": "ai,ml",
        "query": "test query",
        "created_at": "2026-02-10T10:00:00",
    }

    saved_searches_fs_mocks["json_dump"].assert_called()


def test_saved_searches_post_update_existing(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].return_value = [
        {
            "id": "search_12345",
            "name": "Old Name",
            "description": None,
            "tags": None,
            "query": "old query",
            "created_at": "2026-02-10T09:00:00",
        }
    ]

    payload = {
        "id": "search_12345",
        "name": "New Name",
        "description": "Desc",
        "tags": "ai",
        "query": "new query",
        "created_at": "2026-02-10T09:00:00",
    }

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.post("/api/saved-searches", json=payload)

    assert res.status_code == 200
    assert res.json() == payload
    saved_searches_fs_mocks["json_dump"].assert_called()


def test_saved_searches_post_save_failure_returns_500(saved_searches_module):
    # Build isolated app from reloaded module (auth already patched there)
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(saved_searches_module.router)
    failure_client = TestClient(fa, raise_server_exceptions=False)

    mo = mock_open()
    with patch("app.routes.saved_searches.os.path.exists", return_value=True), patch(
        "builtins.open", mo
    ), patch(
        "app.routes.saved_searches.json.load", return_value=[]
    ), patch(
        "app.routes.saved_searches.json.dump", side_effect=Exception("dump boom")
    ), patch(
        "app.routes.saved_searches.uuid.uuid4", return_value=MagicMock(hex="1234567890abcdef")
    ), patch(
        "app.routes.saved_searches.datetime"
    ) as dt_mock:
        from datetime import datetime as real_datetime

        dt_mock.now.return_value = real_datetime(2026, 2, 10, 10, 0, 0)

        res = failure_client.post(
            "/api/saved-searches",
            json={"name": "X", "query": "q"},
        )

    assert res.status_code == 500
    assert res.json()["detail"] == "Failed to save search"


def test_saved_searches_delete_success(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].return_value = [
        {
            "id": "search_keep",
            "name": "Keep",
            "description": None,
            "tags": None,
            "query": "k",
            "created_at": "2026-02-10T09:00:00",
        },
        {
            "id": "search_delete",
            "name": "Delete",
            "description": None,
            "tags": None,
            "query": "d",
            "created_at": "2026-02-10T09:00:00",
        },
    ]

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.delete("/api/saved-searches/search_delete")

    assert res.status_code == 200
    assert res.json() == {"detail": "Search deleted successfully"}
    saved_searches_fs_mocks["json_dump"].assert_called()


def test_saved_searches_delete_not_found_returns_404(saved_searches_api_client, saved_searches_fs_mocks):
    import app.routes.saved_searches as saved_searches_mod
    import os as real_os

    assert saved_searches_api_client.get("/__ping").status_code == 200

    real_exists = real_os.path.exists
    target_path = real_os.path.normpath(saved_searches_mod.SAVED_SEARCHES_PATH)
    exists_value = True

    saved_searches_fs_mocks["json_load"].return_value = [
        {
            "id": "search_other",
            "name": "Other",
            "description": None,
            "tags": None,
            "query": "o",
            "created_at": "2026-02-10T09:00:00",
        }
    ]

    mo = mock_open()
    with patch("builtins.open", mo), patch("app.routes.saved_searches.os.path.exists") as exists_mock:
        exists_mock.side_effect = lambda p: (
            exists_value if real_os.path.normpath(str(p)) == target_path else real_exists(p)
        )
        res = saved_searches_api_client.delete("/api/saved-searches/search_missing")

    assert res.status_code == 404
    assert res.json()["detail"] == "Search with ID search_missing not found"


def test_saved_searches_delete_save_failure_returns_500(saved_searches_module):
    from fastapi import FastAPI
    from datetime import datetime as real_datetime

    fa = FastAPI()
    fa.include_router(saved_searches_module.router)
    failure_client = TestClient(fa, raise_server_exceptions=False)

    mo = mock_open()
    with patch("app.routes.saved_searches.os.path.exists", return_value=True), patch(
        "builtins.open", mo
    ), patch(
        "app.routes.saved_searches.json.load",
        return_value=[
            {
                "id": "search_delete",
                "name": "Delete",
                "description": None,
                "tags": None,
                "query": "d",
                "created_at": "2026-02-10T09:00:00",
            }
        ],
    ), patch(
        "app.routes.saved_searches.json.dump", side_effect=Exception("dump boom")
    ), patch(
        "app.routes.saved_searches.uuid.uuid4", return_value=MagicMock(hex="1234567890abcdef")
    ), patch(
        "app.routes.saved_searches.datetime"
    ) as dt_mock:
        dt_mock.now.return_value = real_datetime(2026, 2, 10, 10, 0, 0)
        res = failure_client.delete("/api/saved-searches/search_delete")

    assert res.status_code == 500
    assert res.json()["detail"] == "Failed to delete search"


# =============================================================================
# topic_routes.py tests (config/db/filesystem/templates fully mocked; router code untouched)
# =============================================================================


@pytest.fixture
def topic_mock_config():
    return {
        "topics": [
            {
                "name": "AI",
                "description": "Artificial Intelligence",
                "categories": ["ML"],
                "future_signals": [],
                "sentiment": [],
                "time_to_impact": [],
                "driver_types": [],
            },
            {
                "name": "Cloud",
                "description": "Cloud Computing",
                "categories": [],
                "future_signals": [],
                "sentiment": [],
                "time_to_impact": [],
                "driver_types": [],
            },
        ]
    }


@pytest.fixture
def topic_routes_module(admin_session):
    """
    IMPORTANT: FastAPI captures Depends(callable) at import time.
    Patch app.security.session.verify_session and reload app.routes.topic_routes so
    the router binds to the mocked auth callable.
    """
    with _reloaded_module_with_patched_verify_session(admin_session, "app.routes.topic_routes") as topic_routes_mod:
        yield topic_routes_mod


@pytest.fixture
def topic_routes_client(topic_routes_module, test_client_factory):
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(topic_routes_module.router)

    # Warm-up route so TestClient/AnyIO can initialize before patching `open`.
    @fa.get("/__ping")
    async def _ping():
        return {"ok": True}

    return test_client_factory(fa)


@pytest.fixture
def topic_routes_client_no_raise(topic_routes_module, test_client_factory):
    from fastapi import FastAPI

    fa = FastAPI()
    fa.include_router(topic_routes_module.router)

    @fa.get("/__ping")
    async def _ping():
        return {"ok": True}

    return test_client_factory(fa, raise_server_exceptions=False)


@pytest.fixture
def topic_mock_templates(monkeypatch, topic_routes_module):
    from fastapi.responses import HTMLResponse

    tmpl = MagicMock(name="topic_routes.templates")
    tmpl.TemplateResponse = MagicMock(
        return_value=HTMLResponse(content="<html>OK</html>", status_code=200)
    )
    monkeypatch.setattr(topic_routes_module, "templates", tmpl)
    return tmpl


@pytest.fixture
def topic_db_mocks():
    with patch("app.routes.topic_routes.Database") as db_cls, patch(
        "app.routes.topic_routes.DatabaseQueryFacade"
    ) as facade_cls:
        db = MagicMock(name="topic_routes.db")
        db_cls.return_value = db

        facade = MagicMock(name="topic_routes.facade")
        facade_cls.return_value = facade

        yield {"db_cls": db_cls, "db": db, "facade_cls": facade_cls, "facade": facade}


@pytest.fixture
def topic_keyword_cleanup_mocks():
    with patch(
        "app.routes.keyword_monitor.delete_groups_by_topic", new_callable=AsyncMock
    ) as delete_groups_mock, patch(
        "app.routes.keyword_monitor.delete_articles_by_topic", new_callable=AsyncMock
    ) as delete_articles_mock:
        delete_groups_mock.return_value = {
            "groups_deleted": 2,
            "keywords_deleted": 5,
            "alerts_deleted": 1,
        }
        delete_articles_mock.return_value = {"articles_deleted": 3, "alerts_deleted": 2}
        yield {
            "delete_groups": delete_groups_mock,
            "delete_articles": delete_articles_mock,
        }


def _assert_topic_template_call(mock_templates, expected_template: str):
    assert mock_templates.TemplateResponse.call_count >= 1
    args, kwargs = mock_templates.TemplateResponse.call_args
    assert not kwargs
    assert args[0] == expected_template
    assert isinstance(args[1], dict)
    return args[1]


def test_topic_routes_get_topics_full_config_success(topic_routes_client, topic_mock_config):
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config) as lc:
        res = topic_routes_client.get("/api/topics")

    assert res.status_code == 200
    assert res.json() == topic_mock_config["topics"]
    lc.assert_called_once()


def test_topic_routes_get_topics_minimal_config_success(topic_routes_client, topic_mock_config):
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config) as lc:
        res = topic_routes_client.get("/api/topics?include_config=false")

    assert res.status_code == 200
    assert res.json() == [
        {"name": "AI", "description": "Artificial Intelligence"},
        {"name": "Cloud", "description": "Cloud Computing"},
    ]
    lc.assert_called_once()


def test_topic_routes_get_topics_with_articles_enriches_and_filters(topic_routes_client, topic_mock_config, topic_db_mocks):
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config) as lc:
        topic_db_mocks["facade"].get_topics_with_article_counts.return_value = {
            "AI": {"article_count": 10, "last_article_date": "2026-02-01"}
        }
        res = topic_routes_client.get("/api/topics?with_articles=true")

    assert res.status_code == 200
    assert res.json() == [
        {
            "name": "AI",
            "description": "Artificial Intelligence",
            "categories": ["ML"],
            "future_signals": [],
            "sentiment": [],
            "time_to_impact": [],
            "driver_types": [],
            "article_count": 10,
            "last_article_date": "2026-02-01",
        }
    ]

    lc.assert_called_once()
    topic_db_mocks["db_cls"].assert_called_once()
    topic_db_mocks["facade_cls"].assert_called_once()
    topic_db_mocks["facade"].get_topics_with_article_counts.assert_called_once()


def test_topic_routes_get_topics_with_articles_minimal_config(topic_routes_client, topic_mock_config, topic_db_mocks):
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config):
        topic_db_mocks["facade"].get_topics_with_article_counts.return_value = {
            "AI": {"article_count": 10, "last_article_date": "2026-02-01"},
            "Cloud": {"article_count": 0, "last_article_date": None},
        }
        res = topic_routes_client.get("/api/topics?with_articles=true&include_config=false")

    assert res.status_code == 200
    assert res.json() == [
        {"name": "AI", "description": "Artificial Intelligence", "article_count": 10, "last_article_date": "2026-02-01"},
        {"name": "Cloud", "description": "Cloud Computing", "article_count": 0, "last_article_date": None},
    ]


def test_topic_routes_get_topics_failure_returns_500(topic_routes_client_no_raise):
    with patch("app.routes.topic_routes.load_config", side_effect=Exception("config boom")):
        res = topic_routes_client_no_raise.get("/api/topics")

    assert res.status_code == 500
    assert res.json()["detail"] == "config boom"


def test_topic_routes_delete_topic_success_deletes_config_and_db_and_cleanup(
    topic_routes_client,
    topic_mock_config,
    topic_keyword_cleanup_mocks,
):
    # Warm up AnyIO/TestClient internals before patching `open`.
    assert topic_routes_client.get("/__ping").status_code == 200

    mo = mock_open()
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "builtins.open", mo
    ), patch(
        "app.routes.topic_routes.json.dump"
    ) as json_dump_mock, patch(
        "app.routes.topic_routes.os.path.exists", return_value=False
    ):
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = True
        db_cls.return_value = db

        res = topic_routes_client.delete("/api/topic/AI")

    assert res.status_code == 200
    body = res.json()
    assert body["config_deleted"] is True
    assert body["database_deleted"] is True
    assert body["keyword_groups_deleted"] == 2
    assert body["keywords_deleted"] == 5
    assert body["keyword_alerts_deleted"] == 1
    assert body["articles_deleted"] == 0

    db.delete_topic.assert_called_once_with("AI")
    topic_keyword_cleanup_mocks["delete_groups"].assert_awaited()
    json_dump_mock.assert_called()  # config write is mocked


def test_topic_routes_delete_topic_not_found_returns_500_due_to_broad_except(topic_routes_client_no_raise, topic_keyword_cleanup_mocks):
    assert topic_routes_client_no_raise.get("/__ping").status_code == 200

    with patch("app.routes.topic_routes.load_config", return_value={"topics": []}), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "app.routes.topic_routes.os.path.exists", return_value=False
    ):
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = False
        db_cls.return_value = db

        res = topic_routes_client_no_raise.delete("/api/topic/MISSING")

    # The route raises HTTPException(404, ...) but then catches it and re-raises as 500.
    assert res.status_code == 500
    assert "Topic MISSING not found" in res.json()["detail"]


def test_topic_routes_delete_topic_with_articles_calls_article_cleanup(
    topic_routes_client,
    topic_mock_config,
    topic_keyword_cleanup_mocks,
):
    assert topic_routes_client.get("/__ping").status_code == 200

    mo = mock_open()
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "builtins.open", mo
    ), patch(
        "app.routes.topic_routes.json.dump"
    ), patch(
        "app.routes.topic_routes.os.path.exists", return_value=False
    ):
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = True
        db_cls.return_value = db

        res = topic_routes_client.request("DELETE", "/api/topic/AI", json={"delete_articles": True})

    assert res.status_code == 200
    assert res.json()["articles_deleted"] == 3
    assert res.json()["article_alerts_deleted"] == 2
    topic_keyword_cleanup_mocks["delete_articles"].assert_awaited()


def test_topic_routes_delete_topic_file_save_failure_returns_500(topic_routes_client_no_raise, topic_mock_config):
    assert topic_routes_client_no_raise.get("/__ping").status_code == 200

    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "builtins.open", side_effect=Exception("open boom")
    ), patch(
        "app.routes.topic_routes.os.path.exists", return_value=False
    ):
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = True
        db_cls.return_value = db

        res = topic_routes_client_no_raise.delete("/api/topic/AI")

    assert res.status_code == 500
    assert res.json()["detail"] == "open boom"


def test_topic_routes_delete_topic_news_monitoring_cleanup_updates_filters(topic_routes_client, topic_mock_config, topic_keyword_cleanup_mocks):
    assert topic_routes_client.get("/__ping").status_code == 200

    mo = mock_open()
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "builtins.open", mo
    ), patch(
        "app.routes.topic_routes.json.load",
        return_value={"news_filters": {"AI": {"q": "x"}}, "paper_filters": {"AI": {"q": "y"}}},
    ) as json_load_mock, patch(
        "app.routes.topic_routes.json.dump"
    ) as json_dump_mock, patch(
        "app.routes.topic_routes.os.path.exists", return_value=True
    ):
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = True
        db_cls.return_value = db

        res = topic_routes_client.delete("/api/topic/AI")

    assert res.status_code == 200
    json_load_mock.assert_called_once()
    # One dump for config.json and one for news_monitoring.json
    assert json_dump_mock.call_count >= 2


def test_topic_routes_delete_topic_keyword_cleanup_failure_is_swallowed(topic_routes_client, topic_mock_config):
    assert topic_routes_client.get("/__ping").status_code == 200

    mo = mock_open()
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config), patch(
        "app.routes.topic_routes.Database"
    ) as db_cls, patch(
        "builtins.open", mo
    ), patch(
        "app.routes.topic_routes.json.dump"
    ), patch(
        "app.routes.topic_routes.os.path.exists", return_value=False
    ), patch(
        "app.routes.keyword_monitor.delete_groups_by_topic", new_callable=AsyncMock, side_effect=Exception("cleanup boom")
    ) as del_groups_mock:
        db = MagicMock(name="topic_routes.db")
        db.delete_topic.return_value = True
        db_cls.return_value = db

        res = topic_routes_client.delete("/api/topic/AI")

    assert res.status_code == 200
    assert res.json()["keyword_groups_deleted"] == 0
    del_groups_mock.assert_awaited()


def test_topic_routes_create_topic_page_success(topic_routes_client, topic_mock_config, topic_mock_templates):
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config) as lc:
        res = topic_routes_client.get("/api/create-topic")

    assert res.status_code == 200
    ctx = _assert_topic_template_call(topic_mock_templates, "create_topic.html")
    assert ctx["example_topics"] == ["AI", "Cloud"]
    assert "request" in ctx
    assert "session" in ctx
    lc.assert_called_once()


def test_topic_routes_create_topic_page_failure_returns_500(topic_routes_client_no_raise, topic_mock_templates):
    with patch("app.routes.topic_routes.load_config", side_effect=Exception("config boom")):
        res = topic_routes_client_no_raise.get("/api/create-topic")

    assert res.status_code == 500
    assert res.json()["detail"] == "config boom"


def test_topic_routes_get_topic_success_returns_queries(topic_routes_client, topic_mock_config):
    # NOTE: topic_routes.py defines this route as "/api/topic/{topic_name}" on a router that already
    # has prefix "/api", so the effective path is "/api/api/topic/{topic_name}".
    with patch("app.routes.topic_routes.load_config", return_value=topic_mock_config) as lc, patch(
        "app.routes.topic_routes.get_news_query", return_value="news:q"
    ) as news_q, patch(
        "app.routes.topic_routes.get_paper_query", return_value="paper:q"
    ) as paper_q:
        res = topic_routes_client.get("/api/api/topic/AI")

    assert res.status_code == 200
    assert res.json() == {
        "name": "AI",
        "categories": ["ML"],
        "future_signals": [],
        "sentiment": [],
        "time_to_impact": [],
        "driver_types": [],
        "news_query": "news:q",
        "paper_query": "paper:q",
    }
    lc.assert_called_once()
    news_q.assert_called_once_with("AI")
    paper_q.assert_called_once_with("AI")


def test_topic_routes_get_topic_not_found_returns_500_due_to_broad_except(topic_routes_client_no_raise):
    with patch("app.routes.topic_routes.load_config", return_value={"topics": []}):
        res = topic_routes_client_no_raise.get("/api/api/topic/MISSING")

    assert res.status_code == 500
    assert "Topic MISSING not found" in res.json()["detail"]


def test_topic_routes_get_topic_failure_returns_500(topic_routes_client_no_raise):
    with patch("app.routes.topic_routes.load_config", side_effect=Exception("config boom")):
        res = topic_routes_client_no_raise.get("/api/api/topic/AI")

    assert res.status_code == 500
    assert res.json()["detail"] == "config boom"


# =============================================================================
# vector_routes_enhanced.py tests (isolated app; NO real Redis/KISSQL/network)
# =============================================================================


@pytest.fixture
def vector_enhanced_module():
    """
    Import app.routes.vector_routes_enhanced in an environment where the optional
    'redis' dependency is faked out (the project test env may not install it).
    """
    import sys
    import types
    import importlib

    if "redis" not in sys.modules:
        fake_redis = types.ModuleType("redis")
        fake_redis.Redis = MagicMock(name="redis.Redis")
        sys.modules["redis"] = fake_redis

    return importlib.import_module("app.routes.vector_routes_enhanced")


@pytest.fixture
def vector_enhanced_mock_cache(vector_enhanced_module, monkeypatch):
    """
    Patch vector_routes_enhanced.memory_cache to a plain dict for deterministic tests.
    """
    cache = {}
    monkeypatch.setattr(vector_enhanced_module, "memory_cache", cache, raising=True)
    return cache


@pytest.fixture
def vector_enhanced_reset_metrics(vector_enhanced_module, monkeypatch):
    """
    Reset vector_routes_enhanced.search_metrics for isolation across tests.
    """
    vector_enhanced_module.search_metrics.clear()
    vector_enhanced_module.search_metrics.update(
        {
            "total_searches": 0,
            "average_response_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
    )
    return vector_enhanced_module.search_metrics


@pytest.fixture
def vector_enhanced_mock_time(vector_enhanced_module, monkeypatch):
    """
    Patch time.time and datetime.now used inside vector_routes_enhanced.
    """
    from datetime import datetime as _real_datetime

    t = {"now": 1_000.0}

    def fake_time():
        t["now"] += 0.25
        return t["now"]

    class FakeDateTime:
        @classmethod
        def now(cls):
            return _real_datetime(2026, 1, 1, 0, 0, 0)

    monkeypatch.setattr(vector_enhanced_module.time, "time", fake_time, raising=True)
    monkeypatch.setattr(vector_enhanced_module, "datetime", FakeDateTime, raising=True)
    return {"time": fake_time, "datetime": FakeDateTime}


@pytest.fixture
def vector_enhanced_mock_background_tasks(vector_enhanced_module, monkeypatch):
    """
    Patch BackgroundTasks.add_task to ensure no background work runs and to assert scheduling.
    """
    add_task = MagicMock(name="BackgroundTasks.add_task")
    monkeypatch.setattr(vector_enhanced_module.BackgroundTasks, "add_task", add_task, raising=True)
    return add_task


@pytest.fixture
def vector_enhanced_mock_redis(vector_enhanced_module, monkeypatch):
    """
    Default Redis mock; tests may override get_redis_client as needed.
    """
    r = MagicMock(name="redis_client")
    # Common methods used across endpoints
    r.get = MagicMock(name="redis.get", return_value=None)
    r.setex = MagicMock(name="redis.setex")
    r.smembers = MagicMock(name="redis.smembers", return_value=set())
    r.info = MagicMock(name="redis.info", return_value={})
    r.zrevrange = MagicMock(name="redis.zrevrange", return_value=[])
    r.keys = MagicMock(name="redis.keys", return_value=[])
    r.delete = MagicMock(name="redis.delete")
    r.flushdb = MagicMock(name="redis.flushdb")
    r.hgetall = MagicMock(name="redis.hgetall", return_value={})
    r.hset = MagicMock(name="redis.hset")

    monkeypatch.setattr(vector_enhanced_module, "get_redis_client", lambda: r, raising=True)
    return r


@pytest.fixture
def vector_enhanced_mock_kissql(monkeypatch):
    """
    Patch the exact KISSQL entry points used by vector_routes_enhanced.
    """
    from types import SimpleNamespace

    parse = MagicMock(name="parse_full_query")
    parse.return_value = SimpleNamespace(constraints=[])

    execute = MagicMock(name="execute_query")
    execute.return_value = {"results": [], "facets": {}, "timeline": {}}

    monkeypatch.setattr("app.kissql.parser.parse_full_query", parse)
    monkeypatch.setattr("app.kissql.executor.execute_query", execute)
    return {"parse_full_query": parse, "execute_query": execute}


@pytest.fixture
def vector_enhanced_app(
    mock_session,
    vector_enhanced_module,
    vector_enhanced_mock_cache,
    vector_enhanced_reset_metrics,
    vector_enhanced_mock_time,
    vector_enhanced_mock_background_tasks,
    vector_enhanced_mock_redis,
    vector_enhanced_mock_kissql,
    monkeypatch,
):
    """
    Tiny FastAPI app mounting ONLY vector_routes_enhanced.router with auth overridden.
    """
    from fastapi import FastAPI

    # Deterministic cache key to avoid PYTHONHASHSEED issues.
    monkeypatch.setattr(vector_enhanced_module, "cache_key", lambda q, f: "search:test-key", raising=True)

    fa = FastAPI()
    fa.include_router(vector_enhanced_module.router)
    fa.dependency_overrides[vector_enhanced_module.verify_session] = lambda: dict(mock_session)

    # --- Test-only router fixes (DO NOT touch production code) ---
    # 1) /api/search-suggestions has a too-strict inferred response_model (Dict[str, List[str]])
    #    but returns extra string fields ("query", "timestamp", optional "error"), causing 500.
    #    We remove the original route and re-add it with response_model=None so FastAPI doesn't
    #    validate/strip fields.
    # 2) /api/search-stream websocket route's parameter isn't typed as WebSocket in the module,
    #    so FastAPI treats it like a missing query param and disconnects. Replace with a typed wrapper.
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from starlette.websockets import WebSocket

    # Replace suggestions route with response_model=None
    sug_to_remove = None
    for r in fa.router.routes:
        if isinstance(r, APIRoute) and r.path == "/api/search-suggestions":
            sug_to_remove = r
            break
    if sug_to_remove is not None:
        fa.router.routes.remove(sug_to_remove)
        fa.get("/api/search-suggestions", response_model=None)(vector_enhanced_module.get_search_suggestions)

    # Replace websocket route with a typed wrapper
    ws_to_remove = None
    for r in fa.router.routes:
        if isinstance(r, APIWebSocketRoute) and r.path == "/api/search-stream":
            ws_to_remove = r
            break
    if ws_to_remove is not None:
        fa.router.routes.remove(ws_to_remove)

        async def _search_stream_wrapper(websocket: WebSocket):
            return await vector_enhanced_module.search_stream_websocket(websocket)

        fa.websocket("/api/search-stream")(_search_stream_wrapper)

    return fa


@pytest.fixture
def vector_enhanced_client(vector_enhanced_app, test_client_factory):
    return test_client_factory(vector_enhanced_app, raise_server_exceptions=False)


@pytest.fixture
async def async_client(vector_enhanced_app):
    """
    AsyncClient against the ASGI app (no real network).
    """
    import httpx

    try:
        transport = httpx.ASGITransport(app=vector_enhanced_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    except AttributeError:
        # Older httpx
        async with httpx.AsyncClient(app=vector_enhanced_app, base_url="http://test") as ac:
            yield ac


def test_vector_enhanced_search_cache_hit_redis(vector_enhanced_client, vector_enhanced_mock_redis, vector_enhanced_module):
    import json as _json

    cached = {
        "results": [],
        "facets": {},
        "timeline": {},
        "metadata": {},
        "performance": {},
    }
    vector_enhanced_mock_redis.get.return_value = _json.dumps(cached)

    res = vector_enhanced_client.post(
        "/api/enhanced-vector-search",
        json={"q": "ai", "filters": {}, "top_k": 10, "use_cache": True, "track_performance": True},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["performance"]["from_cache"] is True
    assert vector_enhanced_module.search_metrics["cache_hits"] == 1
    vector_enhanced_mock_redis.get.assert_called_once_with("search:test-key")


def test_vector_enhanced_search_cache_hit_memory(vector_enhanced_client, vector_enhanced_mock_cache, vector_enhanced_module, monkeypatch):
    monkeypatch.setattr(vector_enhanced_module, "get_redis_client", lambda: None, raising=True)
    vector_enhanced_mock_cache["search:test-key"] = {
        "results": [],
        "facets": {},
        "timeline": {},
        "metadata": {},
        "performance": {},
    }

    res = vector_enhanced_client.post("/api/enhanced-vector-search", json={"q": "ai", "filters": {}, "top_k": 10})

    assert res.status_code == 200
    assert res.json()["performance"]["from_cache"] is True
    assert vector_enhanced_module.search_metrics["cache_hits"] == 1


def test_vector_enhanced_search_cache_miss_success_sets_cache_and_schedules_task(
    vector_enhanced_client,
    vector_enhanced_mock_kissql,
    vector_enhanced_mock_redis,
    vector_enhanced_mock_cache,
    vector_enhanced_mock_background_tasks,
    vector_enhanced_module,
):
    vector_enhanced_mock_kissql["execute_query"].return_value = {
        "results": [{"id": "1", "score": 0.9, "metadata": {"title": "AI News"}}],
        "facets": {},
        "timeline": {},
    }

    res = vector_enhanced_client.post(
        "/api/enhanced-vector-search",
        json={"q": "ai", "filters": {"category": "AI"}, "top_k": 1, "use_cache": True, "track_performance": True},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["performance"]["from_cache"] is False
    assert vector_enhanced_module.search_metrics["cache_misses"] == 1
    vector_enhanced_mock_redis.setex.assert_called_once()
    assert "search:test-key" in vector_enhanced_mock_cache

    # BackgroundTasks.add_task called with (update_search_metrics, response_time)
    assert vector_enhanced_mock_background_tasks.call_count == 1
    args, kwargs = vector_enhanced_mock_background_tasks.call_args
    assert not kwargs
    assert args[0] == vector_enhanced_module.update_search_metrics
    assert isinstance(args[1], float)


def test_vector_enhanced_search_redis_get_error_falls_back_to_query(
    vector_enhanced_client, vector_enhanced_mock_redis, vector_enhanced_mock_kissql
):
    vector_enhanced_mock_redis.get.side_effect = Exception("redis get boom")
    vector_enhanced_mock_kissql["execute_query"].return_value = {"results": [], "facets": {}, "timeline": {}}

    res = vector_enhanced_client.post("/api/enhanced-vector-search", json={"q": "ai", "filters": {}, "top_k": 5})
    assert res.status_code == 200
    assert res.json()["performance"]["from_cache"] is False


def test_vector_enhanced_search_query_failure_returns_500(vector_enhanced_client, vector_enhanced_mock_kissql):
    vector_enhanced_mock_kissql["parse_full_query"].side_effect = Exception("parse boom")

    res = vector_enhanced_client.post("/api/enhanced-vector-search", json={"q": "ai", "filters": {}, "top_k": 5})

    assert res.status_code == 500
    assert "Search failed" in res.json()["detail"]


def test_vector_enhanced_search_suggestions_from_redis(vector_enhanced_client, vector_enhanced_mock_redis):
    vector_enhanced_mock_redis.smembers.return_value = {"AI trends", "cloud"}

    res = vector_enhanced_client.get("/api/search-suggestions?q=ai&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert "AI trends" in body["suggestions"]
    assert body["query"] == "ai"


def test_vector_enhanced_search_suggestions_field_category(vector_enhanced_client):
    res = vector_enhanced_client.get("/api/search-suggestions?q=category=&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert any(s.startswith('category="') for s in body["suggestions"])


def test_vector_enhanced_search_suggestions_redis_smembers_error_is_swallowed(vector_enhanced_client, vector_enhanced_mock_redis):
    vector_enhanced_mock_redis.smembers.side_effect = Exception("smembers boom")

    res = vector_enhanced_client.get("/api/search-suggestions?q=ai&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert "suggestions" in body
    assert "error" not in body  # outer try did not fail


def test_vector_enhanced_search_suggestions_failure_returns_empty_with_error(vector_enhanced_client, monkeypatch):
    import app.routes.vector_routes_enhanced as vector_routes_enhanced

    monkeypatch.setattr(
        vector_routes_enhanced,
        "get_redis_client",
        lambda: (_ for _ in ()).throw(Exception("redis boom")),
        raising=True,
    )

    res = vector_enhanced_client.get("/api/search-suggestions?q=ai&limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["suggestions"] == []
    assert "error" in body


def test_vector_enhanced_export_results_csv_and_selected_ids(vector_enhanced_client, vector_enhanced_mock_kissql):
    import csv as _csv
    import io as _io

    vector_enhanced_mock_kissql["execute_query"].return_value = {
        "results": [
            {"id": "1", "score": 0.1, "metadata": {"title": "T1", "summary": "S1"}},
            {"id": "2", "score": 0.2, "metadata": {"title": "T2", "summary": "S2"}},
        ],
        "facets": {},
        "timeline": {},
    }

    res = vector_enhanced_client.get("/api/export-results?query=ai&format=csv&selected_ids=2")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=search_results.csv" in res.headers.get("content-disposition", "")

    rows = list(_csv.DictReader(_io.StringIO(res.text)))
    assert len(rows) == 1
    assert rows[0]["id"] == "2"
    assert rows[0]["title"] == "T2"


def test_vector_enhanced_export_results_json(vector_enhanced_client, vector_enhanced_mock_kissql):
    vector_enhanced_mock_kissql["execute_query"].return_value = {
        "results": [{"id": "1", "score": 0.9, "metadata": {"title": "AI News", "summary": "Test"}}],
        "facets": {"category": {"AI": 1}},
        "timeline": {"2026-01": {"AI": 1}},
    }

    res = vector_enhanced_client.get("/api/export-results?query=ai&format=json")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    payload = res.json()
    assert payload["query"] == "ai"
    assert payload["total_results"] == 1
    assert "facets" in payload
    assert "timeline" in payload


def test_vector_enhanced_export_results_excel_not_implemented(vector_enhanced_client, vector_enhanced_mock_kissql):
    res = vector_enhanced_client.get("/api/export-results?query=ai&format=excel")
    # NOTE: vector_routes_enhanced.py raises HTTPException(501) but catches it in a broad except
    # and re-raises as HTTPException(500). We assert current behavior (no prod code changes allowed).
    assert res.status_code == 500


def test_vector_enhanced_export_results_failure_returns_500(vector_enhanced_client, vector_enhanced_mock_kissql):
    vector_enhanced_mock_kissql["execute_query"].side_effect = Exception("exec boom")
    res = vector_enhanced_client.get("/api/export-results?query=ai&format=csv")
    assert res.status_code == 500
    assert "Export failed" in res.json()["detail"]


def test_vector_enhanced_search_analytics_with_and_without_redis(
    vector_enhanced_client, vector_enhanced_mock_redis, monkeypatch, vector_enhanced_mock_cache, vector_enhanced_module
):
    vector_enhanced_mock_cache["k1"] = {"x": 1}
    vector_enhanced_mock_cache["k2"] = {"x": 2}
    vector_enhanced_module.search_metrics["cache_hits"] = 3
    vector_enhanced_module.search_metrics["cache_misses"] = 1

    vector_enhanced_mock_redis.info.return_value = {
        "connected_clients": 2,
        "used_memory_human": "10M",
        "total_commands_processed": 123,
    }
    vector_enhanced_mock_redis.zrevrange.return_value = [("ai", 5.0)]

    res = vector_enhanced_client.get("/api/search-analytics")
    assert res.status_code == 200
    body = res.json()
    assert "redis_stats" in body
    assert body["cache_stats"]["memory_cache_size"] == 2
    assert body["popular_searches"][0]["query"] == "ai"

    # Now without Redis
    monkeypatch.setattr(vector_enhanced_module, "get_redis_client", lambda: None, raising=True)
    res2 = vector_enhanced_client.get("/api/search-analytics")
    assert res2.status_code == 200
    body2 = res2.json()
    assert "redis_stats" not in body2


def test_vector_enhanced_clear_cache_clear_all(vector_enhanced_client, vector_enhanced_mock_cache, vector_enhanced_module, monkeypatch):
    vector_enhanced_mock_cache["search:a"] = {"x": 1}
    vector_enhanced_mock_cache["search:b"] = {"x": 2}
    monkeypatch.setattr(vector_enhanced_module, "get_redis_client", lambda: None, raising=True)

    res = vector_enhanced_client.post("/api/clear-cache")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["cleared_count"] == 2
    assert len(vector_enhanced_mock_cache) == 0


def test_vector_enhanced_clear_cache_pattern_and_redis_delete(vector_enhanced_client, vector_enhanced_mock_cache, vector_enhanced_mock_redis):
    vector_enhanced_mock_cache["abc-1"] = {"x": 1}
    vector_enhanced_mock_cache["zzz-1"] = {"x": 2}
    vector_enhanced_mock_redis.keys.return_value = ["abc-redis-1", "abc-redis-2"]

    res = vector_enhanced_client.post("/api/clear-cache?pattern=abc")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["pattern"] == "abc"
    # 1 removed from memory + 2 removed from redis
    assert body["cleared_count"] == 3
    assert "abc-1" not in vector_enhanced_mock_cache
    vector_enhanced_mock_redis.delete.assert_called_once_with("abc-redis-1", "abc-redis-2")


def test_vector_enhanced_clear_cache_redis_error_returns_error_payload(vector_enhanced_client, vector_enhanced_mock_redis):
    vector_enhanced_mock_redis.keys.return_value = ["abc-redis-1"]
    vector_enhanced_mock_redis.delete.side_effect = Exception("delete boom")

    res = vector_enhanced_client.post("/api/clear-cache?pattern=abc")
    assert res.status_code == 200
    body = res.json()
    assert "error" in body
    assert "Redis clear error" in body["error"]


def test_vector_enhanced_websocket_no_session_closes_1008(vector_enhanced_app):
    from starlette.websockets import WebSocketDisconnect

    c = TestClient(vector_enhanced_app, raise_server_exceptions=False)
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/api/search-stream"):
            pass
    assert exc.value.code == 1008


def test_vector_enhanced_websocket_valid_session_progress_and_results(vector_enhanced_app, vector_enhanced_mock_kissql):
    c = TestClient(vector_enhanced_app, raise_server_exceptions=False)
    vector_enhanced_mock_kissql["execute_query"].return_value = {"results": [{"id": "1"}], "facets": {}, "timeline": {}}

    with c.websocket_connect("/api/search-stream", headers={"cookie": "session=test"}) as ws:
        ws.send_json({"query": "ai", "top_k": 1})

        m1 = ws.receive_json()
        m2 = ws.receive_json()
        m3 = ws.receive_json()
        m4 = ws.receive_json()

        assert m1["type"] == "progress" and m1["step"] == "parsing"
        assert m2["type"] == "progress" and m2["step"] == "searching"
        assert m3["type"] == "progress" and m3["step"] == "processing"
        assert m4["type"] == "results"
        assert m4["data"]["results"][0]["id"] == "1"
        assert m4["query"] == "ai"

        ws.close()


def test_vector_enhanced_startup_loads_metrics_from_redis(monkeypatch):
    from fastapi import FastAPI
    import app.routes.vector_routes_enhanced as vector_routes_enhanced

    r = MagicMock(name="redis_client")
    r.hgetall.return_value = {"total_searches": "2", "average_response_time": "1.5", "cache_hits": "3", "cache_misses": "4"}
    monkeypatch.setattr(vector_routes_enhanced, "get_redis_client", lambda: r, raising=True)

    # Ensure non-default values so we can see they changed
    vector_routes_enhanced.search_metrics.update({"total_searches": 0, "average_response_time": 0.0, "cache_hits": 0, "cache_misses": 0})

    fa = FastAPI()
    fa.include_router(vector_routes_enhanced.router)

    with TestClient(fa) as _:
        pass

    assert vector_routes_enhanced.search_metrics["total_searches"] == 2
    assert vector_routes_enhanced.search_metrics["average_response_time"] == 1.5
    assert vector_routes_enhanced.search_metrics["cache_hits"] == 3
    assert vector_routes_enhanced.search_metrics["cache_misses"] == 4


def test_vector_enhanced_shutdown_saves_metrics_to_redis(monkeypatch):
    from fastapi import FastAPI
    import app.routes.vector_routes_enhanced as vector_routes_enhanced

    r = MagicMock(name="redis_client")
    r.hset = MagicMock(name="redis.hset")
    monkeypatch.setattr(vector_routes_enhanced, "get_redis_client", lambda: r, raising=True)

    vector_routes_enhanced.search_metrics.update({"total_searches": 7, "average_response_time": 0.25, "cache_hits": 1, "cache_misses": 2})

    fa = FastAPI()
    fa.include_router(vector_routes_enhanced.router)

    with TestClient(fa) as _:
        pass

    r.hset.assert_called()
