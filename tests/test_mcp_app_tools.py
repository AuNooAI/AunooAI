"""App store tools on the MCP server (docs/APP_STORE_REVIEWS_SPEC.md)."""
import asyncio

import pytest

from app.mcp_access import brand_tools, tools


def test_the_tools_are_registered_and_offered():
    for name in ("get_app_ratings", "get_app_reviews"):
        spec, handler = tools.resolve(name)
        assert spec.name == name and handler is brand_tools.HANDLERS[name]
    assert {"get_app_ratings", "get_app_reviews"} <= {t.name for t in tools.available_tools()}


def test_a_bad_store_is_refused(monkeypatch):
    monkeypatch.setattr(brand_tools, "_module_on", lambda m: None)
    with pytest.raises(brand_tools.ToolError):
        asyncio.run(brand_tools.get_app_reviews(store="itunes"))


def test_ratings_without_a_brand_cover_every_brand_with_apps(monkeypatch):
    monkeypatch.setattr(brand_tools, "_module_on", lambda m: None)

    class _Res:
        def fetchall(self):
            return [(1, "Oviva"), (2, "Noom")]

    class _Conn:
        def execute(self, *a, **k):
            return _Res()

        def close(self):
            pass
    monkeypatch.setattr(brand_tools, "_conn", lambda: _Conn())

    async def fake(bid, session=None):
        return {"brand_id": bid, "configured": True,
                "apps": [{"store": "google_play", "rating": 4.5, "history": [1, 2]}],
                "recent_reviews_30d": {"Google Play": {"5": 3}}}
    import app.routes.brand_watcher_routes as bwr
    monkeypatch.setattr(bwr, "get_brand_app_ratings", fake)
    out = asyncio.run(brand_tools.get_app_ratings())
    assert [b["brand"] for b in out["brands"]] == ["Oviva", "Noom"]
    assert "history" not in out["brands"][0]["apps"][0]
