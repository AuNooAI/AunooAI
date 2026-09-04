"""The tool catalogue: names, JSON schemas, limits, and how each binds to
``AuspexToolsService``.

The first five schemas are the ones the old stdio server in
``app/services/mcp_server.py`` shipped, with ``topic`` made optional where
the service treats a missing topic as "all topics".
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import config
from .errors import ToolError

_TOPIC = {
    "type": "string",
    "description": "Topic name as listed by list_capabilities. Omit for all topics.",
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...] = ()
    timeout: float = config.TOOL_TIMEOUT_SECONDS
    max_bytes: int = config.MAX_RESPONSE_BYTES
    needs_google: bool = False
    # Which Auspex method to call; None means a local handler in this module.
    method: str | None = field(default=None)


_ARTICLE_LIST_BYTES = 64 * 1024
_LLM_TIMEOUT = 90.0

TOOLS: dict[str, ToolSpec] = {
    "list_capabilities": ToolSpec(
        name="list_capabilities",
        description=(
            "Describe this Aunoo site: the topics it tracks, the tools and "
            "prompts available, and who you are connected as. Call this first."
        ),
        properties={},
        timeout=15.0,
    ),
    "search_news": ToolSpec(
        name="search_news",
        description="Search for news articles using TheNewsAPI",
        properties={
            "query": {"type": "string", "description": "Search query for news articles"},
            "max_results": {"type": "integer", "description": "Maximum number of results to return (default: 10)", "default": 10},
            "language": {"type": "string", "description": "Language code (default: en)", "default": "en"},
            "days_back": {"type": "integer", "description": "Number of days back to search (default: 7)", "default": 7},
            "categories": {"type": "array", "items": {"type": "string"}, "description": "News categories to filter by"},
        },
        required=("query",),
        timeout=30.0,
        method="search_news",
    ),
    "get_topic_articles": ToolSpec(
        name="get_topic_articles",
        description="Get recent articles from the database for a topic",
        properties={
            "topic": _TOPIC,
            "limit": {"type": "integer", "description": "Maximum number of articles to return (default: 50)", "default": 50},
            "days_back": {"type": "integer", "description": "Number of days back to search (default: 30)", "default": 30},
        },
        max_bytes=_ARTICLE_LIST_BYTES,
        method="get_topic_articles",
    ),
    "analyze_sentiment_trends": ToolSpec(
        name="analyze_sentiment_trends",
        description="Sentiment distribution for a topic's articles over a period",
        properties={
            "topic": _TOPIC,
            "time_period": {"type": "string", "description": "Time period: 'week', 'month', or 'quarter'", "default": "month", "enum": ["week", "month", "quarter"]},
        },
        method="analyze_sentiment_trends",
    ),
    "get_article_categories": ToolSpec(
        name="get_article_categories",
        description="Article categories and their distribution for a topic",
        properties={"topic": _TOPIC},
        method="get_article_categories",
    ),
    "search_articles_by_keywords": ToolSpec(
        name="search_articles_by_keywords",
        description="Search articles in the database by keywords",
        properties={
            "keywords": {"type": "array", "items": {"type": "string"}, "description": "Keywords to search for"},
            "topic": _TOPIC,
            "limit": {"type": "integer", "description": "Maximum number of results (default: 25)", "default": 25},
        },
        required=("keywords",),
        max_bytes=_ARTICLE_LIST_BYTES,
        method="search_articles_by_keywords",
    ),
    "search_articles_by_categories": ToolSpec(
        name="search_articles_by_categories",
        description="Articles in a topic that fall into the given categories",
        properties={
            "categories": {"type": "array", "items": {"type": "string"}, "description": "Category names, as returned by get_article_categories"},
            "topic": {"type": "string", "description": "Topic name as listed by list_capabilities"},
            "limit": {"type": "integer", "default": 50},
            "days_back": {"type": "integer", "default": 30},
        },
        required=("categories", "topic"),
        max_bytes=_ARTICLE_LIST_BYTES,
        method="search_articles_by_categories",
    ),
    "semantic_search_and_analyze": ToolSpec(
        name="semantic_search_and_analyze",
        description=(
            "Find the articles most relevant to a question and return an AI "
            "analysis of them alongside the articles"
        ),
        properties={
            "query": {"type": "string", "description": "Question or subject to research"},
            "topic": _TOPIC,
            "analysis_type": {"type": "string", "default": "comprehensive", "enum": ["comprehensive", "summary", "trends"]},
            "limit": {"type": "integer", "default": 50},
        },
        required=("query",),
        timeout=_LLM_TIMEOUT,
        max_bytes=_ARTICLE_LIST_BYTES,
        method="semantic_search_and_analyze",
    ),
    "enhanced_database_search": ToolSpec(
        name="enhanced_database_search",
        description=(
            "Natural-language search over the article database. Parses the "
            "query, combines vector and keyword search, and reranks."
        ),
        properties={
            "query": {"type": "string", "description": "Natural-language query"},
            "topic": _TOPIC,
            "limit": {"type": "integer", "default": 50},
        },
        required=("query",),
        timeout=_LLM_TIMEOUT,
        max_bytes=_ARTICLE_LIST_BYTES,
        method="enhanced_database_search",
    ),
    "follow_up_query": ToolSpec(
        name="follow_up_query",
        description="Refine an earlier question with a follow-up and get a fresh analysis",
        properties={
            "original_query": {"type": "string"},
            "follow_up": {"type": "string"},
            "topic": {"type": "string", "description": "Topic name as listed by list_capabilities"},
            "context_articles": {"type": "array", "items": {"type": "object"}, "description": "Optional articles from a previous result to keep in context"},
        },
        required=("original_query", "follow_up", "topic"),
        timeout=_LLM_TIMEOUT,
        method="follow_up_query",
    ),
    "google_web_search": ToolSpec(
        name="google_web_search",
        description="Web search through Google Programmable Search (only when configured on this site)",
        properties={
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        required=("query",),
        timeout=30.0,
        needs_google=True,
        method="google_web_search",
    ),
}


def available_tools() -> list[ToolSpec]:
    google = config.google_search_configured()
    return [t for t in TOOLS.values() if google or not t.needs_google]


def input_schema(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(spec.properties),
        "required": list(spec.required),
    }


def get_spec(name: str) -> ToolSpec:
    spec = TOOLS.get(name)
    if spec is None or (spec.needs_google and not config.google_search_configured()):
        raise ToolError(f"unknown tool: {name!r}")
    return spec


async def list_capabilities(ctx=None) -> dict[str, Any]:
    from app.database import get_database_instance
    from . import recipes

    topics = await asyncio.to_thread(lambda: get_database_instance().get_topics())
    return {
        "server": config.server_name(),
        "base_url": config.base_url(),
        "connected_as": getattr(ctx, "username", None),
        "auth_kind": getattr(ctx, "auth_kind", None),
        "topics": list(topics or []),
        "tools": [t.name for t in available_tools()],
        "prompts": [r["name"] for r in recipes.list_recipes()],
        "notes": (
            "Pass a topic name exactly as listed here. Tools that take no topic "
            "search across every topic."
        ),
    }


def resolve(name: str) -> tuple[ToolSpec, Callable[..., Awaitable[dict[str, Any]]]]:
    spec = get_spec(name)
    if spec.method is None:
        if name == "list_capabilities":
            return spec, list_capabilities
        raise ToolError(f"tool {name!r} has no handler")
    from app.services.auspex_tools import get_auspex_tools_service
    fn = getattr(get_auspex_tools_service(), spec.method, None)
    if fn is None:
        raise ToolError(f"tool {name!r} is not available on this site")
    return spec, fn
