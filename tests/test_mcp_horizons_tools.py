"""get_horizons and render_horizons_chart on the monolith MCP server: read the
newest saved run whose scenarios are horizon scenarios, skipping later runs of
other tabs, parse each scenario's years, and draw the S-curve SVG. The
database is stubbed."""

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

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
        if "LIKE" in sql:
            return _Rows(self.rows)
        if "LOWER(topic)" in sql:
            return _Rows([r for r in self.rows if r[0].lower() == params["t"].lower()])
        return _Rows([r for r in self.rows if r[0] == params["t"]])

    def close(self):
        pass


@pytest.fixture
def horizons(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import horizons_tools
    return horizons_tools


def _payload(generated=None, **extra):
    return json.dumps({"topic": "EV", "generated_at": (generated or datetime.now()).isoformat(), **extra})


_SCENARIOS = [
    {"type": "h1", "title": "LFP dominates", "timeframe": "2026-2032", "sentiment": "Trend"},
    {"type": "h3", "title": "Solid state", "timeframe": "2031 to 2040", "sentiment": "Disruption"},
    {"type": "other", "title": "dropped"},
]


def test_skips_later_run_of_another_tab(horizons, monkeypatch):
    rows = [
        # A consensus run: no scenarios key, but a disruption_scenarios one.
        ("EV", _payload(categories=[{"category_name": "x"}], disruption_scenarios=[{"type": "h1"}]),
         datetime(2026, 10, 3)),
        ("EV", _payload(scenarios=_SCENARIOS), datetime(2026, 10, 2)),
    ]
    monkeypatch.setattr(horizons, "_conn", lambda: _Conn(rows))
    out = asyncio.run(horizons.get_horizons(topic="ev"))
    assert out["has_horizons"] is True and out["topic"] == "EV"
    assert out["counts"] == {"h1": 1, "h2": 0, "h3": 1}
    first, last = out["scenarios"]
    assert (first["timeline_start"], first["timeline_end"], first["horizon"]) == (2026, 2032, "Current")
    assert (last["timeline_start"], last["timeline_end"]) == (2031, 2040)
    assert "display" in out and "stale" not in out


def test_old_run_is_flagged_stale(horizons, monkeypatch):
    old = datetime.now() - timedelta(days=40)
    monkeypatch.setattr(horizons, "_conn", lambda: _Conn([("EV", _payload(old, scenarios=_SCENARIOS), old)]))
    out = asyncio.run(horizons.get_horizons(topic="EV"))
    assert out["age_days"] == 40 and "stale" in out


def test_no_saved_run_lists_topics(horizons, monkeypatch):
    rows = [("EV", _payload(scenarios=_SCENARIOS), datetime(2026, 10, 2)),
            ("Other", _payload(disruption_scenarios=[{"type": "h1"}]), datetime(2026, 10, 1))]
    monkeypatch.setattr(horizons, "_conn", lambda: _Conn(rows))
    out = asyncio.run(horizons.get_horizons(topic="Nothing"))
    assert out["has_horizons"] is False
    assert [t["topic"] for t in out["topics_with_horizons"]] == ["EV"]


def test_chart_plots_every_scenario(horizons, monkeypatch):
    monkeypatch.setattr(horizons, "_conn", lambda: _Conn([("EV", _payload(scenarios=_SCENARIOS), datetime(2026, 10, 2))]))
    out = asyncio.run(horizons.render_horizons_chart(topic="EV"))
    root = ET.fromstring(out["image_svg"])
    assert len(root.findall("{http://www.w3.org/2000/svg}circle")) == 2


def test_registered(horizons):
    from app.mcp_access import tools
    names = [t.name for t in tools.available_tools()]
    assert "get_horizons" in names and "render_horizons_chart" in names
