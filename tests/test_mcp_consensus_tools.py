"""get_consensus on the monolith MCP server: reads the newest saved run that
carries consensus categories, skipping later runs of other tabs, and renames
the numbered category keys. The database is stubbed."""

import asyncio
import json
from datetime import datetime

import pytest


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "GROUP BY topic" in sql:
            return _Rows([("EV", datetime(2026, 10, 2))])
        if "LOWER(topic)" in sql:
            return _Rows([r for r in self.rows if r[0].lower() == params["t"].lower()])
        return _Rows([r for r in self.rows if r[0] == params["t"]])

    def close(self):
        pass


@pytest.fixture
def consensus(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import consensus_tools
    return consensus_tools


def _payload(**extra):
    return json.dumps({"topic": "EV", "generated_at": datetime.now().isoformat(), **extra})


def test_skips_later_run_of_another_tab(consensus, monkeypatch):
    rows = [
        ("EV", _payload(scenarios=[{"x": 1}], categories=[]), datetime(2026, 10, 3)),
        ("EV", _payload(categories=[{"category_name": "LFP", "1_consensus_type": {"summary": "s"}}],
                        article_list=[{"id": 1}]), datetime(2026, 10, 2)),
    ]
    monkeypatch.setattr(consensus, "_conn", lambda: _Conn(rows))
    out = asyncio.run(consensus.get_consensus(topic="ev"))
    assert out["has_consensus"] is True
    assert out["topic"] == "EV"
    assert out["categories"] == [{"name": "LFP", "consensus_type": {"summary": "s"}}]
    assert out["article_list"] == [{"id": 1}]
    assert "stale" not in out


def test_no_saved_run_lists_topics(consensus, monkeypatch):
    monkeypatch.setattr(consensus, "_conn", lambda: _Conn([]))
    out = asyncio.run(consensus.get_consensus(topic="Nothing"))
    assert out["has_consensus"] is False
    assert out["topics_with_consensus"][0]["topic"] == "EV"


def test_registered(consensus):
    from app.mcp_access import tools
    assert "get_consensus" in [t.name for t in tools.available_tools()]
