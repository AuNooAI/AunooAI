"""The subscriber's benchmark tool is registered and checks its arguments
before it touches the database."""

import asyncio

import pytest

from app.mcp_access import brand_tools as bt
from app.mcp_access.errors import ToolError
from app.mcp_access.tools import TOOLS


def test_registered_with_a_handler():
    assert "get_vendor_benchmark" in TOOLS
    assert bt.HANDLERS["get_vendor_benchmark"] is bt.get_vendor_benchmark
    props = TOOLS["get_vendor_benchmark"].properties
    assert {"vendor", "vendor_id", "market", "market_id", "days", "metrics"} <= set(props)


def test_needs_a_vendor(monkeypatch):
    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(bt, "_module_on", lambda m: None)
    monkeypatch.setattr(bt, "_conn", lambda: _Conn())
    monkeypatch.setattr(bt, "_market_id", lambda conn, market, market_id: 2)
    with pytest.raises(ToolError, match="pass vendor"):
        asyncio.run(bt.get_vendor_benchmark(market_id=2))
