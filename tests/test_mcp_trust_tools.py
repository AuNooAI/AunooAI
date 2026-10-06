"""get_trust_signals on the monolith MCP server: listed only when the saas
key is configured, proxies URIs to the saas Skills API, caches answers and
attaches this site's title. The remote call and the local lookup are stubbed."""

import asyncio

import pytest


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    monkeypatch.setenv("APP_URL", "https://example.test")
    monkeypatch.setenv("SAAS_SKILLS_URL", "https://saas.example")
    monkeypatch.setenv("SAAS_SKILLS_KEY", "aunoo_test")


def _entry(url, in_corpus=False):
    return {"url": url, "in_corpus": in_corpus, "source": "example.com",
            "signals": [{"key": "source", "rating": "High", "tone": "pass"}]}


def test_listed_only_when_configured(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "x")
    monkeypatch.delenv("SAAS_SKILLS_URL", raising=False)
    monkeypatch.delenv("SAAS_SKILLS_KEY", raising=False)
    from app.mcp_access import tools
    assert "get_trust_signals" not in [t.name for t in tools.available_tools()]
    monkeypatch.setenv("SAAS_SKILLS_URL", "https://saas.example")
    monkeypatch.setenv("SAAS_SKILLS_KEY", "k")
    assert "get_trust_signals" in [t.name for t in tools.available_tools()]


def test_proxies_caches_and_attaches_local_title(env, monkeypatch):
    from app.mcp_access import trust_tools
    trust_tools._cache.clear()
    calls = []

    async def fake_post(tool, arguments):
        calls.append((tool, arguments))
        return {"truncated": False, "data": {
            "articles": [_entry(u) for u in arguments["urls"]],
            "invalid": [], "tone_key": {"pass": "healthy"}}}

    monkeypatch.setattr(trust_tools, "_post", fake_post)
    monkeypatch.setattr(trust_tools, "_local_titles_sync",
                        lambda uris: {"https://example.com/a": {"title": "Ours", "news_source": "example.com",
                                                                "publication_date": None}})

    out = asyncio.run(trust_tools.get_trust_signals(uris=["https://example.com/a", "https://example.com/b#x"]))
    assert calls[0][0] == "get_trust_signals_for_urls"
    assert calls[0][1]["urls"] == ["https://example.com/a", "https://example.com/b"]
    assert out["rated_by"] == "saas.example"
    assert [a["url"] for a in out["articles"]] == ["https://example.com/a", "https://example.com/b"]
    assert out["articles"][0]["local_article"]["title"] == "Ours"
    assert "local_article" not in out["articles"][1]

    out2 = asyncio.run(trust_tools.get_trust_signals(uri="https://example.com/a"))
    assert len(calls) == 1, "second ask for the same uri must hit the cache"
    assert out2["articles"][0]["cached"] is True


def test_bad_input_and_remote_failures(env, monkeypatch):
    from app.mcp_access import trust_tools
    from app.mcp_access.errors import ToolError
    with pytest.raises(ToolError):
        asyncio.run(trust_tools.get_trust_signals(uris=["not a url"]))

    async def failing(tool, arguments):
        raise ToolError("trust service returned 401: api key not recognised")
    monkeypatch.setattr(trust_tools, "_post", failing)
    trust_tools._cache.clear()
    with pytest.raises(ToolError, match="401"):
        asyncio.run(trust_tools.get_trust_signals(uri="https://example.com/z"))
