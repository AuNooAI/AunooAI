"""Work package 14: /api/health/collection on the monolith.

The database and the three summary sources are stubbed at the module seams,
so this runs without a tenant database and without the shared ledger file.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("NORN_SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-not-for-prod")

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.routes import health_routes  # noqa: E402

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
INTERVALS = {"rss": 60}


def _iso(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


def _runs():
    return {
        "providers": [
            # rss: last success 3 hours ago, interval 60 min -> overdue
            {"provider": "rss", "last_success_at": _iso(timedelta(hours=3)),
             "last_run_at": _iso(timedelta(minutes=10)), "failed": 4, "partial": 0,
             "quota_exhausted": 0, "empty_success": 0},
            # newsdata: runs keep succeeding with zero items -> quiet, not broken
            {"provider": "newsdata", "last_success_at": _iso(timedelta(minutes=30)),
             "last_run_at": _iso(timedelta(minutes=30)), "failed": 0, "partial": 0,
             "quota_exhausted": 0, "empty_success": 12},
            # arxiv: 12h interval, success 20h ago -> within 2 intervals
            {"provider": "arxiv", "last_success_at": _iso(timedelta(hours=20)),
             "last_run_at": _iso(timedelta(hours=1)), "failed": 1, "partial": 0,
             "quota_exhausted": 0, "empty_success": 0},
        ],
        "errors": [{"provider": "rss", "error_code": "timeout", "count": 4}],
        "pending_intervals": [
            {"provider": "newsapi", "scope_key": "kw:7", "interval_start": None,
             "interval_end": None, "coverage_through": None, "consecutive_failures": 0,
             "last_error_code": None, "updated_at": _iso(timedelta(hours=30))},
            {"provider": "newsapi", "scope_key": "kw:8", "interval_start": None,
             "interval_end": None, "coverage_through": None, "consecutive_failures": 0,
             "last_error_code": None, "updated_at": _iso(timedelta(hours=2))},
        ],
    }


def _feeds():
    return [
        {"id": 3, "name": "Old feed", "polling_status": "error",
         "consecutive_error_count": 40, "first_failed_at": _iso(timedelta(hours=50)),
         "last_failed_at": _iso(timedelta(minutes=5)), "last_error": "HTTP 500",
         "parse_partial_count": 0, "needs_attention_reason": None,
         "last_success_at": _iso(timedelta(hours=51)), "last_attempt_at": _iso(timedelta(minutes=5))},
        {"id": 4, "name": "New failure", "polling_status": "error",
         "consecutive_error_count": 2, "first_failed_at": _iso(timedelta(hours=2)),
         "last_failed_at": _iso(timedelta(minutes=5)), "last_error": "timeout",
         "parse_partial_count": 0, "needs_attention_reason": None,
         "last_success_at": _iso(timedelta(hours=3)), "last_attempt_at": _iso(timedelta(minutes=5))},
    ]


def test_alert_builder_overdue_and_quiet_providers():
    alerts = health_routes.build_collection_alerts(
        _runs(), _feeds(), [{"topic": "AI", "count": 5}], now=NOW, intervals=INTERVALS,
    )
    assert "no successful run for rss in 3h" in alerts
    assert not any("newsdata" in a for a in alerts)
    assert not any("arxiv" in a for a in alerts)
    assert any(a.startswith("pending continuation for newsapi kw:7") for a in alerts)
    assert not any("kw:8" in a for a in alerts)
    assert "feed 3 failing for >24h" in alerts
    assert not any("feed 4" in a for a in alerts)
    assert "5 configuration-blocked articles in topic AI" in alerts


def test_alert_builder_never_succeeded_provider():
    runs = {"providers": [{"provider": "xpoz", "last_success_at": None,
                           "last_run_at": _iso(timedelta(hours=40))}],
            "pending_intervals": []}
    alerts = health_routes.build_collection_alerts(runs, [], [], now=NOW, intervals=INTERVALS)
    assert alerts == ["no successful run for xpoz in 40h (never succeeded)"]


def test_expected_intervals_env_override(monkeypatch):
    monkeypatch.setenv("COLLECTION_EXPECTED_INTERVALS", '{"rss": 15, "newsapi": 360}')
    intervals = health_routes.expected_intervals()
    assert intervals["rss"] == 15 and intervals["newsapi"] == 360
    monkeypatch.setenv("COLLECTION_EXPECTED_INTERVALS", "not json")
    assert health_routes.expected_intervals()["rss"] == 60


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(health_routes, "_collection_db", lambda: object())
    monkeypatch.setattr(health_routes, "_runs_summary", lambda db: _runs())
    monkeypatch.setattr(health_routes, "_quota_status",
                        lambda: {"providers": [{"provider": "newsapi", "used": 3, "budget": 100}], "hosts": []})
    monkeypatch.setattr(health_routes, "_rejected_stats", lambda db: {"entries": 10, "hits": 2})
    monkeypatch.setattr(health_routes, "_feed_health_rows", lambda db: _feeds())
    monkeypatch.setattr(
        health_routes, "_count_by_topic",
        lambda db, status: [{"topic": "AI", "count": 5}] if status == "quarantined_config"
        else [{"topic": "AI", "count": 1}],
    )
    monkeypatch.setattr(health_routes, "expected_intervals", lambda: INTERVALS)
    app = FastAPI()
    app.include_router(health_routes.router)
    return TestClient(app)


def test_endpoint_shape_and_alerts(client):
    resp = client.get("/api/health/collection")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("runs", "quota", "rejected_candidates", "feeds",
                "configuration_blocked", "enrichment_failed", "alerts"):
        assert key in body
    assert body["rejected_candidates"] == {"entries": 10, "hits": 2}
    assert body["configuration_blocked"] == [{"topic": "AI", "count": 5}]
    assert body["enrichment_failed"] == [{"topic": "AI", "count": 1}]
    assert [f["id"] for f in body["feeds"]] == [3, 4]
    assert "url" not in body["feeds"][0]
    # The stubbed timestamps are fixed, so the overdue rss provider is far
    # past two intervals by the time the test runs; the quiet one is not
    # unless the clock has moved on by more than two hours since NOW.
    assert any(a.startswith("no successful run for rss") for a in body["alerts"])
    assert "5 configuration-blocked articles in topic AI" in body["alerts"]
    assert "feed 3 failing for >24h" in body["alerts"]
    assert "errors" not in body


def test_endpoint_survives_a_broken_section(client, monkeypatch):
    def boom(db):
        raise RuntimeError("ledger table missing")
    monkeypatch.setattr(health_routes, "_rejected_stats", boom)
    resp = client.get("/api/health/collection")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rejected_candidates"] is None
    assert "ledger table missing" in body["errors"]["rejected_candidates"]
    assert "alerts" in body
