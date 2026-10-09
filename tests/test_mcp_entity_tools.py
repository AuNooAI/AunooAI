"""list_entities and get_entity on the monolith MCP server: registered, refuse
when the entity layer is switched off, and ask for a name. The queries run
against the live tables and are checked by hand; these cover the gates."""

import asyncio

import pytest


@pytest.fixture
def entity(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    from app.mcp_access import entity_tools
    return entity_tools


def test_registered(entity):
    from app.mcp_access import tools
    names = [t.name for t in tools.available_tools()]
    assert "list_entities" in names and "get_entity" in names


def test_refuses_when_layer_off(entity, monkeypatch):
    from app.mcp_access.errors import ToolError
    monkeypatch.setenv("ENTITY_INTELLIGENCE_ENABLED", "false")
    with pytest.raises(ToolError, match="switched off"):
        asyncio.run(entity.list_entities())
    with pytest.raises(ToolError, match="switched off"):
        asyncio.run(entity.get_entity(entity="Acme"))


def test_needs_a_name(entity, monkeypatch):
    from app.mcp_access.errors import ToolError
    monkeypatch.setenv("ENTITY_INTELLIGENCE_ENABLED", "true")
    with pytest.raises(ToolError, match="needs an entity"):
        asyncio.run(entity.get_entity())
