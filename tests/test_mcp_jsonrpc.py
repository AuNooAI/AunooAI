"""The MCP transport on a bare FastAPI app: no database, auth and the tool
registry are stubbed. Checks the wire shapes clients depend on."""

import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    monkeypatch.setenv("APP_URL", "https://example.test")

    from app.mcp_access import auth as mcp_auth, dispatcher, tools, transport
    from app.mcp_access.errors import AuthError

    ctx = mcp_auth.McpAuthContext(username="alice", role="user", auth_kind="api_key", api_key_id=7)

    async def fake_authenticate(header):
        if header == "Bearer good":
            return ctx
        raise AuthError("api key not recognised")

    calls = []

    async def fake_record(ctx_, **fields):
        calls.append(fields)

    async def fake_tool(topic=None, limit=50, **_):
        assert isinstance(limit, int)
        return {"topic": topic, "limit": limit, "articles": [{"title": "t"}]}

    async def boom(**_):
        raise RuntimeError("db down")

    real_resolve = tools.resolve

    def fake_resolve(name):
        if name == "get_topic_articles":
            spec = tools.TOOLS["get_topic_articles"]
            return spec, fake_tool
        if name == "analyze_sentiment_trends":
            return tools.TOOLS["analyze_sentiment_trends"], boom
        return real_resolve(name)

    monkeypatch.setattr(transport, "authenticate", fake_authenticate)
    monkeypatch.setattr(dispatcher, "record_tool_call", fake_record)
    monkeypatch.setattr(tools, "resolve", fake_resolve)

    app = FastAPI()
    app.include_router(transport.router)
    tc = TestClient(app)
    tc.calls = calls
    return tc


def _rpc(client, body, auth="Bearer good"):
    headers = {"content-type": "application/json"}
    if auth:
        headers["authorization"] = auth
    return client.post("/mcp", content=json.dumps(body) if isinstance(body, dict) else body, headers=headers)




def test_parse_error_and_invalid_request(client):
    r = _rpc(client, "{not json")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    r = _rpc(client, {"id": 1, "method": "initialize"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600


def test_initialize_requires_auth_and_points_at_discovery(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, auth=None)
    assert r.status_code == 401
    assert 'resource_metadata="https://example.test/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]
    assert r.json()["error"]["code"] == -32001

    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, auth="Bearer bad")
    assert r.status_code == 401 and "www-authenticate" in r.headers


def test_initialize_ok(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18"}})
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["serverInfo"]["name"].startswith("Aunoo")
    assert "list_capabilities" in res["instructions"]
    assert res["capabilities"]["tools"] == {"listChanged": False}


def test_notification_is_202_without_body(client):
    r = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, auth=None)
    assert r.status_code == 202 and r.content == b""


def test_ping_and_unknown_method(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert r.json() == {"jsonrpc": "2.0", "id": 2, "result": {}}
    r = _rpc(client, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert r.status_code == 404 and r.json()["error"]["code"] == -32601


def test_tools_list_shape(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert "list_capabilities" in names and "get_topic_articles" in names
    tool = next(t for t in r.json()["result"]["tools"] if t["name"] == "search_articles_by_keywords")
    assert tool["inputSchema"]["type"] == "object"
    assert tool["inputSchema"]["required"] == ["keywords"]


def test_tools_call_coerces_and_wraps(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                      "params": {"name": "get_topic_articles", "arguments": {"topic": "AI", "limit": "5"}}})
    assert r.status_code == 200, r.text
    content = r.json()["result"]["content"]
    assert content[0]["type"] == "text"
    payload = json.loads(content[0]["text"])
    assert payload["truncated"] is False
    assert payload["data"]["limit"] == 5
    assert client.calls[-1]["status"] == "ok" and client.calls[-1]["tool_name"] == "get_topic_articles"


def test_tools_call_errors(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                      "params": {"name": "no_such_tool", "arguments": {}}})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32003
    assert client.calls[-1]["status"] == "error"

    r = _rpc(client, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                      "params": {"name": "analyze_sentiment_trends", "arguments": {}}})
    assert r.status_code == 400 and "failed" in r.json()["error"]["message"]
    assert client.calls[-1]["error_code"] == "ToolError"

    r = _rpc(client, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                      "params": {"name": "search_articles_by_keywords", "arguments": {}}})
    assert r.status_code == 400 and "missing required" in r.json()["error"]["message"]


def test_prompts(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 9, "method": "prompts/list"})
    names = [p["name"] for p in r.json()["result"]["prompts"]]
    assert names == ["topic_briefing", "deep_dive", "keyword_scan"]
    r = _rpc(client, {"jsonrpc": "2.0", "id": 10, "method": "prompts/get",
                      "params": {"name": "deep_dive", "arguments": {"query": "chip exports", "topic": "AI"}}})
    msg = r.json()["result"]["messages"][0]
    assert msg["role"] == "user" and "chip exports" in msg["content"][0]["text"]
    r = _rpc(client, {"jsonrpc": "2.0", "id": 11, "method": "prompts/get", "params": {"name": "nope"}})
    assert r.status_code == 404


def test_get_and_delete_probe(client):
    assert client.get("/mcp").status_code == 405
    assert client.delete("/mcp").status_code == 204


def test_cap_payload_is_utf8_safe():
    from app.mcp_access.dispatcher import cap_payload
    big = {"text": "é" * 5000}
    out = cap_payload(big, max_bytes=1024)
    assert out["truncated"] is True
    assert isinstance(out["data"], str)
    out["data"].encode("utf-8")
    assert out["byte_count"] > 1024
